#!/usr/bin/env python3
"""Prepare the replay archive early; finalize delivery only after all four snapshots pass."""
import argparse
import fcntl
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError
from monitor import HOSTS
from storage import client,BUCKET,PREFIX
from bundle_records import index_records, index_digest

ROOT=Path.home()/'.local/state/pbt-1-run'
REPO=Path(__file__).resolve().parents[2]


def verify_archive(s3,key,expected_size,expected_sha256):
    before=s3.head_object(Bucket=BUCKET,Key=key)
    assert before['ContentLength']==expected_size
    digest=hashlib.sha256();size=0
    with s3.get_object(Bucket=BUCKET,Key=key)['Body'] as body:
        for chunk in iter(lambda:body.read(8*1024**2),b''):digest.update(chunk);size+=len(chunk)
    after=s3.head_object(Bucket=BUCKET,Key=key)
    assert before['ETag']==after['ETag'] and after['ContentLength']==size==expected_size
    assert digest.hexdigest()==expected_sha256, 'Replay archive readback differs'
    return {'key':key,'bytes':size,'sha256':digest.hexdigest(),'etag':after['ETag'],'verification':'full remote readback'}


def prepare_bundle(s3):
    ready_path = ROOT/'replay-bundle-ready.json'
    assert not ready_path.exists(), 'Bundle already prepared; use final publication'
    plan=json.loads((ROOT/'workload.json').read_text());v=plan['v2']
    target=24452538+v['final_records']
    assert v['final_records']-v['qualifying_start_index']==50400
    key=PREFIX+'replay/snapshot.tar.zst'
    try:s3.head_object(Bucket=BUCKET,Key=key)
    except ClientError as exc:
        if exc.response['Error']['Code'] not in ('404','NoSuchKey','NotFound'):raise
    else:raise RuntimeError('Bundle destination already exists; inspect before retrying')
    entries=index_records(ROOT,24452539,target)
    # Compare every compressed input byte with the producer's audited records.
    # Only read-only hashing code crosses SSH; storage credentials remain here.
    source_args=['python3','-','--root','/data/pbt-1/pipeline','--first','24452539',
                 '--last',str(target),'--proof',f'/data/pbt-1/pipeline/reopen-{v["final_records"]-3}-complete.json']
    source=json.loads(subprocess.check_output(['ssh','-i',str(Path.home()/'.ssh/devops_eth2_shared_key'),
        '-o','BatchMode=yes','-o','ConnectTimeout=15','root@'+HOSTS['geth'][0],shlex.join(source_args)],
        input=Path(__file__).with_name('bundle_records.py').read_text(),text=True))
    assert source['index_sha256']==index_digest(entries) and source['records']==v['final_records'], 'Producer/controller record mismatch'
    proof=source['proof']
    assert proof['client']=='geth' and proof['stopped'] and proof['verified_bal_bodies']==v['final_records']
    assert proof['qualifying_blocks']==50400 and int(proof['head']['number'],16)==target
    last=json.loads(gzip.decompress((ROOT/entries[-1]['file']).read_bytes()))
    assert last['number']==target
    for record_field,header_field in [('hash','hash'),('state_root','stateRoot'),('bal_hash','blockAccessListHash')]:
        assert last[record_field]==proof['head'][header_field]
    staging=ROOT/'replay-bundle-input'
    staging.mkdir(exist_ok=False)
    genesis=REPO/'network-configs/msf-2/metadata/genesis.json'
    genesis_data=json.loads(genesis.read_text())
    genesis_data['alloc']={('0x'+k if not k.startswith('0x') else k):v for k,v in genesis_data['alloc'].items()}
    source_bytes=json.dumps(genesis_data).encode()
    artifacts=[]
    for name in ['workload.json','source-genesis.json','8037-trace-calibration.json','packing-adjustment-before.json','packing-adjustment-complete.json']:
        data=source_bytes if name=='source-genesis.json' else (ROOT/name).read_bytes()
        (staging/name).write_bytes(data)
        artifacts.append({'file':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    manifest={'version':2,'generated_at':time.time(),'network':'pbt-1','source_anchor':24452538,
              'qualifying_anchor':24452538+v['qualifying_start_index'],'head':target,
              'preparation_blocks':v['qualifying_start_index'],'qualifying_blocks':50400,
              'qualifying_chain_seconds':50400*12,'workload':plan,
              'manifest_kind':'replay_artifact','delivery_complete':False,'source_verification':source,
              'expected_commitments':{k:proof['head'][f] for k,f in [('head_hash','hash'),('state_root','stateRoot'),('bal_hash','blockAccessListHash')]},
              'genesis_sha256':hashlib.sha256(source_bytes).hexdigest(),
              'repository_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
              'records':entries,'artifacts':artifacts,'bundle_layout':'blocks/<height>.json.gz contains payload, forkchoice, BAL and gas accounting; see workload.json for the preparation prefix and qualifying range. Final snapshot delivery is established separately by _snapshot_manifest.json.'}
    manifest_bytes=(json.dumps(manifest,indent=2)+'\n').encode()
    (staging/'manifest.json').write_bytes(manifest_bytes)
    print(json.dumps({'phase':'bundle_inputs_verified','records':len(entries),'input_bytes':source['bytes']}),flush=True)
    # Streaming avoids needing a second full copy of the bundle on the controller.
    # The writer checks each indexed hash again before adding those exact bytes.
    tar=subprocess.Popen([sys.executable,str(Path(__file__).with_name('bundle_records.py')),
        '--root',str(ROOT),'--staging',str(staging)],stdout=subprocess.PIPE)
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
    print(json.dumps({'phase':'bundle_uploaded_readback_pending','bytes':stream.size}),flush=True)
    archive=verify_archive(s3,key,stream.size,stream.sha.hexdigest())
    report={'phase':'replay_bundle_verified','time':time.time(),'head':target,
            'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
            'replay_bundle':archive}
    temporary=ready_path.with_suffix('.tmp');temporary.write_text(json.dumps(report,indent=2)+'\n');temporary.replace(ready_path)
    print(json.dumps(report),flush=True)
    return report


def validate_delivery(manifest,ready,snapshots):
    assert ready['phase']=='replay_bundle_verified' and ready['head']==manifest['head']
    assert ready['replay_bundle']['verification']=='full remote readback'
    assert ready['replay_bundle']['key']==PREFIX+'replay/snapshot.tar.zst'
    assert set(snapshots)==set(HOSTS), 'All four verified snapshots are required'
    for value in snapshots.values():
        assert value['phase']=='snapshot_uploaded_verified' and value['head']==manifest['head']
        for field in ('head_hash','state_root','bal_hash'):
            assert value[field]==manifest['expected_commitments'][field],field


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args()
    with (ROOT/'publish-bundle.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        publish(args)


def publish(args):
    s3=client()
    if args.prepare_only:
        prepare_bundle(s3)
        return
    # Missing snapshots fail before any bundle upload or final metadata write.
    snapshots={c:json.loads((ROOT/f'published-{c}.json').read_text()) for c in HOSTS}
    ready_path=ROOT/'replay-bundle-ready.json'
    ready=json.loads(ready_path.read_text()) if ready_path.exists() else prepare_bundle(s3)
    manifest_bytes=(ROOT/'replay-bundle-input/manifest.json').read_bytes()
    assert hashlib.sha256(manifest_bytes).hexdigest()==ready['manifest_sha256']
    manifest=json.loads(manifest_bytes)
    validate_delivery(manifest,ready,snapshots)
    assert manifest['workload']==json.loads((ROOT/'workload.json').read_text()), 'Workload changed after bundle preparation'
    info=s3.head_object(Bucket=BUCKET,Key=ready['replay_bundle']['key'])
    assert info['ContentLength']==ready['replay_bundle']['bytes'] and info['ETag']==ready['replay_bundle']['etag']
    manifest.pop('records');manifest.pop('manifest_kind');manifest.pop('delivery_complete')
    manifest['snapshots']=snapshots
    manifest['replay_bundle']=ready['replay_bundle']
    manifest['replay_manifest_sha256']=ready['manifest_sha256']
    plan=manifest['workload']
    key=ready['replay_bundle']['key']
    target=manifest['head']
    public_base='https://shadowfork-images.ethpandaops.io/'
    manifest['urls']={c:public_base+x['key'] for c,x in snapshots.items()}
    manifest['urls']['replay']=public_base+key
    calibration=json.loads((ROOT/'replay-bundle-input/8037-trace-calibration.json').read_text())
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
