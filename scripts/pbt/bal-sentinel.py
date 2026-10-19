#!/usr/bin/env python3
"""Read-only spot checks of the oldest and recent generated BALs during replay."""
import gzip
import json
import time
from pipeline_rpc import ANCHOR, ROOT, RPC


def main():
    plan=json.loads((ROOT/'workload.json').read_text())
    status=json.loads((ROOT/'status.json').read_text())
    head=status['head']
    first=ANCHOR+plan['v2']['qualifying_start_index']+1
    rpc=RPC();samples=[]
    for number in sorted({ANCHOR+1,first,max(first,head-64)}):
        if number>head:continue
        expected=json.loads(gzip.decompress((ROOT/'blocks'/f'{number:08d}.json.gz').read_bytes()))
        payload=expected['new_payload'][0]
        bodies=rpc.call('engine_getPayloadBodiesByRangeV2',[hex(number),'0x1'],True)
        assert len(bodies)==1 and bodies[0],f'Missing body at {number}'
        for field in ('blockAccessList','transactions','withdrawals'):
            assert bodies[0].get(field)==payload[field],f'{field} differs at {number}'
        samples.append({'number':number,'bal_bytes':(len(payload['blockAccessList'])-2)//2})
    print(json.dumps({'time':time.time(),'head':head,'samples':samples,'verified':True}))


if __name__=='__main__':main()
