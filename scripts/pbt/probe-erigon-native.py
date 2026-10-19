#!/usr/bin/env python3
"""Compare native replay modes on private clones of the verified checkpoint."""
import argparse
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import time

from pipeline_rpc import ROOT, RPC, save

NATIVE = Path('/data/pbt-1/native')
PROBE = Path('/data/pbt-1/io-probe')
CHECKPOINT = Path('/data/pbt-1/erigon')
HEAD = 24468025
SHA = 'b799a0df4b18dcbd5c662640eca94c6b3913027a43d1375dc8aceb4766c725ce'
IMMUTABLE = {'.kv', '.ef', '.seg', '.v', '.kvi', '.vi', '.efi', '.bt', '.kvei', '.idx'}


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def state(unit):
    output = run('systemctl', 'show', unit, '-p', 'ActiveState', '-p', 'MainPID',
                 '-p', 'Result', '-p', 'ExecMainCode', '-p', 'ExecMainStatus', '-p', 'InvocationID')
    return dict(line.split('=', 1) for line in output.splitlines())


def verify_stop(unit, invocation):
    assert len(invocation) == 32
    stopped = state(unit)
    assert stopped['ActiveState'] == 'inactive' and stopped['MainPID'] == '0', stopped
    assert stopped['Result'] == 'success', stopped
    events = [json.loads(line) for line in run('journalctl', '-u', unit,
        'INVOCATION_ID='+invocation, '-o', 'json', '--no-pager').splitlines()]
    success = [event for event in events if event.get('MESSAGE_ID') == '7ad2d189f7e94e70a38c781354912448']
    assert len(success) == 1, 'Require systemd successful deactivation for this exact invocation'
    return {'state': stopped, 'invocation': invocation, 'deactivation': success[0]}


def stop_verified(unit, path):
    invocation = state(unit)['InvocationID']
    subprocess.run(['systemctl', 'stop', unit], check=True, timeout=1810)
    save(path, verify_stop(unit, invocation))


def namespace(unit, *args):
    current = state(unit)
    assert current['ActiveState'] == 'active' and int(current['MainPID']) > 0, current
    return ['nsenter', '--target', current['MainPID'], '--net', *args]


def io_sample(unit):
    pid = state(unit)['MainPID']
    return {'time': time.time(), 'pid': int(pid),
        'process': {key: int(value) for key, value in
                    (line.split(':', 1) for line in Path('/proc', pid, 'io').read_text().splitlines())},
        'device': [int(value) for value in Path('/sys/block/vda/stat').read_text().split()],
        'pressure': Path('/proc/pressure/io').read_text()}


