#!/usr/bin/env python3
"""Checkpoint and restart the bounded Erigon preparation run without maintenance."""
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from pipeline_rpc import ANCHOR, ROOT, RPC, save

NAME='pbt-1-erigon-execution'
BACKUP=NAME+'-before-maintenance-suppression'
DATA=Path('/data/pbt-1/erigon')
CHECKPOINT=Path('/data/pbt-1/checkpoints/erigon-before-maintenance-suppression')
FLAGS=['--exec.no-background-maintenance=true','--exec.no-prune=true']
IMMUTABLE={'.kv','.ef','.seg','.v','.kvi','.vi','.efi','.bt','.kvei','.idx'}


def run(*args):
    return subprocess.check_output(args,text=True).strip()


def inspect():
    return json.loads(run('docker','inspect',NAME))[0]


def audit(destination):
    rpc=RPC();head=rpc.head();number=int(head['number'],16)
    samples=[]
    for n in sorted({ANCHOR+1,ANCHOR+1021,number-64,number}):
        record=json.loads(gzip.decompress((ROOT/'blocks'/f'{n:08d}.json.gz').read_bytes()))
        block=rpc.call('eth_getBlockByNumber',[hex(n),False])
        for k,v in [('hash','hash'),('stateRoot','state_root'),('blockAccessListHash','bal_hash')]:
            assert block[k]==record[v],(n,k)
        bodies=rpc.call('engine_getPayloadBodiesByRangeV2',[hex(n),'0x1'],True)
        assert len(bodies)==1 and bodies[0]
        for field in ('blockAccessList','transactions','withdrawals'):
            assert bodies[0][field]==record['new_payload'][0][field],(n,field)
        samples.append({'number':n,'hash':block['hash'],'state_root':block['stateRoot'],
                        'bal_hash':block['blockAccessListHash']})
    assert rpc.head()['hash']==head['hash'],'Head changed during quiescent audit'
    save(destination,{'time':time.time(),'head':head,'samples':samples})


def audit_container(destination):
    pid=inspect()['State']['Pid'];assert pid>0
    subprocess.run(['nsenter','--target',str(pid),'--net','python3','-u',__file__,
                    '--audit',str(destination)],check=True)
    return json.loads(destination.read_text())


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def checkpoint():
    assert not CHECKPOINT.exists(),'Checkpoint already exists; inspect prior attempt'
    assert shutil.disk_usage(DATA).free>300*1024**3
    CHECKPOINT.mkdir(parents=True)
    linked=0;copied=0;files=0
    subprocess.run(['docker','pause',NAME],check=True)
    try:
        subprocess.run(['sync','-f',str(DATA/'chaindata/mdbx.dat')],check=True)
        for directory,dirs,names in os.walk(DATA):
            rel=Path(directory).relative_to(DATA)
            if rel==Path('.'):
                dirs[:]=[d for d in dirs if d not in ('temp','logs')]
            target_dir=CHECKPOINT/rel;target_dir.mkdir(exist_ok=True)
            for name in names:
                if name in ('LOCK','mdbx.lck') or name.endswith('.lock') or '.tmp' in name:continue
                source=Path(directory)/name;target=target_dir/name
                assert not source.is_symlink() and source.is_file(),source
                size=source.stat().st_size
                if rel.parts and rel.parts[0]=='snapshots' and source.suffix in IMMUTABLE:
                    os.link(source,target);linked+=size
                else:
                    shutil.copy2(source,target);copied+=size
                    assert source.stat().st_ino!=target.stat().st_ino,source
                assert target.stat().st_size==size
                files+=1
        original=digest(DATA/'chaindata/mdbx.dat')
        assert digest(CHECKPOINT/'chaindata/mdbx.dat')==original
        subprocess.run(['sync','-f',str(CHECKPOINT/'chaindata/mdbx.dat')],check=True)
        result={'time':time.time(),'path':str(CHECKPOINT),'files':files,'linked_immutable_bytes':linked,
                'copied_mutable_bytes':copied,'chaindata_sha256':original,
                'container_paused_during_copy':True}
        save(ROOT/'maintenance-checkpoint.json',result)
    finally:
        subprocess.run(['docker','unpause',NAME],check=True)
    return result


