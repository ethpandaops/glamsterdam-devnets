#!/usr/bin/env python3
"""Stream a stopped, restart-verified native DB into scoped presigned multipart PUTs.

No storage credentials live on the VM. The controller completes and verifies the
multipart upload after this program records every ETag, size and SHA-256.
"""
import argparse
import concurrent.futures
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request
from pipeline_rpc import ROOT, save

PART_SIZE=256*1024**2
V3_HEAD_KEY='pbt-1/20261020-erigon-v3-head/erigon/24503958/snapshot.tar.zst'


def validate_v3_head_proof(proof, conversion):
    """Require H and two verified v3 opens, never the older exporter proof."""
    assert proof['host']=='lighthouse-erigon-2' and proof['client']=='erigon'
    assert proof['status']=='startup_checks_passed'
    assert proof['head']==24503958
    assert proof['head_hash']=='0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216'
    assert proof['state_root']=='0x8cab6f81e370f341e67e66d2333cdf3e6074861f861aa3e490b9411460ad7f22'
    assert proof['commit']=='372df0e68f52f9975370bff38dee6e41aefff0d7'
    assert proof['image']=='registry-1.docker.io/ethpandaops/erigon@sha256:4aec40c643590ec9496c982b22f0efb04835ff071233e92c418f9380cc84db69'
    assert proof['native_reopen_verified'] and proof['v3_format_verified']
    assert proof['memory_gib']==16 and proof['cpus']==8 and proof['network_mode']=='none'
    assert not proof['missing_builder_contracts']
    for key in ('first_stopped_state','stopped_state'):
        state=proof[key]
        assert not state['Running'] and not state['OOMKilled'] and state['ExitCode']==0
    assert conversion['source']=='/data/pbt-1/erigon'
    assert conversion['target_block']==proof['head']
    assert proof.get('converter_build') == conversion.get('converter_build'), 'Converter provenance differs'


