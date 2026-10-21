#!/usr/bin/env python3
"""Cache an immutable archive on a recovery volume; restore only a new datadir.

Bounded parallel ranges, durable contiguous checkpoints and whole-archive SHA256.
No EL startup, pruning, database replacement or deletion of recovery archives.
"""
import concurrent.futures
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

CHUNK = 64 * 1024**2
WORKERS = 4
ROOT = Path('/mnt/pbt-recovery')
JOB = Path('/etc/pbt-recovery/job.json')
URL = Path('/etc/pbt-recovery/source-url')


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_local_cache_job(job, root, hostname):
    # This mode only downloads; it cannot replace or extract any database.
    scopes = {
        'verified-erigon-v3-head-cache': (
            'glamsterdam-pbt-1-lighthouse-erigon-1',
            Path('/data/pbt-1/v3-head-restore/cache')),
        'verified-erigon-v3-head-recovery-cache': (
            'glamsterdam-pbt-1-lighthouse-erigon-2',
            Path('/data/pbt-1/v3-head-recovery/cache')),
        'verified-erigon-1-restored-head-recovery-cache': (
            'glamsterdam-pbt-1-lighthouse-erigon-1',
            Path('/data/pbt-1/v3-head-recovery/cache')),
    }
    assert job['profile'] in scopes
    assert (hostname, root) == scopes[job['profile']]
    assert job['client'] == 'erigon' and job['head'] == 24503958
    assert job['restore'] is False


