"""Render report figures from captured evidence; no inferred outage durations."""
import datetime as dt
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as dates
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / "msf-2-benchmark-2026-10-12"
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)
GREEN, RED, BLUE, MUTED = "#17685c", "#b84d42", "#4377a8", "#647680"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.labelcolor": "#172531", "text.color": "#172531",
                     "figure.facecolor": "white"})
plt.rcParams["svg.hashsalt"] = "msf2-reports-20261013"


def load(name):
    return json.loads((ROOT / "evidence" / name).read_text())


def finish(fig, name, note):
    fig.text(.06, .025, note, fontsize=9, color=MUTED, va="bottom")
    fig.savefig(OUT / name, dpi=125, bbox_inches="tight")
    fig.savefig(OUT / Path(name).with_suffix(".svg"), bbox_inches="tight", metadata={"Date": None})
    svg = OUT / Path(name).with_suffix(".svg")
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    plt.close(fig)


sample = load("besu-allocation-sample.json")
top = sample["first_besu_frames"][:6]
labels = ["Tx announcements\nsendTransactionAnnouncementsToPeer", "No Besu frame in sampled stack",
          "RocksDBSnapshot.get", "HandshakeSecrets.snapshot", "Hash.digestUsingAlgorithm",
          "BytesValueRLPInput.prepareCurrentItem"]
fig, ax = plt.subplots(figsize=(10, 5.1))
weights = [v / sample["total_sampled_weight_bytes"] * 100 for _, v in top]
bars = ax.barh(np.arange(len(top)), weights, color=[GREEN, MUTED, BLUE, BLUE, BLUE, BLUE])
ax.set_yticks(np.arange(len(top)), labels)
ax.invert_yaxis()
ax.set_xlim(0, max(weights) + 7)
ax.set_xlabel("Share of sampled allocation weight (%)")
ax.set_title(f"Besu canary: {sample['sample_count']:,} allocation samples", loc="left", weight="bold", pad=18)
for bar, value in zip(bars, weights):
    ax.text(value + .4, bar.get_y() + bar.get_height()/2, f"{value:.1f}%", va="center")
fig.subplots_adjust(left=.42, right=.95, bottom=.2, top=.84)
finish(fig, "01-besu-allocation-samples.png",
       "Nimbus–Besu checkpoint 09:49:23 UTC, 13 Oct 2026. Grouped by first Besu frame.\n"
       "JFR sample weights estimate allocation traffic; they do not measure retained heap or prove the earlier OOM cause.")

teku = load("teku-private-reproduction.json")
assert all(r["exit_code"] == 1 and not r["oom_killed"] for r in teku["runs"])
minimal = (ROOT / "evidence/teku-minimal-reproduction.log").read_text()
assert "REPRODUCED=" in minimal and "CANONICAL_CONTROL=" in minimal
fig, ax = plt.subplots(figsize=(10, 4.7))
ax.axis("off")
ax.set_title("Teku: the saved record fails; the canonical control succeeds", loc="left", weight="bold", pad=20)
rows = [["26.9.1", "Saved beacon database", "Startup rejects parent hash"],
        ["26.10.0", "Same saved database", "Startup rejects parent hash"],
        ["26.10.0", "Extracted block + stored envelope", "Metadata reader rejects parent hash"],
        ["26.10.0", "Same block + canonical envelope", "Metadata reader succeeds"]]
table = ax.table(cellText=rows, colLabels=["Released reader", "Input", "Observed result"],
                 cellLoc="left", colLoc="left", bbox=[0, .16, 1, .77], colWidths=[.16, .40, .44])
table.auto_set_font_size(False)
table.set_fontsize(10)
for (row, col), cell in table.get_celld().items():
    cell.set_edgecolor("#d6e1de")
    cell.set_facecolor("#edf4f1" if row == 0 else "white")
    if row > 0 and col == 2:
        cell.set_text_props(color=GREEN if row == 4 else RED, weight="bold")
