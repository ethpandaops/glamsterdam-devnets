#!/usr/bin/env python3
"""Bounded, read-only msf-2 monitoring. Run one tick from a systemd timer."""
import argparse
import collections
import concurrent.futures as cf
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

UTC = dt.timezone.utc
NETWORK = 'glamsterdam-msf-2'
REFERENCE = 'nimbus-nethermind-1'
REMOTE = r'''
import concurrent.futures as cf,datetime,json,subprocess,urllib.request
out={'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def fetch(key,path,rpc=False):
 try:
  if rpc:
   req=urllib.request.Request('http://127.0.0.1:8545',data=json.dumps({'jsonrpc':'2.0','id':1,'method':path,'params':[]}).encode(),headers={'Content-Type':'application/json'})
   d=json.load(urllib.request.urlopen(req,timeout=8))
   if 'error' in d:raise ValueError(str(d['error']))
   d=d['result']
   if key in ('el_block','el_peers'):d=int(d,16)
  else:d=json.load(urllib.request.urlopen('http://127.0.0.1:5052'+path,timeout=8))['data']
  return key,d
 except Exception as e:return key,{'error':type(e).__name__+': '+str(e)[:200]}
queries=[('sync','/eth/v1/node/syncing',False),('head','/eth/v1/beacon/headers/head',False),('finality','/eth/v1/beacon/states/head/finality_checkpoints',False),('el_syncing','eth_syncing',True),('el_block','eth_blockNumber',True),('el_peers','net_peerCount',True)]
with cf.ThreadPoolExecutor(max_workers=6) as pool:out.update(pool.map(lambda x:fetch(*x),queries))
if 'error' not in out['head']:
 out['slot']=int(out['head']['header']['message']['slot']);out['root']=out['head']['root']
if 'error' not in out['finality']:out['finalized']=int(out['finality']['finalized']['epoch'])
out['containers']=[]
for name in ['execution','beacon','validator']:
 p=subprocess.run(['docker','inspect','--format','{{json .}}',name],capture_output=True,text=True,timeout=8)
 if p.returncode==0:
  d=json.loads(p.stdout);s=d['State'];out['containers'].append({'name':name,'id':d['Id'],'image':d['Config']['Image'],'image_id':d['Image'],'running':s['Running'],'restarts':d['RestartCount'],'started':s['StartedAt'],'oom_killed':s['OOMKilled'],'exit_code':s['ExitCode']})
print(json.dumps(out))
'''
PROFILE = r'''
import datetime,json,pathlib,shutil,subprocess
p=pathlib.Path('/data/besu-profiling');out={'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'free_bytes':shutil.disk_usage('/data').free}
for name in ['besu-profiling.timer','besu-profiling.service']:
 r=subprocess.run(['systemctl','show',name,'--property=ActiveState,SubState,Result,ExecMainStatus'],capture_output=True,text=True,timeout=8)
 out[name]=dict(x.split('=',1) for x in r.stdout.splitlines() if '='in x)
if (p/'status.json').exists():
 d=json.loads((p/'status.json').read_text());out['status']={k:d[k] for k in ('captured_at_utc','run_id','container_started_at','image_id','recording','bytes') if k in d}
if (p/'active-run').exists():out['active_run']=(p/'active-run').read_text().strip()
out['heap_dumps']=[{'path':str(x),'bytes':x.stat().st_size,'mtime':datetime.datetime.fromtimestamp(x.stat().st_mtime,datetime.timezone.utc).isoformat()} for x in (p/'runs').glob('*/heap.hprof')]
print(json.dumps(out))
'''
CENSUS = r'''
import concurrent.futures as cf,json,sys,urllib.request,urllib.error
base='http://127.0.0.1:5052';epoch=int(sys.argv[1])
def header(slot):
 try:
  d=json.load(urllib.request.urlopen(base+'/eth/v1/beacon/headers/'+str(slot),timeout=8))['data'];return {'slot':slot,'exists':True,'root':d['root']}
 except urllib.error.HTTPError as e:
  return {'slot':slot,'exists':False} if e.code==404 else {'slot':slot,'error':str(e)}
 except Exception as e:return {'slot':slot,'error':type(e).__name__}
with cf.ThreadPoolExecutor(max_workers=5) as pool:headers=list(pool.map(header,range(epoch*32,(epoch+1)*32)))
duties=json.load(urllib.request.urlopen(base+'/eth/v1/validator/duties/proposer/'+str(epoch),timeout=15))
print(json.dumps({'epoch':epoch,'headers':headers,'proposer_duties':duties}))
'''
PATTERNS = {
 'critical': r'OutOfMemoryError|Terminating due|\bFATAL\b|panic:|state root mismatch|INVALID_PAYLOAD|Invalid execution payload',
 'engine_timeout': r'(?i)TimeoutGetPayload|(?:getPayload|newPayload|forkchoice|execution engine|engine API).{0,100}(?:timed out|timeout)|(?:timed out|timeout).{0,100}(?:getPayload|newPayload|forkchoice|execution engine)',
 'duty_loss': r'(?i)Skipping.{0,100}(?:attestation|duties)|Failed to produce block|Unable to produce block|Failed to propose|Block production failed|Failed to create.*block|broadcast.*late',
 'optimistic_activation': r'(?i)optimistic head activation|optimistic mode.*activ|execution engine.*offline|execution layer.*offline',
}


