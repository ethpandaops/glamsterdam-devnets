#!/usr/bin/env python3
"""Check the published N release; --stage writes private Ansible GET jobs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from botocore.exceptions import ClientError
from storage import BUCKET, client

HERE = Path(__file__).resolve().parent
ROOT = Path.home() / '.local/state/pbt-1-run/migration-inputs'
spec = importlib.util.spec_from_file_location('inputs', HERE / 'download-migration-inputs.py')
inputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs)


def release(s3):
    response = s3.get_object(Bucket=BUCKET, Key=inputs.PREFIX + 'release.json')
    with response['Body'] as body:
        value = json.loads(body.read())
    inputs.validate_release(value)
    for name, item in value['files'].items():
        head = s3.head_object(Bucket=BUCKET, Key=item['key'])
        assert head['ContentLength'] == item['bytes'] and head['ETag'] == item['etag']
        assert head['Metadata']['sha256'] == item['sha256']
        assert head['Metadata']['proof-sha256'] == value['proof_sha256']
    return value


def stage(s3, value):
    destination = ROOT / 'ansible-vars.json'
    assert not destination.exists(), 'Prior authorization requires inspection'
    jobs = {}
    for host in inputs.WORKERS:
        jobs[host] = {'host': host, 'release': value, 'release_canonical_sha256': inputs.digest(value),
            'downloader_sha256': hashlib.sha256((HERE / 'download-migration-inputs.py').read_bytes()).hexdigest(),
            'range_reader_sha256': hashlib.sha256((HERE / 'stream_verified_archive.py').read_bytes()).hexdigest(),
            'urls': {name: s3.generate_presigned_url('get_object', Params={
                'Bucket': BUCKET, 'Key': value['files'][name]['key']}, ExpiresIn=86400)
                for name in inputs.names(host)}}
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    inputs.save(destination, {'pbt_migration_input_jobs': jobs})
    print('Private seven-worker jobs staged; no remote downloads started.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', action='store_true')
    args = parser.parse_args()
    try:
        s3 = client()
        value = release(s3)
        if args.stage:
            stage(s3, value)
        else:
            print(json.dumps({'phase': 'verified_release_ready', 'anchor': value['anchor'],
                              'workers': {host: list(inputs.names(host)) for host in inputs.WORKERS}}))
    except ClientError as exc:
        if not args.stage and exc.response['Error']['Code'] in ('NoSuchKey', '404', 'NotFound'):
            print(json.dumps({'phase': 'waiting_for_verified_shared_release', 'authorized': False}))
        else:
            raise SystemExit(type(exc).__name__ + ': publication/input authorization needs inspection') from None
