import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'cache_readback', Path(__file__).with_name('verify-erigon-recovery-cache.py'))
readback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(readback)


class CacheReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.data = b'fixed archive fixture'
        self.checksum = hashlib.sha256(self.data).hexdigest()
        self.archive = self.cache / 'erigon-24503958.tar.zst'
        self.archive.write_bytes(self.data)
        self.write(self.root / 'job.json', {
            'profile': 'verified-erigon-v3-head-recovery-cache',
            'archive_sha256': self.checksum, 'archive_bytes': len(self.data),
            'restore': False})
        self.write(self.cache / 'status.json', {'phase': 'archive_ready_for_staged_restore'})
        self.write(self.cache / 'archive-verified.json', {
            'sha256': self.checksum, 'bytes': len(self.data),
            'mtime_ns': self.archive.stat().st_mtime_ns})
        for attribute, value in [('ROOT', self.root), ('EXPECTED_SHA', self.checksum),
                                 ('EXPECTED_SIZE', len(self.data))]:
            self.enterContext(patch.object(readback, attribute, value))
        self.enterContext(patch.object(
            readback.socket, 'gethostname',
            return_value='glamsterdam-pbt-1-lighthouse-erigon-2'))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value))

    def run_unit(self, load='loaded', active='inactive', result='success'):
        state = {'LoadState': load, 'ActiveState': active,
                 'MainPID': '0', 'Result': result}
        with patch.object(readback, 'unit', return_value=state):
            readback.main()

    def assert_no_proof(self):
        self.assertFalse((self.root / 'stored-cache-verified.json').exists())

    def test_successful_stopped_download(self):
        self.run_unit()
        proof = json.loads((self.root / 'stored-cache-verified.json').read_text())
        self.assertEqual(proof['sha256'], self.checksum)
        self.assertEqual(proof['bytes'], len(self.data))
        self.assertEqual(self.archive.read_bytes(), self.data)

    def test_collected_transient_unit_requires_completed_file_proofs(self):
        self.run_unit(load='not-found')
        self.assertTrue((self.root / 'stored-cache-verified.json').exists())

    def test_collected_unit_with_incomplete_download_rejected(self):
        self.write(self.cache / 'status.json', {'phase': 'downloading'})
        with self.assertRaises(AssertionError):
            self.run_unit(load='not-found')
        self.assert_no_proof()

    def test_failed_loaded_unit_rejected(self):
        with self.assertRaises(AssertionError):
            self.run_unit(active='failed', result='exit-code')
        self.assert_no_proof()

    def test_matching_download_proof_does_not_hide_corrupt_stored_file(self):
        self.archive.write_bytes(b'x' * len(self.data))
        self.write(self.cache / 'archive-verified.json', {
            'sha256': self.checksum, 'bytes': len(self.data),
            'mtime_ns': self.archive.stat().st_mtime_ns})
        with self.assertRaises(AssertionError):
            self.run_unit(load='not-found')
        self.assert_no_proof()
        self.assertEqual(self.archive.read_bytes(), b'x' * len(self.data))

    def test_missing_download_proof_rejected(self):
        (self.cache / 'archive-verified.json').unlink()
        with self.assertRaises(FileNotFoundError):
            self.run_unit(load='not-found')
        self.assert_no_proof()

    def test_download_lock_prevents_overlapping_hash(self):
        with (self.cache / 'download.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                self.run_unit(load='not-found')
        self.assert_no_proof()

    def test_live_unit_can_finish_and_be_collected_between_polls(self):
        states = [
            {'LoadState': 'loaded', 'ActiveState': 'active',
             'MainPID': '123', 'Result': 'success'},
            {'LoadState': 'not-found', 'ActiveState': 'inactive',
             'MainPID': '0', 'Result': 'success'}]
        with patch.object(readback, 'unit', side_effect=states), patch.object(readback.time, 'sleep') as sleep:
            readback.main()
        sleep.assert_called_once_with(30)
        self.assertTrue((self.root / 'stored-cache-verified.json').exists())


if __name__ == '__main__':
    unittest.main()
