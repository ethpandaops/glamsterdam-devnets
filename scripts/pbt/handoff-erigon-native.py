#!/usr/bin/env python3
"""Seal a running native replay segment, reopen the pinned image, then change build."""
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import time

from pipeline_rpc import ROOT, RPC, save

RUN = Path('/data/pbt-1/native-replay')
HISTORY = Path('/data/pbt-1/native-replay-segments')
UNIT = 'pbt-1-native-replay-client'
NAME = 'pbt-1-erigon-execution'


def driver():
    spec = importlib.util.spec_from_file_location('native_driver', Path(__file__).with_name('replay-erigon-native.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def persisted_head(log):
    updated = persisted = None
    for line in log.splitlines():
        if 'head updated ' in line:
            match = re.search(r'\bnumber=(\d+)\b', line)
            if match:
                updated = int(match[1])
        if 'Timings: Post-Forkchoice' in line:
            persisted = updated
    return persisted


def wait_next_head(path, prior_head, timeout=600):
    """Catch a new head notification before the driver stages its next batch.

    This only selects when to stop the driver. The persistence and full segment
    audits still run afterward and remain mandatory.
    """
    deadline = time.monotonic()+timeout
    with path.open() as stream:
        stream.seek(0, 2)
        pending = ''
        while time.monotonic() < deadline:
            pending += stream.read()
            lines = pending.split('\n')
            pending = lines.pop()
            for line in lines:
                if 'head updated ' in line:
                    match = re.search(r'\bnumber=(\d+)\b', line)
                    if match and int(match[1]) > prior_head:
                        return int(match[1])
            time.sleep(.02)
    raise AssertionError('No new head notification; driver was not stopped')


def verify_segment(rpc, read_record, request, progress):
    head = rpc.head()
    end = int(head['number'], 16)
    assert request['start'] <= progress['head'] <= end < request['end']
    assert progress['validated_blocks'] == progress['head']-request['start']+1
    assert end-progress['head'] <= request['batch_size'], 'More than one unreported batch'
    expected_head = read_record(end)
    for key, field in [('hash', 'hash'), ('stateRoot', 'state_root'), ('blockAccessListHash', 'bal_hash')]:
        assert head[key] == expected_head[field], key
    for number in range(request['start'], end+1):
        item = read_record(number)
        header = rpc.call('eth_getBlockByNumber', [hex(number), False])
        for key, field in [('hash', 'hash'), ('stateRoot', 'state_root'), ('blockAccessListHash', 'bal_hash')]:
            assert header[key] == item[field], (number, key)
        if number > progress['head']:
            result = rpc.call('engine_newPayloadV5', item['new_payload'], True)
            assert result['status'] == 'VALID' and result['latestValidHash'] == item['hash'], result
    for number in range(max(request['start'], end-15), end+1):
        body = rpc.call('engine_getPayloadBodiesByRangeV2', [hex(number), '0x1'], True)
        expected = read_record(number)['new_payload'][0]
        assert len(body) == 1 and body[0]
        for field in ('transactions', 'withdrawals', 'blockAccessList'):
            assert body[0][field] == expected[field], (number, field)
    assert rpc.head() == head, 'Head changed during handoff audit'
    return {'time': time.time(), 'head': head, 'start': request['start'], 'end': end,
            'validated_blocks': end-request['start']+1,
            'previously_validated_blocks': progress['validated_blocks'],
            'tail_payloads_verified': end-progress['head'],
            'all_headers_verified': True, 'recent_bodies_verified': min(16, end-request['start']+1)}


def audit_native():
    module = driver()
    rpc = RPC()
    deadline = time.monotonic()+600
    stable = None
    while True:
        head = rpc.head()
        persisted = persisted_head((RUN/'client.log').read_text())
        if persisted == int(head['number'], 16):
            if stable == head:
                break
            stable = head
        else:
            stable = None
        assert time.monotonic() < deadline, 'Inspect in-flight forkchoice before handoff'
        time.sleep(3)
    proof = verify_segment(rpc, module.record,
        json.loads((RUN/'request.json').read_text()), json.loads((RUN/'progress.json').read_text()))
    save(RUN/'handoff-native.json', proof)


def audit_pinned():
    module = driver()
    rpc = RPC()
    proof = json.loads((RUN/'handoff-native.json').read_text())
    assert rpc.head() == proof['head']
    number = proof['end']
    body = rpc.call('engine_getPayloadBodiesByRangeV2', [hex(number), '0x1'], True)
    expected = module.record(number)['new_payload'][0]
    assert len(body) == 1 and body[0]
    for field in ('transactions', 'withdrawals', 'blockAccessList'):
        assert body[0][field] == expected[field], field
    assert rpc.head() == proof['head']
    save(RUN/'handoff-pinned.json', {'time': time.time(), 'head': proof['head'], 'body_verified': True})


def main(args):
    module = driver()
    helper = module.helpers()
    handoff_lock = (ROOT/'native-handoff.lock').open('w')
    fcntl.flock(handoff_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (RUN/'handoff-intent.json').exists(), 'Inspect prior handoff before recovery'
    assert not (RUN/'complete.json').exists()
    original = module.inspect()
    assert not original['State']['Running'] and not original['State']['OOMKilled']
    assert original['State']['ExitCode'] in (0, 130)
    assert helper.state(UNIT)['ActiveState'] == 'active'
    build = json.loads(args.build_report.read_text())
    probe = json.loads(args.probe_proof.read_text())
    assert module.digest(args.binary) == build['sha256']
    assert probe['status']['phase'] == 'verified_stopped'
    assert probe['status']['all_bodies_verified_before_and_after']
    assert probe['timing']['binary']['sha256'] == build['sha256']
    assert probe['timing']['normal_durability'] and probe['timing']['replay']['final_persistence_verified']
    assert probe['timing']['replay']['batch_size'] == args.batch_size
    assert probe['timing'].get('execution_buffer', '512M') == '512M'
    assert build['source']['base_commit'] == '8c1e3893d77d230720d172f1492d95b5777a862c'
    if args.batch_size > 16:
        assert build['source']['continuation_commit'] == '72b4a99bbb46a61ce3ab0932111533da8cb9fcda'
    before = json.loads((RUN/'progress.json').read_text())
    assert before['phase'] == 'native_replaying' and time.time()-before['time'] < 120
    assert before['head']+512 < before['target_head'], 'Too close to completion for this handoff'
    save(RUN/'handoff-intent.json', {'time': time.time(), 'next_build': build,
        'next_batch_size': args.batch_size, 'client_state': helper.state(UNIT), 'progress': before})
    if args.wait_next_head:
        selected = wait_next_head(RUN/'client.log', before['head'])
        save(RUN/'handoff-selected-head.json', {'time': time.time(), 'head': selected,
                                               'persistence_audit_pending': True})
    subprocess.run(['systemctl', 'stop', 'pbt-1-native-replay'], check=True, timeout=120)
    assert module.command('systemctl', 'show', 'pbt-1-native-replay', '-p', 'MainPID', '--value') == '0'
    replay_lock = (ROOT/'native-replay.lock').open('w')
    fcntl.flock(replay_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    save(ROOT/'status.json', {'phase': 'restart_validation', 'time': time.time(),
        'reason': 'Seal native segment and verify pinned reopen before batch-size comparison'})
    subprocess.run(helper.namespace(UNIT, 'python3', __file__, '--audit-native'), check=True)
    helper.stop_verified(UNIT, RUN/'handoff-native-shutdown.json')
    module.command('docker', 'start', NAME)
    deadline = time.monotonic()+1800
    while True:
        state = module.inspect()['State']
        assert state['Running'] and not state['OOMKilled'], state
        result = subprocess.run(['nsenter', '--target', str(state['Pid']), '--net',
            'curl', '-fsS', '--max-time', '10', '-H', 'Content-Type: application/json', '--data',
            '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}',
            'http://127.0.0.1:18545'], capture_output=True, text=True)
        if result.returncode == 0 and json.loads(result.stdout).get('result'):
            break
        assert time.monotonic() < deadline
        time.sleep(5)
    subprocess.run(['nsenter', '--target', str(state['Pid']), '--net', 'python3', __file__, '--audit-pinned'], check=True)
    proof = json.loads((RUN/'handoff-native.json').read_text())
    old_build = json.loads((RUN/'build.json').read_text())
    request = json.loads((RUN/'request.json').read_text())
    current_probe = json.loads((RUN/'probe-proof.json').read_text())
    execution_buffer = current_probe['timing'].get('execution_buffer', '512M')
    save(RUN/'handoff-complete.json', {**proof, 'phase': 'segment_sealed',
        'normal_durability': True, 'pinned_reopen_verified': True,
        'image': original['Config']['Image'], 'binary_sha256': old_build['sha256'],
        'batch_size': request['batch_size'], 'execution_buffer': execution_buffer,
        'final_target': request['end']})
    HISTORY.mkdir(exist_ok=True)
    destination = HISTORY/f'{len(list(HISTORY.iterdir()))+1:04d}'
    assert not destination.exists()
    RUN.rename(destination)
    unit = Path('/etc/systemd/system')/(UNIT+'.service')
    assert unit.read_text() == (destination/'client.service').read_text()
    unit.unlink()
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    replay_lock.close()
    if args.seal_only:
        print(json.dumps({'sealed_segment': str(destination), 'head': proof['end'],
                          'pinned_client_running': True}), flush=True)
        return
    subprocess.run(['systemd-run', '--unit=pbt-1-native-replay', '--property=Type=exec',
        'python3', '-u', '/data/pbt-1/replay-erigon-native.py', '--binary', str(args.binary),
        '--build-report', str(args.build_report), '--probe-proof', str(args.probe_proof),
        '--batch-size', str(args.batch_size), '--execution-buffer', '512M'], check=True)
    print(json.dumps({'sealed_segment': str(destination), 'head': proof['end'],
                      'next_batch_size': args.batch_size}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-native', action='store_true')
    parser.add_argument('--audit-pinned', action='store_true')
    parser.add_argument('--seal-only', action='store_true')
    parser.add_argument('--wait-next-head', action='store_true')
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--build-report', type=Path)
    parser.add_argument('--probe-proof', type=Path)
    parser.add_argument('--batch-size', type=int, choices=[16, 32, 64, 128])
    args = parser.parse_args()
    if args.audit_native:
        audit_native()
    elif args.audit_pinned:
        audit_pinned()
    else:
        assert args.binary and args.build_report and args.probe_proof and args.batch_size
        try:
            main(args)
        except Exception as exc:
            save(ROOT/'status.json', {'phase': 'failed', 'time': time.time(),
                'operation': 'native replay handoff', 'error': str(exc)})
            raise
