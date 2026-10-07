#!/usr/bin/env python3
"""Build the msf-1 prestate on an offline EL: block 1 = funding withdrawals, block 2 = EIP-8282 deploys.

Usage: build_blocks.py <engine url> <rpc url> <jwt hex file> <withdrawals.json> <tx1.raw> <tx2.raw> <out dir>
Writes block1.json / block2.json (engine_newPayloadV4 params) to <out dir>.
"""
import base64, hashlib, hmac, json, sys, time, urllib.request

engine, rpc, jwt_file, wd_file, tx1, tx2, out = sys.argv[1:8]
key = bytes.fromhex(open(jwt_file).read().strip().removeprefix("0x"))
ZERO = "0x" + "00" * 32


def b64(x):
    return base64.urlsafe_b64encode(x).rstrip(b"=").decode()


def call(url, method, params, auth=True):
    hdr = {"content-type": "application/json"}
    if auth:
        h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
        p = b64(json.dumps({"iat": int(time.time())}).encode())
        hdr["Authorization"] = "Bearer " + h + "." + p + "." + b64(hmac.new(key, (h + "." + p).encode(), hashlib.sha256).digest())
    req = urllib.request.Request(url, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(), hdr)
    r = json.load(urllib.request.urlopen(req, timeout=300))
    if "error" in r:
        sys.exit(f"{method}: {r['error']}")
    return r["result"]


def fcu(head, attrs=None):
    st = {"headBlockHash": head, "safeBlockHash": head, "finalizedBlockHash": head}
    r = call(engine, "engine_forkchoiceUpdatedV3", [st, attrs])
    if r["payloadStatus"]["status"] != "VALID":
        sys.exit(f"fcu {head}: {r['payloadStatus']}")
    return r.get("payloadId")


def build(parent, ts, withdrawals, want_txs, name):
    attrs = {"timestamp": hex(ts), "prevRandao": "0x" + hashlib.sha256(name.encode()).hexdigest(),
             "suggestedFeeRecipient": "0x" + "00" * 20, "withdrawals": withdrawals, "parentBeaconBlockRoot": ZERO}
    pid = fcu(parent, attrs)
    time.sleep(4)
    env = call(engine, "engine_getPayloadV5", [pid])
    pl = env["executionPayload"]
    got = list(pl["transactions"])
    if sorted(got) != sorted(want_txs):
        sys.exit(f"{name}: payload has {len(got)} txs, want {len(want_txs)}")
    if len(pl["withdrawals"]) != len(withdrawals):
        sys.exit(f"{name}: payload has {len(pl['withdrawals'])} withdrawals, want {len(withdrawals)}")
    params = [pl, [], ZERO, env.get("executionRequests", [])]
    st = call(engine, "engine_newPayloadV4", params)
    if st["status"] != "VALID":
        sys.exit(f"{name} newPayload: {st}")
    fcu(pl["blockHash"])
    json.dump(params, open(f"{out}/{name}.json", "w"))
    print(f"{name}: number {int(pl['blockNumber'], 16)} hash {pl['blockHash']} stateRoot {pl['stateRoot']} "
          f"gasLimit {int(pl['gasLimit'], 16)} gasUsed {int(pl['gasUsed'], 16)} txs {len(pl['transactions'])} "
          f"withdrawals {len(pl['withdrawals'])} requests {len(params[3])}")
    return pl


head = call(rpc, "eth_getBlockByNumber", ["latest", False], auth=False)
print("head", int(head["number"], 16), head["hash"])
b1 = build(head["hash"], int(head["timestamp"], 16) + 1, json.load(open(wd_file)), [], "block1")
raws = [open(f).read().strip() for f in (tx1, tx2)]
for raw in raws:
    print("sent", call(rpc, "eth_sendRawTransaction", [raw], auth=False))
b2 = build(b1["blockHash"], int(b1["timestamp"], 16) + 1, [], raws, "block2")
for h in ("0x0000bFF46984e3725691FA540a8C7589300D8282", "0x000064D678505ad48F8cCb093BC65613800E8282"):
    code = call(rpc, "eth_getCode", [h, "latest"], auth=False)
    print(h, "code bytes", (len(code) - 2) // 2)
blk = call(rpc, "eth_getBlockByNumber", [b2["blockNumber"], False], auth=False)
for th in blk["transactions"]:
    r = call(rpc, "eth_getTransactionReceipt", [th], auth=False)
    print("receipt", th, "status", r["status"], "gasUsed", int(r["gasUsed"], 16))
