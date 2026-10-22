"""Export gates must reject the wrong state and never accept unverified files."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('export_anchor', Path(__file__).with_name('export-erigon-anchor.py'))
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


def anchor():
    return {'anchor': export.BLOCK, 'source_datadir': str(export.SOURCE), 'image': export.IMAGE,
            'head': {'number': hex(export.BLOCK), 'hash': export.BLOCK_HASH, 'stateRoot': export.MPT_ROOT},
            **{key: True for key in ('clean_reopen_verified', 'anchor_body_verified', 'stopped',
                                    'v3_mpt_preparation_verified', 'stop_after_block_boundary_verified',
                                    'stage_exec_at_anchor_passed')}}


def metadata():
    return {'chainId': '1', 'block': export.BLOCK, 'blockHash': export.BLOCK_HASH,
            'stateRoot': export.MPT_ROOT, 'hashSuite': 'blake3', 'pbtRoot': '0x' + '12' * 32,
            'snapshotDigest': '0x' + '34' * 32, 'preimageDigest': '0x' + '56' * 32,
            'txNum': 100, 'headerCount': 1, 'codeGroupCount': 0, 'storageCount': 0,
            'finalized': False}


class ExportGates(unittest.TestCase):
    def test_only_verified_stopped_anchor_can_export(self):
        export.validate_anchor(anchor())
        for key, value in [('anchor', 24503958), ('source_datadir', '/data/pbt-1/erigon'),
                           ('image', 'unqualified'), ('stopped', False),
                           ('clean_reopen_verified', False), ('stage_exec_at_anchor_passed', False)]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                export.validate_anchor({**anchor(), key: value})
        for key in ('hash', 'stateRoot', 'number'):
            proof = copy.deepcopy(anchor())
            proof['head'][key] = '0x01'
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                export.validate_anchor(proof)

    def test_metadata_rejects_wrong_anchor_suite_and_malformed_digests(self):
        export.validate_metadata(metadata())
        for key, value in [('block', 24503958), ('blockHash', '0x' + '00' * 32),
                           ('stateRoot', '0x' + '00' * 32), ('hashSuite', 'keccak'),
                           ('chainId', '2'), ('pbtRoot', '0x12'), ('snapshotDigest', 'missing'),
                           ('preimageDigest', '0x' + 'gg' * 32), ('headerCount', 0),
                           ('storageCount', True), ('finalized', 'true')]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                export.validate_metadata({**metadata(), key: value})

    def test_missing_anchor_proof_is_a_read_only_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(export.socket, 'gethostname', return_value='glamsterdam-pbt-1-lighthouse-erigon-1'), \
                    patch.object(export, 'ANCHOR', root / 'anchor'), \
                    patch.object(export.subprocess, 'check_output') as execute:
                with self.assertRaises(FileNotFoundError):
                    export.check()
                execute.assert_not_called()
                self.assertEqual(list(root.iterdir()), [])

    def test_native_commands_verify_the_exported_pair_at_N(self):
        commands = export.commands()
        self.assertIn('--experimental.bin-commitment.hash=blake3', commands['export'])
        self.assertIn('--block=24453558', commands['verify'])
        self.assertIn('--snapshot=' + str(export.OUTPUT / 'pbt-snapshot.bin'), commands['verify'])
        self.assertIn('--preimages=' + str(export.OUTPUT / 'framed.bin'), commands['verify'])
        for command in commands.values():
            self.assertEqual(command[0], str(export.BINARY))
            self.assertIn('--datadir=' + str(export.SOURCE), command)

    def exercise_run(self, mode):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            anchor_path, upgrade = root / 'anchor', root / 'upgrade'
            anchor_path.mkdir()
            upgrade.mkdir()
            (anchor_path / 'job.lock').touch()
            (upgrade / 'upgrade.lock').touch()
            (anchor_path / 'complete.json').write_text('{}')
            control, output = root / 'control', root / 'output'
            binary = root / 'erigon'
            binary.write_bytes(b'fixture')
            readiness = {'anchor_proof_sha256': export.sha(anchor_path / 'complete.json')}
            phases = []

            def native(label, command):
                phases.append(label)
                if mode == label + '-failure':
                    raise RuntimeError('Native failure')
                if label == 'export':
                    (output / 'pbt-snapshot.bin').write_bytes(b'snapshot')
                    (output / 'framed.bin').write_bytes(b'preimages')
                    (output / 'pbt-snapshot.meta.json').write_text(json.dumps(metadata()))
                if label == 'verify' and mode == 'changed-artifact':
                    (output / 'framed.bin').write_bytes(b'changed')

            with patch.object(export, 'ANCHOR', anchor_path), patch.object(export, 'UPGRADE', upgrade), \
                    patch.object(export, 'CONTROL', control), patch.object(export, 'OUTPUT', output), \
                    patch.object(export, 'BINARY', binary), patch.object(export, 'BINARY_SHA', export.sha(binary)), \
                    patch.object(export, 'check', return_value=readiness), \
                    patch.object(export, 'run_native', side_effect=native):
                if mode == 'success':
                    export.run()
                    report = json.loads((control / 'complete.json').read_text())
                    self.assertFalse(report['shadowfork_finality_established'])
                    self.assertFalse(report['cross_client_imports_verified'])
                    self.assertFalse(report['uploaded'])
                    self.assertEqual(len(report['artifacts']), 3)
                else:
                    with self.assertRaises(RuntimeError):
                        export.run()
                    self.assertFalse((control / 'complete.json').exists())
                    self.assertEqual(json.loads((control / 'status.json').read_text())['phase'], 'failed')
                self.assertEqual(phases, ['export'] if mode == 'export-failure' else ['export', 'verify'])

    def test_export_failure_never_runs_verifier(self):
        self.exercise_run('export-failure')

    def test_verifier_failure_never_publishes_success(self):
        self.exercise_run('verify-failure')

    def test_changed_artifact_never_publishes_success(self):
        self.exercise_run('changed-artifact')

    def test_complete_keeps_finality_and_import_gates_separate(self):
        self.exercise_run('success')


if __name__ == '__main__':
    unittest.main()