def iso(value=None):
    return (value or dt.datetime.now(UTC)).isoformat()


def moment(value):
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))


def scrub(value):
    """Defense in depth for log excerpts; never collect env or validator files."""
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if re.search(r'(?i)secret|password|api.?key|authorization|token|credential', k) else v if k in ('id', 'image_id') else scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r'(?i)(bearer\s+)[\w.=-]+', r'\1[REDACTED]', value)
    value = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED JWT]', value)
    value = re.sub(r'(?i)((?:secret|password|api.?key|authorization|token|credential)\s*[=:]\s*)(?:"[^"]*"|\S+)', r'\1[REDACTED]', value)
    value = re.sub(r'(https?://)[^\s/@]+:[^\s/@]+@', r'\1[REDACTED]@', value)
    # Ethereum roots with 0x are public; naked 32-byte values may be secrets.
    return re.sub(r'(?<![\w])(?<!0x)[a-fA-F0-9]{64}(?![\w])', '[REDACTED 32-byte value]', value)


def save(path, data, *, sanitize=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(scrub(data) if sanitize else data, indent=2) + '\n')
    temporary.replace(path)


def command(args, *, data=None, timeout=45, cwd=None):
    p = subprocess.run(args, input=data, capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if p.returncode:
        raise RuntimeError(f'{args[0]} exited {p.returncode}: {scrub(p.stderr[-300:])}')
    return p.stdout


def ssh(host, source, *args, sudo=False, timeout=45):
    argv = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', NETWORK + '-' + host]
    if sudo:
        argv += ['sudo', '-n']
    argv += ['python3', '-', *map(str, args)]
    try:
        return json.loads(command(argv, data=source, timeout=timeout))
    except Exception as e:
        return {'error': scrub(str(e))[:350]}


def panda(*args):
    return json.loads(command(['panda', '-o', 'json', *args], timeout=50))


def inventory(repo):
    raw = (repo / 'ansible/inventories/msf-2/inventory.ini').read_text()
    hosts = re.findall(r'^(\S+) ansible_host=', raw, re.M)
    ranges = {h: (int(a), int(b)) for h, a, b in re.findall(r'^(\S+).*validator_start=(\d+) validator_end=(\d+)', raw, re.M)}
    return hosts, ranges


def classify_node(node, wall_slot):
    problems = []
    for key in ('sync', 'head', 'finality', 'el_syncing', 'el_block', 'el_peers'):
        if isinstance(node.get(key), dict) and 'error' in node[key]:
            problems.append('api_' + key)
    if 'error' in node:
        return ['collection_error']
    sync = node.get('sync', {})
    for key in ('is_syncing', 'is_optimistic', 'el_offline'):
        if sync.get(key):
            problems.append(key)
    if wall_slot - node.get('slot', wall_slot) > 3:
        problems.append('head_lag_over_3_slots')
    if node.get('slot', 0) // 32 - node.get('finalized', 0) > 3:
        problems.append('finality_lag_over_3_epochs')
    if node.get('el_syncing') is not False:
        problems.append('el_syncing_or_unknown')
    if node.get('el_peers') == 0:
        problems.append('zero_el_peers')
    for item in node.get('containers', []):
        if not item['running']:
            problems.append(item['name'] + '_stopped')
    return problems


class Monitor:
    def __init__(self, repo, state_dir):
        self.repo, self.state_dir = repo, state_dir
        self.folder = repo / 'md/msf-2-overnight-2026-10-13'
        self.evidence = self.folder / 'evidence'
        self.config = json.loads((self.folder / 'config.json').read_text())
        self.state = json.loads((state_dir / 'state.json').read_text()) if (state_dir / 'state.json').exists() else {'events': {}, 'containers': {}, 'last_full': None, 'last_push': None, 'cycle': 0, 'missed': [], 'assigned': {}}
        self.hosts, self.ranges = inventory(repo)
        self.now = dt.datetime.now(UTC)
        self.end = moment(self.config['end'])
        self.start = moment(self.config['start'])
        self.wall_slot = int((self.now.timestamp() - self.config['genesis_time']) // 12)
        self.stamp = self.now.strftime('%Y%m%dT%H%M%SZ')

    def event(self, kind, host, detail, evidence, known=False, count=1):
        key = kind + ':' + host
        events = self.state['events']
        if key not in events:
            events[key] = {'kind': kind, 'host': host, 'first_seen': iso(self.now), 'observations': 0, 'known_before_window': known, 'first_evidence': evidence}
        item = events[key]
        item.update(last_seen=iso(self.now), latest_detail=scrub(detail), latest_evidence=evidence)
        item['observations'] += count

    def capture(self, path, data):
        save(self.evidence / path, data)
        return 'evidence/' + path

    def read_nodes(self, full):
        hosts = self.hosts if full else [REFERENCE, 'lighthouse-geth-1', 'teku-nethermind-1']
        with cf.ThreadPoolExecutor(max_workers=10) as pool:
            nodes = dict(zip(hosts, pool.map(lambda h: ssh(h, REMOTE), hosts)))
        evidence = self.capture('health/' + self.stamp + '.json', {'at': iso(self.now), 'full': full, 'wall_slot': self.wall_slot, 'nodes': nodes})
        self.state['latest_health'] = evidence
        if full:
            self.state['latest_full_health'] = evidence
            self.state['latest_full_at'] = iso(self.now)
        root_groups = collections.defaultdict(lambda: collections.defaultdict(list))
        finalized_roots = collections.defaultdict(lambda: collections.defaultdict(list))
        validator_ok = 0
        for host, node in nodes.items():
            issues = classify_node(node, self.wall_slot)
            if not issues and host in self.ranges:
                validator_ok += 1
            if issues:
                self.event('health', host, issues, evidence, known=host in ('lighthouse-nimbusel-1', 'nimbus-nimbusel-1'))
            if not issues and 'finalized' in node:
                checkpoint = node.get('finality', {}).get('finalized', {})
                if checkpoint.get('root'):
                    finalized_roots[node['finalized']][checkpoint['root']].append(host)
            if not issues and 'root' in node:
                root_groups[node['slot']][node['root']].append(host)
            for container in node.get('containers', []):
                key = host + ':' + container['name']
                identity = {k: container[k] for k in ('id', 'image', 'image_id', 'restarts', 'started')}
                before = self.state['containers'].get(key)
                if before and before != identity:
                    self.event('container_change', key, {'before': before, 'after': identity, 'attribution': 'restart or deployment candidate; image changes may be Watchtower updates'}, evidence)
                self.state['containers'][key] = identity
        for slot, roots in root_groups.items():
            if len(roots) > 1:
                self.event('validated_root_disagreement_candidate', 'network', {'slot': slot, 'roots': dict(roots), 'requires': 'confirm persistent divergence using finalized roots; API reads are not simultaneous'}, evidence)
        for epoch, roots in finalized_roots.items():
            if len(roots) > 1:
                self.event('finalized_root_disagreement', 'network', {'epoch': epoch, 'roots': dict(roots)}, evidence)
        healthy_refs = [n for h, n in nodes.items() if h in (REFERENCE, 'lighthouse-geth-1', 'teku-nethermind-1') and not classify_node(n, self.wall_slot)]
        if not healthy_refs:
            self.event('no_healthy_reference', 'network', 'All sampled references unavailable or unhealthy', evidence)
        finals = [n['finalized'] for h, n in nodes.items() if h in (REFERENCE, 'lighthouse-geth-1', 'teku-nethermind-1') and 'finalized' in n]
        if finals:
            finalized = max(finals)
            if finalized > self.state.get('finalized', -1):
                self.state['finality_advanced_at'] = iso(self.now)
            self.state['finalized'] = finalized
            self.state.setdefault('first_finalized', finalized)
            if self.now - moment(self.state['finality_advanced_at']) > dt.timedelta(minutes=15):
                self.event('finality_not_advancing_15m', 'network', {'finalized_epoch': finalized, 'last_advance': self.state['finality_advanced_at']}, evidence)
        if full:
            self.state['validator_ok'] = validator_ok
        self.state['wall_slot'] = self.wall_slot
        self.state['last_health_at'] = iso(self.now)
        return nodes

    def read_profiles(self):
        hosts = [h for h in self.hosts if '-besu-' in h]
        with cf.ThreadPoolExecutor(max_workers=6) as pool:
            values = dict(zip(hosts, pool.map(lambda h: ssh(h, PROFILE, sudo=True), hosts)))
        evidence = self.capture('profiling/' + self.stamp + '.json', values)
        for host, data in values.items():
            if 'error' in data:
                self.event('profiling_collection_error', host, data, evidence)
                continue
            status = data.get('status', {})
            if data.get('besu-profiling.timer', {}).get('ActiveState') != 'active' or data.get('besu-profiling.service', {}).get('Result') not in (None, 'success'):
                self.event('profiling_timer_failure', host, data, evidence)
            if not status or (self.now - moment(status['captured_at_utc'])).total_seconds() > 720 or data.get('active_run') != status.get('run_id'):
                self.event('profiling_checkpoint_stale', host, data, evidence)
            if data.get('free_bytes', 0) < 40 * 1024**3:
                self.event('profiling_low_disk', host, data['free_bytes'], evidence)
            for dump in data.get('heap_dumps', []):
                self.event('besu_heap_dump', host, {**dump, 'privacy': 'Host-local metadata only; no dump uploaded'}, evidence, known=moment(dump['mtime']) < self.start)

    def read_metrics(self):
        selector = 'network="' + NETWORK + '",job="execution"'
        queries = {
            'scrapes': 'up{network="' + NETWORK + '"}',
            'besu_heap_fraction': 'jvm_memory_used_bytes{' + selector + ',area="heap",execution_client="besu"} / jvm_memory_max_bytes{' + selector + ',area="heap",execution_client="besu"}',
            'besu_gc_seconds_per_second': 'rate(jvm_gc_collection_seconds_sum{' + selector + ',execution_client="besu"}[5m])',
            'payload_latency_ms': 'rate(new_payload_v1_latency_milliseconds_sum{network="' + NETWORK + '"}[5m]) / rate(new_payload_v1_latency_milliseconds_count{network="' + NETWORK + '"}[5m])',
            'memory_available': 'node_memory_MemAvailable_bytes{network="' + NETWORK + '"}',
            'cpu_steal': 'avg by(instance) (rate(node_cpu_seconds_total{network="' + NETWORK + '",mode="steal"}[5m]))',
            'gas_used': 'eth_exe_block_head_gas_used{network="' + NETWORK + '"}',
        }
        def query(item):
            k, q = item
            try:
                return k, panda('prometheus', 'query', 'devnets', q)
            except Exception as e:
                return k, {'error': str(e)}
        with cf.ThreadPoolExecutor(max_workers=4) as pool:
            results = dict(pool.map(query, queries.items()))
        evidence = self.capture('metrics/' + self.stamp + '.json', {'at': iso(self.now), 'queries': queries, 'results': results})
        for key, result in results.items():
            if 'error' in result or result.get('status') != 'success':
                self.event('metrics_collection_error', key, result, evidence)
                continue
            points = result.get('data', {}).get('result', [])
            if key == 'besu_heap_fraction' and len(points) != 6:
                self.event('besu_heap_metric_coverage', 'collector', {'expected': 6, 'received': len(points)}, evidence)
            for point in points:
                host = point['metric'].get('instance', 'unknown')
                value = float(point['value'][1])
                if not math.isfinite(value):
                    continue
                condition = (key == 'scrapes' and value == 0) or (key == 'besu_heap_fraction' and value >= .9) or (key == 'besu_gc_seconds_per_second' and value >= .5) or (key == 'cpu_steal' and value >= .2)
                if condition:
                    self.event('metric_' + key, host, {'value': value, 'labels': point['metric'], 'interpretation': 'threshold observation, not proof of a client defect'}, evidence)

    def read_logs(self):
        # Delay queries for ingestion; replay five minutes to catch late rows.
        upper = min(self.now - dt.timedelta(minutes=2), self.end)
        cursor = moment(self.state.get('logs_cursor', self.config['start']))
        lower = max(self.start, cursor - dt.timedelta(minutes=5))
        if upper <= lower:
            return
        fmt = lambda d: d.strftime('%Y-%m-%d %H:%M:%S')
        clause = f"ResourceAttributes['network']='{NETWORK}' AND ResourceAttributes['container.name'] IN ('execution','beacon','validator') AND Timestamp >= toDateTime('{fmt(lower)}') AND Timestamp < toDateTime('{fmt(upper)}')"
        seen = set(self.state.get('seen_log_ids', []))
        records, failures = {}, False
        for category, pattern in PATTERNS.items():
            escaped = pattern.replace('\\', '\\\\').replace("'", "\\'")
            common = clause + f" AND match(Body,'{escaped}')"
            count_query = f"SELECT ResourceAttributes['host.name'] AS host, ResourceAttributes['container.name'] AS container, count() AS rows, min(Timestamp) AS first_seen, max(Timestamp) AS last_seen FROM external.otel_logs WHERE {common} GROUP BY host, container ORDER BY host, container LIMIT 200"
            sample_query = f"SELECT DISTINCT Timestamp, ResourceAttributes['host.name'] AS host, ResourceAttributes['container.name'] AS container, substring(Body,1,6000) AS Body FROM external.otel_logs WHERE {common} ORDER BY Timestamp DESC LIMIT 5 BY host, container LIMIT 500"
            try:
                counts = panda('clickhouse', 'query-raw', 'clickhouse-raw', count_query)
                samples = panda('clickhouse', 'query-raw', 'clickhouse-raw', sample_query)
                records[category] = {'count_query': count_query, 'sample_query': sample_query, 'counts': counts, 'samples': samples}
                for row in reversed(samples.get('rows', [])):
                    ident = hashlib.sha256(json.dumps(row).encode()).hexdigest()
                    if ident not in seen:
                        seen.add(ident)
                        self.event('log_' + category, row[1], {'timestamp': row[0], 'container': row[2], 'body': row[3], 'requires': 'correlate with duties and health; logs alone do not prove a new defect'}, 'evidence/logs/' + self.stamp + '.json', known=category == 'engine_timeout' and row[1] in ('nimbus-reth-1', 'nimbus-nimbusel-1'))
            except Exception as e:
                failures = True
                records[category] = {'error': str(e), 'count_query': count_query, 'sample_query': sample_query}
                self.event('logs_collection_error', category, str(e), 'evidence/logs/' + self.stamp + '.json')
        self.capture('logs/' + self.stamp + '.json', {'from': iso(lower), 'to': iso(upper), 'overlap_seconds': 300, 'records': records})
        self.state['seen_log_ids'] = sorted(seen)[-20000:]
        if not failures:
            self.state['logs_cursor'] = iso(upper)

    def read_census(self):
        # Finalized epochs, fully inside the window; never call a live reorg a miss.
        first = math.ceil((self.start.timestamp() - self.config['genesis_time']) / 384)
        last = min(self.state.get('finalized', -1), int((self.end.timestamp() - self.config['genesis_time']) // 384) - 1)
        pending = [e for e in range(first, last + 1) if not (self.evidence / f'epochs/{e}.json').exists()]
        for epoch in pending[:6]:
            d = ssh(REFERENCE, CENSUS, epoch, timeout=90)
            if 'error' in d or len(d.get('headers', [])) != 32 or any('error' in x for x in d.get('headers', [])):
                self.event('census_collection_error', str(epoch), d, self.state.get('latest_health', ''))
                continue
            duties = {int(x['slot']): int(x['validator_index']) for x in d['proposer_duties']['data']}
            if len(duties) != 32:
                self.event('census_collection_error', str(epoch), 'Incomplete proposer duty set', '')
                continue
            evidence = self.capture(f'epochs/{epoch}.json', d)
            for header in d['headers']:
                slot = header['slot']; validator = duties[slot]
                host = next((h for h, (a, b) in self.ranges.items() if a <= validator < b), 'unmapped')
                self.state['assigned'][host] = self.state['assigned'].get(host, 0) + 1
                if header.get('exists') is False:
                    miss = {'slot': slot, 'epoch': epoch, 'validator': validator, 'host': host, 'evidence': evidence}
                    self.state['missed'].append(miss)
                    self.event('missing_canonical_proposal', host, {**miss, 'interpretation': 'A missing canonical slot; may include a late or orphaned attempted proposal'}, evidence, known=host == 'nimbus-reth-1')

    def report(self, finished=False):
        events = self.state['events']
        ordered = sorted(events.values(), key=lambda e: (e['first_seen'], e['kind'], e['host']))
        summary = {k: v for k, v in self.state.items() if k not in ('seen_log_ids', 'containers')}
        summary.update(start=self.config['start'], end=self.config['end'], status='complete' if finished else 'running', last_tick=iso(self.now))
        save(self.folder / 'summary.json', summary)
        rows = []
        for e in ordered:
            detail = json.dumps(e['latest_detail'], ensure_ascii=False).replace('|', '\\|').replace('\n', ' ')[:700]
            evidence = e.get('latest_evidence')
            label = 'Known recurrence' if e['known_before_window'] else 'Review candidate'
            link = f'[evidence]({evidence})' if evidence else 'collector state'
            rows.append(f"| {e['kind']} | {e['host']} | {label} | {e['first_seen']} | {e['last_seen']} | {e['observations']} | {detail} {link} |")
        misses = collections.Counter(x['host'] for x in self.state['missed'])
        duties = '\n'.join(f"| {h} | {misses[h]} | {n} |" for h, n in sorted(self.state['assigned'].items()))
        text = f'''# Glamsterdam msf 2 overnight monitoring October 13 to 14 2026

Monitoring is {'complete' if finished else 'running'} for **{self.config['start']} to {self.config['end']}**. Last tick: **{iso(self.now)}**. The latest full check found **{self.state.get('validator_ok', 'pending')}/36 validator pairings** healthy at **{self.state.get('latest_full_at', 'pending')}**. Reference finalized epoch advanced from **{self.state.get('first_finalized', 'pending')}** to **{self.state.get('finalized', 'pending')}**. This is sampled health, not a claim of uninterrupted operation.

The initial baseline found all 36 validator pairings healthy. Two unstaked Nimbus EL observers retained their previously documented optimistic or Engine offline state. These are tracked as known conditions. [Baseline](evidence/baseline.json). All six Besu hosts also retained afternoon OOM artifacts discovered at startup; these predate the overnight window and are detailed in [the Besu follow-up](besu-oom-followup.md). [Existing client reports](../msf-2-issue-reports-2026-10-13/README.md).

## Findings requiring review

Events are evidence for investigation. Threshold crossings and log errors are candidates; they do not establish a new client defect. Counts are sampled observations or distinct retained log excerpts, not outage counts. Recovery can occur between samples. Known conditions remain labelled separately.

| Signal | Host | Classification | First observed UTC | Last observed UTC | Observations | Latest detail |
|---|---|---|---|---|---:|---|
{chr(10).join(rows) if rows else '| No events yet | | | | | | |'}

## Finalized proposer duty census

Only finalized epochs fully contained in the monitoring window enter the census. A 404 for a finalized canonical slot is counted as missing. Other API failures leave the epoch pending. Missing canonical data does not establish that no block was signed; late and orphaned proposals require log follow-up. The current incomplete epoch and unfinalized tail are excluded.

| Pairing | Missing canonical slots | Assigned duties |
|---|---:|---:|
{duties if duties else '| Census pending | | |'}

## Collection and coverage

Three independent client pairings provide minute-level reference head and finality checks. All 41 hosts are sampled every five minutes, including container image IDs, lifecycle, sync status, peers and execution height. Same-slot validated head differences are candidates for a persistent divergence check; differing finalized roots at the same epoch are recorded separately. A wall-clock head gap over three slots, finality lag over three epochs, or no finality advance for 15 minutes is recorded.

Every five minutes, bounded ClickHouse queries retain counts and up to five recent distinct examples per host and container for critical failures, Engine timeouts, lost duties and optimistic activation. Queries lag wall time by two minutes and replay five minutes for late ingestion. Saved count windows overlap and must not be summed. Log samples are selective and may omit incidents; collector failures are recorded separately. Logs arriving more than five minutes late can be missed.

Prometheus captures Besu heap fraction, GC time, payload latency, scrape health, available memory, CPU steal and gas used every five minutes. Besu checkpoint freshness, timer state, free disk and heap dump metadata are checked every five minutes. Heap dumps and raw JFR files remain private on their nodes. No client restarts or configuration changes are performed by this monitor. Watchtower deployments may cause image or container changes and require operational attribution.

The user systemd timer on the monitoring workstation survives the chat session, with login lingering enabled. It publishes sanitized captures to branch **{self.config['branch']}** hourly and on completion. It stops after the final ingestion catch-up at **{self.config['finish_after']}**. Health snapshots in the five-minute ingestion catch-up can extend beyond the requested window. A workstation outage creates a coverage gap; this does not send unattended alerts or file upstream issues.

[Machine readable summary](summary.json) includes exact event details and every missing slot. [Configuration](config.json) records the window and source baseline. The checked-in collector is [monitor.py](../../scripts/msf2-monitor/monitor.py).
'''
        (self.folder / 'README.md').write_text(text)

    def publish(self):
        prefix = 'md/msf-2-overnight-2026-10-13'
        command(['git', 'add', '--', prefix], cwd=self.repo)
        if command(['git', 'diff', '--cached', '--name-only'], cwd=self.repo).strip():
            # Dedicated worktree; still refuse accidental staging of unrelated work.
            staged = command(['git', 'diff', '--cached', '--name-only'], cwd=self.repo).splitlines()
            if any(not p.startswith(prefix + '/') for p in staged):
                raise RuntimeError('Unrelated staged files: publication refused')
            command(['git', 'commit', '-m', 'Record msf-2 overnight observations ' + self.stamp], timeout=90, cwd=self.repo)
        command(['git', 'push', 'origin', 'HEAD:refs/heads/' + self.config['branch']], timeout=90, cwd=self.repo)
        self.state['last_push'] = iso(self.now)

    def tick(self):
        if self.state.get('complete'):
            return
        if self.state.get('last_health_at') and (self.now - moment(self.state['last_health_at'])).total_seconds() > 180:
            self.event('collection_gap', 'collector', {'last_health_at': self.state['last_health_at'], 'seconds': (self.now - moment(self.state['last_health_at'])).total_seconds()}, '')
        full = not self.state['last_full'] or (self.now - moment(self.state['last_full'])).total_seconds() >= 280
        finished = self.now >= moment(self.config['finish_after'])
        if full or finished:
            self.read_nodes(True)
            self.read_profiles()
            self.read_metrics()
            self.read_logs()
            self.read_census()
            self.state['last_full'] = iso(self.now)
        else:
            self.read_nodes(False)
        self.state['cycle'] += 1
        self.report(finished)
        should_push = finished or not self.state['last_push'] or (self.now - moment(self.state['last_push'])).total_seconds() >= 3600
        if should_push:
            try:
                self.publish()
            except Exception as e:
                self.event('publication_error', 'collector', str(e), '')
                self.report(finished)
        # Failed final publication remains retryable on subsequent timer ticks.
        if finished and self.state.get('last_push') == iso(self.now):
            self.state['complete'] = True
        save(self.state_dir / 'state.json', self.state, sanitize=False)
        print(json.dumps({'at': iso(self.now), 'cycle': self.state['cycle'], 'full': full, 'validator_ok': self.state.get('validator_ok'), 'finalized': self.state.get('finalized'), 'event_groups': len(self.state['events']), 'complete': self.state.get('complete', False)}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--state-dir', type=Path, required=True)
    parser.add_argument('--no-publish', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    with (args.state_dir / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monitor = Monitor(args.repo, args.state_dir)
        if args.no_publish:
            monitor.publish = lambda: None
        try:
            monitor.tick()
        except Exception as e:
            monitor.event('collector_failure', 'collector', str(e), '')
            monitor.report()
            save(args.state_dir / 'state.json', monitor.state, sanitize=False)
            raise


if __name__ == '__main__':
    main()
