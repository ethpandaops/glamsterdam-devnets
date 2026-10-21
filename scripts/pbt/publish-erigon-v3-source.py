#!/usr/bin/env python3
"""Controller: advance qualified v3 source through reopen, upload and readback.

Scoped multipart URLs are the only storage credentials sent to Erigon-1.
Stops on any failed phase; never retries a database mutation automatically.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

from botocore.exceptions import ClientError
from storage import BUCKET, client

ROOT = Path.home() / '.local/state/pbt-1-run/v3-source'
REMOTE = '/data/pbt-1/v3-source-upgrade'
KEY = 'pbt-1/20261020-erigon-v3-source/erigon/24452538/snapshot.tar.zst'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-i',
       str(Path.home() / '.ssh/devops_eth2_shared_key'), 'root@164.92.239.96']


def save(name, value):
    path = ROOT / name
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def ssh(args, data=None):
    return subprocess.check_output(SSH + [shlex.join(args)], input=data, text=True,
                                   stderr=subprocess.PIPE, timeout=90).strip()


def read(name):
    return json.loads(ssh(['cat', REMOTE + '/' + name]))


def start(unit, args, memory):
    fields = dict(line.split('=', 1) for line in ssh([
        'systemctl', 'show', unit, '-p', 'LoadState', '-p', 'ActiveState']).splitlines())
    if fields.get('LoadState') == 'loaded':
        assert fields['ActiveState'] != 'failed', unit + ' failed; inspect before retry'
        return
    ssh(['systemd-run', '--unit=' + unit, '--property=MemoryMax=' + memory,
         '--property=CPUQuota=400%', *args])


def authorize(s3):
    assert not (ROOT / 'upload-job.json').exists(), 'Inspect already authorized multipart upload'
    proof = read('upload-ready.json')
    assert proof['stopped'] and proof['native_reopen_verified'] and proof['v3_state_verified']
    assert int(proof['head']['number'], 16) == 24452538
    try:
        s3.head_object(Bucket=BUCKET, Key=KEY)
    except ClientError as exc:
        assert exc.response['Error']['Code'] in ('404', 'NoSuchKey', 'NotFound')
    else:
        raise RuntimeError('Immutable snapshot destination already exists')
    upload_id = s3.create_multipart_upload(
        Bucket=BUCKET, Key=KEY, ContentType='application/zstd',
        Metadata={'head': '24452538', 'commitment-format': 'v3',
                  'erigon-commit': proof['commit']})['UploadId']
    job = {'profile': 'erigon-v3-source', 'client': 'erigon', 'head': 24452538,
           'key': KEY, 'upload_id': upload_id}
    save('upload-job.json', job)
    job['urls'] = [s3.generate_presigned_url('upload_part', Params={
        'Bucket': BUCKET, 'Key': KEY, 'UploadId': upload_id, 'PartNumber': number},
        ExpiresIn=86400) for number in range(1, 8001)]
    write_code = ("import pathlib,sys;p=pathlib.Path(" + repr(REMOTE + '/upload-authorization.json')
                  + ");p.write_text(sys.stdin.read());p.chmod(0o600)")
    ssh(['python3', '-c', write_code], json.dumps(job))
    save('authorized.json', {'time': time.time(), 'key': KEY})


def finish(s3):
    job = json.loads((ROOT / 'upload-job.json').read_text())
    report = read('upload-complete-parts.json')
    proof = read('upload-ready.json')
    assert report['key'] == KEY == job['key'] and report['upload_id'] == job['upload_id']
    assert proof['stopped'] and proof['native_reopen_verified'] and proof['v3_state_verified']
    parts = report['parts']
    assert [p['PartNumber'] for p in parts] == list(range(1, len(parts) + 1))
    assert sum(p['bytes'] for p in parts) == report['archive_bytes']
    if not (ROOT / 'multipart-completed.json').exists():
        result = s3.complete_multipart_upload(
            Bucket=BUCKET, Key=KEY, UploadId=job['upload_id'],
            MultipartUpload={'Parts': [{k: p[k] for k in ('PartNumber', 'ETag')} for p in parts]})
        save('multipart-completed.json', {'time': time.time(), 'etag': result['ETag']})
    head = s3.head_object(Bucket=BUCKET, Key=KEY)
    assert head['ContentLength'] == report['archive_bytes']
    digest = hashlib.sha256()
    length = 0
    last_saved = 0
    response = s3.get_object(Bucket=BUCKET, Key=KEY)
    with response['Body'] as body:
        for chunk in iter(lambda: body.read(8 * 1024**2), b''):
            digest.update(chunk)
            length += len(chunk)
            if length - last_saved >= 1024**3:
                save('status.json', {'phase': 'full_remote_sha256_readback',
                                     'bytes': length, 'total': report['archive_bytes'],
                                     'time': time.time()})
                last_saved = length
    assert length == report['archive_bytes'] and digest.hexdigest() == report['archive_sha256']
    report.pop('upload_id')
    report['full_remote_sha256_verified'] = True
    report['verified_at'] = time.time()
    metadata = {
        'client': 'erigon', 'head': 24452538, 'head_hash': proof['head']['hash'],
        'state_root': proof['head']['stateRoot'], 'commitment_format': 'v3',
        'tree': 'MPT', 'pbt_migration_performed': False,
        'source': 'jochemnet/erigon/24452538/snapshot-pruned.tar.zst',
        'erigon_commit': proof['commit'], 'binary_sha256': proof['binary_sha256'],
        'archive_bytes': report['archive_bytes'], 'archive_sha256': report['archive_sha256'],
        'native_reopen_verified': True, 'full_remote_sha256_verified': True,
        'archive_excludes': report['archive_excludes'],
        'notes': 'Original source block, upgraded to v3 MPT commitments. No preparation or workload blocks replayed. Use the pinned binary and preserve the source fork schedule.',
    }
    prefix = KEY.rsplit('/', 1)[0] + '/'
    objects = {'_snapshot_metadata.json': metadata, '_snapshot_integrity.json': report,
               '_snapshot_reopen.json': proof, '_snapshot_startup.json': read('native-open-started.json'),
               '_snapshot_conversion.json': read('conversion-complete.json')}
    for name, obj in objects.items():
        s3.put_object(Bucket=BUCKET, Key=prefix + name, Body=(json.dumps(obj, indent=2) + '\n').encode(),
                      ContentType='application/json')
    # Preserve the fork configuration alongside the snapshot. This contains no
    # runtime JWT or node keys.
    genesis = json.loads(ssh(['cat', '/data/pbt-1/pbt-1-source-genesis.json']))
    s3.put_object(Bucket=BUCKET, Key=prefix + '_snapshot_genesis.json',
                  Body=(json.dumps(genesis, indent=2) + '\n').encode(), ContentType='application/json')
    ssh(['rm', REMOTE + '/upload-authorization.json'])
    save('release.json', metadata)
    save('status.json', {'phase': 'published_verified', 'time': time.time(),
                         'url': 'https://shadowfork-images.ethpandaops.io/' + KEY})


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'publish.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (ROOT / 'release.json').exists():
            return
        while True:
            remote = read('status.json')
            phase = remote['phase']
            save('status.json', {'phase': phase, 'remote': remote, 'time': time.time()})
            assert phase != 'failed', remote.get('error', 'Remote job failed')
            if phase == 'converted_pending_native_reopen':
                start('pbt-1-v3-source-qualification',
                      ['python3', '-u', '/data/pbt-1/verify-erigon-v3-source.py'], '2G')
            elif phase == 'v3_source_verified_stopped':
                if not (ROOT / 'authorized.json').exists():
                    authorize(client())
                start('pbt-1-v3-source-upload',
                      ['python3', '-u', '/data/pbt-1/upload-v3-source.py'], '4G')
            elif phase == 'awaiting_upload_verification':
                finish(client())
                return
            time.sleep(30)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        save('status.json', {'phase': 'failed', 'time': time.time(),
                             'error_type': type(exc).__name__,
                             'error': str(exc) if isinstance(exc, AssertionError) else 'Inspect private controller journal'})
        raise
