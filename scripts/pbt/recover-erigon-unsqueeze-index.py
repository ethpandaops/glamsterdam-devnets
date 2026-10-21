#!/usr/bin/env python3
"""Build missing indexes for the completed first unsqueeze data file in isolation.

Does not promote files or resume conversion. The source DB must be stopped after
the known disk-reserve interruption. Mutable metadata is copied independently;
the completed immutable .kv is hardlinked and never rewritten by index creation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time

SOURCE = Path('/data/pbt-1/rehearsal-24453558/erigon')
UPGRADE = Path('/data/pbt-1/v3-source-upgrade')
ROOT = Path('/data/pbt-1/v3-source-index-recovery')
WORK = ROOT / 'datadir'
BINARY = Path('/data/pbt-1/rehearsal-tools/erigon/build/bin/erigon')
SHA = '7d3c5beb8b985d54400c10cb09d6381860da387e85a8a74f0336795f08d025f4'
FILE = 'v2.2-commitment.0-1024000.kv'


def save(name, data):
    temp = ROOT / (name + '.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(ROOT / name)


def main(retry_with_source_files=False):
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    if retry_with_source_files:
        failure = json.loads((ROOT / 'status.json').read_text())
        assert failure['phase'] == 'failed' and failure['error'] == 'Index command exited 1'
        assert 'gap between snapshot files and DB for domain accounts' in (ROOT / 'index.log').read_text()
        assert subprocess.check_output(
            ['systemctl', 'show', 'pbt-1-v3-source-index-recovery',
             '-p', 'MainPID', '--value'], text=True).strip() in ('0', str(os.getpid()))
    else:
        assert not ROOT.exists(), 'Inspect any previous index-recovery attempt'
    prior = json.loads((UPGRADE / 'status.json').read_text())
    assert prior['phase'] == 'failed'
    assert prior['error'] == 'Local free space below 150 GB; interrupted before exhausting disk'
    assert subprocess.check_output(
        ['systemctl', 'show', 'pbt-1-v3-source-upgrade-v3',
         '-p', 'MainPID', '--value'], text=True).strip() == '0'
    assert not (SOURCE / 'snapshots/backup').exists(), 'No promotion may have occurred'
    assert 'build commitment values idx: context canceled' in (UPGRADE / 'unsqueeze.log').read_text()
    data = SOURCE / 'snapshots/rebuild/domain' / FILE
    assert data.is_file() and data.stat().st_size > 100_000_000_000
    original = SOURCE / 'snapshots/domain/v1.1-commitment.0-1024000.kv'
    checkpoint = UPGRADE / 'original-checkpoint/snapshots/domain' / original.name
    assert os.path.samefile(original, checkpoint), 'Original commitment must remain preserved'
    assert shutil.disk_usage(SOURCE).free > 400_000_000_000
    with BINARY.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == SHA
    if retry_with_source_files:
        for name in ('index.log', 'status.json', 'started.json'):
            destination = ROOT / ('attempt-1-' + name)
            assert not destination.exists()
            (ROOT / name).rename(destination)
        # The snapshot-index command opens all domains and checks pruning gaps.
        # Supply the existing immutable files as links, except every old
        # accessor/data file for the converted range: its offsets have changed.
        immutable_extensions = {'.kv', '.kvi', '.kvei', '.bt', '.seg', '.idx',
                                '.ef', '.efi', '.v', '.vi'}
        for directory, subdirs, files in os.walk(SOURCE / 'snapshots'):
            subdirs[:] = [name for name in subdirs if name not in ('rebuild', 'backup')]
            rel = Path(directory).relative_to(SOURCE / 'snapshots')
            destination = WORK / 'snapshots' / rel
            destination.mkdir(parents=True, exist_ok=True)
            for name in files:
                if (Path(name).suffix not in immutable_extensions or
                        '-commitment.0-1024000.' in name):
                    continue
                src, dst = Path(directory) / name, destination / name
                if not dst.exists():
                    os.link(src, dst)
        shutil.copyfile(SOURCE / 'snapshots/erigondb.toml', WORK / 'snapshots/erigondb.toml')
        assert os.path.samefile(data, WORK / 'snapshots/domain' / FILE)
    else:
        ROOT.mkdir()
        (WORK / 'snapshots/domain').mkdir(parents=True)
        subprocess.run(['cp', '-a', '--reflink=auto', '--sparse=always',
                        str(SOURCE / 'chaindata'), str(WORK / 'chaindata')], check=True)
        for name in ('salt-blocks.txt', 'salt-state.txt'):
            shutil.copyfile(SOURCE / 'snapshots' / name, WORK / 'snapshots' / name)
        shutil.copyfile(SOURCE / 'snapshots/erigondb.toml', WORK / 'snapshots/erigondb.toml')
        os.link(data, WORK / 'snapshots/domain' / FILE)
    before = data.stat()
    command = [str(BINARY), 'snapshots', 'index', '--datadir=' + str(WORK)]
    save('started.json', {
        'time': time.time(), 'command': command, 'binary_sha256': SHA,
        'source_data': str(data), 'source_inode': before.st_ino,
        'source_bytes': before.st_size, 'source_mtime_ns': before.st_mtime_ns,
        'mutable_metadata_copied': True, 'source_promotion_authorized': False,
        'source_conversion_resume_authorized': False,
        'source_snapshot_context_linked': retry_with_source_files,
    })
    save('status.json', {'phase': 'building_indexes', 'time': time.time()})
    env = {k: v for k, v in os.environ.items() if k != 'COMMITMENT_V3'}
    env.update(GOMAXPROCS='8', NO_PRUNE='true')
    with (ROOT / 'index.log').open('w') as log:
        proc = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            while proc.poll() is None:
                if shutil.disk_usage(SOURCE).free < 150_000_000_000:
                    proc.send_signal(signal.SIGINT)
                    raise RuntimeError('Index recovery reached the 150 GB disk reserve')
                time.sleep(5)
            assert proc.returncode == 0, f'Index command exited {proc.returncode}'
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                proc.wait(timeout=1800)
    after = data.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ino) == (
        after.st_size, after.st_mtime_ns, after.st_ino), 'Immutable .kv was changed'
    generated = [{'name': p.name, 'bytes': p.stat().st_size}
                 for p in (WORK / 'snapshots').rglob('*')
                 if '-commitment.0-1024000.' in p.name and p.name != FILE]
    assert generated, 'Index command did not produce any accessors'
    save('complete.json', {'time': time.time(), 'generated_files': generated,
                           'data_file_unchanged': True, 'exit_code': proc.returncode,
                           'conversion_qualified': False, 'promoted': False})
    save('status.json', {'phase': 'indexes_built_pending_review', 'time': time.time()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retry-with-source-files', action='store_true')
    args = parser.parse_args()
    try:
        main(args.retry_with_source_files)
    except Exception as exc:
        if ROOT.exists():
            save('status.json', {'phase': 'failed', 'time': time.time(), 'error': str(exc)})
        raise
