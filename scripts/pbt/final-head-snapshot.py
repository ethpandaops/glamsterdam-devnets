#!/usr/bin/env python3
"""Final-head EL snapshots for pbt-1: one archive per client at one common block.

  check                     all nine ELs (and CLs) agree on one head; prints it
  authorize CLIENT HEAD     create the multipart upload, ship presigned part URLs to the VM
  stream                    (runs on the VM) tar|zstd the stopped datadir into the parts
  complete CLIENT           finish the upload, verify sampled ranges, publish metadata + head block

Account credentials stay on the controller (storage.client()); the VM only gets
object-scoped presigned UploadPart URLs.
"""
import argparse, concurrent.futures as cf, hashlib, json, random, subprocess, sys, time, urllib.request
from pathlib import Path

PREFIX = 'pbt-1/20261030-final-head/'
PUBLIC = 'https://shadowfork-images.ethpandaops.io/'
UA = {'User-Agent': 'curl/8.5.0'}  # Cloudflare's bot rule answers Python-urllib with 403
KEY = str(Path.home() / '.ssh/devops_eth2_shared_key')
PART = 256 * 1024**2
STATE = Path.home() / '.local/state/pbt-1-run/final-head'
VM_ROOT = '/data/pbt-1/final-snapshot'
# snapshot source per client type; the second worker of each type is the fallback
SOURCES = {'geth': ('lighthouse-geth-1', '46.101.230.44', '/data/pbt-1/geth'),
           'besu': ('lighthouse-besu-1', '138.68.76.218', '/data/pbt-1/besu'),
           'nethermind': ('lighthouse-nethermind-1', '167.172.188.11', '/data/pbt-1/nethermind'),
           'erigon': ('lighthouse-erigon-1', '164.92.239.96', '/data/pbt-1/erigon')}
# node identity, locks, logs and mempool state (txpool journals, blob pools) stay behind
EXCLUDES = {'geth': ['./nodekey', './LOCK', './geth.ipc', './jwtsecret', './keystore', './transactions.rlp', './blobpool'],
            'besu': ['./key', './logs', './DATABASE_METADATA.json.lock'],
            'nethermind': ['./keystore', './logs', './mainnet/keystore', './mainnet/logs', './mainnet/blobTransactions'],
            # chaindata.sidefork-*: the 2026-10-29 11:59 fork's DB kept as evidence, not the canonical state
            'erigon': ['./temp', './nodekey', './LOCK', './logs', './txpool', './chaindata.sidefork-20261029T1159Z']}
# published metadata: (image, source revision), archive layout, offline steps run before the archive
IMAGES = {'geth': ('local/geth:pbt-fb9925472 (not pushed; CPerezz/go-ethereum pbt branch)', 'fb9925472f8b68792dc9e24bad63b9ac74a4b248'),
          'besu': ('pbt-1/besu:cc564258-e49e3008 (local build)', 'cc5642583b802f8af31c58386d13429fd098d5e5'),
          'nethermind': ('ethpandaops/nethermind@sha256:6a570a4038248460f066907702dcbe1cff9809e9df411d9c30173d5d33d505f0', 'afc0e1f9b8a96a6b2058d33d7013175f2277d81c (pbt-state)'),
          'erigon': ('ethpandaops/erigon@sha256:977277f3f1c559d01d262994e3f2ca019bb517541553066a6e7e04d1efc46f6a', '9ac7b46')}
LAYOUT = {'geth': 'flat geth instance directory; mount under <datadir>/geth',
          'besu': 'besu --data-path contents (database/, caches/)',
          'nethermind': 'nethermind --datadir contents; DBs under mainnet/ (--Init.BaseDbPath=<datadir>/mainnet); flat/ is the pre-switch Patricia flat state, pbt/ the binary tree',
          'erigon': 'erigon --datadir contents (chaindata/, snapshots/)'}
OFFLINE = {'geth': ['geth db compact'], 'besu': ['besu storage trie-log prune (512 layers retained)'],
           'nethermind': [], 'erigon': ['erigon db compact']}
