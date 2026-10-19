#!/usr/bin/env python3
"""Qualify a 2-GiB execution buffer on 256 canonical blocks on the original VM."""
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import time

from pipeline_rpc import ROOT, RPC, ANCHOR, save

PILOT = Path('/data/pbt-1/native-buffer-pilot')
HISTORY = Path('/data/pbt-1/native-replay-segments')
UNIT = 'pbt-1-native-replay-client'
NAME = 'pbt-1-erigon-execution'
BINARY = Path('/data/pbt-1/erigon-native-continuation')
BUILD = BINARY.with_name(BINARY.name+'-build-report.json')


def driver():
    spec = importlib.util.spec_from_file_location('driver', Path(__file__).with_name('replay-erigon-native.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RUN = PILOT
    return module


def verify_bodies(rpc, read_record, first, last, expected_head):
    assert rpc.head() == expected_head
    count = 0
    for low in range(first, last+1, 16):
        size = min(16, last-low+1)
        bodies = rpc.call('engine_getPayloadBodiesByRangeV2', [hex(low), hex(size)], True)
        assert len(bodies) == size
        for number, body in zip(range(low, low+size), bodies):
            item = read_record(number)
            header = rpc.call('eth_getBlockByNumber', [hex(number), False])
            for key, field in [('hash', 'hash'), ('stateRoot', 'state_root'), ('blockAccessListHash', 'bal_hash')]:
                assert header[key] == item[field], (number, key)
            assert body, number
            for field in ('transactions', 'withdrawals', 'blockAccessList'):
                assert body[field] == item['new_payload'][0][field], (number, field)
            count += 1
    assert rpc.head() == expected_head, 'Head changed during body audit'
    return count


def audit(phase):
    module = driver()
    rpc = RPC()
    before = json.loads((PILOT/'before.json').read_text())['head']
    request = json.loads((PILOT/'request.json').read_text())
    head = rpc.head()
    if phase == 'opened':
        assert head == before
        first = last = int(head['number'], 16)
    else:
        first, last = request['start'], request['end']
        assert int(head['number'], 16) == last
        if phase == 'pinned-reopen':
            assert head == json.loads((PILOT/'native-after.json').read_text())['head']
    count = verify_bodies(rpc, module.record, first, last, head)
    save(PILOT/(phase+'.json'), {'time': time.time(), 'head': head,
                               'verified_bodies': count, 'all_headers_verified': True})


def main():
    module = driver()
    helper = module.helpers()
    lock = (ROOT/'native-replay.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not PILOT.exists(), 'Inspect prior pilot before recovery'
    assert not Path('/data/pbt-1/native-replay').exists(), 'Seal the existing run first'
    assert module.command('systemctl', 'show', UNIT, '-p', 'MainPID', '--value') == '0'
    unit = Path('/etc/systemd/system')/(UNIT+'.service')
    assert not unit.exists()
    prior = sorted(HISTORY.iterdir())[-1]
    sealed = json.loads((prior/'handoff-complete.json').read_text())
    assert sealed['pinned_reopen_verified'] and sealed['normal_durability']
    original = module.inspect()
    assert original['State']['Running'] and not original['State']['OOMKilled']
    assert original['Config']['Image'] == sealed['image']
    assert original['HostConfig']['NetworkMode'] == 'none'
    assert original['HostConfig']['Memory'] == original['HostConfig']['MemorySwap'] == 48*1024**3
    assert '--exec.no-background-maintenance=true' in original['Config']['Cmd']
    assert '--exec.no-prune=true' not in original['Config']['Cmd']
    assert not any('MDBX_NO_FSYNC' in value for value in original['Config']['Env'])
    assert not any(value.startswith('--batchSize=') for value in original['Config']['Cmd'])
    build = json.loads(BUILD.read_text())
    assert module.digest(BINARY) == build['sha256']
    assert build['source']['continuation_commit'] == '72b4a99bbb46a61ce3ab0932111533da8cb9fcda'
    verified = json.loads(Path('/data/pbt-1/native-profile-batch64-proof.json').read_text())
    assert verified['status']['phase'] == 'verified_stopped'
    assert verified['status']['all_bodies_verified_before_and_after']
    assert verified['timing']['binary']['sha256'] == build['sha256']
    first = sealed['end']+1
    end = first+255
    assert end < sealed['final_target']
    raw = json.loads(Path('/data/pbt-1/raw-stream/complete.json').read_text())
    assert raw['start'] <= first and raw['end'] >= end
    PILOT.mkdir()
    save(PILOT/'build.json', build)
    save(PILOT/'before.json', {'head': sealed['head']})
    save(PILOT/'request.json', {'start': first, 'end': end, 'batch_size': 64,
        'record_batch_timings': True, 'execution_buffer': '2G', 'final_target': sealed['final_target']})
    save(ROOT/'status.json', {'phase': 'restart_validation', 'time': time.time(),
        'head': first-1, 'reason': 'Bounded 256-block execution-buffer pilot'})
    subprocess.run(['nsenter', '--target', str(original['State']['Pid']), '--net',
        'python3', __file__, '--audit', 'opened'], check=True)
    module.stop(NAME, PILOT/'pinned-shutdown.log')
    client_args = ['--datadir=/data/pbt-1/erigon' if x == '--datadir=/data' else
        f'--authrpc.jwtsecret={ROOT}/jwt' if x == '--authrpc.jwtsecret=/jwt' else
        x+',testing' if x.startswith('--http.api=') else x for x in original['Config']['Cmd']]
    client_args += ['--batchSize=2G', '--pprof', '--pprof.addr=127.0.0.1', '--pprof.port=6060']
    text = '\n'.join(['[Unit]', 'Description=PBT bounded execution-buffer pilot', '[Service]',
        'Type=exec', 'PrivateNetwork=yes', 'MemoryMax=48G', 'MemorySwapMax=0', 'AllowedCPUs=0-7',
        'KillSignal=SIGINT', 'SuccessExitStatus=130', 'TimeoutStopSec=1800', 'SendSIGKILL=no',
        'StandardOutput=append:'+str(PILOT/'client.log'), 'StandardError=inherit',
        'Environment=COMPRESS_WORKERS=2 MERGE_WORKERS=2 MDBX_TRACE_TX=true REPLAY_PROFILE=true',
        'ExecStart='+shlex.join([str(BINARY), *client_args]), ''])
    unit.write_text(text)
    (PILOT/'client.service').write_text(text)
    subprocess.run(['systemd-analyze', 'verify', str(unit)], check=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'start', UNIT], check=True)
    helper.wait_ready(UNIT)
    subprocess.run(helper.namespace(UNIT, 'python3', __file__, '--audit', 'opened'), check=True)
    finish(module, helper, build, sealed, first, end, unit)


def resume_staged():
    module = driver()
    helper = module.helpers()
    lock = (ROOT/'native-replay.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for name in ('progress.json', 'batch-timings.json', 'replay-complete.json', 'complete.json'):
        assert not (PILOT/name).exists(), 'This recovery is only for rejection before the first batch'
    request = json.loads((PILOT/'request.json').read_text())
    prefix = json.loads((PILOT/'pre-staged-prefix.json').read_text())
    state = helper.state(UNIT)
    assert state['ActiveState'] == 'active' and int(state['MainPID']) == prefix['client_pid']
    build = json.loads((PILOT/'build.json').read_text())
    assert module.digest(Path('/proc')/state['MainPID']/'exe') == build['sha256']
    unit = Path('/etc/systemd/system')/(UNIT+'.service')
    assert unit.read_text() == (PILOT/'client.service').read_text()
    assert '--batchSize=2G' in unit.read_text()
    sealed = json.loads((sorted(HISTORY.iterdir())[-1]/'handoff-complete.json').read_text())
    first, end = request['start'], request['end']
    assert first == sealed['end']+1 and end == first+255 and request['batch_size'] == 64
    assert prefix['start'] == first and prefix['end'] == first+63
    assert prefix['verified_stored_headers_and_bodies'] == 64 and prefix['forkchoice_head_unchanged']
    subprocess.run(helper.namespace(UNIT, 'python3', __file__, '--audit', 'opened'), check=True)
    save(PILOT/'stored-prefix-recovery.json', {'time': time.time(), 'client_pid': prefix['client_pid'],
        'head': first-1, 'blocks_already_staged': 64, 'all_engine_validation_retained': True})
    request['pre_staged_first_batch'] = True
    request['first_batch_size'] = 128
    save(PILOT/'request.json', request)
    save(ROOT/'status.json', {'phase': 'restart_validation', 'time': time.time(), 'head': first-1,
        'reason': 'Validate verified stored blocks through normal forkchoice as pilot warmup'})
    finish(module, helper, build, sealed, first, end, unit)


def finish(module, helper, build, sealed, first, end, unit):
    subprocess.run(helper.namespace(UNIT, 'python3', '-u', __file__, '--replay'), check=True)
    save(ROOT/'status.json', {'phase': 'restart_validation', 'time': time.time(), 'head': end,
        'reason': 'Buffer pilot complete; verifying all 256 bodies before and after pinned reopen'})
    subprocess.run(helper.namespace(UNIT, 'python3', __file__, '--audit', 'native-after'), check=True)
    helper.stop_verified(UNIT, PILOT/'native-shutdown.json')
    module.command('docker', 'start', NAME)
    deadline = time.monotonic()+1800
    while True:
        state = module.inspect()['State']
        assert state['Running'] and not state['OOMKilled'], state
        ready = subprocess.run(['nsenter', '--target', str(state['Pid']), '--net', 'curl', '-fsS', '--max-time', '10',
            '-H', 'Content-Type: application/json', '--data', '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}',
            'http://127.0.0.1:18545'], capture_output=True, text=True)
        if ready.returncode == 0 and json.loads(ready.stdout).get('result'):
            break
        assert time.monotonic() < deadline
        time.sleep(5)
    subprocess.run(['nsenter', '--target', str(state['Pid']), '--net', 'python3', __file__, '--audit', 'pinned-reopen'], check=True)
    after = json.loads((PILOT/'pinned-reopen.json').read_text())
    assert after['verified_bodies'] == 256
    replay = json.loads((PILOT/'replay-complete.json').read_text())
    assert replay['validated_blocks'] == 256 and replay['final_persistence_verified']
    timings = json.loads((PILOT/'batch-timings.json').read_text())
    assert [x['validated_blocks'] for x in timings] in ([64, 128, 192, 256], [128, 192, 256])
    warmup_blocks = timings[0]['validated_blocks']
    measured_blocks = 256-warmup_blocks
    warmup = warmup_blocks/timings[0]['blocks_per_second']
    measured = replay['elapsed_seconds']-warmup
    assert measured > 0
    proof = {'status': {'phase': 'verified_stopped', 'time': time.time(), 'blocks': 256,
            'head': end, 'all_bodies_verified_before_and_after': True, 'pinned_reopen_verified': True,
            'pinned_client_running': True},
        'timing': {'binary': build, 'normal_durability': True, 'execution_buffer': '2G',
            'memory_GiB': 48, 'cpus': '0-7', 'replay': {**replay, 'batch_size': 64,
                'warmup_blocks': warmup_blocks, 'measured_blocks': measured_blocks, 'measured_seconds': measured,
                'measured_blocks_per_second': measured_blocks/measured}}}
    save(PILOT/'proof.json', proof)
    segment = {'phase': 'segment_sealed', 'time': time.time(), 'start': first, 'end': end,
        'head': after['head'], 'validated_blocks': 256, 'previously_validated_blocks': 256,
        'tail_payloads_verified': 0, 'all_headers_verified': True, 'recent_bodies_verified': 256,
        'normal_durability': True, 'pinned_reopen_verified': True, 'image': sealed['image'],
        'binary_sha256': build['sha256'], 'batch_size': 64, 'execution_buffer': '2G',
        'final_target': sealed['final_target'], 'pilot_evidence': str(PILOT)}
    destination = HISTORY/f'{len(list(HISTORY.iterdir()))+1:04d}'
    assert not destination.exists()
    destination.mkdir()
    save(destination/'handoff-complete.json', segment)
    save(destination/'build.json', build)
    save(destination/'buffer-pilot-proof.json', proof)
    save(PILOT/'complete.json', {**segment, 'history_path': str(destination)})
    assert unit.read_text() == (PILOT/'client.service').read_text()
    unit.unlink()
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    save(ROOT/'status.json', {'phase': 'native_trial_complete', 'time': time.time(), 'head': end,
        'target_head': sealed['final_target'], 'qualifying_blocks': end-ANCHOR-1020,
        'measured_blocks_per_second': measured_blocks/measured, 'pinned_reopen_verified': True})
    print(json.dumps({'pilot_complete': True, 'head': end, 'measured_blocks_per_second': measured_blocks/measured}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', choices=['opened', 'native-after', 'pinned-reopen'])
    parser.add_argument('--replay', action='store_true')
    parser.add_argument('--resume-staged', action='store_true')
    args = parser.parse_args()
    try:
        if args.audit:
            audit(args.audit)
        elif args.replay:
            driver().replay()
        elif args.resume_staged:
            resume_staged()
        else:
            main()
    except Exception as exc:
        save(ROOT/'status.json', {'phase': 'failed', 'time': time.time(),
            'operation': 'bounded native buffer pilot', 'error': str(exc)})
        raise
