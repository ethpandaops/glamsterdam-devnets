#!/usr/bin/env python3
"""Generate the devnet-7 preloaded-contracts genesis alloc (state-size spray).

Emits a JSON map suitable for the ethereum-genesis-generator's
ADDITIONAL_PRELOADED_CONTRACTS hook: one contract account per CREATE2 salt
0..count-1, as-if deployed through the deterministic-deployment proxy at
0x4e59b44847b379578588920cA78FbF26c0B4956C with the initcode in initcode.txt.

The initcode returns 65,536 bytes of runtime: all JUMPDEST (0x5b), except
bytes [0:4] = 61ffff56 (PUSH2 0xffff; JUMP -> the JUMPDEST at the last byte)
and bytes [44:64] = the address the contract is deployed at (ADDRESS is ORed
in at construction time). Every account therefore has unique code and a
unique code hash. Accounts get nonce 1 (what a real CREATE2 deployment
leaves behind per EIP-161) and balance 0.

Rationale: devnet-7 runs a 300M gas limit and the protocol floor for loading
an account is 2000 gas, so at most 300M/2000 = 150k accounts can be touched
per block; the spray provides exactly that many maximally-heavy targets.

Requires a keccak256 provider: pycryptodome (Crypto.Hash.keccak), pysha3, or
eth-hash. Output is ~19.7 GB for the default 150,000 accounts.

Usage:
  generate-preloaded-contracts.py --initcode initcode.txt \
      --out preloaded-contracts.json [--count 150000] [--runtime runtime.txt]

--runtime is an optional self-check: the salt-0 runtime bytecode must match
the given file byte-for-byte.
"""

import argparse
import sys

try:
    from Crypto.Hash import keccak as _keccak

    def keccak256(data: bytes) -> bytes:
        h = _keccak.new(digest_bits=256)
        h.update(data)
        return h.digest()
except ImportError:
    try:
        import sha3

        def keccak256(data: bytes) -> bytes:
            return sha3.keccak_256(data).digest()
    except ImportError:
        try:
            from eth_hash.auto import keccak as _ethkeccak

            def keccak256(data: bytes) -> bytes:
                return _ethkeccak(data)
        except ImportError:
            sys.exit("need a keccak256 provider: pip install pycryptodome")

FACTORY = bytes.fromhex("4e59b44847b379578588920ca78fbf26c0b4956c")
RUNTIME_SIZE = 0x10000
# runtime[0:4]: PUSH2 0xffff; JUMP -> lands on the JUMPDEST at the last byte
RUNTIME_PREFIX = bytes.fromhex("61ffff56")
ADDR_OFFSET = 44  # runtime[44:64] = deployed address


def runtime_hex_parts() -> tuple[bytes, bytes]:
    """Hex of the runtime split around the embedded address slot."""
    base = bytearray(b"\x5b" * RUNTIME_SIZE)
    base[: len(RUNTIME_PREFIX)] = RUNTIME_PREFIX
    hexcode = bytes(base).hex().encode()
    return hexcode[: ADDR_OFFSET * 2], hexcode[(ADDR_OFFSET + 20) * 2 :]


def create2_address(salt: int, initcode_hash: bytes) -> bytes:
    preimage = b"\xff" + FACTORY + salt.to_bytes(32, "big") + initcode_hash
    return keccak256(preimage)[12:]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--initcode", required=True, help="file with 0x-prefixed initcode hex")
    p.add_argument("--out", required=True, help="output JSON path")
    p.add_argument("--count", type=int, default=150_000, help="number of salts, starting at 0")
    p.add_argument("--runtime", help="optional salt-0 runtime hex file to self-check against")
    args = p.parse_args()

    with open(args.initcode) as f:
        initcode = bytes.fromhex(f.read().strip().removeprefix("0x"))
    initcode_hash = keccak256(initcode)
    print(f"initcode: {len(initcode)} bytes, hash 0x{initcode_hash.hex()}")

    code_head, code_tail = runtime_hex_parts()

    if args.runtime:
        with open(args.runtime) as f:
            expected = f.read().strip().removeprefix("0x").lower().encode()
        addr0 = create2_address(0, initcode_hash).hex().encode()
        built = code_head + addr0 + code_tail
        if built != expected:
            sys.exit("self-check FAILED: salt-0 runtime does not match --runtime file")
        print(f"self-check ok: salt-0 runtime matches {args.runtime} (addr 0x{addr0.decode()})")

    seen: set[bytes] = set()
    entry_pre = b'"0x'
    entry_mid = b'":{"balance":"0","nonce":1,"code":"0x'
    entry_post = b'"}'
    with open(args.out, "wb", buffering=1 << 22) as out:
        out.write(b"{")
        for salt in range(args.count):
            addr = create2_address(salt, initcode_hash)
            seen.add(addr)
            addr_hex = addr.hex().encode()
            if salt:
                out.write(b",")
            out.write(entry_pre)
            out.write(addr_hex)
            out.write(entry_mid)
            out.write(code_head)
            out.write(addr_hex)
            out.write(code_tail)
            out.write(entry_post)
            if salt % 10_000 == 0:
                print(f"  {salt}/{args.count} (salt {salt} -> 0x{addr.hex()})")
        out.write(b"}\n")

    if len(seen) != args.count:
        sys.exit(f"FATAL: only {len(seen)} unique addresses for {args.count} salts")
    print(f"wrote {args.count} accounts ({len(seen)} unique addresses) to {args.out}")


if __name__ == "__main__":
    main()
