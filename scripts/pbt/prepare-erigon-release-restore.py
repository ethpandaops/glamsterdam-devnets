#!/usr/bin/env python3
"""Assemble the verified H restore inputs; --stage copies them, never starts jobs."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import time

from erigon_verified_restore import KEY, validate_bundle
from storage import BUCKET, client

HERE = Path(__file__).resolve().parent
ROOT = Path.home() / '.local/state/pbt-1-run/v3-head-restore'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-i',
       str(Path.home() / '.ssh/devops_eth2_shared_key')]

RECOVERY_PREFLIGHT = '''import json,pathlib,shutil,socket,sys
x=json.load(sys.stdin);root=pathlib.Path('/data/pbt-1/v3-head-recovery')
assert socket.gethostname()=='glamsterdam-pbt-1-lighthouse-erigon-2'
assert root.parent.resolve()==root.parent and not root.exists() and not root.is_symlink()
assert shutil.disk_usage(root.parent).free >= x['bundle']['metadata']['archive_bytes']+150_000_000_000+4*64*1024**2
proof=json.loads((root.parent/'qualification/result.json').read_text())
assert proof==x['bundle']['peer']['proof'], 'Worker qualification changed'
'''


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def remote(host, code, payload=None):
    return subprocess.check_output(SSH + ['root@' + host, shlex.join(['python3', '-c', code])],
                                   input=json.dumps(payload).encode() if payload is not None else None,
                                   stderr=subprocess.PIPE, timeout=90)


def stopped_source(job):
    # Keep the existing qualification/conversion locks held throughout measurement.
    code = r'''import hashlib,importlib.util,json,os,pathlib,stat,sys,time
base=pathlib.Path('/data/pbt-1');path=base/'upload-v3-head-stream.py'
assert hashlib.sha256(path.read_bytes()).hexdigest()=='845930d1580e0a24117e382e8a4d808e3ac142197fbedb3c7b61b91442fe95d9'
sys.path.insert(0,str(base))
s=importlib.util.spec_from_file_location('stream',path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.ROOT=base/'v3-head-publication'
job=json.load(sys.stdin);db,locks=m.require_v3_head_source(job)
excluded={x[len('--exclude=./'):] for x in m.archive_command('erigon',db,True) if x.startswith('--exclude=./')}
assert all('*' not in x and '?' not in x for x in excluded)
apparent=0;count=0
for directory,dirs,files in os.walk(db,followlinks=False):
 rel=pathlib.Path(directory).relative_to(db)
 dirs[:]=[n for n in dirs if str(rel/n) not in excluded]
 for name in files+dirs:
  path=pathlib.Path(directory)/name
  if str(rel/name) in excluded: continue
  st=path.lstat();assert stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)
  apparent+=st.st_size;count+=1
read=lambda p:json.loads((base/p).read_text())
peer={'proof':read('qualification/result.json'),'conversion':read('v3-head-upgrade/conversion-complete.json'),
      'phases':{n:read('v3-head-upgrade/'+n+'.json') for n in ('convert-v3','verify-v3-files','restore-head-block','verify-v3-state')}}
print(json.dumps({'peer':peer,'measurement':{'source':str(db),'source_stopped':True,
 'qualification_sha256':job['qualification_sha256'],'apparent_bytes':apparent,'entries':count,'time':time.time()},
 'upper_bound':apparent+count*8192+20_000_000_000}))
'''
    return json.loads(remote('159.89.21.191', code, job))


def assemble(s3, source=stopped_source):
    prefix = KEY.rsplit('/', 1)[0] + '/'
    def get(name):
        response = s3.get_object(Bucket=BUCKET, Key=prefix + name)
        try:
            return json.loads(response['Body'].read())
        finally:
            response['Body'].close()
    metadata = get('_snapshot_metadata.json')
    integrity = get('_snapshot_integrity.json')
    published_proof = get('_snapshot_reopen.json')
    published_conversion = get('_snapshot_conversion.json')
    assert metadata['full_remote_sha256_verified'] is True
    assert integrity['full_remote_sha256_verified'] is True
    object_head = s3.head_object(Bucket=BUCKET, Key=KEY)
    assert object_head['ContentLength'] == metadata['archive_bytes'] == integrity['archive_bytes']
    job = {'profile': 'erigon-v3-head', 'client': 'erigon', 'head': 24503958,
           'key': KEY, 'qualification_sha256': metadata['qualification_sha256']}
    current = source(job)
    assert current['peer']['proof'] == published_proof, 'Published and current qualification differ'
    assert current['peer']['conversion'] == published_conversion, 'Published and current conversion differ'
    bundle = {'key': KEY, 'etag': object_head['ETag'], 'metadata': metadata, 'integrity': integrity,
              'peer': current['peer'], 'unpacked_upper_bound_bytes': current['upper_bound'],
              'unpacked_measurement': current['measurement']}
    validate_bundle(bundle, module('upgrade_guard', 'upgrade-erigon-head-v3.py'),
                    module('worker_guard', 'qualify-worker.py'))
    return bundle


def stage(s3, bundle):
    # Local validation and all source checks precede creation of a scoped URL.
    validate_bundle(bundle, module('upgrade_guard', 'upgrade-erigon-head-v3.py'),
                    module('worker_guard', 'qualify-worker.py'))
    url = s3.generate_presigned_url('get_object', Params={'Bucket': BUCKET, 'Key': KEY}, ExpiresIn=86400)
    code = '''import json,os,pathlib,sys
x=json.load(sys.stdin);root=pathlib.Path('/data/pbt-1/v3-head-restore')
assert not root.is_symlink()
root.mkdir(mode=0o700,exist_ok=True)
assert root.resolve()==root
for name in ('started.json','complete.json','release-bundle.json','source-url','cache'):
 assert not (root/name).exists(), 'Existing restore inputs/attempt require inspection'
for name,data in [('release-bundle.json',json.dumps(x['bundle'],indent=2)+'\\n'),('source-url',x['url']+'\\n')]:
 fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as stream:stream.write(data)
print('Verified release inputs staged; no worker job started')
'''
    result = remote('164.92.239.96', code, {'bundle': bundle, 'url': url})
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = ROOT / 'release-bundle.json'
    path.write_text(json.dumps(bundle, indent=2) + '\n')
    path.chmod(0o600)
    print(result.decode().strip())


def stage_recovery_cache(s3, bundle):
    """Stage E2's download-only cache; preserve its database and recovery volume."""
    validate_bundle(bundle, module('upgrade_guard', 'upgrade-erigon-head-v3.py'),
                    module('worker_guard', 'qualify-worker.py'))
    payload = {'bundle': bundle}
    # Reject inadequate capacity or a different worker before issuing a URL.
    remote('159.89.21.191', RECOVERY_PREFLIGHT, payload)
    helper = (HERE / 'fetch-recovery-snapshot.py').read_text()
    digest = hashlib.sha256(helper.encode()).hexdigest()
    job = {'profile': 'verified-erigon-v3-head-recovery-cache', 'client': 'erigon',
           'head': 24503958, 'restore': False, 'key': KEY, 'etag': bundle['etag'],
           'archive_bytes': bundle['metadata']['archive_bytes'],
           'archive_sha256': bundle['metadata']['archive_sha256']}
    runner = f'''import hashlib,importlib.util,pathlib
root=pathlib.Path('/data/pbt-1/v3-head-recovery')
path=root/'fetch.py'
assert hashlib.sha256(path.read_bytes()).hexdigest()=={digest!r}
spec=importlib.util.spec_from_file_location('fetch',path)
fetch=importlib.util.module_from_spec(spec);spec.loader.exec_module(fetch)
fetch.ROOT=root/'cache';fetch.JOB=root/'job.json';fetch.URL=root/'source-url'
fetch.main(local_v3_cache=True)
'''
    url = s3.generate_presigned_url('get_object', Params={'Bucket': BUCKET, 'Key': KEY}, ExpiresIn=86400)
    payload['files'] = {'release-bundle.json': json.dumps(bundle, indent=2)+'\n',
                        'job.json': json.dumps(job, indent=2)+'\n', 'source-url': url+'\n',
                        'fetch.py': helper, 'download.py': runner}
    code = RECOVERY_PREFLIGHT + '''
import os
root.mkdir(mode=0o700)
(root/'cache').mkdir(mode=0o700)
for name,data in x['files'].items():
 assert name in ('release-bundle.json','job.json','source-url','fetch.py','download.py')
 fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as stream:
  stream.write(data);stream.flush();os.fsync(stream.fileno())
print('Erigon-2 recovery cache inputs staged; download not started; existing backup preserved')
'''
    print(remote('159.89.21.191', code, payload).decode().strip())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--stage', action='store_true')
    actions.add_argument('--stage-recovery-cache', action='store_true',
                         help='Stage Erigon-2 download-only recovery cache; never starts a job')
    args = parser.parse_args()
    try:
        s3 = client()
        bundle = assemble(s3)
        if args.stage_recovery_cache:
            stage_recovery_cache(s3, bundle)
        elif args.stage:
            stage(s3, bundle)
        else:
            print(json.dumps({'status': 'verified_release_inputs_ready', 'archive_bytes': bundle['metadata']['archive_bytes'],
                              'unpacked_upper_bound_bytes': bundle['unpacked_upper_bound_bytes'], 'staged': False}))
    except Exception as exc:
        # HTTP/SSH errors can contain scoped URLs: retain the class only.
        print('Release preparation stopped:', type(exc).__name__)
        raise SystemExit(1)
