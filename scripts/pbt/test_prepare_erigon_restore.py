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


if __name__ == '__main__':
    unittest.main()
