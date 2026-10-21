#!/usr/bin/env python3
"""Recover the Engine STOP_AFTER_BLOCK capture without changing the anchor.

The pre-commit exit also discarded N's header/body. Commit the recorded N with
the native Engine, stop, unwind one block, then execute N offline. Default is
read-only validation; --run is one attempt, with original evidence preserved.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import time

BASE = Path('/data/pbt-1')
DRIVER = BASE / 'prepare-erigon-anchor.py'
DRIVER_SHA = 'bb62206ba8a679877c42ec12dd00496e42809d4511cbd8ba23a5425444d46b6a'
ROOT = BASE / 'rehearsal-24453558/anchor-preparation'
RECOVERY = ROOT / 'engine-capture-recovery'
NAME = 'pbt-1-erigon-anchor-recovery'
BLOCK = 24453558


def read(path):
    return json.loads(path.read_text())


def load_driver():
    assert hashlib.sha256(DRIVER.read_bytes()).hexdigest() == DRIVER_SHA
    spec = importlib.util.spec_from_file_location('anchor', DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.NAME = NAME
    return module


def validate_positions(text, execution, senders):
    stages = {}
    for line in text.splitlines():
        match = re.fullmatch(r'(Headers|Bodies|Senders|Execution)\s+(\d+)\s+\d+\s*', line)
        if match:
            stages[match[1]] = int(match[2])
    assert stages == {'Headers': senders, 'Bodies': senders,
                      'Senders': senders, 'Execution': execution}, stages
    return stages


def container_command(original):
    args = list(original)
    assert args[:3] == ['docker', 'run', '-d']
    assert args.count('--name') == 1
    index = args.index('--name') + 1
    assert args[index] == 'pbt-1-erigon-anchor-preparation'
    args[index] = NAME
    stop = 'STOP_AFTER_BLOCK=' + str(BLOCK)
    assert args.count(stop) == 1
    index = args.index(stop)
    assert args[index - 1] == '-e'
    del args[index - 1:index + 1]
    assert not any('STOP_AFTER_BLOCK' in arg for arg in args)
    for flag in ('--network=none', '--memory=32g', '--memory-swap=32g',
                 '--cpus=8', '--cpuset-cpus=0-7', '--exec.no-prune=true',
                 '--exec.no-background-maintenance=true'):
        assert flag in args, flag
    return args


def native_env():
    env = dict(os.environ, COMMITMENT_V3='true', NO_PRUNE='true',
               NO_BACKGROUND_E3_BUILD='true', GOMAXPROCS='8')
    env.pop('STOP_AFTER_BLOCK', None)
    env.pop('ERIGON_STOP_AFTER_BLOCK', None)
    return env


def positions(driver):
    return subprocess.check_output([str(driver.INTEGRATION), 'print_stages',
                                    '--datadir=' + str(driver.RESTORE / 'erigon')],
                                   env=native_env(), stderr=subprocess.STDOUT, text=True)


def check(driver):
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    assert not RECOVERY.exists() and not (ROOT / 'complete.json').exists()
    assert read(ROOT / 'status.json')['phase'] == 'failed'
    fields = dict(x.split('=', 1) for x in subprocess.check_output([
        'systemctl', 'show', 'pbt-1-erigon-anchor-preparation', '-p', 'MainPID',
        '-p', 'ActiveState'], text=True).splitlines())
    assert fields['MainPID'] == '0' and fields['ActiveState'] == 'failed'
    driver.require_instruction_alignment()
    driver.require_v3_source()
    driver.verify_prefix()
    assert driver.recovery_ready()
    driver.require_unused_database(driver.RESTORE / 'erigon')
    original = read(ROOT / 'started.json')
    assert original['source'] == str(driver.RESTORE / 'erigon')
    assert original['commit'] == driver.COMMIT
    boundary = read(ROOT / 'stop-boundary.json')
    assert boundary['target_block'] == BLOCK
    assert boundary['payload_hash'] == driver.record(BLOCK)['hash']
    assert read(ROOT / 'stage-spin-review.json')['replay_complete_through'] == BLOCK - 1
    stopped = json.loads(subprocess.check_output([
        'docker', 'inspect', 'pbt-1-erigon-anchor-preparation']))[0]['State']
    assert not stopped['Running'] and not stopped['OOMKilled'] and stopped['ExitCode'] == 0
    assert subprocess.run(['docker', 'inspect', NAME], capture_output=True).returncode != 0
    assert shutil.disk_usage(driver.RESTORE).free > 450_000_000_000
    output = positions(driver)
    stages = validate_positions(output, BLOCK - 1, BLOCK - 1)
    return {'time': time.time(), 'status': 'ready_for_native_anchor_recovery',
            'positions': stages, 'stage_report': output,
            'command': container_command(original['command']), 'genesis_time': None}


def rpc(driver, mode):
    pid = str(driver.state()['Pid'])
    assert os.readlink('/proc/self/ns/net') == os.readlink('/proc/' + pid + '/ns/net')
    assert os.readlink('/proc/self/ns/net') != os.readlink('/proc/1/ns/net')
    driver.pipeline_rpc.ROOT = ROOT
    client, head = driver.wait_rpc()
    if mode == 'commit':
        previous = driver.record(BLOCK - 1)
        assert int(head['number'], 16) == BLOCK - 1
        assert head['hash'] == previous['hash'] and head['stateRoot'] == previous['state_root']
        head = client.apply(driver.record(BLOCK))
    proof = driver.target_audit(client, head)
    driver.save(RECOVERY / (mode + '.json'), {**proof, 'time': time.time()})


def offline(driver, label, flags):
    command = [str(driver.INTEGRATION), 'stage_exec',
               '--datadir=' + str(driver.RESTORE / 'erigon'), '--chain=mainnet',
               '--experimental.commitment-v3', *flags]
    assert not driver.state()['Running']
    driver.status(label, target=BLOCK)
    with (RECOVERY / (label + '.log')).open('x') as out:
        result = subprocess.run(command, env=native_env(), stdout=out, stderr=subprocess.STDOUT)
    report = {'time': time.time(), 'command': command, 'exit_code': result.returncode,
              'integration_sha256': driver.INTEGRATION_SHA,
              'environment': {k: native_env()[k] for k in (
                  'COMMITMENT_V3', 'NO_PRUNE', 'NO_BACKGROUND_E3_BUILD', 'GOMAXPROCS')}}
    driver.save(RECOVERY / (label + '.json'), report)
    assert result.returncode == 0, label
    return report


def run(driver):
    with (ROOT / 'job.lock').open('r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        readiness = check(driver)
        RECOVERY.mkdir()
        driver.save(RECOVERY / 'started.json', readiness)
        for name in ('status.json', 'stage-exec-anchor.json', 'stage-exec-anchor.log'):
            shutil.copy2(ROOT / name, RECOVERY / ('prior-' + name))
        launched = False
        try:
            subprocess.run(readiness['command'], check=True)
            launched = True
            def audit(mode):
                subprocess.run(['nsenter', '--target', str(driver.state()['Pid']), '--net',
                                'python3', '-u', __file__, '--rpc', mode], check=True)
            audit('commit')
            driver.stop_cleanly('recovery-commit-shutdown')
            validate_positions(positions(driver), BLOCK, BLOCK)
            offline(driver, 'unwind-one', ['--unwind=1'])
            validate_positions(positions(driver), BLOCK - 1, BLOCK)
            stage = offline(driver, 'execute-anchor', ['--block=' + str(BLOCK)])
            validate_positions(positions(driver), BLOCK, BLOCK)
            driver.save(ROOT / 'stage-exec-anchor.json', {**stage,
                'recovery': 'Engine commit N, native unwind one block, native re-execution at N',
                'offline_reexecution_verified': True})
            for label in ('after-stage', 'reopen'):
                subprocess.run(['docker', 'start', NAME], check=True)
                audit(label)
                driver.stop_cleanly('recovery-' + label + '-shutdown')
            before, after = read(RECOVERY / 'after-stage.json'), read(RECOVERY / 'reopen.json')
            assert before['head'] == after['head']
            for label in ('after-stage', 'reopen'):
                driver.save(ROOT / (label + '.json'), read(RECOVERY / (label + '.json')))
            driver.save(ROOT / 'complete.json', {
                'time': time.time(), 'anchor': BLOCK, 'head': after['head'],
                'source_datadir': str(driver.RESTORE / 'erigon'), 'image': driver.IMAGE,
                'preparation_blocks': BLOCK - driver.ANCHOR, 'clean_reopen_verified': True,
                'anchor_body_verified': True, 'stopped': True,
                'v3_mpt_preparation_verified': True, 'stop_after_block_boundary_verified': True,
                'stage_exec_at_anchor_passed': True, 'offline_reexecution_verified': True,
                'capture_adaptation': 'Native Engine commit followed by one-block native unwind and offline re-execution; intentional exit discarded N header/body',
                'recovery_evidence': str(RECOVERY), 'pbt_artifacts_exported': False,
                'pbt_format_qualified': False, 'finality_established': False})
            driver.status('anchor_prepared_stopped', head=BLOCK, next_step='export_and_validate_shared_artifacts')
        except Exception as exc:
            driver.status('failed', error=str(exc))
            raise
        finally:
            if launched and driver.state()['Running']:
                driver.stop_cleanly('recovery-failure-shutdown')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--rpc', choices=('commit', 'after-stage', 'reopen'))
    args = parser.parse_args()
    assert not (args.run and args.rpc)
    driver = load_driver()
    if args.rpc:
        rpc(driver, args.rpc)
    elif args.run:
        run(driver)
    else:
        print(json.dumps(check(driver), indent=2))
