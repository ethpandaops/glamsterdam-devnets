#!/usr/bin/env python3
"""Replay verified raw chunks natively, then return to the pinned image for publication."""
import argparse
import fcntl
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import time

from pipeline_rpc import ROOT, RPC, ANCHOR, save
from reopen import stop

RUN = Path('/data/pbt-1/native-replay')
RAW = Path('/data/pbt-1/raw-stream')
NAME = 'pbt-1-erigon-execution'
UNIT = 'pbt-1-native-replay-client'


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def inspect():
    return json.loads(command('docker', 'inspect', NAME))[0]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def helpers():
    spec = importlib.util.spec_from_file_location('native', '/data/pbt-1/probe-erigon-native.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record(number):
    return json.loads(gzip.decompress((ROOT/'blocks'/f'{number:08d}.json.gz').read_bytes()))


def audit(phase):
    rpc = RPC()
    head = rpc.head()
    number = int(head['number'], 16)
    expected = record(number)
    for key, field in [('hash', 'hash'), ('stateRoot', 'state_root'), ('blockAccessListHash', 'bal_hash')]:
        assert head[key] == expected[field], (number, key)
    body = rpc.call('engine_getPayloadBodiesByRangeV2', [hex(number), '0x1'], True)
    assert len(body) == 1 and body[0]
    for field in ('transactions', 'withdrawals', 'blockAccessList'):
        assert body[0][field] == expected['new_payload'][0][field], field
    if phase in ('opened', 'pinned-reopen'):
        prior = json.loads((RUN/('before.json' if phase == 'opened' else 'native-after.json')).read_text())
        assert head == prior['head']
    assert rpc.head() == head
    save(RUN/(phase+'.json'), {'time': time.time(), 'head': head, 'head_body_verified': True})


def persist_fence(head_before):
    deadline = time.monotonic()+600
    while True:
        seen = False
        for line in (RUN/'client.log').read_text().splitlines():
            if '[replay-profile] forkchoice' in line and f'headBefore={head_before} ' in line:
                seen = True
            if seen and 'Timings: Post-Forkchoice' in line:
                return
        assert time.monotonic() < deadline, 'Inspect final persistence before recovery'
        time.sleep(.1)


def replay():
    request = json.loads((RUN/'request.json').read_text())
    raw_request = json.loads((RAW/'request.json').read_text())
    rpc = RPC()
    head = rpc.head()
    first = number = int(head['number'], 16)
    assert head == json.loads((RUN/'before.json').read_text())['head']
    assert request['start'] == first+1 and raw_request['start'] <= first+1
    assert raw_request['end'] == request['end']
    batch_size = request['batch_size']
    manifests = {}
    started = time.monotonic()
    while number < request['end']:
        assert shutil.disk_usage(ROOT).free > 150*10**9, 'Less than 150 GB free'
        last = min(number+batch_size, request['end'])
        chunks = {raw_request['start']+((n-raw_request['start'])//256)*256 for n in range(number+1, last+1)}
        if any(not (RAW/f'{low:08d}/manifest.json').exists() for low in chunks):
            save(ROOT/'status.json', {'phase': 'native_waiting_for_raw', 'time': time.time(),
                'head': number, 'target_head': request['end'], 'qualifying_blocks': number-ANCHOR-1020})
            time.sleep(5)
            continue
        for low in chunks-manifests.keys():
            manifest = json.loads((RAW/f'{low:08d}/manifest.json').read_text())
            assert manifest['start'] == low and manifest['end'] == min(low+255, request['end'])
            assert [x['name'] for x in manifest['files']] == [f'{n:08d}.json.gz' for n in range(low, manifest['end']+1)]
            manifests[low] = {x['name']: x['sha256'] for x in manifest['files']}
        records, raw = [], []
        parent = head['hash']
        for n in range(number+1, last+1):
            item = record(n)
            assert item['number'] == n and item['new_payload'][0]['parentHash'] == parent
            low = raw_request['start']+((n-raw_request['start'])//256)*256
            name = f'{n:08d}.json.gz'
            data = (RAW/f'{low:08d}'/name).read_bytes()
            assert hashlib.sha256(data).hexdigest() == manifests[low][name]
            encoded = json.loads(gzip.decompress(data))
            assert encoded['number'] == n and encoded['hash'] == item['hash']
            records.append(item)
            raw.append(encoded['raw'])
            parent = item['hash']
        for index in range(0, len(records), 16):
            chunk = records[index:index+16]
            params = [raw[index:index+16], [r['new_payload'][0]['blockAccessList'] for r in chunk]]
            if batch_size > 16:
                params.insert(0, chunk[0]['new_payload'][0]['parentHash'])
            result = rpc.call('testing_insertRawBlocksV2' if batch_size > 16 else 'testing_insertRawBlocksV1', params)
            assert result == [r['hash'] for r in chunk]
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
        head = rpc.head()
        assert head['hash'] == records[-1]['hash']
        prior_number, number = number, last
        status = {'phase': 'native_replaying', 'time': time.time(), 'head': number,
            'target_head': request['end'], 'qualifying_blocks': number-ANCHOR-1020,
            'blocks_per_second': (number-first)/(time.monotonic()-started),
            'hash': head['hash'], 'state_root': head['stateRoot'], 'bal_hash': head['blockAccessListHash'],
            'batch_size': batch_size, 'validated_blocks': number-first}
        save(ROOT/'status.json', status)
        save(RUN/'progress.json', status)
        print(json.dumps(status), flush=True)
    persist_fence(prior_number)
    save(RUN/'replay-complete.json', {**status, 'final_persistence_verified': True,
        'elapsed_seconds': time.monotonic()-started,
        'blocks_per_second': (number-first)/(time.monotonic()-started)})


def main(args):
    lock = (ROOT/'native-replay.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not RUN.exists(), 'Inspect prior native replay before recovery'
    pilot = json.loads(Path('/data/pbt-1/native-source-pilot/complete.json').read_text())
    assert pilot['pinned_reopen_verified'] and pilot['normal_durability'] and pilot['speedup'] > 1.3
    build = json.loads(args.build_report.read_text())
    assert digest(args.binary) == build['sha256']
    probe = json.loads(args.probe_proof.read_text())
    assert probe['status']['phase'] == 'verified_stopped' and probe['status']['all_bodies_verified_before_and_after']
    assert probe['timing']['binary']['sha256'] == build['sha256'] and probe['timing']['normal_durability']
    assert probe['timing']['replay']['batch_size'] == args.batch_size
    assert probe['timing'].get('execution_buffer', '512M') == args.execution_buffer
    assert probe['timing']['replay']['final_persistence_verified']
    if args.batch_size > 16:
        assert build['source']['continuation_commit'] == '72b4a99bbb46a61ce3ab0932111533da8cb9fcda'
    original = inspect()
    assert original['State']['Running'] and not original['State']['OOMKilled']
    assert original['Config']['Image'] == pilot['image']
    assert original['HostConfig']['NetworkMode'] == 'none'
    assert original['HostConfig']['Memory'] == original['HostConfig']['MemorySwap'] == 48*1024**3
    assert '--exec.no-background-maintenance=true' in original['Config']['Cmd']
    assert '--exec.no-prune=true' not in original['Config']['Cmd']
    assert not any('MDBX_NO_FSYNC' in x for x in original['Config']['Env'])
    RUN.mkdir()
    save(RUN/'build.json', build)
    save(RUN/'probe-proof.json', probe)
    save(RUN/'original-command.json', original['Config'])
    subprocess.run(['systemctl', 'stop', 'pbt-1-full-run'], check=True)
    save(ROOT/'status.json', {'phase': 'restart_validation', 'time': time.time(), 'reason': 'Starting verified native batch replay'})
    time.sleep(5)
    subprocess.run(['nsenter', '--target', str(original['State']['Pid']), '--net', 'python3', __file__, '--audit', 'before'], check=True)
    before = json.loads((RUN/'before.json').read_text())['head']
    first = int(before['number'], 16)+1
    end = ANCHOR+json.loads((ROOT/'workload.json').read_text())['v2']['final_records']
    assert int(pilot['head']['number'], 16) < first <= end
    raw_request = json.loads((RAW/'request.json').read_text())
    assert raw_request['start'] <= first and raw_request['end'] == end
    save(RUN/'request.json', {'start': first, 'end': end, 'batch_size': args.batch_size})
    stop(NAME, RUN/'pinned-shutdown.log')
    save(RUN/'pinned-shutdown.json', inspect()['State'])
    client_args = ['--datadir=/data/pbt-1/erigon' if x == '--datadir=/data' else
        f'--authrpc.jwtsecret={ROOT}/jwt' if x == '--authrpc.jwtsecret=/jwt' else
        x+',testing' if x.startswith('--http.api=') else x for x in original['Config']['Cmd']]
    client_args += ['--pprof', '--pprof.addr=127.0.0.1', '--pprof.port=6060']
    if args.execution_buffer != '512M':
        client_args.append('--batchSize='+args.execution_buffer)
    unit = Path('/etc/systemd/system')/(UNIT+'.service')
    assert not unit.exists()
    text = '\n'.join(['[Unit]', 'Description=PBT verified native replay', '[Service]',
        'Type=exec', 'PrivateNetwork=yes', 'MemoryMax=48G', 'MemorySwapMax=0', 'AllowedCPUs=0-7',
        'KillSignal=SIGINT', 'SuccessExitStatus=130', 'TimeoutStopSec=1800', 'SendSIGKILL=no',
        'StandardOutput=append:'+str(RUN/'client.log'), 'StandardError=inherit',
        'Environment=COMPRESS_WORKERS=2 MERGE_WORKERS=2 MDBX_TRACE_TX=true REPLAY_PROFILE=true',
        'ExecStart='+shlex.join([str(args.binary), *client_args]), ''])
    unit.write_text(text)
    (RUN/'client.service').write_text(text)
    subprocess.run(['systemd-analyze', 'verify', str(unit)], check=True)
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'start', UNIT], check=True)
    helper = helpers()
    helper.wait_ready(UNIT)
    subprocess.run(helper.namespace(UNIT, 'python3', __file__, '--audit', 'opened'), check=True)
    subprocess.run(helper.namespace(UNIT, 'python3', '-u', __file__, '--replay'), check=True)
    save(ROOT/'status.json', {'phase': 'restart_validation', 'time': time.time(), 'head': end,
        'reason': 'Native replay complete; validating pinned-image reopen'})
    subprocess.run(helper.namespace(UNIT, 'python3', __file__, '--audit', 'native-after'), check=True)
    helper.stop_verified(UNIT, RUN/'native-shutdown.json')
    command('docker', 'start', NAME)
    deadline = time.monotonic()+1800
    while True:
        state = inspect()['State']
        assert state['Running'] and not state['OOMKilled'], state
        ready = subprocess.run(['nsenter', '--target', str(state['Pid']), '--net', 'curl', '-fsS', '--max-time', '10',
            '-H', 'Content-Type: application/json', '--data', '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}',
            'http://127.0.0.1:18545'], capture_output=True, text=True)
        if ready.returncode == 0 and json.loads(ready.stdout).get('result'):
            break
        assert time.monotonic() < deadline
        time.sleep(5)
    subprocess.run(['nsenter', '--target', str(state['Pid']), '--net', 'python3', __file__, '--audit', 'pinned-reopen'], check=True)
    after = json.loads((RUN/'pinned-reopen.json').read_text())['head']
    assert int(after['number'], 16) == end
    save(RUN/'complete.json', {'time': time.time(), 'start': first, 'end': end, 'head': after,
        'validated_blocks': end-first+1, 'batch_size': args.batch_size, 'binary_sha256': build['sha256'],
        'execution_buffer': args.execution_buffer,
        'normal_durability': True, 'pinned_reopen_verified': True, 'image': original['Config']['Image']})
    save(ROOT/'status.json', {'phase': 'replay_complete', 'time': time.time(), 'head': end, 'target_head': end,
        'workload_blocks': end-ANCHOR-3, 'qualifying_blocks': end-ANCHOR-1020,
        'hash': after['hash'], 'state_root': after['stateRoot'], 'bal_hash': after['blockAccessListHash']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--build-report', type=Path)
    parser.add_argument('--probe-proof', type=Path)
    parser.add_argument('--batch-size', type=int, choices=[8, 16, 64, 128])
    parser.add_argument('--execution-buffer', choices=['512M', '2G'], default='512M')
    parser.add_argument('--audit', choices=['before', 'opened', 'native-after', 'pinned-reopen'])
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    try:
        if args.audit:
            audit(args.audit)
        elif args.replay:
            replay()
        else:
            assert args.binary and args.build_report and args.probe_proof and args.batch_size
            main(args)
    except Exception as exc:
        save(ROOT/'status.json', {'phase': 'failed', 'time': time.time(), 'error': str(exc), 'operation': 'native replay'})
        raise
