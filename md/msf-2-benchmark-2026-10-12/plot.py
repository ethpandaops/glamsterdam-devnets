"""Rebuild figures from saved Prometheus responses and monitoring samples.

Requires matplotlib. No live network requests are made.
"""

import datetime as dt
import gzip
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
UTC = dt.timezone.utc


def series(name):
    path = EVIDENCE / name
    if path.exists():
        data = path.read_text()
    else:
        with gzip.open(str(path) + ".gz", "rt") as stream:
            data = stream.read()
    return json.loads(data)["result"]["data"]["result"]


def points(s, scale=1):
    pairs = [(dt.datetime.fromtimestamp(float(t), UTC), float(v) / scale)
             for t, v in s["values"] if v not in ("NaN", "+Inf", "-Inf")]
    return tuple(zip(*pairs)) if pairs else ([], [])


window = json.loads((EVIDENCE / "window.json").read_text())
start = dt.datetime.fromisoformat(window["start"])
end = dt.datetime.fromisoformat(window["end"])
heap = {s["metric"]["consensus_client"]: s for s in series("besu-heap-history.json")}
gc = {s["metric"]["consensus_client"]: s for s in series("besu-gc-history.json")
      if s["metric"].get("gc") == "G1 Old Generation"}
failures = {
    "prysm": "20:41:21.476",
    "teku": "20:50:04.067",
    "nimbus": "20:55:01.162",
    "lodestar": "22:12:22.081",
}
fig, axes = plt.subplots(3, 2, figsize=(13, 9), sharex=True, sharey=True)
for ax, client in zip(axes.flat, sorted(heap)):
    ax.plot(*points(heap[client], 2**30), color="#175b9e", linewidth=1.0)
    ax.axhline(16, color="#175b9e", linestyle=":", linewidth=1)
    ax.set_ylim(0, 17)
    ax.set_title(f"{client}–besu-1", fontsize=11, loc="left")
    ax.grid(alpha=0.16)
    if client in failures:
        at = dt.datetime.fromisoformat("2026-10-12T" + failures[client]).replace(tzinfo=UTC)
        ax.axvline(at, color="#7f2637", linestyle="--", linewidth=1)
        ax.text(at, 16.4, " OOM", fontsize=8, color="#7f2637", ha="left")
    ax.axvspan(start, end, color="#666666", alpha=0.08)
    right = ax.twinx()
    if client in gc:
        right.plot(*points(gc[client]), color="#c95b25", linewidth=0.9, alpha=0.85)
    right.set_ylim(0, 1.05)
    right.tick_params(axis="y", labelsize=8, colors="#c95b25")
    if ax in axes[:, 1]:
        right.set_ylabel("Old-generation GC timer (s/s)", fontsize=9, color="#c95b25")
    if ax in axes[:, 0]:
        ax.set_ylabel("Java heap used (GiB)", fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=UTC))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=[0, 30]))
    ax.set_xlim(dt.datetime(2026, 10, 12, 20, tzinfo=UTC), end)
for ax in axes[-1]:
    ax.set_xlabel("October 12, 2026 (UTC)")
fig.suptitle("Besu 26.9.0: heap usage and GC pressure during msf-2", fontsize=15)
fig.legend(handles=[
    Line2D([], [], color="#175b9e", label="Heap used; dotted line = 16 GiB cap"),
    Line2D([], [], color="#c95b25", label="2-minute rate of old-generation GC timer"),
    Line2D([], [], color="#7f2637", linestyle="--", label="Logged heap termination"),
], loc="upper center", bbox_to_anchor=(0.5, 0.947), ncol=3, fontsize=9)
fig.text(0.5, 0.01, "30-second Prometheus samples. Gray shading marks read-only monitoring. "
         "GC timer rate is not a measurement of retained allocations.", ha="center", fontsize=9)
fig.tight_layout(rect=(0, 0.03, 1, 0.91))
fig.savefig(ROOT / "besu-memory-and-gc.png", dpi=160)
plt.close(fig)

raw = EVIDENCE / "observations.jsonl"
if raw.exists():
    lines = raw.read_text().splitlines()
else:
    with gzip.open(str(raw) + ".gz", "rt") as stream:
        lines = stream.read().splitlines()
samples = sorted((json.loads(line) for line in lines), key=lambda s: s["at"])
times, head_lag, finality_lag = [], [], []
for sample in samples:
    # Thirty-six staked matrix pairings; exclude the two unstaked Nimbus EL observers.
    nodes = [n for h, n in sample["nodes"].items()
             if h.endswith("-1") and not h.startswith(("bootnode", "buildoor"))
             and "nimbusel" not in h and "error" not in n]
    if not nodes:
        continue
    latest = max(n["slot"] for n in nodes)
    times.append(dt.datetime.fromisoformat(sample["at"]))
    head_lag.append(max(latest - n["slot"] for n in nodes))
    finality_lag.append(max(n["slot"] // 32 - n["finalized"] for n in nodes))
fig, axes = plt.subplots(2, 1, figsize=(11, 5.5), sharex=True)
axes[0].plot(times, head_lag, color="#175b9e", marker=".", linewidth=1)
axes[0].set_ylabel("Largest sampled\nCL head gap (slots)")
axes[1].plot(times, finality_lag, color="#27806d", marker=".", linewidth=1)
axes[1].set_ylabel("Largest sampled\nfinality lag (epochs)")
for ax in axes:
    ax.grid(alpha=0.2)
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=UTC))
axes[1].set_xlabel("October 12, 2026 (UTC)")
fig.suptitle("msf-2: direct API observations across the 36 validator pairings")
fig.text(0.5, 0.01, "Approximate one-minute cadence; node requests within each cycle are not simultaneous. "
         "Experimental unstaked Nimbus EL observers are excluded.", ha="center", fontsize=9)
fig.tight_layout(rect=(0, 0.04, 1, 0.96))
fig.savefig(ROOT / "network-continuity.png", dpi=160)
plt.close(fig)
