"""Build offline interactive and Matplotlib charts from sanitized evidence."""
import ast,csv,datetime as dt,json,collections
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import to_hex
ROOT=Path(__file__).resolve().parent;EV=ROOT/'evidence'
START=1791810180;END=1791996228
CLIENTS=['Besu','erigon','ethrex','go-ethereum','Nethermind','Reth']
COLORS=dict(zip(CLIENTS,['#d95f02','#7570b3','#1b9e77','#e7298a','#2385b7','#947000']))
LABELS={10:'Regular chain load (group)',30:'Fuzzing (group)',100:'CREATE2 64 KiB deployment',101:'JUMPDEST CALL',102:'Cold EXTCODEHASH',103:'Cold CALL',104:'Transfer diff-max64k (deleted)',105:'Transfer JUMPDEST (deleted)',106:'Transfer diff-max64k · value 0',107:'Transfer diff-max64k · value 1',108:'Transfer JUMPDEST · value 0',109:'Transfer JUMPDEST · value 1',110:'Cold value-bearing CALL',111:'SLOAD · configuration changed',112:'SLOAD empty slots',113:'Max code deployment',114:'SELFDESTRUCT / creation',115:'SSTORE zero → nonzero',116:'TSTORE none / hit / miss'}
def rows(path):
 d=json.loads(path.read_text())['result'];return [dict(zip(d['columns'],r))for r in d['rows']]
