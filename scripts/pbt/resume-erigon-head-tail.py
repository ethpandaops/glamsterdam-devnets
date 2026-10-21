#!/usr/bin/env python3
"""Resume the verified H tail with a larger native batch; retain every audit gate.

This one-shot handoff requires a recorded intentional stop of the exact former
wrapper/native pair. It never converts again, changes forks, or publishes data.
"""
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

BASE = Path('/data/pbt-1')
ROOT = BASE / 'v3-head-upgrade'
HANDOFF = ROOT / 'tail-batch-handoff'
NATIVE = BASE / 'v3-tools-372df0e6/integration.pinned'
NATIVE_SHA = 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03'
DRIVER_SHA = '81de334b2ea4fc32afd4ed60d24cf7d3ebc96fec347296519e64985deff70b6f'
TARGET = 24503958


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run_phase(driver, name, command):
    driver.run(name, command, v3=True)
    proof = read(ROOT / (name + '.json'))
    proof.update(binary_sha256=sha(Path(command[0])), no_prune_env=os.environ['NO_PRUNE'])
    driver.save(name + '.json', proof)


def validate_stop(receipt, stopped, conversion, verification):
    assert receipt['reason'] == 'increase_native_tail_batch_512MiB_to_4GiB'
    assert receipt['target_block'] == TARGET
    assert receipt['native_binary_sha256'] == NATIVE_SHA
    assert receipt['native_pid'] == 88242 and receipt['native_start_ticks'] == '6041299'
    assert receipt['wrapper_pid'] == 23668
    assert stopped['native_gone'] and stopped['wrapper_gone']
    assert stopped['forced_kill'] is False
    assert stopped['native_completion_proof_absent']
    assert conversion['exit_code'] == verification['exit_code'] == 0
    assert verification['binary_sha256'] == NATIVE_SHA
    assert verification['command'][1:3] == ['commitment', 'verify']
    assert verification['commitment_v3_env'] and verification['no_prune_env'] == 'true'
    assert '--datadir=/data/pbt-1/erigon' in verification['command']


def main():
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-2'
    spec = importlib.util.spec_from_file_location('driver', BASE / 'upgrade-erigon-head-v3.py')
    assert hashlib.sha256(Path(spec.origin).read_bytes()).hexdigest() == DRIVER_SHA
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    with (ROOT / 'upgrade.lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert sha(NATIVE) == NATIVE_SHA
        receipt, stopped = read(HANDOFF / 'stop-requested.json'), read(HANDOFF / 'stopped.json')
        conversion, verification = read(ROOT / 'convert-v3.json'), read(ROOT / 'verify-v3-files.json')
        validate_stop(receipt, stopped, conversion, verification)
        for pid in (receipt['native_pid'], receipt['wrapper_pid']):
            assert not (Path('/proc') / str(pid)).exists()
        for name in ('restore-head-block.json', 'verify-v3-state.json', 'conversion-complete.json'):
            assert not (ROOT / name).exists(), name
        assert not (HANDOFF / 'resumed.json').exists(), 'Inspect the previous resume attempt'
        assert not (BASE / 'qualification/result.json').exists()
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit() or int(proc.name) == os.getpid():
                continue
            try:
                args = (proc / 'cmdline').read_bytes().split(b'\0')
            except (FileNotFoundError, PermissionError):
                continue
            if args and (b'integration' in args[0] or Path(os.fsdecode(args[0])).name == 'erigon'):
                assert not any(b'/data/pbt-1/erigon' in arg for arg in args)
        for cid in subprocess.check_output(['docker', 'ps', '-q'], text=True).splitlines():
            info = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
            for mount in info['Mounts']:
                path = Path(mount['Source'])
                if mount['RW']:
                    assert not (path == driver.SOURCE or path in driver.SOURCE.parents or driver.SOURCE in path.parents)
        start = read(ROOT / 'started.json')
        archive = Path(start['rollback_archive'])
        stat = archive.stat()
        assert archive.parent.is_mount()
        assert stat.st_size == start['rollback_proof']['bytes'] == driver.ARCHIVE_BYTES
        assert stat.st_mtime_ns == start['rollback_proof']['mtime_ns']
        assert start['rollback_proof']['sha256'] == driver.ARCHIVE_SHA
        assert shutil.disk_usage(driver.SOURCE).free > 600_000_000_000
        for name in ('status.json', 'restore-head-block.log'):
            shutil.copy2(ROOT / name, HANDOFF / ('before-' + name))
        profiles = HANDOFF / 'profiles-before'
        profiles.mkdir()
        for path in (driver.SOURCE / 'temp').glob('stage_exec_*.pprof'):
            shutil.copy2(path, profiles / path.name)
        (HANDOFF / 'resumed.json').write_text(json.dumps({
            'time': time.time(), 'batch_size': '4G', 'binary_sha256': NATIVE_SHA,
            'genesis_time': None, 'pbt_activation': False,
        }, indent=2) + '\n')
        common = ['--datadir=' + str(driver.SOURCE), '--chain=mainnet']
        os.environ['NO_PRUNE'] = 'true'
        try:
            run_phase(driver, 'restore-head-block', [str(NATIVE), 'stage_exec', *common,
                      '--block=' + str(TARGET), '--experimental.commitment-v3', '--batchSize=4G'])
            run_phase(driver, 'verify-v3-state', [str(NATIVE), 'commitment', 'verify', *common])
            run_phase(driver, 'after-commitments', [str(NATIVE), 'commitment', 'print', *common])
            driver.save('conversion-complete.json', {
                'time': time.time(), 'source': str(driver.SOURCE), 'target_block': TARGET,
                'native_reopen_qualified': False, 'publication_authorized': False,
                'converter_build': conversion['converter_build'],
                'tail_batch_handoff': str(HANDOFF),
            })
            driver.save('status.json', {'phase': 'converted_pending_native_reopen',
                        'time': time.time(), 'target_block': TARGET})
        except Exception as exc:
            driver.save('status.json', {'phase': 'failed', 'time': time.time(),
                        'target_block': TARGET, 'error': str(exc)})
            raise


if __name__ == '__main__':
    main()
