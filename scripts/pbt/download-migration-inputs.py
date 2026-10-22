#!/usr/bin/env python3
"""Prepare independent writable N inputs without starting migration or clients."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import socket
import time

from stream_verified_archive import ordered_ranges

BASE = Path('/data/pbt-1')
CONTROL = BASE / 'migration-input-control'
FINAL = BASE / 'migration-input-24453558'
STAGING = BASE / 'migration-input-24453558.staging'
PREFIX = 'pbt-1/20261020-pbt-anchor-24453558/'
FILES = ('pbt-snapshot.bin', 'framed.bin', 'pbt-snapshot.meta.json')
ANCHOR_HASH = '0x331c54fd1b37302697157dec30d2a1e0a13682843301f60d8ebac004f8bc4155'
STATE_ROOT = '0x90fe96f02a1d1009e48ccfb82d15bdf5aa130907acd6c4ebe2f2624e5a911260'
COMMIT = '372df0e68f52f9975370bff38dee6e41aefff0d7'
RESERVE = 600_000_000_000
WORKERS = {**{f'lighthouse-{client}-{number}': client
              for client in ('geth', 'besu', 'nethermind') for number in (1, 2)},
           'lighthouse-geth-3': 'geth'}


def names(host):
    assert host in WORKERS, 'Worker is not an input recipient'
    return FILES[1:] if host == 'lighthouse-geth-3' else FILES


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.chmod(0o600)
    temporary.replace(path)


def validate_release(release):
    assert release['anchor'] == 24453558 and release['block_hash'] == ANCHOR_HASH
    assert release['mpt_state_root'] == STATE_ROOT and release['source_commit'] == COMMIT
    assert release['genesis_time'] is None
    assert release['full_remote_sha256_verified'] is True or (
        release.get('verification_deferred_by_user') is True
        and release.get('independent_mpt_reconstruction_verified') is False
        and release.get('transfer_integrity') == 'source_sha256_and_content_md5_multipart_upload')
    assert release['shadowfork_finality_established'] is False
    assert release['cross_client_imports_verified'] is False
    assert re.fullmatch('[0-9a-f]{64}', release['proof_sha256'])
    assert set(release['files']) == set(FILES)
    for name, item in release['files'].items():
        assert item['key'] == PREFIX + name and type(item['bytes']) is int and item['bytes'] > 0
        assert re.fullmatch('[0-9a-f]{64}', item['sha256'])
        assert isinstance(item['etag'], str) and item['etag']
    meta = release['metadata']
    assert meta['block'] == 24453558 and meta['blockHash'] == ANCHOR_HASH and meta['stateRoot'] == STATE_ROOT
    assert meta['chainId'] == '1' and meta['hashSuite'] == 'blake3'
    assert re.fullmatch('0x[0-9a-fA-F]{64}', meta['pbtRoot'])


def validate_job(job, hostname, qualification):
    host = job['host']
    assert hostname == 'glamsterdam-pbt-1-' + host and host in WORKERS
    validate_release(job['release'])
    assert digest(job['release']) == job['release_canonical_sha256']
    assert set(job['urls']) == set(names(host)), 'Wrong inputs for this worker path'
    assert qualification['host'] == host and qualification['client'] == WORKERS[host]
    assert qualification['status'] == 'startup_checks_passed' and qualification['head'] == 24503958
    assert qualification['head_hash'] == '0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216'
    assert type(qualification['service_uid']) is int and qualification['service_uid'] > 0


def check(job):
    qualification = json.loads((BASE / 'qualification/result.json').read_text())
    validate_job(job, socket.gethostname(), qualification)
    pwd.getpwuid(qualification['service_uid'])  # Resolve ownership before a large transfer.
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == job['downloader_sha256']
    assert hashlib.sha256(Path(__file__).with_name('stream_verified_archive.py').read_bytes()).hexdigest() == job['range_reader_sha256']
    assert not FINAL.exists() and not FINAL.is_symlink(), 'Existing inputs require inspection'
    assert not STAGING.exists() and not STAGING.is_symlink(), 'Prior partial input download requires inspection'
    needed = sum(job['release']['files'][name]['bytes'] for name in names(job['host']))
    free = shutil.disk_usage(BASE).free
    assert free > needed + RESERVE + 1024**3, 'Insufficient space for inputs and migration reserve'
    return {'host': job['host'], 'input_bytes': needed, 'free_bytes': free,
            'reserve_after_download_bytes': RESERVE, 'service_uid': qualification['service_uid']}


def transfer(job, readiness, fetch=ordered_ranges):
    validate_release(job['release'])
    assert not FINAL.exists() and not STAGING.exists()
    STAGING.mkdir(mode=0o700)
    proofs = {}
    for name in names(job['host']):
        item = job['release']['files'][name]
        target = STAGING / name
        checksum, received = hashlib.sha256(), 0
        with target.open('xb') as stream:
            for data in fetch(job['urls'][name], item['etag'], item['bytes']):
                assert shutil.disk_usage(BASE).free > RESERVE, 'Migration disk reserve reached'
                assert received + len(data) <= item['bytes'], 'Input grew during download'
                assert stream.write(data) == len(data), 'Short file write'
                checksum.update(data)
                received += len(data)
                save(CONTROL / 'status.json', {'phase': 'downloading', 'file': name,
                     'received_bytes': received, 'file_bytes': item['bytes'], 'time': time.time()})
            stream.flush()
            os.fsync(stream.fileno())
        assert received == item['bytes'] and checksum.hexdigest() == item['sha256'], 'Downloaded input checksum mismatch'
        stored_readback = not job['release'].get('verification_deferred_by_user', False)
        if stored_readback:
            with target.open('rb') as stream:
                assert hashlib.file_digest(stream, 'sha256').hexdigest() == item['sha256'], 'Stored input checksum mismatch'
        stat = target.stat()
        proofs[name] = {'bytes': received, 'sha256': item['sha256'], 'etag': item['etag'],
                        'inode': stat.st_ino, 'mtime_ns': stat.st_mtime_ns,
                        'transfer_sha256_verified': True, 'stored_file_readback_verified': stored_readback}
    assert json.loads((STAGING / 'pbt-snapshot.meta.json').read_text()) == job['release']['metadata']
    proof = {'host': job['host'], 'anchor': 24453558, 'anchor_hash': ANCHOR_HASH,
             'release_canonical_sha256': job['release_canonical_sha256'], 'files': proofs,
             'time': time.time(), 'status': 'verified_inputs_ready', 'independent_writable_copies': True,
             'migration_started': False, 'shadowfork_finality_established': False, 'genesis_time': None}
    save(STAGING / 'ready.json', proof)
    uid = readiness['service_uid']
    gid = pwd.getpwuid(uid).pw_gid
    for path in STAGING.iterdir():
        os.chown(path, uid, gid)
        path.chmod(0o640)
    os.chown(STAGING, uid, gid)
    STAGING.chmod(0o750)
    assert not FINAL.exists()
    STAGING.rename(FINAL)
    save(CONTROL / 'status.json', {'phase': 'verified_inputs_ready', 'time': time.time(),
                                 'host': job['host'], 'files': list(proofs)})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    try:
        job = json.loads((CONTROL / 'job.json').read_text())
        if not args.run:
            print(json.dumps(check(job)))
        else:
            with (CONTROL / 'download.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                readiness = check(job)
                assert not (CONTROL / 'started.json').exists(), 'Prior attempt requires inspection'
                save(CONTROL / 'started.json', {'time': time.time(), **readiness})
                transfer(job, readiness)
    except Exception as exc:
        if args.run:
            save(CONTROL / 'status.json', {'phase': 'failed', 'error_class': type(exc).__name__, 'time': time.time()})
        raise SystemExit(type(exc).__name__ + ': inspect private input-download evidence') from None
