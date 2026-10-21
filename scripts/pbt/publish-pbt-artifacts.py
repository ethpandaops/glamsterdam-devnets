#!/usr/bin/env python3
"""Preserve the native-verified N artifact pair using scoped multipart uploads.

Controller: check (read-only), authorize, finish. Worker: stream.
No automatic retries of whole jobs, exporter cleanup, client startup or launch.
Account credentials stay on the controller. The worker receives only scoped
part URLs. Release metadata is written after full remote SHA-256 readback.
"""
import argparse
import base64
import concurrent.futures
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import socket
import subprocess
import time
import urllib.request

BASE = Path('/data/pbt-1')
ARTIFACTS = BASE / 'artifacts-24453558'
EXPORT_ONLY = os.environ.get('PBT_ARTIFACT_EXPORT_ONLY') == '1'
PROOF = BASE / 'pbt-export-24453558' / ('export-ready.json' if EXPORT_ONLY else 'complete.json')
REMOTE = BASE / 'pbt-artifact-publication'
LOCAL = Path.home() / '.local/state/pbt-1-run/artifact-publication'
FILES = ('pbt-snapshot.bin', 'framed.bin', 'pbt-snapshot.meta.json')
PREFIX = 'pbt-1/20261020-pbt-anchor-24453558/'
PART_SIZE = 64 * 1024**2
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-i',
       str(Path.home() / '.ssh/devops_eth2_shared_key'), 'root@164.92.239.96']
