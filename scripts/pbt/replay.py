#!/usr/bin/env python3
"""Replay immutable generated block records, requiring VALID and identical commitments."""
import argparse
import fcntl
import gzip
import json
import shutil
import time
from pipeline_rpc import RPC, ROOT, ANCHOR, baseline, save


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workload-blocks', type=int, required=True)
    a = p.parse_args()
    lock = (ROOT / 'replay.lock').open('w'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    rpc = RPC(); head = rpc.head(); number = int(head['number'], 16)
    if number == ANCHOR:
        baseline(rpc)
    else:
        prior = json.loads(gzip.decompress((ROOT / 'blocks' / f'{number:08d}.json.gz').read_bytes()))
        assert prior['hash'] == head['hash'] and prior['state_root'] == head['stateRoot']
    target = ANCHOR + 3 + a.workload_blocks
    started = time.time(); first = number;active_seconds=0
    plan=json.loads((ROOT/'workload.json').read_text())
    while number < target:
        path = ROOT / 'blocks' / f'{number+1:08d}.json.gz'
        if not path.exists():
            save(ROOT / 'status.json', {'phase': 'waiting_for_payload', 'time': time.time(),
                                      'head': number, 'target_head': target})
            time.sleep(5); continue
        assert shutil.disk_usage(ROOT).free > 150*10**9, 'Less than 150 GB free'
        record = json.loads(gzip.decompress(path.read_bytes()))
        assert record['number'] == number+1 and record['new_payload'][0]['parentHash'] == head['hash']
        before=time.monotonic();head = rpc.apply(record);active_seconds+=time.monotonic()-before
        number += 1
        status = {'phase': 'replaying', 'time': time.time(), 'head': number,
                  'target_head': target, 'workload_blocks': max(0, number-ANCHOR-3),
                  'blocks_per_second': (number-first)/(time.time()-started), 'hash': head['hash'],
                  'state_root': head['stateRoot'], 'bal_hash': head['blockAccessListHash']}
        status.update(active_blocks_per_second=(number-first)/active_seconds,
                      qualifying_blocks=max(0,number-ANCHOR-plan.get('v2',{}).get('qualifying_start_index',3)))
        save(ROOT / 'status.json', status)
        if number-first <= 4 or (number-ANCHOR) % 25 == 0:
            print(json.dumps(status), flush=True)
    status = {'phase': 'replay_complete', 'time': time.time(), 'head': number,
              'target_head': target, 'workload_blocks': a.workload_blocks, 'hash': head['hash'],
              'state_root': head['stateRoot'], 'bal_hash': head['blockAccessListHash']}
    status['qualifying_blocks']=max(0,number-ANCHOR-plan.get('v2',{}).get('qualifying_start_index',3))
    save(ROOT / 'status.json', status)
    print(json.dumps(status), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        save(ROOT / 'status.json', {'phase': 'failed', 'time': time.time(), 'error': str(exc)})
        raise
