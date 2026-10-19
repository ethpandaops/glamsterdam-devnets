#!/usr/bin/env python3
"""Bounded scratch-file storage benchmark; never opens an execution database."""
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT = Path('/data/pbt-1/io-probe')


def main():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    assert ROOT.resolve() == ROOT, 'Refusing symlinked benchmark directory'
    report = ROOT / 'storage-benchmark.json'
    data = ROOT / 'fio-scratch.dat'
    assert not report.exists() and not data.exists(), 'Inspect existing probe before running again'
    assert shutil.disk_usage(ROOT).free > 30 * 1024**3
    result = {'started_at': time.time(), 'data_path': str(data), 'cases': {},
              'fio_version': subprocess.check_output(['fio', '--version'], text=True).strip(),
              'scope': 'Scratch-file capacity only; does not prove Erigon replay throughput'}
    def run(name, arguments):
        command = ['fio', '--name='+name, '--filename='+str(data), '--size=8G',
                   '--group_reporting=1', '--output-format=json', '--refill_buffers=1',
                   '--randrepeat=1', '--randseed=8037', '--end_fsync=1', *arguments]
        start = time.time()
        proc = subprocess.run(command, capture_output=True, text=True, timeout=300)
        (ROOT/(name+'.stderr')).write_text(proc.stderr)
        assert proc.returncode == 0, (name, proc.returncode, proc.stderr[-2000:])
        raw = json.loads(proc.stdout)
        (ROOT/(name+'.json')).write_text(json.dumps(raw, indent=2)+'\n')
        job = raw['jobs'][0]
        assert job['error'] == 0, job['error']
        result['cases'][name] = {'started_at': start, 'finished_at': time.time(),
            'command': command, 'write_iops': job['write']['iops'],
            'write_bytes_per_second': job['write']['bw_bytes'],
            'write_latency_ns': job['write']['lat_ns'], 'sync': job.get('sync')}
        report.write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({'case': name, 'write_iops': job['write']['iops'],
                          'write_MiB_per_second': job['write']['bw_bytes']/1024**2}), flush=True)
    run('fill', ['--ioengine=libaio', '--rw=write', '--bs=1M', '--direct=1', '--iodepth=16'])
    run('random_direct', ['--ioengine=libaio', '--rw=randwrite', '--bs=4k', '--direct=1',
                          '--iodepth=128', '--time_based=1', '--runtime=30', '--ramp_time=5'])
    run('random_buffered_sync', ['--ioengine=psync', '--rw=randwrite', '--bs=4k', '--direct=0',
                                 '--fdatasync=8192', '--time_based=1', '--runtime=30', '--ramp_time=5'])
    result['finished_at'] = time.time()
    report.write_text(json.dumps(result, indent=2)+'\n')
    # This exact file was created by this invocation; results remain for review.
    data.unlink()


if __name__ == '__main__':
    main()
