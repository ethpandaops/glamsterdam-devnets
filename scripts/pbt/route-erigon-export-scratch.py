#!/usr/bin/env python3
"""One-time scratch routing for the already-running native N exporter.

Existing ETL providers own their open file descriptors (including mmap); future
CreateTemp calls resolve the directory again. Atomic rename-exchange preserves
the old directory and redirects only future files. Never moves database files.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time

BASE = Path('/data/pbt-1')
TMP = BASE / 'rehearsal-24453558/erigon/temp'
OLD = TMP.with_name('temp-before-volume-routing')
MOUNT = Path('/mnt/pbt-export-scratch')
NEW = MOUNT / 'native-temp'
PROOF = BASE / 'export-scratch-routing.json'
PID = 47602
WRAPPER_PID = 47501
BINARY_SHA = '7d3c5beb8b985d54400c10cb09d6381860da387e85a8a74f0336795f08d025f4'


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def native():
    proc = Path('/proc') / str(PID)
    require(proc.exists(), 'Expected native exporter is absent')
    with (proc / 'exe').open('rb') as stream:
        require(hashlib.file_digest(stream, 'sha256').hexdigest() == BINARY_SHA, 'Native binary changed')
    require(b'export-pbt' in (proc / 'cmdline').read_bytes(), 'Not the expected native export')
    return (proc / 'stat').read_text().split()[21]


def check():
    require(socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1', 'Wrong host')
    started = native()
    require(not PROOF.exists() and not OLD.exists(), 'Routing already attempted')
    require(TMP.is_dir() and not TMP.is_symlink(), 'Unexpected original temp directory')
    require(os.path.ismount(MOUNT), 'Scratch volume not mounted')
    require(MOUNT.stat().st_dev != TMP.stat().st_dev, 'Scratch is not on another filesystem')
    require(shutil.disk_usage(MOUNT).free > 500_000_000_000, 'Insufficient new scratch capacity')
    require(not NEW.exists(), 'New scratch directory already exists')
    device = subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '--target', str(MOUNT)], text=True).strip()
    label = subprocess.check_output(['blkid', '-s', 'LABEL', '-o', 'value', device], text=True).strip()
    require(label == 'pbt-export-tmp', 'Unexpected volume label')
    visible = subprocess.check_output(['nsenter', '-t', str(PID), '-m', '--', 'stat', '-c', '%d', str(MOUNT)], text=True)
    require(int(visible) == MOUNT.stat().st_dev, 'Volume not visible in native mount namespace')
    files = list(TMP.iterdir())
    require(files and all(p.is_file() and not p.is_symlink() and p.name.startswith('erigon-sortable-buf-') for p in files), 'Unexpected old scratch contents')
    return {'native_pid': PID, 'native_start_ticks': started, 'native_binary_sha256': BINARY_SHA,
            'source': str(TMP), 'retained': str(OLD), 'new_scratch': str(NEW), 'mount_device': device}


def apply():
    proof = check()
    NEW.mkdir(mode=0o700)
    OLD.symlink_to(NEW)
    os.kill(PID, signal.SIGSTOP)
    try:
        deadline = time.monotonic() + 10
        while True:
            states = [p.read_text().split('State:', 1)[1].splitlines()[0].strip()[0]
                      for p in (Path('/proc') / str(PID) / 'task').glob('*/status')]
            if states and all(s in ('T', 't') for s in states):
                break
            require(time.monotonic() < deadline, 'Native threads did not stop for atomic routing')
            time.sleep(0.02)
        require(native() == proof['native_start_ticks'], 'Native PID changed')
        libc = ctypes.CDLL(None, use_errno=True)
        result = libc.renameat2(-100, os.fsencode(TMP), -100, os.fsencode(OLD), 2)
        require(result == 0, 'Atomic exchange failed: ' + os.strerror(ctypes.get_errno()))
        proof.update(time=time.time(), status='routed', old_directory_inode=OLD.stat().st_ino,
                     old_device=OLD.stat().st_dev, new_device=NEW.stat().st_dev,
                     files=[{'name': p.name, 'inode': p.stat().st_ino, 'size_at_routing': p.stat().st_size}
                            for p in OLD.iterdir()])
        save(PROOF, proof)
    finally:
        os.kill(PID, signal.SIGCONT)
    print(json.dumps({k: v for k, v in proof.items() if k != 'files'}))


def watch():
    proof = json.loads(PROOF.read_text())
    old_ids = {(proof['old_device'], p['inode']) for p in proof['files']}
    while True:
        unit = dict(line.split('=', 1) for line in subprocess.check_output([
            'systemctl', 'show', 'pbt-1-native-anchor-export', '-p', 'MainPID', '-p', 'ActiveState',
            '-p', 'Result'], text=True).splitlines())
        if unit['MainPID'] == '0':
            save(BASE / 'export-scratch-space-status.json', {
                'time': time.time(), 'status': 'export_wrapper_exited_inspect_native_results',
                'old_scratch_reclaimed': proof['status'] != 'routed', 'unit': unit})
            return
        require(unit['MainPID'] == str(WRAPPER_PID), 'Export wrapper identity changed')
        status = json.loads((BASE / 'pbt-export-24453558/status.json').read_text())
        owned_pid = owned_phase_process(status, proof)
        free = shutil.disk_usage(MOUNT).free
        save(BASE / 'export-scratch-space-status.json', {'time': time.time(), 'free_bytes': free,
             'native_pid': owned_pid, 'phase': status['phase'], 'scope': 'export_and_verify_scratch'})
        if free < 50_000_000_000:
            if owned_pid is not None:
                os.kill(owned_pid, signal.SIGINT)
            raise RuntimeError('Scratch reserve reached; interrupted owned native child if present')
        held = set()
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                for fd in (proc / 'fd').iterdir():
                    try:
                        stat = fd.stat()
                        if (stat.st_dev, stat.st_ino) in old_ids:
                            held.add((stat.st_dev, stat.st_ino))
                    except (FileNotFoundError, PermissionError):
                        pass
            except (FileNotFoundError, PermissionError):
                pass
        if not held and proof['status'] == 'routed':
            require(OLD.is_dir() and not OLD.is_symlink() and OLD.stat().st_ino == proof['old_directory_inode'], 'Retained directory changed')
            require({p.name for p in OLD.iterdir()} == {p['name'] for p in proof['files']}, 'Retained file list changed')
            for item in proof['files']:
                path = OLD / item['name']
                require(not path.is_symlink() and path.stat().st_ino == item['inode'], 'Retained file identity changed')
            reclaimed = sum((OLD / p['name']).stat().st_blocks * 512 for p in proof['files'])
            for item in proof['files']:
                (OLD / item['name']).unlink()
            OLD.rmdir()
            proof.update(status='old_scratch_reclaimed_after_all_descriptors_closed', reclaimed_bytes=reclaimed,
                         reclaimed_at=time.time())
            save(PROOF, proof)
        time.sleep(20)


def validate_phase_process(status, proof, command, expected, parent, cgroup, started):
    require(status['phase'] in ('export', 'verify'), 'Unexpected native phase')
    require(command == expected, 'Native phase command changed')
    require(parent == WRAPPER_PID and '/pbt-1-native-anchor-export.service' in cgroup,
            'Native phase is not owned by the export wrapper')
    if status['phase'] == 'export':
        require(status['pid'] == PID and started == proof['native_start_ticks'],
                'Original native exporter identity changed')


def owned_phase_process(status, proof):
    if status['phase'] not in ('export', 'verify'):
        return None
    proc = Path('/proc') / str(status['pid'])
    if not proc.exists():
        return None  # Normal phase transition; the wrapper updates its status next.
    try:
        command = [os.fsdecode(value) for value in (proc / 'cmdline').read_bytes().split(b'\0') if value]
        if not command:
            return None  # An exiting child can briefly remain as a zombie.
        stat = (proc / 'stat').read_text().split()
        expected = json.loads((BASE / 'pbt-export-24453558/started.json').read_text())['commands'][status['phase']]
        validate_phase_process(status, proof, command, expected, int(stat[3]),
                               (proc / 'cgroup').read_text(), stat[21])
        with (proc / 'exe').open('rb') as stream:
            require(hashlib.file_digest(stream, 'sha256').hexdigest() == BINARY_SHA, 'Native binary changed')
    except FileNotFoundError:
        return None
    return status['pid']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true')
    group.add_argument('--watch', action='store_true')
    args = parser.parse_args()
    if args.apply:
        apply()
    elif args.watch:
        watch()
    else:
        print(json.dumps(check()))
