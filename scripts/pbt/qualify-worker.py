#!/usr/bin/env python3
"""Isolated startup qualification for a restored PBT worker.

The job supplies pinned image/source/fixture identities. No CL, peering, payload
submission, migration activation, history expiry or genesis-time selection.
The native database may perform ordinary startup maintenance; a verified local
recovery archive is mandatory. The client is stopped after the checks.
"""
import argparse
import base64
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import socket
import subprocess
import time

ROOT = Path('/data/pbt-1')


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE).strip()


def inspect(name):
    return json.loads(run('docker', 'inspect', name))[0]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def rpc(pid, secret_path, method, params, authenticated=False):
    headers = ['-H', 'Content-Type: application/json']
    port = 18545
    if authenticated:
        def b64(v):
            return base64.urlsafe_b64encode(v).rstrip(b'=')
        secret = bytes.fromhex(secret_path.read_text().strip())
        unsigned = b64(b'{"alg":"HS256","typ":"JWT"}') + b'.' + b64(
            json.dumps({'iat': int(time.time())}).encode())
        jwt = (unsigned + b'.' + b64(hmac.digest(secret, unsigned, 'sha256'))).decode()
        headers += ['-H', 'Authorization: Bearer ' + jwt]
        port = 18551
    request = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params})
    try:
        data = json.loads(run('nsenter', '--target', str(pid), '--net', 'curl',
                              '-fsS', '--max-time', '30', *headers, '--data',
                              request, f'http://127.0.0.1:{port}'))
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f'{method}: transport failure (exit {exc.returncode})') from None
    if 'error' in data:
        raise RuntimeError(f'{method}: {data["error"]}')
    return data['result']


def arguments(client):
    if client == 'erigon':
        return [
            '--datadir=/data', '--chain=mainnet', '--networkid=1',
            '--keep.stored.chain.config', '--experimental.commitment-v3',
            '--nodekey=/node-identity/nodekey',
            '--http', '--http.addr=127.0.0.1', '--http.port=18545',
            '--http.api=eth,web3,debug,admin,net', '--http.vhosts=*',
            '--authrpc.addr=127.0.0.1', '--authrpc.port=18551',
            '--authrpc.jwtsecret=/jwt', '--externalcl', '--nodiscover',
            '--maxpeers=0', '--no-downloader', '--snap.stop',
            '--db.size.limit=2TB', '--exec.no-background-maintenance=true',
            '--exec.no-prune=true',
        ]
    if client == 'geth':
        return [
            '--datadir=/data', '--override.genesis=/config/genesis.json',
            '--nodekey=/node-identity/nodekey', '--http', '--http.addr=127.0.0.1',
            '--http.port=18545', '--http.api=eth,web3,admin,debug,net',
            '--authrpc.addr=127.0.0.1', '--authrpc.port=18551',
            '--authrpc.jwtsecret=/jwt', '--syncmode=full', '--nodiscover',
            '--maxpeers=0', '--port=0', '--rpc.gascap=200000000',
            '--txpool.globalslots=20000', '--txpool.globalqueue=5000',
        ]
    if client == 'nethermind':
        return [
            '--datadir=/data', '--config=mainnet', '--Init.BaseDbPath=/data/mainnet',
            '--Init.ChainSpecPath=/config/genesis.json',
            '--KeyStore.KeyStoreDirectory=/data/keystore',
            '--KeyStore.EnodeKeyFile=/node-identity/node.key.plain',
            '--Init.DiscoveryEnabled=false', '--Network.MaxActivePeers=0',
            '--Network.EnableEnrDiscovery=false', '--Discovery.UseDefaultDiscv5Bootnodes=false',
            '--Sync.FastSync=false', '--Sync.SnapSync=false',
            '--FlatDb.Enabled=true', '--FlatDb.Layout=Flat',
            '--Merge.TerminalTotalDifficulty=0', '--Pruning.Mode=None',
            '--Init.MemoryHint=2500000000', '--TxPool.Size=20000',
            '--JsonRpc.Enabled=true', '--JsonRpc.Host=127.0.0.1',
            '--JsonRpc.Port=18545', '--JsonRpc.EnabledModules=Eth,Web3,Admin,Debug,Net',
            '--JsonRpc.EngineHost=127.0.0.1', '--JsonRpc.EnginePort=18551',
            '--JsonRpc.JwtSecretFile=/jwt',
        ]
    assert client == 'besu'
    return [
        '--data-path=/data', '--genesis-file=/config/genesis.json',
        '--node-private-key-file=/node-identity/nodekey',
        # Besu disables admin_nodeInfo entirely with --p2p-enabled=false.
        # Network isolation is enforced by Docker; keep P2P local with no peers.
        '--network-id=1', '--p2p-enabled=true', '--p2p-host=127.0.0.1',
        '--discovery-enabled=false', '--bootnodes=', '--max-peers=0',
        '--nat-method=NONE', '--sync-mode=FULL',
        '--version-compatibility-protection=false', '--data-storage-format=BONSAI',
        '--bonsai-limit-trie-logs-enabled=false', '--snapsync-server-enabled=true',
        '--host-allowlist=*', '--engine-host-allowlist=*',
        '--rpc-http-enabled=true', '--rpc-http-host=127.0.0.1',
        '--rpc-http-port=18545', '--rpc-http-api=ETH,WEB3,ADMIN,DEBUG,NET',
        '--engine-rpc-enabled=true', '--engine-rpc-port=18551',
        '--engine-jwt-secret=/jwt', '--color-enabled=false',
        '--cache-last-blocks=2048', '--rpc-http-max-active-connections=1000',
        '--rpc-gas-cap=200000000', '--tx-pool-max-prioritized=20000',
    ]


