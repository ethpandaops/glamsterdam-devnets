import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('handoff', Path(__file__).with_name('resume-erigon-bounded-conversion.py'))
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class HandoffIdentity(unittest.TestCase):
    def test_only_original_live_H_conversion_can_be_interrupted(self):
        status = {'phase': 'convert-v3', 'target_block': 24503958}
        command = [str(handoff.ORIGINAL), 'commitment', 'convert', '--datadir=' + str(handoff.SOURCE), '--chain=mainnet', '--v3']
        handoff.validate_running_process(status, command, handoff.ORIGINAL_SHA)
        for altered in ({**status, 'phase': 'verify-v3-files'}, {**status, 'target_block': 24452538}):
            with self.assertRaises(AssertionError):
                handoff.validate_running_process(altered, command, handoff.ORIGINAL_SHA)
        for altered in (command + ['--continue'], [str(handoff.CANDIDATE), *command[1:]],
                        [arg.replace('/data/pbt-1/erigon', '/data/pbt-1/rehearsal-24453558/erigon') for arg in command]):
            with self.assertRaises(AssertionError):
                handoff.validate_running_process(status, altered, handoff.ORIGINAL_SHA)
        with self.assertRaises(AssertionError):
            handoff.validate_running_process(status, command, handoff.CANDIDATE_SHA)


if __name__ == '__main__':
    unittest.main()
