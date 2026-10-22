import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('anchor_handoff', Path(__file__).with_name('handoff-erigon-anchor.py'))
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class AnchorHandoff(unittest.TestCase):
    def test_running_failed_or_unclean_units_do_not_release_hold(self):
        good = {'ActiveState': 'inactive', 'MainPID': '0', 'Result': 'success'}
        handoff.require_stopped_success({'unit': good})
        for field, value in [('ActiveState', 'active'), ('ActiveState', 'failed'),
                             ('MainPID', '42'), ('Result', 'exit-code')]:
            with self.subTest(field=field), self.assertRaises(AssertionError):
                handoff.require_stopped_success({'unit': {**good, field: value}})

    def test_live_read_only_check_stops_before_loading_driver(self):
        with patch.object(handoff.socket, 'gethostname', return_value='glamsterdam-pbt-1-lighthouse-erigon-1'), \
                patch.object(handoff, 'unit', return_value={'MainPID': '123', 'ActiveState': 'active', 'Result': 'success'}), \
                patch.object(handoff, 'sha') as digest, \
                patch.object(handoff.subprocess, 'run') as run:
            with self.assertRaises(AssertionError):
                handoff.check()
            digest.assert_not_called()
            run.assert_not_called()

    def test_failed_predecessor_never_starts_anchor_driver(self):
        with patch.object(handoff, 'unit', return_value={'ActiveState': 'failed'}), \
                patch.object(handoff, 'check') as check, \
                patch.object(handoff.subprocess, 'run') as run:
            with self.assertRaises(AssertionError):
                handoff.wait_and_run()
            check.assert_not_called()
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