def audit_worker(name, job, secret_path, owner_uid):
    deadline = time.monotonic() + 900
    while True:
        state = inspect(name)['State']
        assert state['Running'], 'Client exited during startup'
        pid = state['Pid']
        try:
            head = rpc(pid, secret_path, 'eth_getBlockByNumber', ['latest', False])
            if head:
                break
        except (RuntimeError, ValueError):
            pass
        assert time.monotonic() < deadline, 'RPC startup timeout'
        time.sleep(5)
    if job['client'] == 'geth':
        # This pinned build starts RPC before StartNode installs its shutdown
        # handler. Do not signal it while protocol-stack startup is unfinished.
        # Require the handler itself to be blocked receiving on sigc.
        deadline = time.monotonic() + 120
        while True:
            stacks = rpc(pid, secret_path, 'debug_stacks', [])
            ready = any(
                re.search(r'goroutine \d+ \[chan receive', stack)
                and len(stack.splitlines()) > 1
                and stack.splitlines()[1].endswith('/cmd/utils.StartNode.func1()')
                for stack in stacks.split('\n\n'))
            if ready:
                break
            assert inspect(name)['State']['Running'], 'Geth exited before shutdown readiness'
            assert time.monotonic() < deadline, 'Geth shutdown handler did not become ready'
            time.sleep(1)
    assert int(head['number'], 16) == job['head'], ('Unexpected head', head['number'])
    assert head['hash'] == job['head_hash'] and head['stateRoot'] == job['state_root']
    anchor = rpc(pid, secret_path, 'eth_getBlockByNumber', [hex(job['anchor']), False])
    assert anchor['hash'] == job['anchor_hash'] and anchor['stateRoot'] == job['anchor_state_root']
    peer = rpc(pid, secret_path, 'admin_nodeInfo', [])
    advertised = peer['enode'].split('enode://', 1)[1].split('@', 1)[0]
    assert advertised.lower() == job['node_id'].lower()
    samples = {}
    for address, expected in job['code_samples'].items():
        code = rpc(pid, secret_path, 'eth_getCode', [address, 'latest'])
        got = hashlib.sha256(bytes.fromhex(code.removeprefix('0x'))).hexdigest()
        assert got == expected, ('Code differs', address)
        samples[address] = got
    builder_code = {}
    for address in ('0x0000bff46984e3725691fa540a8c7589300d8282',
                    '0x000064d678505ad48f8ccb093bc65613800e8282'):
        code = rpc(pid, secret_path, 'eth_getCode', [address, 'latest'])
        builder_code[address] = {'bytes': (len(code) - 2) // 2,
                                 'sha256': hashlib.sha256(bytes.fromhex(code[2:])).hexdigest()}
    bodies = {}
    for number, expected in job['payload_samples'].items():
        body = rpc(pid, secret_path, 'engine_getPayloadBodiesByRangeV2',
                   [hex(int(number)), '0x1'], True)
        assert len(body) == 1 and body[0], ('Missing body', number)
        selected = {k: body[0][k] for k in ('blockAccessList', 'transactions', 'withdrawals')}
        assert digest(selected) == expected['sha256'], ('Payload body differs', number)
        bodies[number] = expected
    return dict(status='startup_checks_passed', head=job['head'], head_hash=head['hash'],
                  state_root=head['stateRoot'], anchor=job['anchor'],
                  anchor_hash=anchor['hash'], node_id=advertised,
                  state_code_samples=samples, builder_contracts=builder_code,
                  sampled_payload_bodies=bodies, service_uid=owner_uid,
                  missing_builder_contracts=[a for a, v in builder_code.items() if v['bytes'] == 0])


