#!/usr/bin/env python3
"""One-shot E2 recovery-volume replacement; --run required for mutation."""
import fcntl, hashlib, json, os, socket, stat, subprocess, sys, time
from pathlib import Path
from contextlib import ExitStack
R=Path('/data/pbt-1/v3-head-recovery')
V=Path('/mnt/pbt-recovery')
SOURCE=R/'cache/erigon-24503958.tar.zst'
DEST=V/'erigon-24503958.tar.zst'
TEMP=V/'erigon-24503958.tar.zst.v3-copying'
SHA='b4ab8e0831bd95ddce05b9f52c040de7eaf4a9b8b1fa49106cb3e9cd88938146'
SIZE=461165199193
OLD_SHA='e511af776332da1497c537b58770bec0b7e962c1484cd2dcb9a9d30f6ac268a7'
UUID='6f0756eb-af7d-4d18-b353-2fea060b3c72'
QUAL='ea437a555a69eb58a256f3bb2cbfb7820a0c1cbea43db759adee4bfb7c55c4c7'
def read(p): return json.loads(p.read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def identity(p):
 s=p.lstat()
 assert stat.S_ISREG(s.st_mode)
 return dict(device=s.st_dev,inode=s.st_ino,bytes=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)
def syncdir(p):
 fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY)
 try: os.fsync(fd)
 finally: os.close(fd)
