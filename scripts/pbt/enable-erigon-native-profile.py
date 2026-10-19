#!/usr/bin/env python3
"""Enable existing MDBX timing logs after a clean, audited source restart."""
import fcntl
import json
from pathlib import Path
import subprocess
import time
from pipeline_rpc import ANCHOR, ROOT, save
from reopen import stop

NAME = 'pbt-1-erigon-execution'
BACKUP = NAME+'-before-native-profile'


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def inspect():
    return json.loads(run('docker', 'inspect', NAME))[0]


def audit(phase):
    destination = ROOT/f'native-profile-{phase}.json'
    subprocess.run(['nsenter', '--target', str(inspect()['State']['Pid']), '--net',
        'python3', '-u', '/data/pbt-1/suppress-erigon-maintenance.py', '--audit', str(destination)], check=True)
    return json.loads(destination.read_text())


def main():
    lock = (ROOT/'native-profile.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (ROOT/'native-profile-complete.json').exists()
    initial = inspect()
    assert initial['State']['Running'] and not initial['State']['OOMKilled']
    assert initial['HostConfig']['NetworkMode'] == 'none'
    assert subprocess.run(['docker', 'inspect', BACKUP], capture_output=True).returncode != 0
    command = json.loads((ROOT/'client-command.json').read_text())
    image = initial['Config']['Image']
    assert command[command.index(image)+1:] == initial['Config']['Cmd']
    assert not any(item.startswith('MDBX_') for item in command+initial['Config']['Env'])
    assert '--exec.no-background-maintenance=true' in command
    assert '--exec.no-prune=true' not in command
    subprocess.run(['systemctl', 'stop', 'pbt-1-full-run.service'], check=True)
    save(ROOT/'status.json', {'phase': 'restart_validation', 'time': time.time(),
        'reason': 'Enable native MDBX diagnostics; unchanged durability and memory'})
    before = audit('before')
    save(ROOT/'client-command-before-native-profile.json', command)
    stop(NAME, ROOT/'native-profile-shutdown.log')
    save(ROOT/'native-profile-shutdown.json', inspect()['State'])
    run('docker', 'rename', NAME, BACKUP)
    position = command.index(image)
    updated = command[:position]+['-e', 'MDBX_TRACE_TX=true']+command[position:]
    subprocess.run(updated, check=True)
    save(ROOT/'client-command.json', updated)
    current = inspect()
    assert current['Config']['Image'] == image and current['Config']['Cmd'] == initial['Config']['Cmd']
    for field in ('Binds', 'Memory', 'MemorySwap', 'NetworkMode'):
        assert current['HostConfig'][field] == initial['HostConfig'][field], field
    assert set(current['Config']['Env']) == set(initial['Config']['Env']) | {'MDBX_TRACE_TX=true'}
    deadline = time.monotonic()+1800
    while True:
        state = inspect()['State']
        assert state['Running'] and not state['OOMKilled'], state
        ready = subprocess.run(['nsenter', '--target', str(state['Pid']), '--net',
            'curl', '-fsS', '--max-time', '10', '-H', 'Content-Type: application/json',
            '--data', '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}',
            'http://127.0.0.1:18545'], capture_output=True, text=True)
        if ready.returncode == 0 and json.loads(ready.stdout).get('result'):
            break
        assert time.monotonic() < deadline, 'Inspect startup before recovery'
        time.sleep(5)
    after = audit('after')
    assert after['head'] == before['head'] and after['samples'] == before['samples']
    result = {'time': time.time(), 'head': before['head'], 'samples': before['samples'],
        'image': image, 'normal_durability': True, 'memory_bytes': current['HostConfig']['Memory'],
        'enabled_environment': 'MDBX_TRACE_TX=true', 'pid': inspect()['State']['Pid'],
        'same_head_and_sampled_bals_verified': True}
    save(ROOT/'native-profile-complete.json', result)
    final = json.loads((ROOT/'workload.json').read_text())['v2']['final_records']-3
    head = int(before['head']['number'], 16)
    save(ROOT/'status.json', {'phase': 'replaying', 'time': time.time(), 'head': head,
        'target_head': ANCHOR+3+final, 'qualifying_blocks': head-ANCHOR-1020})
    subprocess.run(['systemd-run', '--unit=pbt-1-full-run', '--property=Type=exec',
        'nsenter', '--target', str(result['pid']), '--net', 'python3', '-u',
        '/data/pbt-1/replay.py', '--workload-blocks', str(final)], check=True)
    print(json.dumps({'head': head, 'pid': result['pid'], 'normal_durability': True}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        save(ROOT/'native-profile-failure.json', {'time': time.time(), 'error': str(exc)})
        raise