def validate_erigon_conversion_identity(job, db, started, complete):
    """Require this worker's H conversion, never an exporter or another host."""
    limits = {'lighthouse-erigon-1': 32, 'lighthouse-erigon-2': 16}
    assert job['client'] == 'erigon' and job['host'] in limits
    assert job['memory_gib'] == limits[job['host']]
    assert job['head'] == 24503958
    assert str(db) == '/data/pbt-1/erigon'
    assert started['host'] == 'glamsterdam-pbt-1-' + job['host']
    for proof in (started, complete):
        assert proof['target_block'] == job['head']
        assert proof['source'] == str(db)
    assert started['target_hash'] == job['head_hash']
    assert started['target_state_root'] == job['state_root']
    assert started['commit'] == job['commit']
    assert started['rollback_sha256'] == job['archive_sha256']


def validate_erigon_converter_build(complete, phases):
    """A patched converter must retain explicit provenance and original checks."""
    build = complete.get('converter_build')
    if build is None:
        return None
    assert build['base_commit'] == '372df0e68f52f9975370bff38dee6e41aefff0d7'
    assert build['patch_sha256'] == '4b04368aad6cf9ee38058eb5d6e6bed79ac251a49138b9c9c28a0c6455483ab9'
    assert build['binary_sha256'] == '1f807caefedc534ae837641ebff1dfdc37c0378ea8e3556263bddd1eb276e9f3'
    original = 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03'
    assert build['independent_verifier_sha256'] == original
    assert phases['convert-v3']['converter_build'] == build
    assert phases['convert-v3']['binary_sha256'] == build['binary_sha256']
    for name in ('verify-v3-files', 'restore-head-block', 'verify-v3-state'):
        assert phases[name]['exit_code'] == 0
        assert phases[name]['binary_sha256'] == original
        expected = ['stage_exec'] if name == 'restore-head-block' else ['commitment', 'verify']
        assert phases[name]['command'][1:1 + len(expected)] == expected
    return build


