#!/usr/bin/env python3
"""Hash completed N exports after explicit deferral of independent reconstruction."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import time

assert os.environ.get('PBT_ARTIFACT_EXPORT_ONLY') == '1'
spec = importlib.util.spec_from_file_location('publication', Path(__file__).with_name('publish-pbt-artifacts.py'))
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


def run():
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    root = pub.PROOF.parent
    decision = json.loads((root / 'verification-deferred-by-user.json').read_text())
    assert decision['independent_mpt_reconstruction_verified'] is False
    assert decision['native_export_exit_code'] == 0
    unit = dict(line.split('=', 1) for line in subprocess.check_output([
        'systemctl', 'show', 'pbt-1-native-anchor-export', '-p', 'MainPID', '-p', 'ActiveState'], text=True).splitlines())
    assert unit['MainPID'] == '0' and unit['ActiveState'] in ('inactive', 'failed')
    exported = json.loads((root / 'export.json').read_text())
    assert exported['exit_code'] == 0 and exported['binary_sha256'] == pub.BINARY_SHA
    assert not pub.PROOF.exists()
    started = json.loads((root / 'started.json').read_text())
    meta = json.loads((pub.ARTIFACTS / 'pbt-snapshot.meta.json').read_text())
    report = {**started, 'status': 'native_export_passed_independent_verification_deferred',
              'metadata': meta, 'source_commit': pub.COMMIT,
              'shadowfork_finality_established': False, 'cross_client_imports_verified': False,
              'independent_mpt_reconstruction_verified': False, 'verification_deferred_by_user': True,
              'artifacts': {}, 'uploaded': False}
    before = {name: pub.identity(pub.ARTIFACTS / name) for name in pub.FILES}
    # This read computes the transfer checksum; it does not rebuild either state tree.
    for name in pub.FILES:
        checksum, count, last = hashlib.sha256(), 0, time.monotonic()
        with (pub.ARTIFACTS / name).open('rb') as stream:
            while data := stream.read(8 * 1024**2):
                checksum.update(data)
                count += len(data)
                if time.monotonic() - last > 30:
                    pub.save(root, 'export-publication-status.json', {
                        'phase': 'transfer_checksum', 'file': name, 'bytes': count,
                        'total': before[name]['bytes'], 'time': time.time()})
                    last = time.monotonic()
        assert count == before[name]['bytes']
        report['artifacts'][name] = {**before[name], 'sha256': checksum.hexdigest()}
    report['time'] = time.time()
    pub.validate_proof(report)
    pub.validate_files(report)
    pub.save(root, 'export-ready.json', report)
    pub.save(root, 'export-publication-status.json', {'phase': 'ready_for_upload', 'time': time.time()})
    print('Completed export ready for upload; independent MPT reconstruction deferred.', flush=True)


if __name__ == '__main__':
    os.umask(0o077)
    run()
