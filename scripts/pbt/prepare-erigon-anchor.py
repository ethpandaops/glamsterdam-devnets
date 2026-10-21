#!/usr/bin/env python3
"""Prepare the full-week anchor on the separate Erigon restore.

Wait for the local recovery archive, replay only the verified 1,020-block
prefix, and require a clean reopen. Never open the published final-head DB.
Requires the older source's completed v3 conversion and two native opens.
The instruction-review hold remains until that evidence has been reviewed.
Shared export and all measured worker migrations remain separate operations.
"""
import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pipeline_rpc
from pipeline_rpc import ANCHOR, ANCHOR_HASH, ANCHOR_ROOT, RPC, save

BASE = Path('/data/pbt-1')
RESTORE = BASE / 'rehearsal-24453558'
CONTROL = RESTORE / 'anchor-preparation'
BLOCKS = BASE / 'pipeline/blocks'
RECOVERY = Path('/mnt/pbt-recovery')
NAME = 'pbt-1-erigon-anchor-preparation'
IMAGE = 'registry-1.docker.io/ethpandaops/erigon@sha256:4aec40c643590ec9496c982b22f0efb04835ff071233e92c418f9380cc84db69'
COMMIT = '372df0e68f52f9975370bff38dee6e41aefff0d7'
UPGRADE = BASE / 'v3-source-upgrade'
INTEGRATION = BASE / 'rehearsal-tools/erigon/build/bin/integration.pinned'
INTEGRATION_SHA = 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03'
TARGET = 24453558
PREFIX_SHA = '822629d9718ca6dad8cbdc7056acd98bffcb2f8a3cc0749f96ea6e4e426e8109'
RECOVERY_SHA = 'e511af776332da1497c537b58770bec0b7e962c1484cd2dcb9a9d30f6ac268a7'
RECOVERY_BYTES = 534953200071


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def state():
    return json.loads(command('docker', 'inspect', NAME))[0]['State']


def status(phase, **details):
    save(CONTROL / 'status.json', {'phase': phase, 'time': time.time(), **details})


def record(number):
    return json.loads(gzip.decompress((BLOCKS / f'{number:08d}.json.gz').read_bytes()))


def require_instruction_alignment():
    assert not (CONTROL / 'instruction-review-hold.json').exists(), (
        'Instruction review hold: review the older source v3/reopen evidence '
        'before enabling anchor preparation')


def require_unused_database(db):
    for cid in command('docker', 'ps', '-q').splitlines():
        info = json.loads(command('docker', 'inspect', cid))[0]
        for mount in info['Mounts']:
            # The existing metrics agent observes the host filesystem read-only.
            if info['Name'] == '/node_exporter' and mount['Source'] == '/' and not mount['RW']:
                continue
            other = Path(mount['Source'])
            assert not (other == db or other in db.parents or db in other.parents), (
                'Running container overlaps exporter database', info['Name'], mount['Source'])


def require_v3_source():
    proof = json.loads((UPGRADE / 'upload-ready.json').read_text())
    assert proof['source'] == str(RESTORE / 'erigon')
    assert proof['stopped'] and proof['native_reopen_verified'] and proof['v3_state_verified']
    assert proof['commit'] == COMMIT
    head = proof['head']
    assert int(head['number'], 16) == ANCHOR
    assert head['hash'] == ANCHOR_HASH and head['stateRoot'] == ANCHOR_ROOT
    for unit in ('pbt-1-v3-source-upgrade-v3', 'pbt-1-v3-source-reopen'):
        assert command('systemctl', 'show', unit, '-p', 'ActiveState', '--value') == 'inactive'
        assert command('systemctl', 'show', unit, '-p', 'MainPID', '--value') == '0'
    for phase in ('convert-v3', 'verify-v3-state', 'restore-source-block'):
        assert json.loads((UPGRADE / (phase + '.json')).read_text())['exit_code'] == 0
    with INTEGRATION.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == INTEGRATION_SHA
    return proof


