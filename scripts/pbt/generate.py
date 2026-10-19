#!/usr/bin/env python3
"""Deterministic mixed transaction workload, durable BAL-bearing Engine replay records.

Run inside the Geth container's network namespace, using the host Python venv.
The original immutable Jochemnet release remains the recoverable anchor. This
advances its working copy. Setup is archived and replayed like every other block.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

from eth_account import Account
from eth_utils import keccak, to_checksum_address
from coincurve import PrivateKey
import rlp
from pipeline_rpc import RPC, ROOT, ANCHOR, baseline, save

WETH = to_checksum_address('0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2')
TREASURY = Account.from_key((1).to_bytes(32, 'big'))  # Public test key, isolated chain only.
WALLETS = [Account.from_key(hashlib.sha256(f'pbt-1-mixed-v1-wallet-{i}'.encode()).digest()) for i in range(64)]
RUNTIME = '6020355f355500'  # Store calldata word 1 at slot calldata word 0.
INIT = '0x6007600a5f3960075ff3' + RUNTIME
SIGNERS = {a.address: PrivateKey(a.key) for a in [TREASURY, *WALLETS]}


def signed(account, nonce, to, value=0, data='0x', gas=500000):
    fields=[1,nonce,10**6,10**9,gas,bytes.fromhex(to[2:]) if to else b'',value,bytes.fromhex(data[2:]),[]]
    signature=SIGNERS[account.address].sign_recoverable(keccak(b'\x02'+rlp.encode(fields)),hasher=None)
    return '0x'+(b'\x02'+rlp.encode(fields+[signature[64],int.from_bytes(signature[:32],'big'),int.from_bytes(signature[32:64],'big')])).hex()


def setup_plan(rpc):
    p = ROOT / 'workload.json'
    if p.exists():
        return json.loads(p.read_text())
    baseline(rpc)
    assert int(rpc.call('eth_getBalance', [TREASURY.address, 'latest']), 16) > 10000 * 10**18
    assert rpc.call('eth_getCode', [WETH, 'latest']) != '0x'
    nonce = int(rpc.call('eth_getTransactionCount', [TREASURY.address, 'latest']), 16)
    # Eight separate storage contracts; 64 distinct senders and bounded storage
    # key space avoid turning this into an account/state bloat stress test.
    contracts = [to_checksum_address(keccak(rlp.encode([bytes.fromhex(TREASURY.address[2:]), nonce+64+i]))[-20:]) for i in range(8)]
    plan = {'version': 1, 'anchor': ANCHOR, 'treasury_nonce': nonce,
            'wallets': [a.address for a in WALLETS], 'contracts': contracts,
            'wallet_initial_nonces': [int(rpc.call('eth_getTransactionCount', [a.address, 'latest']), 16) for a in WALLETS],
            'mix': ['native transfer', 'WETH deposit', 'WETH transfer', 'WETH withdrawal', 'storage write'],
            'timestamp_step_seconds': 12, 'block_gas_limit': 200000000,
            'transactions_per_workload_block': 900, 'setup_blocks': 3,
            'storage_runtime': '0x'+RUNTIME,
            'limitations': 'Synthetic representative operation mix; not measured mainnet traffic. No blobs or CL consensus. Each Engine forkchoice finalizes its head for deterministic persistence.'}
    save(p, plan)
    return plan


def make_txs(rpc, plan, index):
    if plan.get('version')==2 and index>=plan['v2']['start_index']:
        from workload_v2 import make_txs as v2_txs
        return v2_txs(plan,index,signed,WALLETS,TREASURY,WETH)
    n = plan['treasury_nonce']
    if index == 0:
        return [signed(TREASURY, n+i, a.address, 100*10**18) for i, a in enumerate(WALLETS)]
    if index == 1:
        return [signed(TREASURY, n+64+i, None, data=INIT, gas=1000000) for i in range(8)]
    if index == 2:
        return [signed(a, plan['wallet_initial_nonces'][i], WETH, 20*10**18, '0xd0e30db0') for i, a in enumerate(WALLETS)]
    block_index = index - 3
    count = plan['transactions_per_workload_block']
    # Derive nonces from the absolute transaction index, so resumption is exact.
    txs = []
    for j in range(count):
        seq = block_index * count + j
        w = seq % len(WALLETS); a = WALLETS[w]
        nonce = plan['wallet_initial_nonces'][w] + 1 + seq // len(WALLETS)
        kind = seq % 5
        recipient = WALLETS[(w + 1 + (seq // 64) % 63) % 64].address
        if kind == 0:
            tx = signed(a, nonce, recipient, 1)
        elif kind == 1:
            tx = signed(a, nonce, WETH, 10**12, '0xd0e30db0')
        elif kind == 2:
            tx = signed(a, nonce, WETH, data='0xa9059cbb'+recipient[2:].lower().zfill(64)+hex(10**9)[2:].zfill(64))
        elif kind == 3:
            tx = signed(a, nonce, WETH, data='0x2e1a7d4d'+hex(10**12)[2:].zfill(64))
        else:
            slot = (seq // 320) % 4096
            tx = signed(a, nonce, plan['contracts'][w % 8], data='0x'+hex(slot)[2:].zfill(64)+hex(seq+1)[2:].zfill(64))
        txs.append(tx)
    return txs


def archive(record):
    path = ROOT / 'blocks' / f'{record["number"]:08d}.json.gz'
    tmp = path.with_suffix('.tmp')
    with tmp.open('wb') as f:
        f.write(gzip.compress(json.dumps(record, separators=(',', ':')).encode(), compresslevel=1, mtime=0))
        f.flush(); os.fsync(f.fileno())
    tmp.replace(path)


def verify_receipts(rpc, record):
    receipts = rpc.call('eth_getBlockReceipts', [hex(record['number'])])
    assert len(receipts) == record['transactions'], (len(receipts), record['transactions'])
    failed = [r['transactionHash'] for r in receipts if int(r['status'], 16) != 1]
    assert not failed, f'Reverted workload transactions: {failed[:5]}'
    plan=json.loads((ROOT/'workload.json').read_text())
    if plan.get('version')==2 and record['index']>=plan['v2']['qualifying_start_index']:
        v=plan['v2'];state=v['state_gas_per_block']
        execution=sum(int(r['gasUsed'],16) for r in receipts)-state
        bal_bytes=(len(record['new_payload'][0]['blockAccessList'])-2)//2
        record.update(execution_gas=execution,state_gas=state,bal_bytes=bal_bytes,qualifying=True)
        assert record['gas_used']==max(execution,state), f'8037 dimension calculation mismatch: {execution}, {state}, header={record["gas_used"]}'
        assert abs(execution-v['target_execution_gas'])<=v['dimension_tolerance'], f'Execution gas outside target: {execution}'
        assert abs(state-v['target_state_gas'])<=v['dimension_tolerance'], f'State gas outside target: {state}'
        assert bal_bytes>=v['minimum_bal_bytes'], f'BAL too small: {bal_bytes}'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workload-blocks', type=int, required=True)
    a = p.parse_args()
    assert 0 <= a.workload_blocks <= 60000
    import fcntl
    lock = (ROOT / 'generate.lock').open('w'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    rpc = RPC(); plan = setup_plan(rpc)
    (ROOT / 'blocks').mkdir(exist_ok=True)
    pending = ROOT / 'pending.json'
    if pending.exists():
        r = json.loads(pending.read_text()); rpc.apply(r); verify_receipts(rpc, r); archive(r); pending.unlink()
    head = rpc.head()
    index = int(head['number'], 16) - ANCHOR
    if index:
        path = ROOT / 'blocks' / f'{ANCHOR+index:08d}.json.gz'
        prior = json.loads(gzip.decompress(path.read_bytes()))
        assert prior['hash'] == head['hash'] and prior['index'] == index-1
    started = time.time(); start_index = index
    total = a.workload_blocks + 3
    status = {'phase': 'generating', 'time': started, 'head': ANCHOR+index,
              'workload_blocks': max(0,index-3), 'target': a.workload_blocks}
    while index < total:
        assert shutil.disk_usage(ROOT).free > 150*10**9, 'Less than 150 GB free'
        txs = make_txs(rpc, plan, index)
        attrs = {'timestamp': hex(int(head['timestamp'], 16)+12), 'prevRandao': head['hash'],
                 'suggestedFeeRecipient': TREASURY.address, 'withdrawals': [],
                 'parentBeaconBlockRoot': head['hash'], 'slotNumber': hex(int(head['slotNumber'], 16)+1),
                 'targetGasLimit': hex(200000000)}
        envelope = rpc.call('testing_buildBlockV1', [head['hash'], attrs, txs, '0x7062742d312d6d697865642d7631'])
        payload = envelope['executionPayload']
        assert len(payload['transactions']) == len(txs), 'Builder omitted workload transactions'
        assert payload.get('blockAccessList'), 'No BAL in generated payload'
        block_hash = payload['blockHash']
        record = {'index': index, 'number': int(payload['blockNumber'], 16),
                  'kind': 'setup' if index < 3 else 'workload', 'hash': block_hash,
                  'state_root': payload['stateRoot'],
                  'bal_hash': '0x'+keccak(bytes.fromhex(payload['blockAccessList'][2:])).hex(),
                  'transactions': len(txs), 'gas_used': int(payload['gasUsed'], 16),
                  'new_payload': [payload, [], attrs['parentBeaconBlockRoot'], envelope['executionRequests']],
                  'forkchoice': [{'headBlockHash': block_hash, 'safeBlockHash': block_hash, 'finalizedBlockHash': block_hash}, None]}
        save(pending, record)  # Durable replay data BEFORE advancing the working DB.
        head = rpc.apply(record)
        verify_receipts(rpc, record)
        archive(record); pending.unlink()
        index += 1
        elapsed = time.time()-started
        status = {'phase': 'generating', 'time': time.time(), 'head': int(head['number'], 16),
                  'workload_blocks': max(0,index-3), 'target': a.workload_blocks,
                  'blocks_per_second': (index-start_index)/elapsed, 'last_gas_used': record['gas_used'],
                  'last_transactions': len(txs)}
        if plan.get('version')==2:
            status.update(qualifying_blocks=max(0,index-plan['v2']['qualifying_start_index']),
                          execution_gas=record.get('execution_gas'),state_gas=record.get('state_gas'),bal_bytes=record.get('bal_bytes'))
        save(ROOT / 'status.json', status)
        if index <= 5 or index % 25 == 0:
            print(json.dumps(status), flush=True)
    status.update(phase='generation_complete', time=time.time())
    save(ROOT / 'status.json', status)
    print(json.dumps(status), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        save(ROOT / 'status.json', {'phase': 'failed', 'time': time.time(), 'error': str(exc)})
        raise
