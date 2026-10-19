#!/usr/bin/env python3
"""Wait for the pinned restore, validate, drop obsolete Patricia data, and reopen.

Runs on the dedicated PBT-1 Nethermind VM as root. The client performs deletion
with its own FlatDB ownership checks. No directory is manually removed here.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import time

ROOT = Path('/data/pbt-1')
DB = ROOT / 'nethermind/mainnet'
STATE = ROOT / 'snapshot-fetcher'
EVIDENCE = ROOT / 'nethermind-flatdb-cleanup'
FETCHER = 'pbt-1-nethermind-snapshot'
CONTAINER = 'pbt-1-nethermind-flatdb-check'
IMAGE = 'nethermind/nethermind@sha256:25f72063f6fc8ba89f1c08abe1ed3211203b3cf303c9618cc3a2488e1e4ab2e0'
HEAD = 24452538
HASH = '0x0fd7242bab5055dda36f374f352c78cae381daae9b3e8febe895dce35c907591'
STATE_ROOT = '0xecf809f327549d4a93eeae29252e8f33b0e9f188cba92f0bb43207d4c7a9c9ca'
ADDRESSES = [
    '0x00000000219ab540356cbb839cbe05303d7705fa',
    '0x00000961ef480eb55e80d19ad83579a64c007002',
    '0x0000bbddc7ce488642fb579f8b00f3a590007251',
]


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def inspect(name):
    return json.loads(run('docker', 'inspect', name))[0]


def allocated(path):
    return int(run('du', '-s', '-B1', str(path)).split()[0]) if path.exists() else 0


def rpc(pid, method, params):
    value = json.loads(run(
        'nsenter', '--target', str(pid), '--net', 'curl', '-fsS', '--max-time', '30',
        '-H', 'Content-Type: application/json', '--data',
        json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}),
        'http://127.0.0.1:18545',
    ))
    if 'error' in value:
        raise RuntimeError(value['error'])
    return value['result']


def check_head(block):
    return bool(block and int(block['number'], 16) == HEAD
                and block['hash'] == HASH and block['stateRoot'] == STATE_ROOT)


def phase(name, drop, genesis, jwt):
    print(f'Starting {name}; DropPruningTrieState={drop}', flush=True)
    run('docker', 'run', '--detach', '--pull=never', '--name', CONTAINER,
        '--network=none', '--user=0:0', '--memory=32g', '--memory-swap=32g',
        '--volume', f'{DB}:/data', '--volume', f'{genesis}:/chainspec.json:ro',
        '--volume', f'{jwt}:/jwt:ro', IMAGE,
        '--config=mainnet', '--Init.ChainSpecPath=/chainspec.json',
        '--Init.BaseDbPath=/data', '--Init.DiscoveryEnabled=false',
        '--Network.MaxActivePeers=0', '--Network.EnableEnrDiscovery=false',
        '--Discovery.UseDefaultDiscv5Bootnodes=false',
        '--Sync.FastSync=false', '--Sync.SnapSync=false',
        '--FlatDb.Enabled=true', '--FlatDb.Layout=Flat',
        f'--FlatDb.DropPruningTrieState={str(drop).lower()}',
        '--Merge.TerminalTotalDifficulty=0', '--Pruning.Mode=None',
        '--Init.MemoryHint=16000000000', '--JsonRpc.Enabled=true',
        '--JsonRpc.Host=127.0.0.1', '--JsonRpc.Port=18545',
        '--JsonRpc.EnabledModules=Eth,Web3', '--JsonRpc.EngineHost=127.0.0.1',
        '--JsonRpc.EnginePort=18551', '--JsonRpc.JwtSecretFile=/jwt', '--log=INFO')
    success = False
    try:
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            state = inspect(CONTAINER)['State']
            if not state['Running']:
                raise RuntimeError(f'{name} exited before verification: {state["ExitCode"]}')
            pid = state['Pid']
            try:
                block = rpc(pid, 'eth_getBlockByNumber', ['latest', False])
            except (subprocess.CalledProcessError, ValueError, RuntimeError):
                time.sleep(10)
                continue
            if check_head(block):
                break
            time.sleep(10)
        else:
            raise RuntimeError(f'{name} did not reach the pinned head in 30 minutes')
        samples = {}
        for address in ADDRESSES:
            code = rpc(pid, 'eth_getCode', [address, 'latest'])
            if not code or code == '0x':
                raise RuntimeError(f'Missing expected contract code at {address}')
            samples[address] = {
                'code_sha256': hashlib.sha256(bytes.fromhex(code[2:])).hexdigest(),
                'balance': rpc(pid, 'eth_getBalance', [address, 'latest']),
                'slot0': rpc(pid, 'eth_getStorageAt', [address, '0x0', 'latest']),
            }
        (EVIDENCE / f'{name}.json').write_text(json.dumps({'block': block, 'samples': samples}, indent=2))
        success = True
    finally:
        state = inspect(CONTAINER)['State']
        if state['Running']:
            run('docker', 'stop', '--time=600', CONTAINER)
        with (EVIDENCE / f'{name}.log').open('w') as output:
            subprocess.run(['docker', 'logs', CONTAINER], stdout=output, stderr=subprocess.STDOUT, check=True)
        state = inspect(CONTAINER)['State']
        if state['OOMKilled'] or state['ExitCode'] not in (0, 130):
            raise RuntimeError(f'{name} did not shut down cleanly: {state}')
        if success:
            run('docker', 'rm', CONTAINER)
    print(f'{name}: head/root, state samples and clean shutdown verified', flush=True)
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--genesis', type=Path, required=True)
    args = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with (EVIDENCE / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (EVIDENCE / 'complete.json').exists():
            print('Cleanup already completed; see complete.json', flush=True)
            return
        genesis = args.genesis.resolve(strict=True)
        config = json.loads(genesis.read_text())['config']
        if config.get('chainId') != 1 or config.get('amsterdamTime') != 1769856769:
            raise RuntimeError('Unexpected chain identity or Amsterdam schedule')
        print('Waiting for the complete, successful Nethermind restore', flush=True)
        while True:
            state = inspect(FETCHER)['State']
            if not state['Running']:
                if state['ExitCode'] != 0 or not (STATE / 'done').exists():
                    raise RuntimeError('Restore failed or has no completion marker')
                break
            time.sleep(30)
        metadata = json.loads((STATE / 'source-metadata.json').read_text())
        if metadata['shadowfork']['head_hash'] != HASH or metadata['docker_image'] != 'nethermind/nethermind:2.1.0':
            raise RuntimeError('Unexpected snapshot provenance')
        if DB.resolve() != DB or not (DB / 'flat').is_dir() or not (DB / 'state').is_dir():
            raise RuntimeError('Unexpected native database layout; inspect before cleanup')
        # Refuse to open the source concurrently with another container.
        for cid in run('docker', 'ps', '-q').splitlines():
            for mount in inspect(cid).get('Mounts', []):
                source = Path(mount['Source'])
                if source == DB or source in DB.parents or DB in source.parents:
                    raise RuntimeError(f'Another running container mounts the database: {cid}')
        jwt = EVIDENCE / 'jwt'
        jwt.write_text(secrets.token_hex(32)); jwt.chmod(0o600)
        before = allocated(DB / 'state')
        baseline = phase('baseline', False, genesis, jwt)
        cleaned = phase('drop-patricia', True, genesis, jwt)
        if cleaned != baseline:
            raise RuntimeError('State samples changed during cleanup')
        after = allocated(DB / 'state')
        if before > 16 * 1024**2 and after >= 16 * 1024**2:
            raise RuntimeError('Patricia state remains large; inspect ownership/cleanup logs')
        reopened = phase('reopen-flat-only', False, genesis, jwt)
        if reopened != baseline:
            raise RuntimeError('State samples changed on restart')
        report = {'head': HEAD, 'hash': HASH, 'state_root': STATE_ROOT, 'image': IMAGE,
                  'patricia_bytes_before': before, 'patricia_bytes_after': after,
                  'reclaimed_bytes': before-after,
                  'genesis_sha256': hashlib.sha256(genesis.read_bytes()).hexdigest(),
                  'verified_at_unix': int(time.time())}
        (EVIDENCE / 'complete.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
