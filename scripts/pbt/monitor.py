#!/usr/bin/env python3
"""Read-only PBT-1 progress checks; intended to run every 15 minutes."""
import argparse
import concurrent.futures
import datetime
import json
from pathlib import Path
import subprocess
import time

HOSTS = {
    'erigon': ('164.92.239.96', 4118),
    'geth': ('46.101.230.44', 14060),
    'besu': ('138.68.76.218', 14211),
    'nethermind': ('167.172.188.11', 19755),
}
REMOTE = r'''
import glob,json,os,subprocess,sys,time
from pathlib import Path
client=sys.argv[1]
root=Path('/data/pbt-1')
def cmd(*args):
    return subprocess.run(args,capture_output=True,text=True,timeout=20)
r=cmd('docker','inspect','pbt-1-'+client+'-snapshot')
if r.returncode: raise RuntimeError('snapshot container unavailable: '+r.stderr.strip())
state=json.loads(r.stdout)[0]['State']
counts=[int(Path(p).read_text()) for p in glob.glob(str(root/'snapshot-fetcher/tmp/*/emitted'))]
v=os.statvfs(root)
r=cmd('du','-s','-B1',str(root/client))
result={'time':int(time.time()),'container':state['Status'],'exit_code':state['ExitCode'],
        'oom':state['OOMKilled'],'started_at':state['StartedAt'],
        'finished_at':state['FinishedAt'],'done':(root/'snapshot-fetcher/done').is_file(),
        'emitted':max(counts,default=0),'free_bytes':v.f_bavail*v.f_frsize,
        'data_bytes':int(r.stdout.split()[0]) if r.returncode==0 else None}
if client=='nethermind':
    result['cleanup_service']=cmd('systemctl','is-active','pbt-1-nethermind-flatdb-cleanup').stdout.strip()
    p=root/'nethermind-flatdb-cleanup/complete.json'
    result['cleanup_complete']=json.loads(p.read_text()) if p.is_file() else None
    result['cleanup_phases']=[p.name for p in (root/'nethermind-flatdb-cleanup').glob('*.json')]
# A future producer/replay/upload runner can publish explicit phase progress here.
p=root/'pipeline/status.json'
result['pipeline']=json.loads(p.read_text()) if p.is_file() else None
r=cmd('docker','inspect','pbt-1-'+client+'-execution')
result['execution']=json.loads(r.stdout)[0]['State'] if r.returncode==0 else None
r=cmd('systemctl','show','pbt-1-full-run','-p','ActiveState','-p','Result')
result['full_run_service']=dict(line.split('=',1) for line in r.stdout.splitlines() if '=' in line)
p=result.get('pipeline') or {}
if p.get('phase') in ('generating','replaying','waiting_for_payload') and p.get('head',0)>=24453559:
    try:
        probe=subprocess.run(['nsenter','--target',str(result['execution']['Pid']),'--net',
                              'python3','/data/pbt-1/bal-sentinel.py'],
                             capture_output=True,text=True,timeout=55)
        if probe.returncode:raise RuntimeError(probe.stderr[-500:])
        result['bal_retention_probe']=json.loads(probe.stdout)
    except Exception as exc:
        result['bal_retention_probe']={'error':str(exc)}
print(json.dumps(result))
'''