def main():
    lock=(ROOT/'maintenance-restart.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    initial=inspect();assert initial['State']['Running'] and not initial['State']['OOMKilled']
    assert initial['HostConfig']['NetworkMode']=='none'
    assert not (ROOT/'maintenance-restart-complete.json').exists()
    assert subprocess.run(['docker','inspect',BACKUP],capture_output=True).returncode!=0
    command=json.loads((ROOT/'client-command.json').read_text())
    image=initial['Config']['Image'];at=command.index(image)
    assert command[:3]==['docker','run','-d'] and command[at+1:]==initial['Config']['Cmd']
    assert all(flag not in command for flag in FLAGS)
    subprocess.run(['systemctl','stop','pbt-1-full-run.service'],check=True)
    save(ROOT/'status.json',{'phase':'restart_validation','time':time.time(),
                           'reason':'Checkpoint and suppress background maintenance'})
    time.sleep(5)
    before=audit_container(ROOT/'maintenance-restart-before.json')
    head=int(before['head']['number'],16)
    backup=checkpoint()
    subprocess.run(['/data/pbt-1/erigon-bal-backfill','--db',str(CHECKPOINT/'chaindata'),
                    '--records',str(ROOT/'blocks'),'--start',str(head),'--end',str(head),'--dry-run',
                    '--report',str(ROOT/'maintenance-checkpoint-native.json')],check=True)
    native=json.loads((ROOT/'maintenance-checkpoint-native.json').read_text())
    assert native['head']==head and native['head_hash']==before['head']['hash']
    assert native['state_root']==before['head']['stateRoot']
    assert audit_container(ROOT/'maintenance-restart-checkpoint-audit.json')['head']==before['head']
    print('Recoverable checkpoint verified; requesting normal shutdown',flush=True)
    subprocess.run(['docker','kill','--signal=TERM',NAME],check=True)
    deadline=time.monotonic()+180
    while inspect()['State']['Running'] and time.monotonic()<deadline:time.sleep(2)
    forced=False
    if inspect()['State']['Running']:
        forced=True
        print('Normal shutdown stalled; using SIGQUIT after verified checkpoint',flush=True)
        subprocess.run(['docker','kill','--signal=QUIT',NAME],check=True)
        deadline=time.monotonic()+60
        while inspect()['State']['Running'] and time.monotonic()<deadline:time.sleep(1)
    stopped=inspect()['State']
    assert not stopped['Running'] and not stopped['OOMKilled'],stopped
    assert stopped['ExitCode'] in ((0,130,2,131) if forced else (0,130)),stopped
    with (ROOT/'maintenance-restart-shutdown.log').open('w') as stream:
        subprocess.run(['docker','logs',NAME],stdout=stream,stderr=subprocess.STDOUT,check=True)
    save(ROOT/'maintenance-restart-shutdown.json',{'time':time.time(),'forced_sigquit':forced,'state':stopped})
    save(ROOT/'client-command-before-maintenance-suppression.json',command)
    subprocess.run(['docker','rename',NAME,BACKUP],check=True)
    updated=command+FLAGS
    subprocess.run(updated,check=True)
    save(ROOT/'client-command.json',updated)
    current=inspect()
    assert current['Config']['Image']==image and current['Config']['Cmd']==initial['Config']['Cmd']+FLAGS
    for field in ('Binds','Memory','MemorySwap','NetworkMode'):
        assert current['HostConfig'][field]==initial['HostConfig'][field],field
    deadline=time.monotonic()+1800
    while True:
        state=inspect()['State'];assert state['Running'],state
        ready=subprocess.run(['nsenter','--target',str(state['Pid']),'--net','curl','-fsS','--max-time','10',
            '-H','Content-Type: application/json','--data',
            '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}',
            'http://127.0.0.1:18545'],capture_output=True,text=True)
        if ready.returncode==0 and json.loads(ready.stdout).get('result'):break
        assert time.monotonic()<deadline,'RPC startup timeout';time.sleep(5)
    after=audit_container(ROOT/'maintenance-restart-after.json')
    assert after['head']==before['head'] and after['samples']==before['samples']
    result={'time':time.time(),'head':head,'head_hash':before['head']['hash'],
            'state_root':before['head']['stateRoot'],'bal_hash':before['head']['blockAccessListHash'],
            'image':image,'flags':FLAGS,'checkpoint':backup,'forced_sigquit':forced,
            'old_pid':initial['State']['Pid'],'new_pid':inspect()['State']['Pid'],
            'same_head_and_sampled_bals_verified':True,'final_clean_restart_still_required':True}
    save(ROOT/'maintenance-restart-complete.json',result)
    final=json.loads((ROOT/'workload.json').read_text())['v2']['final_records']-3
    save(ROOT/'status.json',{'phase':'replaying','time':time.time(),'head':head,
                           'target_head':ANCHOR+final+3,'qualifying_blocks':head-ANCHOR-1020})
    subprocess.run(['systemd-run','--unit=pbt-1-full-run','--property=Type=exec',
                    'nsenter','--target',str(result['new_pid']),'--net','python3','-u',
                    '/data/pbt-1/replay.py','--workload-blocks',str(final)],check=True)
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1]=='--audit':audit(Path(sys.argv[2]))
    else:
        try:main()
        except Exception as exc:
            save(ROOT/'status.json',{'phase':'failed','time':time.time(),'error':str(exc)});raise
