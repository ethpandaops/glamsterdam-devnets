"""Read-only collection used for the October 14 review. Live re-runs capture new evidence."""
import importlib.util,pathlib,concurrent.futures as cf,json,datetime as dt
repo=pathlib.Path(__file__).resolve().parents[2];sp=importlib.util.spec_from_file_location('m',repo/'scripts/msf2-monitor/monitor.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);ev=repo/'md/msf-2-review-2026-10-14/evidence';c=json.loads((ev/'combined-census.json').read_text())
def collect(miss):
 slot=miss['slot'];at=dt.datetime.fromtimestamp(1791810180+slot*12,m.UTC);fmt=lambda d:d.strftime('%Y-%m-%d %H:%M:%S')
 # Nimbus verbosity needs a selective message filter; keep all warnings/proposal lifecycle messages.
 pattern=r'Execution payload bid validated|First bid for this slot|Timeout while getting|getPayload|Getting execution payload|No execution payload|Unable to propose|Sending proposal fcU|Block proposed|Failed.*proposal|WARN|WRN|ERROR|ERR|Proposal|proposal|[Pp]ropos.*block|[Bb]lock.*propos'
 escaped=pattern.replace('\\','\\\\').replace("'","\\'")
 q=f"SELECT DISTINCT Timestamp,ResourceAttributes['host.name'] AS host,ResourceAttributes['container.name'] AS container,substring(Body,1,7000) AS Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name']='{miss['host']}' AND ResourceAttributes['container.name'] IN ('beacon','validator') AND Timestamp>=toDateTime('{fmt(at-dt.timedelta(seconds=4))}') AND Timestamp<toDateTime('{fmt(at+dt.timedelta(seconds=15))}') AND match(Body,'{escaped}') ORDER BY Timestamp ASC LIMIT 100 SETTINGS max_threads=2"
 try:d={'slot':slot,'slot_start':m.iso(at),'query':q,'result':m.panda('clickhouse','query-raw','clickhouse-raw',q)}
 except Exception as e:d={'query':q,'error':str(e)}
 m.save(ev/f'missed-slot-{slot}-logs.json',d)
 try:m.save(ev/f'dora-slot-{slot}.json',m.panda('dora','slot',m.NETWORK,str(slot)))
 except Exception as e:print('DORA ERROR',slot,str(e),flush=True)
 return slot,len(d.get('result',{}).get('rows',[])),d.get('error')
with cf.ThreadPoolExecutor(max_workers=2)as pool:
 for x in pool.map(collect,c['misses']):print('MISS',x,flush=True)
# Backfill a Nimbus-specific failure phrase absent from the first monitor's regex.
start=m.moment('2026-10-13T21:48:30+00:00');end=m.moment(json.loads((ev/'current-network.json').read_text())['at']);lower=start
while lower<end:
 upper=min(lower+dt.timedelta(hours=2),end);fmt=lambda d:d.strftime('%Y-%m-%d %H:%M:%S')
 q=f"SELECT ResourceAttributes['host.name'] AS host,count() AS count,min(Timestamp) AS first_seen,max(Timestamp) AS last_seen,substring(argMax(Body,Timestamp),1,2000) AS latest_body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['container.name']='beacon' AND Timestamp>=toDateTime('{fmt(lower)}') AND Timestamp<toDateTime('{fmt(upper)}') AND match(Body,'Timeout while getting execution payload|no local.*payload|No local.*payload') GROUP BY host ORDER BY host LIMIT 50 SETTINGS max_threads=2"
 try:d={'query':q,'result':m.panda('clickhouse','query-raw','clickhouse-raw',q)}
 except Exception as e:d={'query':q,'error':str(e)}
 m.save(ev/('nimbus-timeout-counts-'+lower.strftime('%Y%m%dT%H%M%S')+'.json'),d);print('NIMBUS TIMEOUT',lower.isoformat(),d.get('result',{}).get('rows',[]),d.get('error'),flush=True);lower=upper
