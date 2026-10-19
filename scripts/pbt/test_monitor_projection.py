"""Do not turn stale progress or a changed replay run into a completion promise."""
import copy
import unittest

from monitor import replay_projection


class ReplayProjectionTests(unittest.TestCase):
    def setUp(self):
        self.old = {'pipeline': {'phase': 'native_replaying', 'head': 1000,
                                'target_head': 4000, 'time': 1000},
                    'native_replay': {key: {'ActiveState': 'active', 'MainPID': str(i),
                                           'InvocationID': 'invocation-'+key}
                                      for i, key in enumerate(('service', 'client'), 1)}}
        self.new = copy.deepcopy(self.old)
        self.new['pipeline'].update(head=1600, time=1600)

    def test_measures_progress_and_explicitly_excludes_delivery_work(self):
        result = replay_projection(self.new, self.old, 1600)
        self.assertEqual(result['blocks_per_second'], 1)
        self.assertEqual(result['remaining_blocks'], 2400)
        self.assertEqual(result['replay_only_eta_utc'], '1970-01-01T01:06:40+00:00')
        self.assertIn('upload', result['excludes'])

    def test_restart_or_dead_process_invalidates_projection(self):
        for key in ('service', 'client'):
            for field, value in [('InvocationID', 'replacement'), ('InvocationID', ''),
                                 ('MainPID', '99'), ('MainPID', '0'), ('ActiveState', 'failed')]:
                with self.subTest(key=key, field=field, value=value):
                    new = copy.deepcopy(self.new)
                    new['native_replay'][key][field] = value
                    self.assertIsNone(replay_projection(new, self.old, 1600))

    def test_changed_target_or_phase_invalidates_projection(self):
        for field, value in [('target_head', 3000), ('phase', 'restart_validation')]:
            new = copy.deepcopy(self.new)
            new['pipeline'][field] = value
            self.assertIsNone(replay_projection(new, self.old, 1600))

    def test_short_stale_future_or_nonprogressing_samples_do_not_predict(self):
        for update, now in [({'time': 1200}, 1200), ({}, 2600), ({}, 1599),
                            ({'head': 1000}, 1600), ({'head': 999}, 1600),
                            ({'head': 4000}, 1600), ({'time': float('nan')}, 1600)]:
            with self.subTest(update=update, now=now):
                new = copy.deepcopy(self.new)
                new['pipeline'].update(update)
                self.assertIsNone(replay_projection(new, self.old, now))


if __name__ == '__main__':
    unittest.main()
