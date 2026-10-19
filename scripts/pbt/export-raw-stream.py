#!/usr/bin/env python3
"""Export the remaining canonical raw blocks in independently verified chunks."""
import argparse
import fcntl
import importlib.util
import json
from pathlib import Path
import time
from types import SimpleNamespace

from pipeline_rpc import ROOT, ANCHOR, save

OUTPUT = Path('/data/pbt-1/raw-stream')


def main(start):
    lock = (ROOT/'raw-export.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not OUTPUT.exists(), 'Inspect previous export before recovery'
    plan = json.loads((ROOT/'workload.json').read_text())
    end = ANCHOR+plan['v2']['final_records']
    assert ANCHOR < start <= end
    OUTPUT.mkdir()
    save(OUTPUT/'request.json', {'start': start, 'end': end, 'chunk_size': 256})
    spec = importlib.util.spec_from_file_location('fetch', Path(__file__).with_name('fetch-raw-replay-blocks.py'))
    fetch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch)
    for low in range(start, end+1, 256):
        high = min(end, low+255)
        while not (ROOT/'blocks'/f'{high:08d}.json.gz').exists():
            save(OUTPUT/'status.json', {'phase': 'waiting_for_payload', 'time': time.time(),
                'start': start, 'end': end, 'next': low, 'waiting_for': high})
            time.sleep(5)
        fetch.main(SimpleNamespace(start=low, end=high, output=OUTPUT/f'{low:08d}'))
        save(OUTPUT/'status.json', {'phase': 'exporting', 'time': time.time(),
            'start': start, 'end': end, 'last': high, 'exported': high-start+1})
    result = {'phase': 'complete', 'time': time.time(), 'start': start, 'end': end,
              'exported': end-start+1}
    save(OUTPUT/'complete.json', result)
    save(OUTPUT/'status.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=int, required=True)
    args = parser.parse_args()
    try:
        main(args.start)
    except Exception as exc:
        save(OUTPUT/'status.json', {'phase': 'failed', 'time': time.time(), 'error': str(exc)})
        raise
