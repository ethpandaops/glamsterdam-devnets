#!/usr/bin/env python3
"""Check the exact target, state samples, and every generated BAL's availability."""
import argparse
import gzip
import hashlib
import json
import time
from pipeline_rpc import RPC, ROOT, ANCHOR, save


def record(number):
    return json.loads(gzip.decompress((ROOT/'blocks'/f'{number:08d}.json.gz').read_bytes()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workload-blocks', type=int, required=True)
    p.add_argument('--phase', choices=['before','after'], required=True)
    a=p.parse_args(); target=ANCHOR+3+a.workload_blocks
    rpc=RPC(); want=record(target); head=rpc.head()
    assert int(head['number'],16)==target
    assert all(head[k]==want[v] for k,v in [('hash','hash'),('stateRoot','state_root'),('blockAccessListHash','bal_hash')])
    plan=json.loads((ROOT/'workload.json').read_text())
    addresses=plan['wallets'][:4]+plan['contracts'][:4]+(plan.get('v2',{}).get('contracts',[]) if target>=ANCHOR+1020 else [])+[
        '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
        '0x00000961ef480eb55e80d19ad83579a64c007002',
        '0x0000bbddc7ce488642fb579f8b00f3a590007251']
    samples={}
    for address in addresses:
        code=rpc.call('eth_getCode',[address,'latest'])
        if address not in plan['wallets']:assert code!='0x', address
        samples[address]={'code_sha256':hashlib.sha256(bytes.fromhex(code[2:])).hexdigest(),
            'balance':rpc.call('eth_getBalance',[address,'latest']),
            'nonce':rpc.call('eth_getTransactionCount',[address,'latest']),
            'slot0':rpc.call('eth_getStorageAt',[address,'0x0','latest'])}
    count=0; bal_bytes=0; transactions=0; gas=0;qualifying=0;execution_sum=0;state_sum=0;bal_min=None
    if a.phase=='after':
        for start in range(ANCHOR+1,target+1,16):
            size=min(16,target-start+1)
            bodies=rpc.call('engine_getPayloadBodiesByRangeV2',[hex(start),hex(size)],True)
            assert len(bodies)==size
            for number,body in zip(range(start,start+size),bodies):
                expected=record(number)
                payload=expected['new_payload'][0]
                assert body and body.get('blockAccessList')==payload['blockAccessList'], f'Missing/different BAL at {number}'
                assert body['transactions']==payload['transactions'], f'Payload transactions differ at {number}'
                assert body['withdrawals']==payload['withdrawals']
                count+=1;bal_bytes+=(len(payload['blockAccessList'])-2)//2
                transactions+=expected['transactions'];gas+=expected['gas_used']
                if plan.get('version')==2 and expected['index']>=plan['v2']['qualifying_start_index']:
                    v=plan['v2'];assert expected.get('qualifying')
                    assert abs(expected['execution_gas']-v['target_execution_gas'])<=v['dimension_tolerance']
                    assert abs(expected['state_gas']-v['target_state_gas'])<=v['dimension_tolerance']
                    assert expected['gas_used']==max(expected['execution_gas'],expected['state_gas'])
                    assert expected['bal_bytes']>=v['minimum_bal_bytes']
                    qualifying+=1;execution_sum+=expected['execution_gas'];state_sum+=expected['state_gas']
                    bal_min=min(bal_min or expected['bal_bytes'],expected['bal_bytes'])
            if count%1008==0:
                print(f'BAL bodies verified: {count}/{target-ANCHOR}',flush=True)
        before=json.loads((ROOT/f'audit-{a.workload_blocks}-before.json').read_text())
        assert before['samples']==samples, 'State samples changed after restart'
    report={'head':head,'samples':samples,'verified_bal_bodies':count,'bal_bytes':bal_bytes,
            'transactions':transactions,'gas_used':gas,'time':time.time(),'qualifying_blocks':qualifying,
            'qualifying_execution_gas':execution_sum,'qualifying_state_gas':state_sum,'minimum_qualifying_bal_bytes':bal_min}
    save(ROOT/f'audit-{a.workload_blocks}-{a.phase}.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('head','samples')}),flush=True)


if __name__=='__main__':main()
