#!/usr/bin/env python3
"""Make egg's mainnet-shadowfork genesis.json loadable by every EL (same genesis hash).

egg copies eth-clients/mainnet's genesis: its alloc keys have no 0x prefix (nethermind
2.1.0: "hex string without 0x prefix"), baseFeePerGas is null, and the config lacks the
EIP-7002/7251 request contract addresses (besu 26.9.0: "Withdrawal Request Contract
Address not found"). Verified on geth/reth/erigon/nethermind/besu/ethrex/nimbus-el,
2026-10-07. Prints "changed" when it rewrote the file.

With an amsterdamTime argument it also sets config.amsterdamTime: a datadir restored past
Amsterdam (msf-2) needs the fork where its blocks put it, not at genesis, or every client
rewinds them as pre-Amsterdam blocks.

Usage: normalize-shadowfork-genesis.py <genesis.json> [amsterdamTime]
"""
import json
import sys

path = sys.argv[1]
with open(path) as f:
    genesis = json.load(f)
before = json.dumps(genesis, sort_keys=True)

genesis["alloc"] = {(k if k.startswith("0x") else "0x" + k): v for k, v in genesis["alloc"].items()}
if "baseFeePerGas" in genesis and genesis["baseFeePerGas"] is None:
    del genesis["baseFeePerGas"]
config = genesis["config"]
config.setdefault("withdrawalRequestContractAddress", "0x00000961ef480eb55e80d19ad83579a64c007002")
config.setdefault("consolidationRequestContractAddress", "0x0000bbddc7ce488642fb579f8b00f3a590007251")
if len(sys.argv) > 2:
    config["amsterdamTime"] = int(sys.argv[2])

if json.dumps(genesis, sort_keys=True) != before:
    with open(path, "w") as f:
        json.dump(genesis, f, indent=2)
        f.write("\n")
    print("changed")