def main(job_path, wait_for_restore=False, wait_for_erigon_conversion=False, from_verified_release=False):
    job = json.loads(job_path.read_text())
    client = job['client']
    if from_verified_release:
        assert client == 'erigon' and job['host'] == 'lighthouse-erigon-1'
        assert not wait_for_restore and not wait_for_erigon_conversion
    assert client in ('geth', 'nethermind', 'besu', 'erigon')
    assert socket.gethostname() == 'glamsterdam-pbt-1-' + job['host']
    assert job['head'] == 24503958 and job['anchor'] == 24453558
    assert job['memory_gib'] in (16, 32)
    evidence = ROOT / 'qualification'
    evidence.mkdir(exist_ok=True, mode=0o700)
    lock = (evidence / 'run.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (evidence / 'result.json').exists(), 'Inspect prior qualification before repeating'
    if wait_for_erigon_conversion:
        assert client == 'erigon' and job['host'] in (
            'lighthouse-erigon-1', 'lighthouse-erigon-2')
        upgrade = ROOT / 'v3-head-upgrade'
        deadline = time.monotonic() + 24 * 3600
        print('Waiting for the active H conversion to finish before opening Erigon.', flush=True)
        while True:
            conversion = json.loads((upgrade / 'status.json').read_text())
            active = run('systemctl', 'show', 'pbt-1-v3-head-upgrade',
                         '-p', 'ActiveState', '--value')
            assert conversion['phase'] != 'failed' and active != 'failed', 'Conversion failed'
            if active == 'inactive':
                assert (upgrade / 'conversion-complete.json').exists(), 'Conversion stopped early'
                break
            assert active in ('active', 'activating', 'deactivating'), 'Conversion unit missing'
            assert time.monotonic() < deadline, 'Conversion wait timed out'
            (evidence / 'status.json').write_text(json.dumps({
                'phase': 'waiting_for_erigon_conversion', 'time': time.time(),
                'conversion_phase': conversion['phase'], 'conversion_service': active}) + '\n')
            time.sleep(15)
    recovery_root = Path('/mnt/pbt-recovery')
    assert recovery_root.is_mount()
    if wait_for_restore:
        deadline = time.monotonic() + 6 * 3600
        print('Waiting for the active recovery job to finish before opening the database.', flush=True)
        while True:
            restore = json.loads((recovery_root / 'status.json').read_text())
            if restore['phase'] in ('restored_unopened', 'recovery_ready_existing_db_preserved'):
                break
            assert restore['phase'] != 'failed', 'Recovery failed; database will not be opened'
            active = run('systemctl', 'show', 'pbt-recovery-snapshot', '-p', 'ActiveState', '--value')
            assert active in ('active', 'activating'), 'Recovery stopped before completion'
            assert time.monotonic() < deadline, 'Recovery wait timed out; database remains unopened'
            (evidence / 'status.json').write_text(json.dumps({
                'phase': 'waiting_for_restore', 'time': time.time(),
                'recovery_phase': restore['phase'], 'recovery_service': active}) + '\n')
            time.sleep(15)
    status = json.loads((recovery_root / 'status.json').read_text())
    assert status['phase'] in ('restored_unopened', 'recovery_ready_existing_db_preserved')
    archive = recovery_root / f'{client}-{job["head"]}.tar.zst'
    archive_stat = archive.stat()
    proof = json.loads((recovery_root / 'archive-verified.json').read_text())
    assert proof['mtime_ns'] == archive_stat.st_mtime_ns
    assert proof['bytes'] == archive_stat.st_size == job['archive_bytes']
    assert proof['sha256'] == job['archive_sha256']
    db = ROOT / client
    assert db.is_dir() and any(db.iterdir())
    restored_provenance = None
    if from_verified_release:
        from erigon_verified_restore import validate_promoted
        converter_build, restored_provenance = validate_promoted(job, db)
    elif client == 'erigon':
        # A held Erigon-1 job can run only after its own H conversion. The
        # older exporter and a copied Erigon-2 proof cannot qualify it.
        upgrade = ROOT / 'v3-head-upgrade'
        complete = json.loads((upgrade / 'conversion-complete.json').read_text())
        started = json.loads((upgrade / 'started.json').read_text())
        validate_erigon_conversion_identity(job, db, started, complete)
        phases = {phase: json.loads((upgrade / (phase + '.json')).read_text())
                  for phase in ('convert-v3', 'verify-v3-files', 'restore-head-block', 'verify-v3-state')}
        for phase_record in phases.values():
            assert phase_record['exit_code'] == 0
        converter_build = validate_erigon_converter_build(complete, phases)
        restoration = json.loads((upgrade / 'restore-head-block.json').read_text())
        if restoration.get('no_prune_env') != 'true':
            # The first live driver predates the environment fix. Its atomic
            # launcher records the effective setting in the stage_exec log.
            retention = json.loads((upgrade / 'bal-retention-launcher.json').read_text())
            assert retention['environment'] == {'NO_PRUNE': 'true'}
            assert retention['pinned_binary_sha256'] == started['binaries']['integration']
            with (upgrade / 'restore-head-block.log').open() as stream:
                assert '[pbt-preparation] stage_exec NO_PRUNE=true;' in stream.readline()
        assert run('systemctl', 'show', 'pbt-1-v3-head-upgrade', '-p',
                   'ActiveState', '--value') == 'inactive', 'Conversion must have stopped'
        assert run('systemctl', 'show', 'pbt-1-v3-head-upgrade', '-p',
                   'MainPID', '--value') == '0'
        # Docker overlap checks do not cover native processes.
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                args = (proc / 'cmdline').read_bytes().split(b'\0')
                assert ('--datadir=' + str(db)).encode() not in args, (
                    'Native process still has this datadir', proc.name)
            except (FileNotFoundError, ProcessLookupError):
                continue
    for cid in run('docker', 'ps', '-q').splitlines():
        for mount in inspect(cid)['Mounts']:
            other = Path(mount['Source'])
            if mount['RW']:
                assert not (db == other or db in other.parents or other in db.parents), (
                    'Database has another writable container mount', cid)
    genesis_path = evidence / 'config/genesis.json'
    assert hashlib.sha256(genesis_path.read_bytes()).hexdigest() == job['genesis_sha256']
    config = json.loads(genesis_path.read_text())['config']
    assert config['amsterdamTime'] == 1769856769 and 'binaryTrieTime' not in config
    identity = json.loads((ROOT / 'node-identity/public.json').read_text())
    assert identity['node_id'] == job['node_id'] and identity['client'] == client
    image_ref = job['image']
    assert '@sha256:' in image_ref or image_ref.startswith('sha256:')
    if '@sha256:' in image_ref:
        run('docker', 'pull', image_ref)
    image = inspect(image_ref)
    labels = image['Config']['Labels']
    if client == 'besu':
        assert labels['org.opencontainers.image.revision'] == job['commit']
        assert labels['pbt.stateless.revision'] == job['library_commit']
        jar = run('docker', 'run', '--rm', '--network=none', '--entrypoint=sha256sum',
                  image_ref, '/opt/besu/lib/besu-stateless-0.1.8-SNAPSHOT.jar').split()[0]
        assert jar == job['library_jar_sha256']
    else:
        assert labels['ethpandaops.io.commitRef'] == job['commit']

    owner = pwd.getpwnam(client)
    # Match the service account used by the deployment roles.
    subprocess.run(['chown', '-R', f'{owner.pw_uid}:{owner.pw_gid}', str(db)], check=True)
    os.chmod(evidence, 0o755)
    secret_path = evidence / 'jwt'
    if not secret_path.exists():
        fd = os.open(secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write(secrets.token_hex(32))
    os.chown(secret_path, owner.pw_uid, owner.pw_gid)
    if client == 'geth':
        # /data/geth is the instance directory; /data holds the IPC socket.
        os.chown(ROOT, owner.pw_uid, owner.pw_gid)
        mounted_data = ROOT
    else:
        mounted_data = db
    name = 'pbt-1-worker-qualification'
    cmd = [
        'docker', 'run', '-d', '--name', name, '--network=none',
        '--cpus=8', '--cpuset-cpus=0-7', f'--memory={job["memory_gib"]}g',
        f'--memory-swap={job["memory_gib"]}g', '--memory-swappiness=0',
        '--user', f'{owner.pw_uid}:{owner.pw_gid}',
        '--hostname=pbt-check', '--add-host=pbt-check:127.0.0.1',
        '-v', f'{mounted_data}:/data',
        '-v', f'{ROOT}/node-identity:/node-identity:ro',
        '-v', f'{evidence}/config:/config:ro',
        '-v', f'{secret_path}:/jwt:ro',
    ]
    if client == 'besu':
        cmd += ['-e', 'BESU_OPTS=-Xmx8g -XX:MaxHeapFreeRatio=30 -XX:MinHeapFreeRatio=10']
    elif client == 'erigon':
        cmd += ['-e', 'GOMAXPROCS=8', '-e', 'COMMITMENT_V3=true']
    cmd += [image_ref, *arguments(client)]
    (evidence / 'command.json').write_text(json.dumps(cmd, indent=2) + '\n')
    report = {'status': 'starting', 'host': job['host'], 'client': client,
              'time': time.time(), 'image': image_ref, 'commit': job['commit'],
              'memory_gib': job['memory_gib'], 'cpus': 8, 'cpuset': '0-7',
              'network_mode': 'none', 'genesis_time': None,
              'migration_qualified': False, 'full_deployment_qualified': False}
    if client == 'erigon' and converter_build is not None:
        report['converter_build'] = converter_build
    if restored_provenance is not None:
        report.update(restored_provenance)
    started = False
    try:
        run(*cmd)
        started = True
        report.update(audit_worker(name, job, secret_path, owner.pw_uid))
        if client == 'erigon':
            # Verify persistence through a clean shutdown, then repeat all reads.
            before = dict(report)
            run('docker', 'stop', '--time=-1', name)
            state = inspect(name)['State']
            assert not state['Running'] and not state['OOMKilled'] and state['ExitCode'] == 0
            report['first_stopped_state'] = state
            run('docker', 'start', name)
            reopened = audit_worker(name, job, secret_path, owner.pw_uid)
            for key, value in reopened.items():
                assert value == before[key], ('Reopen differs', key)
            report['native_reopen_verified'] = True
            report['v3_format_verified'] = True
    except Exception as exc:
        report.update(status='failed', error=str(exc))
        raise
    finally:
        if started:
            run('docker', 'stop', '--time=-1', name)
            state = inspect(name)['State']
            report['stopped_state'] = state
            with (evidence / 'container.log').open('w') as stream:
                subprocess.run(['docker', 'logs', name], stdout=stream,
                               stderr=subprocess.STDOUT, check=True)
            allowed = (0, 130, 143) if client == 'besu' else (0, 130)
            clean = not state['Running'] and not state['OOMKilled'] and state['ExitCode'] in allowed
            if client == 'besu' and state['ExitCode'] == 143:
                clean &= 'BesuCommand-Shutdown-Hook' in (evidence / 'container.log').read_text()
            if not clean:
                report.update(status='failed', error='Client did not stop cleanly')
        report['finished_at'] = time.time()
        (evidence / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report), flush=True)
    assert report['status'] == 'startup_checks_passed'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('job', type=Path)
    p.add_argument('--wait-for-restore', action='store_true')
    p.add_argument('--wait-for-erigon-conversion', action='store_true')
    p.add_argument('--from-verified-release', action='store_true',
                   help='Qualify Erigon-1 after a separately verified H release restore')
    a = p.parse_args()
    main(a.job, a.wait_for_restore, a.wait_for_erigon_conversion, a.from_verified_release)
