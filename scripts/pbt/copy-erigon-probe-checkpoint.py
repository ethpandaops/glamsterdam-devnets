#!/usr/bin/env python3
"""Copy the preserved Erigon checkpoint using a scoped, read-only SSH key."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path('/data/pbt-1/io-probe')
DATA=Path('/data/pbt-1/erigon')


def save(value):
    tmp=ROOT/'checkpoint-copy-status.json.tmp'
    tmp.write_text(json.dumps(value,indent=2)+'\n')
    tmp.replace(ROOT/'checkpoint-copy-status.json')


def main():
    lock=(ROOT/'checkpoint-copy.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert not (ROOT/'checkpoint-copy-status.json').exists(), 'Inspect existing copy; no automatic restart'
    proof=json.loads((ROOT/'maintenance-checkpoint.json').read_text())
    assert proof['container_paused_during_copy']
    assert proof['chaindata_sha256']=='b799a0df4b18dcbd5c662640eca94c6b3913027a43d1375dc8aceb4766c725ce'
    DATA.mkdir(mode=0o755,exist_ok=True)
    assert DATA.resolve()==DATA and not any(DATA.iterdir()), 'Empty isolated destination required'
    expected=proof['linked_immutable_bytes']+proof['copied_mutable_bytes']
    assert shutil.disk_usage(DATA).free>expected+200*1024**3
    assert not subprocess.check_output(['docker','ps','-q'],text=True).strip(), 'Probe must not run client containers during copy'
    command=['rsync','-aHXS','--numeric-ids','--partial','--info=progress2','--outbuf=L',
             '--bwlimit=262144','--exclude=/chaindata/mdbx.lck','-e',
             'ssh -i /data/pbt-1/io-probe/checkpoint-read-key -o UserKnownHostsFile=/data/pbt-1/io-probe/source-known-hosts -o StrictHostKeyChecking=yes -o BatchMode=yes',
             'root@10.35.0.2:/',str(DATA)+'/']
    result={'started_at':time.time(),'phase':'copying','source_checkpoint':proof['path'],
            'source_ip':'10.35.0.2','destination':str(DATA),'expected_file_count':proof['files'],
            'expected_bytes':expected,'bandwidth_limit_KiB_per_second':262144}
    with (ROOT/'checkpoint-copy.log').open('w') as log:
        proc=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        result['rsync_pid']=proc.pid;save(result)
        rc=proc.wait()
    assert rc==0, ('Checkpoint transfer failed; inspect log',rc)
    result.update(phase='verifying',transfer_finished_at=time.time());save(result)
    files=sum(1 for base,dirs,names in os.walk(DATA) for name in names)
    assert files==proof['files'], (files,proof['files'])
    digest=hashlib.sha256()
    with (DATA/'chaindata/mdbx.dat').open('rb') as db:
        for chunk in iter(lambda:db.read(16*1024**2),b''):digest.update(chunk)
    assert digest.hexdigest()==proof['chaindata_sha256'], 'Copied MDBX differs from preserved checkpoint'
    result.update(phase='copied_verified',finished_at=time.time(),file_count=files,
                  chaindata_sha256=digest.hexdigest(),client_restart_verification_pending=True)
    save(result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    try:main()
    except Exception as exc:
        path=ROOT/'checkpoint-copy-status.json'
        prior=json.loads(path.read_text()) if path.exists() else {}
        prior.update(phase='failed',failed_at=time.time(),error=str(exc));save(prior)
        raise
