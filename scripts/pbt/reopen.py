#!/usr/bin/env python3
"""Clean shutdown/reopen gate; run on a source host after its replay is complete."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import time
from pipeline_rpc import ROOT, save


def run(*args):return subprocess.check_output(args,text=True).strip()


def state(name):return json.loads(run('docker','inspect',name))[0]['State']


def stop(name, log):
    if '-erigon-' in name:
        from erigon_idle import wait_for_idle
        wait_for_idle(name,log.with_suffix('.merge-wait.json'))
    run('docker','stop','--time=1800',name)
    s=state(name)
    with log.open('w') as out:
        subprocess.run(['docker','logs',name],stdout=out,stderr=subprocess.STDOUT,check=True)
    allowed=(0,143) if '-besu-' in name else (0,130)
    assert not s['Running'] and not s['OOMKilled'] and s['ExitCode'] in allowed,s
    if s['ExitCode']==143:
        assert 'BesuCommand-Shutdown-Hook' in log.read_text(), 'Missing Besu graceful shutdown hook'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('client',choices=['geth','besu','erigon','nethermind'])
    p.add_argument('--workload-blocks',type=int,required=True)
    p.add_argument('--stop-after',action='store_true')
    a=p.parse_args();name=f'pbt-1-{a.client}-execution'
    lock=(ROOT/'reopen.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    status=json.loads((ROOT/'status.json').read_text())
    assert status['phase'] in ('generation_complete','replay_complete'),status
    assert status['workload_blocks']==a.workload_blocks,status
    def audit(phase):
        subprocess.run(['nsenter','--target',str(state(name)['Pid']),'--net','python3','-u',
                        '/data/pbt-1/audit.py','--workload-blocks',str(a.workload_blocks),'--phase',phase],check=True)
    audit('before')
    save(ROOT/'status.json',{'phase':'restart_validation','time':time.time(),'workload_blocks':a.workload_blocks})
    stop(name,ROOT/f'reopen-{a.workload_blocks}-before.log')
    run('docker','start',name)
    deadline=time.monotonic()+1800
    while True:
        s=state(name);assert s['Running'],s
        ready=subprocess.run(['nsenter','--target',str(s['Pid']),'--net','curl','-fsS','--max-time','10',
              '-H','Content-Type: application/json','--data',
              '{"jsonrpc":"2.0","id":1,"method":"eth_blockNumber","params":[]}',
              'http://127.0.0.1:18545'],capture_output=True,text=True)
        if ready.returncode==0 and json.loads(ready.stdout).get('result'):break
        assert time.monotonic()<deadline,'RPC startup timeout';time.sleep(5)
    audit('after')
    if a.stop_after:stop(name,ROOT/f'reopen-{a.workload_blocks}-after.log')
    result=json.loads((ROOT/f'audit-{a.workload_blocks}-after.json').read_text())
    result.update(client=a.client,stopped=a.stop_after,image=json.loads(run('docker','inspect',name))[0]['Config']['Image'])
    save(ROOT/f'reopen-{a.workload_blocks}-complete.json',result)
    save(ROOT/'status.json',{'phase':'validated_stopped' if a.stop_after else 'pilot_validated',
                           'time':time.time(),'head':int(result['head']['number'],16),
                           'workload_blocks':a.workload_blocks,'bal_bodies':result['verified_bal_bodies'],
                           'qualifying_blocks':result.get('qualifying_blocks',0)})
    print(f'{a.client}: restart and {result["verified_bal_bodies"]} BAL bodies verified',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        save(ROOT/'status.json',{'phase':'failed','time':time.time(),'error':str(exc)});raise