def commit_export_anchor():
    """Use the documented stage command at N with execution stopped."""
    assert not state()['Running']
    args = [str(INTEGRATION), 'stage_exec', '--datadir=' + str(RESTORE / 'erigon'),
            '--chain=mainnet', '--block=' + str(TARGET), '--experimental.commitment-v3']
    env = dict(os.environ, COMMITMENT_V3='true', NO_PRUNE='true', GOMAXPROCS='8')
    env.pop('STOP_AFTER_BLOCK', None)  # The offline stage must persist N.
    status('committing_export_anchor', target=TARGET)
    with (CONTROL / 'stage-exec-anchor.log').open('w') as log:
        result = subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT)
    save(CONTROL / 'stage-exec-anchor.json', {
        'time': time.time(), 'command': args, 'exit_code': result.returncode,
        'integration_sha256': INTEGRATION_SHA,
        'environment': {k: env[k] for k in ('COMMITMENT_V3', 'NO_PRUNE', 'GOMAXPROCS')}})
    assert result.returncode == 0, 'Anchor stage_exec failed; inspect its log'


def verify_prefix():
    digest = hashlib.sha256()
    parent = ANCHOR_HASH
    for number in range(ANCHOR + 1, TARGET + 1):
        data = (BLOCKS / f'{number:08d}.json.gz').read_bytes()
        digest.update(data)
        item = json.loads(gzip.decompress(data))
        assert item['number'] == number
        assert item['new_payload'][0]['parentHash'] == parent
        parent = item['hash']
    assert digest.hexdigest() == PREFIX_SHA, 'Preparation records differ from qualified prefix'
    return {'start': ANCHOR + 1, 'end': TARGET, 'sha256': digest.hexdigest(),
            'target_hash': parent}


def recovery_ready():
    assert RECOVERY.is_mount(), 'Recovery volume is not mounted'
    proof_path = RECOVERY / 'archive-verified.json'
    if not proof_path.exists():
        return False
    proof = json.loads(proof_path.read_text())
    archive = RECOVERY / 'erigon-24503958.tar.zst'
    stat = archive.stat()
    assert proof['sha256'] == RECOVERY_SHA
    assert proof['bytes'] == stat.st_size == RECOVERY_BYTES
    assert proof['mtime_ns'] == stat.st_mtime_ns
    return True


def wait_rpc():
    rpc = RPC()
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        assert state()['Running'], 'Preparation client exited; inspect its log'
        try:
            head = rpc.call('eth_getBlockByNumber', ['latest', False], timeout=10)
            if head:
                return rpc, head
        except (OSError, RuntimeError, ValueError):
            pass
        time.sleep(3)
    raise RuntimeError('RPC did not become ready within 30 minutes')


def target_audit(rpc, head):
    expected = record(TARGET)
    assert int(head['number'], 16) == TARGET
    for field, key in [('hash', 'hash'), ('stateRoot', 'state_root'),
                       ('blockAccessListHash', 'bal_hash')]:
        assert head[field] == expected[key], field
    bodies = rpc.call('engine_getPayloadBodiesByRangeV2', [hex(TARGET), '0x1'], True)
    assert len(bodies) == 1 and bodies[0]
    for field in ('transactions', 'withdrawals', 'blockAccessList'):
        assert bodies[0][field] == expected['new_payload'][0][field], field
    return {'head': head, 'anchor_body_verified': True}


def verify_intentional_stop(stopped, logs):
    assert not stopped['Running'] and not stopped['OOMKilled'], stopped
    assert stopped['ExitCode'] == 0 and not stopped.get('Error'), stopped
    for line in logs.splitlines():
        if 'STOP_AFTER_BLOCK reached, exiting without commit (debug mode)' not in line:
            continue
        match = re.search(r'\bblock="?([0-9,]+)', line)
        if match and int(match[1].replace(',', '')) == TARGET:
            return {'target_block': TARGET, 'marker': line, 'stopped_state': stopped}
    raise AssertionError('Missing intentional pre-commit stop marker at N')


