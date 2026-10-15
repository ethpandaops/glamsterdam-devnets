#!/usr/bin/env python3
"""Read-only MSF-2 fleet watch. Run on ethereum-node1; keep raw output private.

Every minute: all node heads/finality/optimism, process restarts, disk, and scrape
health. Every five minutes: common-height EL agreement and bounded error samples.
Dora missing/orphaned slots are matched to proposers, then logs are captured.
Events are observations requiring triage, never automatic client-bug verdicts.
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import time
import urllib.request

GENESIS = 1791810180
ANCHOR = 24452538
DORA = 'https://dora.glamsterdam-msf-2.ethpandaops.io'
ROOTS = ['number', 'hash', 'stateRoot', 'gasLimit']

REMOTE = r'''
import datetime,json,subprocess,urllib.request,os,re
errors={}
def get(port,path='/',data=None):
 try:
  q=urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
  return json.load(urllib.request.urlopen(q,timeout=3))
 except Exception as e:errors[str(port)+path]=str(e);return {}
def rpc(method,params):return get(8545,data={'jsonrpc':'2.0','id':1,'method':method,'params':params}).get('result')
b=rpc('eth_getBlockByNumber',['latest',False]) or {}
s=get(5052,'/eth/v1/node/syncing').get('data',{})
f=get(5052,'/eth/v1/beacon/states/head/finality_checkpoints').get('data',{})
raw=subprocess.run(['sudo','docker','inspect','execution','beacon','validator','buildoor'],capture_output=True,text=True,timeout=6)
cs=[]
try:
 for c in json.loads(raw.stdout):
  cs.append({'name':c['Name'].lstrip('/'),'image':c['Config']['Image'],'image_id':c['Image'],'restarts':c['RestartCount'],'state':{k:c['State'].get(k) for k in ['Status','Running','Restarting','OOMKilled','ExitCode','StartedAt','FinishedAt']}})
except Exception:pass
v=os.statvfs('/data')
metrics=get(9090,'/api/v1/targets').get('data',{}).get('activeTargets',[])
out={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'block':{k:b.get(k) for k in ['number','hash','stateRoot','gasLimit','gasUsed','timestamp']},'sync':s,'finality':f,'containers':cs,'disk_used_pct':round(100*(1-v.f_bavail/v.f_blocks),2),'targets':{'count':len(metrics),'down':[t.get('labels',{}).get('job') for t in metrics if t.get('health')!='up']},'errors':errors}
print(json.dumps(out))
'''
COMMON = r'''
import json,urllib.request
try:
 r=urllib.request.Request('http://127.0.0.1:8545',data=json.dumps({'jsonrpc':'2.0','id':1,'method':'eth_getBlockByNumber','params':[HEIGHT,False]}).encode(),headers={'Content-Type':'application/json'})
 b=json.load(urllib.request.urlopen(r,timeout=5)).get('result') or {}
 print(json.dumps({k:b.get(k) for k in ['number','hash','stateRoot','gasLimit']}))
except Exception as e:print(json.dumps({'error':str(e)}))
'''
LOGS = r'''
import subprocess,json,re,collections
pat=re.compile(r'OutOfMemory|Terminating due|\bPANIC\b|\bFATAL\b|\bCRIT\b|state.?root.*mismatch|invalid state.?root|invalid receipts.?root|invalid block.*access|Failed to produce block|No remote or self-built bid|NoViablePayloadBid|Block was broadcast too late|Timeout while getting execution payload|Local execution payload build failed|Unable to import execution payload',re.I)
def clean(s):
 s=re.sub(r'\x1b\[[0-9;]*m','',s)
 s=re.sub(r'(https?://)[^\s/@]+:[^\s/@]+@',r'\1[REDACTED]@',s)
 s=re.sub(r'(?i)((?:private[_ -]?key|mnemonic|password|jwtsecret|secret[_ -]?key)\s*[:=]\s*)[^\s,]+',r'\1[REDACTED]',s)
 s=re.sub(r'eyJ[A-Za-z0-9_.-]{30,}','[REDACTED]',s)
 return s[:2400]
out={}
for n in ['execution','beacon','validator','buildoor']:
 try:
  p=subprocess.run(['sudo','docker','logs','--timestamps','--since',SINCE,'--until',UNTIL,'--tail','25000',n],capture_output=True,text=True,timeout=6)
 except subprocess.TimeoutExpired:
  out[n]={'error':'Log collection exceeded 6 seconds; samples unavailable'};continue
 lines=(p.stdout+p.stderr).splitlines()
 if len(lines)==1 and 'No such container' in lines[0]:continue
 hits=[clean(s) for s in lines if (pat.search(s) or re.search(r'\b(?:ERROR|ERR|ERRO)\b',s)) and not re.search(r'\bDEBUG\b|\bDBG\b',s)]
 selected=[];counts=collections.Counter()
 for s in hits:
  k=re.sub(r'0x[0-9a-f]+|\d+','N',s[31:])[:180];counts[k]+=1
  if counts[k]<=3:selected.append(s)
 out[n]={'scanned_lines':len(lines),'tail_bound':25000,'matching_lines':len(hits),'samples':selected[:50],'tail':[clean(s) for s in lines[-2:]]}
print(json.dumps(out))
'''


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def write_json(path, value):
    tmp = path.with_suffix(path.suffix + '.new')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--key', type=Path, default=Path.home()/'.ssh/devops_eth2_shared_key')
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=True)
    hosts = dict(re.findall(r'^(\S+) .*?ansible_host=([\d.]+)', args.inventory.read_text(), re.M))
    if len(hosts) != 41:
        raise SystemExit(f'Expected 41 real-fleet hosts, found {len(hosts)}; refusing wrong inventory')
    statepath = args.output/'state.json'
    state = json.loads(statepath.read_text()) if statepath.exists() else {'conditions':{},'restart':{},'slots':{},'patterns':{},'cycle':0}
    journal = args.output/'OBSERVATIONS.md'
    if not journal.exists():
        journal.write_text('# MSF-2 monitoring observations\n\nAutomatic read-only observations; root causes require review. Known baseline: Besu heap pressure, Nimbus proposal timeouts, two stalled Nimbus EL sync nodes, Dora/API issues. Times are UTC.\n')

    def ssh(host, code):
        try:
            p = subprocess.run(['ssh','-i',str(args.key),'-o','BatchMode=yes','-o','StrictHostKeyChecking=no','-o','UserKnownHostsFile=/dev/null','-o','ConnectTimeout=5','devops@'+hosts[host],'python3 -'],input=code,capture_output=True,text=True,timeout=30)
            return json.loads(p.stdout) if p.returncode == 0 else {'error':f'SSH/probe exit {p.returncode}'}
        except Exception as e:
            return {'error':type(e).__name__+': '+str(e)[:160]}

    def batch(names, code):
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
            return dict(zip(names, pool.map(lambda h:ssh(h,code), names)))

    while not (args.output/'STOP').exists():
        started = time.monotonic()
        timestamp = utc()
        stamp = timestamp.replace(':','').replace('+0000','Z')
        cycle_dir = args.output/stamp
        cycle_dir.mkdir(exist_ok=True)
        events=[]
        def event(kind,subject,detail,evidence):
            e={'time':timestamp,'kind':kind,'subject':subject,'detail':detail,'evidence':str(evidence.relative_to(args.output))}
            events.append(e)
            with (args.output/'events.jsonl').open('a') as f:f.write(json.dumps(e)+'\n')
            with journal.open('a') as f:f.write(f"\n- **{timestamp} · {kind} · {subject}** — {detail} Evidence: `{e['evidence']}`.\n")
            print(json.dumps(e),flush=True)
        def condition(key,value,subject,detail,path):
            old=state['conditions'].get(key,False)
            state['conditions'][key]=bool(value)
            if value and not old:event('new condition',subject,detail,path)
            elif old and not value:event('recovered',subject,detail,path)

        fleet=batch(list(hosts),REMOTE)
        write_json(cycle_dir/'fleet.json',{'time':timestamp,'hosts':fleet})
        path=cycle_dir/'fleet.json'
        expected=int((time.time()-GENESIS)//12)
        stable=[r for h,r in fleet.items() if '-nimbusel-' not in h and r.get('block',{}).get('number')]
        top=max((int(r['block']['number'],16) for r in stable),default=0)
        finals=[int(r['finality']['finalized']['epoch']) for r in stable if r.get('finality',{}).get('finalized')]
        condition('finality',bool(finals) and expected//32-max(finals)>=4,'network',f'wall epoch {expected//32}, best finalized {max(finals) if finals else None}',path)
        capture=set()
        for h,r in fleet.items():
            before=len(events)
            condition(h+'/rpc',not bool(r.get('sync')) or not bool(r.get('block',{}).get('number')),h,'Host or CL/EL RPC unavailable/timed out (3-second HTTP deadline)' if r.get('error') or not r.get('sync') or not r.get('block',{}).get('number') else 'CL/EL RPC responding',path)
            s=r.get('sync',{})
            lag=expected-int(s.get('head_slot',0))
            condition(h+'/cl-lag',bool(s) and lag>3,h,f'CL head lag {lag} slots; head {s.get("head_slot")}',path)
            final=r.get('finality',{}).get('finalized',{}).get('epoch')
            condition(h+'/finality-unavailable',bool(s) and final is None,h,'Finality endpoint unavailable' if final is None else 'Finality endpoint responding',path)
            condition(h+'/finality-lag',final is not None and expected//32-int(final)>=4,h,f'Wall epoch {expected//32}, finalized {final}',path)
            if '-nimbusel-' not in h:
                height=int(r.get('block',{}).get('number') or '0x0',16)
                condition(h+'/el-lag',bool(height) and top-height>3,h,f'EL head {height}, highest sampled {top}',path)
                condition(h+'/optimistic',bool(s.get('is_optimistic') or s.get('el_offline')),h,f'optimistic={s.get("is_optimistic")}, el_offline={s.get("el_offline")}',path)
            else:
                height=int(r.get('block',{}).get('number') or '0x0',16)
                condition(h+'/known-sync-stall',bool(r.get('block')) and height==0,h,f'Known experimental sync status: execution head={height}',path)
            disk=r.get('disk_used_pct',0)
            condition(h+'/disk',disk>=90,h,f'Data filesystem {disk}% used',path)
            down=r.get('targets',{}).get('down',[])
            condition(h+'/metrics',bool(down),h,'Down scrape targets: '+str(down),path)
            for c in r.get('containers',[]):
                k=h+'/'+c['name'];v=(c['restarts'],c['state']['StartedAt'],c['image_id'])
                old=state['restart'].get(k)
                if old is not None and list(v)!=old:event('process changed',k,f'restarts={c["restarts"]}, started={c["state"]["StartedAt"]}, image={c["image"]}',path)
                state['restart'][k]=list(v)
                condition(k+'/down',not c['state']['Running'],k,'Container state '+c['state']['Status'],path)
            if len(events)>before:capture.add(h)

        # A one-minute delay avoids calling a still-in-flight proposal "missed".
        hi=max(0,expected-5);lo=max(0,hi-64)
        try:
            req=urllib.request.Request(DORA+f'/api/v1/slots?min_slot={lo}&max_slot={hi}&limit=1000',headers={'User-Agent':'Mozilla/5.0'})
            slots=json.load(urllib.request.urlopen(req,timeout=15))['data']['slots']
            write_json(cycle_dir/'slots.json',slots)
            for r in slots:
                slot=str(r['slot']);value=r['status']
                if state['slots'].get(slot)==value:continue
                old=state['slots'].get(slot);state['slots'][slot]=value
                if value in ('Missing','Orphaned') or old in ('Missing','Orphaned'):
                    # Already published slots remain baseline, not fresh alerts.
                    if int(slot)<=2367:continue
                    subject=r.get('proposer_name') or 'unknown proposer'
                    event('slot '+value.lower(),subject,f'slot {slot}; previous={old}; {DORA}/slot/{slot}',cycle_dir/'slots.json')
                    if subject in hosts:capture.add(subject)
            condition('dora-unavailable',False,'Dora','Slot API responding',cycle_dir/'slots.json')
        except Exception as e:
            write_json(cycle_dir/'dora-error.json',{'error':str(e)})
            condition('dora-unavailable',True,'Dora',str(e),cycle_dir/'dora-error.json')

        deep=state['cycle']%5==0
        if deep and top>ANCHOR:
            target=top-4
            agreement=batch([h for h in hosts if '-nimbusel-' not in h],COMMON.replace('HEIGHT',repr(hex(target))))
            write_json(cycle_dir/'agreement.json',{'height':target,'hosts':agreement})
            variants={tuple(r.get(k) for k in ROOTS[1:]) for r in agreement.values() if r.get('hash')}
            missing=[h for h,r in agreement.items() if not r.get('hash')]
            condition('divergence',len(variants)>1,'execution agreement',f'height {target}: {len(variants)} hash/state/gas variants, {len(missing)} unavailable',cycle_dir/'agreement.json')
            condition('agreement-unavailable',bool(missing),'execution agreement',f'height {target}: missing nodes {missing}',cycle_dir/'agreement.json')
            capture.update(hosts)
        if capture:
            since=state.get('last_deep',dt.datetime.fromtimestamp(time.time()-300,dt.timezone.utc).isoformat()) if deep else dt.datetime.fromtimestamp(time.time()-300,dt.timezone.utc).isoformat()
            code=LOGS.replace('SINCE',repr(since)).replace('UNTIL',repr(utc()))
            logs=batch(sorted(capture),code)
            write_json(cycle_dir/'logs.json',logs)
            for h,roles in logs.items():
                if 'error' in roles:continue
                for role,data in roles.items():
                    for s in data.get('samples',[]):
                        # Deduplicate repeat classes by node; retain updated raw samples every cycle.
                        body=s[31:]
                        body=re.sub(r'0x[0-9a-fA-F]+|\d+','N',body)
                        key=h+'/'+role+'/'+body[:140]
                        if key in state['patterns']:continue
                        state['patterns'][key]=timestamp
                        event('new log pattern',h+'/'+role,s[:650],cycle_dir/'logs.json')
            if deep:state['last_deep']=timestamp
        state['cycle']+=1
        state['slots']={s:v for s,v in state['slots'].items() if int(s)>=expected-256}
        state['last_complete']=utc()
        write_json(statepath,state)
        summary={'time':state['last_complete'],'cycle':state['cycle'],'wall_slot':expected,'best_el':top,'finalized':max(finals) if finals else None,'hosts_responding':sum(bool(r.get('sync')) for r in fleet.values()),'active_conditions':[k for k,v in state['conditions'].items() if v],'new_events':len(events),'evidence_directory':str(cycle_dir)}
        write_json(args.output/'latest.json',summary)
        print(json.dumps({'heartbeat':summary}),flush=True)
        if args.once:return
        time.sleep(max(1,args.interval-(time.monotonic()-started)))

if __name__=='__main__':main()
