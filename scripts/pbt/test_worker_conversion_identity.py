"""Reject confusing the older exporter, another worker, or stale H evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'qualify_worker', Path(__file__).with_name('qualify-worker.py'))
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

JOBS = Path(__file__).resolve().parents[2] / 'ansible/inventories/pbt-1/files/qualification-jobs.json'


class ConversionIdentity(unittest.TestCase):
    def setUp(self):
        self.job = json.loads(JOBS.read_text())['lighthouse-erigon-2']
        self.db = Path('/data/pbt-1/erigon')
        self.started = {
            'host': 'glamsterdam-pbt-1-' + self.job['host'],
            'source': str(self.db), 'target_block': self.job['head'],
            'target_hash': self.job['head_hash'],
            'target_state_root': self.job['state_root'],
            'commit': self.job['commit'],
            'rollback_sha256': self.job['archive_sha256'],
        }
        self.complete = {'source': str(self.db), 'target_block': self.job['head']}

    def check(self):
        worker.validate_erigon_conversion_identity(
            self.job, self.db, self.started, self.complete)

    def test_each_worker_requires_its_own_proof_and_memory_limit(self):
        jobs = json.loads(JOBS.read_text())
        for host, memory in [('lighthouse-erigon-1', 32), ('lighthouse-erigon-2', 16)]:
            with self.subTest(host=host):
                self.job = jobs[host]
                self.assertEqual(self.job['memory_gib'], memory)
                self.started['host'] = 'glamsterdam-pbt-1-' + host
                self.check()

    def test_other_host_proof_rejected(self):
        self.started['host'] = 'glamsterdam-pbt-1-lighthouse-erigon-1'
        with self.assertRaises(AssertionError):
            self.check()

    def test_exporter_path_rejected_in_either_record(self):
        for proof in (self.started, self.complete):
            with self.subTest(proof=proof):
                proof['source'] = '/data/pbt-1/rehearsal-24453558/erigon'
                with self.assertRaises(AssertionError):
                    self.check()
                proof['source'] = str(self.db)

    def test_older_block_rejected_in_either_record(self):
        for proof in (self.started, self.complete):
            proof['target_block'] = 24452538
            with self.assertRaises(AssertionError):
                self.check()
            proof['target_block'] = self.job['head']

    def test_wrong_build_hash_root_or_rollback_rejected(self):
        original = copy.deepcopy(self.started)
        for field in ('target_hash', 'target_state_root', 'commit', 'rollback_sha256'):
            with self.subTest(field=field):
                self.started = {**original, field: 'different'}
                with self.assertRaises(AssertionError):
                    self.check()

    def test_wrong_memory_limit_rejected(self):
        self.job['memory_gib'] = 32
        with self.assertRaises(AssertionError):
            self.check()

    def test_missing_provenance_rejected(self):
        del self.started['host']
        with self.assertRaises(KeyError):
            self.check()

    def test_patched_converter_requires_original_verification_and_exact_patch(self):
        build = {
            'base_commit': '372df0e68f52f9975370bff38dee6e41aefff0d7',
            'patch_sha256': '4b04368aad6cf9ee38058eb5d6e6bed79ac251a49138b9c9c28a0c6455483ab9',
            'binary_sha256': '1f807caefedc534ae837641ebff1dfdc37c0378ea8e3556263bddd1eb276e9f3',
            'independent_verifier_sha256': 'c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03',
        }
        phases = {'convert-v3': {'converter_build': build, 'binary_sha256': build['binary_sha256']}}
        for name in ('verify-v3-files', 'restore-head-block', 'verify-v3-state'):
            command = ['original', 'stage_exec'] if name == 'restore-head-block' else ['original', 'commitment', 'verify']
            phases[name] = {'exit_code': 0, 'binary_sha256': build['independent_verifier_sha256'], 'command': command}
        self.assertEqual(worker.validate_erigon_converter_build({'converter_build': build}, phases), build)
        for field in ('base_commit', 'patch_sha256', 'binary_sha256', 'independent_verifier_sha256'):
            with self.subTest(field=field), self.assertRaises(AssertionError):
                worker.validate_erigon_converter_build({'converter_build': {**build, field: 'wrong'}}, phases)
        for name in ('verify-v3-files', 'restore-head-block', 'verify-v3-state'):
            altered = copy.deepcopy(phases)
            altered[name]['binary_sha256'] = build['binary_sha256']
            with self.subTest(phase=name), self.assertRaises(AssertionError):
                worker.validate_erigon_converter_build({'converter_build': build}, altered)

    def test_ordinary_conversion_does_not_invent_patch_provenance(self):
        self.assertIsNone(worker.validate_erigon_converter_build({}, {}))


if __name__ == '__main__':
    unittest.main()
