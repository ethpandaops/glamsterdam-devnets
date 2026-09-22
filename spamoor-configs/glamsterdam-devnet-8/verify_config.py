#!/usr/bin/env python3
"""
Check that these configs are internally consistent.

The configs carry ~190 KB of hex, and every address in them is derived from that hex:
contracts are deployed through spamoor's well-known CREATE2 factory, and the pre-fund
targets are CREATE addresses off the driver.  So the whole thing can be re-derived from
the bytes and compared against what the configs claim, which catches the failure mode that
matters -- an edited init_code with a stale address somewhere else, which still burns a
full block of gas while analysing nothing.

    python3 verify_config.py

Needs only PyYAML; keccak-256 is implemented below so there is no web3/eth-utils
dependency.  Exits non-zero on any mismatch.
"""
import glob
import os
import sys

import yaml

FACTORY = "e883a4ac7904c5b91faaec2ceccb236d985fc329"

# --------------------------------------------------------------------------- keccak-256
_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [
    [0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56], [27, 20, 39, 8, 14],
]


def _keccak_f(a):
    for rnd in range(24):
        c = [a[x][0] ^ a[x][1] ^ a[x][2] ^ a[x][3] ^ a[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ (((c[(x + 1) % 5] << 1) | (c[(x + 1) % 5] >> 63)) & (2**64 - 1))
             for x in range(5)]
        for x in range(5):
            for y in range(5):
                a[x][y] ^= d[x]
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                r = _ROT[x][y]
                b[y][(2 * x + 3 * y) % 5] = ((a[x][y] << r) | (a[x][y] >> (64 - r))) & (2**64 - 1) if r else a[x][y]
        for x in range(5):
            for y in range(5):
                a[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y] & (2**64 - 1))
        a[0][0] ^= _RC[rnd]
    return a


