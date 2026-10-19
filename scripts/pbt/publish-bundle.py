#!/usr/bin/env python3
"""Publish and fully read back the payload/BAL bundle after all four snapshots pass."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError
from monitor import HOSTS
from storage import client,BUCKET,PREFIX

ROOT=Path.home()/'.local/state/pbt-1-run'
REPO=Path(__file__).resolve().parents[2]


def main():
    plan=json.loads((ROOT/'workload.json').read_text());v=plan['v2']
    snapshots={c:json.loads((ROOT/f'published-{c}.json').read_text()) for c in HOSTS}
    target=24452538+v['final_records']
    assert all(x['phase']=='snapshot_uploaded_verified' and x['head']==target for x in snapshots.values())
    for field in ['head_hash','state_root','bal_hash']:
        assert len({x[field] for x in snapshots.values()})==1,field
    files=sorted((ROOT/'blocks').glob('*.json.gz'))
    assert [int(x.name.split('.')[0]) for x in files]==list(range(24452539,target+1))
    entries=[]
    for path in files:
        data=path.read_bytes()
        entries.append({'file':'blocks/'+path.name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    genesis=REPO/'network-configs/msf-2/metadata/genesis.json'
    source=json.loads(genesis.read_text())
    source['alloc']={('0x'+k if not k.startswith('0x') else k):v for k,v in source['alloc'].items()}
    source_bytes=json.dumps(source).encode()
    (ROOT/'source-genesis.json').write_bytes(source_bytes)
    manifest={'version':2,'generated_at':time.time(),'network':'pbt-1','source_anchor':24452538,
              'qualifying_anchor':24452538+v['qualifying_start_index'],'head':target,
              'preparation_blocks':v['qualifying_start_index'],'qualifying_blocks':50400,
              'qualifying_chain_seconds':50400*12,'workload':plan,'snapshots':snapshots,
              'genesis_sha256':hashlib.sha256(source_bytes).hexdigest(),
              'repository_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
              'records':entries,'bundle_layout':'blocks/<height>.json.gz contains payload, forkchoice, BAL and gas accounting; see workload.json for the preparation prefix and qualifying range'}
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    s3=client();key=PREFIX+'replay/snapshot.tar.zst'
    try:s3.head_object(Bucket=BUCKET,Key=key)
    except ClientError as exc:
        if exc.response['Error']['Code'] not in ('404','NoSuchKey','NotFound'):raise
    else:raise RuntimeError('Bundle destination already exists; inspect before retrying')
    # Streaming avoids needing a second full copy of the bundle on the controller.
    tar=subprocess.Popen(['tar','--sort=name','-C',str(ROOT),'-cf','-','blocks','workload.json','manifest.json','source-genesis.json','8037-trace-calibration.json'],stdout=subprocess.PIPE)
    zstd=subprocess.Popen(['zstd','-1','-T2','-q'],stdin=tar.stdout,stdout=subprocess.PIPE);tar.stdout.close()
    class Stream:
        def __init__(self):self.sha=hashlib.sha256();self.size=0
        def read(self,n=-1):
            data=zstd.stdout.read(n);self.sha.update(data);self.size+=len(data);return data
    stream=Stream()
    try:
        s3.upload_fileobj(stream,BUCKET,key,ExtraArgs={'ContentType':'application/zstd'},
              Config=TransferConfig(multipart_threshold=256*1024**2,multipart_chunksize=256*1024**2,max_concurrency=4))
        assert zstd.wait()==0 and tar.wait()==0,'Bundle tar/zstd failed'
    finally:
        if zstd.poll() is None:zstd.terminate()
        if tar.poll() is None:tar.terminate()
    assert s3.head_object(Bucket=BUCKET,Key=key)['ContentLength']==stream.size
    digest=hashlib.sha256();size=0
    with s3.get_object(Bucket=BUCKET,Key=key)['Body'] as body:
        for chunk in iter(lambda:body.read(8*1024**2),b''):digest.update(chunk);size+=len(chunk)
    assert size==stream.size and digest.hexdigest()==stream.sha.hexdigest()
    manifest.pop('records')
    manifest['replay_bundle']={'key':key,'bytes':size,'sha256':digest.hexdigest(),'verification':'full remote readback'}
    public_base='https://shadowfork-images.ethpandaops.io/'
    manifest['urls']={c:public_base+x['key'] for c,x in snapshots.items()}
    manifest['urls']['replay']=public_base+key
    calibration=json.loads((ROOT/'8037-trace-calibration.json').read_text())
    for name,value in [('workload',plan),('manifest',manifest),('8037_calibration',calibration)]:
        data=json.dumps(value,indent=2).encode();object_key=PREFIX+f'_snapshot_{name}.json'
        s3.put_object(Bucket=BUCKET,Key=object_key,Body=data,ContentType='application/json')
        assert s3.get_object(Bucket=BUCKET,Key=object_key)['Body'].read()==data
    # The gateway's browser integrity check rejects Python's default user agent;
    # curl also verifies that the new public layout is actually downloadable.
    for name,url in manifest['urls'].items():
        headers=subprocess.check_output(['curl','-fsSI','--max-time','60',url],text=True)
        assert '200' in headers.splitlines()[0],(name,headers)
    manifest['phase']='delivery_complete';manifest['verified_at']=time.time()
    (ROOT/'delivery-complete.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'phase':'delivery_complete','head':target,'urls':manifest['urls']}),flush=True)


if __name__=='__main__':main()
