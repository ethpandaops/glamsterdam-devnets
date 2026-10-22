#!/usr/bin/env python3
"""Upgrade a PBT-1 Erigon worker's H database; never activate PBT.

The verified H archive on its recovery volume is the rollback copy. Preserve
conversion backups and logs without duplicating the 517 GiB mutable DB locally.
Native reopening and publication remain separate gates.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time

ROOT = Path('/data/pbt-1/v3-head-upgrade')
SOURCE = Path('/data/pbt-1/erigon')
TOOLS = Path('/data/pbt-1/v3-tools-372df0e6')
TARGET = 24503958
COMMIT = '372df0e68f52f9975370bff38dee6e41aefff0d7'
EXPECTED = {
    'integration': 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03',
    'erigon': '7d3c5beb8b985d54400c10cb09d6381860da387e85a8a74f0336795f08d025f4',
}
ARCHIVE_SHA = 'e511af776332da1497c537b58770bec0b7e962c1484cd2dcb9a9d30f6ac268a7'
ARCHIVE_BYTES = 534953200071
OWNS_STATUS = False
REVIEW = SOURCE.parent / 'worker-head-review'
CANDIDATE = SOURCE.parent / 'boundary-review/candidate-bin/integration'
CANDIDATE_SHA = '1f807caefedc534ae837641ebff1dfdc37c0378ea8e3556263bddd1eb276e9f3'
PATCH_SHA = '4b04368aad6cf9ee38058eb5d6e6bed79ac251a49138b9c9c28a0c6455483ab9'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_reviewed_module(name, path, checksum):
    assert sha(path) == checksum
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_peer_qualification(peer, qualifier):
    """Only a complete H result can qualify reusing this converter on worker 1."""
    proof, complete, phases = peer['proof'], peer['conversion'], peer['phases']
    assert proof['host'] == 'lighthouse-erigon-2' and proof['client'] == 'erigon'
    assert proof['status'] == 'startup_checks_passed'
    assert proof['head'] == TARGET
    assert proof['head_hash'] == '0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216'
    assert proof['state_root'] == '0x8cab6f81e370f341e67e66d2333cdf3e6074861f861aa3e490b9411460ad7f22'
    assert proof['commit'] == COMMIT
    assert proof['image'] == 'registry-1.docker.io/ethpandaops/erigon@sha256:4aec40c643590ec9496c982b22f0efb04835ff071233e92c418f9380cc84db69'
    assert proof['memory_gib'] == 16 and proof['cpus'] == 8 and proof['network_mode'] == 'none'
    assert proof['native_reopen_verified'] and proof['v3_format_verified']
    assert not proof['missing_builder_contracts']
    assert complete['source'] == str(SOURCE) and complete['target_block'] == TARGET
    for key in ('first_stopped_state', 'stopped_state'):
        state = proof[key]
        assert not state['Running'] and not state['OOMKilled'] and state['ExitCode'] == 0
    for phase in ('convert-v3', 'verify-v3-files', 'restore-head-block', 'verify-v3-state'):
        assert phases[phase]['exit_code'] == 0
        assert '--datadir=' + str(SOURCE) in phases[phase]['command']
    assert '--block=' + str(TARGET) in phases['restore-head-block']['command']
    assert phases['restore-head-block']['no_prune_env'] == 'true'
    build = qualifier.validate_erigon_converter_build(complete, phases)
    assert build and build == proof['converter_build']
    return build


def bounded_review(worker):
    assert worker == 'lighthouse-erigon-1', 'This handoff is only for the preserved H worker'
    assert sha(CANDIDATE) == CANDIDATE_SHA
    qualifier = load_reviewed_module('qualifier', SOURCE.parent / 'qualify-worker.py',
                                    '36233de17e567000bae118da1124f41946536bcda65b81b6c3531e397b31b350')
    peer_path = REVIEW / 'qualified-erigon-2.json'
    validate_peer_qualification(json.loads(peer_path.read_text()), qualifier)
    comparison = json.loads((REVIEW / 'comparisons-complete.json').read_text())
    assert comparison['worker'] == worker and comparison['source'] == str(SOURCE)
    assert comparison['all_records_equal'] and comparison['inputs_unchanged']
    boundary = load_reviewed_module('boundary', SOURCE.parent / 'resume-erigon-head-boundaries.py',
                                   '32f6ccbc86ab1662ef5d7b218c46678cb8eabf2c1bf5e8a337c7c8c07e9ca0a7')
    read = lambda name: json.loads((REVIEW / name).read_text())
    checked, moved = boundary.validate_plan(read('head-plan.json'), read('head-files.json'),
                                            {d: read(d + '-compare.json') for d in ('accounts', 'storage')})
    for item in checked + moved:
        boundary.same_file(SOURCE / 'snapshots/domain' / item['name'], item)
    assert not (ROOT / 'bounded-selection').exists(), 'Prior file selection requires review'
    build = {'base_commit': COMMIT, 'patch_sha256': PATCH_SHA, 'binary_sha256': CANDIDATE_SHA,
             'binary': str(CANDIDATE), 'independent_verifier_sha256': EXPECTED['integration']}
    return build, moved, sha(peer_path)


def select_bounded_fragments(worker, expected_peer_sha):
    build, moved, peer_sha = bounded_review(worker)
    assert peer_sha == expected_peer_sha, 'Peer qualification changed during unsqueeze'
    directory = ROOT / 'bounded-selection'
    directory.mkdir()
    (directory / 'before.json').write_text(json.dumps({'files': moved, 'peer_sha256': peer_sha}, indent=2) + '\n')
    hidden = directory / 'hidden-domain-files'
    hidden.mkdir()
    for item in moved:
        (SOURCE / 'snapshots/domain' / item['name']).rename(hidden / item['name'])
    (directory / 'applied.json').write_text(json.dumps({'time': time.time(), 'files': moved,
                                                      'converter_build': build}, indent=2) + '\n')


def save(name, data):
    temporary = ROOT / (name + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(ROOT / name)


def run(phase, command, v3=False, converter_build=None):
    env = {k: v for k, v in os.environ.items() if k != 'COMMITMENT_V3'}
    env['GOMAXPROCS'] = '8'
    if 'stage_exec' in command:
        env['NO_PRUNE'] = 'true'  # Preserve the retained BAL corpus during tail reconstruction.
    if v3:
        env['COMMITMENT_V3'] = 'true'
    save('status.json', {'phase': phase, 'time': time.time(), 'target_block': TARGET,
                         'command': command, 'free_bytes': shutil.disk_usage(SOURCE).free})
    with (ROOT / (phase + '.log')).open('w') as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                if shutil.disk_usage(SOURCE).free < 150_000_000_000:
                    process.send_signal(signal.SIGINT)
                    raise RuntimeError('Free space below 150 GB; inspect interrupted conversion')
                time.sleep(5)
            assert process.returncode == 0, f'{phase} exited {process.returncode}; inspect its log'
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                process.wait(timeout=1800)
    save(phase + '.json', {'finished_at': time.time(), 'exit_code': process.returncode,
                           'command': command, 'commitment_v3_env': v3,
                           'no_prune_env': env.get('NO_PRUNE'),
                           'binary_sha256': sha(Path(command[0])),
                           **({'converter_build': converter_build} if converter_build else {})})


def validate_preserved_head(proof, container):
    """The original H producer is preserved, unlike Erigon-2's restored copy."""
    assert proof['client'] == 'erigon' and proof['stopped']
    assert int(proof['head']['number'], 16) == TARGET
    assert proof['head']['hash'] == '0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216'
    assert proof['head']['stateRoot'] == '0x8cab6f81e370f341e67e66d2333cdf3e6074861f861aa3e490b9411460ad7f22'
    assert proof['verified_bal_bodies'] == 51420
    state = container['State']
    assert not state['Running'] and not state['OOMKilled'] and state['ExitCode'] == 0
    assert container['Config']['Image'] == proof['image']
    mounts = [m for m in container['Mounts'] if m['Destination'] == '/data']
    assert len(mounts) == 1 and mounts[0]['Source'] == str(SOURCE)


