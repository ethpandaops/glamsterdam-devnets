#!/usr/bin/env python3
"""Final Erigon-1 cache handoff after restore, own startup, backup and cleanup.

Default is preflight only; --run syncs and drops page cache once. Does not read
database/archive contents, delete data, or start clients.
"""
import fcntl,hashlib,json,os,socket,stat,subprocess,sys,time
from contextlib import ExitStack
from pathlib import Path
B=Path('/data/pbt-1');R=B/'direct-recovery-replacement';V=Path('/mnt/pbt-recovery')
SHA='b4ab8e0831bd95ddce05b9f52c040de7eaf4a9b8b1fa49106cb3e9cd88938146'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def identity(p):
 s=p.lstat();assert stat.S_ISREG(s.st_mode)
 return dict(device=s.st_dev,inode=s.st_ino,bytes=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
def save(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 fd=os.open(p.parent,os.O_DIRECTORY|os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def memory():
 keys={'MemTotal','MemFree','MemAvailable','Buffers','Cached','SwapCached','Dirty','Writeback','SReclaimable','Shmem'}
 return {line.split(':')[0]:int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.split(':')[0] in keys}
def idle():
 units=subprocess.check_output(['systemctl','list-units','--state=running,activating,deactivating','--no-legend','--plain','pbt*'],text=True)
 assert not units.strip(), 'PBT preparation/client unit is running'
 names=set(subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines())
 assert names <= {'nginx-proxy-cert-linker','nginx-proxy-cert-loader','nginx-proxy-gen','nginx-proxy','vector','prometheus','node_exporter'}
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
  try:
   assert (proc/'comm').read_text().strip() not in {'erigon','integration','integration-bou','geth','besu','lighthouse','Nethermind.Runne'}, 'Client process remains'
   for fd in (proc/'fd').iterdir():
    try:target=os.readlink(fd)
    except FileNotFoundError:continue
    assert not (target.startswith(str(B/'erigon')+'/') or target==str(V/'erigon-24503958.tar.zst')), 'Data file is in use'
   for line in (proc/'maps').read_text().splitlines():
    fields=line.split(maxsplit=5)
    if len(fields)==6:
     assert not (fields[5].startswith(str(B/'erigon')+'/') or fields[5]==str(V/'erigon-24503958.tar.zst')), 'Data mapping remains'
  except (FileNotFoundError,ProcessLookupError):pass
 return sorted(names)
os.umask(0o077)
assert socket.gethostname()=='glamsterdam-pbt-1-lighthouse-erigon-1'
assert B.resolve()==B and V.resolve()==V
assert not (B/'memory-handoff.json').exists() and not (B/'memory-handoff-started.json').exists()
with ExitStack() as stack:
 for path in (B/'memory-handoff.lock',B/'qualification/run.lock',B/'v3-head-restore/restore.lock',R/'run.lock',V/'download.lock'):
  f=stack.enter_context(path.open('a'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 Q=sha(B/'qualification/result.json')
 proof=read(B/'qualification/result.json')
 assert proof['host']=='lighthouse-erigon-1' and proof['status']=='startup_checks_passed'
 assert proof['head']==24503958 and proof['memory_gib']==32 and proof['cpus']==8
 assert proof['native_reopen_verified'] and proof['v3_format_verified']
 container=json.loads(subprocess.check_output(['docker','inspect','pbt-1-worker-qualification']))[0]
 state=container['State'];config=container['HostConfig']
 assert state==proof['stopped_state'] and not state['Running'] and not state['OOMKilled'] and state['ExitCode']==0
 assert config['Memory']==config['MemorySwap']==32*1024**3 and config['NanoCpus']==8*10**9 and config['CpusetCpus']=='0-7'
 ready=read(R/'ready.json')
 assert ready['phase']=='ready_for_direct_recovery_download'
 assert ready['archive_sha256']==SHA and ready['qualification_sha256']==Q
 assert ready['restore'] is False and ready['live_database_unchanged'] is True
 job=read(Path('/etc/pbt-recovery/job.json'))
 assert job['archive_sha256']==SHA and job['archive_bytes']==461165199193
 assert job['key']=='pbt-1/20261020-erigon-v3-head/erigon/24503958/snapshot.tar.zst'
 assert job['restore'] is False and job['client']=='erigon' and job['head']==24503958
 assert read(V/'status.json')['phase']=='recovery_ready_existing_db_preserved'
 complete=read(B/'v3-head-restore/complete.json')
 assert complete['archive_sha256']==SHA and complete['archive_transfer']=='stream'
 db=(B/'erigon').stat()
 assert complete['restored_identity']=={'device':db.st_dev,'inode':db.st_ino}
 assert proof['preparation_path']=='restored_verified_H_release'
 assert proof['source_release_archive_sha256']==SHA
 assert not (B/'erigon-original-h-preserved').exists()
 assert subprocess.check_output(['findmnt','-n','-o','SOURCE','--target',str(B)],text=True).strip()=='/dev/vda1'
 tune=subprocess.check_output(['tune2fs','-l','/dev/vda1'],text=True)
 fields=dict(line.split(':',1) for line in tune.splitlines() if ':' in line)
 assert int(fields['Reserved block count'].strip())==25171402
 assert subprocess.check_output(['findmnt','-n','-o','UUID','--target',str(V)],text=True).strip()=='9d3c985b-82b8-418b-a78c-ee3aa78544dd'
 archive=V/'erigon-24503958.tar.zst';ident=identity(archive);archived=read(V/'archive-verified.json')
 assert archived['sha256']==SHA and ident['bytes']==461165199193
 assert archived['bytes']==ident['bytes'] and archived['mtime_ns']==ident['mtime_ns']
 services=idle();before=memory()
 receipt={'worker':'lighthouse-erigon-1','checked_at':time.time(),'qualification_sha256':Q,'recovery_archive_sha256':SHA,'recovery_archive_identity':ident,'recovery_ready_receipt_sha256':sha(R/'ready.json'),'recovery_job_sha256':sha(Path('/etc/pbt-recovery/job.json')),'preparation_and_clients_stopped':True,'allowed_running_containers':services,'before_memory_kib':before,'genesis_time':None,'pbt_activation_time':None,'migration_memory_measurement':False}
 if '--run' not in sys.argv:
  print(json.dumps({'preflight':'passed','before_memory_kib':before,'qualification_sha256':Q}));sys.exit(0)
 save(B/'memory-handoff-started.json',receipt)
 idle()
 subprocess.run(['sync'],check=True)
 receipt['after_sync_memory_kib']=memory()
 Path('/proc/sys/vm/drop_caches').write_text('1\n')
 receipt['after_drop_memory_kib']=memory()
 receipt['completed_at']=time.time()
 receipt['qualification_unchanged']=sha(B/'qualification/result.json')==Q
 receipt['recovery_archive_identity_unchanged']=identity(archive)==ident
 assert receipt['qualification_unchanged'] and receipt['recovery_archive_identity_unchanged']
 receipt['phase']='stopped_worker_cache_handoff_complete'
 receipt['commands']=['sync','write 1 to /proc/sys/vm/drop_caches']
 receipt['repeat_required_after']='Any later preparation read of database or migration-input contents before measured client startup'
 save(B/'memory-handoff.json',receipt)
 print(json.dumps(receipt))

