"""The scratch guard may signal only the expected wrapper's native phase."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('guard', Path(__file__).with_name('route-erigon-export-scratch.py'))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class GuardTests(unittest.TestCase):
    def check(self, phase='verify', pid=123, command=None, parent=None, cgroup=None, started='abc'):
        command = command if command is not None else ['pinned', phase]
        return guard.validate_phase_process({'phase': phase, 'pid': pid}, {'native_start_ticks': 'abc'},
            command, ['pinned', phase], parent if parent is not None else guard.WRAPPER_PID,
            cgroup if cgroup is not None else '0::/system.slice/pbt-1-native-anchor-export.service', started)

    def test_expected_verifier_may_have_a_new_pid(self):
        self.check()

    def test_unrelated_parent_or_cgroup_is_rejected(self):
        for override in ({'parent': 1}, {'cgroup': '0::/system.slice/other.service'}):
            with self.assertRaises(RuntimeError):
                self.check(**override)

    def test_wrong_command_is_rejected(self):
        with self.assertRaises(RuntimeError):
            self.check(command=['pinned', 'other-database'])

    def test_original_exporter_requires_recorded_pid_and_start(self):
        self.check(phase='export', pid=guard.PID)
        for override in ({'pid': 123}, {'pid': guard.PID, 'started': 'different'}):
            with self.assertRaises(RuntimeError):
                self.check(phase='export', **override)


if __name__ == '__main__':
    unittest.main()
