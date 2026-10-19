#!/usr/bin/env python3
"""Restore validated native BAL sidecars after the final clean Erigon shutdown."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from pipeline_rpc import ANCHOR, ROOT, save

REVISION='8c1e3893d77d230720d172f1492d95b5777a862c'
NAME='pbt-1-erigon-execution'
BACKUP=NAME+'-before-bal-retention'
FLAG='--exec.no-prune=true'


def inspect(name):
    return json.loads(subprocess.check_output(['docker','inspect',name]))[0]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workload-blocks',type=int,required=True)
    args=parser.parse_args()
    lock=(ROOT/'bal-retention.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    plan=json.loads((ROOT/'workload.json').read_text())['v2']
    assert args.workload_blocks+3==plan['final_records']
    target=ANCHOR+plan['final_records']
    before=json.loads((ROOT/f'audit-{args.workload_blocks}-before.json').read_text())['head']
    assert int(before['number'],16)==target
    container=inspect(NAME);state=container['State']
    assert not state['Running'] and not state['OOMKilled'] and state['ExitCode'] in (0,130),state
    assert container['HostConfig']['NetworkMode']=='none'
    command=json.loads((ROOT/'client-command.json').read_text())
    image=container['Config']['Image'];image_index=command.index(image)
    assert command[:3]==['docker','run','-d'] and NAME in command
    assert command[image_index+1:]==container['Config']['Cmd'], 'Saved command differs from stopped container'
    marker=ROOT/'bal-retention-prepared.json'
    if marker.exists():
        prior=json.loads(marker.read_text())
        assert prior['head']==target and FLAG in command
        assert prior['head_hash']==before['hash'] and prior['state_root']==before['stateRoot']
        print('Erigon BAL retention already prepared',flush=True);return
    db=Path('/data/pbt-1/erigon')
    for cid in subprocess.check_output(['docker','ps','-q'],text=True).splitlines():
        for mount in inspect(cid)['Mounts']:
            path=Path(mount['Source'])
            assert not (path==db or path in db.parents or db in path.parents), 'Database mounted by running container'
    assert shutil.disk_usage(db).free>100*1024**3, 'Less than 100 GiB free for sidecar restoration'
    binary=Path('/data/pbt-1/erigon-bal-backfill')
    build=json.loads(binary.with_suffix('.json').read_text())
    assert build['client_revision']==REVISION
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==build['binary_sha256']
    if FLAG not in command:
        exists=subprocess.run(['docker','inspect',BACKUP],capture_output=True).returncode==0
        assert not exists, 'Backup container already exists; inspect partial preparation'
    report_path=ROOT/'erigon-bal-backfill.json'
    subprocess.run([str(binary),'--db',str(db/'chaindata'),'--records',str(ROOT/'blocks'),
                    '--start',str(ANCHOR+1),'--end',str(target),'--report',str(report_path)],
                   env={**os.environ,'GOMEMLIMIT':'4GiB'},check=True)
    result=json.loads(report_path.read_text())
    assert not result['dry_run'] and result['verified_records']==plan['final_records']
    assert result['written_sidecars']+result['existing_sidecars']==plan['final_records']
    assert result['start']==ANCHOR+1 and result['end']==result['head']==target
    assert result['head_hash']==before['hash'] and result['state_root']==before['stateRoot']
    if FLAG not in command:
        save(ROOT/'client-command-before-bal-retention.json',command)
        subprocess.run(['docker','rename',NAME,BACKUP],check=True)
        command.append(FLAG)
        # Create the identical pinned profile with pruning disabled. reopen.py
        # starts it and performs the exhaustive API audit before the final stop.
        create=['docker','create',*command[3:]]
        subprocess.run(create,check=True)
        save(ROOT/'client-command.json',command)
        current=inspect(NAME)
        assert current['Config']['Image']==image and current['HostConfig']['NetworkMode']=='none'
        assert current['HostConfig']['Binds']==container['HostConfig']['Binds']
        assert current['HostConfig']['Memory']==container['HostConfig']['Memory']
        assert current['Config']['Cmd']==container['Config']['Cmd']+[FLAG]
    save(ROOT/'erigon-bal-backfill-build.json',build)
    save(marker,{'time':time.time(),'head':target,'head_hash':result['head_hash'],
                 'state_root':result['state_root'],'image':image,'pruning_disabled':True,
                 'binary_sha256':build['binary_sha256'],'sidecars':result['verified_records']})
    print(f'Erigon: {result["verified_records"]} native BAL sidecars prepared; restart/API audit remains required',flush=True)


if __name__=='__main__':main()
