#!/usr/bin/env python3
"""Run the pinned native export and verifier only after the stopped N checks.

Default: read-only readiness check. --run creates a fresh output/evidence pair;
there is no retry, overwrite, upload, client startup or genesis-time selection.
Python checks provenance and records process results; Erigon writes and verifies
the PBT artifacts.
"""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import time

BASE = Path('/data/pbt-1')
SOURCE = BASE / 'rehearsal-24453558/erigon'
ANCHOR = BASE / 'rehearsal-24453558/anchor-preparation'
UPGRADE = BASE / 'v3-source-upgrade'
CONTROL = BASE / 'pbt-export-24453558'
OUTPUT = BASE / 'artifacts-24453558'
BINARY = BASE / 'rehearsal-tools/erigon/build/bin/erigon'
BINARY_SHA = '7d3c5beb8b985d54400c10cb09d6381860da387e85a8a74f0336795f08d025f4'
COMMIT = '372df0e68f52f9975370bff38dee6e41aefff0d7'
IMAGE = 'registry-1.docker.io/ethpandaops/erigon@sha256:4aec40c643590ec9496c982b22f0efb04835ff071233e92c418f9380cc84db69'
BLOCK = 24453558
BLOCK_HASH = '0x331c54fd1b37302697157dec30d2a1e0a13682843301f60d8ebac004f8bc4155'
MPT_ROOT = '0x90fe96f02a1d1009e48ccfb82d15bdf5aa130907acd6c4ebe2f2624e5a911260'
GENESIS_SHA = '3efbcddc03af8e09a40d4a0440e656bc43340e5374e3b4336f60782fd607fd0a'
RESERVE = 150_000_000_000


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(name, value):
    path = CONTROL / name
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def validate_anchor(proof):
    require(proof['anchor'] == BLOCK, 'Wrong export anchor')
    require(proof['source_datadir'] == str(SOURCE), 'Wrong exporter database')
    require(proof['image'] == IMAGE, 'Wrong anchor preparation image')
    for key in ('clean_reopen_verified', 'anchor_body_verified', 'stopped',
                'v3_mpt_preparation_verified', 'stop_after_block_boundary_verified',
                'stage_exec_at_anchor_passed'):
        require(proof[key] is True, 'Missing anchor gate: ' + key)
    head = proof['head']
    require(int(head['number'], 16) == BLOCK and head['hash'] == BLOCK_HASH
            and head['stateRoot'] == MPT_ROOT, 'Anchor hash/root mismatch')


def validate_metadata(meta):
    for key, expected in {'chainId': '1', 'block': BLOCK, 'blockHash': BLOCK_HASH,
                          'stateRoot': MPT_ROOT, 'hashSuite': 'blake3'}.items():
        require(meta[key] == expected, 'Wrong export metadata: ' + key)
    for key in ('pbtRoot', 'snapshotDigest', 'preimageDigest'):
        require(isinstance(meta[key], str) and re.fullmatch(r'0x[0-9a-fA-F]{64}', meta[key]),
                'Malformed export metadata: ' + key)
    for key in ('txNum', 'headerCount', 'codeGroupCount', 'storageCount'):
        require(type(meta[key]) is int and meta[key] >= 0, 'Invalid count: ' + key)
    require(meta['txNum'] > 0 and meta['headerCount'] > 0, 'Empty export for populated anchor')
    require(type(meta['finalized']) is bool, 'Invalid finality field')
    # The offline exporter can carry a forkchoice finalized value. It does not
    # establish finality on a shadowfork that has not launched.


def idle_source():
    for unit in ('pbt-1-v3-source-upgrade-v3', 'pbt-1-v3-source-qualification',
                 'pbt-1-v3-source-reopen'):
        fields = dict(line.split('=', 1) for line in subprocess.check_output([
            'systemctl', 'show', unit, '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result'],
            text=True).splitlines())
        require(fields == {'MainPID': '0', 'ActiveState': 'inactive', 'Result': 'success'},
                'Exporter predecessor has not completed successfully: ' + unit)
    source = os.fsencode(str(SOURCE))
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, PermissionError):
            continue
        require(not any(source in arg for arg in args), 'Another process references exporter DB: ' + proc.name)
    ids = subprocess.check_output(['docker', 'ps', '-q'], text=True).splitlines()
    for cid in ids:
        info = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
        for mount in info['Mounts']:
            if info['Name'] == '/node_exporter' and mount['Source'] == '/' and not mount['RW']:
                continue
            path = Path(mount['Source'])
            require(not (path == SOURCE or path in SOURCE.parents or SOURCE in path.parents),
                    'Running container mounts exporter DB: ' + info['Name'])