def save(p,d):
 t=p.with_name(p.name+'.tmp')
 with t.open('w') as f:
  json.dump(d,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
 t.replace(p);syncdir(p.parent)
def progress(phase,**extra):
 d=dict(phase=phase,time=time.time(),**extra)
 save(R/'replacement-status.json',d)
 print(json.dumps(d),flush=True)
def owners(p):
 target=identity(p); found=[]
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit(): continue
  try:
   for fd in (proc/'fd').iterdir():
    try:s=fd.stat()
    except FileNotFoundError:continue
    if (s.st_dev,s.st_ino)==(target['device'],target['inode']):found.append([proc.name,fd.name])
   for line in (proc/'maps').read_text().splitlines():
    fields=line.split(maxsplit=5)
    if len(fields)>=5:
     major,minor=map(lambda x:int(x,16),fields[3].split(':'))
     if (os.makedev(major,minor),int(fields[4]))==(target['device'],target['inode']):found.append([proc.name,'mmap'])
  except (FileNotFoundError,ProcessLookupError):pass
 return found
def main():
 assert socket.gethostname()=='glamsterdam-pbt-1-lighthouse-erigon-2'
 assert R.resolve()==R and V.resolve()==V and SOURCE.resolve()==SOURCE
 with ExitStack() as stack:
  for p in [R/'replacement.lock',R/'stored-cache-readback.lock',R/'cache/download.lock',V/'download.lock']:
   f=stack.enter_context(p.open('a'));fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  assert not (R/'replacement-started.json').exists()
  assert not TEMP.exists()
  assert subprocess.check_output(['findmnt','-n','-o','UUID','--target',str(V)],text=True).strip()==UUID
  proof=read(R/'stored-cache-verified.json')
  assert proof['phase']=='stored_cache_verified' and proof['sha256']==SHA and proof['bytes']==SIZE
  srcid=identity(SOURCE)
  assert all(proof[k]==v for k,v in srcid.items())
  assert not owners(SOURCE), 'Cache is in use'
  assert digest(R/'original-provenance/manifest.json')=='9a6dc507d2246037d954b205ae6b76afd28abf22c813465b11e18c0653be61f4'
  manifest=read(R/'original-provenance/manifest.json')
  oldid=identity(DEST)
  assert all(manifest['old_archive'][k]==v for k,v in oldid.items())
  for name,info in manifest['files'].items():
   assert digest(R/'original-provenance'/name)==info['sha256']
   assert digest(Path(info['source']))==info['sha256'], 'Original provenance changed'
  assert digest(Path('/data/pbt-1/qualification/result.json'))==QUAL
  release=read(R/'published-release.json')
  assert release['archive_sha256']==SHA and release['archive_bytes']==SIZE
  assert release['qualification_sha256']==QUAL and release['full_remote_sha256_verified']
  assert release['head']==24503958 and release['tree']=='MPT' and release['pbt_migration_performed'] is False
  oldproof=read(V/'archive-verified.json')
  assert oldproof['sha256']==OLD_SHA and oldproof['bytes']==oldid['bytes'] and oldproof['mtime_ns']==oldid['mtime_ns']
  assert not owners(DEST), 'Original archive is in use'
  for proc in Path('/proc').iterdir():
   if not proc.name.isdigit():continue
   try: name=(proc/'comm').read_text().strip()
   except (FileNotFoundError,ProcessLookupError):continue
   assert name not in ['erigon','integration','integration-bou','geth','besu','lighthouse','Nethermind.Runne'], 'Client or native job active'
  containers=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
  allowed={'nginx-proxy-cert-linker','nginx-proxy-cert-loader','nginx-proxy-gen','nginx-proxy','vector','prometheus','node_exporter'}
  assert set(containers)<=allowed
  units=subprocess.check_output(['systemctl','list-units','--state=running,activating,deactivating','--no-legend','--plain','pbt*'],text=True)
  assert not [l for l in units.splitlines() if 'pbt-1-v3-recovery-volume-replacement.service' not in l]
  fs=os.statvfs(V); available=fs.f_bavail*fs.f_frsize
  assert available+DEST.stat().st_blocks*512>SIZE+50_000_000_000
  checks=dict(cache=srcid,old_archive=oldid,volume_uuid=UUID,free_bytes=available,qualification_sha256=QUAL)
  if '--run' not in sys.argv:
   print(json.dumps(dict(preflight='passed',**checks))); return
  save(R/'replacement-started.json',dict(time=time.time(),**checks))
  # Remove only the exact proven old archive; preserve its provenance and the local cache.
  assert identity(DEST)==oldid and identity(SOURCE)==srcid
  DEST.unlink();syncdir(V)
  for name in ['archive-verified.json','download-state.json','restore-started.json','restore-complete.json','restore.log','status.json']:
   p=V/name
   assert digest(p)==manifest['files'][name]['sha256']
   p.unlink()
  save(V/'status.json',dict(phase='replacing_recovery_archive',time=time.time(),archive_bytes=SIZE,live_database_unchanged=True))
  progress('copying_to_recovery_volume',completed_bytes=0,archive_bytes=SIZE)
  count=0; last=time.monotonic()
  with SOURCE.open('rb') as source,TEMP.open('xb') as dest:
   while data:=source.read(8*1024**2):
    dest.write(data);count+=len(data)
    if time.monotonic()-last>=30:
     progress('copying_to_recovery_volume',completed_bytes=count,archive_bytes=SIZE);last=time.monotonic()
   dest.flush();os.fsync(dest.fileno())
  syncdir(V)
  assert count==SIZE and identity(SOURCE)==srcid
  tempid=identity(TEMP);h=hashlib.sha256();count=0;last=time.monotonic()
  progress('hashing_stored_volume_copy',completed_bytes=0,archive_bytes=SIZE)
  with TEMP.open('rb') as f:
   while data:=f.read(8*1024**2):
    h.update(data);count+=len(data)
    if time.monotonic()-last>=30:
     progress('hashing_stored_volume_copy',completed_bytes=count,archive_bytes=SIZE);last=time.monotonic()
  assert count==SIZE and h.hexdigest()==SHA and identity(TEMP)==tempid and identity(SOURCE)==srcid
  assert not DEST.exists()
  TEMP.rename(DEST);syncdir(V)
  finalid=identity(DEST)
  save(V/'archive-verified.json',dict(sha256=SHA,**finalid,verification='full_stored_volume_sha256',time=time.time()))
  job=read(Path('/etc/pbt-recovery/job.json'))
  job.update(archive_bytes=SIZE,archive_sha256=SHA,etag='"886ec54f00b80499902a532f0cab37e4-1718"',
             key='pbt-1/20261020-erigon-v3-head/erigon/24503958/snapshot.tar.zst',
             unpacked_bytes=1192103432995,restore=False)
  save(Path('/etc/pbt-recovery/job.json'),job)
  assert digest(Path('/data/pbt-1/qualification/job.json'))==manifest['files']['qualification-job.json']['sha256']
  assert digest(Path('/data/pbt-1/qualification/result.json'))==QUAL
  receipt=dict(phase='volume_verified_controller_reconciliation_pending',time=time.time(),sha256=SHA,**finalid,
               source_cache_preserved=True,live_database_unchanged=True,qualification_sha256=QUAL,
               original_archive_sha256=OLD_SHA,original_provenance=str(R/'original-provenance'),
               recovery_job_sha256=digest(Path('/etc/pbt-recovery/job.json')),restore=False)
  save(R/'replacement-complete.json',receipt)
  save(V/'status.json',dict(phase='archive_ready_for_staged_restore',time=time.time(),client='erigon',
                           archive_bytes=SIZE,completed_bytes=SIZE,live_database_unchanged=True))
  save(R/'replacement-status.json',receipt)
  print(json.dumps(receipt),flush=True)
if __name__=='__main__':
 os.umask(0o077)
 try:main()
 except Exception as e:
  if '--run' in sys.argv:progress('failed',error_class=type(e).__name__)
  raise
