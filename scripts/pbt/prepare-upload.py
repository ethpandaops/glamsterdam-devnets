#!/usr/bin/env python3
"""Authorize one new immutable snapshot object after its full restart/BAL gate."""
import argparse
import json
from pathlib import Path
import subprocess
from botocore.exceptions import ClientError
from monitor import HOSTS
from storage import client,BUCKET,PREFIX


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('client',choices=HOSTS)
    a=p.parse_args();c=a.client
    ssh=['ssh','-i',str(Path.home()/'.ssh/devops_eth2_shared_key'),'-o','BatchMode=yes','root@'+HOSTS[c][0]]
    root=Path.home()/'.local/state/pbt-1-run'
    plan=json.loads((root/'workload.json').read_text())['v2'];n=plan['final_records']-3
    proof=json.loads(subprocess.check_output(ssh+[f'cat /data/pbt-1/pipeline/reopen-{n}-complete.json']))
    head=int(proof['head']['number'],16)
    assert proof['stopped'] and proof['verified_bal_bodies']==plan['final_records'] and head==24452538+plan['final_records']
    assert proof['qualifying_blocks']==50400
    key=f'{PREFIX}{c}/{head}/snapshot.tar.zst'
    path=root/f'upload-{c}.json'
    if path.exists():raise RuntimeError('Upload already authorized; inspect the existing multipart job before retrying')
    s3=client()
    try:s3.head_object(Bucket=BUCKET,Key=key)
    except ClientError as exc:
        if exc.response['Error']['Code'] not in ('404','NoSuchKey','NotFound'):raise
    else:raise RuntimeError('Immutable destination already exists')
    upload=s3.create_multipart_upload(Bucket=BUCKET,Key=key,ContentType='application/zstd',
               Metadata={'pbt-head':str(head),'client':c,'state-root':proof['head']['stateRoot']})['UploadId']
    job={'client':c,'head':head,'key':key,'upload_id':upload}
    path.write_text(json.dumps(job)+'\n');path.chmod(0o600)
    job['urls']=[s3.generate_presigned_url('upload_part',Params={'Bucket':BUCKET,'Key':key,'UploadId':upload,'PartNumber':i},ExpiresIn=86400)
                 for i in range(1,8001)]
    subprocess.run(ssh+['umask 077; cat > /data/pbt-1/pipeline/upload-authorization.json'],input=json.dumps(job),text=True,check=True)
    (root/f'upload-{c}-authorized.json').write_text(json.dumps({'key':key,'head':head})+'\n')
    print(f'Authorized only multipart PUTs for {key}; account credentials stay on controller.')


if __name__=='__main__':main()
