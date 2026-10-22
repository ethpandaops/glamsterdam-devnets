#!/usr/bin/env python3
"""Reviewed, intentional H conversion handoff; original binaries verify output.

check performs read-only checks on the running first shard. interrupt preserves
its provenance and requests SIGINT. run requires that recorded process to have
stopped before selecting equivalent domain fragments and resuming natively.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
import fcntl

BASE = Path('/data/pbt-1')
ROOT = BASE / 'v3-head-upgrade'
SOURCE = BASE / 'erigon'
REVIEW = BASE / 'boundary-review'
HANDOFF = ROOT / 'bounded-view-handoff'
ORIGINAL = BASE / 'v3-tools-372df0e6/integration.pinned'
CANDIDATE = REVIEW / 'integration-bounded-view'
CANDIDATE_SHA = '1f807caefedc534ae837641ebff1dfdc37c0378ea8e3556263bddd1eb276e9f3'
ORIGINAL_SHA = 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03'
PATCH_SHA = '4b04368aad6cf9ee38058eb5d6e6bed79ac251a49138b9c9c28a0c6455483ab9'
REVIEW_SCRIPT_SHA = '32f6ccbc86ab1662ef5d7b218c46678cb8eabf2c1bf5e8a337c7c8c07e9ca0a7'
DRIVER_SHA = '81de334b2ea4fc32afd4ed60d24cf7d3ebc96fec347296519e64985deff70b6f'
NATIVE_PID = 20231


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def module(path, checksum, name):
    assert sha(path) == checksum
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def review():
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-2'
    assert sha(CANDIDATE) == CANDIDATE_SHA and sha(ORIGINAL) == ORIGINAL_SHA
    report = read(REVIEW / 'erigon-bounded-view-review.json')
    assert report['status'] == 'candidate_built_not_deployed'
    assert report['patch_sha256'] == PATCH_SHA
    assert report['build']['binary_sha256'] == CANDIDATE_SHA
    assert report['fixture_suite']['top_level_tests_passed'] == 20
    assert len(report['records']) == 5
    assert sha(REVIEW / 'bounded-view-fixtures.log') == report['fixture_suite']['log_sha256']
    started = read(ROOT / 'started.json')
    job = read(BASE / 'qualification/job.json')
    assert started['host'] == socket.gethostname() and started['source'] == str(SOURCE)
    assert started['target_block'] == job['head'] == 24503958
    assert started['target_hash'] == job['head_hash']
    assert started['target_state_root'] == job['state_root']
    assert started['binaries']['integration'] == ORIGINAL_SHA
    assert started['commit'] == report['base_commit']
    archive = Path(started['rollback_archive'])
    proof = read(archive.parent / 'archive-verified.json')
    stat = archive.stat()
    assert archive.parent.is_mount()
    assert proof['sha256'] == started['rollback_sha256'] == 'e511af776332da1497c537b58770bec0b7e962c1484cd2dcb9a9d30f6ac268a7'
    assert stat.st_size == proof['bytes'] == 534953200071 and stat.st_mtime_ns == proof['mtime_ns']
    assert read(ROOT / 'unsqueeze.json')['exit_code'] == 0
    assert (ROOT / 'unsqueeze-backup').is_dir() and not (SOURCE / 'snapshots/backup').exists()
    assert not list((SOURCE / 'snapshots/rebuild/domain').iterdir()), 'First shard is no longer incomplete'
    assert shutil.disk_usage(SOURCE).free > 600_000_000_000
    boundary = module(BASE / 'resume-erigon-head-boundaries.py', REVIEW_SCRIPT_SHA, 'boundary')
    checked, moved = boundary.validate_plan(read(REVIEW / 'head-plan.json'), read(REVIEW / 'head-files.json'),
                                            {d: read(REVIEW / (d + '-compare.json')) for d in ('accounts', 'storage')})
    assert read(REVIEW / 'comparisons-complete.json')['all_records_equal']
    for item in checked + moved:
        boundary.same_file(SOURCE / 'snapshots/domain' / item['name'], item)
    driver = module(BASE / 'upgrade-erigon-head-v3.py', DRIVER_SHA, 'upgrade')
    return boundary, driver, moved, report


def validate_running_process(status, command, binary_sha):
    assert status['phase'] == 'convert-v3' and status['target_block'] == 24503958
    assert command == [str(ORIGINAL), 'commitment', 'convert', '--datadir=' + str(SOURCE), '--chain=mainnet', '--v3']
    assert binary_sha == ORIGINAL_SHA


def running():
    boundary, driver, moved, report = review()
    assert not HANDOFF.exists(), 'Prior handoff requires inspection'
    assert boundary.unit('pbt-1-v3-head-upgrade')['ActiveState'] == 'active'
    proc = Path('/proc') / str(NATIVE_PID)
    command = [os.fsdecode(arg) for arg in (proc / 'cmdline').read_bytes().split(b'\0') if arg]
    validate_running_process(read(ROOT / 'status.json'), command, sha(proc / 'exe'))
    assert read(BASE / 'qualification/status.json')['phase'] == 'waiting_for_erigon_conversion'
    assert not (BASE / 'qualification/result.json').exists()
    return {'time': time.time(), 'pid': NATIVE_PID, 'proc_start_ticks': (proc / 'stat').read_text().split()[21],
            'command': command, 'original_binary_sha256': ORIGINAL_SHA,
            'candidate_binary_sha256': CANDIDATE_SHA, 'patch_sha256': PATCH_SHA,
            'reason': 'Intentional switch to tested bounded file-view optimization',
            'move': moved, 'completed_shards': 0, 'source': str(SOURCE), 'target_block': 24503958,
            'genesis_time': None}


def interrupt():
    proof = running()
    HANDOFF.mkdir()
    write(HANDOFF / 'stop-requested.json', proof)
    # The qualifier is only a waiter at this point; it must not treat the
    # deliberate interruption as a successfully converted database.
    subprocess.run(['systemctl', 'stop', 'pbt-1-worker-qualification'], check=True)
    proc = Path('/proc') / str(NATIVE_PID)
    assert (proc / 'stat').read_text().split()[21] == proof['proc_start_ticks']
    assert sha(proc / 'exe') == ORIGINAL_SHA
    os.kill(NATIVE_PID, signal.SIGINT)
    print('SIGINT requested for recorded native converter; wait for the parent unit to stop.')


def run():
    with (ROOT / 'upgrade.lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        boundary, driver, moved, report = review()
        receipt = read(HANDOFF / 'stop-requested.json')
        assert receipt['pid'] == NATIVE_PID and receipt['candidate_binary_sha256'] == CANDIDATE_SHA
        assert not (Path('/proc') / str(NATIVE_PID)).exists(), 'Original converter has not stopped'
        assert boundary.unit('pbt-1-worker-qualification')['MainPID'] == '0'
        unit = boundary.unit('pbt-1-v3-head-upgrade')
        assert unit['MainPID'] in ('0', str(os.getpid()))
        status = read(ROOT / 'status.json')
        assert status['phase'] == 'failed' and status['target_block'] == 24503958
        assert 'context canceled' in (ROOT / 'convert-v3.log').read_text()
        assert not (HANDOFF / 'selection-applied.json').exists()
        # No native or container owner may race the file selection.
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit() or int(proc.name) == os.getpid():
                continue
            try:
                args = (proc / 'cmdline').read_bytes().split(b'\0')
            except (FileNotFoundError, PermissionError):
                continue
            if args and (b'integration' in args[0] or Path(os.fsdecode(args[0])).name == 'erigon'):
                assert not any(os.fsencode(str(SOURCE)) in arg for arg in args)
        for cid in subprocess.check_output(['docker', 'ps', '-q'], text=True).splitlines():
            info = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
            for mount in info['Mounts']:
                if info['Name'] == '/node_exporter' and mount['Source'] == '/' and not mount['RW']:
                    continue
                path = Path(mount['Source'])
                assert not (path == SOURCE or path in SOURCE.parents or SOURCE in path.parents)
        for name in ('status.json', 'convert-v3.log'):
            shutil.copy2(ROOT / name, HANDOFF / ('before-' + name))
        hidden = HANDOFF / 'hidden-domain-files'
        hidden.mkdir()
        for item in moved:
            (SOURCE / 'snapshots/domain' / item['name']).rename(hidden / item['name'])
        write(HANDOFF / 'selection-applied.json', {'time': time.time(), 'files': moved,
              'basis': 'Full logical record equality and indexed contiguous coverage already verified'})
        build = {'base_commit': report['base_commit'], 'patch_sha256': PATCH_SHA,
                 'binary_sha256': CANDIDATE_SHA, 'binary': str(CANDIDATE),
                 'independent_verifier_sha256': ORIGINAL_SHA}
        common = ['--datadir=' + str(SOURCE), '--chain=mainnet']
        try:
            for phase, command, v3 in [
                ('convert-v3', [str(CANDIDATE), 'commitment', 'convert', *common, '--v3', '--continue'], False),
                ('verify-v3-files', [str(ORIGINAL), 'commitment', 'verify', *common], True),
                ('restore-head-block', [str(ORIGINAL), 'stage_exec', *common, '--block=24503958', '--experimental.commitment-v3'], True),
                ('verify-v3-state', [str(ORIGINAL), 'commitment', 'verify', *common], True),
                ('after-commitments', [str(ORIGINAL), 'commitment', 'print', *common], True),
            ]:
                os.environ['NO_PRUNE'] = 'true'
                driver.run(phase, command, v3=v3)
                evidence = read(ROOT / (phase + '.json'))
                evidence['binary_sha256'] = sha(Path(command[0]))
                evidence['no_prune_env'] = 'true'
                if phase == 'convert-v3':
                    evidence['converter_build'] = build
                driver.save(phase + '.json', evidence)
            driver.save('conversion-complete.json', {'time': time.time(), 'source': str(SOURCE),
                        'target_block': 24503958, 'native_reopen_qualified': False,
                        'publication_authorized': False, 'converter_build': build})
            driver.save('status.json', {'phase': 'converted_pending_native_reopen', 'time': time.time(), 'target_block': 24503958})
        except Exception as exc:
            driver.save('status.json', {'phase': 'failed', 'time': time.time(), 'target_block': 24503958, 'error': str(exc)})
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'interrupt', 'run'))
    action = parser.parse_args().action
    if action == 'check':
        print(json.dumps(running(), indent=2))
    elif action == 'interrupt':
        interrupt()
    else:
        run()
