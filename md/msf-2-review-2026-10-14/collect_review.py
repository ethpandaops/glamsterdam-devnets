"""Read-only collection used for the October 14 review. Live re-runs capture new evidence."""
import concurrent.futures as cf,datetime as dt,importlib.util,json,pathlib,re,time
repo=pathlib.Path(__file__).resolve().parents[2];sp=importlib.util.spec_from_file_location('mon',repo/'scripts/msf2-monitor/monitor.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
root=repo/'md/msf-2-review-2026-10-14';ev=root/'evidence';network=json.loads((ev/'current-network.json').read_text());end=m.moment(network['at']);start=m.moment('2026-10-13T21:48:30+00:00');finalized=network['nodes'][m.REFERENCE]['finalized'];first=308
m.save(root/'window.json',{'start':m.iso(start),'end':m.iso(end),'previous_automatic_capture_end':'2026-10-14T08:05:01.721543+00:00','reviewed_log_end':m.iso(end),'first_census_epoch':first,'last_census_epoch':finalized,'method':'Preserved overnight samples plus retrospective canonical census and ClickHouse/Prometheus through current health snapshot; no continuous direct health capture after 08:05'})

def epoch(e):
 old=repo/f'md/msf-2-overnight-2026-10-13/evidence/epochs/{e}.json';p=ev/f'epochs/{e}.json'
 if old.exists() or p.exists():return e,'existing'
 d=m.ssh(m.REFERENCE,m.CENSUS,e,timeout=65)
 if 'error'in d or len(d.get('headers',[]))!=32 or any('error'in h for h in d.get('headers',[])):return e,{'error':d}
 m.save(p,d);return e,'captured'
with cf.ThreadPoolExecutor(max_workers=3) as pool:
 results=list(pool.map(epoch,range(402,finalized+1)))
m.save(ev/'census-collection-status.json',{'results':results,'captured_at':m.iso()})
print('CENSUS',len(results),'errors',sum(isinstance(x[1],dict)for x in results),flush=True)

def run_query(name,query):
 try:
  d=m.panda('clickhouse','query-raw','clickhouse-raw',query);m.save(ev/(name+'.json'),{'query':query,'result':d});return name,d
 except Exception as e:
  m.save(ev/(name+'.json'),{'query':query,'error':str(e)});return name,{'error':str(e)}
# Each interval is disjoint and bounded; aggregation avoids retaining broad log text.
patterns=m.PATTERNS.copy();patterns['critical']=r'OutOfMemoryError|Terminating due|\bFATAL\b|panic:|state root mismatch|INVALID_PAYLOAD|Invalid execution payload|block access list.*mismatch|BAL.*mismatch'
escaped={k:v.replace('\\','\\\\').replace("'","\\'") for k,v in patterns.items()}
category='multiIf('+','.join(f"match(Body,'{v}'),'{k}'"for k,v in escaped.items())+",'none')"
queries=[];lower=start
while lower<end:
 upper=min(lower+dt.timedelta(hours=1),end);fmt=lambda d:d.strftime('%Y-%m-%d %H:%M:%S')
 scope=f"ResourceAttributes['network']='{m.NETWORK}' AND ResourceAttributes['container.name'] IN ('execution','beacon','validator') AND Timestamp >= toDateTime('{fmt(lower)}') AND Timestamp < toDateTime('{fmt(upper)}')"
 q=f"SELECT ResourceAttributes['host.name'] AS host, ResourceAttributes['container.name'] AS container, {category} AS category, count() AS count, min(Timestamp) AS first_seen, max(Timestamp) AS last_seen, substring(argMax(Body,Timestamp),1,2000) AS latest_body FROM external.otel_logs WHERE {scope} AND category!='none' GROUP BY host,container,category ORDER BY category,host,container LIMIT 200 SETTINGS max_threads=2"
 queries.append(('log-counts-'+lower.strftime('%Y%m%dT%H%M%S'),q));lower=upper
with cf.ThreadPoolExecutor(max_workers=2) as pool:
 for name,result in pool.map(lambda x:run_query(*x),queries):print('LOGS',name,'rows',len(result.get('rows',[])),'error',result.get('error'),flush=True)
