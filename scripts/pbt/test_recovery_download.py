"""Exercise real HTTP ranges, recovery checkpoints and checksum rejection."""
import hashlib
import http.server
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'recovery', Path(__file__).with_name('fetch-recovery-snapshot.py'))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)
BODY = bytes(range(256)) * 8192
DIGEST = hashlib.sha256(BODY).hexdigest()
ETAG = '"test-archive"'


class RecoveryDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.seen = []
        seen = self.seen

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                assert self.headers['If-Match'] == ETAG
                low, high = map(int, self.headers['Range'][6:].split('-'))
                seen.append(low)
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {low}-{high}/{len(BODY)}')
                self.send_header('ETag', ETAG)
                self.end_headers()
                self.wfile.write(BODY[low:high + 1])

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        recovery.ROOT = Path(self.temporary.name)
        recovery.JOB = recovery.ROOT / 'job.json'
        recovery.URL = recovery.ROOT / 'url'
        recovery.CHUNK = 65536
        recovery.JOB.write_text(json.dumps({
            'client': 'geth', 'head': 1, 'archive_bytes': len(BODY),
            'archive_sha256': DIGEST, 'etag': ETAG, 'restore': False}))
        recovery.URL.write_text(f'http://127.0.0.1:{self.server.server_port}/archive')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temporary.cleanup()

    def run_download(self):
        # Only the mount precondition is simulated; network, files and hash are real.
        with patch.object(Path, 'is_mount', return_value=True):
            recovery.main()

    def test_fresh_download_and_credential_removal(self):
        self.run_download()
        self.assertEqual((recovery.ROOT / 'geth-1.tar.zst').read_bytes(), BODY)
        self.assertFalse(recovery.URL.exists())

    def test_resume_discards_uncommitted_tail_and_fetches_only_remainder(self):
        offset = 2 * recovery.CHUNK
        (recovery.ROOT / 'geth-1.tar.zst.part').write_bytes(
            BODY[:offset] + b'uncommitted bytes')
        (recovery.ROOT / 'download-state.json').write_text(json.dumps({
            'offset': offset, 'size': len(BODY), 'sha256': DIGEST}))
        self.run_download()
        self.assertEqual(min(self.seen), offset)
        self.assertEqual((recovery.ROOT / 'geth-1.tar.zst').read_bytes(), BODY)

    def test_completed_archive_tampering_is_rejected(self):
        self.run_download()
        archive = recovery.ROOT / 'geth-1.tar.zst'
        archive.write_bytes(b'X' + BODY[1:])
        with self.assertRaises(AssertionError):
            self.run_download()
        self.assertEqual(json.loads((recovery.ROOT / 'status.json').read_text())['phase'],
                         'failed')

    def test_local_cache_uses_real_ranges_and_never_extracts(self):
        job = json.loads(recovery.JOB.read_text())
        job.update(profile='verified-erigon-v3-head-cache', client='erigon', head=24503958)
        recovery.JOB.write_text(json.dumps(job))
        usage = recovery.shutil.disk_usage(recovery.ROOT)
        sufficient = usage._replace(free=200_000_000_000)
        # The payload is only 2 MiB; simulate production capacity while retaining
        # real range requests, disk writes and whole-file hashing.
        with patch.object(recovery, 'validate_local_cache_job') as guard, patch.object(recovery.shutil, 'disk_usage', return_value=sufficient):
            recovery.main(local_v3_cache=True)
        guard.assert_called_once()
        self.assertEqual((recovery.ROOT / 'erigon-24503958.tar.zst').read_bytes(), BODY)
        self.assertEqual(json.loads((recovery.ROOT / 'status.json').read_text())['phase'],
                         'archive_ready_for_staged_restore')
        self.assertFalse((recovery.ROOT / 'restore-started.json').exists())

    def test_local_cache_guard_rejects_extraction_other_hosts_and_recovery_volume(self):
        job = {'profile': 'verified-erigon-v3-head-cache', 'client': 'erigon',
               'head': 24503958, 'restore': False}
        root = Path('/data/pbt-1/v3-head-restore/cache')
        host = 'glamsterdam-pbt-1-lighthouse-erigon-1'
        recovery.validate_local_cache_job(job, root, host)
        for other, directory, hostname in [({**job, 'restore': True}, root, host),
                                         (job, Path('/mnt/pbt-recovery'), host),
                                         (job, root, host.replace('-1', '-2')),
                                         ({**job, 'head': 24452538}, root, host)]:
            with self.assertRaises(AssertionError):
                recovery.validate_local_cache_job(other, directory, hostname)

    def test_second_erigon_recovery_cache_is_separate_and_download_only(self):
        job = {'profile': 'verified-erigon-v3-head-recovery-cache', 'client': 'erigon',
               'head': 24503958, 'restore': False}
        root = Path('/data/pbt-1/v3-head-recovery/cache')
        host = 'glamsterdam-pbt-1-lighthouse-erigon-2'
        recovery.validate_local_cache_job(job, root, host)
        for other, directory, hostname in [({**job, 'restore': True}, root, host),
                                         (job, Path('/mnt/pbt-recovery'), host),
                                         (job, root, host.replace('-2', '-1')),
                                         (job, Path('/data/pbt-1/v3-head-restore/cache'), host)]:
            with self.assertRaises(AssertionError):
                recovery.validate_local_cache_job(other, directory, hostname)

    def test_local_cache_preserves_root_space_before_fetching_any_ranges(self):
        job = json.loads(recovery.JOB.read_text())
        job.update(profile='verified-erigon-v3-head-recovery-cache', client='erigon', head=24503958)
        recovery.JOB.write_text(json.dumps(job))
        usage = recovery.shutil.disk_usage(recovery.ROOT)
        insufficient = usage._replace(free=len(BODY) + recovery.WORKERS * recovery.CHUNK + 149_999_999_999)
        with patch.object(recovery, 'validate_local_cache_job'), patch.object(recovery.shutil, 'disk_usage', return_value=insufficient):
            with self.assertRaises(AssertionError):
                recovery.main(local_v3_cache=True)
        self.assertEqual(self.seen, [])
        self.assertFalse((recovery.ROOT / 'erigon-24503958.tar.zst.part').exists())


if __name__ == '__main__':
    unittest.main()
