"""Read-only collection used for the October 14 review. Live re-runs capture new evidence."""
import importlib.util,pathlib,concurrent.futures as cf,json,datetime as dt
repo=pathlib.Path(__file__).resolve().parents[2];sp=importlib.util.spec_from_file_location('m',repo/'scripts/msf2-monitor/monitor.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);ev=repo/'md/msf-2-review-2026-10-14/evidence';end=json.loads((ev/'current-network.json').read_text())['at'];start='2026-10-13T21:48:30+00:00'
sel='network="glamsterdam-msf-2"'
queries={
'besu-heap':f'jvm_memory_used_bytes{{{sel},job="execution",execution_client="besu",area="heap"}} / jvm_memory_max_bytes{{{sel},job="execution",execution_client="besu",area="heap"}}',
'besu-gc':f'sum by(instance) (rate(jvm_gc_collection_seconds_sum{{{sel},job="execution",execution_client="besu"}}[5m]))',
'workload-gas':f'avg by(execution_client) (eth_exe_block_head_gas_used{{{sel}}})',
'cpu-steal':f'avg by(instance) (rate(node_cpu_seconds_total{{{sel},mode="steal"}}[5m]))',
'available-memory':f'node_memory_MemAvailable_bytes{{{sel}}}',
}
def collect(item):
 name,q=item;args=['prometheus','query-range','devnets',q,'--start',start,'--end',end,'--step','5m']
 try:d={'command':['panda','-o','json',*args],'result':m.panda(*args)}
 except Exception as e:d={'command':args,'error':str(e)}
 m.save(ev/f'{name}-history.json',d);return name,len(d.get('result',{}).get('data',{}).get('result',[])),d.get('error')
with cf.ThreadPoolExecutor(max_workers=3)as pool:
 for x in pool.map(collect,queries.items()):print(x,flush=True)
windows="((Timestamp>=toDateTime('2026-10-14 06:24:56') AND Timestamp<toDateTime('2026-10-14 06:25:06')) OR (Timestamp>=toDateTime('2026-10-14 06:36:44') AND Timestamp<toDateTime('2026-10-14 06:36:54')))"
q=f"SELECT DISTINCT Timestamp,ResourceAttributes['host.name'] AS host,ResourceAttributes['container.name'] AS container,substring(Body,1,7000) AS Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name']='nimbus-reth-1' AND ResourceAttributes['container.name']='beacon' AND {windows} AND match(Body,'Execution payload bid validated|First bid for this slot|Timeout while getting|getPayload|Getting execution payload|No execution payload|Unable to propose|Sending proposal fcU|Block proposed|Failed.*proposal') ORDER BY Timestamp ASC LIMIT 80 SETTINGS max_threads=2"
d=m.panda('clickhouse','query-raw','clickhouse-raw',q);m.save(ev/'nimbus-two-misses-focused.json',{'query':q,'result':d});print('Nimbus focused',len(d['rows']),flush=True)
q=f"SELECT DISTINCT Timestamp,ResourceAttributes['host.name'] AS host,substring(Body,1,7000) AS Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name'] IN ('nimbus-reth-1','lighthouse-reth-1') AND ResourceAttributes['container.name']='execution' AND ({windows} OR (Timestamp>=toDateTime('2026-10-14 06:38:42') AND Timestamp<toDateTime('2026-10-14 06:38:57'))) AND match(Body,'payload|Payload|WARN|ERROR') ORDER BY Timestamp ASC LIMIT 120 SETTINGS max_threads=2"
d=m.panda('clickhouse','query-raw','clickhouse-raw',q);m.save(ev/'reth-local-payload-jobs.json',{'query':q,'result':d});print('Reth jobs',len(d['rows']),flush=True)