ALL = {'geth-1': '46.101.230.44', 'geth-2': '46.101.159.233', 'geth-3': '164.92.171.244',
       'besu-1': '138.68.76.218', 'besu-2': '164.92.248.222', 'nethermind-1': '167.172.188.11',
       'nethermind-2': '201.79.83.218', 'erigon-1': '164.92.239.96', 'erigon-2': '159.89.21.191'}


def ssh(ip, cmd, **kw):
    return subprocess.run(['ssh', '-n' if 'input' not in kw else '-T', '-o', 'BatchMode=yes', '-o', 'ControlPath=none',
                           '-i', KEY, f'root@{ip}', cmd], capture_output=True, text=True, timeout=120, **kw)


PROBE = r'''python3 - <<'EOF'
import json, urllib.request
def rpc(m, p):
    r = urllib.request.Request('http://localhost:8545', json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': m, 'params': p}).encode(), {'content-type': 'application/json'})
    return json.load(urllib.request.urlopen(r, timeout=8))['result']
def cl(u):
    try: return json.load(urllib.request.urlopen('http://localhost:5052' + u, timeout=5))['data']
    except Exception: return None
b = rpc('eth_getBlockByNumber', ['latest', False]); h = cl('/eth/v1/beacon/headers/head')
print(json.dumps({'number': int(b['number'], 16), 'hash': b['hash'], 'stateRoot': b['stateRoot'], 'timestamp': int(b['timestamp'], 16),
                  'cl_slot': h and h['header']['message']['slot'], 'cl_root': h and h['root']}))
EOF'''


def check(_):
    def one(item):
        n, ip = item
        r = ssh(ip, PROBE)
        return n, json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {'error': r.stderr.strip()[-200:]}
    with cf.ThreadPoolExecutor(9) as ex:
        res = dict(ex.map(one, ALL.items()))
    for n, v in res.items(): print(n, v)
    heads = {(v.get('number'), v.get('hash'), v.get('stateRoot')) for v in res.values()}
    cls = {(v.get('cl_slot'), v.get('cl_root')) for v in res.values() if v.get('cl_slot')}
    ok = len(heads) == 1 and None not in next(iter(heads))
    print('COMMON HEAD' if ok else 'HEADS DIFFER', sorted(heads, key=str), 'CL', sorted(cls, key=str))
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f'check-{int(time.time())}.json').write_text(json.dumps(res, indent=1))
    sys.exit(0 if ok else 1)


def authorize(a):
    from storage import client, BUCKET
    node, ip, datadir = SOURCES[a.client]
    key = f'{PREFIX}{a.client}/{a.head}/snapshot.tar.zst'
    STATE.mkdir(parents=True, exist_ok=True)
    jobf = STATE / f'upload-{a.client}.json'
    if jobf.exists(): raise SystemExit(f'{jobf} exists; inspect the existing multipart upload first')
    st = ssh(ip, "docker inspect execution --format '{{.State.Running}} {{.State.ExitCode}} {{.State.OOMKilled}} {{.Config.Image}}'").stdout.split()
    if st[0] != 'false' or st[2] != 'false': raise SystemExit(f'{node}: execution must be stopped cleanly first: {st}')
    size = int(ssh(ip, f'du -s -B1 --apparent-size {datadir}').stdout.split()[0])
    parts = size // PART + 64  # zstd only shrinks; 64 spare parts
    if parts > 10000: raise SystemExit(f'{size} bytes needs {parts} parts > 10000; raise PART')
    s3 = client()
    try:
        s3.head_object(Bucket=BUCKET, Key=key); raise SystemExit(f'{key} already exists')
    except s3.exceptions.ClientError as e:
        if e.response['Error']['Code'] not in ('404', 'NoSuchKey', 'NotFound'): raise
    up = s3.create_multipart_upload(Bucket=BUCKET, Key=key, ContentType='application/zstd',
                                    Metadata={'pbt-head': str(a.head), 'client': a.client, 'node': node})['UploadId']
    job = {'client': a.client, 'node': node, 'head': a.head, 'key': key, 'upload_id': up, 'datadir': datadir,
           'excludes': EXCLUDES[a.client], 'image': st[3], 'exit_code': int(st[1])}
    jobf.write_text(json.dumps(job, indent=1)); jobf.chmod(0o600)
    job['urls'] = [s3.generate_presigned_url('upload_part', Params={'Bucket': BUCKET, 'Key': key, 'UploadId': up, 'PartNumber': i},
                                             ExpiresIn=7 * 86400) for i in range(1, parts + 1)]
    r = ssh(ip, f'mkdir -p {VM_ROOT} && umask 077 && cat > {VM_ROOT}/job.json', input=json.dumps(job))
    if r.returncode: raise SystemExit(r.stderr)
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', '-i', KEY, __file__, f'root@{ip}:{VM_ROOT}/final-head-snapshot.py'], check=True)
    print(f'authorized {key} ({parts} part URLs, datadir {size / 1e12:.2f} TB); start on {node}:\n'
          f'  systemd-run --unit pbt-final-snapshot python3 {VM_ROOT}/final-head-snapshot.py stream')


