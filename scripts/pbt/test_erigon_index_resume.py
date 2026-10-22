"""Check recovery refuses incomplete or mismatched evidence before mutation."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'upgrade', Path(__file__).with_name('upgrade-erigon-v3.py'))
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


class IndexRecoveryGate(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root, self.source = base / 'upgrade', base / 'source'
        self.recovery = base / 'v3-source-index-recovery'
        for p in (self.root / 'original-checkpoint/snapshots/domain',
                  self.source / 'snapshots/domain',
                  self.source / 'snapshots/rebuild/domain',
                  self.recovery / 'datadir/snapshots/domain'):
            p.mkdir(parents=True)
        self.data = self.source / 'snapshots/rebuild/domain/v2.2-commitment.0-1024000.kv'
        self.data.write_bytes(b'completed data')
        os.link(self.data, self.recovery / 'datadir/snapshots/domain' / self.data.name)
        original = self.source / 'snapshots/domain/v1.1-commitment.0-1024000.kv'
        original.write_bytes(b'original')
        os.link(original, self.root / 'original-checkpoint/snapshots/domain' / original.name)
        for p in (self.source / 'snapshots', self.recovery / 'datadir/snapshots'):
            (p / 'erigondb.toml').write_text('step_size = 3125\n')
        self.index = self.recovery / 'datadir/snapshots/domain/v2.1-commitment.0-1024000.kvi'
        self.index.write_bytes(b'new offsets')
        self.write(self.root / 'status.json', {
            'phase': 'failed',
            'error': 'Local free space below 150 GB; interrupted before exhausting disk'})
        (self.root / 'unsqueeze.log').write_text('build commitment values idx: context canceled')
        self.write(self.recovery / 'status.json', {'phase': 'indexes_built_pending_review'})
        self.complete = {'exit_code': 0, 'data_file_unchanged': True, 'promoted': False,
                         'generated_files': [{'name': self.index.name,
                                              'bytes': self.index.stat().st_size}]}
        self.write(self.recovery / 'complete.json', self.complete)
        stat = self.data.stat()
        self.write(self.recovery / 'started.json', {
            'source_data': str(self.data), 'source_inode': stat.st_ino,
            'source_bytes': stat.st_size, 'source_mtime_ns': stat.st_mtime_ns})
        for target, value in (('ROOT', self.root), ('SOURCE', self.source)):
            mock = patch.object(upgrade, target, value)
            mock.start()
            self.addCleanup(mock.stop)
        for mock in (
                patch.object(upgrade.socket, 'gethostname',
                             return_value='glamsterdam-pbt-1-lighthouse-erigon-1'),
                patch.object(upgrade.subprocess, 'check_output', return_value='0')):
            mock.start()
            self.addCleanup(mock.stop)

    @staticmethod
    def write(path, data):
        path.write_text(json.dumps(data))

    def test_completed_recovery_is_read_only_and_selects_continue(self):
        before = (self.root / 'status.json').read_bytes()
        proof = upgrade.index_resume_inputs()
        self.assertEqual(proof['resume_options'], ['--squeeze=false', '--continue'])
        self.assertEqual((self.root / 'status.json').read_bytes(), before)
        self.assertEqual(list(self.data.parent.iterdir()), [self.data])

    def test_running_index_job_cannot_be_promoted(self):
        with patch.object(upgrade.subprocess, 'check_output', return_value='123456'):
            with self.assertRaises(AssertionError):
                upgrade.index_resume_inputs()

    def test_missing_accessor_is_rejected(self):
        self.index.unlink()
        with self.assertRaises(FileNotFoundError):
            upgrade.index_resume_inputs()

    def test_modified_data_file_is_rejected(self):
        self.data.write_bytes(b'changed')
        with self.assertRaises(AssertionError):
            upgrade.index_resume_inputs()

    def test_snapshot_settings_mismatch_is_rejected(self):
        (self.source / 'snapshots/erigondb.toml').write_text('step_size = 390625\n')
        with self.assertRaises(AssertionError):
            upgrade.index_resume_inputs()

    def test_unexpected_accessor_range_is_rejected(self):
        self.complete['generated_files'][0]['name'] = 'v2.1-commitment.1024000-1040000.kvi'
        self.write(self.recovery / 'complete.json', self.complete)
        with self.assertRaises(AssertionError):
            upgrade.index_resume_inputs()

    def test_additional_rebuild_shard_requires_review(self):
        (self.data.parent / 'v2.2-commitment.1024000-1040000.kv').write_bytes(b'partial')
        with self.assertRaises(AssertionError):
            upgrade.index_resume_inputs()


if __name__ == '__main__':
    unittest.main()
