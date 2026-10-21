#!/usr/bin/env python3
"""Build pinned PBT tools on the original VM; exercise upstream small-state fixtures.

Runs independently of the source restore. Never opens an experiment database.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/data/pbt-1/rehearsal-tools')
SOURCE = ROOT / 'erigon'
COMMIT = '372df0e68f52f9975370bff38dee6e41aefff0d7'
TOOLCHAIN_SHA = '3a674e3d261256e14027029938e517f75fc26424a8b3bf1330e4ccac3955ed33'


def main():
    ROOT.mkdir(exist_ok=True)
    report = {'commit': COMMIT, 'started_at': time.time(), 'phase': 'bootstrap',
              'build_verified': False, 'full_state_qualified': False}

    def save():
        report['updated_at'] = time.time()
        temporary = ROOT / 'build-report.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(ROOT / 'build-report.json')

    def run(args, name, env=None):
        report['phase'] = name
        save()
        with (ROOT / (name + '.log')).open('w') as log:
            subprocess.run(args, env=env, cwd=SOURCE if SOURCE.exists() else ROOT,
                           stdout=log, stderr=subprocess.STDOUT, check=True)

    try:
        assert not (ROOT / 'build-report.json').exists(), 'Inspect prior attempt before retry'
        assert not SOURCE.exists(), 'Source must be a new dedicated checkout'
        save()
        run(['apt-get', 'update'], 'apt-update')
        run(['apt-get', 'install', '-y', 'build-essential', 'git', 'pkg-config',
             'cmake', 'ca-certificates'], 'apt-install',
            {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'})
        archive = ROOT / 'go1.26.0-verified.tar.gz'
        with archive.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == TOOLCHAIN_SHA
        report['toolchain_archive_sha256'] = TOOLCHAIN_SHA
        run(['tar', '-xzf', str(archive), '-C', str(ROOT)], 'go-unpack')
        env = {**os.environ, 'PATH': str(ROOT / 'go/bin') + ':' + os.environ['PATH'],
               'GOTOOLCHAIN': 'local', 'GOPATH': str(ROOT / 'gopath'),
               'GOCACHE': str(ROOT / 'go-cache'), 'GOMAXPROCS': '4',
               'GOFLAGS': '-p=4'}
        report['go_version'] = subprocess.check_output(
            [str(ROOT / 'go/bin/go'), 'version'], text=True).strip()
        assert report['go_version'] == 'go version go1.26.0 linux/amd64'
        run(['git', 'init', str(SOURCE)], 'git-init')
        run(['git', 'remote', 'add', 'origin', 'https://github.com/erigontech/erigon.git'],
            'git-remote')
        run(['git', 'fetch', '--depth=1', 'origin', COMMIT], 'git-fetch')
        run(['git', 'checkout', '--detach', COMMIT], 'git-checkout')
        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE,
                                       text=True).strip() == COMMIT
        run(['make', 'GOAMD64_VERSION=v2', 'erigon', 'integration'], 'build', env)
        report['binaries'] = {}
        for name in ('erigon', 'integration'):
            binary = SOURCE / 'build/bin' / name
            with binary.open('rb') as stream:
                sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            report['binaries'][name] = {'path': str(binary), 'sha256': sha}
        report['build_verified'] = True
        run(['go', 'test', './cmd/utils/app', '-run',
             'Test(RunExportPBT|DoExportPBT|ExportPBT|PBTRealChainTxNumConvention)',
             '-count=1', '-timeout=15m'], 'export-fixtures', env)
        run(['go', 'test', './cmd/integration/commands', '-run',
             'TestConvertPBT(HexSourceKeepHex|PrunedSourceOpens|LegacyHexSourceIsRefusedAndRemoved|OutputPassesCommitmentIntegrity|SourceWithoutBinaryTables)$',
             '-count=1', '-timeout=15m'], 'conversion-fixtures', env)
        report['phase'] = 'small_fixtures_passed'
        save()
    except Exception as exc:
        report['failed_phase'] = report['phase']
        report['phase'] = 'failed'
        report['error'] = str(exc)
        save()
        raise


if __name__ == '__main__':
    main()
