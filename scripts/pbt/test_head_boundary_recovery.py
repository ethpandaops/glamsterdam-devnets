"""Reject live owners, unrelated failures and incomplete replacement coverage."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'head_boundary', Path(__file__).with_name('resume-erigon-head-boundaries.py'))
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class HeadBoundaryRecovery(unittest.TestCase):
    def setUp(self):
        self.fields = {'MainPID': '0', 'ActiveState': 'failed', 'Result': 'exit-code'}
        self.status = {'phase': 'failed', 'target_block': 24503958,
                       'error': 'convert-v3 exited 1; inspect its log'}
        self.log = ('phase 1 file /data/pbt-1/erigon/snapshots/domain/'
                    'v2.2-commitment.1050624-1050625.kv: max step 1050624 '
                    'splits accounts domain file [3283200000,3286400000)')

    def test_only_expected_stopped_failure_is_accepted(self):
        recovery.require_failure(self.fields, self.status, self.log, 42)
        # A newly launched recovery owns the same unit but has not yet changed
        # the preceding failure evidence. No other owner may enter this path.
        recovery.require_failure({'MainPID': '42', 'ActiveState': 'active',
                                  'Result': 'success'}, self.status, self.log, 42)

    def test_live_conversion_owner_is_rejected(self):
        with self.assertRaises(AssertionError):
            recovery.require_failure({'MainPID': '11152', 'ActiveState': 'active',
                                      'Result': 'success'}, self.status, self.log, 42)

    def test_success_or_other_failure_cannot_trigger_recovery(self):
        for key, value in [('phase', 'converted_pending_native_reopen'),
                           ('phase', 'convert-v3'), ('target_block', 24452538),
                           ('error', 'Free space below 150 GB')]:
            with self.subTest(key=key, value=value), self.assertRaises(AssertionError):
                recovery.require_failure(self.fields, {**self.status, key: value}, self.log, 42)
        with self.assertRaises(AssertionError):
            recovery.require_failure(self.fields, self.status,
                                     self.log.replace('1050624 splits', '1049727 splits'), 42)

    @staticmethod
    def fixture():
        plan, manifest, proofs = [], [], {}
        for domain in ('accounts', 'storage'):
            item = {'domain': domain, 'hide': f'v2.0-{domain}.1050624-1051648.kv',
                    'gaps': [], 'replacements': [], 'indexes': []}
            for step in range(1050624, 1051648):
                stem = f'{domain}.{step}-{step + 1}'
                names = [f'{version}-{stem}{ext}' for version, ext in
                         [('v2.0', '.kv'), ('v2.0', '.bt'), ('v1.2', '.kvei')]]
                item['replacements'].append({'name': names[0], 'start': step, 'end': step + 1})
                item['indexes'].append({'file': names[0], 'siblings': names})
                manifest.extend({'dir': 'domain', 'name': name} for name in names)
            for version, ext in [('v2.0', '.kv'), ('v2.0', '.bt'), ('v1.2', '.kvei')]:
                manifest.append({'dir': 'domain', 'name': f'{version}-{domain}.1050624-1051648{ext}'})
            proofs[domain] = {'domain': domain, 'fragments': 1024, 'records': 10,
                              'merged': str(recovery.SOURCE / 'snapshots/domain' / item['hide']),
                              'all_records_equal': True, 'inputs_unchanged': True}
            plan.append(item)
        return plan, manifest, proofs

    def test_full_contiguous_indexed_range_selects_only_six_files(self):
        plan, manifest, proofs = self.fixture()
        before = copy.deepcopy(plan)
        checked, moved = recovery.validate_plan(plan, manifest, proofs)
        self.assertEqual(len(checked), 6144)
        self.assertEqual(len(moved), 6)
        self.assertEqual(plan, before)
        self.assertTrue(all('1050624-1051648.' in f['name'] for f in moved))

    def test_gap_overlap_or_wrong_accessor_is_rejected(self):
        for mutation in ('gap', 'overlap', 'accessor'):
            plan, manifest, proofs = self.fixture()
            if mutation == 'gap':
                plan[0]['replacements'].pop(5)
            elif mutation == 'overlap':
                plan[0]['replacements'][5]['start'] -= 1
            else:
                plan[0]['indexes'][5]['siblings'][1] = 'v2.0-accounts.1050624-1051648.bt'
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                recovery.validate_plan(plan, manifest, proofs)

    def test_failed_comparison_or_wrong_database_is_rejected(self):
        for key, value in [('all_records_equal', False), ('inputs_unchanged', False),
                           ('merged', '/data/pbt-1/rehearsal-24453558/erigon'),
                           ('fragments', 20), ('records', 0)]:
            plan, manifest, proofs = self.fixture()
            proofs['accounts'][key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                recovery.validate_plan(plan, manifest, proofs)


if __name__ == '__main__':
    unittest.main()
