"""Rebuild review statistics from preserved evidence; no live queries."""
import collections
import datetime as dt
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
EV = ROOT / 'evidence'
REPO = ROOT.parents[1]
window = json.loads((ROOT / 'window.json').read_text())
inventory = (REPO / 'ansible/inventories/msf-2/inventory.ini').read_text()
ranges = [(h, int(a), int(b)) for h, a, b in re.findall(r'^(\S+).*validator_start=(\d+) validator_end=(\d+)', inventory, re.M)]
assigned, misses, epochs, timing = collections.Counter(), [], [], []
old = REPO / 'md/msf-2-overnight-2026-10-13/evidence/epochs'
files = list(old.glob('*.json')) + list((EV / 'epochs').glob('*.json'))
for path in sorted(files, key=lambda p: int(p.stem)):
    data = json.loads(path.read_text())
    if not window['first_census_epoch'] <= data['epoch'] <= window['last_census_epoch']:
        continue
    epochs.append(data['epoch'])
    duties = {int(x['slot']): int(x['validator_index']) for x in data['proposer_duties']['data']}
    assert len(data['headers']) == len(duties) == 32
    for header in data['headers']:
        assert 'error' not in header
        slot = header['slot']; validator = duties[slot]
        host = next(h for h, a, b in ranges if a <= validator < b)
        assigned[host] += 1
        if header['exists'] is False:
            misses.append({'slot': slot, 'epoch': data['epoch'], 'validator': validator, 'host': host, 'evidence': str(path.relative_to(REPO))})
assert epochs == list(range(window['first_census_epoch'], window['last_census_epoch'] + 1))
for miss in misses:
    path = EV / f"missed-slot-{miss['slot']}-logs.json"
    if not path.exists():
        continue
    data = json.loads(path.read_text())
    rows = data.get('result', {}).get('rows', [])
    start = dt.datetime.fromtimestamp(1791810180 + miss['slot'] * 12, dt.timezone.utc)
    record = {**miss, 'slot_start_utc': start.isoformat()}
    for key, phrase in [('validated_bid', 'Execution payload bid validated'), ('local_get_payload', 'name=engine_getPayloadV6'), ('timeout', 'Timeout while getting execution payload')]:
        hits = [r for r in rows if phrase in r[-1] and (key != 'validated_bid' or f"bidSlot={miss['slot']} " in r[-1])]
        if hits:
            row = hits[0]
            at = dt.datetime.fromisoformat(row[0][:26]).replace(tzinfo=dt.timezone.utc)
            record[key + '_at'] = row[0]
            record[key + '_offset_seconds'] = (at - start).total_seconds()
    if 'local_get_payload_offset_seconds' in record and 'timeout_offset_seconds' in record:
        record['request_to_timeout_seconds'] = record['timeout_offset_seconds'] - record['local_get_payload_offset_seconds']
    timing.append(record)
night = json.loads((REPO / 'md/msf-2-overnight-2026-10-13/summary.json').read_text())
current = json.loads((EV / 'current-network.json').read_text())
first = json.loads((REPO / 'md/msf-2-overnight-2026-10-13/evidence/baseline.json').read_text())
counts = collections.Counter()
for path in EV.glob('log-counts-*.json'):
    data = json.loads(path.read_text())
    assert 'error' not in data, path
    for row in data['result']['rows']:
        counts[(row[0], row[1], row[2])] += int(row[3])
nimbus_timeouts = collections.Counter()
for path in EV.glob('nimbus-timeout-counts-*.json'):
    data = json.loads(path.read_text())
    assert 'error' not in data, path
    for row in data['result']['rows']:
        nimbus_timeouts[row[0]] += int(row[1])
results = {'window': window, 'epochs': epochs, 'canonical_slots_examined': sum(assigned.values()), 'assigned': dict(assigned), 'missing_by_host': dict(collections.Counter(x['host'] for x in misses)), 'misses': misses, 'miss_timings': timing, 'nimbus_payload_timeout_counts': dict(nimbus_timeouts), 'disjoint_hourly_log_counts': [{'host': h, 'container': c, 'category': k, 'count': n} for (h, c, k), n in sorted(counts.items())], 'overnight_capture_count': night['cycle'], 'first_reference_finalized': first['nodes']['nimbus-nethermind-1']['finalized'], 'last_reference_finalized': current['nodes']['nimbus-nethermind-1']['finalized']}
(EV / 'review-summary.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps({'epochs': [min(epochs), max(epochs)], 'slots': results['canonical_slots_examined'], 'misses': results['missing_by_host'], 'assigned_affected': {h: assigned[h] for h in results['missing_by_host']}, 'finality': [results['first_reference_finalized'], results['last_reference_finalized']], 'nimbus_timeouts': dict(nimbus_timeouts)}, indent=2))
