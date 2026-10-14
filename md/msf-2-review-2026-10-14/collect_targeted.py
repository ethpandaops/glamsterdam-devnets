"""Read-only collection used for the October 14 review. Live re-runs capture new evidence."""
import importlib.util,pathlib,concurrent.futures as cf,json
repo=pathlib.Path(__file__).resolve().parents[2];sp=importlib.util.spec_from_file_location('m',repo/'scripts/msf2-monitor/monitor.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);ev=repo/'md/msf-2-review-2026-10-14/evidence'
queries={
'nimbus-missed-proposal-logs':"SELECT DISTINCT Timestamp,ResourceAttributes['host.name'] AS host,ResourceAttributes['container.name'] AS container,substring(Body,1,7000) AS Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name']='nimbus-reth-1' AND ResourceAttributes['container.name']='beacon' AND Timestamp>=toDateTime('2026-10-14 06:24:35') AND Timestamp<toDateTime('2026-10-14 06:37:10') AND match(Body,'12410|12469|Timeout while getting execution payload|Getting execution payload|No execution payload|Unable to|Block proposed') ORDER BY Timestamp ASC LIMIT 160 SETTINGS max_threads=2",
'lighthouse-fallback-logs':"SELECT DISTINCT Timestamp,ResourceAttributes['host.name'] AS host,ResourceAttributes['container.name'] AS container,substring(Body,1,7000) AS Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name']='lighthouse-reth-1' AND ResourceAttributes['container.name'] IN ('beacon','validator','execution') AND Timestamp>=toDateTime('2026-10-14 06:38:30') AND Timestamp<toDateTime('2026-10-14 06:39:00') AND NOT match(Body,'New LC optimistic header|TRACE|DEBUG|\"level\":\"debug\"') ORDER BY Timestamp ASC LIMIT 180 SETTINGS max_threads=2",
'prysm-besu-body-timeout':"SELECT DISTINCT Timestamp,ResourceAttributes['host.name'] AS host,ResourceAttributes['container.name'] AS container,substring(Body,1,7000) AS Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name']='prysm-besu-1' AND ResourceAttributes['container.name'] IN ('execution','beacon') AND Timestamp>=toDateTime('2026-10-14 02:31:00') AND Timestamp<toDateTime('2026-10-14 02:32:20') AND match(Body,'WARN|ERROR|timeout|Timeout|f5e4a143|payload|Payload') ORDER BY Timestamp ASC LIMIT 120 SETTINGS max_threads=2",
}
def collect(item):
 name,q=item
 try:d={'query':q,'result':m.panda('clickhouse','query-raw','clickhouse-raw',q)}
 except Exception as e:d={'query':q,'error':str(e)}
 m.save(ev/(name+'.json'),d);return name,len(d.get('result',{}).get('rows',[])),d.get('error')
with cf.ThreadPoolExecutor(max_workers=2)as pool:
 for x in pool.map(collect,queries.items()):print(x,flush=True)
for slot in (12410,12469,12479):
 try:d=m.panda('dora','slot',m.NETWORK,str(slot));m.save(ev/f'dora-slot-{slot}.json',d);print('DORA',slot,'saved',flush=True)
 except Exception as e:print('DORA',slot,str(e),flush=True)
