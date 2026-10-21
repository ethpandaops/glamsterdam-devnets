import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

import erigon_verified_restore as restore
import test_preserved_erigon_head as fixtures
upgrade, qualifier = fixtures.upgrade, fixtures.qualifier


def bundle_fixture():
    peer = fixtures.OptimizedHandoff().peer()
    proof = peer['proof']
    checksum = 'a' * 64
    meta = {'client': 'erigon', 'head': proof['head'], 'head_hash': proof['head_hash'],
            'state_root': proof['state_root'], 'erigon_commit': proof['commit'], 'image': proof['image'],
            'converter_build': proof['converter_build'], 'commitment_format': 'v3', 'tree': 'MPT',
            'pbt_migration_performed': False, 'launch_authorized': False, 'genesis_time': None,
            'full_remote_sha256_verified': True, 'native_reopen_verified': True,
            'archive_sha256': checksum, 'archive_bytes': 100,
            'qualification_sha256': hashlib.sha256((json.dumps(proof, indent=2) + '\n').encode()).hexdigest()}
    return {'peer': peer, 'metadata': meta,
            'integrity': {'client': 'erigon', 'head': proof['head'], 'key': restore.KEY,
                          'archive_sha256': checksum, 'archive_bytes': 100, 'full_remote_sha256_verified': True},
            'key': restore.KEY, 'etag': '"fixture"', 'unpacked_upper_bound_bytes': 1000,
            'unpacked_measurement': {'source': '/data/pbt-1/erigon', 'source_stopped': True,
                                    'qualification_sha256': meta['qualification_sha256'], 'apparent_bytes': 900}}


