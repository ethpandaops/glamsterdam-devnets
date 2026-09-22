#!/usr/bin/env python3
"""
Check the live chain before and between steps.  No credentials needed.

Every address in these configs is a CREATE2 address off spamoor's "well-known" factory,
and that factory's deployer wallet is derived as sha256(root private key || name)
(`spamoor/walletpool.go:575-599`) -- so it is stable for a given spamoor instance, NOT
across networks or across a root-key rotation.  If the factory is not the expected one,
the blob lands somewhere else, the driver EXTCODECOPYs an empty account, the initcode
becomes 128 KiB of zeros, the jump to byte 131,041 hits a non-JUMPDEST, and every child
frame halts exceptionally -- burning whole blocks while analysing nothing.

This script is the gate against that, and doubles as the progress check between steps.

    python3 preflight.py                 # against devnet-8's public RPC
    python3 preflight.py --rpc <url>

Exit codes: 0 ready for the next step, 1 something is wrong.
"""
import argparse
import json
import os
import sys
import urllib.request

from verify_config import FACTORY, create, create2  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RPC = "https://rpc.glamsterdam-devnet-8.ethpandaops.io"


def rpc(method, params, url):
    req = urllib.request.Request(
        url,
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"content-type": "application/json", "user-agent": "curl/8.5.0"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        body = json.load(r)
    if "error" in body:
        raise RuntimeError("%s: %s" % (method, body["error"]))
    return body["result"]


def has_code(addr, url):
    return rpc("eth_getCode", [addr, "latest"], url) not in ("0x", "0x0", None)


def balance(addr, url):
    return int(rpc("eth_getBalance", [addr, "latest"], url), 16)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rpc", default=RPC)
    a = ap.parse_args()

    meta = json.load(open(os.path.join(HERE, "addresses.json")))
    problems, notes = [], []

    blk = rpc("eth_getBlockByNumber", ["latest", False], a.rpc)
    num = int(blk["number"], 16)
    limit = int(blk["gasLimit"], 16)
    fee = int(blk["baseFeePerGas"], 16)
    print("chain            block %d, gas limit %d, base fee %d wei (%.4f gwei)"
          % (num, limit, fee, fee / 1e9))
    if limit < 150_000_000:
        problems.append("block gas limit is %d; these configs assume ~200M" % limit)
    if fee > 5e9:
        problems.append("base fee is %.2f gwei, close to the configs' 20 gwei cap -- "
                        "transactions will stall" % (fee / 1e9))
    elif fee > 1e9:
        notes.append("base fee %.2f gwei is already elevated; the 20 gwei cap is ~%d "
                     "full blocks away" % (fee / 1e9, 0))

    # 1. THE load-bearing check
    factory = "0x" + FACTORY
    if has_code(factory, a.rpc):
        print("factory          %s  HAS CODE  (addresses in these configs are valid)" % factory)
    else:
        problems.append(
            "factory %s has NO code. The spamoor root key for this instance does not "
            "derive the factory these configs were built against, so every address here "
            "is wrong and the attack would burn blocks doing nothing. Regenerate the "
            "configs against the correct factory before running anything." % factory)

    # 2. prep progress
    blob, drv = meta["blob"], meta["create_driver"]
    blob_ok, drv_ok = has_code(blob, a.rpc), has_code(drv, a.rpc)
    print("blob   (prep 1/3) %s  %s" % (blob, "deployed" if blob_ok else "NOT deployed"))
    print("driver (prep 2/3) %s  %s" % (drv, "deployed" if drv_ok else "NOT deployed"))

    funded = sum(1 for t in meta["prefund_targets"][:8] if balance(t, a.rpc) > 0)
    total_probe = 8
    print("prefund(prep 3/3) %d of the first %d targets funded" % (funded, total_probe))

    for n, addr in sorted(meta["ring_drivers"].items(), key=lambda kv: int(kv[0])):
        print("ring driver n=%-6s %s  %s"
              % (n, addr, "deployed" if has_code(addr, a.rpc) else "not deployed"))

    # 3. next step
    print()
    if problems:
        print("NOT READY:")
        for p in problems:
            print("  - %s" % p)
        return 1
    for note in notes:
        print("note: %s" % note)

    if not blob_ok:
        nxt = "start 'prep 1/3' (the 64 KiB source blob), then re-run this script -- it " \
              "must report the blob deployed at %s" % blob
    elif not drv_ok:
        nxt = "start 'prep 2/3' (the CREATE driver), then re-run this script"
    elif funded < total_probe:
        nxt = "start 'prep 3/3' (pre-fund), then re-run this script -- needed by attack A " \
              "only; attack B can start now"
    else:
        nxt = "preparation is complete: attacks A and B can start. For C, start the " \
              "corpus and gate the attack on 'monitor_corpus.py --verify 16384'"
    print("READY. Next: %s" % nxt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
