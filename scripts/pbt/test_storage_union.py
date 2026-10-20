import copy
from types import SimpleNamespace
import unittest

from storage_union import PARAMS, qualified_environment, verify_warmup
from test_buffer_pilot import module


class StorageWarmup(unittest.TestCase):
    def setUp(self):
        self.head = {'number': '0x123', 'hash': 'head'}
        self.value = '0x'+'00'*32
        self.move_head = False
        self.current = self.head
        self.rpc = SimpleNamespace(head=lambda: self.current, call=self.call)

    def call(self, method, params, *, timeout):
        self.assertEqual((method, params, timeout), ('eth_getStorageAt', PARAMS, 1800))
        if self.move_head:
            self.current = {'number': '0x124', 'hash': 'changed'}
        return self.value

    def test_compares_pinned_value_without_changing_head(self):
        baseline = verify_warmup(self.rpc, self.head)
        result = verify_warmup(self.rpc, self.head, baseline)
        self.assertTrue(result['head_unchanged'])
        self.assertTrue(result['pinned_value_verified'])

    def test_head_change_is_fatal(self):
        self.move_head = True
        with self.assertRaises(AssertionError):
            verify_warmup(self.rpc, self.head)

    def test_different_native_value_is_fatal(self):
        baseline = verify_warmup(self.rpc, self.head)
        self.value = '0x'+'01'*32
        with self.assertRaises(AssertionError):
            verify_warmup(self.rpc, self.head, baseline)

    def test_other_baseline_head_or_slot_is_fatal(self):
        baseline = verify_warmup(self.rpc, self.head)
        for field, value in [('head', {}), ('params', [])]:
            wrong = {**baseline, field: value}
            with self.assertRaises(AssertionError):
                verify_warmup(self.rpc, self.head, wrong)


class UnionBuildGate(unittest.TestCase):
    def setUp(self):
        module.configure('union-64')
        self.addCleanup(module.configure, 'buffer-64')
        self.build = {'sha256': 'candidate', 'source': {
            'continuation_commit': '72b4a99bbb46a61ce3ab0932111533da8cb9fcda',
            'union_commit': 'a'*40, 'union_environment': {'DOMAIN_STORAGE_UNION': 'true'},
            'union_parent_binary_sha256': 'qualified-parent'}}
        self.proof = {'status': {'phase': 'verified_stopped', 'all_bodies_verified_before_and_after': True},
                      'timing': {'binary': {'sha256': 'qualified-parent'}}}

    def test_candidate_requires_qualified_parent_and_exact_environment(self):
        module.verify_build(self.build, self.proof, 'candidate')
        self.assertEqual((module.PILOT.name, module.BINARY.name, module.BATCH_SIZE, module.BUFFER, module.BLOCKS),
                         ('native-union-pilot', 'erigon-native-union', 64, '2G', 256))

    def test_mismatched_parent_or_disabled_union_is_fatal(self):
        for field, value in [('union_parent_binary_sha256', 'other'), ('union_environment', {})]:
            wrong = copy.deepcopy(self.build)
            wrong['source'][field] = value
            with self.assertRaises(AssertionError):
                module.verify_build(wrong, self.proof, 'candidate')

    def test_wrong_candidate_binary_is_fatal(self):
        with self.assertRaises(AssertionError):
            module.verify_build(self.build, self.proof, 'other')

    def test_full_replay_requires_the_qualified_environment_and_warmup(self):
        proof = copy.deepcopy(self.proof)
        proof['timing'].update(environment={'DOMAIN_STORAGE_UNION': 'true'},
                               filter_warmup={'head_unchanged': True, 'pinned_value_verified': True})
        self.assertEqual(qualified_environment(self.build, proof), {'DOMAIN_STORAGE_UNION': 'true'})
        for change in ['environment', 'head_unchanged', 'pinned_value_verified']:
            wrong = copy.deepcopy(proof)
            if change == 'environment':
                wrong['timing']['environment'] = {}
            else:
                wrong['timing']['filter_warmup'][change] = False
            with self.assertRaises(AssertionError):
                qualified_environment(self.build, wrong)

    def test_legacy_build_cannot_inherit_union_environment(self):
        self.assertEqual(qualified_environment({'source': {}}, {'timing': {}}), {})
        with self.assertRaises(AssertionError):
            qualified_environment({'source': {}}, {'timing': {'environment': {'DOMAIN_STORAGE_UNION': 'true'}}})


if __name__ == '__main__':
    unittest.main()
