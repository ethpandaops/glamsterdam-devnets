#!/usr/bin/env python3
"""Qualify two isolated native opens of the converted original source."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import time

import pipeline_rpc
from pipeline_rpc import RPC, ANCHOR, ANCHOR_HASH, ANCHOR_ROOT, save

ROOT = Path('/data/pbt-1/v3-source-upgrade')
SOURCE = Path('/data/pbt-1/rehearsal-24453558/erigon')
BINARY = Path('/data/pbt-1/rehearsal-tools/erigon/build/bin/erigon')
UNIT = 'pbt-1-v3-source-reopen'
SHA = '7d3c5beb8b985d54400c10cb09d6381860da387e85a8a74f0336795f08d025f4'
INTEGRATION_SHA = 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03'
OWNS_STATUS = False


def show(key):
    return subprocess.check_output(['systemctl', 'show', UNIT, '-p', key, '--value'], text=True).strip()


def require_audit_namespace():
    pid = show('MainPID')
    assert pid != '0', 'Native client stopped before audit'
    native = os.readlink('/proc/' + pid + '/ns/net')
    current = os.readlink('/proc/self/ns/net')
    host = os.readlink('/proc/1/ns/net')
    assert native != host, 'Native client is not in its private network namespace'
    assert current == native, 'Audit entered the wrong network namespace'
    assert show('MainPID') == pid, 'Native client changed during namespace check'
    return {'native_pid': int(pid), 'network_namespace': native, 'audit_namespace': current}


def audit(label):
    namespace = require_audit_namespace()
    pipeline_rpc.ROOT = ROOT
    rpc = RPC()
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        assert show('MainPID') != '0', 'Native client stopped before RPC became available'
        try:
            head = rpc.call('eth_getBlockByNumber', ['latest', False], timeout=10)
        except (OSError, ValueError, RuntimeError):
            time.sleep(3)
            continue
        if not head:
            time.sleep(3)
            continue
        assert int(head['number'], 16) == ANCHOR
        assert head['hash'] == ANCHOR_HASH and head['stateRoot'] == ANCHOR_ROOT
        save(ROOT / (label + '.json'), {'head': head, 'time': time.time(), **namespace})
        return
    raise RuntimeError('Native RPC startup exceeded 30 minutes')


def require_completed_conversion():
    """Read-only handoff check; a premature invocation must not alter progress."""
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    fields = dict(line.split('=', 1) for line in subprocess.check_output([
        'systemctl', 'show', 'pbt-1-v3-source-upgrade-v3',
        '-p', 'ActiveState', '-p', 'MainPID', '-p', 'Result'], text=True).splitlines())
    assert fields['ActiveState'] == 'inactive' and fields['MainPID'] == '0', (
        'Conversion has not stopped', fields)
    assert fields['Result'] == 'success', 'Conversion service did not finish successfully'
    complete = json.loads((ROOT / 'conversion-complete.json').read_text())
    assert complete['source'] == str(SOURCE) and complete['target_block'] == ANCHOR
    started = json.loads((ROOT / 'started.json').read_text())
    assert started['source'] == str(SOURCE) and started['source_block'] == ANCHOR
    assert started['integration_sha256'] == INTEGRATION_SHA
    assert json.loads((ROOT / 'status.json').read_text())['phase'] == 'converted_pending_native_reopen'
    for phase in ('convert-v3', 'verify-v3-files', 'restore-source-block', 'verify-v3-state'):
        evidence = json.loads((ROOT / (phase + '.json')).read_text())
        assert evidence['exit_code'] == 0, phase
        assert '--datadir=' + str(SOURCE) in evidence['command'], phase
        if phase == 'restore-source-block':
            assert '--block=' + str(ANCHOR) in evidence['command']
            assert evidence['no_prune_env'] == 'true'


def main():
    global OWNS_STATUS
    require_completed_conversion()
    lock = (ROOT / 'upgrade.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (ROOT / 'native-open-started.json').exists(), 'Inspect prior validation before retry'
    unit_path = Path('/etc/systemd/system') / (UNIT + '.service')
    assert not unit_path.exists(), 'Inspect existing native validation unit'
    with BINARY.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == SHA
    shutil.copyfile('/data/pbt-1/pipeline/jwt', ROOT / 'jwt')
    (ROOT / 'jwt').chmod(0o600)
    original = json.loads(subprocess.check_output(['docker', 'inspect', 'pbt-1-erigon-execution']))[0]
    assert not original['State']['Running']
    flags = [f for f in original['Config']['Cmd']
             if not f.startswith(('--datadir=', '--authrpc.jwtsecret='))]
    flags += ['--datadir=' + str(SOURCE), '--authrpc.jwtsecret=' + str(ROOT / 'jwt'),
              '--experimental.commitment-v3', '--keep.stored.chain.config']
    assert '--exec.no-prune=true' in flags and '--exec.no-background-maintenance=true' in flags
    command = [str(BINARY), *flags]
    save(ROOT / 'native-open-started.json', {'time': time.time(), 'command': command, 'sha256': SHA})
    OWNS_STATUS = True
    save(ROOT / 'status.json', {'phase': 'native_reopen_validation', 'time': time.time()})
    unit_path.write_text(
        '[Unit]\nDescription=Isolated PBT v3 source reopen qualification\n'
        '[Service]\nType=exec\nPrivateNetwork=yes\nMemoryMax=32G\nMemorySwapMax=0\n'
        'CPUQuota=800%\nAllowedCPUs=0-7\nTimeoutStopSec=1800\nSendSIGKILL=no\n'
        'Environment=GOMAXPROCS=8 COMPRESS_WORKERS=2 MERGE_WORKERS=2\n'
        'Restart=no\nExecStart=' + shlex.join(command) + '\n'
        'StandardOutput=append:' + str(ROOT / 'native-client.log') + '\n'
        'StandardError=inherit\n')
    subprocess.run(['systemctl', 'daemon-reload'], check=True)
    subprocess.run(['systemctl', 'start', UNIT], check=True)
    try:
        for label in ('native-before', 'native-after'):
            if label == 'native-after':
                subprocess.run(['systemctl', 'start', UNIT], check=True)
            pid = show('MainPID')
            assert pid != '0'
            # Type=exec waits for systemd's namespace setup and execve. With
            # Type=simple, nsenter can attach before PrivateNetwork is applied.
            assert os.path.samefile('/proc/' + pid + '/exe', BINARY)
            subprocess.run(['nsenter', '--target', pid, '--net', 'python3', __file__,
                            '--audit', label], check=True)
            subprocess.run(['systemctl', 'stop', UNIT], check=True, timeout=1900)
            assert show('MainPID') == '0' and show('Result') == 'success'
        before = json.loads((ROOT / 'native-before.json').read_text())['head']
        after = json.loads((ROOT / 'native-after.json').read_text())['head']
        assert before == after
        save(ROOT / 'upload-ready.json', {
            'time': time.time(), 'head': after, 'source': str(SOURCE), 'stopped': True,
            'native_reopen_verified': True, 'v3_state_verified': True,
            'commit': '372df0e68f52f9975370bff38dee6e41aefff0d7', 'binary_sha256': SHA})
        save(ROOT / 'status.json', {'phase': 'v3_source_verified_stopped', 'time': time.time(),
                                    'head': ANCHOR})
    finally:
        if show('MainPID') != '0':
            subprocess.run(['systemctl', 'stop', UNIT], check=True, timeout=1900)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', choices=('native-before', 'native-after'))
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    assert not (args.audit and args.check_only)
    try:
        if args.check_only:
            require_completed_conversion()
            print('Conversion handoff checks passed; no client started.')
        elif args.audit:
            audit(args.audit)
        else:
            main()
    except Exception as exc:
        if OWNS_STATUS:
            save(ROOT / 'status.json', {'phase': 'failed', 'time': time.time(), 'error': str(exc)})
        raise
