"""Check incident semantics and public artifact sanitization without live calls."""
import datetime as dt
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('monitor', Path(__file__).with_name('monitor.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MonitorChecks(unittest.TestCase):
    def test_secrets_removed_from_log_excerpts(self):
        secret = 'c' * 64
        jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJpYXQiOjF9.signature'
        data = {'Body': f'Authorization=Bearer {jwt} password="with spaces" secret={secret} https://user:pass@example.test/ key {secret}', 'api_key': 'private', 'image_id': 'sha256:' + 'd' * 64, 'id': 'e' * 64, 'root': '0x' + 'f' * 64}
        clean = m.scrub(data)
        self.assertNotIn(jwt, clean['Body'])
        self.assertNotIn(secret, clean['Body'])
        self.assertNotIn('with spaces', clean['Body'])
        self.assertNotIn('user:pass', clean['Body'])
        self.assertEqual(clean['api_key'], '[REDACTED]')
        self.assertEqual(clean['image_id'], data['image_id'])
        self.assertEqual(clean['id'], data['id'])
        self.assertEqual(clean['root'], data['root'])

    def test_healthy_boundary_and_stale_head(self):
        node = {'sync': {'is_syncing': False, 'is_optimistic': False, 'el_offline': False}, 'slot': 320, 'finalized': 8, 'el_syncing': False, 'el_peers': 3, 'containers': [{'name':'execution','running':True}]}
        self.assertEqual(m.classify_node(node, 323), [])
        self.assertIn('head_lag_over_3_slots', m.classify_node(node, 324))
        node['finalized'] = 6
        self.assertIn('finality_lag_over_3_epochs', m.classify_node(node, 320))

    def test_observer_optimism_does_not_change_staked_inventory(self):
        hosts, ranges = m.inventory(Path(__file__).resolve().parents[2])
        self.assertEqual(len(hosts), 41)
        self.assertEqual(len(ranges), 36)
        self.assertNotIn('nimbus-nimbusel-1', ranges)
        self.assertEqual(sum(b-a for a,b in ranges.values()), 36000)

    def test_normal_optimistic_light_client_logs_excluded(self):
        normal = 'DBG New LC optimistic header topics="beacnde"'
        self.assertFalse(any(m.re.search(p, normal) for p in m.PATTERNS.values()))
        self.assertTrue(m.re.search(m.PATTERNS['engine_timeout'], 'Local getPayload TimeoutGetPayload'))


if __name__ == '__main__':
    unittest.main()