fig.subplots_adjust(left=.06, right=.97, top=.84, bottom=.15)
finish(fig, "02-teku-record-controls.png",
       "All cases use beacon root 3c681a00…6549 (slot 2559). Offline; no validator keys.\n"
       "The fixture isolates consumption of inconsistent stored metadata; its original writer is still unknown.")

private = load("nimbus-private-listener-test.json")
live = load("nimbus-engine-morning-probe.json")
fig, axes = plt.subplots(1, 2, figsize=(11, 5.3), gridspec_kw={"width_ratios": [1.2, 1]})
ax = axes[0]
for offset, port, color, label in [(-.16, "8545", BLUE, "Ordinary RPC"), (.16, "8551", GREEN, "Engine RPC")]:
    records = [private[k][port] for k in ["before", "after_fin", "after_rst"]]
    values = [r["latency_seconds"] * 1000 for r in records]
    bars = ax.barh(np.arange(3) + offset, values, height=.28, color=color, label=label)
    for b, v, r in zip(bars, values, records):
        ax.text(v * 1.13, b.get_y()+b.get_height()/2,
                f"≥{v:.0f} ms timeout" if "error" in r else f"{v:.1f} ms", va="center", fontsize=8)
        if "error" in r:
            b.set_color(RED)
            b.set_edgecolor("#622c24")
            b.set_hatch("//")
ax.set_yticks(range(3), ["Before", "Queued FIN", "Queued reset"])
ax.invert_yaxis()
ax.set_xscale("log")
ax.set_xlim(.7, 18000)
ax.set_title("Private listener control", loc="left", weight="bold")
ax.legend(loc="upper right", fontsize=8)
ax = axes[1]
records = [live["results"][n]["probe"] for n in ["lighthouse-nimbusel-1", "nimbus-nimbusel-1"]]
values = [r["latency_seconds"] * 1000 for r in records]
bars = ax.barh(range(2), values, color=[GREEN, RED], height=.4)
ax.set_yticks(range(2), ["Control observer", "Affected observer"])
ax.invert_yaxis()
ax.set_xscale("log")
ax.set_xlim(.7, 90000)
for b, v, r in zip(bars, values, records):
    ax.text(v * 1.15, b.get_y()+b.get_height()/2,
            f"≥{v/1000:.1f} s timeout" if "error" in r else f"{v:.1f} ms", va="center", fontsize=8)
ax.set_title("Live paired Engine probe", loc="left", weight="bold")
for ax in axes:
    ax.set_xlabel("Request time (ms, logarithmic scale)")
fig.subplots_adjust(left=.14, right=.95, bottom=.24, top=.82, wspace=.8)
finish(fig, "03-nimbus-listener-controls.png",
       "Private: same deployed image, no peers/workload; reset kills Engine acceptance while FIN and ordinary RPC survive.\n"
       "Live: 08:43 UTC, 13 Oct 2026. Hatched/red timeout bars are lower bounds, not completed-response latencies.")

warnings = json.loads(load("overnight-erigon-optimism.json")["output"])["rows"]
times = [dt.datetime.fromisoformat(r[0]) for r in warnings]
assert len(times) == 22 and {r[1] for r in warnings} == {"teku-erigon-1"}
fig, axes = plt.subplots(2, 1, figsize=(11, 6.6), gridspec_kw={"height_ratios": [1.4, 1]})
ax = axes[0]
events = [(0, "FCU unwind begins", BLUE), (.499, "Replacement payload arrives", BLUE),
          (1.014, "Quick SYNCING reply", RED), (48.124, "Teku skips 31 attestations", RED),
          (120, "Lodestar proposal gets HTTP 503", RED), (132.152, "Lodestar execution reports synced", GREEN)]
for index, (seconds, label, color) in enumerate(events):
    ax.scatter(seconds, index, s=65, color=color, zorder=3)
