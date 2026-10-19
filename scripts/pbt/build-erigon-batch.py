#!/usr/bin/env python3
"""Build the bounded batch prototype after the native comparison finishes."""
import fcntl
import argparse
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


def main(continuation=False, resume_build=False):
    lock = (ROOT/'benchmark.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX)
    for variant in (('profile-batch16',) if continuation else ('profile', 'profile-no-writemap')):
        status = json.loads((ROOT/variant/'status.json').read_text())
        assert status['phase'] == 'verified_stopped', (variant, status)
    name = 'continuation' if continuation else 'batch'
    manifest = json.loads((ROOT/(name+'-source-manifest.json')).read_text())
    assert run('git', 'rev-parse', 'HEAD') == manifest['base_commit']
    previous = manifest['final_file_blobs'] if resume_build else manifest['previous_file_blobs'] if continuation else manifest['profile_file_blobs']
    changed = set(run('git', 'diff', '--name-only').splitlines()) | set(run('git', 'ls-files', '--others', '--exclude-standard').splitlines())
    assert changed == set(previous), changed
    for path, blob in previous.items():
        assert run('git', 'hash-object', path) == blob, path
    patch = ROOT/(name+'.patch')
    assert digest(patch) == manifest['patch_sha256']
    binary = ROOT/('erigon-'+name)
    assert not binary.exists() and not (ROOT/(name+'-build-report.json')).exists()
    if not resume_build:
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=SOURCE, check=True)
        subprocess.run(['git', 'apply', str(patch)], cwd=SOURCE, check=True)
    for path, blob in manifest['final_file_blobs'].items():
        assert run('git', 'hash-object', path) == blob, path
    env = {**os.environ, 'GOTOOLCHAIN': 'go1.26.0', 'GOPATH': str(ROOT/'go'),
           'GOCACHE': str(ROOT/'go-cache'), 'GOMAXPROCS': '12',
           'PATH': '/opt/pbt-go/go/bin:'+os.environ['PATH']}
    command = ['make', 'GOAMD64_VERSION=v2', 'BUILD_TAGS=nosqlite,noboltdb', 'erigon']
    started = time.monotonic()
    with (ROOT/('build-'+name+'.log')).open('w') as log:
        subprocess.run(command, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    subprocess.run(['cp', '--reflink=auto', str(SOURCE/'build/bin/erigon'), str(binary)], check=True)
    report = {'time': time.time(), 'seconds': time.monotonic()-started,
        'source': manifest, 'path': str(binary), 'sha256': digest(binary),
        'version': run(str(binary), '--version'), 'command': command,
        'replay_started': False, 'canonical_routing_changed': False}
    (ROOT/(name+'-build-report.json')).write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--continuation', action='store_true')
    parser.add_argument('--resume-build', action='store_true')
    args = parser.parse_args()
    main(args.continuation, args.resume_build)
