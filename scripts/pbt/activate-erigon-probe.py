#!/usr/bin/env python3
"""Open a verified checkpoint on the isolated probe and validate a bounded replay."""
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time

from pipeline_rpc import ANCHOR, ROOT, RPC, save
from reopen import stop

PROBE = Path('/data/pbt-1/io-probe')
NAME = 'pbt-1-erigon-execution'
IMAGE = 'erigontech/erigon@sha256:28ee51ce29ecfedc4b9aee10b347ec97d990f8776bb8d51786c6642055791481'
HEAD = 24468025
BLOCKS = 256
TARGET = HEAD + BLOCKS
MDBX_SHA = 'b799a0df4b18dcbd5c662640eca94c6b3913027a43d1375dc8aceb4766c725ce'


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def inspect():
    return json.loads(run('docker', 'inspect', NAME))[0]


def record(number):
    return json.loads(gzip.decompress((ROOT/'blocks'/f'{number:08d}.json.gz').read_bytes()))


def command_for_probe(command):
    assert command[:3] == ['docker', 'run', '-d']
    assert command[command.index('--name')+1] == NAME
    assert IMAGE in command and '--network=none' in command
    assert '--pull=never' in command
    assert '--exec.no-background-maintenance=true' in command
    assert '--exec.no-prune=true' not in command
    assert not any('MDBX_' in item for item in command), 'Normal durability required'
    assert command.count('--memory=48g') == command.count('--memory-swap=48g') == 1
    # This is snapshot preparation hardware, not a 16/32 GiB migration trial.
    return [item.replace('=48g', '=224g') if item in
            ('--memory=48g', '--memory-swap=48g') else item for item in command]


def wait_ready():
    deadline = time.monotonic()+1800
    while True:
        state = inspect()['State']
        assert state['Running'] and not state['OOMKilled'], state
        ready = subprocess.run(['nsenter', '--target', str(state['Pid']), '--net',
            'curl', '-fsS', '--max-time', '10', '-H', 'Content-Type: application/json',
            '--data', '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}',
            'http://127.0.0.1:18545'], capture_output=True, text=True)
        if ready.returncode == 0 and json.loads(ready.stdout).get('result'):
            return
        assert time.monotonic() < deadline, 'RPC startup timed out; inspect before recovery'
        time.sleep(5)


def audit(phase):
    rpc = RPC()
    head = rpc.head()
    expected = HEAD if phase == 'checkpoint' else TARGET
    assert int(head['number'], 16) == expected
    original = json.loads((PROBE/'maintenance-restart-before.json').read_text())
    if phase == 'checkpoint':
        assert head == original['head'], 'Copied checkpoint changed canonical head'
    numbers = {entry['number'] for entry in original['samples']}
    numbers.add(expected)
    if phase != 'checkpoint':
        numbers.update(range(HEAD+1, TARGET+1))
    samples = []
    for number in sorted(numbers):
        want = record(number)
        block = rpc.call('eth_getBlockByNumber', [hex(number), False])
        for key, field in [('hash', 'hash'), ('stateRoot', 'state_root'),
                           ('blockAccessListHash', 'bal_hash')]:
            assert block[key] == want[field], (number, key)
        bodies = rpc.call('engine_getPayloadBodiesByRangeV2', [hex(number), '0x1'], True)
        assert len(bodies) == 1 and bodies[0], number
        for key in ('blockAccessList', 'transactions', 'withdrawals'):
            assert bodies[0][key] == want['new_payload'][0][key], (number, key)
        samples.append({'number': number, 'hash': block['hash'],
                        'state_root': block['stateRoot'], 'bal_hash': block['blockAccessListHash']})
    assert rpc.head()['hash'] == head['hash'], 'Head changed during audit'
    result = {'time': time.time(), 'head': head, 'samples': samples,
              'verified_bodies': len(samples)}
    if phase == 'after':
        before = json.loads((PROBE/'replay-before.json').read_text())
        assert result['head'] == before['head'] and result['samples'] == before['samples']
    save(PROBE/f'replay-{phase}.json', result)


def audit_in_namespace(phase):
    subprocess.run(['nsenter', '--target', str(inspect()['State']['Pid']), '--net',
                    'python3', '-u', __file__, '--audit', phase], check=True)


