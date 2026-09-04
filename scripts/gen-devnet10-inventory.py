#!/usr/bin/env python3
"""Generate ansible/inventories/devnet-10/inventory.ini from the deployed devnet-9 fleet.

devnet-10 reuses the devnet-9 droplets. Terraform is not in this path -- terraform/devnet-10
manages only DNS -- so this script owns the devnet-10 topology:

  * droplet facts (ip, ipv6, region, arch, builder_index) come from the deployed
    devnet-9 inventory, which is current because the droplets are untouched;
  * DigitalOcean names and terraform state keys stay at their devnet-9 values, since
    renaming there would recreate the fleet. host-mapping.txt records the mapping;
  * hostnames become prysm-geth-<n>: every node runs prysm, the only client
    implementing the Heze fork that carries goldfish, over geth;
  * 120000 validators = 200 supernodes x 596 + 800 home stakers x 1, so that
    SLOTS_PER_ROUND=8 with TARGET_COMMITTEE_SIZE=2500 gives 6 committees per slot.

Supernodes are numbered first (1..200), then home stakers (201..1000), each block
ordered by devnet-9 EL then CL then index, so the mapping is stable across re-runs.
Validator ranges are assigned to physical hosts independently of naming, so a host
keeps its range no matter how the naming changes.

    python3 scripts/gen-devnet10-inventory.py
"""

import collections
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "ansible/inventories/devnet-9/inventory.ini"
DEST = ROOT / "ansible/inventories/devnet-10/inventory.ini"
MAPPING = ROOT / "ansible/inventories/devnet-10/host-mapping.txt"

NETWORK = "glamsterdam-devnet-10"
# Every node runs geth; the devnet-9 EL spread survives only as ordering below.
TARGET_EL = "geth"
SUPER_VALIDATORS = 596
HOME_VALIDATORS = 1

CL_ORDER = ["lighthouse", "prysm", "teku", "nimbus", "lodestar", "grandine"]
EL_ORDER = ["geth", "nethermind", "reth", "besu", "erigon", "ethrex", "nimbusel"]
# Emission order the terraform inventory template used for execution client groups.
EL_TEMPLATE_ORDER = ["besu", "ethereumjs", "geth", "nethermind",
                     "erigon", "reth", "nimbusel", "ethrex"]

# Supernodes per devnet-9 group. Per-EL totals are 20% of that EL's fleet:
# geth 82/410, nethermind 60/300, reth 28/140, besu 16/80, erigon 8/40,
# ethrex 4/20, nimbusel 2/10  ->  200 supernodes, 800 home stakers.
SUPER = {
    "lighthouse-geth": 35, "prysm-geth": 25, "teku-geth": 11,
    "nimbus-geth": 7, "lodestar-geth": 3, "grandine-geth": 1,
    "lighthouse-nethermind": 26, "prysm-nethermind": 19, "teku-nethermind": 8,
    "nimbus-nethermind": 5, "lodestar-nethermind": 2, "grandine-nethermind": 0,
    "lighthouse-reth": 12, "prysm-reth": 9, "teku-reth": 4,
    "nimbus-reth": 2, "lodestar-reth": 1, "grandine-reth": 0,
    "lighthouse-besu": 7, "prysm-besu": 5, "teku-besu": 2,
    "nimbus-besu": 1, "lodestar-besu": 0, "grandine-besu": 1,
    "lighthouse-erigon": 3, "prysm-erigon": 2, "teku-erigon": 1,
    "nimbus-erigon": 1, "lodestar-erigon": 0, "grandine-erigon": 1,
    "lighthouse-ethrex": 2, "prysm-ethrex": 1, "teku-ethrex": 1,
    "nimbus-ethrex": 0, "lodestar-ethrex": 0,
    "lighthouse-nimbusel": 1, "prysm-nimbusel": 1, "teku-nimbusel": 0,
    "nimbus-nimbusel": 0,
}


def read_source():
    try:
        return SRC.read_text()
    except FileNotFoundError:
        rel = SRC.relative_to(ROOT)
        return subprocess.run(["git", "-C", ROOT, "show", f"HEAD:{rel}"],
                              capture_output=True, text=True, check=True).stdout


def load_fleet():
    """old hostname -> {group, index, ip, ipv6, region, arch, builder_index}"""
    fleet = {}
    for line in read_source().splitlines():
        if "ansible_host=" not in line:
            continue
        parts = line.split()
        kv = dict(x.split("=", 1) for x in parts[1:] if "=" in x)
        host = parts[0]
        group, idx = host.rsplit("-", 1)
        fleet[host] = {
            "group": group, "index": int(idx),
            "ip": kv["ansible_host"], "ipv6": kv.get("ipv6", "none"),
            "region": kv.get("cloud_region", "ams3"), "arch": kv.get("arch", "amd64"),
            "builder_index": kv.get("builder_index"),
        }
    return fleet


