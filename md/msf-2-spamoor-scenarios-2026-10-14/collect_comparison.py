"""Exact RPC quantiles for independently attributed sampled canonical blocks."""
import json,collections,subprocess
from pathlib import Path
from collect_timings import NODE_FILTER
ROOT=Path(__file__).resolve().parent;EV=ROOT/'evidence'
def collect():
 groups=collections.defaultdict(list)
 for b in json.loads((EV/'canonical-mined-samples.json').read_text())['blocks']:
  known=[(int(n),k)for k,n in b['counts'].items()if k!='unknown']
  if known:
   n,sid=max(known)
   if n/max(1,b['tx_count'])>=.9:groups[sid].append(b['hash'])
 args=[]
 for sid,hashes in sorted(groups.items(),key=lambda x:int(x[0])):
  args.extend(["block_hash IN ("+','.join(repr(h)for h in hashes)+")",repr(sid)])
 label='multiIf('+','.join(args)+",'unknown')"
 hashes=[h for a in groups.values()for h in a]
 query=f"""SELECT {label} AS scenario_id,meta_execution_implementation AS client,status,count() AS calls,uniqExact(block_hash) AS blocks,uniqExact(meta_client_name) AS nodes,quantileExact(0.5)(duration_ms) AS p50_ms,quantileExact(0.95)(duration_ms) AS p95_ms,max(duration_ms) AS max_ms,groupUniqArray(meta_execution_version) AS versions FROM (SELECT DISTINCT block_hash,requested_date_time,meta_client_name,meta_execution_implementation,meta_execution_version,status,duration_ms FROM `glamsterdam-msf-2`.execution_engine_new_payload WHERE meta_network_name='glamsterdam-msf-2' AND block_number>=24452539 AND block_number<24467705 AND block_hash IN ({','.join(repr(h)for h in hashes)}) AND requested_date_time>=toDateTime('2026-10-12 13:03:00') AND requested_date_time<toDateTime('2026-10-14 16:43:48') AND source='ENGINE_SOURCE_SNOOPER' AND {NODE_FILTER}) GROUP BY scenario_id,client,status ORDER BY scenario_id,client,status LIMIT 500 SETTINGS max_threads=2"""
 p=subprocess.run(['panda','-o','json','clickhouse','query-raw','clickhouse-raw',query],capture_output=True,text=True,timeout=90)
 if p.returncode:raise RuntimeError(p.stderr[-300:])
 d={'method':'Exact quantiles of deduplicated RPC calls on sampled canonical blocks with at least 90% of transaction count mapped to one scenario. Not gas dominance or a controlled experiment.','eligible_block_counts':{k:len(v)for k,v in groups.items()},'query':query,'result':json.loads(p.stdout)}
 (EV/'scenario-client-comparison.json').write_text(json.dumps(d,indent=2)+'\n');print('rows',len(d['result']['rows']))
if __name__=='__main__':collect()