COMMIT = '372df0e68f52f9975370bff38dee6e41aefff0d7'
BLOCK_HASH = '0x331c54fd1b37302697157dec30d2a1e0a13682843301f60d8ebac004f8bc4155'
STATE_ROOT = '0x90fe96f02a1d1009e48ccfb82d15bdf5aa130907acd6c4ebe2f2624e5a911260'
BINARY_SHA = '7d3c5beb8b985d54400c10cb09d6381860da387e85a8a74f0336795f08d025f4'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def save(root, name, value):
    path = root / name
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def valid_sha(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def validate_proof(proof):
    expected_status = 'native_export_passed_independent_verification_deferred' if EXPORT_ONLY else 'native_export_and_verification_passed'
    require(proof['status'] == expected_status, 'Wrong export qualification mode')
    if EXPORT_ONLY:
        require(proof.get('independent_mpt_reconstruction_verified') is False
                and proof.get('verification_deferred_by_user') is True, 'Missing explicit verification deferral')
    require(proof['anchor'] == 24453558 and proof['block_hash'] == BLOCK_HASH
            and proof['mpt_state_root'] == STATE_ROOT, 'Wrong artifact anchor')
    require(proof['source'] == '/data/pbt-1/rehearsal-24453558/erigon', 'Wrong exporter source')
    require(proof['source_commit'] == COMMIT and proof['binary_sha256'] == BINARY_SHA, 'Wrong native build')
    meta = proof['metadata']
    require(meta['block'] == 24453558 and meta['blockHash'] == BLOCK_HASH
            and meta['stateRoot'] == STATE_ROOT and meta['chainId'] == '1'
            and meta['hashSuite'] == 'blake3', 'Wrong artifact metadata')
    require(proof['shadowfork_finality_established'] is False
            and proof['cross_client_imports_verified'] is False, 'Unexpected qualification claims')
    require(set(proof['artifacts']) == set(FILES), 'Unexpected artifact set')
    for item in proof['artifacts'].values():
        require(type(item['bytes']) is int and item['bytes'] > 0
                and math.ceil(item['bytes'] / PART_SIZE) <= 10000, 'Invalid artifact size')
        require(valid_sha(item['sha256']), 'Invalid artifact checksum')


def identity(path):
    require(path.is_file() and not path.is_symlink(), 'Artifact must be a regular file')
    st = path.stat()
    return {'inode': st.st_ino, 'bytes': st.st_size, 'mtime_ns': st.st_mtime_ns}


def validate_files(proof):
    for name in FILES:
        require(identity(ARTIFACTS / name) == {
            k: proof['artifacts'][name][k] for k in ('inode', 'bytes', 'mtime_ns')},
            'Artifact identity changed: ' + name)


def remote_readiness():
    require(socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1', 'Wrong host')
    raw = PROOF.read_bytes()
    proof = json.loads(raw)
    validate_proof(proof)
    validate_files(proof)
    for phase in (('export',) if EXPORT_ONLY else ('export', 'verify')):
        result = json.loads((PROOF.parent / (phase + '.json')).read_text())
        require(result['exit_code'] == 0 and result['binary_sha256'] == BINARY_SHA,
                'Missing native phase evidence: ' + phase)
    return {'proof_sha256': digest(raw), 'proof': proof}


def ssh(args, data=None):
    return subprocess.check_output(SSH + [shlex.join(args)], input=data,
                                   stderr=subprocess.PIPE, timeout=90)


def check():
    evidence = json.loads(ssh(['python3', str(BASE / 'publish-pbt-artifacts.py'), 'worker-check']))
    validate_proof(evidence['proof'])
    return evidence


def require_absent(s3, key):
    from botocore.exceptions import ClientError
    from storage import BUCKET
    try:
        s3.head_object(Bucket=BUCKET, Key=key)
    except ClientError as exc:
        require(exc.response['Error']['Code'] in ('404', 'NoSuchKey', 'NotFound'), 'Storage check failed')
    else:
        raise RuntimeError('Immutable artifact destination already exists')


def put_release(s3, raw):
    from storage import BUCKET
    # The controller's botocore predates the IfNoneMatch API parameter. Add the
    # standard conditional header before signing, as documented by R2:
    # https://developers.cloudflare.com/r2/examples/aws/custom-header/
    def condition(params, **kwargs):
        params['headers']['If-None-Match'] = '*'
    event = 'before-call.s3.PutObject'
    s3.meta.events.register(event, condition)
    try:
        return s3.put_object(Bucket=BUCKET, Key=PREFIX + 'release.json',
                             Body=raw, ContentType='application/json')
    finally:
        s3.meta.events.unregister(event, condition)


def authorize(s3):
    from storage import BUCKET
    require(not (LOCAL / 'authorization-started.json').exists(), 'Prior authorization requires inspection')
    evidence = check()  # Must pass before any multipart storage mutation.
    for name in (*FILES, 'release.json'):
        require_absent(s3, PREFIX + name)
    save(LOCAL, 'authorization-started.json', {'time': time.time(), 'proof_sha256': evidence['proof_sha256']})
    job = {**evidence, 'files': {}, 'prefix': PREFIX, 'part_size': PART_SIZE}
    save(LOCAL, 'job.json', job)
    scoped = {**job, 'files': {}}
    for name in FILES:
        item = evidence['proof']['artifacts'][name]
        key = PREFIX + name
        upload = s3.create_multipart_upload(Bucket=BUCKET, Key=key,
                    ContentType='application/json' if name.endswith('.json') else 'application/octet-stream',
                    Metadata={'sha256': item['sha256'], 'anchor': '24453558',
                              'proof-sha256': evidence['proof_sha256']})['UploadId']
        info = {'key': key, 'upload_id': upload, 'bytes': item['bytes'], 'sha256': item['sha256']}
        job['files'][name] = info
        save(LOCAL, 'job.json', job)
        scoped['files'][name] = {**info, 'urls': [s3.generate_presigned_url('upload_part', Params={
            'Bucket': BUCKET, 'Key': key, 'UploadId': upload, 'PartNumber': n}, ExpiresIn=86400)
            for n in range(1, math.ceil(item['bytes'] / PART_SIZE) + 1)]}
    code = """import os,pathlib,sys
p=pathlib.Path('/data/pbt-1/pbt-artifact-publication');p.mkdir(mode=0o700,exist_ok=True)
fd=os.open(p/'authorization.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'wb') as out:out.write(sys.stdin.buffer.read())
"""
    ssh(['python3', '-c', code], json.dumps(scoped).encode())
    save(LOCAL, 'status.json', {'phase': 'authorized_not_started', 'time': time.time()})


def put_part(url, number, data):
    for attempt in range(6):
        try:
            request = urllib.request.Request(url, data=data, method='PUT',
                        headers={'Content-MD5': base64.b64encode(hashlib.md5(data).digest()).decode()})
            with urllib.request.urlopen(request, timeout=600) as response:
                require(response.status == 200, 'Part upload rejected')
                return {'PartNumber': number, 'ETag': response.headers['ETag'],
                        'bytes': len(data), 'sha256': digest(data)}
        except Exception:
            if attempt == 5:
                raise RuntimeError('Part upload failed after six attempts') from None
            time.sleep(min(2**attempt, 30))


def stream():
    job = json.loads((REMOTE / 'authorization.json').read_text())
    require(job['prefix'] == PREFIX and job['part_size'] == PART_SIZE, 'Wrong upload profile')
    evidence = remote_readiness()
    require(evidence == {k: job[k] for k in ('proof', 'proof_sha256')}, 'Export proof changed')
    require(set(job['files']) == set(FILES), 'Incomplete upload authorization')
    require(not (REMOTE / 'started.json').exists(), 'Prior stream attempt requires inspection')
    save(REMOTE, 'started.json', {'time': time.time(), 'proof_sha256': job['proof_sha256']})
    results = {}
    for name in FILES:
        info = job['files'][name]
        expected = job['proof']['artifacts'][name]
        require(info['key'] == PREFIX + name and info['bytes'] == expected['bytes']
                and info['sha256'] == expected['sha256'], 'Wrong file authorization')
        require(len(info['urls']) == math.ceil(info['bytes'] / PART_SIZE), 'Wrong part count')
        total, checksum, parts, number = 0, hashlib.sha256(), [], 0
        with (ARTIFACTS / name).open('rb') as source, concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            pending = set()
            while True:
                data = source.read(PART_SIZE)
                if not data:
                    break
                number += 1
                require(number <= len(info['urls']), 'Artifact grew during upload')
                checksum.update(data)
                total += len(data)
                pending.add(pool.submit(put_part, info['urls'][number - 1], number, data))
                if len(pending) >= 4:
                    done, pending = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
                    parts.extend(f.result() for f in done)
                    save(REMOTE, 'status.json', {'phase': 'uploading', 'file': name,
                         'uploaded_bytes': sum(p['bytes'] for p in parts), 'time': time.time()})
            parts.extend(f.result() for f in concurrent.futures.as_completed(pending))
        require(total == expected['bytes'] and checksum.hexdigest() == expected['sha256'],
                'Streamed artifact checksum mismatch')
        validate_files(job['proof'])
        results[name] = {'bytes': total, 'sha256': checksum.hexdigest(),
                         'parts': sorted(parts, key=lambda p: p['PartNumber'])}
        save(REMOTE, 'parts-progress.json', results)
    require(digest(PROOF.read_bytes()) == job['proof_sha256'], 'Export proof changed during upload')
    save(REMOTE, 'parts-complete.json', {'proof_sha256': job['proof_sha256'], 'files': results})
    save(REMOTE, 'status.json', {'phase': 'awaiting_remote_readback', 'time': time.time()})


def validate_parts(result, expected):
    require(result['bytes'] == expected['bytes'] and result['sha256'] == expected['sha256'], 'Wrong upload result')
    parts = result['parts']
    require(len(parts) == math.ceil(expected['bytes'] / PART_SIZE), 'Missing or extra upload parts')
    require([p['PartNumber'] for p in parts] == list(range(1, len(parts) + 1)), 'Part order mismatch')
    require(all(p['bytes'] == PART_SIZE for p in parts[:-1])
            and 0 < parts[-1]['bytes'] <= PART_SIZE
            and sum(p['bytes'] for p in parts) == expected['bytes'], 'Part size mismatch')
    require(all(valid_sha(p['sha256']) and p['ETag'] for p in parts), 'Invalid part evidence')
    return [{'PartNumber': p['PartNumber'], 'ETag': p['ETag']} for p in parts]


def finish(s3):
    from storage import BUCKET
    from remote_readback import readback
    job = json.loads((LOCAL / 'job.json').read_text())
    evidence = check()
    require(evidence == {k: job[k] for k in ('proof', 'proof_sha256')}, 'Export evidence changed')
    report = json.loads(ssh(['cat', str(REMOTE / 'parts-complete.json')]))
    require(report['proof_sha256'] == job['proof_sha256'] and set(report['files']) == set(FILES), 'Wrong parts report')
    for name in FILES:
        info, result = job['files'][name], report['files'][name]
        parts = validate_parts(result, info)
        completed = name + '.multipart-completed.json'
        if not (LOCAL / completed).exists():
            actual = []
            for page in s3.get_paginator('list_parts').paginate(Bucket=BUCKET, Key=info['key'], UploadId=info['upload_id']):
                actual.extend(page.get('Parts', []))
            require([(p['PartNumber'], p['ETag'], p['Size']) for p in actual] ==
                    [(p['PartNumber'], p['ETag'], p['bytes']) for p in result['parts']], 'Stored part list mismatch')
            reply = s3.complete_multipart_upload(Bucket=BUCKET, Key=info['key'], UploadId=info['upload_id'],
                                                MultipartUpload={'Parts': parts})
            save(LOCAL, completed, {'time': time.time(), 'etag': reply['ETag']})
        head = s3.head_object(Bucket=BUCKET, Key=info['key'])
        require(head['ContentLength'] == info['bytes'] and head['Metadata']['proof-sha256'] == job['proof_sha256']
                and head['Metadata']['sha256'] == info['sha256'], 'Stored artifact metadata mismatch')
        last_saved = 0
        def progress(length):
            nonlocal last_saved
            if length - last_saved >= 1024**3:
                save(LOCAL, 'status.json', {'phase': 'remote_sha256_readback', 'file': name,
                     'bytes': length, 'total': info['bytes'], 'time': time.time()})
                last_saved = length
        length, checksum = readback(s3, BUCKET, info['key'], head['ETag'], info['bytes'], progress)
        require(length == info['bytes'] and checksum == info['sha256'], 'Full remote checksum mismatch')
        save(LOCAL, name + '.verified.json', {'key': info['key'], 'bytes': length, 'sha256': checksum,
                                             'etag': head['ETag'], 'time': time.time()})
    release = {'anchor': 24453558, 'block_hash': BLOCK_HASH, 'mpt_state_root': STATE_ROOT,
               'source_commit': COMMIT, 'proof_sha256': job['proof_sha256'],
               'metadata': job['proof']['metadata'], 'full_remote_sha256_verified': True,
               'independent_mpt_reconstruction_verified': not EXPORT_ONLY,
               'verification_deferred_by_user': EXPORT_ONLY,
               'shadowfork_finality_established': False, 'cross_client_imports_verified': False,
               'genesis_time': None, 'files': {name: json.loads((LOCAL / (name + '.verified.json')).read_text()) for name in FILES}}
    require_absent(s3, PREFIX + 'release.json')
    raw = (json.dumps(release, indent=2) + '\n').encode()
    put_release(s3, raw)
    require(s3.get_object(Bucket=BUCKET, Key=PREFIX + 'release.json')['Body'].read() == raw, 'Release metadata readback failed')
    save(LOCAL, 'release.json', release)
    save(LOCAL, 'status.json', {'phase': 'published_verified', 'time': time.time()})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'worker-check', 'authorize', 'stream', 'finish'))
    args = parser.parse_args()
    if args.action in ('check', 'worker-check'):
        value = check() if args.action == 'check' else remote_readiness()
        print(json.dumps(value, indent=2))
        return
    root = REMOTE if args.action == 'stream' else LOCAL
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (root / 'publication.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if args.action == 'stream':
                stream()
            else:
                from storage import client
                {'authorize': authorize, 'finish': finish}[args.action](client())
        except Exception as exc:
            # URL-bearing exception text and authorization contents are private.
            save(root, 'status.json', {'phase': 'failed', 'error_class': type(exc).__name__, 'time': time.time()})
            raise SystemExit(type(exc).__name__ + ': inspect private job evidence') from None


if __name__ == '__main__':
    main()