def check():
    require(socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1', 'Wrong host')
    proof = read(ANCHOR / 'complete.json')
    validate_anchor(proof)
    require(not (ANCHOR / 'instruction-review-hold.json').exists(), 'Anchor review hold remains')
    stage = read(ANCHOR / 'stage-exec-anchor.json')
    require(stage['exit_code'] == 0 and '--block=' + str(BLOCK) in stage['command']
            and '--datadir=' + str(SOURCE) in stage['command'], 'Missing successful stage at N')
    require(stage['environment']['NO_PRUNE'] == 'true', 'Anchor BAL retention not established')
    require(sha(BINARY) == BINARY_SHA, 'Native export binary changed')
    require(sha(BASE / 'pbt-1-source-genesis.json') == GENESIS_SHA, 'Source genesis changed')
    require(not OUTPUT.exists() and not CONTROL.exists(), 'Existing export attempt; inspect before retry')
    require(shutil.disk_usage(SOURCE).free > 450_000_000_000, 'Export requires 450 GB free initially')
    idle_source()
    return {'status': 'ready_for_native_export', 'anchor': BLOCK, 'block_hash': BLOCK_HASH,
            'mpt_state_root': MPT_ROOT, 'source': str(SOURCE), 'binary_sha256': BINARY_SHA,
            'anchor_proof_sha256': sha(ANCHOR / 'complete.json'), 'genesis_time': None}


def commands():
    return {
        'export': [str(BINARY), 'snapshots', 'export-pbt', '--datadir=' + str(SOURCE),
                   '--out=' + str(OUTPUT), '--experimental.bin-commitment.hash=blake3'],
        'verify': [str(BINARY), 'snapshots', 'verify-pbt', '--datadir=' + str(SOURCE),
                   '--snapshot=' + str(OUTPUT / 'pbt-snapshot.bin'),
                   '--preimages=' + str(OUTPUT / 'framed.bin'), '--block=' + str(BLOCK),
                   '--tmpdir=' + str(OUTPUT / 'verify-tmp')],
    }


def run_native(label, command):
    env = dict(os.environ, COMMITMENT_V3='true', GOMAXPROCS='8')
    env.pop('STOP_AFTER_BLOCK', None)
    started = time.time()
    with (CONTROL / (label + '.log')).open('x') as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            while process.poll() is None:
                free = shutil.disk_usage(SOURCE).free
                save('status.json', {'phase': label, 'pid': process.pid, 'time': time.time(),
                                     'free_bytes': free, 'anchor': BLOCK})
                require(free > RESERVE, 'Export disk reserve reached')
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            save(label + '.json', {'command': command, 'pid': process.pid,
                                  'started': started, 'finished': time.time(),
                                  'exit_code': process.returncode, 'binary_sha256': BINARY_SHA})
    require(process.returncode == 0, label + ' failed; inspect native log')


def identity(path):
    stat = path.stat()
    require(path.is_file() and not path.is_symlink() and stat.st_size > 0, 'Missing regular artifact')
    return {'inode': stat.st_ino, 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def run():
    with ExitStack() as stack:
        # Hold the existing conversion and anchor locks throughout export.
        for path in (UPGRADE / 'upgrade.lock', ANCHOR / 'job.lock'):
            lock = stack.enter_context(path.open('r+'))
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        readiness = check()
        CONTROL.mkdir()
        OUTPUT.mkdir()
        save('started.json', {**readiness, 'time': time.time(), 'commands': commands()})
        try:
            run_native('export', commands()['export'])
            meta = read(OUTPUT / 'pbt-snapshot.meta.json')
            validate_metadata(meta)
            files = ['pbt-snapshot.bin', 'framed.bin', 'pbt-snapshot.meta.json']
            before = {name: identity(OUTPUT / name) for name in files}
            run_native('verify', commands()['verify'])
            artifacts = {}
            for name in files:
                path = OUTPUT / name
                digest = sha(path)
                require(identity(path) == before[name], 'Artifact changed during verification: ' + name)
                artifacts[name] = {**before[name], 'sha256': digest}
            require(sha(BINARY) == BINARY_SHA, 'Export binary changed during operation')
            require(sha(ANCHOR / 'complete.json') == readiness['anchor_proof_sha256'], 'Anchor proof changed')
            report = {**readiness, 'status': 'native_export_and_verification_passed',
                      'time': time.time(), 'metadata': meta, 'artifacts': artifacts,
                      'source_commit': COMMIT, 'shadowfork_finality_established': False,
                      'cross_client_imports_verified': False, 'uploaded': False}
            save('complete.json', report)
            save('status.json', {'phase': report['status'], 'time': time.time(), 'anchor': BLOCK})
        except Exception as exc:
            save('status.json', {'phase': 'failed', 'time': time.time(), 'error': str(exc)})
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.run:
        run()
    else:
        print(json.dumps(check(), indent=2))
