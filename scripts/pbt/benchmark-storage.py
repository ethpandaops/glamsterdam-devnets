#!/usr/bin/env python3
"""Compare dedicated files on the Besu VM's local disk and attached volume."""
import argparse
import datetime
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

LOCAL = Path('/data/pbt-1/storage-benchmark-local')
VOLUME = Path('/mnt/glamsterdam_pbt_1_besu_benchmark')
RESULTS = Path('/data/pbt-1/storage-benchmark')
PROFILES = [
    ('sequential_read_1m_qd32', ['--rw=read', '--bs=1M', '--iodepth=32']),
    ('sequential_write_1m_qd32', ['--rw=write', '--bs=1M', '--iodepth=32']),
    ('random_read_4k_qd1', ['--rw=randread', '--bs=4k', '--iodepth=1']),
    ('random_read_16k_qd32', ['--rw=randread', '--bs=16k', '--iodepth=32']),
    ('mixed_16k_qd32', ['--rw=randrw', '--rwmixread=70', '--bs=16k', '--iodepth=32']),
    ('durable_write_4k_qd1', [
        '--rw=write', '--bs=4k', '--iodepth=1', '--ioengine=psync', '--fdatasync=1']),
]


def run(*args):
    return subprocess.check_output(args, text=True, timeout=30).strip()


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def state(directory, phase, **fields):
    value = {'time': time.time(), 'phase': phase, **fields}
    save(directory / 'status.json', value)
    print(json.dumps(value), flush=True)