def main(local_v3_cache=False):
    job = json.loads(JOB.read_text())
    if local_v3_cache:
        validate_local_cache_job(job, ROOT, socket.gethostname())
        assert ROOT.resolve() == ROOT and ROOT.is_dir()
    else:
        assert ROOT.is_mount(), 'Recovery volume must be mounted'
    client = job['client']
    assert client in ('geth', 'besu', 'nethermind', 'erigon')
    archive = ROOT / f'{client}-{job["head"]}.tar.zst'
    partial = archive.with_suffix(archive.suffix + '.part')
    status = ROOT / 'status.json'
    checkpoint = ROOT / 'download-state.json'
    verified = ROOT / 'archive-verified.json'
    size = job['archive_bytes']
    expected = job['archive_sha256']
    started = time.time()
    lock = (ROOT / 'download.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def progress(phase, **values):
        save(status, {'phase': phase, 'time': time.time(), 'client': client,
                      'archive_bytes': size, 'started_at': started, **values})

    progress('preflight')
    try:
        if archive.exists():
            st = archive.stat()
            proof = json.loads(verified.read_text()) if verified.exists() else {}
            if not (st.st_size == size and proof.get('sha256') == expected
                    and proof.get('mtime_ns') == st.st_mtime_ns):
                progress('verifying_existing_archive')
                assert st.st_size == size and sha256(archive) == expected
                save(verified, {'sha256': expected, 'bytes': size,
                                'mtime_ns': st.st_mtime_ns, 'time': time.time()})
        else:
            chunks = ROOT / '.chunks'
            chunks.mkdir(exist_ok=True)
            if checkpoint.exists():
                previous = json.loads(checkpoint.read_text())
                assert previous['sha256'] == expected and previous['size'] == size
                offset = previous['offset']
                assert offset == size or offset % CHUNK == 0
                assert partial.exists() and partial.stat().st_size >= offset
            else:
                assert not partial.exists(), 'Inspect uncheckpointed partial archive'
                offset = 0
            reserve = 150_000_000_000 if local_v3_cache else 0
            assert shutil.disk_usage(ROOT).free >= size - offset + WORKERS * CHUNK + reserve
            hasher = hashlib.sha256()
            if offset:
                progress('verifying_resume_prefix', completed_bytes=offset)
                with partial.open('rb') as stream:
                    remaining = offset
                    while remaining:
                        data = stream.read(min(8 * 1024**2, remaining))
                        assert data
                        hasher.update(data)
                        remaining -= len(data)

            def fetch(index):
                low = index * CHUNK
                high = min(low + CHUNK, size) - 1
                path = chunks / str(index)
                for attempt in range(12):
                    try:
                        request = urllib.request.Request(
                            URL.read_text().strip(),
                            headers={'Range': f'bytes={low}-{high}',
                                     'If-Match': job['etag']})
                        with urllib.request.urlopen(request, timeout=90) as response:
                            assert response.status == 206
                            assert response.headers['Content-Range'] == f'bytes {low}-{high}/{size}'
                            assert response.headers['ETag'] == job['etag']
                            with path.open('wb') as stream:
                                remaining = high - low + 1
                                while remaining:
                                    data = response.read(min(1024**2, remaining))
                                    if not data:
                                        raise RuntimeError('Short range response')
                                    stream.write(data)
                                    remaining -= len(data)
                        assert path.stat().st_size == high - low + 1
                        return path
                    except Exception:
                        # URLs are scoped credentials: never include request errors in logs.
                        if attempt == 11:
                            raise RuntimeError(f'Range {index} failed after 12 attempts') from None
                        time.sleep(min(2**attempt, 30))

            initial = offset
            with partial.open('r+b' if partial.exists() else 'w+b') as out:
                out.truncate(offset)
                out.seek(offset)
                with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
                    pending = {}
                    first = offset // CHUNK
                    count = (size + CHUNK - 1) // CHUNK
                    for index in range(first, min(first + WORKERS, count)):
                        pending[index] = pool.submit(fetch, index)
                    for index in range(first, count):
                        path = pending.pop(index).result()
                        with path.open('rb') as stream:
                            while data := stream.read(8 * 1024**2):
                                out.write(data)
                                hasher.update(data)
                                offset += len(data)
                        out.flush()
                        os.fsync(out.fileno())
                        save(checkpoint, {'offset': offset, 'size': size, 'sha256': expected})
                        path.unlink()
                        if index + WORKERS < count:
                            pending[index + WORKERS] = pool.submit(fetch, index + WORKERS)
                        speed = (offset - initial) / max(time.time() - started, 1)
                        progress('downloading', completed_bytes=offset,
                                 bytes_per_second=speed,
                                 eta_seconds=(size - offset) / max(speed, 1))
            assert offset == size
            assert hasher.hexdigest() == expected, 'Full archive SHA256 mismatch; preserve for inspection'
            partial.replace(archive)
            save(verified, {'sha256': expected, 'bytes': size,
                            'mtime_ns': archive.stat().st_mtime_ns, 'time': time.time()})
        progress('archive_verified', completed_bytes=size)
        if job['restore']:
            data = Path(job['datadir'])
            assert data == Path('/data/pbt-1') / client
            done = ROOT / 'restore-complete.json'
            claim = ROOT / 'restore-started.json'
            if not done.exists():
                assert not claim.exists(), 'Partial extraction requires inspection; archive is retained'
                data.mkdir(parents=True, exist_ok=True)
                assert not list(data.iterdir()), 'Never overwrite an existing database'
                assert shutil.disk_usage(data).free > job['unpacked_bytes'] + 100_000_000_000
                save(claim, {'archive_sha256': expected, 'datadir': str(data), 'time': time.time()})
                progress('extracting', completed_bytes=size, datadir=str(data))
                with (ROOT / 'restore.log').open('w') as log:
                    subprocess.run(['tar', '--zstd', '-xf', str(archive), '-C', str(data)],
                                   stdout=log, stderr=subprocess.STDOUT, check=True)
                save(done, {'archive_sha256': expected, 'datadir': str(data),
                            'time': time.time(), 'client_started': False})
            progress('restored_unopened', completed_bytes=size, datadir=str(data))
        elif local_v3_cache:
            progress('archive_ready_for_staged_restore', completed_bytes=size)
        else:
            progress('recovery_ready_existing_db_preserved', completed_bytes=size)
        URL.unlink(missing_ok=True)
    except Exception as exc:
        progress('failed', error=str(exc))
        raise
    finally:
        lock.close()


if __name__ == '__main__':
    main()