def preflight(worker):
    assert worker in ('lighthouse-erigon-1', 'lighthouse-erigon-2')
    assert socket.gethostname() == 'glamsterdam-pbt-1-' + worker
    # Both copies coexist on Erigon-1. Never compete with its exporter for disk.
    if worker == 'lighthouse-erigon-1':
        for unit in ('pbt-1-v3-source-upgrade-v3', 'pbt-1-v3-source-qualification',
                     'pbt-1-v3-source-reopen', 'pbt-1-erigon-anchor-preparation'):
            active = subprocess.check_output(
                ['systemctl', 'show', unit, '-p', 'ActiveState', '--value'],
                text=True).strip()
            assert active == 'inactive', (unit, active)
    assert not (ROOT / 'started.json').exists(), 'Inspect any prior attempt; never retry automatically'
    recovery = Path('/mnt/pbt-recovery')
    assert recovery.is_mount()
    status = json.loads((recovery / 'status.json').read_text())
    assert status['client'] == 'erigon'
    if worker == 'lighthouse-erigon-2':
        assert status['phase'] == 'restored_unopened'
        restored = json.loads((recovery / 'restore-complete.json').read_text())
        assert restored['archive_sha256'] == ARCHIVE_SHA and restored['datadir'] == str(SOURCE)
    else:
        assert status['phase'] == 'recovery_ready_existing_db_preserved'
        original = json.loads((SOURCE.parent / 'pipeline/reopen-51417-complete.json').read_text())
        container = json.loads(subprocess.check_output(
            ['docker', 'inspect', 'pbt-1-erigon-execution']))[0]
        validate_preserved_head(original, container)
    # Erigon-2's first unsqueeze needed approximately 735 GB above baseline.
    # Retain the 150 GB interruption reserve and additional headroom at startup.
    assert shutil.disk_usage(SOURCE).free > 1_000_000_000_000, 'Need >1 TB free before starting'
    return recovery


