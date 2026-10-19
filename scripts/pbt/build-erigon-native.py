#!/usr/bin/env python3
"""Build pinned baseline and instrumented Erigon binaries on the probe VM."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/data/pbt-1/native')
SOURCE = ROOT/'source'
COMMIT = '8c1e3893d77d230720d172f1492d95b5777a862c'


def run(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    ROOT.mkdir(exist_ok=True)
    assert not SOURCE.exists(), 'Inspect existing source/build before retrying'
    os.environ['GOTOOLCHAIN'] = 'go1.26.0'
    os.environ['GOPATH'] = str(ROOT/'go')
    os.environ['GOCACHE'] = str(ROOT/'go-cache')
    assert run('go', 'version') == 'go version go1.26.0 linux/amd64'
    started = time.time()
    subprocess.run(['git', 'clone', '--depth=1', '--branch=v3.7.1',
        'https://github.com/erigontech/erigon.git', str(SOURCE)], check=True)
    assert run('git', 'rev-parse', 'HEAD', cwd=SOURCE) == COMMIT
    assert not run('git', 'status', '--porcelain', cwd=SOURCE)
    env = {**os.environ, 'GOMAXPROCS': '12'}
    command = ['make', 'GOAMD64_VERSION=v2', 'BUILD_TAGS=nosqlite,noboltdb', 'erigon']
    builds = []
    for name in ('stock', 'profile'):
        if name == 'profile':
            subprocess.run(['git', 'apply', '--check', str(ROOT/'profile.patch')], cwd=SOURCE, check=True)
            subprocess.run(['git', 'apply', str(ROOT/'profile.patch')], cwd=SOURCE, check=True)
        before = time.monotonic()
        with (ROOT/f'build-{name}.log').open('w') as log:
            subprocess.run(command, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        binary = ROOT/f'erigon-{name}'
        subprocess.run(['cp', '--reflink=auto', str(SOURCE/'build/bin/erigon'), str(binary)], check=True)
        builds.append({'name': name, 'seconds': time.monotonic()-before,
            'path': str(binary), 'sha256': digest(binary), 'version': run(str(binary), '--version')})
        report = {'started_at': started, 'updated_at': time.time(), 'source_commit': COMMIT,
            'go_version': run('go', 'version'), 'command': command,
            'patch_sha256': digest(ROOT/'profile.patch'), 'builds': builds}
        (ROOT/'build-report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(builds[-1]), flush=True)


if __name__ == '__main__':
    main()
