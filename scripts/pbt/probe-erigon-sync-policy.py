#!/usr/bin/env python3
"""Bounded SAFE_NOSYNC pilot, followed by a normal-durability restart gate."""
import fcntl
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
from pipeline_rpc import ANCHOR, ROOT, RPC, save
from reopen import stop

NAME='pbt-1-erigon-execution'
spec=importlib.util.spec_from_file_location('maintenance','/data/pbt-1/suppress-erigon-maintenance.py')
maintenance=importlib.util.module_from_spec(spec);spec.loader.exec_module(maintenance)


def run(*args):return subprocess.check_output(args,text=True).strip()


def inspect():return json.loads(run('docker','inspect',NAME))[0]


def ready():
    deadline=time.monotonic()+1800
    while True:
        state=inspect()['State'];assert state['Running'],state
        r=subprocess.run(['nsenter','--target',str(state['Pid']),'--net','curl','-fsS','--max-time','10',
            '-H','Content-Type: application/json','--data',
            '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}',
            'http://127.0.0.1:18545'],capture_output=True,text=True)
        if r.returncode==0 and json.loads(r.stdout).get('result'):return state['Pid']
        assert time.monotonic()<deadline,'RPC startup timeout';time.sleep(5)


def replace(command,suffix):
    prior=inspect();assert not prior['State']['Running']
    backup=NAME+suffix
    assert subprocess.run(['docker','inspect',backup],capture_output=True).returncode!=0,backup
    subprocess.run(['docker','rename',NAME,backup],check=True)
    subprocess.run(command,check=True)
    save(ROOT/'client-command.json',command)
    current=inspect();assert current['Config']['Image']==prior['Config']['Image']
    for field in ('Binds','Memory','MemorySwap','NetworkMode'):
        assert current['HostConfig'][field]==prior['HostConfig'][field],field
    return ready()


def pilot():
    rpc=RPC();before=rpc.head();first=int(before['number'],16)
    start=time.monotonic();warm=None;count=128;bal_bytes=0
    for offset in range(1,count+1):
        number=first+offset
        record=json.loads(gzip.decompress((ROOT/'blocks'/f'{number:08d}.json.gz').read_bytes()))
        head=rpc.apply(record)
        bodies=rpc.call('engine_getPayloadBodiesByRangeV2',[hex(number),'0x1'],True)
        assert len(bodies)==1 and bodies[0]
        for key in ('blockAccessList','transactions','withdrawals'):
            assert bodies[0][key]==record['new_payload'][0][key],(number,key)
        bal_bytes+=(len(bodies[0]['blockAccessList'])-2)//2
        if offset==8:warm=time.monotonic()
        if offset%16==0:print(f'Sync-policy pilot: {offset}/{count} blocks and BAL bodies verified',flush=True)
    elapsed=time.monotonic()-start;measured=time.monotonic()-warm
    save(ROOT/'sync-policy-v2-pilot-blocks.json',{'time':time.time(),'first':first+1,'head':head,
         'blocks':count,'verified_bal_bodies':count,'bal_bytes':bal_bytes,'seconds':elapsed,
         'warmup_blocks':8,'measured_blocks':120,'measured_seconds':measured,
         'measured_blocks_per_second':120/measured,'includes_body_audit':True})


