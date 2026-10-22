#!/usr/bin/env python3
"""Wait for an authorized Erigon recovery cache, then hash it; never alter archives."""
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import time

ROOT = Path('/data/pbt-1/v3-head-recovery')
UNIT = 'pbt-1-v3-head-recovery-cache'
EXPECTED_SHA = 'b4ab8e0831bd95ddce05b9f52c040de7eaf4a9b8b1fa49106cb3e9cd88938146'
EXPECTED_SIZE = 461165199193

def save(name, data):
    tmp = ROOT / (name + '.tmp')
    with tmp.open('w') as stream:
        json.dump(data, stream)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    tmp.replace(ROOT / name)

def unit():
    return dict(line.split('=', 1) for line in subprocess.check_output(
        ['systemctl', 'show', UNIT, '-p', 'LoadState', '-p', 'ActiveState',
         '-p', 'MainPID', '-p', 'Result'], text=True).splitlines())

def main():
    with ExitStack() as handles:
        _main(handles)


def _main(handles):
    profiles = {
        'glamsterdam-pbt-1-lighthouse-erigon-2': 'verified-erigon-v3-head-recovery-cache',
        'glamsterdam-pbt-1-lighthouse-erigon-1': 'verified-erigon-1-restored-head-recovery-cache',
    }
    hostname = socket.gethostname()
    assert hostname in profiles
    assert ROOT.resolve() == ROOT
    assert not (ROOT / 'stored-cache-verified.json').exists()
    guard = handles.enter_context((ROOT / 'stored-cache-readback.lock').open('a'))
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    job = json.loads((ROOT / 'job.json').read_text())
    assert job['profile'] == profiles[hostname]
    assert job['archive_sha256'] == EXPECTED_SHA and job['archive_bytes'] == EXPECTED_SIZE
    assert job['restore'] is False
    save('stored-cache-readback-status.json', {'phase':'waiting_for_download','time':time.time()})
    while True:
        state = unit()
        if state['LoadState'] == 'not-found':
            # systemd may collect a completed transient unit before this poll.
            # Missing alone is not success: require the final download phase,
            # matching archive proof and exclusive lock below, then hash afresh.
            assert state['ActiveState'] == 'inactive' and state['MainPID'] == '0'
            break
        assert state['LoadState'] == 'loaded', 'Unexpected download unit state'
        if state['ActiveState'] == 'inactive':
            assert state['Result'] == 'success' and state['MainPID'] == '0'
            break
        assert state['ActiveState'] in ('active', 'activating', 'deactivating'), 'Download failed'
        time.sleep(30)
    download_lock = handles.enter_context((ROOT / 'cache/download.lock').open('a'))
    fcntl.flock(download_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    progress = json.loads((ROOT / 'cache/status.json').read_text())
    assert progress['phase'] == 'archive_ready_for_staged_restore'
    proof = json.loads((ROOT / 'cache/archive-verified.json').read_text())
    assert proof['sha256'] == EXPECTED_SHA and proof['bytes'] == EXPECTED_SIZE
    path = ROOT / 'cache/erigon-24503958.tar.zst'
    before = path.lstat()
    assert stat.S_ISREG(before.st_mode) and before.st_size == EXPECTED_SIZE
    assert proof['mtime_ns'] == before.st_mtime_ns
    digest = hashlib.sha256()
    count = 0
    report = time.monotonic()
    with path.open('rb') as stream:
        assert os.fstat(stream.fileno()) == before
        while data := stream.read(8 * 1024**2):
            digest.update(data)
            count += len(data)
            if time.monotonic() - report >= 30:
                save('stored-cache-readback-status.json', {'phase':'hashing_stored_cache',
                     'completed_bytes':count,'archive_bytes':EXPECTED_SIZE,'time':time.time()})
                report = time.monotonic()
        after = os.fstat(stream.fileno())
    identity = lambda s: (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
    assert identity(before) == identity(after) == identity(path.lstat()), 'Stored cache changed'
    assert count == EXPECTED_SIZE and digest.hexdigest() == EXPECTED_SHA, 'Stored checksum mismatch'
    result = {'phase':'stored_cache_verified','path':str(path),'sha256':digest.hexdigest(),
              'bytes':count,'device':after.st_dev,'inode':after.st_ino,
              'mtime_ns':after.st_mtime_ns,'ctime_ns':after.st_ctime_ns,
              'time':time.time(),'original_recovery_archive_changed':False}
    save('stored-cache-verified.json',result)
    save('stored-cache-readback-status.json',result)
    print(json.dumps(result),flush=True)

if __name__ == '__main__':
    os.umask(0o077)
    try:
        main()
    except Exception as exc:
        save('stored-cache-readback-status.json', {'phase':'failed','error_class':type(exc).__name__,'time':time.time()})
        raise
