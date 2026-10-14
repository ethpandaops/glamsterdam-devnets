"""Draw review figures from captured telemetry; no live requests."""
import datetime as dt
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as dates

ROOT = Path(__file__).resolve().parent
EV = ROOT / 'evidence'
summary = json.loads((EV / 'review-summary.json').read_text())
colors = {'nimbus-reth-1': '#b03a2e', 'nimbus-besu-1': '#d68910', 'grandine-reth-1': '#7d3c98'}
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})

def save(fig, name):
    fig.savefig(ROOT / (name + '.png'), dpi=155, bbox_inches='tight')
    path = ROOT / (name + '.svg')
    fig.savefig(path, bbox_inches='tight')
    path.write_text('\n'.join(x.rstrip() for x in path.read_text().splitlines()) + '\n')
    plt.close(fig)

fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained', gridspec_kw={'width_ratios': [1, 1.8]})
hosts = list(colors)
for i, h in enumerate(hosts):
    n = summary['missing_by_host'][h]
    axes[0].barh(i, n, color=colors[h])
    axes[0].text(n + .12, i, f"{n}/{summary['assigned'][h]} assigned", va='center', fontsize=9)
axes[0].set(yticks=range(3), yticklabels=['Nimbus–Reth', 'Nimbus–Besu', 'Grandine–Reth'], xlim=(0, 10.5), xlabel='Missing canonical proposals', title=f"9 misses among {summary['canonical_slots_examined']:,} finalized slots")
axes[0].invert_yaxis()
timings = [t for t in summary['miss_timings'] if 'validated_bid_offset_seconds' in t]
labels = []
for i, t in enumerate(timings):
    labels.append(f"{t['slot']} · {'Besu' if t['host']=='nimbus-besu-1' else 'Reth'}")
    axes[1].scatter(t['validated_bid_offset_seconds'], i, marker='D', color='#17685c', s=45, label='Validated remote bid' if i == 0 else None)
    axes[1].scatter(t['local_get_payload_offset_seconds'], i, marker='o', color='#2874a6', s=40, label='Local getPayload request' if i == 0 else None)
    axes[1].scatter(t['timeout_offset_seconds'], i, marker='X', color='#b03a2e', s=65, label='Local timeout; canonical slot missing' if i == 0 else None)
    axes[1].plot([t['local_get_payload_offset_seconds'], t['timeout_offset_seconds']], [i, i], color='#b03a2e', alpha=.35)
axes[1].axvline(0, color='#85929e', linestyle='--')
axes[1].set(yticks=range(len(labels)), yticklabels=labels, xlabel='Seconds relative to slot start', xlim=(-.7, 2.2), title='Every Nimbus miss had a validated pre-slot bid')
axes[1].invert_yaxis()
axes[1].legend(loc='upper center', bbox_to_anchor=(.5, -.15), fontsize=8)
fig.suptitle('Glamsterdam msf-2 · October 13–14 · observational duty census', fontsize=14)
save(fig, 'proposal-review')

slow = json.loads((EV / 'reth-delayed-valid-responses.json').read_text())
fig, ax = plt.subplots(figsize=(10, 5.6), layout='constrained')
palette = {'prysm-reth-1': '#2874a6', 'grandine-reth-1': '#7d3c98', 'nimbus-reth-1': '#b03a2e'}
labels = [f"{x['block']} · {x['host'].split('-')[0]}" for x in slow]
ax.barh(range(len(slow)), [x['elapsed_seconds'] for x in slow], color=[palette[x['host']] for x in slow])
for i, x in enumerate(slow):
    ax.text(x['elapsed_seconds'] + .1, i, f"{x['elapsed_seconds']:.2f}s", va='center', fontsize=9)
ax.axvline(12, color='#34495e', linestyle='--')
ax.text(12.1, -.65, '12 second slot', color='#34495e', fontsize=9)
ax.set(yticks=range(len(labels)), yticklabels=labels, xlim=(0, 16), xlabel='Reth logged request elapsed time (seconds)', title='VALID results arrived after the CL had cancelled the request\n14:27–14:28 UTC · elapsed time includes queueing and execution')
ax.invert_yaxis()
ax.grid(axis='x', alpha=.15); ax.set_axisbelow(True)
save(fig, 'reth-delayed-valid')

fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True, layout='constrained')
heap = json.loads((EV / 'besu-heap-history.json').read_text())['result']['data']['result']
for series in heap:
    axes[0].plot([dt.datetime.fromtimestamp(float(t), dt.timezone.utc) for t, _ in series['values']], [float(v) * 100 for _, v in series['values']], label=series['metric']['instance'].replace('glamsterdam-msf-2-', '').replace('-besu-1', ''), linewidth=1.2)
axes[0].axhline(90, linestyle='--', color='#b03a2e', alpha=.45)
axes[0].set(ylabel='Besu heap occupied (%)', ylim=(0, 105), title='Six Besu nodes: high heap samples, no additional OOM artifacts found')
axes[0].legend(ncol=6, fontsize=8, loc='upper center', bbox_to_anchor=(.5, 1.04))
gas = json.loads((EV / 'workload-gas-history.json').read_text())['result']['data']['result']
for series in gas:
    if series['metric']['execution_client'] == 'nethermind':
        axes[1].plot([dt.datetime.fromtimestamp(float(t), dt.timezone.utc) for t, _ in series['values']], [float(v)/1e6 for _, v in series['values']], color='#17685c')
axes[1].set(ylabel='Head gas used (millions)', xlabel='UTC · five minute samples', title='Workload varies: sampled Nethermind head gas across pairings')
axes[1].xaxis.set_major_locator(dates.HourLocator(interval=3)); axes[1].xaxis.set_major_formatter(dates.DateFormatter('%H:%M', tz=dt.timezone.utc))
for ax in axes:ax.grid(alpha=.15); ax.set_axisbelow(True)
save(fig, 'besu-workload-review')