def main():
    lock=(ROOT/'sync-policy-v2-pilot.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not (ROOT/'sync-policy-v2-pilot-complete.json').exists()
    prior=inspect();assert prior['State']['Running'] and not prior['State']['OOMKilled']
    assert prior['HostConfig']['NetworkMode']=='none'
    command=json.loads((ROOT/'client-command.json').read_text());image=prior['Config']['Image']
    assert command[:3]==['docker','run','-d'] and command[command.index(image)+1:]==prior['Config']['Cmd']
    assert '--exec.no-background-maintenance=true' in command
    assert not any('MDBX_NO_FSYNC' in entry for entry in command)
    binary=Path('/data/pbt-1/erigon-sync-policy-guarded')
    build=json.loads(binary.with_suffix('.json').read_text())
    assert build['mdbx_go_version']=='v0.43.0'
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==build['binary_sha256']
    proof=json.loads((ROOT/'sync-policy-owner-guard-fixture.json').read_text())
    assert proof['host']['returncode']==1 and 'PID namespace' in proof['host']['stderr']
    assert proof['inside']['returncode']==0 and proof['inside']['seconds']>10
    assert proof['owner_exit_code']=='0' and proof['binary_sha256']==build['binary_sha256']
    # Verify the guard in both namespaces before stopping any production work.
    host_check=subprocess.run([str(binary),'--db','/data/pbt-1/erigon/chaindata',
                               '--owner-pid',str(prior['State']['Pid']),'--verify-owner-only'],
                              capture_output=True,text=True,timeout=10)
    assert host_check.returncode==1 and 'PID namespace' in host_check.stderr
    subprocess.run(['docker','cp',str(binary),NAME+':/tmp/pbt-erigon-sync-policy'],check=True)
    owner_check=json.loads(run('docker','exec','--user','0:0',NAME,'/tmp/pbt-erigon-sync-policy',
                               '--db','/data/chaindata','--owner-pid','1','--verify-owner-only'))
    assert owner_check=={'owner_verified':True,'database_opened':False}
    subprocess.run(['systemctl','stop','pbt-1-full-run.service'],check=True)
    save(ROOT/'status.json',{'phase':'restart_validation','time':time.time(),'reason':'Bounded sync-policy pilot'})
    time.sleep(5)
    before=maintenance.audit_container(ROOT/'sync-policy-v2-before.json')
    save(ROOT/'client-command-before-sync-policy-v2.json',command)
    stop(NAME,ROOT/'sync-policy-v2-before-shutdown.log')
    durable=[arg for arg in command if arg!='--exec.no-prune=true']
    trial=durable.copy();index=trial.index(image);trial[index:index]=['-e','MDBX_NO_FSYNC=true']
    pid=replace(trial,'-before-sync-policy-v2-pilot')
    subprocess.run(['docker','cp',str(binary),NAME+':/tmp/pbt-erigon-sync-policy'],check=True)
    policy=json.loads(run('docker','exec','--user','0:0',NAME,'/tmp/pbt-erigon-sync-policy',
                          '--db','/data/chaindata','--owner-pid','1'))
    assert 9.999<=policy['period_seconds']<=10 and policy['threshold_bytes']==256*1024**2
    save(ROOT/'sync-policy-v2-pilot-config.json',policy)
    save(ROOT/'sync-policy-v2-build.json',build)
    opened=maintenance.audit_container(ROOT/'sync-policy-v2-opened.json')
    assert opened['head']==before['head'] and opened['samples']==before['samples']
    subprocess.run(['nsenter','--target',str(pid),'--net','python3','-u',__file__,'--pilot'],check=True)
    blocks=json.loads((ROOT/'sync-policy-v2-pilot-blocks.json').read_text())
    assert blocks['blocks']==blocks['verified_bal_bodies']==128
    save(ROOT/'status.json',{'phase':'restart_validation','time':time.time(),
                           'head':int(blocks['head']['number'],16),'reason':'Verify normal-durability reopen after sync pilot'})
    quiescent=maintenance.audit_container(ROOT/'sync-policy-v2-after-pilot.json')
    assert quiescent['head']==blocks['head']
    # Clean close forces the remaining buffers to disk. Reopen without the
    # delayed-flush environment variable before treating the pilot as passed.
    stop(NAME,ROOT/'sync-policy-v2-pilot-shutdown.log')
    pid=replace(durable,'-before-sync-policy-v2-durability-check')
    assert not any('MDBX_NO_FSYNC' in x for x in inspect()['Config']['Env'])
    after=maintenance.audit_container(ROOT/'sync-policy-v2-durable-reopen.json')
    assert after['head']==quiescent['head'] and after['samples']==quiescent['samples']
    result={'time':time.time(),'before_head':int(before['head']['number'],16),
            'head':int(after['head']['number'],16),'head_hash':after['head']['hash'],
            'state_root':after['head']['stateRoot'],'bal_hash':after['head']['blockAccessListHash'],
            'policy':policy,'pilot':blocks,'normal_durability_reopen_verified':True,
            'pruning_restored_for_replay':True,'delayed_flush_currently_enabled':False,
            'image':image,'new_pid':pid}
    save(ROOT/'sync-policy-v2-pilot-complete.json',result)
    final=json.loads((ROOT/'workload.json').read_text())['v2']['final_records']-3
    save(ROOT/'status.json',{'phase':'replaying','time':time.time(),'head':result['head'],
                           'target_head':ANCHOR+final+3,'qualifying_blocks':result['head']-ANCHOR-1020})
    subprocess.run(['systemd-run','--unit=pbt-1-full-run','--property=Type=exec',
                    'nsenter','--target',str(pid),'--net','python3','-u','/data/pbt-1/replay.py',
                    '--workload-blocks',str(final)],check=True)
    print(json.dumps({'head':result['head'],'measured_blocks_per_second':blocks['measured_blocks_per_second'],
                      'normal_durability_reopen_verified':True,'delayed_flush_currently_enabled':False}),flush=True)


if __name__=='__main__':
    try:
        if '--pilot' in sys.argv:pilot()
        else:main()
    except Exception as exc:
        save(ROOT/'status.json',{'phase':'failed','time':time.time(),'error':str(exc)});raise
