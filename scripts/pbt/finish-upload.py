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
             '_snapshot_integrity.json':report,'_snapshot_reopen.json':proof,
             '_snapshot_startup.json':{'preparation_command':read('client-command.json'),
                 'notes':'The reopened proof uses this pinned preparation profile. Supply the bundled source genesis; adjust host paths and resource limits for consumers. Nethermind requires FlatDB and TTD=0; Erigon uses snap.stop.'}}
    if c=='nethermind':
        cleanup=json.loads(subprocess.check_output(ssh+['cat /data/pbt-1/nethermind-flatdb-cleanup/complete.json']))
        assert cleanup['head']==plan['anchor']==24452538 and cleanup['image']==proof['image']
        assert cleanup['patricia_bytes_after']<16*1024**2
        assert cleanup['reclaimed_bytes']==cleanup['patricia_bytes_before']-cleanup['patricia_bytes_after']>0
        objects['_snapshot_flatdb_cleanup.json']=cleanup
        metadata['pbt']['patricia_cleanup_evidence']=prefix+'_snapshot_flatdb_cleanup.json'
    if c=='erigon':
        pilot_present=subprocess.run(ssh+['test -d /data/pbt-1/native-source-pilot']).returncode
        assert pilot_present in (0,1), 'Could not inspect native replay provenance'
        if pilot_present==0:
            pilot=json.loads(subprocess.check_output(ssh+['cat /data/pbt-1/native-source-pilot/complete.json']))
            build=json.loads(subprocess.check_output(ssh+['cat /data/pbt-1/erigon-native-batch-build-report.json']))
            assert pilot['pinned_reopen_verified'] and pilot['normal_durability']
            assert pilot['pilot_blocks']==192 and pilot['image']==proof['image']
            assert int(pilot['head']['number'],16)<=report['head']
            assert pilot['binary_sha256']==build['sha256']
            assert build['source']['base_commit']=='8c1e3893d77d230720d172f1492d95b5777a862c'
            objects['_snapshot_native_replay_probe.json']=pilot
            objects['_snapshot_native_replay_build.json']=build
            metadata['pbt']['native_replay']={
                'notes':'A bounded replay comparison used a custom native build. The database then passed pinned-image reopen validation; final snapshot validation also uses the pinned image.',
                'probe_evidence':prefix+'_snapshot_native_replay_probe.json',
                'build_evidence':prefix+'_snapshot_native_replay_build.json'}
        native_present=subprocess.run(ssh+['test -d /data/pbt-1/native-replay']).returncode
        assert native_present in (0,1), 'Could not inspect continuous native replay provenance'
        if native_present==0:
            native=json.loads(subprocess.check_output(ssh+['cat /data/pbt-1/native-replay/complete.json']))
            build=json.loads(subprocess.check_output(ssh+['cat /data/pbt-1/native-replay/build.json']))
            assert native['pinned_reopen_verified'] and native['normal_durability']
            assert native['end']==report['head'] and native['head']['hash']==proof['head']['hash']
            assert native['image']==proof['image'] and native['binary_sha256']==build['sha256']
            assert native['validated_blocks']==native['end']-native['start']+1>0
            objects['_snapshot_native_replay_complete.json']=native
            objects['_snapshot_native_replay_continuous_build.json']=build
            metadata['pbt']['native_replay']['continuous']={
                'evidence':prefix+'_snapshot_native_replay_complete.json',
                'build_evidence':prefix+'_snapshot_native_replay_continuous_build.json',
                'notes':'The remaining replay used this native build, with VALID payloads and matching commitments for each block; final validation reopened the pinned image.'}
        backfill=read('erigon-bal-backfill.json');retention=read('bal-retention-prepared.json')
        assert not backfill['dry_run'] and backfill['verified_records']==v['final_records']
        assert backfill['written_sidecars']+backfill['existing_sidecars']==v['final_records']
        assert backfill['head']==report['head'] and backfill['head_hash']==proof['head']['hash']
        assert backfill['state_root']==proof['head']['stateRoot'] and retention['pruning_disabled']
        objects['_snapshot_bal_backfill.json']=backfill
        objects['_snapshot_bal_backfill_build.json']=read('erigon-bal-backfill-build.json')
        metadata['pbt']['bal_retention']={'mode':'Native sidecars restored from validated replay inputs after clean stop',
            'required_flag':'--exec.no-prune=true','evidence':prefix+'_snapshot_bal_backfill.json'}
        command=objects['_snapshot_startup.json']['preparation_command']
        if '--exec.no-background-maintenance=true' in command:
            maintenance=read('maintenance-restart-complete.json')
            assert maintenance['same_head_and_sampled_bals_verified'] and maintenance['image']==proof['image']
            assert maintenance['head']<=report['head']
            assert all(flag in command for flag in maintenance['flags'])
            objects['_snapshot_maintenance_restart.json']=maintenance
            metadata['pbt']['background_maintenance']={
                'during_preparation':'Disabled to avoid a large merge backlog during the bounded replay run',
                'profile_flag':'--exec.no-background-maintenance=true',
                'evidence':prefix+'_snapshot_maintenance_restart.json'}
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
