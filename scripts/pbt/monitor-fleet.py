#!/usr/bin/env python3
"""Read-only checks of the nine migration workers and recovery downloads."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import time

ROOT = Path.home() / '.local/state/pbt-1-run/fleet'
REMOTE = r'''
import json,pathlib,shutil,subprocess,os,time
root=pathlib.Path('/mnt/pbt-recovery')
status=root/'status.json'
download=json.loads(status.read_text()) if status.exists() else None
extraction=None
if download and download.get('phase')=='extracting':
 for proc in pathlib.Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:
   if (proc/'comm').read_text().strip()!='zstd':continue
   for fd in (proc/'fd').iterdir():
    archive=fd.resolve()
    if archive.parent!=root or not archive.name.endswith('.tar.zst'):continue
    pos=int(next(l.split()[1] for l in (proc/'fdinfo'/fd.name).read_text().splitlines() if l.startswith('pos:')))
    start=float((proc/'stat').read_text().rsplit(')',1)[1].split()[19])/os.sysconf('SC_CLK_TCK')
    elapsed=float(pathlib.Path('/proc/uptime').read_text().split()[0])-start
    size=archive.stat().st_size
    rate=pos/max(elapsed,1)
    extraction={'pid':int(proc.name),'compressed_input_bytes':pos,'archive_bytes':size,
                'input_percent':round(pos*100/size,1),'elapsed_seconds':round(elapsed),
                'average_input_bytes_per_second':round(rate),
                'estimated_input_seconds_remaining':round((size-pos)/max(rate,1))}
  except (OSError,StopIteration,ValueError):continue
service=subprocess.run(['systemctl','show','pbt-recovery-snapshot','-p','ActiveState','-p','Result'],capture_output=True,text=True)
qualification_service=subprocess.run(['systemctl','show','pbt-1-worker-qualification','-p','ActiveState','-p','Result'],capture_output=True,text=True)
exporter_handoff={}
for kind,unit in (('qualification','pbt-1-v3-source-qualification'),('native_client','pbt-1-v3-source-reopen'),
                  ('anchor_preparation','pbt-1-erigon-anchor-preparation'),
                  ('anchor_capture_recovery','pbt-1-anchor-capture-recovery'),
                  ('native_export','pbt-1-native-anchor-export'),
                  ('export_scratch_guard','pbt-1-export-scratch-guard'),
                  ('artifact_upload','pbt-1-pbt-artifact-upload'),
                  ('exporter_recovery_copy','pbt-1-exporter-recovery-copy')):
 result=subprocess.run(['systemctl','show',unit,'-p','LoadState','-p','ActiveState','-p','MainPID','-p','Result','-p','MemoryCurrent','-p','MemoryMax'],capture_output=True,text=True)
 fields=dict(l.split('=',1) for l in result.stdout.splitlines() if '=' in l)
 if fields.get('LoadState')!='not-found':exporter_handoff[kind]=fields
qualification_path=pathlib.Path('/data/pbt-1/qualification/result.json')
qualification=json.loads(qualification_path.read_text()) if qualification_path.exists() else None
head_restore={}
restore_root=pathlib.Path('/data/pbt-1/v3-head-restore')
if restore_root.exists():
 result=subprocess.run(['systemctl','show','pbt-1-v3-head-restore','-p','LoadState','-p','ActiveState',
                        '-p','MainPID','-p','Result'],capture_output=True,text=True)
 head_restore['service']=dict(l.split('=',1) for l in result.stdout.splitlines() if '=' in l)
 head_restore['inputs_staged']=(restore_root/'release-bundle.json').exists()
 for label,relative in (('status','status.json'),('cache','cache/status.json'),('completion','complete.json')):
  path=restore_root/relative
  if path.exists():
   value=json.loads(path.read_text())
   head_restore[label]={k:value[k] for k in ('phase','time','completed_bytes','archive_bytes',
    'bytes_per_second','eta_seconds','profile','archive_sha256','local_v3_conversion_performed','worker_qualified') if k in value}
migration_inputs={}
head_recovery_cache={}
recovery_cache_root=pathlib.Path('/data/pbt-1/v3-head-recovery')
if recovery_cache_root.exists():
 head_recovery_cache['inputs_staged']=(recovery_cache_root/'job.json').is_file()
 cache_status=recovery_cache_root/'cache/status.json'
 if cache_status.exists():
  value=json.loads(cache_status.read_text())
  head_recovery_cache['status']={k:value[k] for k in ('phase','time','completed_bytes','archive_bytes',
   'bytes_per_second','eta_seconds') if k in value}
 result=subprocess.run(['systemctl','show','pbt-1-v3-head-recovery-cache','-p','LoadState','-p','ActiveState',
                        '-p','SubState','-p','MainPID','-p','Result'],capture_output=True,text=True)
 head_recovery_cache['service']=dict(l.split('=',1) for l in result.stdout.splitlines() if '=' in l)
input_status=pathlib.Path('/data/pbt-1/migration-input-control/status.json')
if input_status.exists():
 value=json.loads(input_status.read_text())
 migration_inputs['status']={k:value[k] for k in ('phase','file','received_bytes','file_bytes','time','host','files','error_class') if k in value}
 result=subprocess.run(['systemctl','show','pbt-1-migration-input-download','-p','LoadState','-p','ActiveState','-p','SubState','-p','MainPID','-p','Result'],capture_output=True,text=True)
 migration_inputs['service']=dict(l.split('=',1) for l in result.stdout.splitlines() if '=' in l)
 migration_inputs['original_download_proof_present']=pathlib.Path('/data/pbt-1/migration-input-24453558/ready.json').is_file()
erigon_upgrades={}
for kind,directory,unit in (
 ('exporter','v3-source-upgrade','pbt-1-v3-source-upgrade-v3'),
 ('head','v3-head-upgrade','pbt-1-v3-head-upgrade'),
 ('exporter_index_recovery','v3-source-index-recovery','pbt-1-v3-source-index-recovery')):
 upgrade_root=pathlib.Path('/data/pbt-1')/directory
 upgrade_status=upgrade_root/'status.json'
 if not upgrade_status.exists():continue
 phase=json.loads(upgrade_status.read_text())
 unit_result=subprocess.run(['systemctl','show',unit,'-p','ActiveState','-p','SubState','-p','Result','-p','MainPID'],capture_output=True,text=True)
 unit_state=dict(l.split('=',1) for l in unit_result.stdout.splitlines() if '=' in l)
 log=upgrade_root/('index.log' if kind=='exporter_index_recovery' else phase.get('phase','')+'.log')
 latest_progress=None
 log_stat=None
 if log.exists():
  info=log.stat()
  log_stat={'bytes':info.st_size,'mtime':info.st_mtime}
  with log.open('rb') as stream:
   stream.seek(max(0,info.st_size-262144))
   lines=stream.read().decode(errors='replace').splitlines()
  progress=[l for l in lines if '[commitment_convert]' in l
            or '[commitment_verify]' in l
            or ('Execution]' in l and ('parallel done' in l or 'Committed' in l))
            or ('[snapshots]' in l and 'Indexing' in l and 'progress=' in l)]
  if progress:latest_progress=progress[-1][:2000]
 events=pathlib.Path('/sys/fs/cgroup/system.slice')/(unit+'.service')/'memory.events'
 memory_events=dict(l.split() for l in events.read_text().splitlines()) if events.exists() else None
 cgroup=events.parent
 io_path=cgroup/'io.stat'
 cpu_path=cgroup/'cpu.stat'
 io_stat=io_path.read_text().splitlines() if io_path.exists() else None
 cpu_stat=dict(l.split() for l in cpu_path.read_text().splitlines()) if cpu_path.exists() else {}
 memory_limits={n:(cgroup/n).read_text().strip() for n in ('memory.max','memory.current')
                if (cgroup/n).exists()}
 erigon_upgrades[kind]={'status':phase,'service':unit_state,'log':log_stat,
                        'latest_progress':latest_progress,'memory_events':memory_events,
                        'memory_limits':memory_limits,
                        'io_stat':io_stat,'cpu_usage_usec':int(cpu_stat.get('usage_usec',0))}
containers=subprocess.run(['docker','ps','--format','{{.Names}}'],capture_output=True,text=True)
mem=next(l for l in pathlib.Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemTotal:'))
print(json.dumps({'time':time.time(),'cpus':os.cpu_count(),'memory_kib':int(mem.split()[1]),
 'root_disk':shutil.disk_usage('/')._asdict(),
 'recovery_mounted':root.is_mount(),
 'recovery_disk':shutil.disk_usage(root)._asdict() if root.is_mount() else None,
 'download':download,'extraction':extraction,
 'download_service':dict(l.split('=',1) for l in service.stdout.splitlines() if '=' in l),
 'qualification':{k:qualification.get(k) for k in ('status','image','head','head_hash','node_id','missing_builder_contracts','finished_at','error',
  'preparation_path','source_release_archive_sha256','local_v3_conversion_performed')} if qualification else None,
 'qualification_service':dict(l.split('=',1) for l in qualification_service.stdout.splitlines() if '=' in l),
 'exporter_handoff':exporter_handoff,
 'erigon_upgrades':erigon_upgrades,
 'head_restore':head_restore,
 'head_recovery_cache':head_recovery_cache,
 'migration_inputs':migration_inputs,
 'running_containers':containers.stdout.splitlines()}))
'''


def main():
    hosts = json.loads((ROOT / 'hosts.json').read_text())
    previous_path = ROOT / 'latest.json'
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    maintenance_path = ROOT / 'maintenance.json'
    maintenance = json.loads(maintenance_path.read_text()) if maintenance_path.exists() else {}

    def check(item):
        name, host = item
        try:
            proc = subprocess.run(
                ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-i',
                 str(Path.home() / '.ssh/devops_eth2_shared_key'),
                 'root@' + host['ip'], 'python3 -'],
                input=REMOTE, text=True, capture_output=True, timeout=35, check=True)
            return name, json.loads(proc.stdout)
        except Exception as exc:
            return name, {'error': str(exc)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=9) as pool:
        results = dict(pool.map(check, hosts.items()))
    alerts = []
    for name, state in results.items():
        if 'error' in state:
            if maintenance.get(name, {}).get('until', 0) > time.time():
                state['planned_maintenance'] = maintenance[name]
            else:
                alerts.append(name + ': SSH unavailable')
            continue
        job = state.get('download') or {}
        if job.get('phase') == 'failed':
            alerts.append(name + ': ' + job.get('error', 'download/restore failed'))
        qualification = state.get('qualification') or {}
        if (qualification.get('status') == 'failed'
                or state['qualification_service'].get('ActiveState') == 'failed'):
            alerts.append(name + ': worker startup qualification failed')
        if qualification.get('missing_builder_contracts'):
            alerts.append(name + ': missing builder request contracts')
        if job.get('phase') in ('downloading', 'extracting'):
            if state['download_service'].get('ActiveState') != 'active':
                alerts.append(name + ': job stopped before completion')
        old = (previous.get('hosts', {}).get(name, {}).get('download') or {})
        if (job.get('phase') == old.get('phase') == 'downloading'
                and job.get('completed_bytes') == old.get('completed_bytes')
                and time.time() - job.get('time', 0) > 900):
            alerts.append(name + ': no download progress for 15 minutes')
        old_state = previous.get('hosts', {}).get(name, {})
        recovery_cache = state.get('head_recovery_cache') or {}
        cache_status = recovery_cache.get('status', {})
        cache_service = recovery_cache.get('service', {})
        cache_phase = cache_status.get('phase')
        if cache_phase == 'failed' or cache_service.get('ActiveState') == 'failed':
            alerts.append(name + ': corrected H recovery cache failed; original backup remains protected')
        elif (cache_phase and cache_phase not in ('archive_verified', 'archive_ready_for_staged_restore')
              and cache_service.get('ActiveState') not in ('active', 'activating')):
            alerts.append(name + ': corrected H recovery cache stopped before verification')
        old_cache = old_state.get('head_recovery_cache', {}).get('status', {})
        if (cache_phase == old_cache.get('phase') == 'downloading'
                and cache_status.get('completed_bytes') == old_cache.get('completed_bytes')
                and state['time'] - cache_status.get('time', 0) > 900):
            alerts.append(name + ': corrected H recovery cache has no progress for 15 minutes; inspect live process')
        restored = state.get('head_restore') or {}
        if restored:
            service = restored.get('service', {})
            cache = restored.get('cache', {})
            phase = restored.get('status', {}).get('phase')
            if service.get('ActiveState') == 'failed' or cache.get('phase') == 'failed':
                alerts.append(name + ': verified H release restore failed; original database is preserved')
            elif ((cache or phase) and phase != 'restored_pending_own_qualification'
                  and service.get('ActiveState') not in ('active', 'activating')):
                alerts.append(name + ': verified H release restore stopped before completion')
            old_cache = old_state.get('head_restore', {}).get('cache', {})
            if (cache.get('phase') == old_cache.get('phase') == 'downloading'
                    and cache.get('completed_bytes') == old_cache.get('completed_bytes')
                    and state['time'] - cache.get('time', 0) > 900):
                alerts.append(name + ': verified H release download has no progress for 15 minutes')
            if service.get('ActiveState') == 'active' and state['root_disk']['free'] < 300_000_000_000:
                alerts.append(name + ': verified H release restore has less than 300 GB free')
        inputs = state.get('migration_inputs', {})
        if inputs:
            phase = inputs['status'].get('phase')
            service = inputs['service']
            if phase == 'failed' or service.get('ActiveState') == 'failed':
                alerts.append(name + ': migration input download failed')
            elif phase != 'verified_inputs_ready' and service.get('ActiveState') not in ('active', 'activating'):
                alerts.append(name + ': migration input download stopped before verification')
        for kind, service in state.get('exporter_handoff', {}).items():
            if service.get('ActiveState') == 'failed':
                alerts.append(name + ': exporter ' + kind + ' failed; inspect handoff evidence')
        for kind, upgrade in state.get('erigon_upgrades', {}).items():
            phase = upgrade['status'].get('phase')
            service = upgrade['service']
            label = name + ': Erigon ' + kind
            if phase == 'failed' or service.get('ActiveState') == 'failed':
                alerts.append(label + ' conversion failed')
            elif (phase not in ('converted_pending_native_reopen',
                                'native_reopen_validation', 'v3_source_verified_stopped',
                                'indexes_built_pending_review', 'indexes_reused_by_conversion')
                  and service.get('ActiveState') not in ('active', 'activating')):
                alerts.append(label + ' conversion stopped before completion')
            events = upgrade.get('memory_events') or {}
            if int(events.get('oom_kill', 0)):
                alerts.append(label + ' conversion recorded an OOM kill')
            if (service.get('ActiveState') == 'active'
                    and state['root_disk']['free'] < 300_000_000_000):
                alerts.append(label + ' conversion has less than 300 GB free; driver stops below 150 GB')
            # A quiet log alone does not prove a dead job. Report the evidence
            # for inspection; never restart a conversion from monitoring.
            old_upgrade = old_state.get('erigon_upgrades', {}).get(kind, {})
            log, old_log = upgrade.get('log'), old_upgrade.get('log')
            if (service.get('ActiveState') == 'active' and log and old_log
                    and phase == old_upgrade.get('status', {}).get('phase')
                    and log == old_log and state['time'] - log['mtime'] > 1800):
                alerts.append(label + ' conversion log unchanged for 30 minutes; inspect live process')
        extraction, old_extraction = state.get('extraction'), old_state.get('extraction')
        if (extraction and old_extraction and extraction['pid'] == old_extraction['pid']
                and extraction['compressed_input_bytes'] == old_extraction['compressed_input_bytes']
                and state['time'] - old_state.get('time', 0) >= 900):
            alerts.append(name + ': extraction input has not advanced for 15 minutes')
        if state['root_disk']['free'] < 100_000_000_000:
            alerts.append(name + ': less than 100 GB local free space')
    publication = None
    publication_status = ROOT.parent / 'v3-head-publication/status.json'
    if publication_status.exists():
        publication = {'status': json.loads(publication_status.read_text())}
        service = subprocess.run(['systemctl', '--user', 'show', 'pbt-1-v3-head-publication',
                                  '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result'],
                                 capture_output=True, text=True, timeout=10)
        publication['service'] = dict(line.split('=', 1) for line in service.stdout.splitlines() if '=' in line)
        if (publication['status'].get('phase') == 'failed'
                or publication['service'].get('ActiveState') == 'failed'):
            alerts.append('H snapshot publication controller failed; inspect private evidence')
        elif (publication['status'].get('phase') != 'published_verified'
              and publication['service'].get('ActiveState') != 'active'):
            alerts.append('H snapshot publication controller stopped before verified release')
    artifacts = None
    artifact_status = ROOT.parent / 'artifact-publication/auto-status.json'
    if artifact_status.exists():
        artifacts = {'status': json.loads(artifact_status.read_text())}
        service = subprocess.run(['systemctl', '--user', 'show', 'pbt-1-artifact-publication',
                                  '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result'],
                                 capture_output=True, text=True, timeout=10)
        artifacts['service'] = dict(line.split('=', 1) for line in service.stdout.splitlines() if '=' in line)
        if artifacts['status'].get('phase') == 'failed' or artifacts['service'].get('ActiveState') == 'failed':
            alerts.append('Shared N artifact publication controller failed; inspect private evidence')
        elif artifacts['status'].get('phase') != 'published_verified' and artifacts['service'].get('ActiveState') != 'active':
            alerts.append('Shared N artifact publication controller stopped before verified release')
    report = {'checked_at': time.time(), 'hosts': results, 'alerts': alerts,
              'head_publication': publication, 'artifact_publication': artifacts}
    temporary = ROOT / 'latest.tmp'
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(previous_path)
    with (ROOT / 'history.jsonl').open('a') as stream:
        stream.write(json.dumps(report) + '\n')
    print(json.dumps({'alerts': alerts, 'hosts': {
        name: {'cpus': state.get('cpus'), 'phase': (state.get('download') or {}).get('phase'),
               'qualification': (state.get('qualification') or {}).get('status'),
               'extraction_percent': (state.get('extraction') or {}).get('input_percent'),
               'bytes': (state.get('download') or {}).get('completed_bytes')}
        for name, state in results.items()}}))


if __name__ == '__main__':
    main()
