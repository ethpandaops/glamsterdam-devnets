#!/usr/bin/env python3
"""Stage direct E1 recovery download after its own H startup; --run reclaims old archive.

Run on Erigon-1 with original-provenance/ and source-url already staged under
/data/pbt-1/direct-recovery-replacement. Starts no service and touches no database.
The existing pbt-recovery-snapshot service performs the subsequent streamed download.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

BASE = Path('/data/pbt-1')
ROOT = BASE / 'direct-recovery-replacement'
VOLUME = Path('/mnt/pbt-recovery')
SHA = 'b4ab8e0831bd95ddce05b9f52c040de7eaf4a9b8b1fa49106cb3e9cd88938146'
SIZE = 461165199193
KEY = 'pbt-1/20261020-erigon-v3-head/erigon/24503958/snapshot.tar.zst'
UUID = '9d3c985b-82b8-418b-a78c-ee3aa78544dd'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    assert ROOT.resolve() == ROOT and VOLUME.resolve() == VOLUME
    # Reuse the exact-file identity/owner and durable-save helpers from E2.
    spec = importlib.util.spec_from_file_location('replacement', ROOT / 'replacement-helpers.py')
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    locks = []
    for path in (ROOT / 'run.lock', BASE / 'qualification/run.lock',
                 BASE / 'v3-head-restore/restore.lock', VOLUME / 'download.lock'):
        handle = path.open('a')
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(handle)
    assert not (ROOT / 'started.json').exists(), 'Inspect prior attempt before resuming'
    complete = read(BASE / 'v3-head-restore/complete.json')
    bundle_path = BASE / 'v3-head-restore/release-bundle.json'
    bundle = read(bundle_path)
    meta = bundle['metadata']
    assert bundle['key'] == KEY and meta['archive_sha256'] == SHA and meta['archive_bytes'] == SIZE
    assert meta['full_remote_sha256_verified'] is True
    assert complete['bundle_sha256'] == digest(bundle_path)
    assert complete['archive_sha256'] == SHA and complete['archive_transfer'] == 'stream'
    db = (BASE / 'erigon').stat()
    assert complete['restored_identity'] == {'device': db.st_dev, 'inode': db.st_ino}
    proof_path = BASE / 'qualification/result.json'
    proof = read(proof_path)
    assert proof['host'] == 'lighthouse-erigon-1' and proof['status'] == 'startup_checks_passed'
    assert proof['memory_gib'] == 32 and proof['cpus'] == 8
    assert proof['preparation_path'] == 'restored_verified_H_release'
    assert proof['source_release_archive_sha256'] == SHA and proof['source_release_key'] == KEY
    for field in ('head', 'head_hash', 'state_root', 'image', 'converter_build'):
        assert proof[field] == meta[field]
    assert proof['genesis_time'] is None and proof['native_reopen_verified'] is True
    assert proof['v3_format_verified'] is True
    for field in ('first_stopped_state', 'stopped_state'):
        state = proof[field]
        assert not state['Running'] and not state['OOMKilled'] and state['ExitCode'] == 0
    for unit in ('pbt-1-v3-head-restore', 'pbt-1-worker-qualification', 'pbt-recovery-snapshot'):
        result = subprocess.check_output(['systemctl', 'show', unit, '-p', 'MainPID',
                                          '-p', 'ActiveState', '-p', 'Result'], text=True)
        state = dict(line.split('=', 1) for line in result.splitlines())
        assert state == {'MainPID': '0', 'ActiveState': 'inactive', 'Result': 'success'}, unit
    containers = set(subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).splitlines())
    assert containers <= {'nginx-proxy-cert-linker', 'nginx-proxy-cert-loader', 'nginx-proxy-gen',
                          'nginx-proxy', 'vector', 'prometheus', 'node_exporter'}
    assert subprocess.check_output(['findmnt', '-n', '-o', 'UUID', '--target', str(VOLUME)], text=True).strip() == UUID
    provenance = ROOT / 'original-provenance'
    manifest = read(provenance / 'manifest.json')
    assert manifest['volume_uuid'] == UUID
    old = VOLUME / 'erigon-24503958.tar.zst'
    old_identity = helpers.identity(old)
    assert old_identity == manifest['old_archive'] and not helpers.owners(old)
    for name, item in manifest['files'].items():
        if item['exists']:
            assert digest(provenance / name) == item['sha256']
        # Qualification can legitimately change during the H restore.
        if name == 'recovery-job.json' or item['source'].startswith(str(VOLUME) + '/'):
            current = Path(item['source'])
            if item['exists']:
                assert digest(current) == item['sha256']
            else:
                assert not current.exists()
    oldproof = read(VOLUME / 'archive-verified.json')
    assert oldproof['sha256'] == manifest['old_archive_sha256']
    assert oldproof['bytes'] == old_identity['bytes'] and oldproof['mtime_ns'] == old_identity['mtime_ns']
    assert not old.with_suffix('.zst.part').exists()
    assert shutil.disk_usage(VOLUME).free + old.stat().st_blocks * 512 > SIZE + 20_000_000_000
    # Check fresh single-object access before deleting the superseded backup.
    url = (ROOT / 'source-url').read_text().strip()
    request = urllib.request.Request(url, headers={'Range': 'bytes=0-0', 'If-Match': bundle['etag']})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == 206 and response.headers['ETag'] == bundle['etag']
            assert response.headers['Content-Range'] == f'bytes 0-0/{SIZE}'
            assert len(response.read()) == 1
    except Exception:
        raise RuntimeError('Corrected archive access check failed; URL withheld') from None
    job = read(Path('/etc/pbt-recovery/job.json'))
    job.update(archive_bytes=SIZE, archive_sha256=SHA, key=KEY, etag=bundle['etag'],
               unpacked_bytes=bundle['unpacked_upper_bound_bytes'], restore=False)
    receipt = dict(time=time.time(), old_archive=old_identity, archive_sha256=SHA,
                   archive_bytes=SIZE, qualification_sha256=digest(proof_path),
                   live_database_unchanged=True, restore=False)
    if '--run' not in sys.argv:
        print(json.dumps(dict(preflight='passed', **receipt)))
        return
    helpers.save(ROOT / 'started.json', receipt)
    assert helpers.identity(old) == old_identity
    old.unlink()
    for name in ('archive-verified.json', 'download-state.json', 'status.json'):
        (VOLUME / name).unlink()
    helpers.syncdir(VOLUME)
    helpers.save(Path('/etc/pbt-recovery/job.json'), job)
    target = Path('/etc/pbt-recovery/source-url')
    with target.open('w') as stream:
        stream.write(url + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    target.chmod(0o600)
    helpers.save(ROOT / 'ready.json', dict(phase='ready_for_direct_recovery_download', **receipt))
    print('Corrected recovery job staged; start pbt-recovery-snapshot.service. Database unchanged.')


if __name__ == '__main__':
    os.umask(0o077)
    main()
