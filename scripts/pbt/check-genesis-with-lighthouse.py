#!/usr/bin/env python3
"""Load an existing candidate with pinned Lighthouse in an isolated container.

Does not generate a timestamp, publish files, connect an EL, run validators or
deploy a worker. Each invocation uses a fresh database and public config subset.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
PUBLIC_FILES = ('bootstrap_nodes.txt', 'config.yaml', 'deposit_contract.txt',
                'deposit_contract_block.txt', 'deposit_contract_block_hash.txt',
                'genesis.json', 'genesis.ssz', 'genesis_validators_root.txt', 'validator_names.yaml')


def command(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE).strip()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')
    path.chmod(0o600)


def inspect(cid):
    return json.loads(command('docker', 'inspect', cid))[0]


def rpc(pid, endpoint):
    args = ([] if os.geteuid() == 0 else ['sudo', '-n']) + [
        'nsenter', '--target', str(pid), '--net', 'curl', '-fsS', '--max-time', '5',
        '-H', 'Accept: application/json', 'http://127.0.0.1:5052' + endpoint]
    return json.loads(command(*args))


def interrupted(signum, frame):
    raise KeyboardInterrupt()


def validate(workspace, report_name):
    assert Path(report_name).name == report_name and report_name.endswith('.json')
    workspace = workspace.resolve(strict=True)
    assert workspace.is_relative_to(Path.home() / '.local/state/pbt-1-run/genesis')
    report_path = workspace / report_name
    assert not report_path.exists(), 'Preserve the existing validation report; use a new report name'
    spec = importlib.util.spec_from_file_location('structure', Path(__file__).with_name('validate-genesis.py'))
    structure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(structure)
    expected = structure.validate(workspace)
    parsed = json.loads((workspace / 'output/parsed/parsedConsensusGenesis.json').read_text())
    pinned = json.loads((REPO / 'scripts/pbt/migration-builds.json').read_text())['lighthouse']
    image = json.loads(command('docker', 'image', 'inspect', pinned['image_digest']))[0]
    assert image['Config']['Labels']['ethpandaops.io.commitRef'] == pinned['commit']
    identifier = uuid.uuid4().hex[:12]
    evidence = workspace / ('lighthouse-check-' + identifier)
    evidence.mkdir(mode=0o700)
    config = evidence / 'network-config'
    config.mkdir(mode=0o700)
    source = workspace / 'output/metadata'
    hashes = {}
    for name in PUBLIC_FILES:
        path = source / name
        assert path.is_file() and not path.is_symlink(), name
        hashes[name] = sha(path)
        shutil.copyfile(path, config / name)
        (config / name).chmod(0o644)
    assert set(p.name for p in config.iterdir()) == set(PUBLIC_FILES)
    name = 'pbt-1-genesis-validation-' + identifier
    args = ['docker', 'create', '--name=' + name, '--pull=never', '--network=none',
            '--memory=4g', '--memory-swap=4g', '--cpus=2', '--restart=no',
            '--tmpfs=/check:rw,size=1g', '-v', str(config) + ':/network-config:ro',
            pinned['image_digest'], 'lighthouse', 'bn', '--testnet-dir=/network-config',
            '--datadir=/check', '--disable-upnp', '--disable-quic',
            '--execution-endpoint=http://127.0.0.1:8551',
            '--execution-jwt-secret-key=' + '0' * 64, '--http', '--http-address=127.0.0.1',
            '--port=19000', '--target-peers=0', '--disable-enr-auto-update', '--allow-insecure-genesis-sync']
    save(evidence / 'command.json', args)
    cid = command(*args)
    save(evidence / 'container.json', {'id': cid, 'name': name, 'time': time.time()})
    try:
        command('docker', 'start', cid)
        deadline = time.monotonic() + 240
        while True:
            info = inspect(cid)
            assert info['State']['Running'], 'Isolated Lighthouse exited; inspect retained container log'
            assert info['HostConfig']['NetworkMode'] == 'none'
            assert info['HostConfig']['Memory'] == info['HostConfig']['MemorySwap'] == 4 * 1024**3
            try:
                genesis = rpc(info['State']['Pid'], '/eth/v1/beacon/genesis')['data']
                decoded = rpc(info['State']['Pid'], '/eth/v2/debug/beacon/states/genesis')
                break
            except (subprocess.CalledProcessError, ValueError, KeyError):
                assert time.monotonic() < deadline, 'Lighthouse genesis API startup exceeded four minutes'
                time.sleep(2)
        state = decoded['data']
        assert decoded['version'] == 'gloas'
        assert int(state['slot']) == 0 and int(state['genesis_time']) == expected['genesis_time']
        assert int(genesis['genesis_time']) == expected['genesis_time']
        assert state['latest_block_hash'] == expected['head_hash']
        assert state['latest_execution_payload_bid']['parent_block_hash'] == expected['head_hash']
        assert state['eth1_data']['block_hash'] == expected['head_hash']
        assert state['genesis_validators_root'] == genesis['genesis_validators_root'] == expected['genesis_validators_root']
        assert len(state['validators']) == expected['validator_count'] == 2304
        assert [v['pubkey'] for v in state['validators']] == [v['pubkey'] for v in parsed['validators']]
        assert state['balances'] == parsed['balances']
        assert [v['withdrawal_credentials'] for v in state['validators']] == [v['withdrawal_credentials'] for v in parsed['validators']]
        structure.validate_withdrawal_funding(state)
        save(evidence / 'decoded-genesis.json', decoded)
        save(evidence / 'genesis-api.json', genesis)
    finally:
        if inspect(cid)['State']['Running']:
            command('docker', 'stop', '--time=30', cid)
        with (evidence / 'container.log').open('w') as log:
            subprocess.run(['docker', 'logs', cid], stdout=log, stderr=subprocess.STDOUT, check=True)
        stopped = inspect(cid)['State']
        save(evidence / 'stopped.json', stopped)
    assert not stopped['Running'] and not stopped['OOMKilled'] and stopped['ExitCode'] == 0
    for filename, checksum in hashes.items():
        assert sha(source / filename) == sha(config / filename) == checksum
    report = {'status': 'isolated_genesis_load_passed', 'checked_at': time.time(),
              'scope': 'Existing validation candidate; no launch time selected, EL connected or validator running',
              'image': pinned['image_digest'], 'source_commit': pinned['commit'],
              'genesis_ssz_sha256': hashes['genesis.ssz'], 'decoded_version': decoded['version'],
              'head': expected['head'], 'execution_head_hash': expected['head_hash'],
              'genesis_validators_root': expected['genesis_validators_root'], 'validator_count': 2304,
              'network_mode': 'none', 'container_stopped': True, 'container_id': cid,
              'launch_authorized': False, 'public_metadata_sha256': hashes,
              'evidence_directory': str(evidence), 'genesis_timestamp_purpose': 'candidate_validation_only'}
    save(report_path, report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    parser.add_argument('--report-name', default='lighthouse-validation.json')
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, interrupted)
    result = validate(args.workspace, args.report_name)
    print(json.dumps({key: result[key] for key in ('status', 'head', 'validator_count', 'container_stopped', 'launch_authorized')}))
