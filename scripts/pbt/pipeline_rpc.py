"""RPC and durable evidence helpers for the isolated PBT source VMs."""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path('/data/pbt-1/pipeline')
ANCHOR = 24452538
ANCHOR_HASH = '0x0fd7242bab5055dda36f374f352c78cae381daae9b3e8febe895dce35c907591'
ANCHOR_ROOT = '0xecf809f327549d4a93eeae29252e8f33b0e9f188cba92f0bb43207d4c7a9c9ca'


def save(path, obj):
    import os
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    with tmp.open('w') as f:
        json.dump(obj, f, separators=(',', ':')); f.write('\n'); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)


class RPC:
    def __init__(self):
        self.secret = bytes.fromhex((ROOT / 'jwt').read_text().strip())

    def call(self, method, params, engine=False, timeout=600):
        headers = {'Content-Type': 'application/json'}
        if engine:
            enc = lambda x: base64.urlsafe_b64encode(x).rstrip(b'=')
            body = enc(b'{"alg":"HS256","typ":"JWT"}') + b'.' + enc(json.dumps({'iat': int(time.time())}).encode())
            headers['Authorization'] = 'Bearer ' + (body + b'.' + enc(hmac.new(self.secret, body, hashlib.sha256).digest())).decode()
        data = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params}).encode()
        req = urllib.request.Request('http://127.0.0.1:' + ('18551' if engine else '18545'), data=data, headers=headers)
        result = json.load(urllib.request.urlopen(req, timeout=timeout))
        if 'error' in result:
            raise RuntimeError(f'{method}: {result["error"]}')
        return result['result']

    def head(self):
        return self.call('eth_getBlockByNumber', ['latest', False])

    def apply(self, record, warmup=1800):
        deadline = time.monotonic() + warmup
        delay = .01
        while True:
            s = self.call('engine_newPayloadV5', record['new_payload'], True)
            if s['status'] == 'VALID':
                assert s['latestValidHash'] == record['hash'], s
                break
            if s['status'] not in ('SYNCING', 'ACCEPTED') or time.monotonic() >= deadline:
                raise RuntimeError(f'newPayload {record["number"]}: {s}')
            self.call('engine_forkchoiceUpdatedV3', record['forkchoice'], True)
            time.sleep(delay); delay = min(delay * 2, 1)
        delay = .01
        while True:
            s = self.call('engine_forkchoiceUpdatedV3', record['forkchoice'], True)['payloadStatus']
            if s['status'] == 'VALID':
                assert s['latestValidHash'] == record['hash'], s
                break
            if s['status'] != 'SYNCING' or time.monotonic() >= deadline:
                raise RuntimeError(f'forkchoice {record["number"]}: {s}')
            time.sleep(delay); delay = min(delay * 2, 1)
        # Erigon can acknowledge forkchoice before its separate RPC view catches
        # up. Wait for that view; a differing commitment at the target is fatal.
        deadline = time.monotonic() + 120
        delay = .01
        while True:
            block = self.head()
            if block and int(block['number'], 16) >= record['number']:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f'RPC head did not reach {record["number"]} after VALID forkchoice')
            time.sleep(delay); delay = min(delay*2, .2)
        for key, want in [('hash', record['hash']), ('stateRoot', record['state_root']),
                          ('blockAccessListHash', record['bal_hash'])]:
            if block.get(key) != want:
                raise RuntimeError(f'{record["number"]} {key}: {block.get(key)} != {want}')
        return block


def baseline(rpc):
    block = rpc.head()
    assert int(block['number'], 16) == ANCHOR and block['hash'] == ANCHOR_HASH and block['stateRoot'] == ANCHOR_ROOT, block
    save(ROOT / 'baseline.json', block)
    return block