def stream(_):
    root = Path(VM_ROOT); job = json.loads((root / 'job.json').read_text())
    st = subprocess.check_output(['docker', 'inspect', 'execution', '--format', '{{.State.Running}}'], text=True).strip()
    assert st == 'false', 'execution container is running'
    tar = subprocess.Popen(['tar', '--sparse', '--sort=name', *[f'--exclude={e}' for e in job['excludes']],
                            '-C', job['datadir'], '-cf', '-', '.'], stdout=subprocess.PIPE, stderr=(root / 'tar.log').open('w'))
    zst = subprocess.Popen(['zstd', '-1', '-T8', '-q'], stdin=tar.stdout, stdout=subprocess.PIPE, stderr=(root / 'zstd.log').open('w'))
    tar.stdout.close()
    whole = hashlib.sha256(); parts = []; total = 0; t0 = time.time()

    def put(n, data, digest):
        for attempt in range(6):
            try:
                req = urllib.request.Request(job['urls'][n - 1], data=data, method='PUT')
                with urllib.request.urlopen(req, timeout=600) as r:
                    return {'PartNumber': n, 'ETag': r.headers['ETag'], 'bytes': len(data), 'sha256': digest}
            except Exception as e:
                if attempt == 5: raise
                time.sleep(2 ** attempt)
    with cf.ThreadPoolExecutor(4) as ex:
        futs = []; n = 0
        while True:
            data = zst.stdout.read(PART)
            if not data: break
            n += 1; whole.update(data); total += len(data)
            futs.append(ex.submit(put, n, data, hashlib.sha256(data).hexdigest()))
            while len([f for f in futs if not f.done()]) >= 4: time.sleep(0.2)
            (root / 'progress.json').write_text(json.dumps({'parts': n, 'bytes': total, 'elapsed': time.time() - t0}))
        parts = [f.result() for f in futs]
    assert zst.wait() == 0 and tar.wait() == 0, 'tar/zstd failed; do not complete'
    out = {'key': job['key'], 'upload_id': job['upload_id'], 'head': job['head'], 'parts': parts,
           'archive_bytes': total, 'archive_sha256': whole.hexdigest(), 'elapsed': time.time() - t0,
           'data_bytes': int(subprocess.check_output(['du', '-s', '-B1', '--apparent-size', job['datadir']]).split()[0])}
    (root / 'parts.json').write_text(json.dumps(out))
    print(json.dumps({k: v for k, v in out.items() if k != 'parts'}))


