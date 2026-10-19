#!/usr/bin/env python3
"""Build the bounded batch prototype after the native comparison finishes."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/data/pbt-1/native')
SOURCE = ROOT/'source'


def run(*args):
    return subprocess.check_output(args, cwd=SOURCE, text=True).strip()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    lock = (ROOT/'benchmark.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX)
    for variant in ('profile', 'profile-no-writemap'):
        status = json.loads((ROOT/variant/'status.json').read_text())
        assert status['phase'] == 'verified_stopped', (variant, status)
    manifest = json.loads((ROOT/'batch-source-manifest.json').read_text())
    assert run('git', 'rev-parse', 'HEAD') == manifest['base_commit']
    assert set(run('git', 'diff', '--name-only').splitlines()) == set(manifest['profile_file_blobs'])
    for name, blob in manifest['profile_file_blobs'].items():
        assert run('git', 'hash-object', name) == blob, name
    patch = ROOT/'batch.patch'
    assert digest(patch) == manifest['patch_sha256']
    binary = ROOT/'erigon-batch'
    assert not binary.exists() and not (ROOT/'batch-build-report.json').exists()
    subprocess.run(['git', 'apply', '--check', str(patch)], cwd=SOURCE, check=True)
    subprocess.run(['git', 'apply', str(patch)], cwd=SOURCE, check=True)
    for name, blob in manifest['final_file_blobs'].items():
        assert run('git', 'hash-object', name) == blob, name
    env = {**os.environ, 'GOTOOLCHAIN': 'go1.26.0', 'GOPATH': str(ROOT/'go'),
           'GOCACHE': str(ROOT/'go-cache'), 'GOMAXPROCS': '12'}
    command = ['make', 'GOAMD64_VERSION=v2', 'BUILD_TAGS=nosqlite,noboltdb', 'erigon']
    started = time.monotonic()
    with (ROOT/'build-batch.log').open('w') as log:
        subprocess.run(command, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run(['cp', '--reflink=auto', str(SOURCE/'build/bin/erigon'), str(binary)], check=True)
    report = {'time': time.time(), 'seconds': time.monotonic()-started,
        'source': manifest, 'path': str(binary), 'sha256': digest(binary),
        'version': run(str(binary), '--version'), 'command': command,
        'replay_started': False, 'canonical_routing_changed': False}
    (ROOT/'batch-build-report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