def check(client, identity):
    host, chunks = HOSTS[client]
    result = subprocess.run(
        ['ssh', '-i', identity, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
         '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=2',
         f'root@{host}', 'python3', '-', client],
        input=REMOTE, capture_output=True, text=True, timeout=75,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-500:] or 'remote check failed')
    record = json.loads(result.stdout)
    record.update(host=host, total_chunks=chunks)
    record['restore_complete'] = record['done'] and record['container']=='exited' and record['exit_code']==0
    record['progress_percent'] = 100.0 if record['restore_complete'] else round(100*record['emitted']/chunks, 1)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--identity', default=str(Path.home()/'.ssh/devops_eth2_shared_key'))
    parser.add_argument('--output', type=Path, default=Path.home()/'.local/state/pbt-1-monitor')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    latest = args.output/'latest.json'
    previous = json.loads(latest.read_text()) if latest.exists() else {}
    now = time.time()
    report = {'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'epoch':now,'clients':{},'alerts':[],'events':[]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(check,c,args.identity):c for c in HOSTS}
        for job in concurrent.futures.as_completed(jobs):
            client = jobs[job]
            old = previous.get('clients',{}).get(client,{})
            try:
                r = job.result()
            except Exception as exc:
                r = {'error':str(exc)}
                report['alerts'].append(f'{client}: {exc}')
                report['clients'][client] = r
                continue
            report['clients'][client] = r
            if r['oom'] or (r['container']=='exited' and not r['restore_complete']):
                report['alerts'].append(f'{client}: restore failed/incomplete; exit={r["exit_code"]}, OOM={r["oom"]}')
            if r['free_bytes'] < 100_000_000_000:
                report['alerts'].append(f'{client}: free disk below 100 GB')
            if r['container']=='running' and old.get('container')=='running':
                delta=r['emitted']-old.get('emitted',0)
                elapsed=now-previous.get('epoch',now)
                if delta <= 0 and elapsed >= 600:
                    report['alerts'].append(f'{client}: no extraction progress since previous check')
                elif delta > 0 and elapsed > 0:
                    r['eta_seconds']=round((r['total_chunks']-r['emitted'])*elapsed/delta)
            if r['restore_complete'] and not old.get('restore_complete'):
                report['events'].append(f'{client}: restore complete')
            pipeline = r.get('pipeline') or {}
            if r.get('full_run_service',{}).get('ActiveState')=='failed':
                report['alerts'].append(f'{client}: full-run service failed; inspect journal')
            if 'error' in r.get('bal_retention_probe',{}):
                report['alerts'].append(f'{client}: BAL retention probe failed: '+r['bal_retention_probe']['error'])
            if pipeline.get('phase') == 'failed':
                report['alerts'].append(f'{client}: pipeline failed: {pipeline.get("error", "inspect logs")}')
            if pipeline.get('phase') in ('generating','replaying','uploading','awaiting_upload_verification') and now-pipeline.get('time',now) > 900:
                report['alerts'].append(f'{client}: pipeline progress is over 15 minutes old')
            execution=r.get('execution') or {}
            if execution.get('OOMKilled'):
                report['alerts'].append(f'{client}: execution container was OOM-killed')
            allowed_stopped=('validated_stopped','uploading','awaiting_upload_verification','snapshot_uploaded_verified','failed','restart_validation')
            if execution and not execution.get('Running') and pipeline.get('phase') not in allowed_stopped:
                report['alerts'].append(f'{client}: execution container unexpectedly stopped; exit={execution.get("ExitCode")}')
            if client=='nethermind':
                if r['cleanup_service']=='failed':
                    report['alerts'].append('nethermind: FlatDB cleanup service failed; inspect phase logs')
                if r['cleanup_complete'] and not old.get('cleanup_complete'):
                    report['events'].append('nethermind: Patricia cleanup and FlatDB restart verification complete')
                if r['restore_complete'] and not r['cleanup_complete'] and r['cleanup_service'] not in ('active','activating'):
                    report['alerts'].append('nethermind: restore complete but cleanup has not completed and is not running')
    tmp=args.output/'latest.json.tmp'
    controller=Path.home()/'.local/state/pbt-1-run/advance-status.json'
    if controller.is_file():
        workflow=json.loads(controller.read_text())
        report['workflow']=workflow
        report['alerts'].extend('workflow: '+error for error in workflow.get('errors',[]))
        if now-workflow.get('time',0)>180:
            report['alerts'].append('workflow: coordinator status is over three minutes old')
    active_replay=any((r.get('pipeline') or {}).get('phase') in
                      ('generating','replaying','waiting_for_payload') for r in report['clients'].values())
    relay=controller.parent/'relay-status.json'
    if active_replay:
        if not relay.is_file():
            report['alerts'].append('relay: no successful transfer report')
        elif now-json.loads(relay.read_text()).get('time',0)>900:
            report['alerts'].append('relay: no successful transfer in 15 minutes')
    tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(latest)
    with (args.output/'history.jsonl').open('a') as out:
        out.write(json.dumps(report)+'\n')
    lines=[f'# PBT-1 progress — {report["checked_at"]}', '',
           '| Client | Restore | Extracted GiB | Free GiB | Cleanup | Pipeline |',
           '| --- | --- | ---: | ---: | --- | --- |']
    for client in HOSTS:
        r=report['clients'][client]
        if 'error' in r:
            lines.append(f'| {client} | CHECK FAILED | — | — | — | — |');continue
        cleanup='—'
        if client=='nethermind':cleanup='verified complete' if r['cleanup_complete'] else r['cleanup_service']
        p=r.get('pipeline') or {}
        phase=p.get('phase','not started')
        if 'head' in p:phase+=f' at {p["head"]:,}'
        if p.get('qualifying_blocks') is not None:phase+=f'; {p["qualifying_blocks"]:,} qualifying'
        data_gib=f'{r["data_bytes"]/2**30:.1f}' if r['data_bytes'] is not None else '—'
        lines.append(f'| {client} | {r["progress_percent"]}% ({r["container"]}) | {data_gib} | {r["free_bytes"]/2**30:.1f} | {cleanup} | {phase} |')
    lines += ['', 'Alerts: ' + ('; '.join(report['alerts']) or 'none'),
              'Events: ' + ('; '.join(report['events']) or 'none'), '',
              'Pipeline stages are reported separately; generation/replay completion does not establish snapshot upload completion.']
    (args.output/'status.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines),flush=True)
    # An alert is recorded as a failed check in systemd, but the timer keeps running.
    raise SystemExit(1 if report['alerts'] else 0)


if __name__=='__main__':
    main()