def submit_stop_block(rpc, item):
    """Submit N, accepting a disconnected RPC only with the exact stop evidence."""
    assert item['number'] == TARGET
    deadline = time.monotonic() + 1800
    transport_failures = 0
    while time.monotonic() < deadline:
        current = state()
        if not current['Running']:
            logs = subprocess.check_output(
                ['docker', 'logs', NAME], text=True, stderr=subprocess.STDOUT)
            proof = verify_intentional_stop(current, logs)
            (CONTROL / 'intentional-stop.log').write_text(logs)
            proof.update(time=time.time(), payload_hash=item['hash'],
                         transport_failures=transport_failures)
            save(CONTROL / 'stop-boundary.json', proof)
            return proof
        try:
            payload = rpc.call('engine_newPayloadV5', item['new_payload'], True, timeout=30)
            assert payload['status'] in ('VALID', 'ACCEPTED', 'SYNCING'), payload
            if payload['status'] == 'VALID':
                assert payload['latestValidHash'] == item['hash'], payload
            choice = rpc.call('engine_forkchoiceUpdatedV3', item['forkchoice'], True,
                              timeout=30)['payloadStatus']
            assert choice['status'] in ('VALID', 'ACCEPTED', 'SYNCING'), choice
            if choice['status'] == 'VALID':
                assert choice['latestValidHash'] == item['hash'], choice
        except (OSError, ValueError):
            # A normal RPC response is not guaranteed when Erigon exits before
            # committing N. Transport failure alone never proves success.
            transport_failures += 1
        time.sleep(0.5)
    raise RuntimeError('Erigon did not produce the expected STOP_AFTER_BLOCK boundary')


def rpc_stage(stage):
    pipeline_rpc.ROOT = CONTROL
    rpc, head = wait_rpc()
    if stage in ('after-stage', 'reopen'):
        save(CONTROL / (stage + '.json'), target_audit(rpc, head))
        return
    assert int(head['number'], 16) == ANCHOR
    assert head['hash'] == ANCHOR_HASH and head['stateRoot'] == ANCHOR_ROOT
    save(CONTROL / 'baseline.json', head)
    verify_prefix()
    started = time.time()
    for number in range(ANCHOR + 1, TARGET):
        assert shutil.disk_usage(RESTORE).free > 200_000_000_000, 'Local free space below 200 GB'
        item = record(number)
        assert item['new_payload'][0]['parentHash'] == head['hash']
        head = rpc.apply(item)
        status('replaying_preparation', head=number, target=TARGET,
               blocks_per_second=(number - ANCHOR) / (time.time() - started))
    save(CONTROL / 'before-intentional-stop.json', {'head': head, 'time': time.time()})
    item = record(TARGET)
    assert item['new_payload'][0]['parentHash'] == head['hash']
    status('waiting_for_intentional_stop', target=TARGET, previous_head=TARGET - 1)
    submit_stop_block(rpc, item)


def stop_cleanly(label):
    # The shared helper waits for Erigon background work before graceful stop
    # and rejects OOM/forced termination.
    from reopen import stop
    stop(NAME, CONTROL / (label + '.log'))