class ReleaseGuards(unittest.TestCase):
    def test_verified_matching_H_release_accepted(self):
        self.assertEqual(restore.validate_bundle(bundle_fixture(), upgrade, qualifier),
                         bundle_fixture()['peer']['proof']['converter_build'])

    def test_incomplete_upload_wrong_head_or_bad_provenance_rejected(self):
        cases = [('metadata', 'full_remote_sha256_verified', False),
                 ('integrity', 'full_remote_sha256_verified', False),
                 ('metadata', 'archive_sha256', 'b' * 64),
                 ('metadata', 'qualification_sha256', 'b' * 64),
                 ('metadata', 'head', 24452538), ('metadata', 'tree', 'PBT'),
                 ('metadata', 'launch_authorized', True),
                 ('unpacked_measurement', 'source_stopped', False)]
        for section, key, value in cases:
            bundle = bundle_fixture()
            bundle[section][key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                restore.validate_bundle(bundle, upgrade, qualifier)

    def test_failed_original_verifier_is_not_bypassed_by_release_metadata(self):
        bundle = bundle_fixture()
        bundle['peer']['phases']['verify-v3-state']['exit_code'] = 1
        with self.assertRaises(AssertionError):
            restore.validate_bundle(bundle, upgrade, qualifier)


class RestoreFilesystem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / 'erigon'
        self.source.mkdir()
        (self.source / 'original-sentinel').write_text('original H remains recoverable')
        self.control = self.base / 'control'
        self.control.mkdir()
        payload = self.base / 'payload'
        (payload / 'chaindata').mkdir(parents=True)
        (payload / 'chaindata/mdbx.dat').write_bytes(b'fixture restored database')
        (payload / 'snapshots/domain').mkdir(parents=True)
        (payload / 'snapshots/domain/fixture.kv').write_bytes(b'fixture immutable file')
        self.archive = self.base / 'fixture.tar.zst'
        subprocess.run(['tar', '--zstd', '-cf', str(self.archive), '-C', str(payload), '.'], check=True)
        self.bundle = bundle_fixture()
        self.bundle['metadata']['archive_bytes'] = self.archive.stat().st_size
        self.bundle['metadata']['archive_sha256'] = restore.sha(self.archive)
        for key in ('archive_bytes', 'archive_sha256'):
            self.bundle['integrity'][key] = self.bundle['metadata'][key]
        self.bundle['unpacked_measurement']['source'] = str(self.source)
        (self.control / 'release-bundle.json').write_text(json.dumps(self.bundle))
        (self.control / 'source-url').write_text('https://fixture.invalid/archive')
        self.patches = [patch.object(restore, name, value) for name, value in {
            'BASE': self.base, 'CONTROL': self.control, 'SOURCE': self.source,
            'CACHE': self.control / 'cache', 'STAGING': self.base / 'restored',
            'PRESERVED': self.base / 'preserved', 'RESERVE': 0}.items()]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def downloader(self):
        module = types.SimpleNamespace()
        def main(local_v3_cache=False):
            self.assertTrue(local_v3_cache)
            archive = module.ROOT / 'erigon-24503958.tar.zst'
            shutil.copyfile(self.archive, archive)
            (module.ROOT / 'archive-verified.json').write_text(json.dumps({
                'bytes': archive.stat().st_size, 'sha256': restore.sha(archive),
                'mtime_ns': archive.stat().st_mtime_ns}))
        module.main = main
        return module

    def execute(self, stream=False):
        # Real tar extraction and directory promotion; source release guards and
        # HTTP transfer are exercised separately, not simulated as proof here.
        with patch.object(restore, 'preflight', return_value=self.bundle), \
                patch.object(restore, 'idle_database'), \
                patch.object(restore.socket, 'gethostname', return_value='glamsterdam-pbt-1-lighthouse-erigon-1'), \
                patch.object(restore, 'load', return_value=self.downloader()):
            restore.run(stream=stream)

    def test_stream_extracts_and_hashes_without_a_second_archive_copy(self):
        payload = self.archive.read_bytes()
        with patch('stream_verified_archive.ordered_ranges', return_value=[payload[:50], payload[50:]]):
            self.execute(stream=True)
        self.assertFalse(restore.CACHE.exists())
        self.assertTrue((restore.PRESERVED / 'original-sentinel').exists())
        self.assertEqual((self.source / 'chaindata/mdbx.dat').read_bytes(), b'fixture restored database')
        proof = restore.read(self.control / 'stream-verified.json')
        self.assertEqual(proof['sha256'], restore.sha(self.archive))
        self.assertTrue(proof['whole_archive_verified'])
        self.assertEqual(restore.read(self.control / 'complete.json')['archive_transfer'], 'stream')
        peer = self.bundle['peer']['proof']
        job = {k: peer[k] for k in ('client', 'head', 'head_hash', 'state_root', 'image', 'commit')}
        job.update(host='lighthouse-erigon-1', memory_gib=32)
        with patch.object(restore, 'guards', return_value=(upgrade, qualifier)), \
                patch.object(restore.socket, 'gethostname', return_value='glamsterdam-pbt-1-lighthouse-erigon-1'), \
                patch.object(restore, 'idle_database'), \
                patch.object(restore.subprocess, 'check_output', return_value='MainPID=0\nActiveState=inactive\nResult=success\n'):
            restore.validate_promoted(job, self.source)
            proof['sha256'] = 'b' * 64
            (self.control / 'stream-verified.json').write_text(json.dumps(proof))
            with self.assertRaises(AssertionError):
                restore.validate_promoted(job, self.source)

    def test_whole_stream_checksum_failure_never_promotes_even_valid_tar(self):
        self.bundle['metadata']['archive_sha256'] = 'b' * 64
        with patch('stream_verified_archive.ordered_ranges', return_value=[self.archive.read_bytes()]), \
                self.assertRaisesRegex(AssertionError, 'checksum mismatch'):
            self.execute(stream=True)
        self.assertTrue((self.source / 'original-sentinel').exists())
        self.assertFalse(restore.PRESERVED.exists())
        self.assertFalse((self.control / 'complete.json').exists())
        self.assertFalse((self.control / 'stream-verified.json').exists())

    def test_broken_stream_never_moves_original(self):
        with patch('stream_verified_archive.ordered_ranges', return_value=[b'broken archive']), \
                self.assertRaises(AssertionError):
            self.execute(stream=True)
        self.assertTrue((self.source / 'original-sentinel').exists())
        self.assertFalse((self.control / 'complete.json').exists())

    def test_extracts_fresh_database_and_preserves_original_in_full(self):
        original_inode = self.source.stat().st_ino
        self.execute()
        self.assertEqual((restore.PRESERVED / 'original-sentinel').read_text(), 'original H remains recoverable')
        self.assertEqual(restore.PRESERVED.stat().st_ino, original_inode)
        self.assertEqual((self.source / 'chaindata/mdbx.dat').read_bytes(), b'fixture restored database')
        proof = restore.read(self.control / 'complete.json')
        self.assertFalse(proof['worker_qualified'])
        self.assertFalse(proof['local_v3_conversion_performed'])

    def test_promotion_failure_puts_original_back(self):
        rename = Path.rename
        def fail_staging(path, target):
            if path == restore.STAGING:
                raise OSError('fixture promotion failure')
            return rename(path, target)
        with patch.object(Path, 'rename', fail_staging), self.assertRaises(OSError):
            self.execute()
        self.assertTrue((self.source / 'original-sentinel').is_file())
        self.assertFalse((self.control / 'complete.json').exists())
        self.assertTrue((restore.STAGING / 'chaindata/mdbx.dat').is_file())

    def test_extraction_failure_never_moves_original(self):
        self.archive.write_bytes(b'invalid archive')
        with self.assertRaises(AssertionError):
            self.execute()
        self.assertTrue((self.source / 'original-sentinel').is_file())
        self.assertFalse(restore.PRESERVED.exists())

    def test_restored_identity_requires_own_worker_limit_and_stopped_restorer(self):
        self.execute()
        peer = self.bundle['peer']['proof']
        job = {k: peer[k] for k in ('client', 'head', 'head_hash', 'state_root', 'image', 'commit')}
        job.update(host='lighthouse-erigon-1', memory_gib=32)
        state = 'MainPID=0\nActiveState=inactive\nResult=success\n'
        with patch.object(restore, 'guards', return_value=(upgrade, qualifier)), \
                patch.object(restore.socket, 'gethostname', return_value='glamsterdam-pbt-1-lighthouse-erigon-1'), \
                patch.object(restore, 'idle_database'), \
                patch.object(restore.subprocess, 'check_output', return_value=state) as systemctl:
            build, provenance = restore.validate_promoted(job, self.source)
            self.assertEqual(build, peer['converter_build'])
            self.assertFalse(provenance['local_v3_conversion_performed'])
            with self.assertRaises(AssertionError):
                restore.validate_promoted({**job, 'memory_gib': 16}, self.source)
            with self.assertRaises(AssertionError):
                restore.validate_promoted({**job, 'host': 'lighthouse-erigon-2'}, self.source)
            systemctl.return_value = state.replace('inactive', 'active').replace('MainPID=0', 'MainPID=123')
            with self.assertRaises(AssertionError):
                restore.validate_promoted(job, self.source)

    def test_changed_restored_directory_cannot_reuse_promotion_proof(self):
        self.execute()
        self.source.rename(self.base / 'moved')
        self.source.mkdir()
        peer = self.bundle['peer']['proof']
        job = {k: peer[k] for k in ('client', 'head', 'head_hash', 'state_root', 'image', 'commit')}
        job.update(host='lighthouse-erigon-1', memory_gib=32)
        with patch.object(restore, 'guards', return_value=(upgrade, qualifier)), \
                patch.object(restore.socket, 'gethostname', return_value='glamsterdam-pbt-1-lighthouse-erigon-1'), \
                self.assertRaises(AssertionError):
            restore.validate_promoted(job, self.source)


if __name__ == '__main__':
    unittest.main()
