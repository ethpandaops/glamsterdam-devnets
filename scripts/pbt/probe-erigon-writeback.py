#!/usr/bin/env python3
"""Measure earlier kernel writeback during live replay, then restore host settings."""
import fcntl
import json
from pathlib import Path
import subprocess
import time

from pipeline_rpc import ROOT, save

RUN = Path('/data/pbt-1/native-replay')
UNIT = 'pbt-1-native-replay-client'
SETTINGS = ('dirty_background_bytes', 'dirty_background_ratio')


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def settings():
    return {key: int(Path('/proc/sys/vm', key).read_text()) for key in SETTINGS}


def set_value(key, value):
    command('sysctl', '-w', f'vm.{key}={value}')


def sample(pid):
    assert command('systemctl', 'is-active', UNIT) == 'active'
    assert int(command('systemctl', 'show', UNIT, '-p', 'MainPID', '--value')) == pid
    status = json.loads((ROOT/'status.json').read_text())
    assert status['phase'] == 'native_replaying', status
    assert time.time()-status['time'] < 120, 'Replay has not reported progress for two minutes'
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('Dirty', 'Writeback', 'MemAvailable'):
            memory[key] = int(value.split()[0])*1024
    io = dict(line.split(': ', 1) for line in Path(f'/proc/{pid}/io').read_text().splitlines())
    return {'time': time.time(), 'monotonic': time.monotonic(),
            'head': status['head'], 'validated_at': status['time'],
            'memory': memory, 'io': {k: int(v) for k, v in io.items()}}


def main():
    lock = (ROOT/'writeback-probe.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    destination = RUN/'writeback-probe.json'
    assert not destination.exists(), 'Inspect previous trial before recovery'
    pid = int(command('systemctl', 'show', UNIT, '-p', 'MainPID', '--value'))
    assert pid > 0
    service = command('systemctl', 'cat', UNIT)
    assert 'MDBX_NO_FSYNC' not in service
    original = settings()
    report = {'started': time.time(), 'pid': pid, 'original': original,
              'normal_durability': True, 'phases': [], 'restored': False}
    save(destination, report)
    try:
        for name, seconds in [('baseline', 120), ('early_writeback', 180), ('restored', 120)]:
            if name == 'early_writeback':
                set_value('dirty_background_bytes', 64*1024**2)
                assert settings() == {'dirty_background_bytes': 64*1024**2, 'dirty_background_ratio': 0}
            elif name == 'restored':
                key = 'dirty_background_bytes' if original['dirty_background_bytes'] else 'dirty_background_ratio'
                set_value(key, original[key])
                assert settings() == original
            phase = {'name': name, 'settings': settings(), 'samples': [sample(pid)]}
            report['phases'].append(phase)
            save(destination, report)
            deadline = time.monotonic()+seconds
            while time.monotonic() < deadline:
                time.sleep(min(5, max(0, deadline-time.monotonic())))
                phase['samples'].append(sample(pid))
                save(destination, report)
            first, last = phase['samples'][0], phase['samples'][-1]
            phase['blocks'] = last['head']-first['head']
            phase['seconds'] = last['monotonic']-first['monotonic']
            phase['blocks_per_second'] = phase['blocks']/phase['seconds']
            print(json.dumps({k: v for k, v in phase.items() if k != 'samples'}), flush=True)
        report['completed'] = time.time()
    finally:
        key = 'dirty_background_bytes' if original['dirty_background_bytes'] else 'dirty_background_ratio'
        set_value(key, original[key])
        report['restored'] = settings() == original
        report['finished'] = time.time()
        save(destination, report)
        assert report['restored'], 'Restore original writeback settings before proceeding'


if __name__ == '__main__':
    main()