def require_v3_head_source(job):
    assert ROOT==Path('/data/pbt-1/v3-head-publication')
    assert socket.gethostname()=='glamsterdam-pbt-1-lighthouse-erigon-2'
    assert job['client']=='erigon' and job['head']==24503958 and job['key']==V3_HEAD_KEY
    base=Path('/data/pbt-1')
    raw=(base/'qualification/result.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==job['qualification_sha256']
    proof=json.loads(raw)
    conversion=json.loads((base/'v3-head-upgrade/conversion-complete.json').read_text())
    validate_v3_head_proof(proof,conversion)
    locks=[]
    for path in (base/'v3-head-upgrade/upgrade.lock',base/'qualification/run.lock'):
        handle=path.open('a')
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        locks.append(handle)
    for unit in ('pbt-1-v3-head-upgrade','pbt-1-worker-qualification'):
        active=subprocess.check_output(['systemctl','show',unit,'-p','ActiveState','--value'],text=True).strip()
        assert active=='inactive', (unit,active)
    current=json.loads(subprocess.check_output(['docker','inspect','pbt-1-worker-qualification']))[0]['State']
    assert not current['Running'] and current['FinishedAt']==proof['stopped_state']['FinishedAt']
    db=base/'erigon'
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        try:argv=(proc/'cmdline').read_bytes().split(bytes([0]))
        except (FileNotFoundError,ProcessLookupError):continue
        for i,arg in enumerate(argv):
            path=arg[len(b'--datadir='):] if arg.startswith(b'--datadir=') else (
                argv[i+1] if arg==b'--datadir' and i+1<len(argv) else None)
            if path:
                assert Path(os.fsdecode(path)).resolve()!=db, ('Native DB process remains',proc.name)
    return db,locks


def archive_command(client, db, v3_source=False):
    excludes=['--exclude=./nodekey','--exclude=./nodes','--exclude=./key',
              '--exclude=./jwtsecret','--exclude=./logs','--exclude=./LOG',
              '--exclude=./LOCK','--exclude=./geth.ipc','--exclude=./mainnet/state',
              '--exclude=./keystore','--exclude=./mainnet/keystore']
    if client=='erigon':
        excludes.append('--exclude=./temp')
    if v3_source:
        excludes += ['--exclude=./snapshots/backup', '--exclude=./snapshots/rebuild',
                     '--exclude=./snap/rebuild']
    return ['tar','--sparse','--sort=name',*excludes,'-C',str(db),'-cf','-','.']


def main():
    lock=(ROOT/'upload.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    job=json.loads((ROOT/'upload-authorization.json').read_text())
    c=job['client'];head=job['head'];workload=head-24452538-3
    workers=32 if c=='erigon' else 4
    v3_source=job.get('profile')=='erigon-v3-source'
    v3_head=job.get('profile')=='erigon-v3-head'
    source_locks=[]  # Keep these locks for the whole archive stream.
    if v3_head:
        db,source_locks=require_v3_head_source(job)
        workers=8
    elif v3_source:
        assert ROOT==Path('/data/pbt-1/v3-source-upgrade')
        assert c=='erigon' and head==24452538
        proof=json.loads((ROOT/'upload-ready.json').read_text())
        assert proof['stopped'] and proof['native_reopen_verified'] and proof['v3_state_verified']
        assert proof['head']['hash']=='0x0fd7242bab5055dda36f374f352c78cae381daae9b3e8febe895dce35c907591'
        assert proof['head']['stateRoot']=='0xecf809f327549d4a93eeae29252e8f33b0e9f188cba92f0bb43207d4c7a9c9ca'
        assert int(proof['head']['number'],16)==head
        db=Path('/data/pbt-1/rehearsal-24453558/erigon')
        assert proof['source']==str(db)
        unit=subprocess.check_output(['systemctl','show','pbt-1-v3-source-reopen',
                                      '-p','MainPID','--value'],text=True).strip()
        assert unit=='0', 'Native source client is still running'
        assert job['key'].startswith('pbt-1/20261020-erigon-v3-source/')
        workers=8
    else:
        proof=json.loads((ROOT/f'reopen-{workload}-complete.json').read_text())
        assert proof['stopped'] and int(proof['head']['number'],16)==head
        assert proof['verified_bal_bodies']==workload+3
        inspect=json.loads(subprocess.check_output(['docker','inspect',f'pbt-1-{c}-execution']))[0]
        assert not inspect['State']['Running'] and not inspect['State']['OOMKilled']
        assert inspect['State']['ExitCode'] in ((0,143) if c=='besu' else (0,130))
        db=Path('/data/pbt-1')/c
        assert job['key'].startswith('pbt-1/20261019-mixed-8037-v2/')
    for cid in subprocess.check_output(['docker','ps','-q'],text=True).splitlines():
        container=json.loads(subprocess.check_output(['docker','inspect',cid]))[0]
        for mount in container['Mounts']:
            if (container['Name']=='/node_exporter' and mount['Source']=='/'
                    and mount['Destination']=='/rootfs' and not mount['RW']):
                continue
            path=Path(mount['Source'])
            assert not (path==db or path in db.parents or db in path.parents), 'Database is mounted by a running container'
    if c=='nethermind':
        cleanup=json.loads((Path('/data/pbt-1/nethermind-flatdb-cleanup/complete.json')).read_text())
        assert cleanup['patricia_bytes_after'] < 16*1024**2
        state=db/'mainnet/state'
        assert not state.exists() or int(subprocess.check_output(['du','-s','-B1',str(state)],text=True).split()[0]) < 16*1024**2
    assert len(job['urls']) <= 10000
    stage=ROOT/'upload-parts';stage.mkdir(exist_ok=True)
    # Native layouts match the source releases: Geth's instance dir is flat;
    # Nethermind includes mainnet/. Its empty Patricia stub is omitted too.
    archive_args=archive_command(c,db,v3_source or v3_head)
    tarlog=(ROOT/'upload-tar.log').open('w')
    tar=subprocess.Popen(archive_args,stdout=subprocess.PIPE,stderr=tarlog)
    zlog=(ROOT/'upload-zstd.log').open('w')
    zstd=subprocess.Popen(['zstd','-1','-T4','-q'],stdin=tar.stdout,stdout=subprocess.PIPE,stderr=zlog)
    tar.stdout.close()
    results=[];total=0;digest=hashlib.sha256();started=time.time()
    def put(item):
        number,path,size,sha=item
        for attempt in range(8):
            try:
                # At most `workers` 256-MiB PUT buffers; remove stages after PUT.
                data=path.read_bytes()
                request=urllib.request.Request(job['urls'][number-1],data=data,method='PUT',
                    headers={'Content-MD5':base64.b64encode(hashlib.md5(data).digest()).decode()})
                with urllib.request.urlopen(request,timeout=600) as response:
                    assert response.status==200
                    etag=response.headers['ETag']
                path.unlink()
                return {'PartNumber':number,'ETag':etag,'bytes':size,'sha256':sha}
            except Exception:
                if attempt==7:raise RuntimeError(f'Upload part {number} failed after 8 attempts') from None
                time.sleep(min(2**attempt,60))
    def collect(future):
        results.append(future.result())
        save(ROOT/'upload-progress.json',{'time':time.time(),'parts':sorted(results,key=lambda x:x['PartNumber']),
                                         'uploaded_bytes':sum(x['bytes'] for x in results)})
        save(ROOT/'status.json',{'phase':'uploading','time':time.time(),'head':head,
                                'uploaded_bytes':sum(x['bytes'] for x in results),'parts':len(results)})
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            pending=set();number=0
            while True:
                data=bytearray()
                while len(data)<PART_SIZE:
                    chunk=zstd.stdout.read(min(8*1024**2,PART_SIZE-len(data)))
                    if not chunk:break
                    data.extend(chunk)
                if not data:break
                number+=1;assert number<=len(job['urls']), 'Multipart capacity exceeded'
                digest.update(data);total+=len(data)
                path=stage/f'{number:05d}.part';path.write_bytes(data)
                sha=hashlib.sha256(data).hexdigest();size=len(data);del data
                pending.add(pool.submit(put,(number,path,size,sha)))
                if len(pending)>=workers:
                    done,pending=concurrent.futures.wait(pending,return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in done:collect(future)
            for future in concurrent.futures.as_completed(pending):collect(future)
        assert zstd.wait()==0,'zstd failed'
        assert tar.wait()==0,'tar failed; do not complete multipart upload'
        report={'client':c,'head':head,'key':job['key'],'upload_id':job['upload_id'],
                'parts':sorted(results,key=lambda x:x['PartNumber']),'archive_bytes':total,
                'archive_sha256':digest.hexdigest(),'seconds':time.time()-started,'time':time.time(),
                'data_bytes':int(subprocess.check_output(['du','-s','-B1',str(db)],text=True).split()[0]),
                'upload_workers':workers,'archive_excludes':[x for x in archive_args if x.startswith('--exclude=')]}
        save(ROOT/'upload-complete-parts.json',report)
        save(ROOT/'status.json',{'phase':'awaiting_upload_verification','time':time.time(),'head':head,'archive_bytes':total})
        print(json.dumps({k:v for k,v in report.items() if k not in ('parts','upload_id')}),flush=True)
    finally:
        if zstd.poll() is None:zstd.terminate()
        if tar.poll() is None:tar.terminate()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v3-head',action='store_true')
    args=parser.parse_args()
    if args.v3_head:ROOT=Path('/data/pbt-1/v3-head-publication')
    try:main()
    except Exception as exc:
        save(ROOT/'status.json',{'phase':'failed','time':time.time(),'error':str(exc)});raise
