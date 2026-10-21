import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('recover', Path(__file__).with_name('recover-erigon-anchor.py'))
recover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recover)


class NativeCaptureRecovery(unittest.TestCase):
    def test_offline_execution_requires_body_and_senders_at_target(self):
        def report(exec_block, sender_block):
            return '\n'.join(f'{key}\t\t{number}\t0' for key, number in [
                ('Headers', sender_block), ('Bodies', sender_block),
                ('Senders', sender_block), ('Execution', exec_block)])
        n = recover.BLOCK
        recover.validate_positions(report(n - 1, n), n - 1, n)
        for text in (report(n - 1, n - 1), report(n, n), report(n - 2, n), ''):
            with self.subTest(text=text), self.assertRaises(AssertionError):
                recover.validate_positions(text, n - 1, n)

    def test_recovery_removes_only_the_intentional_exit(self):
        args = ['docker', 'run', '-d', '--name', 'pbt-1-erigon-anchor-preparation',
                '--network=none', '--memory=32g', '--memory-swap=32g', '--cpus=8',
                '--cpuset-cpus=0-7', '-e', 'STOP_AFTER_BLOCK=24453558',
                '-e', 'COMMITMENT_V3=true', 'pinned-image', '--exec.no-prune=true',
                '--exec.no-background-maintenance=true', '--datadir=/data']
        changed = recover.container_command(args)
        expected = [*args[:4], recover.NAME, *args[5:10], *args[12:]]
        self.assertEqual(changed, expected)
        for broken in (args + ['STOP_AFTER_BLOCK=other'],
                       [a for a in args if a != '--exec.no-prune=true'],
                       [a.replace('24453558', '24503958') for a in args]):
            with self.assertRaises(AssertionError):
                recover.container_command(broken)

    def test_offline_environment_keeps_history_and_suppresses_exit_and_maintenance(self):
        with patch.dict(recover.os.environ, {'STOP_AFTER_BLOCK': '24453558',
                                             'ERIGON_STOP_AFTER_BLOCK': '24453558'}):
            env = recover.native_env()
        self.assertNotIn('STOP_AFTER_BLOCK', env)
        self.assertNotIn('ERIGON_STOP_AFTER_BLOCK', env)
        for name in ('COMMITMENT_V3', 'NO_PRUNE', 'NO_BACKGROUND_E3_BUILD'):
            self.assertEqual(env[name], 'true')


if __name__ == '__main__':
    unittest.main()
