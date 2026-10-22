#!/usr/bin/env python3
"""Validate a locally generated PBT-1 genesis candidate; never deploy it."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import yaml

REPO = Path(__file__).resolve().parents[2]
INVENTORY = REPO / 'ansible/inventories/pbt-1'


def validate_withdrawal_funding(state):
    # Same mnemonic-account-0 sweep used by MSF-2. The separately reviewed
    # funding transfer tops up Spamoor's mnemonic-account-9 root wallet.
    recipient = '0x454b0EA7d8aD3C56D0CF2e44Ed97b2Feab4D7AF2'
    credential = '0x01' + '00' * 11 + recipient[2:].lower()
    assert len(state['validators']) == len(state['balances']) == 2304
    assert all(v['withdrawal_credentials'].lower() == credential for v in state['validators']), 'Withdrawal destination/type changed'
    assert all(int(v['effective_balance']) == 32_000_000_000 for v in state['validators']), 'Unexpected effective balance'
    assert all(int(b) == 10_000_000_000_000 for b in state['balances']), 'Missing genesis withdrawal funding'
    return {'recipient': recipient, 'credential_type': '0x01',
            'validator_balance_eth': 10000, 'effective_balance_eth': 32,
            'initial_excess_eth': 2304 * (10000 - 32),
            'funding_path': 'CL excess-balance withdrawals to account 0, then transfer to Spamoor account 9',
            'live_withdrawals_verified': False}


def validate(workspace):
    files = INVENTORY / 'files'
    provenance = json.loads((files / 'genesis-input-provenance.json').read_text())
    raw_head = (files / 'shadowfork_block.json').read_bytes()
    block = json.loads(raw_head)['result']
    assert hashlib.sha256(raw_head).hexdigest() == provenance['block_file_sha256']
    assert block['hash'] == provenance['hash']
    assert block['stateRoot'] == provenance['state_root']
    assert int(block['number'], 16) == provenance['head'] == 24503958
    assert block['transactions'] and all(isinstance(t, dict) for t in block['transactions'])

    output = workspace / 'output'
    metadata = output / 'metadata'
    source = (files / 'source-genesis.json').read_bytes()
    assert hashlib.sha256(source).hexdigest() == provenance['source_genesis_sha256']
    assert (metadata / 'genesis.json').read_bytes() == source
    genesis = json.loads(source)
    assert genesis['config']['amsterdamTime'] == 1769856769
    assert 'binaryTrieTime' not in genesis['config']

    config = yaml.safe_load((metadata / 'config.yaml').read_text())
    state = json.loads((output / 'parsed/parsedConsensusGenesis.json').read_text())
    assert int(state['slot']) == 0
    assert config['GLOAS_FORK_EPOCH'] == 0
    assert config['HEZE_FORK_EPOCH'] == 2**64 - 1
    assert int(state['fork']['current_version'], 16) == config['GLOAS_FORK_VERSION']
    assert int(state['genesis_time']) > int(block['timestamp'], 16)
    assert int(state['genesis_time']) == config['MIN_GENESIS_TIME'] + config['GENESIS_DELAY']
    assert state['latest_block_hash'] == block['hash']
    assert state['latest_execution_payload_bid']['parent_block_hash'] == block['hash']
    assert state['eth1_data']['block_hash'] == block['hash']
    assert (metadata / 'deposit_contract_block_hash.txt').read_text().strip() == block['hash']
    assert int((metadata / 'deposit_contract_block.txt').read_text().strip()) == 24503958
    assert config['GAS_LIMIT_SCHEDULE'] == [{'EPOCH': 0, 'GAS_LIMIT': 200000000}]

    ranges = {}
    for line in (INVENTORY / 'inventory.ini').read_text().splitlines():
        if 'ansible_host=' not in line:
            continue
        fields = dict(re.findall(r'(\w+)=(\S+)', line))
        start, end = int(fields['validator_start']), int(fields['validator_end'])
        assert end - start == 256
        ranges[line.split()[0]] = {'start': start, 'end': end}
    assert len(ranges) == 9
    indices = [i for r in ranges.values() for i in range(r['start'], r['end'])]
    assert sorted(indices) == list(range(2304)), 'Validator assignments overlap or have gaps'
    assert len(state['validators']) == len(state['balances']) == 2304
    assert len({v['pubkey'] for v in state['validators']}) == 2304
    assert config['MIN_GENESIS_ACTIVE_VALIDATOR_COUNT'] == 2304
    assert all(int(v['activation_epoch']) == 0 for v in state['validators'])
    withdrawal_funding = validate_withdrawal_funding(state)
    assert (metadata / 'genesis_validators_root.txt').read_text().strip() == state['genesis_validators_root']

    keys_verified = False
    keys = workspace / 'validator-keys'
    if keys.exists():
        for host, assigned in ranges.items():
            directory = keys / host
            assert (directory / '.keyrange').read_text() == f"{assigned['start']}-{assigned['end']}"
            expected = {v['pubkey'].removeprefix('0x')
                        for v in state['validators'][assigned['start']:assigned['end']]}
            generated = json.loads((directory / 'pubkeys.json').read_text())
            assert {p.removeprefix('0x') for p in generated} == expected, host
            keystores = list((directory / 'keys').rglob('*.json'))
            assert len(keystores) == 256, host
            assert {json.loads(p.read_text())['pubkey'].removeprefix('0x')
                    for p in keystores} == expected, host
        keys_verified = True

    artifacts = {}
    for filename in ('genesis.ssz', 'genesis.json', 'config.yaml',
                     'genesis_validators_root.txt', 'deposit_contract_block_hash.txt'):
        content = (metadata / filename).read_bytes()
        assert content
        artifacts[filename] = {'bytes': len(content),
                               'sha256': hashlib.sha256(content).hexdigest()}
    lighthouse_verified = False
    lighthouse_report = workspace / 'lighthouse-validation.json'
    if lighthouse_report.exists():
        lighthouse = json.loads(lighthouse_report.read_text())
        pinned = json.loads((REPO / 'scripts/pbt/migration-builds.json').read_text())['lighthouse']
        assert lighthouse['status'] == 'isolated_genesis_load_passed'
        assert lighthouse['source_commit'] == pinned['commit']
        assert lighthouse['image'] == pinned['image_digest']
        assert lighthouse['genesis_ssz_sha256'] == artifacts['genesis.ssz']['sha256']
        assert lighthouse['execution_head_hash'] == block['hash']
        assert lighthouse['genesis_validators_root'] == state['genesis_validators_root']
        assert lighthouse['decoded_version'] == 'gloas'
        assert lighthouse['validator_count'] == 2304
        assert lighthouse['network_mode'] == 'none' and lighthouse['container_stopped']
        lighthouse_verified = True
    return {
        'status': 'structural_checks_passed',
        'launch_authorized': False,
        'timestamp_purpose': 'validation_candidate_not_scheduled_launch',
        'genesis_time': int(state['genesis_time']),
        'head': provenance['head'], 'head_hash': block['hash'],
        'mpt_state_root': block['stateRoot'],
        'genesis_validators_root': state['genesis_validators_root'],
        'validator_count': 2304, 'validator_ranges': ranges,
        'withdrawal_funding': withdrawal_funding,
        'validator_public_key_mapping_verified': keys_verified,
        'isolated_lighthouse_genesis_load_verified': lighthouse_verified,
        'artifacts': artifacts,
        'pending': [*([] if lighthouse_verified else ['Pinned Lighthouse SSZ/startup compatibility']),
                    *([] if keys_verified else ['Validator key generation and public-key mapping verification']),
                    'All worker build, database and pre-genesis checks',
                    'Live Engine API, block production and finality after launch',
                    'Choose actual launch time and regenerate/revalidate before deployment'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workspace', type=Path)
    args = parser.parse_args()
    report = validate(args.workspace)
    (args.workspace / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
