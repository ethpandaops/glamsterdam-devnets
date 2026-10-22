"""Check that preparation refuses unverified recovery and altered replay input."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    'anchor', Path(__file__).with_name('prepare-erigon-anchor.py'))
anchor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(anchor)


class AnchorGates(unittest.TestCase):
    def test_metrics_read_only_root_mount_is_allowed(self):
        info = {'Name': '/node_exporter', 'Mounts': [{'Source': '/', 'RW': False}]}
        with patch.object(anchor, 'command', side_effect=['metrics', json.dumps([info])]):
            anchor.require_unused_database(Path('/data/pbt-1/rehearsal-24453558/erigon'))

    def test_other_overlapping_mounts_are_rejected(self):
        db = Path('/data/pbt-1/rehearsal-24453558/erigon')
        for name, source, writable in [('/node_exporter', '/', True), ('/other', '/', False),
                                      ('/node_exporter', str(db), False),
                                      ('/client', str(db / 'chaindata'), True)]:
            info = {'Name': name, 'Mounts': [{'Source': source, 'RW': writable}]}
            with self.subTest(info=info), \
                    patch.object(anchor, 'command', side_effect=['container', json.dumps([info])]), \
                    self.assertRaisesRegex(AssertionError, 'overlaps exporter database'):
                anchor.require_unused_database(db)

    def test_missing_v3_reopen_proof_prevents_any_client_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(anchor, 'CONTROL', root / 'anchor'), \
                    patch.object(anchor, 'UPGRADE', root / 'upgrade'), \
                    patch.object(anchor.subprocess, 'check_output') as execute:
                with self.assertRaises(FileNotFoundError):
                    anchor.main()
                execute.assert_not_called()

    def test_worker_head_proof_cannot_qualify_the_older_exporter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'upload-ready.json').write_text(json.dumps({
                'source': '/data/pbt-1/erigon', 'stopped': True,
                'native_reopen_verified': True, 'v3_state_verified': True,
                'commit': anchor.COMMIT,
                'head': {'number': hex(24503958)}}))
            with patch.object(anchor, 'UPGRADE', root), \
                    patch.object(anchor.subprocess, 'check_output') as execute:
                with self.assertRaises(AssertionError):
                    anchor.require_v3_source()
                execute.assert_not_called()

    def test_review_hold_prevents_any_client_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'instruction-review-hold.json').write_text('{}')
            with patch.object(anchor, 'CONTROL', root), \
                    patch.object(anchor.subprocess, 'check_output') as execute:
                with self.assertRaisesRegex(AssertionError, 'Instruction review hold'):
                    anchor.main()
                execute.assert_not_called()

    def test_download_must_be_verified_and_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(anchor, 'RECOVERY', root), patch.object(Path, 'is_mount', return_value=True):
                self.assertFalse(anchor.recovery_ready())
                archive = root / 'erigon-24503958.tar.zst'
                archive.write_bytes(b'fixture')
                proof = {'sha256': anchor.RECOVERY_SHA, 'bytes': 7,
                         'mtime_ns': archive.stat().st_mtime_ns}
                (root / 'archive-verified.json').write_text(json.dumps(proof))
                with patch.object(anchor, 'RECOVERY_BYTES', 7):
                    self.assertTrue(anchor.recovery_ready())
                    archive.write_bytes(b'changed archive')
                    with self.assertRaises(AssertionError):
                        anchor.recovery_ready()

    def test_replay_rejects_tampering_even_with_valid_parent_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = {'number': anchor.ANCHOR + 1, 'hash': 'fixture',
                    'new_payload': [{'parentHash': anchor.ANCHOR_HASH}]}
            payload = gzip.compress(json.dumps(item).encode())
            path = root / f'{anchor.ANCHOR + 1:08d}.json.gz'
            path.write_bytes(payload)
            with patch.object(anchor, 'BLOCKS', root), \
                    patch.object(anchor, 'TARGET', anchor.ANCHOR + 1), \
                    patch.object(anchor, 'PREFIX_SHA', hashlib.sha256(payload).hexdigest()):
                self.assertEqual(anchor.verify_prefix()['target_hash'], 'fixture')
                item['hash'] = 'altered'
                path.write_bytes(gzip.compress(json.dumps(item).encode()))
                with self.assertRaises(AssertionError):
                    anchor.verify_prefix()

    def test_replay_rejects_discontinuous_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = gzip.compress(json.dumps({
                'number': anchor.ANCHOR + 1, 'hash': 'fixture',
                'new_payload': [{'parentHash': 'wrong-parent'}]}).encode())
            (root / f'{anchor.ANCHOR + 1:08d}.json.gz').write_bytes(payload)
            with patch.object(anchor, 'BLOCKS', root), \
                    patch.object(anchor, 'TARGET', anchor.ANCHOR + 1), \
                    patch.object(anchor, 'PREFIX_SHA', hashlib.sha256(payload).hexdigest()):
                with self.assertRaises(AssertionError):
                    anchor.verify_prefix()

    def test_intentional_stop_requires_exact_target_and_clean_exit(self):
        stopped = {'Running': False, 'OOMKilled': False, 'ExitCode': 0, 'Error': ''}
        marker = ('[Execution] STOP_AFTER_BLOCK reached, exiting without commit '
                  f'(debug mode) block={anchor.TARGET:,}')
        self.assertEqual(anchor.verify_intentional_stop(stopped, marker)['target_block'],
                         anchor.TARGET)
        for key, value in [('Running', True), ('OOMKilled', True), ('ExitCode', 137)]:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                anchor.verify_intentional_stop({**stopped, key: value}, marker)
        for log in ('ordinary shutdown', marker.replace(f'{anchor.TARGET:,}', '24,452,538')):
            with self.subTest(log=log), self.assertRaises(AssertionError):
                anchor.verify_intentional_stop(stopped, log)

    def test_rpc_disconnect_requires_subsequent_exact_stop_evidence(self):
        item = {'number': anchor.TARGET, 'hash': 'target-hash',
                'new_payload': ['fixture'], 'forkchoice': ['fixture']}
        rpc = Mock()
        rpc.call.side_effect = OSError('connection closed by intentional exit')
        stopped = {'Running': False, 'OOMKilled': False, 'ExitCode': 0, 'Error': ''}
        marker = ('[Execution] STOP_AFTER_BLOCK reached, exiting without commit '
                  f'(debug mode) block={anchor.TARGET}')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(anchor, 'CONTROL', root), \
                    patch.object(anchor, 'state', side_effect=[{'Running': True}, stopped]), \
                    patch.object(anchor.subprocess, 'check_output', return_value=marker), \
                    patch.object(anchor.time, 'sleep'):
                proof = anchor.submit_stop_block(rpc, item)
                self.assertEqual(proof['transport_failures'], 1)
                self.assertEqual(proof['payload_hash'], 'target-hash')
                self.assertTrue((root / 'stop-boundary.json').exists())

    def test_crash_after_disconnect_is_not_accepted_as_planned_stop(self):
        rpc = Mock()
        rpc.call.side_effect = OSError('connection lost')
        item = {'number': anchor.TARGET, 'hash': 'target-hash',
                'new_payload': ['fixture'], 'forkchoice': ['fixture']}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(anchor, 'CONTROL', root), \
                    patch.object(anchor, 'state', side_effect=[
                        {'Running': True}, {'Running': False, 'OOMKilled': True, 'ExitCode': 137}]), \
                    patch.object(anchor.subprocess, 'check_output', return_value='OOM'), \
                    patch.object(anchor.time, 'sleep'):
                with self.assertRaises(AssertionError):
                    anchor.submit_stop_block(rpc, item)
                self.assertFalse((root / 'stop-boundary.json').exists())

    def test_invalid_payload_is_not_treated_as_expected_disconnect(self):
        rpc = Mock()
        rpc.call.return_value = {'status': 'INVALID', 'validationError': 'invalid state root'}
        item = {'number': anchor.TARGET, 'hash': 'target-hash',
                'new_payload': ['fixture'], 'forkchoice': ['fixture']}
        with patch.object(anchor, 'state', return_value={'Running': True}):
            with self.assertRaises(AssertionError):
                anchor.submit_stop_block(rpc, item)


if __name__ == '__main__':
    unittest.main()
