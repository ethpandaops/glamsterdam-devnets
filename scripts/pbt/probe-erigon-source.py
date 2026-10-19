#!/usr/bin/env python3
"""Compare native replay on the original VM, then verify the pinned client reopen."""
import fcntl
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time

from pipeline_rpc import ROOT, RPC, ANCHOR, save
from reopen import stop

PILOT = Path('/data/pbt-1/native-source-pilot')
DATA = Path('/data/pbt-1/erigon')
NAME = 'pbt-1-erigon-execution'
UNIT = 'pbt-1-native-source-client'
BINARY = Path('/data/pbt-1/erigon-native-batch')
SHA = 'b1c3fc01aff41318597763c2b5b9c46ee16354995c279000ef4ac4b8db443403'
IMMUTABLE = {'.kv', '.ef', '.seg', '.v', '.kvi', '.vi', '.efi', '.bt', '.kvei', '.idx'}


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def native_helpers():
    spec = importlib.util.spec_from_file_location('native', '/data/pbt-1/probe-erigon-native.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def inspect():
    return json.loads(run('docker', 'inspect', NAME))[0]


def record(number):
    return json.loads(gzip.decompress((ROOT/'blocks'/f'{number:08d}.json.gz').read_bytes()))


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def checkpoint(head):
    destination = PILOT/'checkpoint'
    destination.mkdir()
    copied = linked = files = 0
    db_sha = None
    for directory, dirs, names in os.walk(DATA):
        relative = Path(directory).relative_to(DATA)
        target_dir = destination/relative
        target_dir.mkdir(exist_ok=True)
        for name in names:
            if name in ('LOCK', 'mdbx.lck') or name.endswith('.lock') or '.tmp' in name:
                continue
            source = Path(directory)/name
            target = target_dir/name
            assert source.is_file() and not source.is_symlink(), source
            initial = source.stat()
            if relative.parts and relative.parts[0] == 'snapshots' and source.suffix in IMMUTABLE:
                os.link(source, target)
                linked += initial.st_size
            elif relative == Path('chaindata') and name == 'mdbx.dat':
                hasher = hashlib.sha256()
                with source.open('rb') as src, target.open('xb') as dst:
                    while chunk := src.read(16*1024**2):
                        hasher.update(chunk)
                        dst.write(chunk)
                    dst.flush()
                    os.fsync(dst.fileno())
                shutil.copystat(source, target)
                assert source.stat().st_mtime_ns == initial.st_mtime_ns
                db_sha = hasher.hexdigest()
                assert digest(target) == db_sha
                copied += initial.st_size
            else:
                shutil.copy2(source, target)
                copied += initial.st_size
            assert target.stat().st_size == initial.st_size
            files += 1
    assert db_sha
    subprocess.run(['sync', '-f', str(destination)], check=True)
    save(PILOT/'checkpoint.json', {'time': time.time(), 'head': head, 'path': str(destination),
        'data_files_excluding_locks': files, 'copied_bytes': copied, 'linked_immutable_bytes': linked,
        'chaindata_sha256': db_sha, 'client_cleanly_stopped': True})
    helper = Path('/data/pbt-1/erigon-bal-backfill')
    build = json.loads(helper.with_suffix('.json').read_text())
    assert build['client_revision'] == '8c1e3893d77d230720d172f1492d95b5777a862c'
    assert digest(helper) == build['binary_sha256']
    subprocess.run([str(helper), '--db', str(destination/'chaindata'),
        '--records', str(ROOT/'blocks'), '--start', str(int(head['number'], 16)),
        '--end', str(int(head['number'], 16)), '--dry-run',
        '--report', str(PILOT/'checkpoint-native.json')], env={**os.environ, 'GOMEMLIMIT': '4GiB'}, check=True)
    verified = json.loads((PILOT/'checkpoint-native.json').read_text())
    assert verified['dry_run'] and verified['verified_records'] == 1
    assert verified['head_hash'] == head['hash'] and verified['state_root'] == head['stateRoot']


def audit(phase):
    rpc = RPC()
    prior = json.loads((PILOT/'before.json').read_text())
    head = rpc.head()
    first = int(prior['head']['number'], 16)
    last = int(head['number'], 16)
    assert last == (first if phase == 'opened' else first+192)
    numbers = {entry['number'] for entry in prior['samples']} | set(range(first+1, last+1)) | {last}
    samples = []
    for number in sorted(numbers):
        want = record(number)
        header = rpc.call('eth_getBlockByNumber', [hex(number), False])
        for key, field in [('hash', 'hash'), ('stateRoot', 'state_root'), ('blockAccessListHash', 'bal_hash')]:
            assert header[key] == want[field], (number, key)
        bodies = rpc.call('engine_getPayloadBodiesByRangeV2', [hex(number), '0x1'], True)
        assert len(bodies) == 1 and bodies[0]
        for key in ('blockAccessList', 'transactions', 'withdrawals'):
            assert bodies[0][key] == want['new_payload'][0][key], (number, key)
        samples.append({'number': number, 'hash': header['hash'],
            'state_root': header['stateRoot'], 'bal_hash': header['blockAccessListHash']})
    assert rpc.head() == head
    if phase == 'opened':
        assert head == prior['head'] and samples == prior['samples']
    if phase == 'pinned-reopen':
        expected = json.loads((PILOT/'native-after.json').read_text())
        assert head == expected['head'] and samples == expected['samples']
    save(PILOT/(phase+'.json'), {'time': time.time(), 'head': head, 'samples': samples,
                               'verified_bodies': len(samples)})


def persist_fence(head_before):
    started = time.monotonic()
    while True:
        seen = False
        for line in (PILOT/'client.log').read_text().splitlines():
            if '[replay-profile] forkchoice' in line and f'headBefore={head_before} ' in line:
                seen = True
            if seen and 'Timings: Post-Forkchoice' in line:
                return time.monotonic()-started
        assert time.monotonic()-started < 600, 'Inspect native persistence before retrying'
        time.sleep(.05)


def replay():
    rpc = RPC()
    first = int(json.loads((PILOT/'before.json').read_text())['head']['number'], 16)
    assert int(rpc.head()['number'], 16) == first
    for mode, start, count, batch in [('sequential', first+1, 64, 1), ('batch', first+65, 128, 8)]:
        durations = []
        for low in range(start, start+count, batch):
            records = [record(number) for number in range(low, low+batch)]
            before = time.monotonic()
            if batch == 1:
                rpc.apply(records[0])
            else:
                raw = [json.loads(gzip.decompress((PILOT/'raw'/f'{r["number"]:08d}.json.gz').read_bytes()))['raw'] for r in records]
                hashes = rpc.call('testing_insertRawBlocksV1', [raw, [r['new_payload'][0]['blockAccessList'] for r in records]])
                assert hashes == [r['hash'] for r in records]
                deadline = time.monotonic()+600
                while True:
                    result = rpc.call('engine_forkchoiceUpdatedV3', records[-1]['forkchoice'], True)['payloadStatus']
                    if result['status'] == 'VALID':
                        assert result['latestValidHash'] == records[-1]['hash']
                        break
                    assert result['status'] == 'SYNCING' and time.monotonic() < deadline, result
                    time.sleep(.05)
                for item in records:
                    result = rpc.call('engine_newPayloadV5', item['new_payload'], True)
                    assert result['status'] == 'VALID' and result['latestValidHash'] == item['hash'], result
                    header = rpc.call('eth_getBlockByNumber', [hex(item['number']), False])
                    for key, field in [('hash', 'hash'), ('stateRoot', 'state_root'), ('blockAccessListHash', 'bal_hash')]:
                        assert header[key] == item[field], (item['number'], key)
                assert rpc.head()['hash'] == records[-1]['hash']
            durations.extend([(time.monotonic()-before)/batch]*batch)
            save(PILOT/'progress.json', {'time': time.time(), 'mode': mode, 'head': low+batch-1,
                'mode_completed': low-start+batch, 'mode_blocks': count})
            save(ROOT/'status.json', {'phase': 'restart_validation', 'time': time.time(),
                'head': low+batch-1, 'reason': 'Bounded source comparison: '+mode})
        tail = persist_fence(start+count-batch-1)
        for index in range(count-batch, count):
            durations[index] += tail/batch
        measured = sum(durations[8:])
        save(PILOT/(mode+'-timing.json'), {'time': time.time(), 'start': start, 'end': start+count-1,
            'blocks': count, 'batch_size': batch, 'warmup_blocks': 8, 'measured_blocks': count-8,
            'measured_seconds': measured, 'blocks_per_second': (count-8)/measured,
            'final_persistence_wait_seconds': tail, 'seconds_per_block': durations,
            'duration_allocation': 'batch time divided equally; not individual block latency'})


def main():
    lock = (ROOT/'native-source-pilot.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not PILOT.exists(), 'Inspect prior source pilot; never overwrite evidence'
    assert digest(BINARY) == SHA
    proof = json.loads(Path('/data/pbt-1/native-batch-comparison.json').read_text())
    assert proof['same_head_after_restart'] and proof['batch_speedup'] > 1.3
    original = inspect()
    assert original['State']['Running'] and not original['State']['OOMKilled']
    assert original['HostConfig']['NetworkMode'] == 'none'
    assert original['HostConfig']['Memory'] == original['HostConfig']['MemorySwap'] == 48*1024**3
    command = json.loads((ROOT/'client-command.json').read_text())
    image = original['Config']['Image']
    assert command[command.index(image)+1:] == original['Config']['Cmd']
    assert '--exec.no-background-maintenance=true' in command and '--exec.no-prune=true' not in command
    assert not any('MDBX_NO_FSYNC' in value for value in command+original['Config']['Env'])
    assert shutil.disk_usage(DATA).free > 300*1024**3
    PILOT.mkdir()
    save(PILOT/'original-command.json', command)
    subprocess.run(['systemctl', 'stop', 'pbt-1-full-run.service'], check=True)
    save(ROOT/'status.json', {'phase': 'restart_validation', 'time': time.time(),
        'reason': 'Bounded original-VM native replay comparison'})
    time.sleep(5)
    subprocess.run(['nsenter', '--target', str(inspect()['State']['Pid']), '--net', 'python3',
        '/data/pbt-1/suppress-erigon-maintenance.py', '--audit', str(PILOT/'before.json')], check=True)
    before = json.loads((PILOT/'before.json').read_text())
    first = int(before['head']['number'], 16)
    for number in range(first+1, first+193):
        assert record(number)['number'] == number
    save(PILOT/'request.json', {'time': time.time(), 'start': first+1, 'end': first+192,
                              'output': str(PILOT/'raw')})
    save(ROOT/'status.json', {'phase': 'restart_validation', 'time': time.time(), 'head': first,
        'reason': 'Preserving current checkpoint for bounded native source comparison'})
    stop(NAME, PILOT/'pinned-before-shutdown.log')
    save(PILOT/'pinned-before-shutdown.json', inspect()['State'])
    checkpoint(before['head'])
    deadline = time.monotonic()+1800
    while not (PILOT/'raw/manifest.json').exists():
        assert time.monotonic() < deadline, 'Raw fixture delivery missing; inspect before recovery'
        time.sleep(5)
    manifest = json.loads((PILOT/'raw/manifest.json').read_text())
    assert manifest['start'] == first+1 and manifest['end'] == first+192 and len(manifest['files']) == 192
    for entry in manifest['files']:
        assert digest(PILOT/'raw'/entry['name']) == entry['sha256'], entry['name']
    args = [f'--datadir={DATA}' if x == '--datadir=/data' else
            f'--authrpc.jwtsecret={ROOT}/jwt' if x == '--authrpc.jwtsecret=/jwt' else
            x+',testing' if x.startswith('--http.api=') else x for x in original['Config']['Cmd']]
    unit = Path('/etc/systemd/system')/(UNIT+'.service')
    assert not unit.exists()
    text = '\n'.join(['[Unit]', 'Description=PBT bounded source replay comparison', '[Service]',
        'Type=exec', 'PrivateNetwork=yes', 'MemoryMax=48G', 'MemorySwapMax=0', 'AllowedCPUs=0-7',
        'KillSignal=SIGINT', 'SuccessExitStatus=130', 'TimeoutStopSec=1800', 'SendSIGKILL=no',
        'StandardOutput=append:'+str(PILOT/'client.log'), 'StandardError=inherit',
        'Environment=COMPRESS_WORKERS=2 MERGE_WORKERS=2 MDBX_TRACE_TX=true REPLAY_PROFILE=true',
        'ExecStart='+shlex.join([str(BINARY), *args]), ''])
    unit.write_text(text)
    (PILOT/'client.service').write_text(text)
    subprocess.run(['systemd-analyze', 'verify', str(unit)], check=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'start', UNIT], check=True)
    helpers = native_helpers()
    helpers.wait_ready(UNIT)
    for action in ('opened', 'replay', 'native-after'):
        subprocess.run(helpers.namespace(UNIT, 'python3', '-u', __file__, action), check=True)
    helpers.stop_verified(UNIT, PILOT/'native-shutdown.json')
    run('docker', 'start', NAME)
    deadline = time.monotonic()+1800
    while True:
        state = inspect()['State']
        assert state['Running'] and not state['OOMKilled'], state
        ready = subprocess.run(['nsenter', '--target', str(state['Pid']), '--net', 'curl', '-fsS',
            '--max-time', '10', '-H', 'Content-Type: application/json', '--data',
            '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}',
            'http://127.0.0.1:18545'], capture_output=True, text=True)
        if ready.returncode == 0 and json.loads(ready.stdout).get('result'):
            break
        assert time.monotonic() < deadline
        time.sleep(5)
    subprocess.run(['nsenter', '--target', str(state['Pid']), '--net', 'python3', '-u', __file__, 'pinned-reopen'], check=True)
    sequential = json.loads((PILOT/'sequential-timing.json').read_text())
    batch = json.loads((PILOT/'batch-timing.json').read_text())
    after = json.loads((PILOT/'pinned-reopen.json').read_text())
    save(PILOT/'complete.json', {'time': time.time(), 'head': after['head'], 'pilot_blocks': 192,
        'sequential': sequential, 'batch': batch, 'speedup': batch['blocks_per_second']/sequential['blocks_per_second'],
        'normal_durability': True, 'pinned_reopen_verified': True, 'binary_sha256': SHA,
        'image': image, 'continuous_batch_replay_enabled': False,
        'comparison_limit': 'Consecutive ranges: sequential 64 then batch 128; same VM, binary and resource limits, advancing state.'})
    final = json.loads((ROOT/'workload.json').read_text())['v2']['final_records']-3
    save(ROOT/'status.json', {'phase': 'replaying', 'time': time.time(), 'head': first+192,
        'target_head': ANCHOR+3+final, 'qualifying_blocks': first+192-ANCHOR-1020})
    subprocess.run(['systemd-run', '--unit=pbt-1-full-run', '--property=Type=exec', 'nsenter',
        '--target', str(state['Pid']), '--net', 'python3', '-u', '/data/pbt-1/replay.py',
        '--workload-blocks', str(final)], check=True)


if __name__ == '__main__':
    import sys
    try:
        if len(sys.argv) == 2 and sys.argv[1] == 'replay':
            replay()
        elif len(sys.argv) == 2 and sys.argv[1] in ('opened', 'native-after', 'pinned-reopen'):
            audit(sys.argv[1])
        else:
            assert len(sys.argv) == 1
            main()
    except Exception as exc:
        save(ROOT/'status.json', {'phase': 'failed', 'time': time.time(), 'error': str(exc),
                                 'operation': 'original VM native replay comparison'})
        raise
