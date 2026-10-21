#!/usr/bin/env python3
"""Read back nine-worker node metrics without moving gateway credentials.

Uses an existing worker's Prometheus write identity for the same gateway's
read endpoint. Only metric values and labels leave the worker.
"""
import json
from pathlib import Path
import subprocess
import time

REMOTE = r'''
import base64,json,urllib.parse,urllib.request,yaml
from pathlib import Path
config=yaml.safe_load(Path('/data/prometheus/etc/prometheus.yml').read_text())
writer=config['remote_write'][0]
base='https://victoriametrics-public.analytics.production.platform.ethpandaops.io'
assert writer['url']==base+'/insert/1/prometheus'
auth=writer['basic_auth']
assert auth['username']=='glamsterdam-pbt-1'
token=base64.b64encode((auth['username']+':'+auth['password']).encode()).decode()
selector='up{ingress_user="glamsterdam-pbt-1",job="node"}'
responses={}
for label,query in (('up',selector),('sample_age_seconds','time()-timestamp('+selector+')')):
 url=base+'/select/1/prometheus/api/v1/query?'+urllib.parse.urlencode({'query':query})
 request=urllib.request.Request(url,headers={'Authorization':'Basic '+token,
                                            'User-Agent':'pbt-preparation-monitor/1.0'})
 with urllib.request.urlopen(request,timeout=30) as response:data=json.load(response)
 assert data['status']=='success' and not data.get('isPartial',False)
 responses[label]=data['data']['result']
print(json.dumps(responses))
'''


def main():
    private = Path.home() / '.local/state/pbt-1-run'
    hosts = json.loads((private / 'fleet/hosts.json').read_text())
    source = hosts['lighthouse-erigon-2']['ip']
    output = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '-i',
         str(Path.home() / '.ssh/devops_eth2_shared_key'),
         'root@' + source, 'python3 -'], input=REMOTE, text=True,
        capture_output=True, check=True, timeout=80)
    response = json.loads(output.stdout)
    expected = {'glamsterdam-pbt-1-' + host for host in hosts}
    up = {r['metric']['instance']: float(r['value'][1]) for r in response['up']}
    age = {r['metric']['instance']: float(r['value'][1])
           for r in response['sample_age_seconds']}
    problems = []
    for host in sorted(expected):
        if up.get(host) != 1:
            problems.append(host + ': missing or down')
        if not 0 <= age.get(host, float('inf')) < 180:
            problems.append(host + ': sample missing or older than 3 minutes')
    report = {
        'checked_at': time.time(),
        'scope': 'Central gateway node metrics only; EL/CL remain separate runtime checks',
        'status': 'passed' if not problems else 'failed', 'problems': problems,
        'workers': {host: {'up': up.get(host), 'sample_age_seconds': age.get(host)}
                    for host in sorted(expected)},
    }
    (private / 'monitoring-nine-worker-readback.json').write_text(
        json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    assert not problems, 'Central node metrics missing, down or stale'


if __name__ == '__main__':
    main()
