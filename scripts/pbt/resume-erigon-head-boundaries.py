#!/usr/bin/env python3
"""Reviewed H-worker boundary recovery, usable only after the specific failure.

Preserves six merged-domain files and resumes the unchanged native converter.
The current running conversion must not be interrupted to invoke this script.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time

SOURCE = Path('/data/pbt-1/erigon')
ROOT = Path('/data/pbt-1/v3-head-upgrade')
REVIEW = Path('/data/pbt-1/boundary-review')
TOOLS = Path('/data/pbt-1/v3-tools-372df0e6')
UNIT = 'pbt-1-v3-head-upgrade'
TARGET = 24503958
NATIVE_SHA = 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03'
DRIVER_SHA = '81de334b2ea4fc32afd4ed60d24cf7d3ebc96fec347296519e64985deff70b6f'
ARCHIVE_SHA = 'e511af776332da1497c537b58770bec0b7e962c1484cd2dcb9a9d30f6ac268a7'
PREFIX = [(0, 1024000), (1024000, 1040000), (1040000, 1048000),
          (1048000, 1049000), (1049000, 1049600), (1049600, 1050624)]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def unit(name):
    return dict(line.split('=', 1) for line in subprocess.check_output([
        'systemctl', 'show', name, '-p', 'MainPID', '-p', 'ActiveState',
        '-p', 'Result'], text=True).splitlines())


def require_failure(fields, status, log, own_pid):
    assert fields['MainPID'] in ('0', str(own_pid)), 'Conversion still has another owner'
    if fields['MainPID'] == '0':
        assert fields['ActiveState'] == 'failed' and fields['Result'] == 'exit-code'
    assert status['phase'] == 'failed', 'Never change a running or successful conversion'
    assert status['target_block'] == TARGET
    assert status['error'] == 'convert-v3 exited 1; inspect its log'
    assert re.search(r'max step 1050624 splits (accounts|storage) domain file '
                     r'\[3283200000,3286400000\)', log), 'Different failure requires review'
    assert 'phase 1 file ' in log and 'commitment.1050624-1050625.kv' in log


def same_file(path, record):
    stat = path.stat()
    assert (stat.st_ino, stat.st_size, stat.st_mtime_ns) == (
        record['inode'], record['size'], record['mtime_ns']), path


def validate_plan(plan, manifest, proofs):
    """Validate exact coverage and accessor names before filesystem operations."""
    assert len(plan) == 2 and {p['domain'] for p in plan} == {'accounts', 'storage'}
    indexed = {(f['dir'], f['name']): f for f in manifest}
    checked, moved = [], []
    for item in plan:
        domain = item['domain']
        assert item['hide'] == f'v2.0-{domain}.1050624-1051648.kv'
        assert not item['gaps']
        proof = proofs[domain]
        assert proof['domain'] == domain and proof['fragments'] == 1024
        assert proof['merged'] == str(SOURCE / 'snapshots/domain' / item['hide'])
        assert proof['all_records_equal'] and proof['inputs_unchanged'] and proof['records'] > 0
        assert len(item['replacements']) == len(item['indexes']) == 1024
        for step, replacement, indexes in zip(range(1050624, 1051648), item['replacements'], item['indexes']):
            stem = f'{domain}.{step}-{step + 1}'
            assert replacement['start'] == step and replacement['end'] == step + 1
            assert replacement['name'] == indexes['file'] == f'v2.0-{stem}.kv'
            for ext in ('.kv', '.bt', '.kvei'):
                names = [n for n in indexes['siblings'] if n.endswith(ext)]
                assert len(names) == 1 and names[0].split('-', 1)[-1] == stem + ext
                checked.append(indexed['domain', names[0]])
        siblings = [f for f in manifest if f['dir'] == 'domain' and
                    f['name'].split('-', 1)[-1].startswith(f'{domain}.1050624-1051648.')]
        assert len(siblings) == 3 and {Path(f['name']).suffix for f in siblings} == {'.kv', '.bt', '.kvei'}
        moved.extend(siblings)
    return checked, moved


def check():
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-2'
    require_failure(unit(UNIT), read(ROOT / 'status.json'),
                    (ROOT / 'convert-v3.log').read_text(), os.getpid())
    assert not (ROOT / 'boundary-recovery').exists(), 'Inspect prior recovery; no automatic retry'
    for name in ('pbt-1-worker-qualification', 'pbt-1-domain-fragment-review'):
        assert unit(name)['MainPID'] == '0', name
    assert unit('pbt-1-domain-fragment-review')['Result'] == 'success'
    started = read(ROOT / 'started.json')
    job = read(SOURCE.parent / 'qualification/job.json')
    assert started['host'] == socket.gethostname()
    assert started['source'] == str(SOURCE) and started['target_block'] == job['head'] == TARGET
    assert started['target_hash'] == job['head_hash']
    assert started['target_state_root'] == job['state_root']
    assert started['rollback_sha256'] == ARCHIVE_SHA
    assert started['binaries']['integration'] == sha(TOOLS / 'integration.pinned') == NATIVE_SHA
    assert read(ROOT / 'unsqueeze.json')['exit_code'] == 0
    assert (ROOT / 'unsqueeze-backup').is_dir() and not (SOURCE / 'snapshots/backup').exists()
    archive = Path('/mnt/pbt-recovery/erigon-24503958.tar.zst')
    assert archive.parent.is_mount()
    proof = read(archive.parent / 'archive-verified.json')
    stat = archive.stat()
    assert proof['sha256'] == ARCHIVE_SHA and proof['bytes'] == stat.st_size == 534953200071
    assert proof['mtime_ns'] == stat.st_mtime_ns
    fixture = read(REVIEW / 'resume-fixture-result.json')
    assert fixture['service']['Result'] == 'success' and fixture['service']['ExecMainStatus'] == '0'
    assert fixture['source_commit'] == started['commit']
    assert fixture['test_file_sha256'] == sha(REVIEW / 'erigon-v3-resume-fixture_test.go')
    assert read(REVIEW / 'comparisons-complete.json')['all_records_equal']
    checked, moved = validate_plan(read(REVIEW / 'head-plan.json'), read(REVIEW / 'head-files.json'),
                                  {d: read(REVIEW / (d + '-compare.json')) for d in ('accounts', 'storage')})
    for record in checked + moved:
        same_file(SOURCE / 'snapshots/domain' / record['name'], record)
    # Require exactly the expected contiguous completed prefix; the native
    # preflight also checks it again before reusing any output.
    expected = {f'{version}-commitment.{start}-{end}{ext}' for start, end in PREFIX
                for version, ext in [('v3.0', '.kv'), ('v2.0', '.bt'), ('v1.2', '.kvei')]}
    rebuild = SOURCE / 'snapshots/rebuild/domain'
    assert {p.name for p in rebuild.iterdir()} == expected
    assert all((rebuild / name).stat().st_size > 0 for name in expected)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, PermissionError):
            continue
        if args and Path(os.fsdecode(args[0])).name in ('erigon', 'integration', 'integration.pinned'):
            assert not any(os.fsencode(str(SOURCE)) in arg for arg in args), 'Native database owner remains'
    for cid in subprocess.check_output(['docker', 'ps', '-q'], text=True).splitlines():
        container = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
        for mount in container['Mounts']:
            if container['Name'] == '/node_exporter' and mount['Source'] == '/' and not mount['RW']:
                continue
            path = Path(mount['Source'])
            assert not (path == SOURCE or path in SOURCE.parents or SOURCE in path.parents)
    assert shutil.disk_usage(SOURCE).free > 300_000_000_000
    driver = SOURCE.parent / 'upgrade-erigon-head-v3.py'
    assert sha(driver) == DRIVER_SHA
    spec = importlib.util.spec_from_file_location('upgrade', driver)
    upgrade = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(upgrade)
    assert upgrade.ROOT == ROOT and upgrade.SOURCE == SOURCE and upgrade.TARGET == TARGET
    # Use the reviewed stage runner with the unchanged binary. Explicitly set
    # NO_PRUNE for its future stage_exec child (the original runner predates it).
    return upgrade, {'time': time.time(), 'move': moved, 'completed_prefix': PREFIX,
                     'integration_sha256': NATIVE_SHA, 'resume_options': ['--v3', '--continue']}


def main(apply):
    with (ROOT / 'upgrade.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        upgrade, proof = check()
        if not apply:
            print(json.dumps(proof, indent=2))
            return
        recovery = ROOT / 'boundary-recovery'
        recovery.mkdir()
        hidden = recovery / 'hidden-domain-files'
        hidden.mkdir()
        (recovery / 'preflight.json').write_text(json.dumps(proof, indent=2) + '\n')
        for name in ('status.json', 'convert-v3.log'):
            shutil.copy2(ROOT / name, recovery / ('before-' + name))
        for record in proof['move']:
            (SOURCE / 'snapshots/domain' / record['name']).rename(hidden / record['name'])
        (recovery / 'selection-applied.json').write_text(json.dumps({'time': time.time(), 'files': proof['move']}) + '\n')
        binary = str(TOOLS / 'integration.pinned')
        common = ['--datadir=' + str(SOURCE), '--chain=mainnet']
        try:
            upgrade.run('convert-v3', [binary, 'commitment', 'convert', *common, '--v3', '--continue'])
            upgrade.run('verify-v3-files', [binary, 'commitment', 'verify', *common], v3=True)
            os.environ['NO_PRUNE'] = 'true'
            upgrade.run('restore-head-block', [binary, 'stage_exec', *common,
                        '--block=' + str(TARGET), '--experimental.commitment-v3'], v3=True)
            restoration = read(ROOT / 'restore-head-block.json')
            restoration['no_prune_env'] = 'true'
            upgrade.save('restore-head-block.json', restoration)
            upgrade.run('verify-v3-state', [binary, 'commitment', 'verify', *common], v3=True)
            upgrade.run('after-commitments', [binary, 'commitment', 'print', *common], v3=True)
            upgrade.save('conversion-complete.json', {'time': time.time(), 'source': str(SOURCE),
                         'target_block': TARGET, 'native_reopen_qualified': False, 'publication_authorized': False})
            upgrade.save('status.json', {'phase': 'converted_pending_native_reopen', 'time': time.time(), 'target_block': TARGET})
        except Exception as exc:
            upgrade.save('status.json', {'phase': 'failed', 'time': time.time(), 'target_block': TARGET, 'error': str(exc)})
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Apply only after the read-only check has passed')
    main(parser.parse_args().apply)
