#!/usr/bin/env python3
"""Complete the scoped multipart upload, verify remote ranges, publish provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import time
from monitor import HOSTS
from storage import client,BUCKET,PREFIX


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('client',choices=HOSTS)
    a=p.parse_args();c=a.client
    root=Path.home()/'.local/state/pbt-1-run'
    plan=json.loads((root/'workload.json').read_text());v=plan['v2'];n=v['final_records']-3
    job=json.loads((root/f'upload-{c}.json').read_text())
    assert job['key'].startswith(PREFIX+c+'/')
    ssh=['ssh','-i',str(Path.home()/'.ssh/devops_eth2_shared_key'),'-o','BatchMode=yes','root@'+HOSTS[c][0]]
    def read(name):return json.loads(subprocess.check_output(ssh+['cat /data/pbt-1/pipeline/'+name]))
    report=read('upload-complete-parts.json');proof=read(f'reopen-{n}-complete.json')
    assert report['key']==job['key'] and report['upload_id']==job['upload_id']
    assert proof['stopped'] and report['head']==int(proof['head']['number'],16)==24452538+v['final_records']
    assert proof['qualifying_blocks']==50400
    parts=report['parts']
    assert [x['PartNumber'] for x in parts]==list(range(1,len(parts)+1))
    assert sum(x['bytes'] for x in parts)==report['archive_bytes']
    s3=client();completion=root/f'upload-{c}-completed.json'
    if not completion.exists():
        response=s3.complete_multipart_upload(Bucket=BUCKET,Key=job['key'],UploadId=job['upload_id'],
                    MultipartUpload={'Parts':[{k:p[k] for k in ['PartNumber','ETag']} for p in parts]})
        completion.write_text(json.dumps({'time':time.time(),'etag':response['ETag']})+'\n')
    head=s3.head_object(Bucket=BUCKET,Key=job['key'])
    assert head['ContentLength']==report['archive_bytes']
    rng=random.Random(report['archive_sha256'])
    selected=sorted({0,len(parts)-1,*rng.sample(range(len(parts)),min(3,len(parts)))})
    offsets=[];offset=0
    for part in parts:offsets.append(offset);offset+=part['bytes']
    checks=[]
    for i in selected:
        part=parts[i];start=offsets[i];end=start+part['bytes']-1
        response=s3.get_object(Bucket=BUCKET,Key=job['key'],Range=f'bytes={start}-{end}')
        assert response['ResponseMetadata']['HTTPStatusCode']==206
        digest=hashlib.sha256();length=0
        with response['Body'] as body:
            for chunk in iter(lambda:body.read(8*1024**2),b''):digest.update(chunk);length+=len(chunk)
        assert length==part['bytes'] and digest.hexdigest()==part['sha256']
        checks.append({'part':i+1,'bytes':length,'sha256':digest.hexdigest()})
        print(f'{c}: remote range {i+1}/{len(parts)} verified',flush=True)
    report['verified_ranges']=checks;report['verified_at']=time.time()
    report.pop('upload_id')
    prefix=job['key'].rsplit('/',1)[0]+'/'
    metadata={'docker_image':proof['image'],'data_size_bytes':report['data_bytes'],
              'archive_size_bytes':report['archive_bytes'],'archive_sha256':report['archive_sha256'],
              'shadowfork':{'head':report['head'],'head_hash':proof['head']['hash'],
                            'state_root':proof['head']['stateRoot'],'amsterdam_time':1769856769,
                            'base':24452538,'network':'pbt-1','filler':'geth','gas_limit':200000000,
                            'notes':'Already Amsterdam. Preserve the source genesis/fork schedule; isolated chain-id-1 benchmark state.'},
              'pbt':{'source_release':'jochemnet/'+c+'/24452538','source_anchor':24452538,
                     'preparation_blocks':v['qualifying_start_index'],'workload_blocks':50400,
                     'qualifying_anchor':24452538+v['qualifying_start_index'],
                     'verified_bal_bodies':proof['verified_bal_bodies'],
                     'workload_gas_targets':{'execution':100000000,'state':100000000,'block_limit':200000000},
                     'minimum_qualifying_bal_bytes':proof['minimum_qualifying_bal_bytes'],
                     'native_layout':'flat geth instance directory; mount under <datadir>/geth' if c=='geth' else 'source native layout',
                     'nethermind_patricia_omitted':c=='nethermind','clean_restart_verified':True,
                     'workload_manifest':PREFIX+'_snapshot_workload.json'}}
    objects={'_snapshot_metadata.json':metadata,'_snapshot_eth_getBlockByNumber.json':{'jsonrpc':'2.0','id':1,'result':proof['head']},
             '_snapshot_integrity.json':report,'_snapshot_reopen.json':proof}
    for name,value in objects.items():
        data=json.dumps(value,indent=2).encode()
        s3.put_object(Bucket=BUCKET,Key=prefix+name,Body=data,ContentType='application/json')
        assert s3.get_object(Bucket=BUCKET,Key=prefix+name)['Body'].read()==data
    result={'phase':'snapshot_uploaded_verified','time':time.time(),'head':report['head'],
            'key':job['key'],'archive_bytes':report['archive_bytes'],'archive_sha256':report['archive_sha256'],
            'head_hash':proof['head']['hash'],'state_root':proof['head']['stateRoot'],
            'bal_hash':proof['head']['blockAccessListHash'],'qualifying_blocks':proof['qualifying_blocks']}
    (root/f'published-{c}.json').write_text(json.dumps(result,indent=2)+'\n')
    subprocess.run(ssh+['cat > /data/pbt-1/pipeline/status.json'],input=json.dumps(result),text=True,check=True)
    # The completed upload no longer needs its object-scoped signed URLs.
    subprocess.run(ssh+['rm /data/pbt-1/pipeline/upload-authorization.json'],check=True)
    print(json.dumps(result),flush=True)


if __name__=='__main__':main()
