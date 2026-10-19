#!/usr/bin/env python3
"""Advance the overnight workflow only when the preceding evidence gate passed.

The timer never automatically retries failed database operations. Failures are
recorded for operator inspection while other independent clients may progress.
"""
import concurrent.futures
import fcntl
import json
from pathlib import Path
import shlex
import subprocess
import time
from monitor import HOSTS

REPO=Path(__file__).resolve().parents[2]
ROOT=Path.home()/'.local/state/pbt-1-run'
IDENTITY=str(Path.home()/'.ssh/devops_eth2_shared_key')


def command(args):
    return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT,timeout=60).strip()


def ssh(c,args):
    return command(['ssh','-i',IDENTITY,'-o','BatchMode=yes','-o','ConnectTimeout=15',
                    'root@'+HOSTS[c][0],shlex.join(args)])


def remote_state(c):
    text=ssh(c,['python3','-c',"import json;from pathlib import Path;p=Path('/data/pbt-1/pipeline/status.json');print(p.read_text() if p.exists() else '{}')"])
    return json.loads(text)


def start(c,unit,args,local=False):
    # A failed unit remains available for inspection; do not reset/retry it.
    show=['systemctl',*(['--user'] if local else []),'show',unit,'-p','LoadState','-p','ActiveState','-p','Result']
    output=command(show) if local else ssh(c,show)
    fields=dict(line.split('=',1) for line in output.splitlines() if '=' in line)
    if fields.get('LoadState')=='loaded':
        if fields.get('ActiveState')=='failed':raise RuntimeError(f'{unit} failed; inspect journal')
        return
    run=['systemd-run',*(['--user'] if local else []),'--unit='+unit,'--property=Type=exec']
    if local:run+=['--property=EnvironmentFile='+str(ROOT/'storage.env')]
    run+=args
    print(command(run) if local else ssh(c,run),flush=True)


def advance(c,status,full):
    plan=json.loads((ROOT/'workload.json').read_text())['v2']
    pilot=plan['pilot_records']-3;final=plan['final_records']-3
    phase=status.get('phase')
    if phase=='failed':raise RuntimeError(status.get('error','remote pipeline failed'))
    if phase in ('generation_complete','replay_complete'):
        n=status['workload_blocks']
        if n not in (pilot,final):return  # A calibration/setup run, not a gate.
        if c=='geth' and n==final:
            # Raw export needs the live source RPC. Preserve it until all requested
            # blocks are exported; a failed export needs operator inspection.
            raw=json.loads(ssh(c,['python3','-c',"import json;from pathlib import Path;p=Path('/data/pbt-1/raw-stream');print(json.dumps({'present':p.exists(),'complete':json.loads((p/'complete.json').read_text()) if (p/'complete.json').exists() else None,'status':json.loads((p/'status.json').read_text()) if (p/'status.json').exists() else {}}))"]))
            if raw['present']:
                if raw['status'].get('phase')=='failed':raise RuntimeError('Raw block export failed; inspect before Geth shutdown')
                if raw['complete'] is None:return
                assert raw['complete']['end']==status['head'] and raw['complete']['phase']=='complete'
        start(c,f'pbt-1-reopen-{n}', ['python3','-u','/data/pbt-1/reopen.py',c,'--workload-blocks',str(n)]
              +(['--stop-after'] if n==final else []))
    elif phase=='pilot_validated' and full:
        pid=ssh(c,['docker','inspect','-f','{{.State.Pid}}',f'pbt-1-{c}-execution'])
        assert pid!='0'
        python='/data/pbt-1/venv/bin/python' if c=='geth' else 'python3'
        script='generate.py' if c=='geth' else 'replay.py'
        start(c,'pbt-1-full-run',['nsenter','--target',pid,'--net',python,'-u','/data/pbt-1/'+script,'--workload-blocks',str(final)])
    elif phase=='validated_stopped':
        if (ROOT/f'upload-{c}-authorized.json').exists():
            start(c,'pbt-1-upload',['python3','-u','/data/pbt-1/upload.py'])
        else:
            start(c,f'pbt-1-authorize-upload-{c}',[str(ROOT/'venv/bin/python'),str(REPO/'scripts/pbt/prepare-upload.py'),c],local=True)
    elif phase=='awaiting_upload_verification':
        start(c,f'pbt-1-verify-upload-{c}',[str(ROOT/'venv/bin/python'),'-u',str(REPO/'scripts/pbt/finish-upload.py'),c],local=True)


def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    lock=(ROOT/'advance.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    states={};errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(remote_state,c):c for c in HOSTS}
        for job in concurrent.futures.as_completed(jobs):
            c=jobs[job]
            try:states[c]=job.result()
            except Exception as e:errors.append(f'{c}: {e}')
    approved=ROOT/'full-run-gate.json'
    plan=json.loads((ROOT/'workload.json').read_text())['v2']
    if not approved.exists() and len(states)==4 and all(s.get('phase')=='pilot_validated' and s.get('qualifying_blocks')==1000 for s in states.values()):
        assert all(s['workload_blocks']==plan['pilot_records']-3 and s['bal_bodies']==plan['pilot_records'] for s in states.values())
        # Reopen audit itself verifies each head against the same immutable bundle.
        approved.write_text(json.dumps({'time':time.time(),'pilot':states},indent=2)+'\n')
        print('All four pilot restart/BAL gates passed; full 50,400-block run enabled',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(advance,c,s,approved.exists()):c for c,s in states.items()}
        for job in concurrent.futures.as_completed(jobs):
            c=jobs[job]
            try:job.result()
            except Exception as e:errors.append(f'{c}: {e}')
    if not (ROOT/'delivery-complete.json').exists() and all((ROOT/f'published-{c}.json').exists() for c in HOSTS):
        try:
            start('geth','pbt-1-publish-bundle',[str(ROOT/'venv/bin/python'),'-u',str(REPO/'scripts/pbt/publish-bundle.py')],local=True)
        except Exception as e:errors.append(f'bundle: {e}')
    result={'time':time.time(),'full_run_enabled':approved.exists(),'clients':states,'errors':errors}
    tmp=ROOT/'advance-status.json.tmp';tmp.write_text(json.dumps(result,indent=2)+'\n');tmp.replace(ROOT/'advance-status.json')
    for error in errors:print(error,flush=True)
    raise SystemExit(1 if errors else 0)


if __name__=='__main__':main()
