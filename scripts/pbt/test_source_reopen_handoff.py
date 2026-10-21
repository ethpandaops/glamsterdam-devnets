"""Ensure native reopening cannot overlap conversion or use the H worker proof."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'source_reopen', Path(__file__).with_name('verify-erigon-v3-source.py'))
reopen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reopen)


class SourceReopenHandoff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.records = {
            'status.json': {'phase': 'converted_pending_native_reopen'},
            'started.json': {'source': str(reopen.SOURCE), 'source_block': reopen.ANCHOR,
                             'integration_sha256': reopen.INTEGRATION_SHA},
            'conversion-complete.json': {'source': str(reopen.SOURCE),
                                         'target_block': reopen.ANCHOR},
        }
        for phase in ('convert-v3', 'verify-v3-files', 'restore-source-block', 'verify-v3-state'):
            self.records[phase + '.json'] = {
                'exit_code': 0, 'no_prune_env': 'true',
                'command': ['integration', '--datadir=' + str(reopen.SOURCE),
                            '--block=' + str(reopen.ANCHOR)]}

    def check(self, state='inactive', pid='0'):
        for name, record in self.records.items():
            (self.root / name).write_text(json.dumps(record))
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch.object(reopen, 'ROOT', self.root), \
                patch.object(reopen.socket, 'gethostname',
                             return_value='glamsterdam-pbt-1-lighthouse-erigon-1'), \
                patch.object(reopen.subprocess, 'check_output',
                             return_value=f'ActiveState={state}\nMainPID={pid}\nResult=success\n'):
            try:
                reopen.require_completed_conversion()
            finally:
                self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_success_is_read_only(self):
        self.check()

    def test_live_converter_rejected_even_with_complete_file(self):
        with self.assertRaisesRegex(AssertionError, 'not stopped'):
            self.check('active', '123')

    def test_h_worker_proof_rejected(self):
        self.records['conversion-complete.json'].update(
            source='/data/pbt-1/erigon', target_block=24503958)
        with self.assertRaises(AssertionError):
            self.check()

    def test_failed_verification_rejected(self):
        self.records['verify-v3-state.json']['exit_code'] = 1
        with self.assertRaises(AssertionError):
            self.check()

    def test_tail_reconstruction_without_bal_retention_rejected(self):
        self.records['restore-source-block.json']['no_prune_env'] = None
        with self.assertRaises(AssertionError):
            self.check()

    def test_other_database_in_phase_command_rejected(self):
        self.records['verify-v3-files.json']['command'] = ['integration', '--datadir=/data/pbt-1/erigon']
        with self.assertRaises(AssertionError):
            self.check()


class ReopenNamespace(unittest.TestCase):
    def check(self, native='net:[2]', audit='net:[2]', host='net:[1]', pids=('123', '123')):
        links = {'/proc/123/ns/net': native, '/proc/self/ns/net': audit, '/proc/1/ns/net': host}
        with patch.object(reopen, 'show', side_effect=pids), \
                patch.object(reopen.os, 'readlink', side_effect=links.__getitem__):
            return reopen.require_audit_namespace()

    def test_private_namespace_identity_is_recorded(self):
        self.assertEqual(self.check(), {'native_pid': 123, 'network_namespace': 'net:[2]',
                                        'audit_namespace': 'net:[2]'})

    def test_audit_in_host_namespace_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'wrong network namespace'):
            self.check(audit='net:[1]')

    def test_client_without_private_namespace_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'not in its private'):
            self.check(native='net:[1]', audit='net:[1]')

    def test_stopped_or_replaced_client_is_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'stopped'):
            self.check(pids=('0',))
        with self.assertRaisesRegex(AssertionError, 'changed'):
            self.check(pids=('123', '456'))


if __name__ == '__main__':
    unittest.main()
