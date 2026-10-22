import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import test_verified_erigon_restore as fixtures

spec = importlib.util.spec_from_file_location('prepare_restore', Path(__file__).with_name('prepare-erigon-release-restore.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class ControllerRestoreInputs(unittest.TestCase):
    def setUp(self):
        self.bundle = fixtures.bundle_fixture()
        self.s3 = Mock()
        self.objects = {'_snapshot_metadata.json': self.bundle['metadata'],
                        '_snapshot_integrity.json': self.bundle['integrity'],
                        '_snapshot_reopen.json': self.bundle['peer']['proof'],
                        '_snapshot_conversion.json': self.bundle['peer']['conversion']}
        self.s3.get_object.side_effect = lambda **kw: {'Body': io.BytesIO(
            json.dumps(self.objects[kw['Key'].rsplit('/', 1)[1]]).encode())}
        self.s3.head_object.return_value = {'ContentLength': 100, 'ETag': '"fixture"'}
        self.source = Mock(return_value={'peer': self.bundle['peer'],
                                         'measurement': self.bundle['unpacked_measurement'],
                                         'upper_bound': self.bundle['unpacked_upper_bound_bytes']})

    def test_assembles_only_matching_published_and_stopped_source(self):
        self.assertEqual(prepare.assemble(self.s3, self.source), self.bundle)
        self.source.assert_called_once()
        self.s3.generate_presigned_url.assert_not_called()

    def test_pending_remote_checksum_never_contacts_worker_or_issues_url(self):
        self.objects['_snapshot_integrity.json']['full_remote_sha256_verified'] = False
        with self.assertRaises(AssertionError):
            prepare.assemble(self.s3, self.source)
        self.source.assert_not_called()
        self.s3.generate_presigned_url.assert_not_called()

    def test_changed_source_proof_is_rejected(self):
        self.objects['_snapshot_reopen.json'] = copy.deepcopy(self.bundle['peer']['proof'])
        self.objects['_snapshot_reopen.json']['head'] = 24452538
        with self.assertRaises(AssertionError):
            prepare.assemble(self.s3, self.source)

    def test_invalid_bundle_cannot_issue_a_download_url(self):
        self.bundle['metadata']['tree'] = 'PBT'
        with self.assertRaises(AssertionError):
            prepare.stage(self.s3, self.bundle)
        self.s3.generate_presigned_url.assert_not_called()

    def test_staged_files_are_private_valid_json_and_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote_root = root / 'worker'
            def execute(host, code, payload):
                self.assertEqual(host, '164.92.239.96')
                code = code.replace('/data/pbt-1/v3-head-restore', str(remote_root))
                return subprocess.check_output(['/usr/bin/python3', '-c', code],
                                               input=json.dumps(payload).encode(), stderr=subprocess.PIPE)
            self.s3.generate_presigned_url.return_value = 'https://fixture.invalid/scoped'
            with patch.object(prepare, 'remote', side_effect=execute), patch.object(prepare, 'ROOT', root / 'controller'):
                prepare.stage(self.s3, self.bundle)
                self.assertEqual(json.loads((remote_root / 'release-bundle.json').read_text()), self.bundle)
                self.assertEqual((remote_root / 'source-url').read_text(), 'https://fixture.invalid/scoped\n')
                self.assertEqual((remote_root / 'source-url').stat().st_mode & 0o777, 0o600)
                with self.assertRaises(subprocess.CalledProcessError):
                    prepare.stage(self.s3, self.bundle)
                self.assertEqual((remote_root / 'source-url').read_text(), 'https://fixture.invalid/scoped\n')

    def test_recovery_cache_rejects_unverified_release_before_worker_or_url(self):
        self.bundle['integrity']['full_remote_sha256_verified'] = False
        with patch.object(prepare, 'remote') as remote, self.assertRaises(AssertionError):
            prepare.stage_recovery_cache(self.s3, self.bundle)
        remote.assert_not_called()
        self.s3.generate_presigned_url.assert_not_called()

    def test_recovery_cache_stages_private_download_only_files_and_preserves_backup(self):
        self.check_recovery_cache(free=1_000_000_000_000)

    def test_recovery_cache_insufficient_space_rejected_before_url(self):
        self.check_recovery_cache(free=100)

    def check_recovery_cache(self, free):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / 'qualification').mkdir()
            (base / 'qualification/result.json').write_text(json.dumps(self.bundle['peer']['proof']))
            backup = base / 'old-recovery-archive'
            backup.write_bytes(b'original backup')
            def execute(host, code, payload):
                self.assertEqual(host, '159.89.21.191')
                code = code.replace('/data/pbt-1/v3-head-recovery', str(base / 'v3-head-recovery'))
                overrides = ('import socket,shutil,types\n'
                             "socket.gethostname=lambda:'glamsterdam-pbt-1-lighthouse-erigon-2'\n"
                             f'shutil.disk_usage=lambda p:types.SimpleNamespace(free={free})\n')
                return subprocess.check_output(['/usr/bin/python3', '-c', overrides+code],
                                               input=json.dumps(payload).encode(), stderr=subprocess.PIPE)
            self.s3.generate_presigned_url.return_value = 'https://fixture.invalid/scoped'
            with patch.object(prepare, 'remote', side_effect=execute):
                if free == 100:
                    with self.assertRaises(subprocess.CalledProcessError):
                        prepare.stage_recovery_cache(self.s3, self.bundle)
                    self.s3.generate_presigned_url.assert_not_called()
                    self.assertFalse((base / 'v3-head-recovery').exists())
                else:
                    prepare.stage_recovery_cache(self.s3, self.bundle)
                    root = base / 'v3-head-recovery'
                    job = json.loads((root / 'job.json').read_text())
                    self.assertIs(job['restore'], False)
                    self.assertEqual(job['archive_sha256'], self.bundle['metadata']['archive_sha256'])
                    self.assertEqual(job['etag'], self.bundle['etag'])
                    self.assertEqual(job['profile'], 'verified-erigon-v3-head-recovery-cache')
                    helper = (root / 'fetch.py').read_bytes()
                    self.assertIn(hashlib.sha256(helper).hexdigest(), (root / 'download.py').read_text())
                    compile((root / 'download.py').read_text(), 'download.py', 'exec')
                    self.assertEqual((root / 'source-url').read_text(), 'https://fixture.invalid/scoped\n')
                    self.assertFalse(list((root / 'cache').iterdir()))
                    for item in root.iterdir():
                        if item.is_file():
                            self.assertEqual(item.stat().st_mode & 0o777, 0o600)
                    with self.assertRaises(subprocess.CalledProcessError):
                        prepare.stage_recovery_cache(self.s3, self.bundle)
            self.assertEqual(backup.read_bytes(), b'original backup')


class RestoredWorkerRecoveryInputs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.bundle = fixtures.bundle_fixture()
        self.s3 = Mock()
        self.s3.generate_presigned_url.return_value = 'https://fixture.invalid/scoped'
        self.free = 1_000_000_000_000
        self.unit_active = False
        self.container_running = False
        for name in ('qualification', 'v3-head-restore', 'erigon'):
            (self.base / name).mkdir()
        self.backup = self.base / 'old-recovery-archive'
        self.backup.write_bytes(b'original backup remains')
        bundle_path = self.base / 'v3-head-restore/release-bundle.json'
        bundle_path.write_text(json.dumps(self.bundle))
        st = (self.base / 'erigon').stat()
        self.complete = {
            'host': 'glamsterdam-pbt-1-lighthouse-erigon-1',
            'profile': 'restored_verified_H_release', 'archive_transfer': 'stream',
            'bundle_sha256': hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
            'archive_sha256': self.bundle['metadata']['archive_sha256'],
            'local_v3_conversion_performed': False,
            'restored_identity': {'device': st.st_dev, 'inode': st.st_ino}}
        self.stream = {
            'whole_archive_verified': True, 'method': 'etag_bound_ranges_to_fresh_directory',
            'sha256': self.complete['archive_sha256'], 'bytes': self.bundle['metadata']['archive_bytes'],
            'key': self.bundle['key'], 'etag': self.bundle['etag'],
            'bundle_sha256': self.complete['bundle_sha256'],
            'restored_identity': self.complete['restored_identity']}
        self.proof = copy.deepcopy(self.bundle['peer']['proof'])
        self.proof.update(host='lighthouse-erigon-1', memory_gib=32, cpuset='0-7',
                          genesis_time=None, preparation_path='restored_verified_H_release',
                          source_release_key=self.bundle['key'],
                          source_release_archive_sha256=self.complete['archive_sha256'],
                          local_v3_conversion_performed=False)
        self.proof['stopped_state']['FinishedAt'] = 'fixture-clean-stop'
        self.write_evidence()

    def tearDown(self):
        self.tmp.cleanup()

    def write_evidence(self):
        for name, value in [('qualification/result.json', self.proof),
                            ('v3-head-restore/complete.json', self.complete),
                            ('v3-head-restore/stream-verified.json', self.stream)]:
            (self.base / name).write_text(json.dumps(value))

    def execute(self, host, code, payload):
        self.assertEqual(host, '164.92.239.96')
        code = code.replace('/data/pbt-1/v3-head-recovery', str(self.base / 'v3-head-recovery'))
        unit = 'MainPID=123\nActiveState=active\nResult=success\n' if self.unit_active else (
            'MainPID=0\nActiveState=inactive\nResult=success\n')
        container = json.dumps([{'State': {'Running': self.container_running,
                                          'FinishedAt': 'fixture-clean-stop'}}])
        overrides = (
            'import socket,shutil,subprocess,types\n'
            "socket.gethostname=lambda:'glamsterdam-pbt-1-lighthouse-erigon-1'\n"
            f'shutil.disk_usage=lambda p:types.SimpleNamespace(free={self.free})\n'
            f'subprocess.check_output=lambda args,**kw: {unit!r} if args[0]=="systemctl" else {container!r}\n')
        return subprocess.check_output(['/usr/bin/python3', '-c', overrides + code],
                                       input=json.dumps(payload).encode(), stderr=subprocess.PIPE)

    def stage(self):
        with patch.object(prepare, 'remote', side_effect=self.execute):
            prepare.stage_recovery_cache(self.s3, self.bundle, restored_worker=True)

    def assert_rejected_before_url(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.stage()
        self.s3.generate_presigned_url.assert_not_called()
        self.assertFalse((self.base / 'v3-head-recovery').exists())
        self.assertEqual(self.backup.read_bytes(), b'original backup remains')

    def test_own_restore_and_qualification_stage_only_private_download_inputs(self):
        before = {name: (self.base / name).read_bytes() for name in (
            'qualification/result.json', 'v3-head-restore/complete.json', 'old-recovery-archive')}
        self.stage()
        root = self.base / 'v3-head-recovery'
        job = json.loads((root / 'job.json').read_text())
        self.assertIs(job['restore'], False)
        self.assertEqual(job['profile'], 'verified-erigon-1-restored-head-recovery-cache')
        spec = importlib.util.spec_from_file_location('staged_cache_fetch', root / 'fetch.py')
        fetch = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fetch)
        fetch.validate_local_cache_job(job, Path('/data/pbt-1/v3-head-recovery/cache'),
                                       'glamsterdam-pbt-1-lighthouse-erigon-1')
        with self.assertRaises(AssertionError):
            fetch.validate_local_cache_job(job, Path('/data/pbt-1/v3-head-recovery/cache'),
                                           'glamsterdam-pbt-1-lighthouse-erigon-2')
        self.assertEqual(job['archive_sha256'], self.complete['archive_sha256'])
        self.assertEqual(job['key'], self.bundle['key'])
        self.assertFalse(list((root / 'cache').iterdir()))
        for path in root.iterdir():
            if path.is_file():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        for name, data in before.items():
            self.assertEqual((self.base / name).read_bytes(), data)
        self.s3.generate_presigned_url.reset_mock()
        with self.assertRaises(subprocess.CalledProcessError):
            self.stage()
        self.s3.generate_presigned_url.assert_not_called()

    def test_peer_proof_cannot_substitute_for_own_qualification(self):
        for field, wrong in [('host', 'lighthouse-erigon-2'), ('memory_gib', 16),
                             ('status', 'starting'), ('native_reopen_verified', False)]:
            with self.subTest(field=field):
                original = self.proof[field]
                self.proof[field] = wrong
                self.write_evidence()
                self.assert_rejected_before_url()
                self.proof[field] = original

    def test_corrupt_or_changed_restore_evidence_rejected(self):
        for record, field, wrong in [(self.stream, 'whole_archive_verified', False),
                                     (self.stream, 'sha256', 'b' * 64),
                                     (self.complete, 'bundle_sha256', 'b' * 64),
                                     (self.complete, 'restored_identity', {'device': 0, 'inode': 0})]:
            with self.subTest(field=field):
                original = record[field]
                record[field] = wrong
                self.write_evidence()
                self.assert_rejected_before_url()
                record[field] = original

    def test_active_preparation_and_running_client_rejected(self):
        self.unit_active = True
        self.assert_rejected_before_url()
        self.unit_active = False
        self.container_running = True
        self.assert_rejected_before_url()

    def test_insufficient_cache_capacity_rejected_before_url(self):
        self.free = 100
        self.assert_rejected_before_url()

    def test_failed_qualification_lock_rejected(self):
        import fcntl
        with (self.base / 'qualification/run.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assert_rejected_before_url()


if __name__ == '__main__':
    unittest.main()
