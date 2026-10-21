"""Full readback must gate the N release, including a corrupt stored object."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('artifacts', Path(__file__).with_name('publish-pbt-artifacts.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def proof():
    return {'status': 'native_export_and_verification_passed', 'anchor': 24453558,
            'block_hash': m.BLOCK_HASH, 'mpt_state_root': m.STATE_ROOT,
            'source': '/data/pbt-1/rehearsal-24453558/erigon',
            'source_commit': m.COMMIT, 'binary_sha256': m.BINARY_SHA,
            'metadata': {'block': 24453558, 'blockHash': m.BLOCK_HASH,
                         'stateRoot': m.STATE_ROOT, 'chainId': '1', 'hashSuite': 'blake3'},
            'shadowfork_finality_established': False, 'cross_client_imports_verified': False,
            'artifacts': {name: {'bytes': 5, 'sha256': m.digest(b'abcde'), 'inode': 1, 'mtime_ns': 1}
                          for name in m.FILES}}


class Publication(unittest.TestCase):
    def test_export_only_check_passes_mode_to_remote_worker(self):
        exported = proof()
        exported.update(status='native_export_passed_independent_verification_deferred',
                        independent_mpt_reconstruction_verified=False,
                        verification_deferred_by_user=True)
        evidence = {'proof': exported, 'proof_sha256': 'a' * 64}
        with patch.object(m, 'EXPORT_ONLY', True), patch.object(m, 'ssh', return_value=json.dumps(evidence).encode()) as ssh:
            self.assertEqual(m.check(), evidence)
            self.assertEqual(ssh.call_args.args[0][:2], ['env', 'PBT_ARTIFACT_EXPORT_ONLY=1'])

    def test_deferred_verification_requires_explicit_mode_and_record(self):
        exported = proof()
        exported.update(status='native_export_passed_independent_verification_deferred',
                        independent_mpt_reconstruction_verified=False,
                        verification_deferred_by_user=True)
        with self.assertRaises(RuntimeError):
            m.validate_proof(exported)
        with patch.object(m, 'EXPORT_ONLY', True):
            m.validate_proof(exported)
            for change in ({'verification_deferred_by_user': False},
                           {'independent_mpt_reconstruction_verified': True},
                           {'anchor': 24503958}):
                with self.subTest(change=change), self.assertRaises(RuntimeError):
                    m.validate_proof({**exported, **change})

    def test_reject_wrong_anchor_build_or_unverified_export(self):
        m.validate_proof(proof())
        for key, value in [('anchor', 24503958), ('block_hash', '0x00'),
                           ('source_commit', 'different'), ('status', 'exported'),
                           ('shadowfork_finality_established', True)]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                m.validate_proof({**proof(), key: value})
        changed = proof()
        changed['metadata']['hashSuite'] = 'keccak'
        with self.assertRaises(RuntimeError):
            m.validate_proof(changed)

    def test_missing_proof_cannot_authorize_storage(self):
        from unittest.mock import Mock
        storage = Mock()
        with tempfile.TemporaryDirectory() as directory, patch.object(m, 'LOCAL', Path(directory)), \
                patch.object(m, 'check', side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                m.authorize(storage)
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertEqual(storage.mock_calls, [])

    def test_reject_changed_local_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(m, 'ARTIFACTS', Path(directory)):
            expected = proof()
            for name in m.FILES:
                path = Path(directory) / name
                path.write_bytes(b'abcde')
                expected['artifacts'][name].update(m.identity(path))
            m.validate_files(expected)
            (Path(directory) / m.FILES[0]).write_bytes(b'changed')
            with self.assertRaises(RuntimeError):
                m.validate_files(expected)

    def exercise_finish(self, corrupt=False, missing_part=False, changed_proof=False, deferred=False):
        with tempfile.TemporaryDirectory() as directory, patch.object(m, 'LOCAL', Path(directory)), \
                patch.object(m, 'PART_SIZE', 4):
            evidence = {'proof': proof(), 'proof_sha256': 'a' * 64}
            job = {**evidence, 'prefix': m.PREFIX, 'files': {}}
            report = {'proof_sha256': evidence['proof_sha256'], 'files': {}}
            for name in m.FILES:
                info = {'bytes': 5, 'sha256': m.digest(b'abcde'), 'key': m.PREFIX + name, 'upload_id': name}
                job['files'][name] = info
                report['files'][name] = {**{k: info[k] for k in ('bytes', 'sha256')}, 'parts': [
                    {'PartNumber': 1, 'ETag': 'part-1', 'bytes': 4, 'sha256': m.digest(b'abcd')},
                    {'PartNumber': 2, 'ETag': 'part-2', 'bytes': 1, 'sha256': m.digest(b'e')}]}
            if missing_part:
                report['files'][m.FILES[0]]['parts'].pop()
            (Path(directory) / 'job.json').write_text(json.dumps(job))
            releases = []

            class Storage:
                def get_paginator(self, name):
                    return self

                def paginate(self, **kwargs):
                    return [{'Parts': [{'PartNumber': 1, 'ETag': 'part-1', 'Size': 4},
                                       {'PartNumber': 2, 'ETag': 'part-2', 'Size': 1}]}]

                def complete_multipart_upload(self, **kwargs):
                    return {'ETag': 'object'}

                def head_object(self, **kwargs):
                    return {'ETag': 'object', 'ContentLength': 5,
                            'Metadata': {'proof-sha256': 'a' * 64, 'sha256': m.digest(b'abcde')}}

                def get_object(self, **kwargs):
                    if kwargs['Key'].endswith('release.json'):
                        return {'Body': io.BytesIO(releases[-1])}
                    assert not deferred, 'Deferred mode unexpectedly reread the remote object'
                    assert kwargs['IfMatch'] == 'object'
                    start, end = map(int, kwargs['Range'].removeprefix('bytes=').split('-'))
                    data = (b'wrong' if corrupt else b'abcde')[start:end + 1]
                    return {'Body': io.BytesIO(data), 'ETag': 'object',
                            'ContentRange': f'bytes {start}-{end}/5', 'ContentLength': len(data)}

                def put_object(self, **kwargs):
                    releases.append(kwargs['Body'])

            observed = copy.deepcopy(evidence)
            if changed_proof:
                observed['proof_sha256'] = 'b' * 64
            with patch.object(m, 'EXPORT_ONLY', deferred), patch.object(m, 'check', return_value=observed), \
                    patch.object(m, 'ssh', return_value=json.dumps(report).encode()), \
                    patch.object(m, 'require_absent'), \
                    patch.object(m, 'put_release', side_effect=lambda s3, raw: s3.put_object(Body=raw)):
                if corrupt or missing_part or changed_proof:
                    with self.assertRaises(RuntimeError):
                        m.finish(Storage())
                    self.assertEqual(releases, [])
                    self.assertFalse((Path(directory) / 'release.json').exists())
                else:
                    m.finish(Storage())
                    release = json.loads(releases[0])
                    self.assertEqual(release['full_remote_sha256_verified'], not deferred)
                    self.assertEqual(release['independent_mpt_reconstruction_verified'], not deferred)
                    self.assertEqual(release['verification_deferred_by_user'], deferred)
                    self.assertFalse(release['shadowfork_finality_established'])
                    self.assertFalse(release['cross_client_imports_verified'])
                    self.assertIsNone(release['genesis_time'])
                    self.assertEqual(set(release['files']), set(m.FILES))

    def test_deferred_mode_reports_transport_scope_without_remote_reread(self):
        self.exercise_finish(deferred=True)

    def test_corrupt_remote_object_never_releases(self):
        self.exercise_finish(corrupt=True)

    def test_missing_part_never_releases(self):
        self.exercise_finish(missing_part=True)

    def test_changed_proof_never_releases(self):
        self.exercise_finish(changed_proof=True)

    def test_release_requires_all_three_full_readbacks(self):
        self.exercise_finish()

    def test_stream_refuses_checksum_mismatch_even_after_successful_puts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / 'artifacts'
            remote = root / 'remote'
            artifacts.mkdir()
            remote.mkdir()
            expected = proof()
            for name in m.FILES:
                path = artifacts / name
                path.write_bytes(b'wrong')
                expected['artifacts'][name].update(m.identity(path))
            evidence = {'proof': expected, 'proof_sha256': 'a' * 64}
            job = {**evidence, 'prefix': m.PREFIX, 'part_size': m.PART_SIZE,
                   'files': {name: {'key': m.PREFIX + name, 'bytes': 5,
                                    'sha256': m.digest(b'abcde'), 'urls': ['https://unused.invalid']}
                             for name in m.FILES}}
            (remote / 'authorization.json').write_text(json.dumps(job))
            with patch.object(m, 'REMOTE', remote), patch.object(m, 'ARTIFACTS', artifacts), \
                    patch.object(m, 'remote_readiness', return_value=evidence), \
                    patch.object(m, 'put_part', return_value={'PartNumber': 1, 'ETag': 'part', 'bytes': 5, 'sha256': m.digest(b'wrong')}):
                with self.assertRaisesRegex(RuntimeError, 'checksum mismatch'):
                    m.stream()
            self.assertFalse((remote / 'parts-complete.json').exists())

    def test_installed_sdk_signs_conditional_header_and_removes_hook_afterwards(self):
        import boto3
        from botocore.config import Config
        client = boto3.client('s3', endpoint_url='https://unused.invalid', region_name='auto',
                              aws_access_key_id='fixture', aws_secret_access_key='fixture',
                              config=Config(signature_version='s3v4', retries={'max_attempts': 0}))
        sent = []

        class CapturedBeforeNetwork(Exception):
            pass

        def capture(request, **kwargs):
            sent.append(dict(request.headers))
            raise CapturedBeforeNetwork()

        client.meta.events.register('before-send.s3.PutObject', capture)
        with self.assertRaises(CapturedBeforeNetwork):
            m.put_release(client, b'{}')
        self.assertEqual(sent[0]['If-None-Match'], b'*')
        self.assertIn(b'if-none-match', sent[0]['Authorization'])
        with self.assertRaises(CapturedBeforeNetwork):
            client.put_object(Bucket='fixture-bucket', Key='ordinary', Body=b'{}')
        self.assertNotIn('If-None-Match', sent[1])


if __name__ == '__main__':
    unittest.main()
