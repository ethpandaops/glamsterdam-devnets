#!/usr/bin/env python3
"""Read-only Jochemnet release consistency and lower-bound disk planning.

Fetches small metadata documents only; never downloads/restores a database.
Disk estimates are planning inputs, not an admission check for deployment.
"""
import argparse
import concurrent.futures
import datetime
import json
import math
from pathlib import Path
import re
import subprocess

CLIENTS = ("geth", "nethermind", "besu", "erigon")
HEAD = 24452538
HEAD_HASH = "0x0fd7242bab5055dda36f374f352c78cae381daae9b3e8febe895dce35c907591"
ROOT = "0xecf809f327549d4a93eeae29252e8f33b0e9f188cba92f0bb43207d4c7a9c9ca"
BASE_URL = "https://shadowfork-images.ethpandaops.io/jochemnet"


def fetch(url):
    # curl works with this host's HTTP policy; Python urllib receives HTTP 403.
    proc = subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--location",
         "--proto", "=https", "--proto-redir", "=https", "--max-time", "30",
         "--max-filesize", "20000000", url],
        capture_output=True, text=True, check=True,
    )
    return json.loads(proc.stdout)


def validate(client, metadata, envelope):
    block = envelope["result"]
    shadow = metadata["shadowfork"]
    expected = {"number": HEAD, "hash": HEAD_HASH, "stateRoot": ROOT,
                "gasLimit": 200000000}
    for key, value in expected.items():
        actual = int(block[key], 16) if isinstance(value, int) else block[key]
        if actual != value:
            raise ValueError(f"{client}: {key}: {actual!r} != {value!r}")
    if (shadow["head"] != HEAD or shadow["head_hash"] != HEAD_HASH
            or shadow["amsterdam_time"] != 1769856769
            or shadow["gas_limit"] != 200000000
            or shadow["network"] != "jochemnet"):
        raise ValueError(f"{client}: unexpected release metadata")
    if int(block["timestamp"], 16) < shadow["amsterdam_time"]:
        raise ValueError(f"{client}: release is not yet on Amsterdam")
    if type(metadata["data_size_bytes"]) is not int or metadata["data_size_bytes"] <= 0:
        raise ValueError(f"{client}: invalid restored size")
    if not re.fullmatch(r"0x[0-9a-f]{64}", block["stateRoot"]):
        raise ValueError(f"{client}: invalid state root")


def inspect(client):
    base = f"{BASE_URL}/{client}/{HEAD}"
    metadata = fetch(f"{base}/_snapshot_metadata.json")
    block = fetch(f"{base}/_snapshot_eth_getBlockByNumber.json")
    validate(client, metadata, block)
    return client, {"url": base, "metadata": metadata,
                    "header": {key: block["result"][key] for key in
                               ("number", "hash", "stateRoot", "timestamp", "gasLimit")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capacity-tib", type=float, default=2.6,
                        help="Historical node-3 offer, NOT measured current free space")
    parser.add_argument("--reserve-fraction", type=float, default=0.20)
    parser.add_argument("--pbt-gb", type=float, default=450)
    parser.add_argument("--artifacts-gb", type=float, default=155.2)
    parser.add_argument("--nethermind-reclaimed-gb", type=float, default=0,
                        help="Measured space reclaimed by dropping the obsolete Patricia DB; default assumes no saving")
    args = parser.parse_args()
    if not (all(math.isfinite(v) for v in (args.capacity_tib, args.reserve_fraction,
                                         args.pbt_gb, args.artifacts_gb, args.nethermind_reclaimed_gb))
            and args.capacity_tib > 0 and 0 <= args.reserve_fraction < 1
            and args.pbt_gb > 0 and args.artifacts_gb > 0
            and args.nethermind_reclaimed_gb >= 0):
        parser.error("capacity and sizes must be positive; reclaimed space nonnegative; reserve in [0, 1)")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        clients = dict(pool.map(inspect, CLIENTS))
    if len({c["header"]["timestamp"] for c in clients.values()}) != 1:
        raise ValueError("release timestamps disagree")
    capacity = int(args.capacity_tib * 2**40)
    budget = int(capacity * (1 - args.reserve_fraction))
    artifacts = int(args.artifacts_gb * 10**9)
    pbt = int(args.pbt_gb * 10**9)
    reclaimed = int(args.nethermind_reclaimed_gb * 10**9)
    if reclaimed >= clients["nethermind"]["metadata"]["data_size_bytes"]:
        parser.error("reclaimed space must be smaller than the restored Nethermind database")
    for client, data in clients.items():
        data["restored_before_cleanup_bytes"] = data["metadata"]["data_size_bytes"]
        data["retained_after_cleanup_bytes"] = data["restored_before_cleanup_bytes"] - (reclaimed if client == "nethermind" else 0)
    cases = {}
    for members in [(c,) for c in CLIENTS] + [("erigon", "geth"),
                                             ("erigon", "nethermind"), CLIENTS]:
        # One artifact pair shared on disk; native PBT cost assumed per client.
        lower = sum(clients[c]["retained_after_cleanup_bytes"] + pbt for c in members) + artifacts
        cases["+".join(members)] = {
            "lower_bound_bytes": lower,
            "headroom_after_reserve_bytes": budget - lower,
            "within_assumed_budget": lower <= budget,
        }
    report = {
        "collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "release_metadata_checks": "PASS",
        "database_open_or_migration_tested": False,
        "assumptions": {"capacity_bytes": capacity, "reserve_fraction": args.reserve_fraction,
                        "pbt_bytes_per_client": pbt, "shared_artifact_bytes": artifacts,
                        "nethermind_reclaimed_bytes": reclaimed,
                        "reclamation_source": "operator input; zero means no saving assumed, not a measurement",
                        "restore_note": "Full restored size is needed before cleanup; migration estimates use retained size. No deletion is performed.",
                        "capacity_source": "historical offer; current VM capacity unverified",
                        "excluded": ["conversion scratch", "archive staging", "BAL retention",
                                     "chain growth", "backup/clone divergence", "OS and other workloads"],
                        "size_source": "plan estimates; Jochemnet PBT size unmeasured"},
        "clients": clients, "disk_cases": cases,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"PASS: four published headers agree at {HEAD}; database compatibility untested")
    for label, case in cases.items():
        print(f"{label}: lower bound {case['lower_bound_bytes'] / 10**9:.1f} GB; "
              f"headroom after reserve {case['headroom_after_reserve_bytes'] / 10**9:.1f} GB")


if __name__ == "__main__":
    main()
