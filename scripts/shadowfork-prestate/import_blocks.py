#!/usr/bin/env python3
"""Import the msf-1 prestate blocks (engine_newPayloadV4 params) into an EL whose CL is stopped.

Usage: import_blocks.py <engine url> <rpc url> <jwt hex file> <block1.json> <block2.json>
Prints one line; exits non-zero unless the EL ends at block 2's hash.
"""
import base64, hashlib, hmac, json, sys, time, urllib.request

engine, rpc, jwt_file, *blocks = sys.argv[1:6]
key = bytes.fromhex(open(jwt_file).read().strip().removeprefix("0x"))
BASE = "0x488010e5acf359838e53d5908b1c3cb166ddc7b84c04e3f14463a95c249a5ba8"
CHECK = {"8282-deposit": "0x0000bFF46984e3725691FA540a8C7589300D8282",
         "8282-exit": "0x000064D678505ad48F8cCb093BC65613800E8282"}
FUNDED = ["0x86cf016fb873d50a7b8f31eb154c9234dd31b058", "0x6939cfb4f0cb4b59ed87cb7a9eeb238ccb0a5800"]


def b64(x):
    return base64.urlsafe_b64encode(x).rstrip(b"=").decode()


def call(url, method, params, auth=True):
    hdr = {"content-type": "application/json"}
    if auth:
        h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        p = b64(json.dumps({"iat": int(time.time())}).encode())
        hdr["Authorization"] = "Bearer " + h + "." + p + "." + b64(hmac.new(key, (h + "." + p).encode(), hashlib.sha256).digest())
    req = urllib.request.Request(url, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(), hdr)
    r = json.load(urllib.request.urlopen(req, timeout=600))
    if "error" in r:
        raise RuntimeError(f"{method}: {r['error']}")
    return r["result"]


def head():
    b = call(rpc, "eth_getBlockByNumber", ["latest", False], auth=False)
    return int(b["number"], 16), b["hash"]


def until(fn, what, tries=60, wait=5):
    for _ in range(tries):
        st = fn()
        if st["status"] == "VALID":
            return st
        if st["status"] == "INVALID":
            sys.exit(f"FAIL {what}: {st}")
        time.sleep(wait)
    sys.exit(f"FAIL {what}: still {st}")


params = [json.load(open(f)) for f in blocks]
want = params[-1][0]["blockHash"]
n, h = head()
if h != want:
    if h != BASE:
        sys.exit(f"FAIL head {n} {h} is neither the jochemnet head nor block 2")
    for p in params:
        bh = p[0]["blockHash"]
        st = call(engine, "engine_newPayloadV4", p)["status"]
        if st == "INVALID":
            sys.exit(f"FAIL newPayload {bh[:10]}: INVALID")
        fc = {"headBlockHash": bh, "safeBlockHash": bh, "finalizedBlockHash": bh}
        until(lambda: call(engine, "engine_forkchoiceUpdatedV3", [fc, None])["payloadStatus"], f"fcu {bh[:10]} (newPayload {st})")
    for _ in range(60):
        n, h = head()
        if h == want:
            break
        time.sleep(5)
    if h != want:
        sys.exit(f"FAIL head {n} {h} != {want}")
code = {k: (len(call(rpc, "eth_getCode", [a, "latest"], auth=False)) - 2) // 2 for k, a in CHECK.items()}
bal = [int(call(rpc, "eth_getBalance", [a, "latest"], auth=False), 16) // 10**18 for a in FUNDED]
print(f"OK head {n} {h[:10]} code {code} balances(ETH) {bal}")
