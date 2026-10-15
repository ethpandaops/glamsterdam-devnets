"""Read-only canonical block sampling: one block every 25 blocks (~5 min).
Attribution uses public Spamoor wallet addresses and explicitly recorded targets.
No scenario inference from scheduling, calldata, fees or transaction value.
"""
import json,subprocess,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
EV=ROOT/'evidence'

def collect():
 senders={}
 for sid,addresses in json.loads((EV/'live-sender-attribution.json').read_text())['mapping'].items():
  for a in addresses:senders.setdefault(a,[]).append(int(sid))
 targets={}
 for x in json.loads((EV/'scenario-public-configuration.json').read_text()):
  a=x.get('fields',{}).get('target_address')
  if isinstance(a,str) and re.fullmatch(r'0x[0-9a-fA-F]{40}',a):targets.setdefault(a.lower(),[]).append(x['id'])
 # Captured public deployment addresses; no raw pod logs are published.
 logs=Path('/tmp/msf2-spamoor-private/pod.log')
 if logs.exists():
  for line in logs.read_text().splitlines():
   if 'deployed' not in line.lower():continue
   sid=re.search(r'spammer_id[=:](\d+)',line)
   if not sid:continue
   for a in re.findall(r'0x[0-9a-fA-F]{40}\b',line):
    # Limit to named deployment fields, not transaction hashes or factory addresses.
    if re.search(r'(?:deployed[^\"]*? at |(?:address|contract|run_code)[=:])'+re.escape(a),line):targets.setdefault(a.lower(),[]).append(int(sid.group(1)))
 targets={a:sorted(set(s)) for a,s in targets.items()}
 (EV/'public-target-attribution.json').write_text(json.dumps(targets,indent=2)+'\n')
 conf={'senders':senders,'targets':targets,'blocks':list(range(24452539,24467705,25))}
 remote=r'''
import json,urllib.request,concurrent.futures,time,collections
CFG=CONFIG

def one(n):
 time.sleep(.05)
 req=urllib.request.Request('http://127.0.0.1:8545',data=json.dumps({'jsonrpc':'2.0','id':1,'method':'eth_getBlockByNumber','params':[hex(n),True]}).encode(),headers={'Content-Type':'application/json'})
 try:
  b=json.load(urllib.request.urlopen(req,timeout=20))['result'];counts=collections.Counter();examples={};unknown=collections.Counter();conflict=0
  for tx in b['transactions']:
   s=CFG['senders'].get(tx['from'].lower(),[]);t=CFG['targets'].get((tx.get('to')or'').lower(),[])
   # Conflicting or ambiguous mappings remain unknown.
   ids=set(s)|set(t)
   sid=str(next(iter(ids))) if len(ids)==1 else 'unknown'
   if len(ids)>1:conflict+=1
   counts[sid]+=1
   if sid!='unknown' and sid not in examples:examples[sid]={'hash':tx['hash'],'from':tx['from'],'to':tx['to'],'method':'sender' if len(s)==1 else 'target'}
   if sid=='unknown':unknown[(tx.get('to')or'creation').lower()]+=1
  return {'number':n,'hash':b['hash'],'timestamp':int(b['timestamp'],16),'gas_used':int(b['gasUsed'],16),'tx_count':len(b['transactions']),'counts':dict(counts),'examples':examples,'conflicts':conflict,'unknown_targets':dict(unknown.most_common(3))}
 except Exception as e:return {'number':n,'error':str(e)[:150]}
with concurrent.futures.ThreadPoolExecutor(max_workers=2)as p:
 for row in p.map(one,CFG['blocks']):print(json.dumps(row),flush=True)
'''.replace('CONFIG',repr(conf))
 p=subprocess.Popen(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=8','glamsterdam-msf-2-nimbus-nethermind-1','python3','-'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 p.stdin.write(remote);p.stdin.close();rows=[]
 for line in p.stdout:
  rows.append(json.loads(line))
  if len(rows)%100==0:print('sampled',len(rows),flush=True)
 code=p.wait()
 if code:raise RuntimeError(p.stderr.read()[:300])
 (EV/'canonical-mined-samples.json').write_text(json.dumps({'method':'one canonical block every 25 block numbers; sender or explicit target matching; ambiguous/unknown retained','blocks':rows},indent=2)+'\n')
 print('complete',len(rows),'errors',sum('error'in r for r in rows),flush=True)
if __name__=='__main__':collect()
