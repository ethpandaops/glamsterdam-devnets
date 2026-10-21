#!/usr/bin/env python3
"""Convert only the separately restored Jochemnet source to v3 commitments.

Keeps a rollback checkpoint, both conversion backups and logs. Never advances
the chain beyond the original source block or touches the final-head database.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time

ROOT = Path('/data/pbt-1/v3-source-upgrade')
SOURCE = Path('/data/pbt-1/rehearsal-24453558/erigon')
TOOLS = Path('/data/pbt-1/rehearsal-tools/erigon/build/bin')
BASE_BLOCK = 24452538
BUILD_SHA = 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03'


def save(name, value):
    temporary = ROOT / (name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(ROOT / name)


def status(phase, **values):
    save('status.json', {'phase': phase, 'time': time.time(), **values})


def run(phase, args, v3=False):
    env = {k: v for k, v in os.environ.items() if k != 'COMMITMENT_V3'}
    env['GOMAXPROCS'] = '8'
    if 'stage_exec' in args:
        env['NO_PRUNE'] = 'true'  # Preserve BALs while restoring the source block.
    if v3:
        env['COMMITMENT_V3'] = 'true'
    status(phase, command=args, free_bytes=shutil.disk_usage(SOURCE).free)
    with (ROOT / (phase + '.log')).open('w') as log:
        process = subprocess.Popen(args, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if shutil.disk_usage(SOURCE).free < 150_000_000_000:
                    process.send_signal(signal.SIGINT)
                    raise RuntimeError('Local free space below 150 GB; interrupted before exhausting disk')
                time.sleep(5)
            assert process.returncode == 0, f'{phase} exited {process.returncode}; inspect log'
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=1800)
    save(phase + '.json', {'finished_at': time.time(), 'exit_code': process.returncode,
                           'command': args, 'commitment_v3_env': v3,
                           'no_prune_env': env.get('NO_PRUNE')})


def index_resume_inputs():
    """Read-only validation for the one known interrupted unsqueeze shard."""
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    recovery = ROOT.parent / 'v3-source-index-recovery'
    assert json.loads((recovery / 'status.json').read_text())['phase'] == 'indexes_built_pending_review'
    for unit in ('pbt-1-v3-source-index-recovery', 'pbt-1-v3-source-upgrade-v3'):
        pid = subprocess.check_output(
            ['systemctl', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip()
        assert pid == '0' or (unit.endswith('upgrade-v3') and pid == str(os.getpid()))
    prior = json.loads((ROOT / 'status.json').read_text())
    assert prior['phase'] == 'failed'
    assert prior['error'] == 'Local free space below 150 GB; interrupted before exhausting disk'
    assert 'build commitment values idx: context canceled' in (ROOT / 'unsqueeze.log').read_text()
    complete = json.loads((recovery / 'complete.json').read_text())
    assert complete['exit_code'] == 0 and complete['data_file_unchanged']
    assert complete['promoted'] is False
    started = json.loads((recovery / 'started.json').read_text())
    data_name = 'v2.2-commitment.0-1024000.kv'
    index_name = 'v2.1-commitment.0-1024000.kvi'
    data = SOURCE / 'snapshots/rebuild/domain' / data_name
    assert started['source_data'] == str(data)
    stat = data.stat()
    assert (stat.st_ino, stat.st_size, stat.st_mtime_ns) == (
        started['source_inode'], started['source_bytes'], started['source_mtime_ns'])
    assert os.path.samefile(data, recovery / 'datadir/snapshots/domain' / data_name)
    # At this pinned commit legacy commitments require the hash-map accessor.
    # A new partial index, old offsets or any unexpected range must be reviewed.
    generated = complete['generated_files']
    assert len(generated) == 1 and generated[0]['name'] == index_name
    index = recovery / 'datadir/snapshots/domain' / index_name
    assert index.stat().st_size == generated[0]['bytes'] > 0
    assert sorted(p.name for p in data.parent.iterdir()) == [data_name]
    assert not (SOURCE / 'snapshots/backup').exists()
    original_name = 'v1.1-commitment.0-1024000.kv'
    assert os.path.samefile(
        SOURCE / 'snapshots/domain' / original_name,
        ROOT / 'original-checkpoint/snapshots/domain' / original_name)
    assert (SOURCE / 'snapshots/erigondb.toml').read_bytes() == (
        recovery / 'datadir/snapshots/erigondb.toml').read_bytes()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
            assert ('--datadir=' + str(SOURCE)).encode() not in args, (
                'Source still open by native process', proc.name)
        except (FileNotFoundError, ProcessLookupError):
            continue
    with index.open('rb') as stream:
        index_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'index': str(index), 'index_sha256': index_hash,
            'index_bytes': index.stat().st_size, 'data': str(data),
            'data_inode': stat.st_ino, 'data_bytes': stat.st_size,
            'previous_options': ['--squeeze=false'],
            'resume_options': ['--squeeze=false', '--continue']}


def main(resume_schema=False, resume_index=False):
    with (ROOT / 'upgrade.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if resume_index:
            recovery_proof = index_resume_inputs()
        elif resume_schema:
            prior = json.loads((ROOT / 'status.json').read_text())
            assert prior == {**prior, 'phase': 'failed',
                              'error': 'before-commitments exited 2; inspect log'}
            assert (ROOT / 'checkpoint.json').exists()
            assert not (ROOT / 'unsqueeze.log').exists()
            assert "db-table doesn't exists: CommitmentBinHistoryKeys" in (ROOT / 'before-commitments.log').read_text()
            (ROOT / 'before-commitments.log').rename(ROOT / 'before-commitments-before-schema.log')
        else:
            assert not (ROOT / 'started.json').exists(), 'Inspect previous attempt; no automatic retry'
        fixture = json.loads((ROOT / 'fixtures.json').read_text())
        assert fixture['exit_code'] == 0
        integration_path = TOOLS / ('integration.pinned' if resume_index else 'integration')
        with integration_path.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == BUILD_SHA
        assert (SOURCE.parent / 'snapshot-fetcher/done').exists()
        assert shutil.disk_usage(SOURCE).free > 500_000_000_000
        assert not (SOURCE / 'snapshots/backup').exists()
        if not resume_index:
            assert not (SOURCE / 'snapshots/rebuild').exists()
        for cid in subprocess.check_output(['docker', 'ps', '-q'], text=True).splitlines():
            container = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
            for mount in container['Mounts']:
                if (container['Name'] == '/node_exporter' and mount['Source'] == '/'
                        and mount['Destination'] == '/rootfs' and not mount['RW']):
                    continue
                path = Path(mount['Source'])
                assert not (path == SOURCE or path in SOURCE.parents or SOURCE in path.parents), (
                    'Source overlaps running container mount', container['Name'], str(path))
        checkpoint = ROOT / 'original-checkpoint'
        if not resume_schema and not resume_index:
            save('started.json', {'time': time.time(), 'source': str(SOURCE),
                                  'source_block': BASE_BLOCK, 'integration_sha256': BUILD_SHA})
            checkpoint.mkdir()
            status('preserving_original_checkpoint')
            # Snapshot files are immutable; conversion stages replacement files
            # and renames originals. Mutable databases are independent copies.
            subprocess.run(['cp', '-al', str(SOURCE / 'snapshots'), str(checkpoint / 'snapshots')], check=True)
            for path in SOURCE.iterdir():
                if path.name == 'snapshots':
                    continue
                subprocess.run(['cp', '-a', '--reflink=auto', '--sparse=always',
                                str(path), str(checkpoint / path.name)], check=True)
            subprocess.run(['sync'], check=True)
            save('checkpoint.json', {'path': str(checkpoint), 'finished_at': time.time(),
                                     'immutable_snapshots_hardlinked': True,
                                     'mutable_databases_copied': True})
        common = ['--datadir=' + str(SOURCE), '--chain=mainnet']
        integration = str(integration_path)
        # The dedicated command creates new schema tables even when no numbered
        # migration is pending; ordinary accede-mode opens cannot create them.
        if resume_index:
            # Preserve the interruption evidence before linking the independently
            # completed accessor. The converter validates the complete prefix.
            for name in ('unsqueeze.log', 'status.json'):
                destination = ROOT / ('before-index-recovery-' + name)
                assert not destination.exists()
                (ROOT / name).rename(destination)
            index = Path(recovery_proof['index'])
            os.link(index, SOURCE / 'snapshots/rebuild/domain' / index.name)
            save('index-recovery-resume.json', {**recovery_proof, 'time': time.time()})
        else:
            run('schema-migrations', [integration, 'run_migrations', *common])
            run('before-commitments', [integration, 'commitment', 'print', *common])
        run('unsqueeze', [integration, 'commitment', 'convert', *common, '--squeeze=false',
                          *(['--continue'] if resume_index else [])])
        backup = SOURCE / 'snapshots/backup'
        if backup.exists():
            # The v3 converter refuses a nonempty backup directory. Preserve the
            # first stage's backups outside the source before the next stage.
            backup.rename(ROOT / 'unsqueeze-backup')
        run('convert-v3', [integration, 'commitment', 'convert', *common, '--v3'])
        run('verify-v3-files', [integration, 'commitment', 'verify', *common], v3=True)
        # Conversion resets execution rows to immutable files. Restore the same
        # original source block using its already stored blocks/configuration.
        run('restore-source-block', [integration, 'stage_exec', *common,
                                    '--block=' + str(BASE_BLOCK), '--experimental.commitment-v3'], v3=True)
        run('verify-v3-state', [integration, 'commitment', 'verify', *common], v3=True)
        run('after-commitments', [integration, 'commitment', 'print', *common], v3=True)
        save('conversion-complete.json', {'time': time.time(), 'source': str(SOURCE),
                                          'target_block': BASE_BLOCK,
                                          'native_reopen_qualified': False,
                                          'upload_authorized': False})
        status('converted_pending_native_reopen', target_block=BASE_BLOCK)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--resume-after-schema-preflight', action='store_true')
    mode.add_argument('--resume-after-index-recovery', action='store_true')
    mode.add_argument('--check-index-recovery', action='store_true')
    args = parser.parse_args()
    if args.check_index_recovery:
        # This check must not replace the original failure evidence.
        print(json.dumps(index_resume_inputs(), indent=2))
    else:
        try:
            main(args.resume_after_schema_preflight, args.resume_after_index_recovery)
        except Exception as exc:
            status('failed', error=str(exc))
            raise