def main(worker, check_only=False, bounded_view=False):
    global OWNS_STATUS
    recovery = preflight(worker)
    build, peer_sha = None, None
    if bounded_view:
        build, _, peer_sha = bounded_review(worker)
    if check_only:
        print('Worker identity, recovery path, exporter inactivity and disk checks passed')
        return
    ROOT.mkdir(exist_ok=True)
    lock = (ROOT / 'upgrade.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    preflight(worker)
    archive = recovery / f'erigon-{TARGET}.tar.zst'
    stat = archive.stat()
    proof = json.loads((recovery / 'archive-verified.json').read_text())
    assert proof['sha256'] == ARCHIVE_SHA
    assert proof['bytes'] == stat.st_size == ARCHIVE_BYTES
    assert proof['mtime_ns'] == stat.st_mtime_ns
    assert not (SOURCE / 'snapshots/backup').exists()
    assert not (SOURCE / 'snapshots/rebuild').exists()
    assert not (SOURCE / 'snap/rebuild').exists()
    for name, sha in EXPECTED.items():
        with (TOOLS / name).open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == sha, name
    fixtures = json.loads((ROOT / 'fixtures.json').read_text())
    assert fixtures['exit_code'] == 0 and fixtures['command'][0:2] == ['go', 'test']
    assert fixtures['command'][2] == './db/state'
    for cid in subprocess.check_output(['docker', 'ps', '-q'], text=True).splitlines():
        container = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
        for mount in container['Mounts']:
            path = Path(mount['Source'])
            if mount['RW']:
                assert not (path == SOURCE or path in SOURCE.parents or SOURCE in path.parents), (
                    'Database overlaps a running writable mount', container['Name'])
    OWNS_STATUS = True
    save('started.json', {
        'time': time.time(), 'host': socket.gethostname(), 'source': str(SOURCE),
        'target_block': TARGET, 'target_hash': '0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216',
        'target_state_root': '0x8cab6f81e370f341e67e66d2333cdf3e6074861f861aa3e490b9411460ad7f22',
        'commit': COMMIT, 'binaries': EXPECTED, 'rollback_archive': str(archive),
        'rollback_sha256': ARCHIVE_SHA, 'rollback_proof': proof,
        'mutable_db_checkpoint_copied': False, 'genesis_time': None,
        'pbt_activation': False, 'publication_authorized': False,
        **({'converter_build': build, 'qualified_peer_proof_sha256': peer_sha} if build else {}),
    })
    common = ['--datadir=' + str(SOURCE), '--chain=mainnet']
    integration = str(TOOLS / 'integration')
    run('schema-migrations', [integration, 'run_migrations', *common])
    run('before-commitments', [integration, 'commitment', 'print', *common])
    run('unsqueeze', [integration, 'commitment', 'convert', *common, '--squeeze=false'])
    backup = SOURCE / 'snapshots/backup'
    if backup.exists():
        assert not (ROOT / 'unsqueeze-backup').exists()
        backup.rename(ROOT / 'unsqueeze-backup')
    if bounded_view:
        select_bounded_fragments(worker, peer_sha)
    run('convert-v3', [str(CANDIDATE) if bounded_view else integration,
                       'commitment', 'convert', *common, '--v3'], converter_build=build)
    run('verify-v3-files', [integration, 'commitment', 'verify', *common], v3=True)
    # Conversion resets the mutable execution rows to the immutable checkpoint.
    # stage_exec reads the stored chain configuration and executes retained blocks
    # back to H; it neither follows a CL nor downloads/accepts a later head.
    run('restore-head-block', [integration, 'stage_exec', *common,
                              '--block=' + str(TARGET), '--experimental.commitment-v3'], v3=True)
    run('verify-v3-state', [integration, 'commitment', 'verify', *common], v3=True)
    run('after-commitments', [integration, 'commitment', 'print', *common], v3=True)
    save('conversion-complete.json', {
        'time': time.time(), 'source': str(SOURCE), 'target_block': TARGET,
        'native_reopen_qualified': False, 'publication_authorized': False,
        **({'converter_build': build} if build else {})})
    save('status.json', {'phase': 'converted_pending_native_reopen',
                         'time': time.time(), 'target_block': TARGET})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=['lighthouse-erigon-1', 'lighthouse-erigon-2'],
                        default='lighthouse-erigon-2')
    parser.add_argument('--check-only', action='store_true',
                        help='Read-only identity, recovery-path and capacity check; not binary qualification')
    parser.add_argument('--bounded-view', action='store_true',
                        help='Worker 1 only: require completed worker 2 qualification before optimized conversion')
    args = parser.parse_args()
    try:
        main(args.worker, args.check_only, args.bounded_view)
    except Exception as exc:
        if OWNS_STATUS:
            save('status.json', {'phase': 'failed', 'time': time.time(),
                                 'target_block': TARGET, 'error': str(exc)})
        raise
