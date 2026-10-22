#!/usr/bin/env python3
"""Protect the future stage_exec child of an already running conversion.

The Python conversion driver has already loaded its environment logic. Install
an atomic launcher at its integration path, preserving the exact binary inode
under integration.pinned. The current unsqueeze process keeps its original
executable and is not restarted. Only future stage_exec calls gain NO_PRUNE.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import time

SHA = 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03'
JOBS = {
    'head': ('glamsterdam-pbt-1-lighthouse-erigon-2',
             '/data/pbt-1/v3-tools-372df0e6',
             '/data/pbt-1/v3-head-upgrade', 'pbt-1-v3-head-upgrade'),
    'exporter': ('glamsterdam-pbt-1-lighthouse-erigon-1',
                 '/data/pbt-1/rehearsal-tools/erigon/build/bin',
                 '/data/pbt-1/v3-source-upgrade', 'pbt-1-v3-source-upgrade-v3'),
}


def main(kind):
    host, tools, evidence, unit = JOBS[kind]
    assert socket.gethostname() == host
    root = Path(evidence)
    assert json.loads((root / 'status.json').read_text())['phase'] == 'unsqueeze'
    active = subprocess.check_output(
        ['systemctl', 'show', unit, '-p', 'ActiveState', '--value'], text=True).strip()
    assert active == 'active'
    binary = Path(tools) / 'integration'
    saved = binary.with_name('integration.pinned')
    assert not saved.exists() and not (root / 'bal-retention-launcher.json').exists()
    with binary.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == SHA
    # A hardlink preserves the exact inode used by the current child process.
    os.link(binary, saved)
    launcher = (
        '#!/bin/sh\nset -eu\n'
        'if [ "${1-}" = stage_exec ]; then\n'
        '  export NO_PRUNE=true\n'
        '  echo "[pbt-preparation] stage_exec NO_PRUNE=true; pinned integration '
        + SHA + '" >&2\n'
        'fi\nexec ' + shlex.quote(str(saved)) + ' "$@"\n'
    )
    temporary = binary.with_name('integration.launcher.tmp')
    with temporary.open('x') as stream:
        stream.write(launcher)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o755)
    subprocess.run(['sh', '-n', str(temporary)], check=True)
    temporary.replace(binary)
    proof = {
        'time': time.time(), 'kind': kind, 'unit': unit,
        'current_conversion_restarted': False, 'scope': 'future stage_exec children',
        'launcher_path': str(binary),
        'launcher_sha256': hashlib.sha256(launcher.encode()).hexdigest(),
        'pinned_binary_path': str(saved), 'pinned_binary_sha256': SHA,
        'environment': {'NO_PRUNE': 'true'},
        'reason': 'stage_exec calls PruneExecutionStage; retain the BAL corpus',
    }
    (root / 'bal-retention-launcher.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps(proof))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=JOBS)
    main(parser.parse_args().kind)
