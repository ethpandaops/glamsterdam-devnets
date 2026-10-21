#!/usr/bin/env python3
"""Controller handoff: wait for E1 H restore, then run its isolated startup once."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import time

ROOT = Path.home() / '.local/state/pbt-1-run/erigon-1-restored-qualification'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-i',
       str(Path.home() / '.ssh/devops_eth2_shared_key'), 'root@164.92.239.96']
OBSERVE = '''import json,pathlib,subprocess
base=pathlib.Path('/data/pbt-1')
def unit(name):
 text=subprocess.check_output(['systemctl','show',name,'-p','ActiveState','-p','MainPID','-p','Result'],text=True)
 return dict(line.split('=',1) for line in text.splitlines())
proof=base/'qualification/result.json'
print(json.dumps({'restore':unit('pbt-1-v3-head-restore'),
 'qualification':unit('pbt-1-worker-qualification'),
 'restore_complete':(base/'v3-head-restore/complete.json').exists(),
 'qualification_proof':json.loads(proof.read_text()) if proof.exists() else None}))
'''


def save(phase, **extra):
    temporary = ROOT / 'status.tmp'
    temporary.write_text(json.dumps(dict(phase=phase, time=time.time(), **extra), indent=2) + '\n')
    temporary.replace(ROOT / 'status.json')


def remote(args):
    return subprocess.check_output(SSH + [shlex.join(args)], stderr=subprocess.PIPE, timeout=60)


def main():
    ROOT.mkdir(mode=0o700, exist_ok=True)
    with (ROOT / 'started.json').open('x') as stream:
        json.dump({'time': time.time(), 'scope': 'Own isolated E1 startup after corrected H restore; no network launch'}, stream)
    launched = False
    while True:
        try:
            observation = json.loads(remote(['python3', '-c', OBSERVE]))
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            save('observation_unavailable', qualification_launch_attempted=launched)
            time.sleep(30)
            continue
        restore = observation['restore']
        qualification = observation['qualification']
        assert restore['ActiveState'] != 'failed' and restore['Result'] == 'success', 'Restore failed'
        if not launched:
            assert qualification['MainPID'] == '0' and observation['qualification_proof'] is None, 'Existing qualification requires inspection'
            if observation['restore_complete'] and restore['MainPID'] == '0' and restore['ActiveState'] == 'inactive':
                save('starting_isolated_qualification')
                # Claim once before sending: an ambiguous SSH result must not cause a retry.
                (ROOT / 'launch-attempted.json').write_text(json.dumps({'time': time.time()}) + '\n')
                output = remote(['systemd-run', '--unit=pbt-1-worker-qualification',
                                 '--property=Type=exec', '--property=Restart=no',
                                 '--property=UMask=0077', '/usr/bin/python3',
                                 '/data/pbt-1/qualify-restored-worker.py',
                                 '/data/pbt-1/qualification/job.json', '--from-verified-release'])
                (ROOT / 'launch.log').write_bytes(output)
                launched = True
            else:
                parent = subprocess.check_output(['systemctl', '--user', 'show',
                    'pbt-1-post-publication', '-p', 'ActiveState', '-p', 'MainPID'], text=True)
                parent = dict(line.split('=', 1) for line in parent.splitlines())
                assert parent['ActiveState'] != 'failed', 'Post-publication handoff failed'
                assert parent['MainPID'] != '0' or restore['MainPID'] != '0', 'No live process can complete the pending restore'
                save('waiting_for_restore', restore=restore, parent=parent)
        else:
            assert qualification['ActiveState'] != 'failed' and qualification['Result'] == 'success', 'Own startup failed'
            if qualification['MainPID'] == '0':
                proof = observation['qualification_proof']
                assert proof and proof['host'] == 'lighthouse-erigon-1'
                assert proof['status'] == 'startup_checks_passed' and proof['head'] == 24503958
                assert proof['memory_gib'] == 32 and proof['cpus'] == 8
                assert proof['preparation_path'] == 'restored_verified_H_release'
                assert proof['genesis_time'] is None and not proof['stopped_state']['Running']
                (ROOT / 'result.json').write_text(json.dumps(proof, indent=2) + '\n')
                save('own_H_startup_passed', recovery_replacement_pending=True, network_launched=False)
                return
            save('isolated_qualification_running', service=qualification)
        time.sleep(30)


if __name__ == '__main__':
    os.umask(0o077)
    try:
        main()
    except Exception as exc:
        save('failed', error_class=type(exc).__name__)
        raise
