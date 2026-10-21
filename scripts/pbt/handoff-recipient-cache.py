#!/usr/bin/env python3
"""Clear clean preparation cache on a stopped, input-ready non-Erigon worker.

Run on the recipient: default is preflight only; --run performs sync/drop_caches.
Refuses active preparation, missing input proofs and prior handoffs. No content
rehash, client startup or migration is performed.
"""
import fcntl,hashlib,json,os,socket,stat,subprocess,sys,time
from contextlib import ExitStack
from pathlib import Path
B=Path('/data/pbt-1');V=Path('/mnt/pbt-recovery')
HOST=socket.gethostname().removeprefix('glamsterdam-pbt-1-')
assert HOST in {f'lighthouse-{c}-{n}' for c in ('geth','besu','nethermind') for n in (1,2)} | {'lighthouse-geth-3'}
CLIENT=HOST.split('-')[1]; RAM=32 if HOST.endswith('-2') else 16
INPUT=B/'migration-input-24453558'
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
 allowed={'nginx-proxy-cert-linker','nginx-proxy-cert-loader','nginx-proxy-gen','nginx-proxy','vector','prometheus','node_exporter'}
 if HOST=='lighthouse-geth-1':allowed|={'cert_issuer','dns_server'}
 assert names <= allowed
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit() or int(proc.name)==os.getpid():continue
  try:
   assert (proc/'comm').read_text().strip() not in {'erigon','integration','integration-bou','geth','besu','lighthouse','Nethermind.Runne'}, 'Client process remains'
   for fd in (proc/'fd').iterdir():
    try:target=os.readlink(fd)
    except FileNotFoundError:continue
    assert not (target.startswith(str(B/CLIENT)+'/') or target==str(V/(CLIENT+'-24503958.tar.zst')) or target.startswith(str(INPUT)+'/')), 'Data file is in use'
   for line in (proc/'maps').read_text().splitlines():
    fields=line.split(maxsplit=5)
    if len(fields)==6:
     assert not (fields[5].startswith(str(B/CLIENT)+'/') or fields[5]==str(V/(CLIENT+'-24503958.tar.zst')) or fields[5].startswith(str(INPUT)+'/')), 'Data mapping remains'
  except (FileNotFoundError,ProcessLookupError):pass
 return sorted(names)
assert socket.gethostname()=='glamsterdam-pbt-1-'+HOST
assert B.resolve()==B and V.resolve()==V and INPUT.resolve()==INPUT
assert not (B/'memory-handoff.json').exists() and not (B/'memory-handoff-started.json').exists()
os.umask(0o077)
with ExitStack() as stack:
 for path in (B/'memory-handoff.lock',B/'qualification/run.lock',B/'migration-input-control/download.lock',V/'download.lock'):
  f=stack.enter_context(path.open('a'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 proof=read(B/'qualification/result.json');Q=sha(B/'qualification/result.json')
 assert proof['host']==HOST and proof['client']==CLIENT and proof['status']=='startup_checks_passed'
 assert proof['head']==24503958 and proof['head_hash']=='0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216'
 assert proof['memory_gib']==RAM and proof['cpus']==8 and proof['genesis_time'] is None
 container=json.loads(subprocess.check_output(['docker','inspect','pbt-1-worker-qualification']))[0]
 state=container['State'];config=container['HostConfig']
 allowed_exit=(0,130,143) if CLIENT=='besu' else (0,130)
 assert state==proof['stopped_state'] and not state['Running'] and not state['OOMKilled'] and state['ExitCode'] in allowed_exit
 if CLIENT=='besu' and state['ExitCode']==143:
  assert 'BesuCommand-Shutdown-Hook' in (B/'qualification/container.log').read_text()
 assert config['Memory']==config['MemorySwap']==RAM*1024**3 and config['NanoCpus']==8*10**9 and config['CpusetCpus']=='0-7'
 job=read(Path('/etc/pbt-recovery/job.json'));qualification_job=read(B/'qualification/job.json');archive=V/(CLIENT+'-24503958.tar.zst')
 ident=identity(archive);archived=read(V/'archive-verified.json')
 assert V.is_mount() and job['client']==CLIENT and job['head']==24503958
 assert archived['sha256']==job['archive_sha256']==qualification_job['archive_sha256']
 assert ident['bytes']==job['archive_bytes']==archived['bytes'] and ident['mtime_ns']==archived['mtime_ns']
 ready=read(INPUT/'ready.json'); ready_sha=sha(INPUT/'ready.json')
 assert ready['host']==HOST and ready['status']=='verified_inputs_ready'
 assert ready['anchor']==24453558 and ready['independent_writable_copies'] is True
 assert ready['migration_started'] is False and ready['genesis_time'] is None
 expected={'framed.bin','pbt-snapshot.meta.json'}
 if HOST!='lighthouse-geth-3': expected.add('pbt-snapshot.bin')
 assert set(ready['files'])==expected
 input_ids={}
 for name,info in ready['files'].items():
  current=identity(INPUT/name);input_ids[name]=current
  assert info['transfer_sha256_verified'] is True
  assert all(current[k]==info[k] for k in ('bytes','inode','mtime_ns'))
 services=idle();before=memory()
 receipt={'worker':HOST,'checked_at':time.time(),'qualification_sha256':Q,'recovery_archive_sha256':job['archive_sha256'],'recovery_archive_identity':ident,'migration_input_ready_sha256':ready_sha,'migration_input_identities':input_ids,'preparation_and_clients_stopped':True,'allowed_running_containers':services,'before_memory_kib':before,'genesis_time':None,'pbt_activation_time':None,'migration_memory_measurement':False}
 if '--run' not in sys.argv:
  print(json.dumps({'preflight':'passed','before_memory_kib':before,'qualification_sha256':Q}));sys.exit(0)
 save(B/'memory-handoff-started.json',receipt)
 idle();subprocess.run(['sync'],check=True)
 receipt['after_sync_memory_kib']=memory()
 Path('/proc/sys/vm/drop_caches').write_text('1\n')
 receipt['after_drop_memory_kib']=memory();receipt['completed_at']=time.time()
 assert sha(B/'qualification/result.json')==Q and identity(archive)==ident
 assert sha(INPUT/'ready.json')==ready_sha and all(identity(INPUT/name)==info for name,info in input_ids.items())
 receipt.update(qualification_unchanged=True,recovery_archive_identity_unchanged=True,migration_input_identities_unchanged=True,phase='stopped_worker_cache_handoff_complete',commands=['sync','write 1 to /proc/sys/vm/drop_caches'],repeat_required_after='Any later preparation read of database or migration-input contents before measured client startup')
 save(B/'memory-handoff.json',receipt)
 print(json.dumps(receipt))
