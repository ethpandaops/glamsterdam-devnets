#!/usr/bin/env python3
"""Reopen a stopped source DB with a pinned migration image, isolated from peers.

Run on an original source worker after its recovery archive has been verified.
This checks startup, H/N, state reads and three retained BAL bodies. It does not
qualify migration or replace a full BAL audit or deployment-argument validation.
"""
import argparse
import base64
import gzip
import hashlib
import hmac
import json
from pathlib import Path
import subprocess
import time

ROOT = Path('/data/pbt-1')
HEAD = 24503958
ANCHOR = 24453558
HEAD_HASH = '0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216'
STATE_ROOT = '0x8cab6f81e370f341e67e66d2333cdf3e6074861f861aa3e490b9411460ad7f22'
ANCHOR_HASH = '0x331c54fd1b37302697157dec30d2a1e0a13682843301f60d8ebac004f8bc4155'


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def inspect(name):
    return json.loads(command('docker', 'inspect', name))[0]


def rpc(pid, method, params, authenticated=False):
    headers = ['-H', 'Content-Type: application/json']
    port = 18545
    if authenticated:
        secret = bytes.fromhex((ROOT / 'pipeline/jwt').read_text().strip().removeprefix('0x'))
        def b64(value):
            return base64.urlsafe_b64encode(value).rstrip(b'=')
        body = b64(b'{"alg":"HS256","typ":"JWT"}') + b'.' + b64(
            json.dumps({'iat': int(time.time())}).encode())
        token = (body + b'.' + b64(hmac.digest(secret, body, 'sha256'))).decode()
        headers += ['-H', 'Authorization: Bearer ' + token]
        port = 18551
    request = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
    result = json.loads(command('nsenter', '--target', str(pid), '--net', 'curl',
                                '-fsS', '--max-time', '30', *headers, '--data',
                                request, f'http://127.0.0.1:{port}'))
    assert 'error' not in result, result
    return result['result']


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('client', choices=['geth', 'nethermind'])
    p.add_argument('--image', required=True)
    p.add_argument('--commit', required=True)
    p.add_argument('--memory-gib', type=int, choices=[16, 32], required=True)
    a = p.parse_args()
    assert '@sha256:' in a.image
    evidence = ROOT / 'migration-builds' / (a.client + '-startup')
    evidence.mkdir(parents=True, exist_ok=True)
    assert not (evidence / 'result.json').exists(), 'Inspect the existing evidence before repeating'
    recovery = json.loads(Path('/mnt/pbt-recovery/status.json').read_text())
    assert recovery['phase'] == 'recovery_ready_existing_db_preserved', recovery
    source = inspect(f'pbt-1-{a.client}-execution')
    assert not source['State']['Running']
    for mount in source['Mounts']:
        if mount['Type'] == 'bind' and mount['RW']:
            path = Path(mount['Source'])
            for cid in command('docker', 'ps', '-q').splitlines():
                for other in inspect(cid)['Mounts']:
                    if not other['RW']:
                        continue
                    other_path = Path(other['Source'])
                    assert not (path == other_path or path in other_path.parents
                                or other_path in path.parents), (
                                    'DB has a writable mount in a running container', cid, other_path)
    genesis = json.loads((ROOT / 'pbt-1-source-genesis.json').read_text())
    assert genesis['config']['amsterdamTime'] == 1769856769
    assert 'binaryTrieTime' not in genesis['config']
    command('docker', 'pull', a.image)
    image = inspect(a.image)
    assert image['Config']['Labels']['ethpandaops.io.commitRef'] == a.commit
    name = f'pbt-1-{a.client}-migration-image-check'
    args = ['docker', 'run', '-d', '--name', name, '--network', 'none',
            '--cpus', '8', '--memory', f'{a.memory_gib}g',
            '--memory-swap', f'{a.memory_gib}g']
    for mount in source['Mounts']:
        if mount['Type'] == 'bind':
            args += ['-v', mount['Source'] + ':' + mount['Destination']
                     + (':ro' if not mount['RW'] else '')]
    client_args = source['Config']['Cmd']
    if a.client == 'nethermind':
        client_args = [
            '--Init.MemoryHint=2500000000' if v.startswith('--Init.MemoryHint=') else v
            for v in client_args]
    args += [a.image, *client_args]
    (evidence / 'command.json').write_text(json.dumps(args, indent=2) + '\n')
    report = {'status': 'starting', 'time': time.time(), 'image': a.image,
              'commit': a.commit, 'memory_gib': a.memory_gib, 'cpus': 8,
              'network_mode': 'none', 'migration_qualified': False}
    started = False
    try:
        command(*args)
        started = True
        deadline = time.monotonic() + 600
        while True:
            container = inspect(name)
            assert container['State']['Running'], container['State']
            pid = container['State']['Pid']
            try:
                head = rpc(pid, 'eth_getBlockByNumber', ['latest', False])
                if head is not None:
                    break
            except (subprocess.CalledProcessError, ValueError, AssertionError):
                pass
            assert time.monotonic() < deadline, 'RPC startup timeout'
            time.sleep(5)
        assert int(head['number'], 16) == HEAD, head['number']
        assert head['hash'] == HEAD_HASH and head['stateRoot'] == STATE_ROOT
        anchor = rpc(pid, 'eth_getBlockByNumber', [hex(ANCHOR), False])
        assert anchor['hash'] == ANCHOR_HASH
        samples = {}
        for address in ('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
                        '0x00000961ef480eb55e80d19ad83579a64c007002',
                        '0x0000bbddc7ce488642fb579f8b00f3a590007251'):
            code = rpc(pid, 'eth_getCode', [address, 'latest'])
            assert code != '0x', address
            samples[address] = hashlib.sha256(bytes.fromhex(code[2:])).hexdigest()
        bodies = {}
        for number in (ANCHOR + 1, (ANCHOR + HEAD) // 2, HEAD):
            body = rpc(pid, 'engine_getPayloadBodiesByRangeV2', [hex(number), '0x1'], True)
            expected = json.loads(gzip.decompress(
                (ROOT / 'pipeline/blocks' / f'{number:08d}.json.gz').read_bytes()))
            payload = expected['new_payload'][0]
            assert len(body) == 1 and body[0]
            for key in ('blockAccessList', 'transactions', 'withdrawals'):
                assert body[0][key] == payload[key], (number, key)
            bodies[str(number)] = {
                'bal_bytes': (len(body[0]['blockAccessList']) - 2) // 2,
                'transactions': len(body[0]['transactions'])}
        report.update(status='startup_and_sample_checks_passed', head=HEAD,
                      head_hash=head['hash'], state_root=head['stateRoot'],
                      anchor=ANCHOR, anchor_hash=anchor['hash'], code_samples=samples,
                      sampled_payload_bodies=bodies)
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        if started:
            # Do not kill a DB process on a timer; verify its graceful stop.
            command('docker', 'stop', '--time', '-1', name)
            state = inspect(name)['State']
            report['stopped_state'] = state
            with (evidence / 'container.log').open('w') as stream:
                subprocess.run(['docker', 'logs', name], stdout=stream,
                               stderr=subprocess.STDOUT, check=True)
            if state['Running'] or state['OOMKilled'] or state['ExitCode'] not in (0, 130):
                report.update(status='failed', error='Container did not stop cleanly')
        report['finished_at'] = time.time()
        (evidence / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)
    assert report['status'] == 'startup_and_sample_checks_passed', report


if __name__ == '__main__':
    main()
