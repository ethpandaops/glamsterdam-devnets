"""An automatic handoff must not publish unfinished or failed native output."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('handoff', Path(__file__).with_name('publish-pbt-artifacts-when-ready.py'))
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


class HandoffTests(unittest.TestCase):
    def state(self, active, result='success', proof=False):
        return {'export': {'ActiveState': active, 'Result': result,
                           'MainPID': '123' if active == 'active' else '0'}, 'export_proof': proof}

    def test_live_native_job_is_wait_even_with_early_proof(self):
        self.assertFalse(handoff.phase_ready(self.state('active', proof=True), 'export'))

    def test_failed_native_job_never_qualifies(self):
        with self.assertRaises(AssertionError):
            handoff.phase_ready(self.state('failed', 'exit-code', True), 'export')

    def test_successful_exit_without_proof_never_qualifies(self):
        with self.assertRaises(AssertionError):
            handoff.phase_ready(self.state('inactive'), 'export')

    def test_failed_full_validation_cannot_authorize_upload(self):
        pub = Mock()
        pub.check.side_effect = RuntimeError('Native file hash mismatch')
        state = {'upload': {'LoadState': 'not-found'}, 'upload_proof': False}
        with tempfile.TemporaryDirectory() as directory, patch.object(handoff, 'ROOT', Path(directory)), \
                patch.object(handoff, 'wait_for', return_value=state), patch.object(handoff, 'action') as action:
            with self.assertRaises(RuntimeError):
                handoff.run(pub)
            action.assert_not_called()
            pub.ssh.assert_not_called()


if __name__ == '__main__':
    unittest.main()