def metrics(job):
    result = {'usr_cpu': job['usr_cpu'], 'sys_cpu': job['sys_cpu']}
    for direction in ('read', 'write'):
        data = job[direction]
        if data['io_bytes']:
            result[direction] = {
                'bytes': data['io_bytes'], 'iops': data['iops'],
                'mib_per_second': data['bw_bytes'] / 1024**2,
                'completion_latency_ns': data['clat_ns'],
            }
    sync = job.get('sync', {})
    # fio 3.39's psync output can report total_ios=0 while lat_ns.N
    # contains every fdatasync sample. Preserve that measured distribution.
    if sync.get('total_ios') or sync.get('lat_ns', {}).get('N'):
        result['fdatasync'] = sync
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    assert re.fullmatch(r'[a-z0-9-]+', args.run_id), 'Unsafe run id'
    directory = RESULTS / args.run_id
    directory.mkdir(parents=True, exist_ok=False)
    paths = {}
    try:
        assert VOLUME.is_mount() and not VOLUME.is_symlink(), 'Volume not mounted'
        mounts = json.loads(run('findmnt', '-J', '-T', str(VOLUME)))['filesystems']
        assert len(mounts) == 1 and mounts[0]['source'] == '/dev/sda', mounts
        assert run('blkid', '-s', 'UUID', '-o', 'value', '/dev/sda') == \
            '125b91a3-eb46-41f9-bfc1-29a3ecf21a81', 'Unexpected volume identity'
        client = json.loads(run('docker', 'inspect', 'pbt-1-besu-execution'))[0]
        assert not client['State']['Running'], 'Besu must remain stopped'
        LOCAL.mkdir(exist_ok=True)
        assert not LOCAL.is_symlink() and LOCAL.stat().st_dev != VOLUME.stat().st_dev
        size = 32 * 1024**2 if args.smoke else 64 * 1024**3
        runtime, ramp = (1, 0) if args.smoke else (120, 60)
        for label, root in [('local', LOCAL), ('volume', VOLUME)]:
            assert shutil.disk_usage(root).free > size + 100 * 1024**3
            testdir = root / ('fio-' + args.run_id)
            testdir.mkdir(exist_ok=False)
            path = testdir / 'test-data.bin'
            with path.open('xb') as handle:
                handle.truncate(size)
            paths[label] = path
        manifest = {
            'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'fio_version': run('fio', '--version'),
            'kernel': run('uname', '-r'), 'hostname': run('hostname'),
            'cpu': json.loads(run('lscpu', '-J')),
            'block_devices': json.loads(run('lsblk', '-J', '-b', '-o',
                                           'NAME,SIZE,FSTYPE,MOUNTPOINTS')),
            'mounts': {label: json.loads(run('findmnt', '-J', '-T', str(path)))
                       for label, path in paths.items()},
            'file_bytes_each': size, 'runtime_seconds': runtime,
            'warmup_seconds': ramp, 'smoke_only': args.smoke,
            'method': 'Single-job direct I/O to fully written files; alternating disk order. '
                      'Live filesystem comparison, not a raw-device or migration benchmark.',
            'besu_initial_state': client['State'],
        }
        save(directory / 'manifest.json', manifest)
        deadline = time.monotonic() + 900
        while 'ext4lazyinit' in run('ps', '-eo', 'comm'):
            state(directory, 'waiting_for_filesystem_initialization')
            assert time.monotonic() < deadline, 'Filesystem initialization still active'
            time.sleep(15)

        def fio(label, name, options, timed):
            path = paths[label]
            assert path.is_file() and not path.is_symlink()
            assert not json.loads(run('docker', 'inspect',
                                     'pbt-1-besu-execution'))[0]['State']['Running']
            output = directory / f'{name}-{label}.json'
            command = [
                'fio', '--name=' + name, '--filename=' + str(path),
                '--size=' + str(size), '--direct=1', '--ioengine=libaio',
                '--numjobs=1', '--group_reporting=1', '--refill_buffers=1',
                '--randrepeat=1', '--randseed=20261020', '--fallocate=none',
                '--allow_file_create=0', '--end_fsync=1',
                '--percentile_list=50:95:99:99.9', '--output-format=json',
                '--output=' + str(output), *options,
            ]
            if timed:
                command += ['--time_based=1', '--runtime=' + str(runtime),
                            '--ramp_time=' + str(ramp)]
            save(directory / f'{name}-{label}-command.json', command)
            state(directory, 'measuring' if timed else 'prefilling',
                  disk=label, workload=name)
            completed = subprocess.run(command, text=True, capture_output=True,
                                       timeout=runtime + ramp + 120 if timed else 1800)
            (directory / f'{name}-{label}.stderr').write_text(completed.stderr)
            assert completed.returncode == 0, completed.stderr[-2000:]
            data = json.loads(output.read_text())
            assert len(data['jobs']) == 1 and data['jobs'][0]['error'] == 0, data
            job = data['jobs'][0]
            if not timed:
                assert job['write']['io_bytes'] == size and path.stat().st_size == size
                assert path.stat().st_blocks * 512 >= size, 'Unwritten/sparse test file'
            else:
                assert job['job_runtime'] >= runtime * 1000 * 0.95
            return metrics(job)

        for label in paths:
            fio(label, 'prefill', ['--rw=write', '--bs=1M', '--iodepth=32'], False)
        rows = []
        profiles = [PROFILES[0], PROFILES[-1]] if args.smoke else PROFILES
        for index, (name, options) in enumerate(profiles):
            order = ['local', 'volume'] if index % 2 == 0 else ['volume', 'local']
            for label in order:
                row = {'workload': name, 'disk': label,
                       'metrics': fio(label, name, options, True)}
                rows.append(row)
                save(directory / 'results.json', rows)
                print(json.dumps(row), flush=True)
        for path in paths.values():
            assert path.is_file() and not path.is_symlink()
            path.unlink()
            path.parent.rmdir()
        state(directory, 'complete', measured_jobs=len(rows),
              test_files_removed=True, smoke_only=args.smoke)
    except Exception as exc:
        state(directory, 'failed', error=str(exc),
              test_files_preserved=[str(path) for path in paths.values()])
        raise


if __name__ == '__main__':
    main()