def main():
    CONTROL.mkdir(parents=True, exist_ok=True)
    with (CONTROL / 'job.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require_instruction_alignment()
        v3_proof = require_v3_source()
        assert not (CONTROL / 'started.json').exists(), 'Inspect existing attempt; no automatic restart'
        assert (RESTORE / 'snapshot-fetcher/done').exists()
        assert (RESTORE / 'erigon/chaindata').is_dir()
        proof = verify_prefix()
        save(CONTROL / 'prefix-proof.json', proof)
        status('waiting_for_verified_recovery_archive', target=TARGET)
        deadline = time.monotonic() + 24 * 3600
        while not recovery_ready():
            require_instruction_alignment()
            download_path = RECOVERY / 'status.json'
            if download_path.exists():
                download = json.loads(download_path.read_text())
                assert download['phase'] != 'failed', 'Recovery download failed'
            assert time.monotonic() < deadline, 'Recovery download gate exceeded 24 hours'
            time.sleep(30)
        require_instruction_alignment()
        assert shutil.disk_usage(RESTORE).free > 300_000_000_000
        db = RESTORE / 'erigon'
        require_unused_database(db)
        assert not subprocess.run(['docker', 'container', 'inspect', NAME],
                                  capture_output=True).returncode == 0, 'Existing preparation container'
        shutil.copyfile(BASE / 'pipeline/jwt', CONTROL / 'jwt')
        (CONTROL / 'jwt').chmod(0o600)
        source = json.loads(command('docker', 'inspect', 'pbt-1-erigon-execution'))[0]
        assert not source['State']['Running']
        # Use the stopped original container only as a source for its known
        # network/RPC/retention flags, never for its former legacy image.
        flags = list(source['Config']['Cmd'])
        for required in ('--datadir=/data', '--nodiscover', '--maxpeers=0',
                         '--no-downloader', '--snap.stop', '--exec.no-prune=true',
                         '--exec.no-background-maintenance=true'):
            assert required in flags, required
        flags += ['--experimental.commitment-v3', '--keep.stored.chain.config']
        command('docker', 'pull', IMAGE)
        image = json.loads(command('docker', 'inspect', IMAGE))[0]
        assert image['Config']['Labels']['ethpandaops.io.commitRef'] == COMMIT
        args = ['docker', 'run', '-d', '--pull=never', '--name', NAME,
                '--network=none', '--hostname=localhost', '--user=0:0',
                '--memory=32g', '--memory-swap=32g', '--cpus=8', '--cpuset-cpus=0-7',
                '-e', 'COMPRESS_WORKERS=2', '-e', 'MERGE_WORKERS=2',
                '-e', 'GOMAXPROCS=8', '-e', 'COMMITMENT_V3=true',
                '-e', 'STOP_AFTER_BLOCK=' + str(TARGET),
                '-v', f'{db}:/data', '-v', f'{CONTROL / "jwt"}:/jwt:ro',
                '-v', f'{BASE / "pbt-1-source-genesis.json"}:/genesis.json:ro',
                IMAGE, *flags]
        save(CONTROL / 'started.json', {'time': time.time(), 'command': args,
                                      'source': str(db), 'prefix': proof,
                                      'v3_source_proof': v3_proof, 'commit': COMMIT})
        launched = False
        try:
            command(*args)
            launched = True
            status('opening_original_source', target=TARGET)
            subprocess.run(['nsenter', '--target', str(state()['Pid']), '--net',
                            'python3', '-u', __file__, '--rpc-stage', 'replay'], check=True)
            boundary = json.loads((CONTROL / 'stop-boundary.json').read_text())
            assert boundary['target_block'] == TARGET
            assert boundary['payload_hash'] == record(TARGET)['hash']
            assert not state()['Running']
            commit_export_anchor()
            for stage in ('after-stage', 'reopen'):
                command('docker', 'start', NAME)
                subprocess.run(['nsenter', '--target', str(state()['Pid']), '--net',
                                'python3', '-u', __file__, '--rpc-stage', stage], check=True)
                stop_cleanly(stage + '-shutdown')
            before = json.loads((CONTROL / 'after-stage.json').read_text())
            after = json.loads((CONTROL / 'reopen.json').read_text())
            assert before['head'] == after['head']
            save(CONTROL / 'complete.json', {
                'time': time.time(), 'anchor': TARGET, 'head': after['head'],
                'source_datadir': str(db), 'image': IMAGE, 'preparation_blocks': TARGET - ANCHOR,
                'clean_reopen_verified': True, 'anchor_body_verified': True,
                'stopped': True, 'v3_mpt_preparation_verified': True,
                'stop_after_block_boundary_verified': True,
                'stage_exec_at_anchor_passed': True, 'pbt_artifacts_exported': False,
                'pbt_format_qualified': False, 'finality_established': False})
            status('anchor_prepared_stopped', head=TARGET, next_step='export_and_validate_shared_artifacts')
        finally:
            if launched and state()['Running']:
                stop_cleanly('failure-shutdown')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rpc-stage', choices=('replay', 'after-stage', 'reopen'))
    args = parser.parse_args()
    try:
        if args.rpc_stage:
            rpc_stage(args.rpc_stage)
        else:
            main()
    except Exception as exc:
        status('failed', error=str(exc))
        raise
