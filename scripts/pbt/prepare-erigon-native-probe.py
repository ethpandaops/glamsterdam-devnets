#!/usr/bin/env python3
"""Wait for the live checkpoint copy, revoke its key, then start one native trial."""
import fcntl
import json
from pathlib import Path
import shlex
import subprocess
import time

ROOT = Path.home()/'.local/state/pbt-1-run'
SOURCE = '164.92.239.96'
PROBE = '167.172.181.164'
COMMENT = 'pbt-1-erigon-checkpoint-probe-20261019'
SHA = 'b799a0df4b18dcbd5c662640eca94c6b3913027a43d1375dc8aceb4766c725ce'


def ssh(host, args, data=None):
    return subprocess.check_output(['ssh', '-i', str(Path.home()/'.ssh/devops_eth2_shared_key'),
        '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'root@'+host, shlex.join(args)],
        input=data, text=True, timeout=60).strip()


def save(value):
    target = ROOT/'native-probe-preparation.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2)+'\n')
    temporary.replace(target)


def main():
    lock = (ROOT/'native-probe-preparation.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (ROOT/'native-probe-preparation.json').exists(), 'Inspect prior preparation before retrying'
    metadata = json.loads((ROOT/'erigon-io-probe.json').read_text())
    assert metadata['public_ip'] == PROBE and metadata['private_ip'] == '10.35.0.6'
    started = time.time()
    deadline = time.monotonic()+7200
    while True:
        current = json.loads(ssh(PROBE, ['python3', '-c',
            "import json,subprocess;from pathlib import Path;"
            "p=Path('/data/pbt-1/io-probe/checkpoint-copy-status.json');"
            "u=subprocess.check_output(['systemctl','show','pbt-1-checkpoint-copy','-p','ActiveState','-p','MainPID','-p','Result'],text=True);"
            "print(json.dumps({'copy':json.loads(p.read_text()),'service':dict(x.split('=',1) for x in u.splitlines())}))"]))
        copied = current['copy']
        save({'phase': 'waiting_for_copy', 'started_at': started, 'time': time.time(), 'observed': current})
        if copied['phase'] == 'copied_verified':
            assert current['service']['ActiveState'] != 'failed'
            break
        assert copied['phase'] in ('copying', 'verifying'), current
        assert current['service']['ActiveState'] == 'active' and int(current['service']['MainPID']) > 0, current
        assert time.monotonic() < deadline, 'Copy still running after preparation wait bound; inspect without restarting it'
        time.sleep(30)
    assert copied['file_count'] == 179485 and copied['chaindata_sha256'] == SHA
    revocation = json.loads(ssh(SOURCE, ['python3', '-'], r'''
import json,os,time
from pathlib import Path
path=Path('/root/.ssh/authorized_keys')
comment='pbt-1-erigon-checkpoint-probe-20261019'
rows=path.read_text().splitlines(keepends=True)
matches=[row for row in rows if row.strip().endswith(' '+comment)]
assert len(matches)==1, 'Expected exactly one scoped checkpoint key; inspect access state'
line=matches[0]
assert 'from="10.35.0.6",restrict,command="/usr/bin/ionice -c 3 /usr/bin/rrsync -ro /data/pbt-1/checkpoints/erigon-before-maintenance-suppression"' in line
assert 'AAAAC3NzaC1lZDI1NTE5AAAAIMhHZLNN9zZH223ZjQeCr4N4Sl1aKj/Q8DZPJwrmDOp0' in line
remaining=[row for row in rows if row!=line]
assert len(remaining)==len(rows)-1 and remaining
tmp=path.with_name('authorized_keys.pbt-1-revoke.tmp')
fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,path.stat().st_mode&0o777)
with os.fdopen(fd,'w') as stream:
    stream.writelines(remaining);stream.flush();os.fsync(stream.fileno())
assert path.read_text()==''.join(rows), 'Access file changed concurrently; inspect before revoking'
tmp.replace(path)
assert path.read_text()==''.join(remaining)
proof={'time':time.time(),'source_host':'164.92.239.96','comment':comment,'matching_entries_before':1,'matching_entries_after':0}
Path('/data/pbt-1/pipeline/checkpoint-read-access-revoked.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))
'''))
    revocation['copy'] = copied
    proof = ssh(PROBE, ['python3', '-'],
        "import json;from pathlib import Path\n"
        "root=Path('/data/pbt-1/io-probe')\n"
        "proof=json.loads("+repr(json.dumps(revocation))+")\n"
        "for name in ('checkpoint-read-key','checkpoint-read-key.pub'):\n"
        "    path=root/name\n"
        "    if path.exists():path.unlink()\n"
        "assert not (root/'checkpoint-read-key').exists()\n"
        "proof['private_key_removed']=True\n"
        "(root/'checkpoint-read-access-revoked.json').write_text(json.dumps(proof,indent=2)+'\\n')\n"
        "print(json.dumps(proof))\n")
    revocation = json.loads(proof)
    (ROOT/'checkpoint-read-access-revoked.json').write_text(json.dumps(revocation, indent=2)+'\n')
    save({'phase': 'starting_native_profile', 'started_at': started, 'time': time.time(), 'revocation': revocation})
    result = ssh(PROBE, ['systemd-run', '--unit=pbt-1-native-probe-profile', '--property=Type=exec',
        'python3', '-u', '/data/pbt-1/probe-erigon-native.py', '--variant', 'profile', '--blocks', '64'])
    save({'phase': 'native_profile_started', 'started_at': started, 'time': time.time(),
        'revocation': revocation, 'unit': 'pbt-1-native-probe-profile', 'result': result})


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        path = ROOT/'native-probe-preparation.json'
        prior = json.loads(path.read_text()) if path.exists() else {}
        prior.update(phase='failed', time=time.time(), error=str(exc))
        save(prior)
        raise
