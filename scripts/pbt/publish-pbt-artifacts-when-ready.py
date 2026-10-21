#!/usr/bin/env python3
"""Wait for native N verification, then run the reviewed publication sequence.

Only this controller has storage credentials. The unchanged worker publisher
receives scoped multipart URLs. No client startup, cleanup or genesis selection.
"""
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time

SCRIPT = Path(__file__).with_name('publish-pbt-artifacts.py')
SCRIPT_SHA = 'd98d6d7ab56dc18d9aabd6f33b85ed5d82de904239265b46486e8e1dbde18493'
ROOT = Path.home() / '.local/state/pbt-1-run/artifact-publication'


def publisher():
    assert hashlib.sha256(SCRIPT.read_bytes()).hexdigest() == SCRIPT_SHA, 'Publisher changed'
    spec = importlib.util.spec_from_file_location('artifact_publisher', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe(pub):
    code = '''import hashlib,json,pathlib,subprocess
b=pathlib.Path('/data/pbt-1')
def unit(name):
 return dict(x.split('=',1) for x in subprocess.check_output(['systemctl','show',name,'-p','LoadState','-p','ActiveState','-p','Result','-p','MainPID'],text=True).splitlines())
print(json.dumps({'export':unit('pbt-1-native-anchor-export'),
 'upload':unit('pbt-1-pbt-artifact-upload'),
 'export_proof':(b/'pbt-export-24453558/complete.json').is_file(),
 'upload_proof':(b/'pbt-artifact-publication/parts-complete.json').is_file(),
 'publisher_sha256':hashlib.sha256((b/'publish-pbt-artifacts.py').read_bytes()).hexdigest()}))
'''
    result = json.loads(pub.ssh(['python3', '-c', code]))
    assert result['publisher_sha256'] == SCRIPT_SHA, 'Remote publisher changed'
    return result


def phase_ready(observation, phase):
    unit = observation[phase]
    if unit['ActiveState'] in ('active', 'activating', 'deactivating'):
        assert unit['Result'] == 'success', 'Active unit reports an error'
        return False
    assert unit['ActiveState'] == 'inactive' and unit['Result'] == 'success', 'Predecessor failed'
    assert unit['MainPID'] == '0' and observation[phase + '_proof'], 'Missing completed predecessor proof'
    return True


def wait_for(pub, phase):
    while True:
        try:
            state = observe(pub)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pub.save(ROOT, 'auto-status.json', {'phase': 'waiting_for_observation', 'job': phase, 'time': time.time()})
            time.sleep(60)
            continue
        pub.save(ROOT, 'auto-status.json', {'phase': 'waiting_for_' + phase, 'observation': state, 'time': time.time()})
        if phase_ready(state, phase):
            return state
        time.sleep(60)


def action(name):
    assert hashlib.sha256(SCRIPT.read_bytes()).hexdigest() == SCRIPT_SHA, 'Publisher changed'
    with (ROOT / ('auto-' + name + '.log')).open('x') as log:
        subprocess.run(['/usr/bin/python3', str(SCRIPT), name], stdout=log,
                       stderr=subprocess.STDOUT, check=True)


def run(pub):
    assert not (ROOT / 'auto-started.json').exists(), 'Prior automatic attempt requires inspection'
    assert not (ROOT / 'authorization-started.json').exists(), 'Prior authorization requires inspection'
    pub.save(ROOT, 'auto-started.json', {'time': time.time(), 'publisher_sha256': SCRIPT_SHA})
    state = wait_for(pub, 'export')
    assert state['upload']['LoadState'] == 'not-found' and not state['upload_proof'], 'Prior upload requires inspection'
    pub.check()  # Full native result, metadata and file identity gates precede authorization.
    action('authorize')
    pub.ssh(['systemd-run', '--unit=pbt-1-pbt-artifact-upload', '--property=Type=exec',
             '--property=MemoryMax=4G', '--property=CPUQuota=400%', '--property=AllowedCPUs=0-3',
             '--property=UMask=0077', '--property=Restart=no',
             '/usr/bin/python3', '/data/pbt-1/publish-pbt-artifacts.py', 'stream'])
    wait_for(pub, 'upload')
    pub.save(ROOT, 'auto-status.json', {'phase': 'full_remote_checksum_readback', 'time': time.time()})
    action('finish')
    release = json.loads((ROOT / 'release.json').read_text())
    assert release['full_remote_sha256_verified'] is True and release['genesis_time'] is None
    pub.save(ROOT, 'auto-status.json', {'phase': 'published_verified', 'time': time.time()})


if __name__ == '__main__':
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    pub = publisher()
    with (ROOT / 'auto.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            run(pub)
        except Exception as exc:
            pub.save(ROOT, 'auto-status.json', {'phase': 'failed', 'error_class': type(exc).__name__, 'time': time.time()})
            raise SystemExit(type(exc).__name__ + ': inspect private publication evidence') from None
