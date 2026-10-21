#!/usr/bin/env python3
"""Copy the older exporter's recovery tree onto spare Geth-2 space.

The short-lived SSH key is constrained by the source's authorized_keys to a
read-only rsync export. No database starts and no source files are removed.
"""
import json
from pathlib import Path
import shutil
import socket
import subprocess
import time

ROOT = Path('/data/pbt-1/erigon-exporter-recovery')


def save(name, value):
    path = ROOT / name
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def main():
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-geth-2'
    assert not (ROOT / 'started.json').exists() and not (ROOT / 'tree').exists()
    assert shutil.disk_usage(ROOT).free > 1_000_000_000_000
    assert (ROOT / 'transfer-key').stat().st_mode & 0o777 == 0o600
    ssh = ('ssh -i ' + str(ROOT / 'transfer-key') + ' -o IdentitiesOnly=yes'
           ' -o StrictHostKeyChecking=yes -o UserKnownHostsFile=' + str(ROOT / 'known_hosts')
           + ' -o BatchMode=yes -o ConnectTimeout=20')
    common = ['rsync', '-aH', '--numeric-ids', '-e', ssh,
              'root@10.35.0.2:./', str(ROOT / 'tree') + '/']
    save('started.json', {'time': time.time(), 'source_host': 'lighthouse-erigon-1',
                         'source': '/data/pbt-1/v3-source-upgrade', 'destination': str(ROOT / 'tree'),
                         'geth_database_modified': False, 'source_deleted': False})
    try:
        save('status.json', {'phase': 'copying', 'time': time.time()})
        with (ROOT / 'copy.log').open('x') as log:
            subprocess.run(common[:2] + ['--info=progress2', '--partial'] + common[2:],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        save('status.json', {'phase': 'full_file_checksum_comparison', 'time': time.time()})
        result = subprocess.run(common[:2] + ['--dry-run', '--checksum', '--itemize-changes'] + common[2:],
                                capture_output=True, text=True, check=True)
        (ROOT / 'checksum-comparison.txt').write_text(result.stdout)
        (ROOT / 'checksum-comparison.stderr').write_text(result.stderr)
        assert not result.stdout.strip(), 'Recovery copy differs from the source'
        save('complete.json', {'time': time.time(), 'status': 'full_tree_checksum_comparison_passed',
                               'source': '/data/pbt-1/v3-source-upgrade',
                               'destination': str(ROOT / 'tree'), 'source_host': 'lighthouse-erigon-1',
                               'comparison': 'rsync --dry-run --checksum --itemize-changes: zero changes',
                               'geth_database_modified': False, 'source_deleted': False})
        save('status.json', {'phase': 'verified_recovery_copy', 'time': time.time()})
    except Exception as exc:
        save('status.json', {'phase': 'failed', 'time': time.time(), 'error_class': type(exc).__name__})
        raise
    finally:
        (ROOT / 'transfer-key').unlink(missing_ok=True)


if __name__ == '__main__':
    main()
