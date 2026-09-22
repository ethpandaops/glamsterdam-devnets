#!/usr/bin/env python3
"""
Disassemble the bytecode these configs carry, so the hex can be read instead of trusted.

    python3 disassemble.py            # the drivers (skips the 64 KiB random blob)
    python3 disassemble.py --blob     # include a summary of the blob's byte histogram

Needs only PyYAML.
"""
import argparse
import collections
import glob
import os

import yaml

OPCODES = {
    0x00: "STOP", 0x01: "ADD", 0x02: "MUL", 0x03: "SUB", 0x04: "DIV", 0x05: "SDIV",
    0x06: "MOD", 0x07: "SMOD", 0x08: "ADDMOD", 0x09: "MULMOD", 0x0A: "EXP",
    0x0B: "SIGNEXTEND", 0x10: "LT", 0x11: "GT", 0x12: "SLT", 0x13: "SGT", 0x14: "EQ",
    0x15: "ISZERO", 0x16: "AND", 0x17: "OR", 0x18: "XOR", 0x19: "NOT", 0x1A: "BYTE",
    0x1B: "SHL", 0x1C: "SHR", 0x1D: "SAR", 0x20: "KECCAK256", 0x30: "ADDRESS",
    0x31: "BALANCE", 0x32: "ORIGIN", 0x33: "CALLER", 0x34: "CALLVALUE",
    0x35: "CALLDATALOAD", 0x36: "CALLDATASIZE", 0x37: "CALLDATACOPY", 0x38: "CODESIZE",
    0x39: "CODECOPY", 0x3A: "GASPRICE", 0x3B: "EXTCODESIZE", 0x3C: "EXTCODECOPY",
    0x3D: "RETURNDATASIZE", 0x3E: "RETURNDATACOPY", 0x3F: "EXTCODEHASH",
    0x40: "BLOCKHASH", 0x41: "COINBASE", 0x42: "TIMESTAMP", 0x43: "NUMBER",
    0x44: "PREVRANDAO", 0x45: "GASLIMIT", 0x46: "CHAINID", 0x47: "SELFBALANCE",
    0x48: "BASEFEE", 0x50: "POP", 0x51: "MLOAD", 0x52: "MSTORE", 0x53: "MSTORE8",
    0x54: "SLOAD", 0x55: "SSTORE", 0x56: "JUMP", 0x57: "JUMPI", 0x58: "PC",
    0x59: "MSIZE", 0x5A: "GAS", 0x5B: "JUMPDEST", 0x5C: "TLOAD", 0x5D: "TSTORE",
    0x5E: "MCOPY", 0x5F: "PUSH0", 0xF0: "CREATE", 0xF1: "CALL", 0xF2: "CALLCODE",
    0xF3: "RETURN", 0xF4: "DELEGATECALL", 0xF5: "CREATE2", 0xFA: "STATICCALL",
    0xFD: "REVERT", 0xFE: "INVALID", 0xFF: "SELFDESTRUCT",
}


def mnemonic(op):
    if 0x60 <= op <= 0x7F:
        return "PUSH%d" % (op - 0x5F)
    if 0x80 <= op <= 0x8F:
        return "DUP%d" % (op - 0x7F)
    if 0x90 <= op <= 0x9F:
        return "SWAP%d" % (op - 0x8F)
    if 0xA0 <= op <= 0xA4:
        return "LOG%d" % (op - 0xA0)
    return OPCODES.get(op, "UNKNOWN_%02x" % op)


def disassemble(code, max_push_hex=40):
    pc, out = 0, []
    while pc < len(code):
        op = code[pc]
        if 0x60 <= op <= 0x7F:
            n = op - 0x5F
            data = code[pc + 1:pc + 1 + n].hex()
            if len(data) > max_push_hex:
                data = data[:max_push_hex] + "..."
            out.append((pc, "%-8s 0x%s" % (mnemonic(op), data)))
            pc += 1 + n
        else:
            out.append((pc, mnemonic(op)))
            pc += 1
    return out


def split_deploy_prefix(init_code):
    """
    These contracts all deploy with the same shape: PUSHn len, PUSH1 off, PUSH1 0,
    CODECOPY, PUSHn len, PUSH1 0, RETURN, then the runtime.  Recover the runtime by
    reading the offset the constructor CODECOPYs from.
    """
    for pc, text in disassemble(init_code):
        if text.startswith("CODECOPY"):
            break
    else:
        return None, init_code
    ops = disassemble(init_code)
    pushes = [t for _, t in ops[:3] if t.startswith("PUSH")]
    if len(pushes) < 2:
        return None, init_code
    off = int(pushes[1].split("0x")[1], 16)
    if 0 < off < len(init_code):
        return init_code[:off], init_code[off:]
    return None, init_code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blob", action="store_true", help="also summarise the 64 KiB blob")
    a = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    seen = set()
    for path in sorted(glob.glob(os.path.join(here, "*.yaml"))):
        for s in yaml.safe_load(open(path)):
            for key in ("init_code", "contract_code"):
                hexstr = s["config"].get(key)
                if not hexstr or hexstr in seen:
                    continue
                seen.add(hexstr)
                code = bytes.fromhex(hexstr[2:] if hexstr.startswith("0x") else hexstr)
                is_blob = len(code) > 4096
                if is_blob and not a.blob:
                    print("== %s\n   %s: %d bytes -- the random-alphabet blob, skipped "
                          "(use --blob)\n" % (s["name"], key, len(code)))
                    continue
                print("== %s\n   %s: %d bytes" % (s["name"], key, len(code)))
                prefix, runtime = split_deploy_prefix(code)
                if prefix is not None:
                    print("   constructor: %d bytes, returns the %d-byte runtime below"
                          % (len(prefix), len(runtime)))
                if is_blob:
                    hist = collections.Counter(runtime)
                    print("   runtime head : %s  (PUSH2 0xFFFF ; JUMP -> forces analysis "
                          "of the whole 64 KiB)" % runtime[:4].hex())
                    print("   runtime tail : %s (32 x JUMPDEST -> the jump target can "
                          "never be push-data)" % runtime[-8:].hex())
                    print("   bytes 32..63 : %s (overwritten with the contract's own "
                          "ADDRESS at deploy, so every copy has a unique code hash)"
                          % runtime[32:40].hex())
                    print("   histogram    : %s"
                          % ", ".join("0x%02x x%d" % (b, n)
                                      for b, n in sorted(hist.items())))
                else:
                    for pc, text in disassemble(runtime):
                        print("   %4d  %s" % (pc, text))
                print()


if __name__ == "__main__":
    main()