def keccak256(data: bytes) -> bytes:
    rate = 136
    pad = rate - (len(data) % rate)          # pad10*1, with 0x81 when only one byte is free
    padded = data + (b"\x81" if pad == 1 else b"\x01" + b"\x00" * (pad - 2) + b"\x80")
    a = [[0] * 5 for _ in range(5)]
    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            a[i % 5][i // 5] ^= int.from_bytes(block[i * 8:(i + 1) * 8], "little")
        a = _keccak_f(a)
    out = b""
    for i in range(4):
        out += a[i % 5][i // 5].to_bytes(8, "little")
    return out[:32]


assert keccak256(b"").hex() == \
    "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470", "keccak self-test"
assert keccak256(b"abc").hex() == \
    "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45", "keccak self-test"


# --------------------------------------------------------------------------- addresses
def create2(factory_hex, salt, init_code):
    pre = b"\xff" + bytes.fromhex(factory_hex) + salt.to_bytes(32, "big") + keccak256(init_code)
    return keccak256(pre)[12:].hex()


def create(sender_hex, nonce):
    """RLP([addr, nonce]) for the nonce ranges these configs use."""
    addr = bytes.fromhex(sender_hex)
    if nonce == 0:
        n = b"\x80"
    elif nonce < 0x80:
        n = bytes([nonce])
    elif nonce <= 0xFF:
        n = b"\x81" + bytes([nonce])
    else:
        n = b"\x82" + nonce.to_bytes(2, "big")
    payload = b"\x94" + addr + n
    return keccak256(bytes([0xC0 + len(payload)]) + payload)[12:].hex()


# --------------------------------------------------------------------------- checks
HERE = os.path.dirname(os.path.abspath(__file__))
fails, checks = [], 0


def check(cond, msg):
    global checks
    checks += 1
    if not cond:
        fails.append(msg)
    return cond


spammers = {}
for path in sorted(glob.glob(os.path.join(HERE, "*.yaml"))):
    for s in yaml.safe_load(open(path)):
        spammers[s["name"]] = s

by_kind = {}
for name, s in spammers.items():
    if "prep 1/3" in name:
        by_kind["blob"] = s
    elif "prep 2/3" in name:
        by_kind["driver"] = s
    elif "prep 3/3" in name:
        by_kind["funder"] = s
    elif "attack A" in name:
        by_kind["a"] = s
    elif "attack B" in name:
        by_kind["b"] = s
    elif "corpus" in name:
        by_kind["corpus"] = s
    elif "attack C" in name:
        by_kind["c"] = s
    elif "ring driver" in name:
        by_kind.setdefault("rings", []).append(s)

# 1. the blob address the drivers are told to EXTCODECOPY == CREATE2 of the blob init_code
blob_init = bytes.fromhex(by_kind["blob"]["config"]["init_code"])
blob_addr = create2(FACTORY, by_kind["blob"]["config"]["start_salt"], blob_init)
for k in ("a", "b"):
    cd = by_kind[k]["config"]["call_data"][2:]
    check(cd[24:64] == blob_addr,
          "attack %s call_data points at 0x%s, blob deploys to 0x%s" % (k.upper(), cd[24:64], blob_addr))
check(len(blob_init) == 65552, "blob init_code is %d bytes, expected 65552" % len(blob_init))

# 2. the driver address the attacks call == CREATE2 of the driver init_code
drv_init = bytes.fromhex(by_kind["driver"]["config"]["init_code"])
drv_addr = create2(FACTORY, by_kind["driver"]["config"]["start_salt"], drv_init)
for k in ("a", "b"):
    check(by_kind[k]["config"]["contract_address"][2:].lower() == drv_addr,
          "attack %s calls 0x%s, driver deploys to 0x%s"
          % (k.upper(), by_kind[k]["config"]["contract_address"][2:], drv_addr))

# 3. the pre-fund list == CREATE(driver, 1..N), the addresses attack A actually creates
fund_cd = bytes.fromhex(by_kind["funder"]["config"]["call_data"][2:])
check(len(fund_cd) % 32 == 0, "pre-fund call_data is not a whole number of words")
n_targets = len(fund_cd) // 32
for i in range(n_targets):
    word = fund_cd[i * 32:(i + 1) * 32]
    check(word[:12] == b"\x00" * 12, "pre-fund target %d is not a left-padded address" % i)
    want = create(drv_addr, i + 1)
    if word[12:].hex() != want:
        check(False, "pre-fund target %d is 0x%s, CREATE(driver,%d) is 0x%s"
              % (i, word[12:].hex(), i + 1, want))
        break

# 4. attack A's budget must fit inside the pre-funded range
PER_CREATE = 20286
iters_a = (by_kind["a"]["config"]["gas_limit"] - 21000) // PER_CREATE
check(iters_a <= n_targets,
      "attack A can run %d CREATEs but only %d targets are pre-funded; the excess pays "
      "NEW_ACCOUNT" % (iters_a, n_targets))

# 5. scenario B must carry a state-gas reservoir, or it ends in out-of-gas
TX_MAX_GAS_LIMIT = 2**24
NEW_ACCOUNT = 120 * 1530
check(by_kind["b"]["config"]["gas_limit"] - TX_MAX_GAS_LIMIT >= NEW_ACCOUNT,
      "attack B gas_limit %d leaves a reservoir of %d, below one NEW_ACCOUNT charge (%d); "
      "the charge will spill into execution gas and the tx will OOG"
      % (by_kind["b"]["config"]["gas_limit"],
         by_kind["b"]["config"]["gas_limit"] - TX_MAX_GAS_LIMIT, NEW_ACCOUNT))

# 6. the corpus initcode must EXTCODECOPY the same blob
corpus_init = bytes.fromhex(by_kind["corpus"]["config"]["init_code"])
check(bytes.fromhex(blob_addr) in corpus_init,
      "corpus init_code does not reference the blob at 0x%s" % blob_addr)

# 7. attack C must point at a ring driver, and never at one larger than the corpus
ring_addrs = {create2(FACTORY, r["config"]["start_salt"],
                      bytes.fromhex(r["config"]["init_code"])): r["name"]
              for r in by_kind.get("rings", [])}
c_target = by_kind["c"]["config"]["contract_address"][2:].lower()
check(c_target in ring_addrs, "attack C calls 0x%s, which is not one of the ring drivers" % c_target)
corpus_n = by_kind["corpus"]["config"]["total_count"] + by_kind["corpus"]["config"]["start_salt"]
if c_target in ring_addrs:
    ring_n = int(ring_addrs[c_target].rsplit("n=", 1)[-1].rstrip(")"))
    check(ring_n <= corpus_n,
          "attack C uses ring n=%d but the corpus only builds %d contracts" % (ring_n, corpus_n))

# --------------------------------------------------------------------------- report
print("factory       0x%s" % FACTORY)
print("blob          0x%s  (%d bytes of init_code)" % (blob_addr, len(blob_init)))
print("create driver 0x%s" % drv_addr)
print("pre-funded    %d targets, CREATE(driver, 1..%d)" % (n_targets, n_targets))
print("attack A      %d CREATEs per tx at %d gas each" % (iters_a, PER_CREATE))
print("attack B      reservoir %d >= NEW_ACCOUNT %d"
      % (by_kind["b"]["config"]["gas_limit"] - TX_MAX_GAS_LIMIT, NEW_ACCOUNT))
for addr, name in sorted(ring_addrs.items(), key=lambda kv: kv[1]):
    print("ring driver   0x%s  %s%s" % (addr, name, "   <- attack C" if addr == c_target else ""))
print()
if fails:
    print("FAILED %d of %d checks:" % (len(fails), checks))
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("all %d checks passed" % checks)
