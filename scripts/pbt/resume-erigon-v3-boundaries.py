#!/usr/bin/env python3
"""One reviewed exporter recovery: retain merged files outside the snapshot set.

The native converter remains unchanged. Only the two audited accounts/storage
ranges may be hidden, after full record equality and native resume fixtures.
No worker H database, recovery archive, genesis, or network is changed.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time

ROOT = Path('/data/pbt-1/v3-source-upgrade')
REVIEW = Path('/data/pbt-1/boundary-review')
SOURCE = Path('/data/pbt-1/rehearsal-24453558/erigon')
BIN = Path('/data/pbt-1/rehearsal-tools/erigon/build/bin/integration.pinned')
SHA = 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03'
UNIT = 'pbt-1-v3-source-upgrade-v3.service'


def read(path):
    return json.loads(path.read_text())


def unit(name):
    return dict(line.split('=', 1) for line in subprocess.check_output([
        'systemctl', 'show', name, '-p', 'MainPID', '-p', 'ActiveState',
        '-p', 'Result', '-p', 'ExecMainStatus'], text=True).splitlines())


def same_file(path, expected):
    stat = path.stat()
    assert stat.st_ino == expected['inode'], path
    assert stat.st_size == expected['size'], path
    assert stat.st_mtime_ns == expected['mtime_ns'], path


def check():
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    assert not (ROOT / 'boundary-recovery').exists(), 'Inspect prior recovery; no automatic retry'
    prior = read(ROOT / 'status.json')
    assert prior['phase'] == 'failed' and prior['error'] == 'convert-v3 exited 1; inspect log'
    assert 'max step 1049727 splits accounts domain file' in (ROOT / 'convert-v3.log').read_text()
    assert read(ROOT / 'unsqueeze.json')['exit_code'] == 0
    assert read(ROOT / 'checkpoint.json')['mutable_databases_copied']
    assert (ROOT / 'original-checkpoint/snapshots/domain').is_dir()
    assert (ROOT / 'unsqueeze-backup').is_dir()
    assert not (SOURCE / 'snapshots/backup').exists()
    assert unit(UNIT)['MainPID'] in ('0', str(os.getpid()))
    for name in ('pbt-1-v3-source-qualification', 'pbt-1-v3-source-reopen',
                 'pbt-1-domain-fragment-review'):
        assert unit(name)['MainPID'] == '0', name
    assert unit('pbt-1-domain-fragment-review')['Result'] == 'success'
    fixture = unit('pbt-1-v3-resume-fixture')
    assert fixture['MainPID'] == '0' and fixture['Result'] == 'success'
    assert fixture['ExecMainStatus'] == '0'
    assert read(REVIEW / 'comparisons-complete.json')['all_records_equal']
    with BIN.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == SHA
    assert shutil.disk_usage(SOURCE).free > 300_000_000_000
    # No native DB owner or container may race the reviewed file selection.
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, PermissionError):
            continue
        if args and Path(os.fsdecode(args[0])).name in ('erigon', 'integration', 'integration.pinned'):
            assert not any(os.fsencode(str(SOURCE)) in arg for arg in args), args
    for cid in subprocess.check_output(['docker', 'ps', '-q'], text=True).splitlines():
        container = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
        for mount in container['Mounts']:
            if container['Name'] == '/node_exporter' and mount['Source'] == '/' and not mount['RW']:
                continue
            path = Path(mount['Source'])
            assert not (path == SOURCE or path in SOURCE.parents or SOURCE in path.parents)
    manifest = read(REVIEW / 'exporter-files.json')
    indexed = {(f['dir'], f['name']): f for f in manifest}
    plan = read(REVIEW / 'exporter-plan.json')
    assert {p['domain'] for p in plan} == {'accounts', 'storage'} and len(plan) == 2
    move = []
    for item in plan:
        domain = item['domain']
        expected = f'v2.0-{domain}.1049600-1049856.kv'
        assert item['hide'] == expected and not item['gaps']
        proof = read(REVIEW / (domain + '-compare.json'))
        assert proof['all_records_equal'] and proof['inputs_unchanged']
        assert proof['merged'] == str(SOURCE / 'snapshots/domain' / expected)
        assert proof['domain'] == domain and proof['fragments'] == 20
        assert proof['records'] > 0
        cursor = 1049600
        assert len(item['replacements']) == len(item['indexes']) == 20
        for replacement, indexes in zip(item['replacements'], item['indexes']):
            assert replacement['start'] == cursor
            cursor = replacement['end']
            assert indexes['file'] == replacement['name']
            for ext in ('.kv', '.bt', '.kvei'):
                names = [n for n in indexes['siblings'] if n.endswith(ext)]
                assert len(names) == 1
                same_file(SOURCE / 'snapshots/domain' / names[0], indexed['domain', names[0]])
        assert cursor == 1049856
        siblings = [f for f in manifest if f['dir'] == 'domain' and
                    f['name'].split('-', 1)[-1].startswith(domain + '.1049600-1049856.')]
        assert len(siblings) == 3 and {Path(f['name']).suffix for f in siblings} == {'.kv', '.bt', '.kvei'}
        for f in siblings:
            same_file(SOURCE / 'snapshots/domain' / f['name'], f)
            move.append(f)
    completed = [f for f in manifest if f['dir'] == 'rebuild/domain']
    assert len(completed) == 15
    assert {Path(f['name']).suffix for f in completed} == {'.kv', '.bt', '.kvei'}
    for f in completed:
        same_file(SOURCE / 'snapshots/rebuild/domain' / f['name'], f)
    assert sorted(p.name for p in (SOURCE / 'snapshots/rebuild/domain').iterdir()) == sorted(f['name'] for f in completed)
    return {'time': time.time(), 'move': move, 'completed_shards_preserved': 5,
            'integration_sha256': SHA, 'native_resume_options': ['--v3', '--continue']}


def main(check_only):
    with (ROOT / 'upgrade.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        proof = check()
        if check_only:
            print(json.dumps(proof, indent=2))
            return
        spec = importlib.util.spec_from_file_location('upgrade', '/data/pbt-1/upgrade-erigon-v3-index-recovery.py')
        upgrade = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(upgrade)
        assert upgrade.ROOT == ROOT and upgrade.SOURCE == SOURCE and upgrade.BASE_BLOCK == 24452538
        recovery = ROOT / 'boundary-recovery'
        recovery.mkdir()
        hidden = recovery / 'hidden-domain-files'
        hidden.mkdir()
        (recovery / 'preflight.json').write_text(json.dumps(proof, indent=2) + '\n')
        for name in ('status.json', 'convert-v3.log'):
            shutil.copy2(ROOT / name, recovery / ('before-' + name))
        for f in proof['move']:
            (SOURCE / 'snapshots/domain' / f['name']).rename(hidden / f['name'])
        (recovery / 'selection-applied.json').write_text(json.dumps({'time': time.time(), 'files': proof['move']}) + '\n')
        common = ['--datadir=' + str(SOURCE), '--chain=mainnet']
        try:
            upgrade.run('convert-v3', [str(BIN), 'commitment', 'convert', *common, '--v3', '--continue'])
            upgrade.run('verify-v3-files', [str(BIN), 'commitment', 'verify', *common], v3=True)
            upgrade.run('restore-source-block', [str(BIN), 'stage_exec', *common,
                        '--block=24452538', '--experimental.commitment-v3'], v3=True)
            upgrade.run('verify-v3-state', [str(BIN), 'commitment', 'verify', *common], v3=True)
            upgrade.run('after-commitments', [str(BIN), 'commitment', 'print', *common], v3=True)
            upgrade.save('conversion-complete.json', {'time': time.time(), 'source': str(SOURCE),
                         'target_block': 24452538, 'native_reopen_qualified': False, 'upload_authorized': False})
            upgrade.status('converted_pending_native_reopen', target_block=24452538)
        except Exception as exc:
            upgrade.status('failed', error=str(exc))
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    main(parser.parse_args().check_only)