def complete(a):
    from storage import client, BUCKET
    node, ip, _ = SOURCES[a.client]
    job = json.loads((STATE / f'upload-{a.client}.json').read_text())
    rep = json.loads(ssh(ip, f'cat {VM_ROOT}/parts.json').stdout)
    assert rep['upload_id'] == job['upload_id'] and rep['key'] == job['key']
    parts = rep['parts']
    assert [p['PartNumber'] for p in parts] == list(range(1, len(parts) + 1)) and sum(p['bytes'] for p in parts) == rep['archive_bytes']
    s3 = client()
    s3.complete_multipart_upload(Bucket=BUCKET, Key=job['key'], UploadId=job['upload_id'],
                                 MultipartUpload={'Parts': [{'PartNumber': p['PartNumber'], 'ETag': p['ETag']} for p in parts]})
    assert s3.head_object(Bucket=BUCKET, Key=job['key'])['ContentLength'] == rep['archive_bytes']
    offs = [0]
    for p in parts[:-1]: offs.append(offs[-1] + p['bytes'])
    pick = sorted({0, len(parts) - 1, *random.Random(rep['archive_sha256']).sample(range(len(parts)), min(3, len(parts)))})
    for i in pick:
        r = s3.get_object(Bucket=BUCKET, Key=job['key'], Range=f'bytes={offs[i]}-{offs[i] + parts[i]["bytes"] - 1}')
        h = hashlib.sha256(r['Body'].read()).hexdigest(); assert h == parts[i]['sha256'], f'part {i + 1} mismatch'
        print(f'part {i + 1}/{len(parts)} verified')
    head = json.loads((STATE / 'head.json').read_text())
    assert head['block_number'] == rep['head']
    meta = {'docker_image': IMAGES[a.client][0], 'source_revision': IMAGES[a.client][1],
            'data_size_bytes': rep['data_bytes'], 'archive_size_bytes': rep['archive_bytes'], 'archive_sha256': rep['archive_sha256'],
            'shadowfork': {'head': head['block_number'], 'head_hash': head['block_hash'], 'state_root': head['state_root'],
                           'timestamp': head['timestamp'], 'cl_slot': int(head['cl_slot']), 'cl_head_root': head['cl_head_root'],
                           'amsterdam_time': 1769856769, 'binary_trie_time': 1793264400, 'chain_id': 1, 'network': 'pbt-1',
                           'genesis': PREFIX + '_snapshot_genesis.json', 'gas_limit': 200000000,
                           'notes': 'pbt-1 final head, 1.3 days after the binary-trie switch (EIP-8347): binary trie canonical. '
                                    'All nine ELs (3 geth, 2 besu, 2 nethermind, 2 erigon) agreed on this head/stateRoot.'},
            'snapshot': {'client': a.client, 'node': node, 'native_layout': LAYOUT[a.client], 'excludes': job['excludes'],
                         'offline_steps': OFFLINE[a.client], 'clean_restart_verified': True,
                         'frozen_at': head['frozen_at'], 'nodes_agreeing': head['nodes_agreeing']}}
    base = job['key'].rsplit('/', 1)[0] + '/'
    s3.put_object(Bucket=BUCKET, Key=base + '_snapshot_metadata.json', Body=json.dumps(meta, indent=2).encode(), ContentType='application/json')
    s3.put_object(Bucket=BUCKET, Key=base + '_snapshot_eth_getBlockByNumber.json',
                  Body=(STATE / f'block-{rep["head"]}.json').read_bytes(), ContentType='application/json')
    # public availability: the CDN serves only snapshot.tar.zst and _snapshot_* names (anything else is 403)
    pub = PUBLIC + job['key']
    with urllib.request.urlopen(urllib.request.Request(pub, method='HEAD', headers=UA), timeout=60) as r:
        assert int(r.headers['Content-Length']) == rep['archive_bytes'], f'{pub}: {r.headers["Content-Length"]}'
    with urllib.request.urlopen(urllib.request.Request(pub, headers={**UA, 'Range': f'bytes=0-{parts[0]["bytes"] - 1}'}), timeout=600) as r:
        assert hashlib.sha256(r.read()).hexdigest() == parts[0]['sha256'], f'{pub}: first part mismatch'
    for name in ('_snapshot_metadata.json', '_snapshot_eth_getBlockByNumber.json'):
        with urllib.request.urlopen(urllib.request.Request(PUBLIC + base + name, headers=UA), timeout=60) as r: json.load(r)
    meta['public'] = {'archive': pub, 'metadata': PUBLIC + base + '_snapshot_metadata.json'}
    (STATE / f'published-{a.client}.json').write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest='cmd', required=True)
    s.add_parser('check')
    x = s.add_parser('authorize'); x.add_argument('client', choices=SOURCES); x.add_argument('head', type=int)
    s.add_parser('stream')
    x = s.add_parser('complete'); x.add_argument('client', choices=SOURCES)
    a = p.parse_args()
    {'check': check, 'authorize': authorize, 'stream': stream, 'complete': complete}[a.cmd](a)
