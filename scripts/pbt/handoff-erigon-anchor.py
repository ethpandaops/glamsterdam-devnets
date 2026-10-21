#!/usr/bin/env python3
"""Wait for the verified, stopped older exporter, then reconstruct N offline.

Default checks only. --wait waits for existing processes, validates their
evidence, archives the instruction-review hold, and invokes the reviewed native
replay/stage driver once. No genesis or PBT activation time is chosen.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import time

BASE = Path('/data/pbt-1')
CONTROL = BASE / 'rehearsal-24453558/anchor-preparation'
UPGRADE = BASE / 'v3-source-upgrade'
DRIVER = BASE / 'prepare-erigon-anchor.py'
DRIVER_SHA = 'bb62206ba8a679877c42ec12dd00496e42809d4511cbd8ba23a5425444d46b6a'
HOLD = CONTROL / 'instruction-review-hold.json'
UNITS = ('pbt-1-v3-source-upgrade-v3', 'pbt-1-v3-source-qualification', 'pbt-1-v3-source-reopen')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def unit(name):
    return dict(line.split('=', 1) for line in subprocess.check_output([
        'systemctl', 'show', name, '-p', 'ActiveState', '-p', 'MainPID', '-p', 'Result'],
        text=True).splitlines())


def require_stopped_success(states):
    for name, value in states.items():
        assert value['MainPID'] == '0' and value['ActiveState'] == 'inactive', (name, value)
        assert value['Result'] == 'success', (name, value)


def check():
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    require_stopped_success({name: unit(name) for name in UNITS})
    assert sha(DRIVER) == DRIVER_SHA
    assert not (CONTROL / 'started.json').exists(), 'Prior anchor attempt requires review'
    assert not (CONTROL / 'handoff-release.json').exists(), 'Handoff already released'
    assert HOLD.exists(), 'Expected instruction-review hold is missing'
    assert 'Legacy-to-v3 and exact export pin' in read(HOLD)['reason']
    spec = importlib.util.spec_from_file_location('anchor', DRIVER)
    anchor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(anchor)
    proof = anchor.require_v3_source()
    prefix = anchor.verify_prefix()
    assert prefix['target_hash'] == '0x331c54fd1b37302697157dec30d2a1e0a13682843301f60d8ebac004f8bc4155'
    assert anchor.recovery_ready(), 'Recovery archive not verified'
    assert anchor.shutil.disk_usage(anchor.RESTORE).free > 300_000_000_000
    before, after = read(UPGRADE / 'native-before.json'), read(UPGRADE / 'native-after.json')
    assert before['head'] == after['head'] == proof['head']
    assert read(UPGRADE / 'status.json')['phase'] == 'v3_source_verified_stopped'
    return {'time': time.time(), 'status': 'ready_for_offline_anchor_preparation',
            'source_block': anchor.ANCHOR, 'target_block': anchor.TARGET,
            'source': str(anchor.RESTORE / 'erigon'), 'driver_sha256': DRIVER_SHA,
            'reopen_proof_sha256': sha(UPGRADE / 'upload-ready.json'),
            'prefix': prefix, 'hold_sha256': sha(HOLD),
            'genesis_time': None, 'shadowfork_launch_authorized': False}


def wait_and_run():
    deadline = time.monotonic() + 24 * 3600
    while True:
        states = {name: unit(name) for name in UNITS}
        assert all(value['ActiveState'] != 'failed' for value in states.values()), states
        if all(value['ActiveState'] == 'inactive' for value in states.values()):
            break
        assert time.monotonic() < deadline, 'Exporter wait exceeded 24 hours'
        time.sleep(30)
    proof = check()
    # The hold was created by preparation tooling pending these exact checks.
    # Preserve it and the evidence before the existing driver can start.
    archived = CONTROL / 'instruction-review-hold-qualified.json'
    assert not archived.exists()
    HOLD.rename(archived)
    (CONTROL / 'handoff-release.json').write_text(json.dumps(proof, indent=2) + '\n')
    subprocess.run(['python3', '-u', str(DRIVER)], check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wait', action='store_true')
    args = parser.parse_args()
    if args.wait:
        wait_and_run()
    else:
        print(json.dumps(check(), indent=2))
