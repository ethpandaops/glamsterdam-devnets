#!/usr/bin/env python3
"""Explicit controller actions for the qualified H v3 archive; never start clients."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

from botocore.exceptions import ClientError
from storage import BUCKET, client
from upload import PART_SIZE, V3_HEAD_KEY, validate_v3_head_proof

ROOT = Path.home() / '.local/state/pbt-1-run/v3-head-publication'
REMOTE = '/data/pbt-1/v3-head-publication'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-i',
       str(Path.home() / '.ssh/devops_eth2_shared_key'), 'root@159.89.21.191']
UPLOAD_UNIT = 'pbt-1-v3-head-upload'


def save(name, value):
    path = ROOT / name
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def ssh(args, data=None):
    return subprocess.check_output(SSH + [shlex.join(args)], input=data,
                                   stderr=subprocess.PIPE, timeout=90)


def evidence():
    raw = ssh(['cat', '/data/pbt-1/qualification/result.json'])
    proof = json.loads(raw)
    conversion = json.loads(ssh(['cat', '/data/pbt-1/v3-head-upgrade/conversion-complete.json']))
    validate_v3_head_proof(proof, conversion)
    return raw, proof, conversion


def preflight():
    raw, proof, conversion = evidence()
    job = {'profile': 'erigon-v3-head', 'client': 'erigon', 'head': 24503958,
           'key': V3_HEAD_KEY, 'qualification_sha256': hashlib.sha256(raw).hexdigest()}
    # The same stopped-source guards also execute immediately before streaming.
    code = """import importlib.util,json,pathlib,sys