ax.set_yticks(range(len(events)), [e[1] for e in events])
ax.invert_yaxis()
ax.set_xlim(-3, 143)
ax.set_xlabel("Seconds after 22:58:36 UTC on October 12")
ax.grid(axis="x", alpha=.15)
ax.set_title("Erigon recurrence: unwind, optimistic duties, then recovery", loc="left", weight="bold", pad=16)
ax = axes[1]
ax.vlines(times, 0, 1, color=RED, linewidth=2)
ax.set_ylim(0, 1.3)
ax.set_yticks([])
ax.set_xlim(dt.datetime(2026,10,13,0), dt.datetime(2026,10,13,8,30))
ax.xaxis.set_major_formatter(dates.DateFormatter("%H:%M"))
ax.set_title("22 further Teku–Erigon optimistic activation warnings", loc="left", fontsize=12, pad=12)
ax.set_xlabel("October 13, UTC")
fig.subplots_adjust(left=.35, right=.96, bottom=.2, top=.87, hspace=.75)
finish(fig, "04-erigon-recovery-timeline.png",
       "Events are observed timestamps; the chart does not assert a continuously optimistic interval on either node.\n"
       "The lower panel counts activation warnings, not separate measured outages. The quick-status branch is not isolated.")

census = json.loads((OLD / "evidence/monitoring-summary.json").read_text())
hosts = ["nimbus-reth-1", "grandine-besu-1", "lighthouse-besu-1", "lodestar-erigon-1"]
assigned = census["duty_census_assigned_by_host"]
missed = census["duty_census_missed_by_host"]
counts = [assigned[h] for h in hosts]
missing = [missed[h] for h in hosts]
other_count = sum(assigned.values()) - sum(counts)
assert sum(assigned.values()) == 288 and sum(missed.values()) == 16
counts.append(other_count)
missing.append(0)
fig, axes = plt.subplots(1, 2, figsize=(11, 5.7), gridspec_kw={"width_ratios": [1.3, 1]})
ax = axes[0]
rates = [m / n * 100 for m, n in zip(missing, counts)]
bars = ax.barh(range(5), rates, color=[RED, BLUE, BLUE, BLUE, GREEN])
ax.set_yticks(range(5), ["Nimbus–Reth", "Grandine–Besu", "Lighthouse–Besu", "Lodestar–Erigon", "Other 32 pairings"])
ax.invert_yaxis()
ax.set_xlim(0, 125)
ax.set_xticks([0, 25, 50, 75, 100])
for bar, m, n, r in zip(bars, missing, counts, rates):
    ax.text(r + 2, bar.get_y()+bar.get_height()/2, f"{m}/{n}", va="center", fontsize=10)
ax.set_xlabel("Missing canonical blocks / assigned proposals (%)")
ax.set_title("Completed epochs 88–96", loc="left", weight="bold", pad=16)
ax = axes[1]
ax.axis("off")
steps = [("Validated bid arrives before slot", GREEN),
         ("Local getPayload times out", RED),
         ("Missing-local-candidate guard returns", RED),
         ("External selection is never reached", MUTED)]
for i, (label, color) in enumerate(steps):
    y = .85 - .22 * i
    ax.text(.5, y, label, ha="center", va="center", fontsize=10,
            bbox={"boxstyle":"round,pad=.7", "facecolor":"#edf4f1", "edgecolor":color}, transform=ax.transAxes)
    if i < 3:
        ax.annotate("", xy=(.5,y-.15), xytext=(.5,y-.075), xycoords="axes fraction", arrowprops={"arrowstyle":"->", "color":MUTED})
ax.set_title("Released integrated-proposer path", fontsize=11, weight="bold", pad=16)
fig.subplots_adjust(left=.17, right=.98, bottom=.22, top=.84, wspace=.6)
finish(fig, "05-nimbus-proposal-impact.png",
       "Canonical-duty census: 288 assigned slots, 16 missing; Nimbus–Reth accounts for 12 (75%) of the missing slots.\n"
       "The 12/12 applies only to these completed epochs. Overnight timeout/publication log counts are a separate population.")
print("Rendered five new figures from captured data.")