def audit(phase, trial, blocks):
    spec = importlib.util.spec_from_file_location('activation', '/data/pbt-1/activate-erigon-probe.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PROBE = trial
    module.TARGET = HEAD+blocks
    module.audit(phase)


def wait_ready(unit):
    deadline = time.monotonic()+1800
    while True:
        result = subprocess.run(namespace(unit, 'curl', '-fsS', '--max-time', '10',
            '-H', 'Content-Type: application/json', '--data',
            '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}',
            'http://127.0.0.1:18545'), capture_output=True, text=True)
        if result.returncode == 0 and json.loads(result.stdout).get('result'):
            return
        assert time.monotonic() < deadline, 'Inspect startup before retrying'
        time.sleep(5)


def replay(trial, blocks):
    rpc = RPC()
    assert int(rpc.head()['number'], 16) == HEAD
    durations = []
    started = time.monotonic()
    for offset in range(1, blocks+1):
        number = HEAD+offset
        record = json.loads(gzip.decompress((ROOT/'blocks'/f'{number:08d}.json.gz').read_bytes()))
        before = time.monotonic()
        head = rpc.apply(record)
        durations.append(time.monotonic()-before)
        save(trial/'replay-progress.json', {'time': time.time(), 'head': number,
            'hash': head['hash'], 'state_root': head['stateRoot'], 'bal_hash': head['blockAccessListHash'],
            'completed': offset, 'target_blocks': blocks})
    measured = sum(durations[8:])
    save(trial/'replay-timing.json', {'time': time.time(), 'blocks': blocks,
        'elapsed_seconds': time.monotonic()-started, 'warmup_blocks': 8,
        'measured_blocks': blocks-8, 'measured_apply_seconds': measured,
        'measured_blocks_per_second': (blocks-8)/measured, 'apply_seconds_per_block': durations})


def clone(trial):
    data = trial/'data'
    data.mkdir()
    files = 0
    copied = 0
    linked = 0
    for directory, dirs, names in os.walk(CHECKPOINT):
        relative = Path(directory).relative_to(CHECKPOINT)
        destination = data/relative
        destination.mkdir(exist_ok=True)
        for name in names:
            source = Path(directory)/name
            target = destination/name
            assert source.is_file() and not source.is_symlink(), source
            if relative.parts and relative.parts[0] == 'snapshots' and source.suffix in IMMUTABLE:
                os.link(source, target)
                linked += source.stat().st_size
            else:
                shutil.copy2(source, target)
                assert source.stat().st_ino != target.stat().st_ino
                copied += source.stat().st_size
            files += 1
    assert files == 179485
    assert digest(data/'chaindata/mdbx.dat') == SHA
    subprocess.run(['sync', '-f', str(data/'chaindata/mdbx.dat')], check=True)
    save(trial/'clone.json', {'files': files, 'copied_bytes': copied, 'linked_bytes': linked,
                              'chaindata_sha256': SHA, 'source': str(CHECKPOINT)})
    return data


def main(args):
    lock = (NATIVE/'benchmark.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    trial = NATIVE/args.variant
    assert not trial.exists(), 'Inspect prior trial; never overwrite replay evidence'
    copy = json.loads((PROBE/'checkpoint-copy-status.json').read_text())
    assert copy['phase'] == 'copied_verified' and copy['chaindata_sha256'] == SHA
    assert copy['file_count'] == 179485
    revoked = json.loads((PROBE/'checkpoint-read-access-revoked.json').read_text())
    assert revoked['matching_entries_after'] == 0 and revoked['private_key_removed']
    assert not (PROBE/'checkpoint-read-key').exists()
    assert not run('docker', 'ps', '-q')
    assert digest(CHECKPOINT/'chaindata/mdbx.dat') == SHA
    assert shutil.disk_usage(NATIVE).free > 150*1024**3
    build = json.loads((NATIVE/'build-report.json').read_text())
    assert build['source_commit'] == '8c1e3893d77d230720d172f1492d95b5777a862c'
    binary_name = 'stock' if args.variant == 'stock' else 'profile'
    artifact = next(item for item in build['builds'] if item['name'] == binary_name)
    binary = Path(artifact['path'])
    assert digest(binary) == artifact['sha256']
    for number in range(HEAD, HEAD+args.blocks+1):
        assert (ROOT/'blocks'/f'{number:08d}.json.gz').is_file(), number
    trial.mkdir()
    shutil.copy2(PROBE/'maintenance-restart-before.json', trial/'maintenance-restart-before.json')
    data = clone(trial)
    jwt = ROOT/'jwt'
    if not jwt.exists():
        jwt.write_text(secrets.token_hex(32)); jwt.chmod(0o600)
    original = json.loads((PROBE/'source-command.json').read_text())
    image = next(item for item in original if item.startswith('erigontech/erigon@sha256:'))
    client_args = original[original.index(image)+1:]
    assert '--exec.no-background-maintenance=true' in client_args
    assert '--exec.no-prune=true' not in client_args
    client_args = [f'--datadir={data}' if item == '--datadir=/data' else
                   f'--authrpc.jwtsecret={jwt}' if item == '--authrpc.jwtsecret=/jwt' else item
                   for item in client_args]
    if args.variant == 'profile-no-writemap':
        client_args.append('--db.writemap=false')
    client_args += ['--pprof', '--pprof.addr=127.0.0.1', '--pprof.port=6060']
    unit = 'pbt-1-native-'+args.variant
    command = [str(binary), *client_args]
    save(trial/'command.json', command)
    unit_path = Path('/etc/systemd/system')/(unit+'.service')
    assert not unit_path.exists(), 'Existing trial unit requires inspection'
    unit_text = '\n'.join(['[Unit]', 'Description=Isolated PBT native replay trial', '[Service]',
        'Type=exec', 'PrivateNetwork=yes', 'MemoryMax=48G', 'MemorySwapMax=0', 'AllowedCPUs=0-7',
        'KillSignal=SIGINT', 'SuccessExitStatus=130', 'TimeoutStopSec=1800', 'SendSIGKILL=no',
        'StandardOutput=append:'+str(trial/'client.log'), 'StandardError=inherit',
        'Environment=COMPRESS_WORKERS=2 MERGE_WORKERS=2 MDBX_TRACE_TX=true REPLAY_PROFILE=true',
        'ExecStart='+shlex.join(command), ''])
    unit_path.write_text(unit_text)
    (trial/'client.service').write_text(unit_text)
    subprocess.run(['systemd-analyze', 'verify', str(unit_path)], check=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'start', unit], check=True)
    wait_ready(unit)
    def check(phase):
        subprocess.run(namespace(unit, 'python3', '-u', __file__, '--variant', args.variant,
            '--blocks', str(args.blocks), '--audit', phase), check=True)
    check('checkpoint')
    save(trial/'status.json', {'phase': 'replaying', 'time': time.time(), 'blocks': args.blocks})
    profile = subprocess.Popen(namespace(unit, 'curl', '-fsS', '--max-time', '75',
        '-o', str(trial/'cpu.pprof'), 'http://127.0.0.1:6060/debug/pprof/profile?seconds=60'))
    io_before = io_sample(unit)
    log_start = (trial/'client.log').stat().st_size
    started = time.monotonic()
    try:
        subprocess.run(namespace(unit, 'python3', '-u', __file__, '--variant', args.variant,
            '--blocks', str(args.blocks), '--replay'), check=True)
        elapsed = time.monotonic()-started
        io_after = io_sample(unit)
        log_end = (trial/'client.log').stat().st_size
    finally:
        profile_code = profile.wait(timeout=80)
    save(trial/'timing.json', {'time': time.time(), 'blocks': args.blocks,
        'seconds': elapsed, 'blocks_per_second': args.blocks/elapsed, 'cpu_profile_exit_code': profile_code,
        'binary': artifact, 'normal_durability': True, 'memory_GiB': 48, 'cpus': '0-7',
        'log_window': {'start_byte': log_start, 'end_byte': log_end},
        'replay': json.loads((trial/'replay-timing.json').read_text())})
    save(trial/'io.json', {'before': io_before, 'after': io_after,
        'device_write_bytes_per_block': (io_after['device'][6]-io_before['device'][6])*512/args.blocks,
        'process_write_bytes_per_block': (io_after['process']['write_bytes']-io_before['process']['write_bytes'])/args.blocks})
    check('before')
    stop_verified(unit, trial/'shutdown.json')
    subprocess.run(['systemctl', 'start', unit], check=True)
    wait_ready(unit)
    check('after')
    stop_verified(unit, trial/'final-shutdown.json')
    assert digest(CHECKPOINT/'chaindata/mdbx.dat') == SHA, 'Pristine source checkpoint changed'
    save(trial/'status.json', {'phase': 'verified_stopped', 'time': time.time(), 'blocks': args.blocks,
        'head': HEAD+args.blocks, 'all_bodies_verified_before_and_after': True,
        'canonical_routing_changed': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', choices=['stock', 'profile', 'profile-no-writemap'], required=True)
    parser.add_argument('--blocks', type=int, default=64)
    parser.add_argument('--audit', choices=['checkpoint', 'before', 'after'])
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    assert 64 <= args.blocks <= 256
    if args.audit:
        audit(args.audit, NATIVE/args.variant, args.blocks)
    elif args.replay:
        replay(NATIVE/args.variant, args.blocks)
    else:
        try:
            main(args)
        except Exception as exc:
            trial = NATIVE/args.variant
            if trial.is_dir():
                save(trial/'status.json', {'phase': 'failed', 'time': time.time(), 'error': str(exc)})
            raise
