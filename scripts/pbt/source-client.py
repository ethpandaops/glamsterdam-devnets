#!/usr/bin/env python3
"""Start an isolated PBT preparation client; never connect the chain-id-1 DB to peers."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess

ROOT = Path('/data/pbt-1')
IMAGES = {'geth': 'ethereum/client-go:v1.17.7', 'besu': 'hyperledger/besu:26.9.0',
          'erigon': 'erigontech/erigon:v3.7.1', 'nethermind': 'nethermind/nethermind:2.1.0'}


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('client', choices=IMAGES)
    a = p.parse_args(); c = a.client
    db = ROOT / c
    state = json.loads(run('docker', 'inspect', f'pbt-1-{c}-snapshot'))[0]['State']
    assert not state['Running'] and state['ExitCode'] == 0
    assert (ROOT / 'snapshot-fetcher/done').is_file()
    genesis = ROOT / 'pbt-1-source-genesis.json'
    assert json.loads(genesis.read_text())['config']['amsterdamTime'] == 1769856769
    if c == 'nethermind':
        assert (ROOT / 'nethermind-flatdb-cleanup/complete.json').is_file()
        db = db / 'mainnet'
    for cid in run('docker', 'ps', '-q').splitlines():
        for m in json.loads(run('docker', 'inspect', cid))[0]['Mounts']:
            other = Path(m['Source'])
            assert not (other == db or other in db.parents or db in other.parents), (cid, other)
    out = ROOT / 'pipeline'; out.mkdir(exist_ok=True)
    jwt = out / 'jwt'
    if not jwt.exists():
        jwt.write_text(secrets.token_hex(32)); jwt.chmod(0o600)
    # Pin the locally pulled image by digest for repeatable subsequent opens.
    image = json.loads(run('docker', 'image', 'inspect', IMAGES[c]))[0]['RepoDigests'][0]
    dest = '/data/geth' if c == 'geth' else '/data'
    if c == 'geth':
        assert (db / 'chaindata').is_dir() and (db / 'triedb').is_dir()
    args = ['docker', 'run', '-d', '--pull=never', '--name', f'pbt-1-{c}-execution',
            '--network=none', '--hostname=localhost', '--user=0:0', '--memory=48g', '--memory-swap=48g',
            '-v', f'{db}:{dest}', '-v', f'{genesis}:/genesis.json:ro',
            '-v', f'{jwt}:/jwt:ro']
    if c == 'besu':
        # The image entrypoint changes UID; invoke Besu directly so the root-only
        # JWT remains readable without making it world-readable on the host.
        args += ['--entrypoint=/opt/besu/bin/besu', '-e', 'JAVA_OPTS=-Xmx24g']
    args += [image]
    if c == 'geth':
        args += ['--datadir=/data', '--override.genesis=/genesis.json', '--override.amsterdam=1769856769',
                 '--http', '--http.addr=127.0.0.1', '--http.port=18545', '--http.api=eth,web3,debug,testing',
                 '--authrpc.addr=127.0.0.1', '--authrpc.port=18551', '--authrpc.jwtsecret=/jwt',
                 '--syncmode=full', '--nodiscover', '--maxpeers=0', '--port=0', '--cache=8192',
                 '--cache.gc=0', '--rpc.http-body-limit=128', '--rpc.gascap=200000000']
    elif c == 'besu':
        assert (db / 'database').is_dir()
        args += ['--data-path=/data', '--genesis-file=/genesis.json', '--network-id=1',
                 '--p2p-enabled=false', '--sync-mode=FULL', '--host-allowlist=all',
                 '--engine-host-allowlist=all', '--rpc-http-enabled=true', '--rpc-http-host=127.0.0.1',
                 '--rpc-http-port=18545', '--rpc-http-api=ETH,WEB3,DEBUG',
                 '--engine-rpc-enabled=true', '--engine-rpc-port=18551', '--engine-jwt-secret=/jwt']
    elif c == 'erigon':
        assert (db / 'chaindata').is_dir() and (db / 'snapshots').is_dir()
        args += ['--datadir=/data', '--chain=mainnet', '--networkid=1', '--override.osaka=1764798551',
                 '--override.amsterdam=1769856769', '--http', '--http.addr=127.0.0.1',
                 '--http.port=18545', '--http.api=eth,web3,debug', '--http.vhosts=*',
                 '--authrpc.addr=127.0.0.1', '--authrpc.port=18551', '--authrpc.jwtsecret=/jwt',
                 '--externalcl', '--nodiscover', '--maxpeers=0', '--no-downloader', '--snap.stop',
                 '--db.size.limit=2TB']
    else:
        args += ['--config=mainnet', '--Init.ChainSpecPath=/genesis.json', '--Init.BaseDbPath=/data',
                 '--Init.DiscoveryEnabled=false', '--Network.MaxActivePeers=0',
                 '--Network.EnableEnrDiscovery=false', '--Discovery.UseDefaultDiscv5Bootnodes=false',
                 '--Sync.FastSync=false', '--Sync.SnapSync=false', '--FlatDb.Enabled=true',
                 '--FlatDb.Layout=Flat', '--Merge.TerminalTotalDifficulty=0', '--Pruning.Mode=None',
                 '--Init.MemoryHint=24000000000', '--JsonRpc.Enabled=true', '--JsonRpc.Host=127.0.0.1',
                 '--JsonRpc.Port=18545', '--JsonRpc.EnabledModules=Eth,Web3,Debug',
                 '--JsonRpc.EngineHost=127.0.0.1', '--JsonRpc.EnginePort=18551', '--JsonRpc.JwtSecretFile=/jwt',
                 '--FlatDb.CompactionOffset=0', '--FlatDb.CompactSize=1', '--FlatDb.MinReorgDepth=0',
                 '--FlatDb.MaxReorgDepth=0', '--FlatDb.EnableLongFinality=false']
    (out / 'client-command.json').write_text(json.dumps(args, indent=2) + '\n')
    print(run(*args))


if __name__ == '__main__':
    main()
