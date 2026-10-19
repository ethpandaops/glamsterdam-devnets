#!/usr/bin/env python3
"""Export a bounded raw-block fixture from the canonical Geth replay source."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

from pipeline_rpc import ROOT, RPC, save


def main(args):
    assert 1 <= args.end-args.start+1 <= 256
    output = Path('/data/pbt-1/raw-replay-fixture')
    assert not output.exists(), 'Preserve existing fixture and inspect before retrying'
    output.mkdir()
    rpc = RPC()
    files = []
    for number in range(args.start, args.end+1):
        record = json.loads(gzip.decompress((ROOT/'blocks'/f'{number:08d}.json.gz').read_bytes()))
        header = rpc.call('eth_getBlockByNumber', [hex(number), False])
        for key, field in [('hash', 'hash'), ('stateRoot', 'state_root'), ('blockAccessListHash', 'bal_hash')]:
            assert header[key] == record[field], (number, key)
        raw = rpc.call('debug_getRawBlock', [hex(number)])
        assert raw.startswith('0x') and len(raw) > 100
        data = gzip.compress(json.dumps({'number': number, 'hash': record['hash'], 'raw': raw}).encode(), compresslevel=1)
        name = f'{number:08d}.json.gz'
        (output/name).write_bytes(data)
        files.append({'name': name, 'sha256': hashlib.sha256(data).hexdigest()})
    save(output/'manifest.json', {'start': args.start, 'end': args.end, 'source': 'Geth debug_getRawBlock', 'files': files})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--end', type=int, required=True)
    main(parser.parse_args())
