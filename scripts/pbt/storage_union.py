"""Warm the optional native storage filter with a verified read-only RPC."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from pipeline_rpc import RPC, save

PARAMS = ['0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2',
          '0x'+hashlib.sha256(b'pbt-1-storage-union-readonly-warmup').hexdigest(), 'latest']


def verify_warmup(rpc, head, baseline=None):
    assert rpc.head() == head, 'Warmup must start at the audited head'
    started = time.monotonic()
    value = rpc.call('eth_getStorageAt', PARAMS, timeout=1800)
    assert isinstance(value, str) and value.startswith('0x') and len(bytes.fromhex(value[2:])) == 32
    assert rpc.head() == head, 'Read-only warmup changed the head'
    if baseline is not None:
        assert baseline['head'] == head and baseline['params'] == PARAMS
        assert value == baseline['value'], 'Native storage result differs from the pinned release'
    return {'time': time.time(), 'head': head, 'params': PARAMS, 'value': value,
            'seconds': time.monotonic()-started, 'head_unchanged': True,
            'pinned_value_verified': baseline is not None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    assert not args.output.exists(), 'Inspect an earlier warmup before retrying'
    before = json.loads(args.before.read_text())['head']
    baseline = json.loads(args.baseline.read_text()) if args.baseline else None
    save(args.output, verify_warmup(RPC(), before, baseline))
