"""Read-only, bounded newPayload aggregation over the whole msf-2 run."""
import concurrent.futures as cf
import datetime as dt
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parent
EV=ROOT/'evidence'
FIRST,LAST=24452539,24467704
PREFIX='ethpandaops/devnets/glamsterdam-msf-2-'
# Standard validator matrix only: exclude bootnode, builders and cold-sync observers.
NODE_FILTER="match(meta_client_name,'glamsterdam-msf-2-(grandine|lighthouse|lodestar|nimbus|prysm|teku)-(besu|erigon|ethrex|geth|nethermind|reth)-1$')"

def collect(pair):
 lo,hi=FIRST,LAST+1
 begin,finish=pair
 finish=min(finish,'2026-10-14 16:43:48')
 query=f"""SELECT toStartOfInterval(requested_date_time,INTERVAL 5 MINUTE) AS time, meta_execution_implementation AS client, status, count() AS calls, uniqExact(meta_client_name) AS nodes, uniqExact(block_hash) AS blocks, quantileExact(0.5)(duration_ms) AS p50_ms, quantileExact(0.95)(duration_ms) AS p95_ms, max(duration_ms) AS max_ms, avg(gas_used) AS mean_gas, groupUniqArray(meta_execution_version) AS versions FROM (SELECT DISTINCT block_hash, requested_date_time, meta_client_name, meta_execution_implementation,meta_execution_version,status,duration_ms,gas_used FROM `glamsterdam-msf-2`.execution_engine_new_payload WHERE meta_network_name='glamsterdam-msf-2' AND block_number>={lo} AND block_number<{hi} AND requested_date_time>=toDateTime('{begin}') AND requested_date_time<toDateTime('{finish}') AND source='ENGINE_SOURCE_SNOOPER' AND {NODE_FILTER}) GROUP BY time,client,status ORDER BY time,client,status LIMIT 3000 SETTINGS max_threads=2"""
 path=EV/('timings-'+begin.replace('-','').replace(' ','T').replace(':','')+'.json')
 if path.exists() and 'result'in json.loads(path.read_text()):return lo,'existing'
 p=subprocess.run(['panda','-o','json','clickhouse','query-raw','clickhouse-raw',query],capture_output=True,text=True,timeout=60)
 if p.returncode:
  d={'query':query,'error':p.stderr[-300:]}
 else:d={'query':query,'result':json.loads(p.stdout)}
 path.write_text(json.dumps(d,indent=2)+'\n')
 return lo,len(d.get('result',{}).get('rows',[])),d.get('error')
if __name__=='__main__':
 times=[dt.datetime(2026,10,12,12)+dt.timedelta(hours=12*i)for i in range(6)];pairs=[(a.strftime('%Y-%m-%d %H:%M:%S'),b.strftime('%Y-%m-%d %H:%M:%S'))for a,b in zip(times,times[1:])]
 with cf.ThreadPoolExecutor(max_workers=2)as pool:
  for r in pool.map(collect,pairs):print(r,flush=True)
