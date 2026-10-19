#!/usr/bin/env python3
"""Stream verified raw chunks through the controller without storing a second copy."""
import fcntl
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import time

from monitor import HOSTS

ROOT = Path.home()/'.local/state/pbt-1-run'
REMOTE = '/data/pbt-1/raw-stream'
IDENTITY = str(Path.home()/'.ssh/devops_eth2_shared_key')


def ssh(client, args):
    return ['ssh', '-i', IDENTITY, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
            'root@'+HOSTS[client][0], shlex.join(args)]


def remote(client, code, *args):
    return subprocess.check_output(ssh(client, ['python3', '-c', code, *args]), text=True, timeout=60).strip()


def save(result):
    path = ROOT/'raw-relay-status.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'time': time.time(), **result})+'\n')
    temp.replace(path)


VERIFY = '''import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]); want=int(sys.argv[2]); m=json.loads((p/'manifest.json').read_text())
assert m['start']==want and 1<=m['end']-want+1<=256
assert [x['name'] for x in m['files']]==[f'{n:08d}.json.gz' for n in range(want,m['end']+1)]
for x in m['files']:
    with (p/x['name']).open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==x['sha256'], x['name']
print(json.dumps({'start':want,'end':m['end'],'files':len(m['files'])}))
'''


def transfer(low):
    name = f'{low:08d}'
    target = REMOTE+'/'+name
    incoming = target+'.incoming'
    exists = remote('erigon', 'from pathlib import Path;import sys;print(int(Path(sys.argv[1]).exists()))', target)
    if exists == '1':
        return json.loads(remote('erigon', VERIFY, target, str(low)))
    remote('erigon', 'from pathlib import Path;import sys;Path(sys.argv[1]).mkdir(parents=True)', incoming)
    # Both SSH sessions originate on the controller. No administrative keys or
    # archive files are placed on either peer for the transfer.
    with tempfile.TemporaryFile() as errors:
        source = subprocess.Popen(ssh('geth', ['tar', '-C', target, '-cf', '-', '.']),
                                  stdout=subprocess.PIPE, stderr=errors)
        sink = subprocess.Popen(ssh('erigon', ['tar', '-C', incoming, '-xf', '-']),
                                stdin=source.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        source.stdout.close()
        try:
            _, stderr = sink.communicate(timeout=600)
            source_code = source.wait(timeout=60)
            assert sink.returncode == 0, stderr.decode()
            assert source_code == 0, 'Inspect source SSH transfer failure'
        finally:
            for process in (sink, source):
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=30)
    report = json.loads(remote('erigon', VERIFY, incoming, str(low)))
    remote('erigon', 'from pathlib import Path;import sys;a,b=map(Path,sys.argv[1:]);assert not b.exists();a.rename(b)', incoming, target)
    return report


def main():
    lock = (ROOT/'raw-relay.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    request = json.loads(remote('geth', 'from pathlib import Path;print(Path("'+REMOTE+'/request.json").read_text())'))
    low = request['start']
    assert request['chunk_size'] == 256
    remote('erigon', 'from pathlib import Path;import sys;p=Path(sys.argv[1]);p.mkdir(exist_ok=True);r=p/"request.json";v=sys.argv[2];assert not r.exists() or r.read_text()==v;r.write_text(v)', REMOTE, json.dumps(request))
    while low <= request['end']:
        available = remote('geth', 'from pathlib import Path;import sys;print(int(Path(sys.argv[1]).exists()))', REMOTE+f'/{low:08d}/manifest.json')
        if available != '1':
            export = json.loads(remote('geth', 'from pathlib import Path;print(Path("'+REMOTE+'/status.json").read_text())'))
            assert export['phase'] != 'failed', export
            save({'phase': 'waiting_for_chunk', 'next': low, 'end': request['end']})
            time.sleep(10)
            continue
        save({'phase': 'transferring', 'next': low, 'end': request['end']})
        report = transfer(low)
        assert report['end'] == min(low+255, request['end'])
        low = report['end']+1
        save({'phase': 'transferred', 'last': low-1, 'end': request['end']})
    result = {'phase': 'complete', **request, 'verified_files': request['end']-request['start']+1}
    remote('erigon', 'from pathlib import Path;import sys;p=Path(sys.argv[1]);t=p.with_suffix(".tmp");t.write_text(sys.argv[2]);t.replace(p)', REMOTE+'/complete.json', json.dumps(result))
    save(result)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        save({'phase': 'failed', 'error': str(exc)})
        raise
