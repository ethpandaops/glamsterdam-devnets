#!/usr/bin/env python3
"""Measure batched fork choice while requiring VALID for every input payload."""
import fcntl
import gzip
import json
import subprocess
import sys
import time
from pipeline_rpc import ROOT, RPC, save

NAME = 'pbt-1-erigon-execution'
REPORT = ROOT/'batch-wait-probe.json'


def load(number):
    return json.loads(gzip.decompress((ROOT/'blocks'/f'{number:08d}.json.gz').read_bytes()))


def verify(rpc, records):
    start = time.monotonic()
    for record in records:
        header = rpc.call('eth_getBlockByNumber', [hex(record['number']), False])
        for key, source in [('hash','hash'), ('stateRoot','state_root'), ('blockAccessListHash','bal_hash')]:
            assert header[key] == record[source], (record['number'], key)
    header_seconds = time.monotonic()-start
    for offset in range(0, len(records), 16):
        group = records[offset:offset+16]
        bodies = rpc.call('engine_getPayloadBodiesByRangeV2', [hex(group[0]['number']), hex(len(group))], True)
        assert len(bodies) == len(group)
        for body, record in zip(bodies, group):
            for key in ('blockAccessList','transactions','withdrawals'):
                assert body and body[key] == record['new_payload'][0][key], (record['number'], key)
    return {'verified_headers': len(records), 'verified_bal_bodies': len(records),
            'header_seconds': header_seconds, 'total_audit_seconds': time.monotonic()-start}


def probe():
    lock=(ROOT/'replay.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not REPORT.exists(), 'Existing probe requires inspection'
    rpc=RPC();head=rpc.head();number=int(head['number'],16)
    expected=load(number)
    assert all(head[k]==expected[v] for k,v in [('hash','hash'),('stateRoot','state_root'),('blockAccessListHash','bal_hash')])
    result={'started_at':time.time(),'initial_head':number,'cases':[],
            'durability':'unchanged','payloads_unchanged':True,
            'forkchoice_schedule':'Each payload VALID; forkchoice only at the end of each batch'}
    save(ROOT/'status.json',{'phase':'replay_batch_probe','time':time.time(),'head':number})
    for count,batched in [(8,False),(16,True),(32,True)]:
        records=[load(n) for n in range(number+1,number+count+1)]
        assert records[0]['new_payload'][0]['parentHash']==head['hash']
        for prior,current in zip(records,records[1:]):
            assert current['new_payload'][0]['parentHash']==prior['hash']
        case={'blocks':count,'batched':batched,'first':number+1,'events':[]}
        result['cases'].append(case);start=time.monotonic()
        if not batched:
            for record in records:head=rpc.apply(record)
        else:
            for record in records:
                deadline=time.monotonic()+180;attempts=0;pending=[]
                while True:
                    response=rpc.call('engine_newPayloadV5',record['new_payload'],True);attempts+=1
                    if response['status']=='VALID':
                        assert response['latestValidHash']==record['hash'],response
                        break
                    assert response['status'] in ('SYNCING','ACCEPTED'),response
                    pending.append(response['status'])
                    save(REPORT,result)
                    assert time.monotonic()<deadline, ('Payload did not become VALID without an intermediate forkchoice',record['number'],response)
                    time.sleep(.1)
                case['events'].append({'number':record['number'],'status':'VALID','attempts':attempts,'pending':pending})
            # apply rechecks the last payload, advances forkchoice and waits for
            # the canonical RPC view, validating all final commitments.
            head=rpc.apply(records[-1])
        case['apply_seconds']=time.monotonic()-start
        case['apply_blocks_per_second']=count/case['apply_seconds']
        case.update(verify(rpc,records));case['head']=records[-1]['number']
        number=case['head'];save(REPORT,result)
        save(ROOT/'status.json',{'phase':'replay_batch_probe','time':time.time(),'head':number})
        print(json.dumps({k:v for k,v in case.items() if k!='events'}),flush=True)
    result.update(finished_at=time.time(),head=number,head_hash=head['hash'],
                  state_root=head['stateRoot'],bal_hash=head['blockAccessListHash'],
                  all_headers_and_bodies_verified=True)
    save(REPORT,result)


def host():
    assert not REPORT.exists(), 'Existing probe requires inspection'
    state=json.loads(subprocess.check_output(['docker','inspect',NAME]))[0]
    assert state['State']['Running'] and not state['State']['OOMKilled']
    assert not any('MDBX_NO_FSYNC' in x for x in state['Config']['Env'])
    subprocess.run(['systemctl','stop','pbt-1-full-run'],check=True)
    subprocess.run(['nsenter','--target',str(state['State']['Pid']),'--net','python3','-u',__file__],check=True)
    result=json.loads(REPORT.read_text());assert result['all_headers_and_bodies_verified']
    save(ROOT/'status.json',{'phase':'replaying','time':time.time(),'head':result['head'],
                            'target_head':24503958,'qualifying_blocks':result['head']-24453558})
    subprocess.run(['systemd-run','--unit=pbt-1-full-run','--property=Type=exec','nsenter',
                    '--target',str(state['State']['Pid']),'--net','python3','-u','/data/pbt-1/replay.py',
                    '--workload-blocks','51417'],check=True)


if __name__=='__main__':
    try:
        if '--host' in sys.argv:host()
        else:probe()
    except Exception as exc:
        save(ROOT/'status.json',{'phase':'failed','time':time.time(),'error':str(exc)})
        raise
