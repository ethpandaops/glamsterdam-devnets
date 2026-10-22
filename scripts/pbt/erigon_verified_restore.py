#!/usr/bin/env python3
"""Restore a verified H release beside Erigon-1's preserved original database.

No source conversion is attributed to this worker. Its separate qualifier must
still open, inspect, stop and reopen the restored database under 32 GiB / 8 CPU.
Default is read-only preflight; --run downloads, extracts and promotes once.
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

BASE = Path('/data/pbt-1')
CONTROL = BASE / 'v3-head-restore'
CACHE = CONTROL / 'cache'
SOURCE = BASE / 'erigon'
STAGING = BASE / 'erigon-v3-restored'
PRESERVED = BASE / 'erigon-original-h-preserved'
KEY = 'pbt-1/20261020-erigon-v3-head/erigon/24503958/snapshot.tar.zst'
RESERVE = 150_000_000_000


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(path):
    st = path.stat()
    return {'device': st.st_dev, 'inode': st.st_ino}


def load(name, path, expected=None):
    if expected:
        assert sha(path) == expected, 'Changed prerequisite: ' + str(path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guards():
    upgrade = load('original_head_guard', BASE / 'upgrade-erigon-worker-head-v3.py',
                   '29ae64c4ff5498783345ee4aab6e681f9e05afc31acaa5850943fddac07fa636')
    qualifier = load('original_worker_guard', BASE / 'qualify-worker.py',
                     '36233de17e567000bae118da1124f41946536bcda65b81b6c3531e397b31b350')
    return upgrade, qualifier


def validate_bundle(bundle, upgrade, qualifier):
    build = upgrade.validate_peer_qualification(bundle['peer'], qualifier)
    meta, integrity = bundle['metadata'], bundle['integrity']
    proof = bundle['peer']['proof']
    assert bundle['key'] == integrity['key'] == KEY
    assert integrity['client'] == meta['client'] == 'erigon'
    assert integrity['head'] == meta['head'] == 24503958
    assert meta['head_hash'] == proof['head_hash'] and meta['state_root'] == proof['state_root']
    assert meta['erigon_commit'] == proof['commit'] and meta['image'] == proof['image']
    assert meta['converter_build'] == build
    assert meta['commitment_format'] == 'v3' and meta['tree'] == 'MPT'
    assert meta['pbt_migration_performed'] is False and meta['launch_authorized'] is False
    assert meta['full_remote_sha256_verified'] is True and integrity['full_remote_sha256_verified'] is True
    assert meta['native_reopen_verified'] is True and meta['genesis_time'] is None
    encoded = (json.dumps(proof, indent=2) + '\n').encode()
    assert hashlib.sha256(encoded).hexdigest() == meta['qualification_sha256']
    assert integrity['archive_bytes'] == meta['archive_bytes'] > 0
    checksum = meta['archive_sha256']
    assert integrity['archive_sha256'] == checksum
    assert len(checksum) == 64 and all(c in '0123456789abcdef' for c in checksum)
    assert isinstance(bundle['etag'], str) and bundle['etag'].startswith('"') and bundle['etag'].endswith('"')
    assert type(bundle['unpacked_upper_bound_bytes']) is int and bundle['unpacked_upper_bound_bytes'] > 0
    assert bundle['unpacked_measurement']['source'] == str(SOURCE)
    assert bundle['unpacked_measurement']['source_stopped'] is True
    assert bundle['unpacked_measurement']['qualification_sha256'] == meta['qualification_sha256']
    assert 0 < bundle['unpacked_measurement']['apparent_bytes'] <= bundle['unpacked_upper_bound_bytes']
    return build


def save(name, value):
    path = CONTROL / name
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def idle_database():
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, ProcessLookupError):
            continue
        for path in (SOURCE, STAGING, PRESERVED):
            encoded = os.fsencode(str(path))
            assert not any(arg in (encoded, b'--datadir=' + encoded) or encoded + b'/' in arg
                           for arg in args), 'Database process remains: ' + proc.name
    for cid in subprocess.check_output(['docker', 'ps', '-q'], text=True).split():
        container = json.loads(subprocess.check_output(['docker', 'inspect', cid]))[0]
        for mount in container['Mounts']:
            if not mount['RW']:
                continue
            other = Path(mount['Source'])
            for path in (SOURCE, STAGING, PRESERVED):
                assert not (path == other or path in other.parents or other in path.parents), 'Writable database mount'


def preflight(stream=False):
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    upgrade, qualifier = guards()
    bundle = read(CONTROL / 'release-bundle.json')
    validate_bundle(bundle, upgrade, qualifier)
    upgrade.preflight('lighthouse-erigon-1')
    assert not STAGING.exists() and not PRESERVED.exists(), 'Inspect previous restore before retry'
    assert not (CONTROL / 'started.json').exists(), 'Restore is single-attempt; inspect previous attempt'
    original = json.loads(subprocess.check_output(['docker', 'inspect', 'pbt-1-erigon-execution']))[0]
    assert original['HostConfig']['RestartPolicy']['Name'] in ('', 'no'), 'Original producer can restart automatically'
    need = bundle['unpacked_upper_bound_bytes'] + RESERVE
    if not stream:
        need += bundle['metadata']['archive_bytes']
    assert shutil.disk_usage(SOURCE).free > need, 'Insufficient fresh restore space and reserve'
    idle_database()
    return bundle


def stream_extract(bundle):
    from stream_verified_archive import ordered_ranges
    meta = bundle['metadata']
    checksum, count = hashlib.sha256(), 0
    url = (CONTROL / 'source-url').read_text().strip()
    assert url.startswith('https://'), 'Expected scoped HTTPS archive URL'
    STAGING.mkdir(mode=0o700)
    with (CONTROL / 'extract.log').open('x') as log:
        process = subprocess.Popen(['tar', '--zstd', '-xf', '-', '-C', str(STAGING)],
                                   stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            for chunk in ordered_ranges(url, bundle['etag'], meta['archive_bytes']):
                assert shutil.disk_usage(STAGING).free > RESERVE, 'Restore disk reserve reached'
                assert process.poll() is None, 'Extraction stopped during archive transfer'
                checksum.update(chunk)
                count += len(chunk)
                process.stdin.write(chunk)
                save('status.json', {'phase': 'streaming_verified_release', 'time': time.time(),
                                    'completed_bytes': count, 'archive_bytes': meta['archive_bytes']})
            process.stdin.close()
            while process.poll() is None:
                assert shutil.disk_usage(STAGING).free > RESERVE, 'Restore disk reserve reached'
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
            assert process.returncode == 0, 'Fresh extraction failed'
            assert shutil.disk_usage(STAGING).free > RESERVE, 'Restore disk reserve reached'
            assert count == meta['archive_bytes'] and checksum.hexdigest() == meta['archive_sha256'], (
                'Whole streamed archive checksum mismatch; original database remains untouched')
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=120)
            if not process.stdin.closed:
                try:
                    process.stdin.close()
                except BrokenPipeError:
                    pass
    save('stream-verified.json', {'time': time.time(), 'method': 'etag_bound_ranges_to_fresh_directory',
                                'sha256': checksum.hexdigest(), 'bytes': count, 'etag': bundle['etag'],
                                'key': KEY, 'bundle_sha256': sha(CONTROL / 'release-bundle.json'),
                                'restored_identity': identity(STAGING), 'whole_archive_verified': True})


def cached_extract(bundle):
    CACHE.mkdir(mode=0o700)
    meta = bundle['metadata']
    job = {'profile': 'verified-erigon-v3-head-cache', 'client': 'erigon', 'head': 24503958,
           'archive_bytes': meta['archive_bytes'], 'archive_sha256': meta['archive_sha256'],
           'etag': bundle['etag'], 'restore': False}
    (CACHE / 'job.json').write_text(json.dumps(job) + '\n')
    downloader = load('recovery_fetch', BASE / 'fetch-verified-erigon-release.py')
    downloader.ROOT, downloader.JOB, downloader.URL = CACHE, CACHE / 'job.json', CONTROL / 'source-url'
    downloader.main(local_v3_cache=True)
    assert shutil.disk_usage(SOURCE).free > bundle['unpacked_upper_bound_bytes'] + RESERVE
    STAGING.mkdir(mode=0o700)
    archive = CACHE / 'erigon-24503958.tar.zst'
    save('status.json', {'phase': 'extracting_verified_release', 'time': time.time()})
    with (CONTROL / 'extract.log').open('x') as log:
        process = subprocess.Popen(['tar', '--zstd', '-xf', str(archive), '-C', str(STAGING)],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None:
                assert shutil.disk_usage(STAGING).free > RESERVE, 'Restore disk reserve reached'
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=120)
        assert process.returncode == 0, 'Extraction failed; original database remains unchanged'


def run(stream=False):
    bundle = preflight(stream=stream)
    with (CONTROL / 'restore.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        bundle = preflight(stream=stream)
        save('started.json', {'time': time.time(), 'bundle_sha256': sha(CONTROL / 'release-bundle.json'),
                             'original_identity': identity(SOURCE), 'original_path': str(SOURCE)})
        meta = bundle['metadata']
        if stream:
            stream_extract(bundle)
        else:
            cached_extract(bundle)
        assert (STAGING / 'chaindata/mdbx.dat').is_file() and (STAGING / 'snapshots/domain').is_dir()
        assert not (STAGING / 'nodekey').exists(), 'Release unexpectedly contains a node identity'
        idle_database()
        before = read(CONTROL / 'started.json')
        assert identity(SOURCE) == before['original_identity']
        assert sha(CONTROL / 'release-bundle.json') == before['bundle_sha256']
        fresh_identity = identity(STAGING)
        save('promotion-started.json', {'time': time.time(), 'restored_identity': fresh_identity,
                                        'preserved_path': str(PRESERVED)})
        SOURCE.rename(PRESERVED)
        try:
            STAGING.rename(SOURCE)
        except BaseException:
            if not SOURCE.exists():
                PRESERVED.rename(SOURCE)
            raise
        save('complete.json', {'time': time.time(), 'profile': 'restored_verified_H_release',
                              'host': socket.gethostname(), 'bundle_sha256': before['bundle_sha256'],
                              'archive_sha256': meta['archive_sha256'], 'restored_identity': fresh_identity,
                              'original_identity': before['original_identity'], 'preserved_path': str(PRESERVED),
                              'local_v3_conversion_performed': False, 'worker_qualified': False,
                              'archive_transfer': 'stream' if stream else 'cache',
                              'genesis_time': None})
        save('status.json', {'phase': 'restored_pending_own_qualification', 'time': time.time()})


def validate_promoted(job, db):
    assert job['host'] == 'lighthouse-erigon-1' and job['client'] == 'erigon'
    assert job['memory_gib'] == 32 and db == SOURCE
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    bundle = read(CONTROL / 'release-bundle.json')
    build = validate_bundle(bundle, *guards())
    proof = read(CONTROL / 'complete.json')
    assert proof['host'] == socket.gethostname() and proof['profile'] == 'restored_verified_H_release'
    assert proof['local_v3_conversion_performed'] is False and proof['worker_qualified'] is False
    assert proof['bundle_sha256'] == sha(CONTROL / 'release-bundle.json')
    meta = bundle['metadata']
    assert job['head'] == meta['head'] and job['head_hash'] == meta['head_hash']
    assert job['state_root'] == meta['state_root'] and job['image'] == meta['image']
    assert job['commit'] == meta['erigon_commit']
    assert proof['archive_sha256'] == meta['archive_sha256']
    assert proof['restored_identity'] == identity(db)
    assert proof['preserved_path'] == str(PRESERVED) and proof['original_identity'] == identity(PRESERVED)
    transfer = proof.get('archive_transfer', 'cache')
    assert transfer in ('stream', 'cache')
    if transfer == 'stream':
        streamed = read(CONTROL / 'stream-verified.json')
        assert streamed['method'] == 'etag_bound_ranges_to_fresh_directory'
        assert streamed['whole_archive_verified'] is True
        assert streamed['sha256'] == meta['archive_sha256'] and streamed['bytes'] == meta['archive_bytes']
        assert streamed['etag'] == bundle['etag'] and streamed['key'] == KEY
        assert streamed['bundle_sha256'] == proof['bundle_sha256']
        assert streamed['restored_identity'] == proof['restored_identity']
    else:
        archive = CACHE / 'erigon-24503958.tar.zst'
        archived = read(CACHE / 'archive-verified.json')
        assert archived['sha256'] == meta['archive_sha256']
        assert archived['bytes'] == archive.stat().st_size == meta['archive_bytes']
        assert archived['mtime_ns'] == archive.stat().st_mtime_ns
    state = dict(line.split('=', 1) for line in subprocess.check_output([
        'systemctl', 'show', 'pbt-1-v3-head-restore', '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result'],
        text=True).splitlines())
    assert state == {'MainPID': '0', 'ActiveState': 'inactive', 'Result': 'success'}
    idle_database()
    return build, {'preparation_path': proof['profile'], 'source_release_key': KEY,
                   'source_release_archive_sha256': meta['archive_sha256'],
                   'local_v3_conversion_performed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--stream', action='store_true', help='Extract into a fresh directory while hashing; promote only after whole-archive SHA256 passes')
    args = parser.parse_args()
    if args.run:
        run(stream=args.stream)
    else:
        preflight(stream=args.stream)
        print('Verified H release and fresh restore capacity checked; no files changed')