def stamp(s):return int(dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp())
def date(t):return dt.datetime.fromtimestamp(t,dt.timezone.utc)
def build():
 timings=[]
 for p in sorted(EV.glob('timings-*.json')):
  for r in rows(p):
   timings.append({'t':stamp(r['time']),'client':r['client'],'status':r['status'],**{k:int(r[k])for k in ['calls','nodes','blocks','p50_ms','p95_ms','max_ms']},'mean_gas':round(float(r['mean_gas'])),'versions':ast.literal_eval(r['versions'])})
 assert len({(r['t'],r['client'],r['status'])for r in timings})==len(timings)
 audits=json.loads((EV/'scenario-audit-events.json').read_text());open_runs={};runs=[];names={}
 for a in sorted(audits,key=lambda a:(a['timestamp'],a['id'])):
  if not a['entity_id'].isdigit():continue
  sid=int(a['entity_id']);t=a['timestamp'];names[sid]=a['entity_name']
  if a['action_type']=='spammer_start':
   if sid in open_runs:runs.append({'id':sid,'start':open_runs.pop(sid),'end':t})
   open_runs[sid]=t
  if a['action_type'] in ['spammer_pause','spammer_delete'] and sid in open_runs:runs.append({'id':sid,'start':open_runs.pop(sid),'end':t})
 for sid,t in open_runs.items():runs.append({'id':sid,'start':t,'end':END,'open_at_cutoff':True})
 runs=[r for r in runs if r['end']>START and r['start']<END]
 for r in runs:r['start']=max(r['start'],START);r['end']=min(r['end'],END)
 ids=sorted(set(r['id']for r in runs));scenario_palette=[to_hex(plt.get_cmap('tab20')(i))for i in range(20)if i not in (14,15)];palette={str(s):scenario_palette[i%len(scenario_palette)]for i,s in enumerate(ids)};palette['unknown']='#c5c8cd'
 blocks=json.loads((EV/'canonical-mined-samples.json').read_text())['blocks']
 assert all('error'not in b and sum(b['counts'].values())==b['tx_count']for b in blocks)
 comp=[]
 for r in rows(EV/'scenario-client-comparison.json'):
  comp.append({'id':int(r['scenario_id']),'client':r['client'],'status':r['status'],**{k:int(r[k])for k in ['calls','blocks','nodes','p50_ms','p95_ms','max_ms']},'versions':ast.literal_eval(r['versions'])})
 total=sum(b['tx_count']for b in blocks);unknown=sum(b['counts'].get('unknown',0)for b in blocks)
 data={'start':START,'end':END,'clients':CLIENTS,'colors':COLORS,'scenario_colors':palette,'labels':{str(s):LABELS.get(s,names.get(s,str(s)))for s in ids},'names':{str(s):names.get(s,LABELS.get(s,str(s)))for s in ids},'runs':runs,'timings':timings,'samples':[{k:b[k]for k in ['number','hash','timestamp','gas_used','tx_count','counts','conflicts']}for b in blocks],'comparison':comp,'updates':json.loads((EV/'configuration-change-markers.json').read_text()),'sample_tx_count':total,'sample_known_percent':round(100*(total-unknown)/total,1)}
 (ROOT/'chart-data.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
 packed=dict(data);packed['timing_keys']=list(timings[0]);packed['timings']=[[r[k]for k in packed['timing_keys']]for r in timings]
 template=(ROOT/'chart-template.html').read_text();(ROOT/'msf-2-spamoor-newpayload.html').write_text(template.replace('__DATA__',json.dumps(packed,separators=(',',':'))))
 with (ROOT/'newpayload-5min.csv').open('w')as f:
  w=csv.DictWriter(f,fieldnames=['time_utc','client','status','calls','nodes','blocks','p50_ms','p95_ms','max_ms','mean_gas','versions'],lineterminator='\n');w.writeheader()
  for r in timings:w.writerow({'time_utc':date(r['t']).isoformat(),**{k:v for k,v in r.items()if k!='t'}})
 with (ROOT/'scenario-runs.csv').open('w')as f:
  w=csv.writer(f,lineterminator='\n');w.writerow(['scenario_id','label','start_utc','end_utc','basis'])
  for r in runs:w.writerow([r['id'],data['labels'][str(r['id'])],date(r['start']).isoformat(),date(r['end']).isoformat(),'scheduler audit; submission interval, not mined attribution'])
 fig,axes=plt.subplots(3,1,figsize=(16,13),sharex=True,gridspec_kw={'height_ratios':[3,5,1.5]},layout='constrained')
 ax=axes[0]
 for c in CLIENTS:
  rr=sorted((r for r in timings if r['client']==c and r['status']=='VALID'),key=lambda r:r['t']);ax.plot([date(r['t'])for r in rr],[max(.1,r['p95_ms'])for r in rr],lw=1.05,color=COLORS[c],label={'go-ethereum':'Geth','erigon':'Erigon','ethrex':'Ethrex'}.get(c,c))
 ax.set_yscale('log');ax.set_ylabel('newPayload RPC p95 (ms)\nVALID responses · 5-minute bins');ax.grid(alpha=.2);ax.legend(ncol=6,loc='upper left');ax.set_title('glamsterdam-msf-2 · Spamoor scenarios and client newPayload latency\n12–14 October 2026 UTC · standard 36 validator nodes',loc='left',fontsize=17)
 ax=axes[1]
 for r in runs:
  y=ids.index(r['id']);ax.barh(y,(r['end']-r['start'])/86400,left=mdates.date2num(date(r['start'])),height=.65,color=palette[str(r['id'])])
 ax.set_yticks(range(len(ids)),[f'#{s}  {data["labels"][str(s)]}'for s in ids],fontsize=9);ax.invert_yaxis();ax.grid(axis='x',alpha=.2);ax.set_ylabel('Recorded submission intervals\nSpamoor start/pause audit')
 ax=axes[2]
 # Exactly one sampled canonical block per 25 block numbers; fractions are tx count.
 for b in blocks:
  left=mdates.date2num(date(b['timestamp']));bottom=0
  for sid,n in sorted(b['counts'].items()):
   v=100*n/max(1,b['tx_count']);ax.bar(left,v,width=240/86400,bottom=bottom,color=palette.get(sid,'#c5c8cd'),align='center',linewidth=0);bottom+=v
 ax.set_ylim(0,100);ax.set_ylabel('Sampled mined mix\n% of transaction count');ax.xaxis.set_major_locator(mdates.HourLocator(interval=6));ax.xaxis.set_major_formatter(mdates.DateFormatter('%d Oct\n%H:%M',tz=dt.timezone.utc));ax.set_xlim(date(START),date(END));ax.set_xlabel(f'UTC · {len(blocks)} canonical block samples · {data["sample_known_percent"]}% of sampled transactions attributed · grey = unknown\nRecorded runs may overlap or leave queued transactions after pause. RPC time includes client behavior; SYNCING is excluded here.\nComparisons across implementations are observational; client response semantics and client versions differ.',fontsize=10)
 fig.savefig(ROOT/'msf-2-spamoor-newpayload.png',dpi=120);fig.savefig(ROOT/'msf-2-spamoor-newpayload.svg');plt.close(fig)
 svg=ROOT/'msf-2-spamoor-newpayload.svg';svg.write_text('\n'.join(line.rstrip()for line in svg.read_text().splitlines())+'\n')
 print({'timing_bins':len(timings),'runs':len(runs),'sampled_blocks':len(blocks),'attributed_percent':data['sample_known_percent'],'comparison_rows':len(comp)})
if __name__=='__main__':build()