def assign(fleet):
    """Attach supernode flag + validator range to every validating host."""
    counts = collections.Counter(h["group"] for h in fleet.values())
    unknown = set(SUPER) - set(counts)
    if unknown:
        sys.exit(f"SUPER names absent from the deployed fleet: {sorted(unknown)}")
    for name, n in SUPER.items():
        if not 0 <= n <= counts[name]:
            sys.exit(f"{name}: {n} supernodes requested but only {counts[name]} hosts")
    if sum(SUPER.values()) != 200:
        sys.exit(f"supernode total is {sum(SUPER.values())}, expected 200")

    cursor = 0
    # Same walk order the terraform node list used, so ranges land identically.
    for cl in CL_ORDER:
        for el in EL_ORDER:
            group = f"{cl}-{el}"
            if group not in counts:
                continue
            members = sorted((h for h in fleet.values() if h["group"] == group),
                             key=lambda h: h["index"])
            n_super = SUPER[group]
            for block, per in ((members[:n_super], SUPER_VALIDATORS),
                               (members[n_super:], HOME_VALIDATORS)):
                for h in block:
                    h["supernode"] = per == SUPER_VALIDATORS
                    h["val_start"], cursor = cursor, cursor + per
                    h["val_end"] = cursor

    for host, h in fleet.items():
        if "supernode" not in h:  # bootnodes and buildoors carry no validators
            h["supernode"] = bool(re.search(r"bootnode|mev", h["group"]))
    return cursor


def rename(fleet):
    buckets = collections.defaultdict(list)
    for host, h in fleet.items():
        m = re.match(r"^(buildoor-)?([a-z]+)-([a-z0-9]+)$", h["group"])
        if not m or m.group(2) not in CL_ORDER:
            continue  # bootnodes keep their name
        prefix, cl, el = m.group(1) or "", m.group(2), m.group(3)
        # Supernodes take the low indices; within each block, order by the devnet-9
        # EL then CL then index, so the mapping is stable across re-runs.
        sort_key = (0 if h.get("val_end") and h["supernode"] else 1,
                    EL_ORDER.index(el), CL_ORDER.index(cl), h["index"])
        buckets[f"{prefix}prysm-{TARGET_EL}"].append((sort_key, host))

    mapping = {}
    for group, rows in buckets.items():
        for n, (_, host) in enumerate(sorted(rows), start=1):
            mapping[host] = (f"{group}-{n}", group)
    return mapping


def emit(fleet, mapping):
    by_group = collections.defaultdict(list)
    for host, h in fleet.items():
        new_name, new_group = mapping.get(host, (host, h["group"]))
        line = (f"{new_name} ansible_host={h['ip']} ipv6={h['ipv6']} cloud=digitalocean "
                f"cloud_region={h['region']} arch={h['arch']} "
                f"ethereum_node_cl_supernode_enabled={h['supernode']}")
        if h.get("val_end"):
            line += f" validator_start={h['val_start']} validator_end={h['val_end']}"
        if h["builder_index"] is not None:
            line += f" builder_index={h['builder_index']}"
        by_group[new_group].append(line)

    out = ["localhost", "", "[all:vars]", f"ethereum_network_name={NETWORK}", ""]
    for group in sorted(by_group):
        out.append(f"[{group.replace('-', '_')}]")
        out += sorted(by_group[group], key=lambda l: l.split()[0])
        out.append("")

    node_groups = sorted(g for g in by_group if not g.startswith("bootnode"))
    out += [
        "# Consensus client groups",
        "#",
        "# Every node runs prysm over geth, so every group is a child of [prysm]. Keeping",
        "# prysm at this depth preserves group_vars precedence against the EL group.",
        "# DigitalOcean and terraform still use the devnet-9 names; see host-mapping.txt.",
        "[prysm:children]",
    ] + [g.replace("-", "_") for g in node_groups] + [""]

    out += ["# Execution client groups", ""]
    els = []
    for el in EL_TEMPLATE_ORDER:
        members = [g for g in node_groups if g.rsplit("-", 1)[-1] == el]
        out.append(f"[{el}:children]")
        out += [g.replace("-", "_") for g in members]
        out.append("")
        if members:
            els.append(el)

    buildoors = [g for g in node_groups if g.startswith("buildoor-")]
    out += ["# Buildoor host aggregator", "", "[buildoor:children]"]
    out += [g.replace("-", "_") for g in buildoors]
    out += [
        "",
        "# ansible_group_priority MUST live in the inventory (not group_vars/) — it is consulted",
        "# while loading group_vars, so a value placed in group_vars/buildoor.yaml is read too late",
        "# and the buildoor overrides lose to alphabetically-later sibling groups (geth, prysm).",
        "[buildoor:vars]",
        "ansible_group_priority=100",
        "",
        "# Global groups",
        "",
        "[consensus_node:children]",
        "prysm",
        "",
        "[execution_node:children]",
    ] + sorted(els) + (["buildoor"] if buildoors else []) + [
        "",
        "[ethereum_node:children]",
        "consensus_node",
        "execution_node",
        "",
        "[dns_server:children]",
        "bootnode",
        "",
        "[mev_boost:children]",
        "consensus_node",
        "",
        "[arm]",
        "",
    ]
    return "\n".join(out)


def main():
    fleet = load_fleet()
    total = assign(fleet)
    mapping = rename(fleet)
    DEST.write_text(emit(fleet, mapping))
    MAPPING.write_text(
        "# devnet-10: DigitalOcean droplet / terraform state name -> ansible inventory name.\n"
        "# The left column is what the DO console and `terraform state list` show.\n"
        "# Regenerated by scripts/gen-devnet10-inventory.py.\n"
        + "".join(f"{old}\t{new}\n" for old, (new, _) in sorted(mapping.items())))

    sup = sum(1 for h in fleet.values() if h.get("val_end") and h["supernode"])
    home = sum(1 for h in fleet.values() if h.get("val_end") and not h["supernode"])
    print(f"wrote {DEST.relative_to(ROOT)}: {len(fleet)} hosts")
    print(f"  {sup} supernodes x {SUPER_VALIDATORS} + {home} home x {HOME_VALIDATORS} "
          f"= {total} validators")
    print(f"  mapping -> {MAPPING.relative_to(ROOT)}")


main()
