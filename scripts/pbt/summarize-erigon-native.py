#!/usr/bin/env python3
"""Summarize measured native replay timing without mixing in restart audits."""
import argparse
import json
from pathlib import Path
import re
import statistics


UNITS = {'h': 3600, 'm': 60, 's': 1, 'ms': .001, 'µs': .000001,
         'us': .000001, 'ns': .000000001}
DURATION = re.compile(r'(\d+(?:\.\d+)?)(ns|µs|us|ms|s|m|h)')


def duration(value):
    parts = list(DURATION.finditer(value))
    if not parts or ''.join(part.group() for part in parts) != value:
        return None
    return sum(float(part[1])*UNITS[part[2]] for part in parts)


def summarize(trial):
    timing = json.loads((trial/'timing.json').read_text())
    bounds = timing['log_window']
    with (trial/'client.log').open('rb') as stream:
        stream.seek(bounds['start_byte'])
        lines = stream.read(bounds['end_byte']-bounds['start_byte']).decode().splitlines()
    stages = {}
    for line in lines:
        match = re.search(r'\[replay-profile\] (\w+)|\[mdbx\] (commit)', line)
        if not match:
            continue
        stage = match[1] or 'mdbxCommit'
        values = stages.setdefault(stage, {})
        for key, value in re.findall(r'(\w+)=([^\s]+)', line[match.end():]):
            seconds = duration(value)
            if seconds is not None:
                values.setdefault(key, []).append(seconds)
    details = {stage: {key: {'count': len(values), 'mean_seconds': statistics.mean(values),
                            'max_seconds': max(values), 'total_seconds': sum(values)}
                       for key, values in fields.items()} for stage, fields in stages.items()}
    status = json.loads((trial/'status.json').read_text())
    io = json.loads((trial/'io.json').read_text())
    return {'variant': trial.name, 'status': status, 'timing': timing,
            'device_write_MiB_per_block': io['device_write_bytes_per_block']/1024**2,
            'process_write_MiB_per_block': io['process_write_bytes_per_block']/1024**2,
            'stages': details,
            'scope': 'Log stages cover the timed replay window, including the warmup blocks recorded in timing.replay. '
                     'Nested stage totals overlap. Device IO covers the entire VM; '
                     'process IO may omit mmap write attribution. Fixed CPU/RAM limits '
                     'do not establish hardware equivalence with the original source VM.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trial', type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.trial), indent=2))
