#!/usr/bin/env python3
"""Read-only PBT-1 progress checks; intended to run every 15 minutes."""
import argparse
import concurrent.futures
import datetime
import ipaddress
import json
import math
from pathlib import Path
import shutil
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
if client=='erigon' and (root/'native-source-pilot').exists():
    pilot=root/'native-source-pilot'
    service=cmd('systemctl','show','pbt-1-native-source-pilot','-p','ActiveState','-p','MainPID','-p','Result')
    result['native_source_pilot']={'service':dict(line.split('=',1) for line in service.stdout.splitlines() if '=' in line)}
    for name in ('request','progress','checkpoint'):
        path=pilot/(name+'.json')
        if path.exists():result['native_source_pilot'][name]=json.loads(path.read_text())
    path=pilot/'complete.json'
    if path.exists():
        complete=json.loads(path.read_text())
        result['native_source_pilot']['complete']={key:complete[key] for key in
            ('time','pilot_blocks','speedup','pinned_reopen_verified','continuous_batch_replay_enabled')}
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


def check_probe(host, identity):
    ipaddress.ip_address(host)
    code = r'''
import json,re,subprocess,time
from pathlib import Path
root=Path('/data/pbt-1/io-probe')
p=root/'checkpoint-copy-status.json'
copy=json.loads(p.read_text()) if p.exists() else None
unit=subprocess.check_output(['systemctl','show','pbt-1-checkpoint-copy',
    '-p','ActiveState','-p','MainPID','-p','Result'],text=True,timeout=15)
log=root/'checkpoint-copy.log'
r={'time':time.time(),'copy':copy,
   'service':dict(x.split('=',1) for x in unit.splitlines() if '=' in x)}
native=Path('/data/pbt-1/native')
if native.exists():
    build_unit=subprocess.check_output(['systemctl','show','pbt-1-native-build',
        '-p','ActiveState','-p','MainPID','-p','Result'],text=True,timeout=10)
    r['native_build_service']=dict(x.split('=',1) for x in build_unit.splitlines() if '=' in x)
    build=native/'build-report.json'
    if build.exists():r['native_build']=json.loads(build.read_text())
    batch_unit=subprocess.check_output(['systemctl','show','pbt-1-native-batch-build',
        '-p','ActiveState','-p','MainPID','-p','Result'],text=True,timeout=10)
    r['native_batch_build_service']=dict(x.split('=',1) for x in batch_unit.splitlines() if '=' in x)
    batch_build=native/'batch-build-report.json'
    if batch_build.exists():r['native_batch_build']=json.loads(batch_build.read_text())
    r['native_trials']={}
    for variant in ('stock','profile','profile-no-writemap','profile-batch'):
        trial=native/variant
        job=subprocess.check_output(['systemctl','show','pbt-1-native-probe-'+variant,
            '-p','ActiveState','-p','MainPID','-p','Result'],text=True,timeout=10)
        job_state=dict(x.split('=',1) for x in job.splitlines() if '=' in x)
        if not trial.exists() and job_state.get('ActiveState') not in ('active','failed'):continue
        current={'job':job_state}
        for key in ('status','timing'):
            path=trial/(key+'.json')
            if path.exists():current[key]=json.loads(path.read_text())
        trial_unit=subprocess.check_output(['systemctl','show','pbt-1-native-'+variant,
            '-p','ActiveState','-p','MainPID','-p','Result'],text=True,timeout=10)
        current['service']=dict(x.split('=',1) for x in trial_unit.splitlines() if '=' in x)
        r['native_trials'][variant]=current
if log.exists():
    r['log_bytes']=log.stat().st_size
    r['log_updated_at']=log.stat().st_mtime
    with log.open('rb') as f:
        f.seek(max(0,log.stat().st_size-2048))
        lines=f.read().decode(errors='replace').replace('\r','\n').splitlines()
    r['latest_progress']=lines[-1] if lines else ''
    match=re.match(r'\s*([\d,]+)\s+\d+%',r['latest_progress'])
    if match:r['copied_logical_bytes']=int(match[1].replace(',',''))
print(json.dumps(r))
'''
    result=subprocess.run(['ssh','-i',str(identity),'-o','BatchMode=yes','-o','ConnectTimeout=15',
                           'root@'+host,'python3','-'],input=code,capture_output=True,text=True,timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.strip()[-500:] or 'probe check failed')
    record=json.loads(result.stdout);record['host']=host
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
            if r.get('native_source_pilot',{}).get('service',{}).get('ActiveState')=='failed':
                report['alerts'].append('erigon: original-VM native pilot failed; inspect preserved evidence')
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
    plan_path=controller.parent/'workload.json'
    if plan_path.is_file():
        plan=json.loads(plan_path.read_text())
        files=list((controller.parent/'blocks').glob('*.json.gz'))
        recorded_bytes=sum(p.stat().st_size for p in files)
        remaining=max(0,plan['v2']['final_records']-len(files))
        # Allow 25% above the observed average, plus 10 GiB for logs/metadata.
        # Publication streams its tar/zstd output and needs no second full copy.
        estimated=math.ceil(1.25*recorded_bytes/max(1,len(files))*remaining)
        free=shutil.disk_usage(controller.parent).free
        report['controller_storage']={'free_bytes':free,'replay_bytes':recorded_bytes,
            'replay_records':len(files),'remaining_records':remaining,
            'estimated_additional_bytes':estimated,'reserve_bytes':10*2**30}
        if free<estimated+10*2**30:
            report['alerts'].append('controller: insufficient projected replay-bundle disk headroom')
    if controller.is_file():
        workflow=json.loads(controller.read_text())
        report['workflow']=workflow
        report['alerts'].extend('workflow: '+error for error in workflow.get('errors',[]))
        if now-workflow.get('time',0)>180:
            report['alerts'].append('workflow: coordinator status is over three minutes old')
    probe_path=controller.parent/'erigon-io-probe.json'
    if probe_path.is_file():
        try:
            preparation=controller.parent/'native-probe-preparation.json'
            if preparation.exists() and json.loads(preparation.read_text()).get('phase')=='failed':
                report['alerts'].append('temporary Erigon probe: native preparation failed; inspect controller service')
            probe=check_probe(json.loads(probe_path.read_text())['public_ip'],args.identity)
            report['temporary_probe']=probe
            phase=(probe.get('copy') or {}).get('phase')
            if phase=='failed' or probe['service'].get('ActiveState')=='failed':
                report['alerts'].append('temporary Erigon probe: checkpoint copy failed; inspect preserved evidence')
            if phase in ('copying','verifying') and probe['service'].get('ActiveState')!='active':
                report['alerts'].append('temporary Erigon probe: copy is incomplete and its service is not active')
            if phase=='copying' and now-probe.get('log_updated_at',now)>900:
                report['alerts'].append('temporary Erigon probe: no copy progress output for 15 minutes')
            if probe.get('native_build_service',{}).get('ActiveState')=='failed':
                report['alerts'].append('temporary Erigon probe: native build failed; inspect build logs')
            if probe.get('native_batch_build_service',{}).get('ActiveState')=='failed':
                report['alerts'].append('temporary Erigon probe: native batch build failed; inspect build logs')
            for variant,trial in probe.get('native_trials',{}).items():
                if (trial['service'].get('ActiveState')=='failed' or trial.get('status',{}).get('phase')=='failed'
                        or trial.get('job',{}).get('ActiveState')=='failed'):
                    report['alerts'].append(f'temporary Erigon probe: native {variant} trial failed')
        except Exception as exc:
            report['temporary_probe']={'error':str(exc)}
            report['alerts'].append('temporary Erigon probe: '+str(exc))
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
    if 'controller_storage' in report:
        s=report['controller_storage']
        lines += ['', f'Controller replay storage: {s["replay_bytes"]/2**30:.1f} GiB; '
                  f'{s["free_bytes"]/2**30:.1f} GiB free; estimated additional '
                  f'{s["estimated_additional_bytes"]/2**30:.1f} GiB plus 10 GiB reserve.']
    if 'temporary_probe' in report:
        probe=report['temporary_probe']
        if 'error' not in probe:
            phase=(probe.get('copy') or {}).get('phase','provisioned')
            progress=''
            if 'copied_logical_bytes' in probe:
                progress=(f'{probe["copied_logical_bytes"]/2**30:.1f} / '
                          f'{probe["copy"]["expected_bytes"]/2**30:.1f} GiB logical copy progress.')
            lines += ['', f'Temporary Erigon probe: {phase}; copy service '
                      f'{probe["service"].get("ActiveState", "unknown")}. '
                      f'{progress}']
            if 'native_build_service' in probe:
                built=', '.join(item['name'] for item in probe.get('native_build',{}).get('builds',[])) or 'none yet'
                lines += [f'Native Erigon build: {probe["native_build_service"].get("ActiveState", "unknown")}; binaries built: {built}.']
            for variant,trial in probe.get('native_trials',{}).items():
                lines += [f'Native {variant} trial: {trial.get("status",{}).get("phase", "preparing")}.']
    lines += ['', 'Alerts: ' + ('; '.join(report['alerts']) or 'none'),
              'Events: ' + ('; '.join(report['events']) or 'none'), '',
              'Pipeline stages are reported separately; generation/replay completion does not establish snapshot upload completion.']
    (args.output/'status.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines),flush=True)
    # An alert is recorded as a failed check in systemd, but the timer keeps running.
    raise SystemExit(1 if report['alerts'] else 0)


if __name__=='__main__':
    main()