def main():
    lock = (PROBE/'activation.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (PROBE/'activation-status.json').exists(), 'Inspect prior activation; no automatic retry'
    copied = json.loads((PROBE/'checkpoint-copy-status.json').read_text())
    assert copied['phase'] == 'copied_verified'
    assert copied['file_count'] == copied['expected_file_count'] == 179485
    assert copied['chaindata_sha256'] == MDBX_SHA
    assert not subprocess.check_output(['docker', 'ps', '-aq'], text=True).strip()
    revoked = json.loads((PROBE/'checkpoint-read-access-revoked.json').read_text())
    assert revoked['source_host'] == '164.92.239.96'
    assert revoked['comment'] == 'pbt-1-erigon-checkpoint-probe-20261019'
    assert revoked['matching_entries_after'] == 0 and revoked['private_key_removed']
    assert not (PROBE/'checkpoint-read-key').exists()
    with Path('/data/pbt-1/erigon/chaindata/mdbx.dat').open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == MDBX_SHA
    original = json.loads((PROBE/'maintenance-restart-before.json').read_text())
    assert int(original['head']['number'], 16) == HEAD
    for number in {x['number'] for x in original['samples']} | set(range(HEAD, TARGET+1)):
        assert record(number)['number'] == number
    assert json.loads(Path('/data/pbt-1/pbt-1-source-genesis.json').read_text())['config']['amsterdamTime'] == 1769856769
    assert json.loads((ROOT/'workload.json').read_text())['v2']['final_records'] == 51420
    command = command_for_probe(json.loads((PROBE/'source-command.json').read_text()))
    subprocess.run(['docker', 'image', 'inspect', IMAGE], check=True, stdout=subprocess.DEVNULL)
    jwt = ROOT/'jwt'
    assert not jwt.exists()
    jwt.write_text(secrets.token_hex(32)); jwt.chmod(0o600)
    save(ROOT/'client-command.json', command)
    save(PROBE/'activation-status.json', {'phase': 'starting', 'time': time.time(),
        'checkpoint_head': HEAD, 'pilot_target': TARGET, 'memory_limit_GiB': 224,
        'source_copy': copied, 'canonical_routing_changed': False})
    subprocess.run(command, check=True)
    live = inspect()
    assert live['Config']['Image'] == IMAGE and live['HostConfig']['NetworkMode'] == 'none'
    assert live['HostConfig']['Memory'] == live['HostConfig']['MemorySwap'] == 224*1024**3
    assert not any(item.startswith('MDBX_') for item in live['Config']['Env'])
    wait_ready()
    audit_in_namespace('checkpoint')
    started = time.monotonic()
    save(PROBE/'activation-status.json', {'phase': 'pilot_replaying', 'time': time.time(),
                                         'checkpoint_head': HEAD, 'pilot_target': TARGET})
    subprocess.run(['nsenter', '--target', str(inspect()['State']['Pid']), '--net',
        'python3', '-u', '/data/pbt-1/replay.py', '--workload-blocks', str(TARGET-ANCHOR-3)], check=True)
    elapsed = time.monotonic()-started
    save(PROBE/'pilot-timing.json', {'time': time.time(), 'blocks': BLOCKS,
        'elapsed_seconds': elapsed, 'blocks_per_second': BLOCKS/elapsed,
        'start_head': HEAD, 'end_head': TARGET, 'image': IMAGE,
        'normal_durability': True, 'memory_limit_GiB': 224})
    audit_in_namespace('before')
    save(PROBE/'activation-status.json', {'phase': 'pilot_restart_validation', 'time': time.time()})
    stop(NAME, PROBE/'pilot-clean-shutdown.log')
    shutdown = inspect()['State']
    save(PROBE/'pilot-clean-shutdown.json', shutdown)
    run('docker', 'start', NAME)
    wait_ready()
    audit_in_namespace('after')
    result = json.loads((PROBE/'pilot-timing.json').read_text())
    result.update(phase='pilot_verified', finished_at=time.time(), clean_restart_verified=True,
                  all_pilot_bodies_verified_before_and_after=True,
                  canonical_routing_changed=False, full_replay_pending=True)
    save(PROBE/'activation-status.json', result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--audit':
        assert sys.argv[2] in ('checkpoint', 'before', 'after')
        audit(sys.argv[2])
    else:
        try:
            main()
        except Exception as exc:
            save(PROBE/'activation-failure.json', {'time': time.time(), 'error': str(exc)})
            raise
