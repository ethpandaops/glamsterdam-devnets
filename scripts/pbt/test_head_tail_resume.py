import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('tail', Path(__file__).with_name('resume-erigon-head-tail.py'))
tail = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tail)


class TailResumeGate(unittest.TestCase):
    def proofs(self):
        return [
            {'reason': 'increase_native_tail_batch_512MiB_to_4GiB', 'target_block': 24503958,
             'native_binary_sha256': tail.NATIVE_SHA, 'native_pid': 88242,
             'native_start_ticks': '6041299', 'wrapper_pid': 23668},
            {'native_gone': True, 'wrapper_gone': True, 'forced_kill': False,
             'native_completion_proof_absent': True},
            {'exit_code': 0},
            {'exit_code': 0, 'binary_sha256': tail.NATIVE_SHA,
             'command': [str(tail.NATIVE), 'commitment', 'verify', '--datadir=/data/pbt-1/erigon'],
             'commitment_v3_env': True, 'no_prune_env': 'true'},
        ]

    def test_reviewed_handoff_accepts(self):
        tail.validate_stop(*self.proofs())

    def test_unverified_or_live_state_rejected(self):
        for index, key, value in [
            (0, 'target_block', 24453558), (0, 'native_pid', 47602),
            (0, 'native_start_ticks', 'changed'), (0, 'native_binary_sha256', 'other'),
            (1, 'native_gone', False), (1, 'wrapper_gone', False),
            (1, 'forced_kill', True), (1, 'native_completion_proof_absent', False),
            (2, 'exit_code', 1), (3, 'exit_code', 1), (3, 'binary_sha256', 'candidate'),
            (3, 'no_prune_env', 'false'), (3, 'commitment_v3_env', False),
            (3, 'command', [str(tail.NATIVE), 'commitment', 'verify', '--datadir=/wrong']),
        ]:
            proofs = copy.deepcopy(self.proofs())
            proofs[index][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(AssertionError):
                tail.validate_stop(*proofs)


if __name__ == '__main__':
    unittest.main()
