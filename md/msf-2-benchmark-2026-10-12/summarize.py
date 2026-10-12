"""Summarize saved observations; no live queries or client mutations."""

import collections
import datetime as dt
import gzip
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
raw = EVIDENCE / "observations.jsonl"
if raw.exists():
    lines = raw.read_text().splitlines()
else:
    with gzip.open(str(raw) + ".gz", "rt") as stream:
        lines = stream.read().splitlines()
samples = sorted((json.loads(line) for line in lines), key=lambda s: s["at"])
inventory = (ROOT.parents[1] / "ansible/inventories/msf-2/inventory.ini").read_text()
ranges = [(match[0], int(match[1]), int(match[2]))
          for match in re.findall(r"^(\S+).*validator_start=(\d+) validator_end=(\d+)",
                                  inventory, re.MULTILINE)]
staked = {host for host, _, _ in ranges}
errors, scrapes, health = collections.Counter(), collections.Counter(), collections.Counter()
metric_errors, head_gaps, lag, disagreements, lifecycle = [], [], [], [], []
last = {}
for sample in samples:
    nodes = sample["nodes"]
    valid_nodes = {h: n for h, n in nodes.items() if "error" not in n}
    latest = max(n["slot"] for n in valid_nodes.values())
    by_slot = collections.defaultdict(lambda: collections.defaultdict(list))
    gaps = {}
    for host, node in nodes.items():
        if "error" in node:
            errors[host] += 1
            continue
        sync = node["sync"]
        if any(sync.get(k) for k in ("is_syncing", "is_optimistic", "el_offline")):
            health[host] += 1
        if host in staked:
            gaps[host] = latest - node["slot"]
            lag.append(node["slot"] // 32 - node["finalized"])
        if not any(sync.get(k) for k in ("is_syncing", "is_optimistic", "el_offline")):
            by_slot[node["slot"]][node["root"]].append(host)
        for container in node["containers"]:
            key = (host, container["name"])
            identity = (container["id"], container["restarts"], container["started"])
            if key in last and identity != last[key]:
                lifecycle.append({"at": sample["at"], "host": host,
                                  "container": container["name"],
                                  "before": last[key], "after": identity})
            last[key] = identity
    head_gaps.append({"at": sample["at"], "maximum": max(gaps.values()),
                      "nodes_over_three_slots": {h: n for h, n in gaps.items() if n > 3}})
    for slot, roots in by_slot.items():
        if len(roots) > 1:
            disagreements.append({"at": sample["at"], "slot": slot, "roots": roots})
    for key, metric in sample["metrics"].items():
        if "error" in metric or metric.get("status") != "success":
            metric_errors.append({"at": sample["at"], "query": key, "result": metric})
    for point in sample["metrics"].get("scrapes", {}).get("data", {}).get("result", []):
        if point["value"][1] != "1":
            scrapes[(point["metric"].get("instance"), point["metric"].get("job"))] += 1

epochs = {}
initial = json.loads((EVIDENCE / "slots-epochs88-90.json").read_text())
for epoch in (88, 89, 90):
    epochs[epoch] = {"headers": [h for h in initial["headers"] if h["slot"] // 32 == epoch],
                     "proposer_duties": initial["proposer_duties"][str(epoch)]}
for path in sorted(EVIDENCE.glob("proposal-epoch-*.json")):
    record = json.loads(path.read_text())
    epochs[record["epoch"]] = record
misses = []
totals, assigned = collections.Counter(), collections.Counter()
for epoch, record in sorted(epochs.items()):
    duties = {int(d["slot"]): int(d["validator_index"])
              for d in record["proposer_duties"]["data"]}
    for slot, validator in duties.items():
        host = next((h for h, first, end in ranges if first <= validator < end), "unmapped")
        assigned[host] += 1
    for header in record["headers"]:
        if header.get("exists") is False:
            slot = header["slot"]
            validator = duties[slot]
            host = next((h for h, first, end in ranges if first <= validator < end), "unmapped")
            misses.append({"epoch": epoch, "slot": slot, "proposer": validator, "host": host})
            totals[host] += 1

first, final = samples[0], samples[-1]
last_staked = {h: n for h, n in final["nodes"].items() if h in staked and "error" not in n}
summary = {
    "window": json.loads((EVIDENCE / "window.json").read_text()),
    "first_cycle_start": first["at"],
    "last_cycle_start": final["at"],
    "capture_records": len(samples),
    "node_checks": sum(len(s["nodes"]) for s in samples),
    "max_interval_seconds": max((dt.datetime.fromisoformat(b["at"]) -
                                  dt.datetime.fromisoformat(a["at"])).total_seconds()
                                 for a, b in zip(samples, samples[1:])),
    "api_error_counts": dict(errors),
    "metric_errors": metric_errors,
    "sync_or_optimism_or_offline_sample_counts": dict(health),
    "failed_scrape_sample_counts": [{"instance": h, "job": j, "count": n}
                                   for (h, j), n in scrapes.items()],
    "container_lifecycle_changes": lifecycle,
    "same_slot_validated_root_disagreements": disagreements,
    "validator_head_gap_max_slots": max(x["maximum"] for x in head_gaps),
    "validator_head_gap_over_three_slots": [x for x in head_gaps if x["nodes_over_three_slots"]],
    "validator_finality_lag_epochs_min_max": [min(lag), max(lag)],
    "first_reference_finalized_epoch": first["nodes"]["nimbus-nethermind-1"]["finalized"],
    "last_reference_finalized_epoch": final["nodes"]["nimbus-nethermind-1"]["finalized"],
    "last_validator_host_count": len(last_staked),
    "last_validator_sync_status_clear": all(not any(n["sync"].get(k) for k in
                                                    ("is_syncing", "is_optimistic", "el_offline"))
                                             for n in last_staked.values()),
    "duty_census_completed_epochs": sorted(epochs),
    "duty_census_missed_by_host": dict(totals),
    "duty_census_assigned_by_host": dict(assigned),
    "duty_census_missed_slots": misses,
    "limits": "Capture includes a brief collector reload overlap; node reads are not simultaneous. "
              "The duty census covers completed epochs only, excluding partial epochs at window boundaries. "
              "Log filters are selective; absence between samples is not established.",
}
(EVIDENCE / "monitoring-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps({k: v for k, v in summary.items() if k in (
    "capture_records", "node_checks", "validator_head_gap_max_slots",
    "validator_finality_lag_epochs_min_max", "last_reference_finalized_epoch",
    "last_validator_sync_status_clear", "duty_census_missed_by_host")}, indent=2))
