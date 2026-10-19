#!/usr/bin/env python3
"""Relay completed replay records through the controller; no SSH key on source VMs."""
import concurrent.futures
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import time
from monitor import HOSTS

ROOT = Path.home() / '.local/state/pbt-1-run'
SSH = 'ssh -i /home/ubuntu/.ssh/devops_eth2_shared_key -o BatchMode=yes -o ConnectTimeout=15'


def run(args):
    subprocess.run(args, check=True, timeout=300)


def push(client):
    host = 'root@' + HOSTS[client][0]
    run(SSH.split() + [host, 'mkdir -p /data/pbt-1/pipeline/blocks'])
    run(['rsync', '-a', '--ignore-existing', '--include=*.json.gz', '--exclude=*', '-e', SSH,
         str(ROOT / 'blocks')+'/', host+':/data/pbt-1/pipeline/blocks/'])


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    lock = (ROOT / 'relay.lock').open('w'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert shutil.disk_usage(ROOT).free > 30*10**9, 'Controller disk below 30 GB'
    (ROOT / 'blocks').mkdir(exist_ok=True)
    run(['rsync', '-a', '--ignore-existing', '--include=*.json.gz', '--exclude=*', '-e', SSH,
         'root@'+HOSTS['geth'][0]+':/data/pbt-1/pipeline/blocks/', str(ROOT / 'blocks')+'/'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(push, ['besu','erigon','nethermind']):
            pass
    files = sorted((ROOT / 'blocks').glob('*.json.gz'))
    report = {'time':time.time(), 'files':len(files), 'last':files[-1].name if files else None}
    tmp=ROOT/'relay-status.json.tmp'
    tmp.write_text(json.dumps(report)+'\n');tmp.replace(ROOT/'relay-status.json')
    print(json.dumps(report),flush=True)


if __name__ == '__main__':
    main()
