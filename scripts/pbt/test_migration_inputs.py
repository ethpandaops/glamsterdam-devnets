"""Artifact delivery must preserve anchors and refuse incomplete input sets."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('inputs', Path(__file__).with_name('download-migration-inputs.py'))
inputs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs)


def fixture(host='lighthouse-geth-1'):
    meta = {'block': 24453558, 'blockHash': inputs.ANCHOR_HASH, 'stateRoot': inputs.STATE_ROOT,
            'chainId': '1', 'hashSuite': 'blake3', 'pbtRoot': '0x' + 'a' * 64}
    data = {'pbt-snapshot.bin': b'snapshot-content', 'framed.bin': b'preimage-content',
            'pbt-snapshot.meta.json': json.dumps(meta).encode()}
    release = {'anchor': 24453558, 'block_hash': inputs.ANCHOR_HASH, 'mpt_state_root': inputs.STATE_ROOT,
               'source_commit': inputs.COMMIT, 'full_remote_sha256_verified': True, 'genesis_time': None,
               'shadowfork_finality_established': False, 'cross_client_imports_verified': False,
               'proof_sha256': 'b' * 64, 'metadata': meta,
               'files': {name: {'key': inputs.PREFIX + name, 'bytes': len(value),
                         'sha256': hashlib.sha256(value).hexdigest(), 'etag': '"fixture"'}
                         for name, value in data.items()}}
    return {'host': host, 'release': release, 'release_canonical_sha256': inputs.digest(release),
            'urls': {name: name for name in inputs.names(host)}}, data


class Inputs(unittest.TestCase):
    def exercise(self, host='lighthouse-geth-1', failure=None):
        job, data = fixture(host)
        if failure == 'wrong-meta':
            other = dict(job['release']['metadata'], block=24453559)
            data['pbt-snapshot.meta.json'] = json.dumps(other).encode()
            item = job['release']['files']['pbt-snapshot.meta.json']
            item.update(bytes=len(data['pbt-snapshot.meta.json']), sha256=hashlib.sha256(data['pbt-snapshot.meta.json']).hexdigest())
            job['release_canonical_sha256'] = inputs.digest(job['release'])
        seen = []
        def fetch(url, etag, total):
            seen.append(url)
            value = data[url]
            if failure == 'corrupt' and url == 'framed.bin':
                value = b'X' * len(value)
            if failure == 'truncated' and url == 'framed.bin':
                value = value[:-1]
            yield value
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / 'control'
            control.mkdir()
            final, staging = root / 'final', root / 'staging'
            with patch.object(inputs, 'BASE', root), patch.object(inputs, 'CONTROL', control), \
                    patch.object(inputs, 'FINAL', final), patch.object(inputs, 'STAGING', staging), \
                    patch.object(inputs, 'RESERVE', 0):
                if failure:
                    with self.assertRaises(AssertionError):
                        inputs.transfer(job, {'service_uid': os.getuid()}, fetch)
                    self.assertFalse(final.exists())
                else:
                    inputs.transfer(job, {'service_uid': os.getuid()}, fetch)
                    proof = json.loads((final / 'ready.json').read_text())
                    self.assertEqual(set(proof['files']), set(inputs.names(host)))
                    self.assertFalse(proof['migration_started'])
                    self.assertFalse(proof['shadowfork_finality_established'])
                    self.assertIsNone(proof['genesis_time'])
                    for name in inputs.names(host):
                        self.assertEqual((final / name).read_bytes(), data[name])
                        self.assertEqual((final / name).stat().st_mode & 0o777, 0o640)
                    self.assertEqual(set(seen), set(inputs.names(host)))
                    self.assertFalse(staging.exists())

    def test_complete_pair_is_promoted_as_writable_independent_inputs(self):
        self.exercise()

    def test_geth_self_receives_preimages_and_metadata_only(self):
        self.exercise('lighthouse-geth-3')

    def test_corrupt_body_cannot_promote(self):
        self.exercise(failure='corrupt')

    def test_truncated_body_cannot_promote(self):
        self.exercise(failure='truncated')

    def test_wrong_anchor_metadata_cannot_promote_even_with_its_checksum(self):
        self.exercise(failure='wrong-meta')

    def test_unverified_release_or_wrong_anchor_is_rejected(self):
        job, _ = fixture()
        for key, value in [('full_remote_sha256_verified', False), ('anchor', 24453559), ('genesis_time', 1)]:
            release = copy.deepcopy(job['release'])
            release[key] = value
            with self.assertRaises(AssertionError):
                inputs.validate_release(release)

    def test_self_worker_rejects_import_pair(self):
        job, _ = fixture('lighthouse-geth-3')
        job['urls']['pbt-snapshot.bin'] = 'unexpected'
        with self.assertRaises(AssertionError):
            inputs.validate_job(job, 'glamsterdam-pbt-1-lighthouse-geth-3', {})

    def test_erigon_is_not_a_shared_import_recipient(self):
        with self.assertRaises(AssertionError):
            inputs.names('lighthouse-erigon-1')

    def test_insufficient_migration_headroom_refuses_before_creating_files(self):
        job, _ = fixture()
        job['downloader_sha256'] = hashlib.sha256(Path(inputs.__file__).read_bytes()).hexdigest()
        job['range_reader_sha256'] = hashlib.sha256(Path(inputs.__file__).with_name('stream_verified_archive.py').read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'qualification').mkdir()
            (root / 'qualification/result.json').write_text(json.dumps({
                'host': job['host'], 'client': 'geth', 'status': 'startup_checks_passed',
                'head': 24503958, 'head_hash': '0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216',
                'service_uid': 12345}))
            with patch.object(inputs, 'BASE', root), patch.object(inputs, 'FINAL', root / 'final'), \
                    patch.object(inputs, 'STAGING', root / 'staging'), \
                    patch.object(inputs.socket, 'gethostname', return_value='glamsterdam-pbt-1-' + job['host']), \
                    patch.object(inputs.pwd, 'getpwuid', return_value=SimpleNamespace(pw_gid=12345)), \
                    patch.object(inputs.shutil, 'disk_usage', return_value=SimpleNamespace(free=500_000_000_000)):
                with self.assertRaisesRegex(AssertionError, 'Insufficient space'):
                    inputs.check(job)
                self.assertFalse((root / 'staging').exists())
                self.assertFalse((root / 'final').exists())


if __name__ == '__main__':
    unittest.main()
