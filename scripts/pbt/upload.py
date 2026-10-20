#!/usr/bin/env python3
"""Stream a stopped, restart-verified native DB into scoped presigned multipart PUTs.

No storage credentials live on the VM. The controller completes and verifies the
multipart upload after this program records every ETag, size and SHA-256.
"""
import concurrent.futures
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
from pipeline_rpc import ROOT, save

PART_SIZE=256*1024**2


def archive_command(client, db):
    excludes=['--exclude=./nodekey','--exclude=./nodes','--exclude=./key',
              '--exclude=./jwtsecret','--exclude=./logs','--exclude=./LOG',
              '--exclude=./LOCK','--exclude=./geth.ipc','--exclude=./mainnet/state',
              '--exclude=./keystore','--exclude=./mainnet/keystore']
    if client=='erigon':
        excludes.append('--exclude=./temp')
    return ['tar','--sparse','--sort=name',*excludes,'-C',str(db),'-cf','-','.']


def main():
    lock=(ROOT/'upload.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    job=json.loads((ROOT/'upload-authorization.json').read_text())
    c=job['client'];head=job['head'];workload=head-24452538-3
    workers=16 if c=='erigon' else 4
    proof=json.loads((ROOT/f'reopen-{workload}-complete.json').read_text())
    assert proof['stopped'] and int(proof['head']['number'],16)==head
    assert proof['verified_bal_bodies']==workload+3
    inspect=json.loads(subprocess.check_output(['docker','inspect',f'pbt-1-{c}-execution']))[0]
    assert not inspect['State']['Running'] and not inspect['State']['OOMKilled']
    assert inspect['State']['ExitCode'] in ((0,143) if c=='besu' else (0,130))
    db=Path('/data/pbt-1')/c
    for cid in subprocess.check_output(['docker','ps','-q'],text=True).splitlines():
        for mount in json.loads(subprocess.check_output(['docker','inspect',cid]))[0]['Mounts']:
            path=Path(mount['Source'])
            assert not (path==db or path in db.parents or db in path.parents), 'Database is mounted by a running container'
    if c=='nethermind':
        cleanup=json.loads((Path('/data/pbt-1/nethermind-flatdb-cleanup/complete.json')).read_text())
        assert cleanup['patricia_bytes_after'] < 16*1024**2
        state=db/'mainnet/state'
        assert not state.exists() or int(subprocess.check_output(['du','-s','-B1',str(state)],text=True).split()[0]) < 16*1024**2
    assert job['key'].startswith('pbt-1/20261019-mixed-8037-v2/')
    assert len(job['urls']) <= 10000
    stage=ROOT/'upload-parts';stage.mkdir(exist_ok=True)
    # Native layouts match the source releases: Geth's instance dir is flat;
    # Nethermind includes mainnet/. Its empty Patricia stub is omitted too.
    archive_args=archive_command(c,db)
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
    try:main()
    except Exception as exc:
        save(ROOT/'status.json',{'phase':'failed','time':time.time(),'error':str(exc)});raise
