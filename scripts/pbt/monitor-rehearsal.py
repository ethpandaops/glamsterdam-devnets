#!/usr/bin/env python3
"""Read-only 15-minute monitoring of the full-week Erigon preparation."""
import json
from pathlib import Path
import subprocess
import time

ROOT = Path.home() / '.local/state/pbt-1-run/rehearsal'
REMOTE = r'''
import json,pathlib,shutil,subprocess,time
root=pathlib.Path('/data/pbt-1/rehearsal-24453558')
name='pbt-1-erigon-rehearsal-snapshot'
state=json.loads(subprocess.check_output(['docker','inspect',name]))[0]['State']
logs=subprocess.run(['docker','logs','--tail','8',name],capture_output=True,text=True)
build=pathlib.Path('/data/pbt-1/rehearsal-tools/build-report.json')
anchor=root/'anchor-preparation/status.json'
upgrade=pathlib.Path('/data/pbt-1/v3-source-upgrade/status.json')
print(json.dumps({'time':time.time(),'restore':{k:state[k] for k in ('Running','ExitCode','OOMKilled','StartedAt')},
 'restore_done':(root/'snapshot-fetcher/done').exists(),
 'restore_log_tail':(logs.stdout+logs.stderr).splitlines()[-8:],
 'available_bytes':shutil.disk_usage(root).free,
 'build':json.loads(build.read_text()) if build.exists() else None,
 'anchor_preparation':json.loads(anchor.read_text()) if anchor.exists() else None,
 'v3_upgrade':json.loads(upgrade.read_text()) if upgrade.exists() else None}))
'''


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    result = {'time': time.time(), 'alerts': []}
    try:
        output = subprocess.run(
            ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-i',
             str(Path.home() / '.ssh/devops_eth2_shared_key'),
             'root@164.92.239.96', 'python3 -'],
            input=REMOTE, capture_output=True, text=True, check=True, timeout=45)
        result.update(json.loads(output.stdout))
        state = result['restore']
        if not state['Running'] and (state['ExitCode'] != 0 or not result['restore_done']):
            result['alerts'].append('Restore stopped without successful completion')
        if state['OOMKilled']:
            result['alerts'].append('Restore OOM')
        if result['available_bytes'] < 100_000_000_000:
            result['alerts'].append('Less than 100 GB available; inspect before replay/conversion')
        if result['build'] and result['build']['phase'] == 'failed':
            result['alerts'].append('Build or compatibility fixture failed')
        preparation = result.get('anchor_preparation') or {}
        if preparation.get('phase') == 'failed':
            result['alerts'].append('Anchor preparation: ' + preparation.get('error', 'failed'))
        upgrade = result.get('v3_upgrade') or {}
        if upgrade.get('phase') == 'failed':
            result['alerts'].append('V3 source upgrade: ' + upgrade.get('error', 'failed'))
        publication = Path.home() / '.local/state/pbt-1-run/v3-source/status.json'
        if publication.exists():
            result['v3_publication'] = json.loads(publication.read_text())
            if result['v3_publication'].get('phase') == 'failed':
                result['alerts'].append('V3 publication controller needs inspection')
    except Exception as exc:
        result['alerts'].append(str(exc))
    temporary = ROOT / 'latest.tmp'
    temporary.write_text(json.dumps(result, indent=2) + '\n')
    temporary.replace(ROOT / 'latest.json')
    with (ROOT / 'history.jsonl').open('a') as stream:
        stream.write(json.dumps(result) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
