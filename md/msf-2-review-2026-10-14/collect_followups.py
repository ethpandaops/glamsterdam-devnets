"""Read-only collection used for the October 14 review. Live re-runs capture new evidence."""
import pathlib,importlib.util,concurrent.futures as cf,json,datetime as dt
repo=pathlib.Path(__file__).resolve().parents[2];sp=importlib.util.spec_from_file_location('m',repo/'scripts/msf2-monitor/monitor.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);ev=repo/'md/msf-2-review-2026-10-14/evidence'
queries={
'grandine-reth-full-duty':"SELECT DISTINCT Timestamp,ResourceAttributes['container.name'] AS container,substring(Body,1,7000) AS Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name']='grandine-reth-1' AND ResourceAttributes['container.name'] IN ('beacon','validator','execution') AND Timestamp>=toDateTime('2026-10-14 14:27:30') AND Timestamp<toDateTime('2026-10-14 14:28:20') AND match(Body,'bid|payload|Payload|block_producer|WARN|ERROR|error') ORDER BY Timestamp ASC LIMIT 200 SETTINGS max_threads=2",
'afternoon-engine-stalls':"SELECT DISTINCT Timestamp,ResourceAttributes['host.name'] AS host,ResourceAttributes['container.name'] AS container,substring(Body,1,5000) AS Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name'] IN ('nimbus-besu-1','lighthouse-besu-1','nimbus-reth-1','grandine-reth-1','prysm-reth-1') AND ResourceAttributes['container.name'] IN ('beacon','execution') AND Timestamp>=toDateTime('2026-10-14 14:24:00') AND Timestamp<toDateTime('2026-10-14 14:34:00') AND match(Body,'(WARN|WRN|ERROR|ERR).*(timeout|Timeout|timed out|payload|Payload|sync)|Block imported|Imported block|Validated.*block') ORDER BY Timestamp ASC LIMIT 300 SETTINGS max_threads=2",
}
def collect(item):
 name,q=item
 try:d={'query':q,'result':m.panda('clickhouse','query-raw','clickhouse-raw',q)}
 except Exception as e:d={'query':q,'error':str(e)}
 m.save(ev/(name+'.json'),d);return name,len(d.get('result',{}).get('rows',[])),d.get('error')
with cf.ThreadPoolExecutor(max_workers=2)as pool:
 for x in pool.map(collect,queries.items()):print(x,flush=True)
for host,slot in [('lighthouse-reth-1',13157),('lighthouse-besu-1',14812)]:
 at=dt.datetime.fromtimestamp(1791810180+slot*12,m.UTC);fmt=lambda d:d.strftime('%Y-%m-%d %H:%M:%S')
 q=f"SELECT DISTINCT Timestamp,ResourceAttributes['container.name'] AS container,substring(Body,1,7000) AS Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name']='{host}' AND ResourceAttributes['container.name'] IN ('beacon','validator') AND Timestamp>=toDateTime('{fmt(at-dt.timedelta(seconds=5))}') AND Timestamp<toDateTime('{fmt(at+dt.timedelta(seconds=6))}') AND match(Body,'bid|Bid|payload|Payload|published block|Execution engine call failed') ORDER BY Timestamp ASC LIMIT 80 SETTINGS max_threads=2"
 d=m.panda('clickhouse','query-raw','clickhouse-raw',q);m.save(ev/f'lighthouse-fallback-slot-{slot}.json',{'query':q,'result':d});m.save(ev/f'dora-slot-{slot}.json',m.panda('dora','slot',m.NETWORK,str(slot)));print('LH fallback',slot,len(d['rows']),flush=True)