sys.path.insert(0,'/data/pbt-1')
s=importlib.util.spec_from_file_location('stream','/data/pbt-1/upload-v3-head-stream.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.ROOT=pathlib.Path('/data/pbt-1/v3-head-publication')
db,locks=m.require_v3_head_source(json.load(sys.stdin))
print('qualified H source stopped')
"""
    ssh(['python3', '-c', code], json.dumps(job).encode())
    return job, proof, conversion


def authorize(s3):
    assert not (ROOT / 'upload-job.json').exists(), 'Existing authorization requires inspection'
    job, proof, conversion = preflight()
    try:
        s3.head_object(Bucket=BUCKET, Key=V3_HEAD_KEY)
    except ClientError as exc:
        assert exc.response['Error']['Code'] in ('404', 'NoSuchKey', 'NotFound')
    else:
        raise RuntimeError('Immutable H destination already exists')
    job['upload_id'] = s3.create_multipart_upload(
        Bucket=BUCKET, Key=V3_HEAD_KEY, ContentType='application/zstd',
        Metadata={'head': '24503958', 'commitment-format': 'v3',
                  'qualification-sha256': job['qualification_sha256']})['UploadId']
    save('upload-job.json', job)
    save('qualification.json', proof)
    save('conversion.json', conversion)
    scoped = {**job, 'urls': [s3.generate_presigned_url('upload_part', Params={
        'Bucket': BUCKET, 'Key': V3_HEAD_KEY, 'UploadId': job['upload_id'],
        'PartNumber': n}, ExpiresIn=86400) for n in range(1, 8001)]}
    code = """import os,pathlib,sys
p=pathlib.Path('/data/pbt-1/v3-head-publication')
p.mkdir(mode=0o700,exist_ok=True)
fd=os.open(p/'upload-authorization.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'wb') as f:f.write(sys.stdin.buffer.read())
"""
    ssh(['python3', '-c', code], json.dumps(scoped).encode())
    save('authorized.json', {'time': time.time(), 'key': V3_HEAD_KEY})


def validate_parts(report, job):
    assert report['client'] == 'erigon' and report['head'] == 24503958
    assert report['key'] == job['key'] == V3_HEAD_KEY
    assert report['upload_id'] == job['upload_id']
    parts = report['parts']
    assert 0 < len(parts) <= 8000
    assert [p['PartNumber'] for p in parts] == list(range(1, len(parts) + 1))
    assert all(p['bytes'] == PART_SIZE for p in parts[:-1])
    assert 0 < parts[-1]['bytes'] <= PART_SIZE
    assert sum(p['bytes'] for p in parts) == report['archive_bytes']
    for digest in [report['archive_sha256'], *(p['sha256'] for p in parts)]:
        assert len(digest) == 64 and all(c in '0123456789abcdef' for c in digest)
    return [{'PartNumber': p['PartNumber'], 'ETag': p['ETag']} for p in parts]


def observe():
    """Read unit state and non-secret progress, never the scoped URLs."""
    code = """import json,pathlib,subprocess
base=pathlib.Path('/data/pbt-1');result={'units':{}}
for name in ('pbt-1-v3-head-upgrade','pbt-1-worker-qualification','pbt-1-v3-head-upload'):
 text=subprocess.check_output(['systemctl','show',name,'-p','ActiveState','-p','SubState','-p','MainPID','-p','Result','-p','LoadState'],text=True)
 result['units'][name]=dict(line.split('=',1) for line in text.splitlines())
for key,path in (('conversion','v3-head-upgrade/status.json'),('qualification','qualification/status.json'),('upload','v3-head-publication/status.json')):
 p=base/path
 value=json.loads(p.read_text()) if p.exists() else {}
 result[key]={k:value[k] for k in ('phase','time','uploaded_bytes','parts','archive_bytes') if k in value}
result['conversion_complete']=(base/'v3-head-upgrade/conversion-complete.json').exists()
result['qualification_complete']=(base/'qualification/result.json').exists()
result['upload_complete']=(base/'v3-head-publication/upload-complete-parts.json').exists()
print(json.dumps(result))
"""
    return json.loads(ssh(['python3', '-c', code]))


def workers_ready(observation):
    states = [observation['units'][name] for name in
              ('pbt-1-v3-head-upgrade', 'pbt-1-worker-qualification')]
    assert all(s['ActiveState'] != 'failed' for s in states), 'A preparation unit failed'
    assert observation['conversion'].get('phase') != 'failed', 'Conversion failed'
    if any(s['ActiveState'] in ('active', 'activating', 'deactivating') for s in states):
        return False
    assert all(s['ActiveState'] == 'inactive' and s['MainPID'] == '0'
               and s['Result'] == 'success' for s in states), 'Unexpected stopped preparation state'
    assert observation['conversion_complete'] and observation['qualification_complete'], 'Stopped without required proofs'
    return True


def observe_until(predicate, phase, deadline):
    while True:
        assert time.monotonic() < deadline, phase + ' exceeded its wait limit'
        try:
            observation = observe()
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            # A lost observation is not a stopped remote job. Re-poll the same
            # named units; never create a second uploader after an SSH timeout.
            save('status.json', {'phase': phase, 'time': time.time(), 'observation': 'temporarily_unavailable'})
            time.sleep(30)
            continue
        if predicate(observation):
            return observation
        save('status.json', {'phase': phase, 'time': time.time(), 'remote': observation})
        time.sleep(30)


def upload_finished(observation):
    unit = observation['units'][UPLOAD_UNIT]
    assert unit['ActiveState'] != 'failed' and unit['Result'] == 'success', 'Native archive upload failed'
    assert observation['upload'].get('phase') != 'failed', 'Archive upload recorded a failure'
    if unit['MainPID'] != '0' or unit['SubState'] in ('running', 'start'):
        return False
    assert unit['ActiveState'] == 'active' and unit['SubState'] == 'exited', 'Uploader stopped unexpectedly'
    assert observation['upload_complete'], 'Uploader exited without completed parts'
    return True


def automatic():
    """Wait, authorize once, stream once, verify the full archive and publish."""
    assert not (ROOT / 'upload-job.json').exists(), 'Prior authorization requires inspection'
    state = observe_until(workers_ready, 'waiting_for_H_conversion_and_reopen', time.monotonic() + 86400)
    assert state['units'][UPLOAD_UNIT]['LoadState'] == 'not-found', 'Existing uploader requires inspection'
    # Full existing preflight runs inside authorize before any storage mutation.
    storage = client()
    authorize(storage)
    save('status.json', {'phase': 'starting_H_upload', 'time': time.time(), 'unit': UPLOAD_UNIT})
    try:
        ssh(['systemd-run', '--unit=' + UPLOAD_UNIT, '--property=Type=exec',
             '--property=RemainAfterExit=yes', '--property=MemoryMax=16G',
             '--property=CPUQuota=400%', '--property=TimeoutStopSec=1800',
             '--property=SendSIGKILL=no', '/usr/bin/python3', '-u',
             '/data/pbt-1/upload-v3-head-stream.py', '--v3-head'])
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        # Observe the same unit: the start may have reached the VM even though
        # the SSH reply was lost. Do not retry the mutation.
        save('status.json', {'phase': 'observing_H_upload_start', 'time': time.time(), 'unit': UPLOAD_UNIT})
    observe_until(upload_finished, 'streaming_H_archive', time.monotonic() + 86400)
    ssh(['systemctl', 'stop', UPLOAD_UNIT])  # RemainAfterExit retains the exit proof until observed.
    finish(storage)


def finish(s3):
    job = json.loads((ROOT / 'upload-job.json').read_text())
    report = json.loads(ssh(['cat', REMOTE + '/upload-complete-parts.json']))
    parts = validate_parts(report, job)
    raw, proof, conversion = evidence()
    assert hashlib.sha256(raw).hexdigest() == job['qualification_sha256']
    if not (ROOT / 'multipart-completed.json').exists():
        actual = []
        for page in s3.get_paginator('list_parts').paginate(
                Bucket=BUCKET, Key=V3_HEAD_KEY, UploadId=job['upload_id']):
            actual.extend(page.get('Parts', []))
        assert [(p['PartNumber'], p['ETag'], p['Size']) for p in actual] == [
            (p['PartNumber'], p['ETag'], p['bytes']) for p in report['parts']]
        result = s3.complete_multipart_upload(
            Bucket=BUCKET, Key=V3_HEAD_KEY, UploadId=job['upload_id'],
            MultipartUpload={'Parts': parts})
        save('multipart-completed.json', {'time': time.time(), 'etag': result['ETag']})
    head = s3.head_object(Bucket=BUCKET, Key=V3_HEAD_KEY)
    assert head['ContentLength'] == report['archive_bytes']
    assert head['Metadata']['qualification-sha256'] == job['qualification_sha256']
    digest = hashlib.sha256()
    length = last_saved = 0
    with s3.get_object(Bucket=BUCKET, Key=V3_HEAD_KEY, IfMatch=head['ETag'])['Body'] as body:
        for chunk in iter(lambda: body.read(8 * 1024**2), b''):
            digest.update(chunk)
            length += len(chunk)
            if length - last_saved >= 1024**3:
                save('status.json', {'phase': 'full_remote_sha256_readback',
                                     'bytes': length, 'total': report['archive_bytes'],
                                     'time': time.time()})
                last_saved = length
    assert length == report['archive_bytes'] and digest.hexdigest() == report['archive_sha256']
    genesis_raw = ssh(['cat', '/data/pbt-1/qualification/config/genesis.json'])
    assert hashlib.sha256(genesis_raw).hexdigest() == (
        '3efbcddc03af8e09a40d4a0440e656bc43340e5374e3b4336f60782fd607fd0a')
    report.pop('upload_id')
    report.update(full_remote_sha256_verified=True, verified_at=time.time())
    metadata = {
        'client': 'erigon', 'head': 24503958, 'head_hash': proof['head_hash'],
        'state_root': proof['state_root'], 'commitment_format': 'v3', 'tree': 'MPT',
        'pbt_migration_performed': False, 'erigon_commit': proof['commit'],
        'image': proof['image'], 'archive_bytes': length, 'archive_sha256': digest.hexdigest(),
        'qualification_sha256': job['qualification_sha256'],
        'native_reopen_verified': True, 'full_remote_sha256_verified': True,
        'post_conversion_bal_validation': 'Three sampled bodies; no new full-range audit',
        'genesis_time': None, 'launch_authorized': False,
    }
    if conversion.get('converter_build') is not None:
        metadata['converter_build'] = conversion['converter_build']
    prefix = V3_HEAD_KEY.rsplit('/', 1)[0] + '/'
    for name, obj in {
        '_snapshot_integrity.json': report, '_snapshot_reopen.json': proof,
        '_snapshot_conversion.json': conversion, '_snapshot_genesis.json': json.loads(genesis_raw),
        '_snapshot_metadata.json': metadata,
    }.items():
        s3.put_object(Bucket=BUCKET, Key=prefix + name,
                      Body=(json.dumps(obj, indent=2) + '\n').encode(),
                      ContentType='application/json')
    save('release.json', metadata)
    ssh(['rm', REMOTE + '/upload-authorization.json'])
    save('status.json', {'phase': 'published_verified', 'time': time.time(),
                         'url': 'https://shadowfork-images.ethpandaops.io/' + V3_HEAD_KEY})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check', 'authorize', 'finish', 'auto'])
    args = parser.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (ROOT / 'controller.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == 'check':
            preflight()
            print('Qualified H source is stopped; no storage mutation performed')
        elif args.action == 'authorize':
            authorize(client())
        elif args.action == 'auto':
            try:
                automatic()
            except Exception as exc:
                save('status.json', {'phase': 'failed', 'time': time.time(), 'error_class': type(exc).__name__})
                raise
        else:
            finish(client())


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # SDK and SSH exceptions may contain scoped URLs; retain only the class.
        print('Publication stopped:', type(exc).__name__, '(inspect private evidence)')
        raise SystemExit(1)
