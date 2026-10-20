"""Verify that interrupted native replay cannot be sealed across a validation gap."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('handoff', Path(__file__).with_name('handoff-erigon-native.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HandoffChecks(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.bad_header = self.bad_payload = self.bad_body = False
        self.request = {'start': 101, 'end': 1000, 'batch_size': 16}
        self.progress = {'head': 116, 'validated_blocks': 16}
        self.end = 120
        self.rpc = SimpleNamespace(head=lambda: self.header(self.end), call=self.call)

    def header(self, n):
        return {'number': hex(n), 'hash': str(n), 'stateRoot': 's'+str(n), 'blockAccessListHash': 'b'+str(n)}

    def record(self, n):
        return {'hash': str(n), 'state_root': 's'+str(n), 'bal_hash': 'b'+str(n),
                'new_payload': [{'number': n, 'transactions': [str(n)], 'withdrawals': [], 'blockAccessList': 'bal'+str(n)}]}

    def call(self, method, params, engine=False):
        self.calls.append(method)
        if method == 'eth_getBlockByNumber':
            header = self.header(int(params[0], 16))
            if self.bad_header:
                header['stateRoot'] = 'incorrect'
            return header
        if method == 'engine_newPayloadV5':
            return {'status': 'INVALID' if self.bad_payload else 'VALID', 'latestValidHash': str(params[0]['number'])}
        if method == 'engine_getPayloadBodiesByRangeV2':
            body = self.record(int(params[0], 16))['new_payload'][0]
            if self.bad_body:
                body['blockAccessList'] = 'incorrect'
            return [body]
        raise AssertionError(method)

    def verify(self):
        return module.verify_segment(self.rpc, self.record, self.request, self.progress)

    def test_checks_all_headers_and_unreported_tail(self):
        proof = self.verify()
        self.assertEqual(proof['validated_blocks'], 20)
        self.assertEqual(proof['tail_payloads_verified'], 4)
        self.assertEqual(self.calls.count('engine_newPayloadV5'), 4)
        self.assertEqual(self.calls.count('eth_getBlockByNumber'), 20)
        self.assertEqual(self.calls.count('engine_getPayloadBodiesByRangeV2'), 16)

    def test_refuses_gap_larger_than_inflight_batch(self):
        self.end = 133
        with self.assertRaises(AssertionError):
            self.verify()
        self.assertEqual(self.calls, [])

    def test_refuses_inconsistent_prior_validation_count(self):
        self.progress['validated_blocks'] = 15
        with self.assertRaises(AssertionError):
            self.verify()
        self.assertEqual(self.calls, [])

    def test_wrong_commitment_invalid_payload_or_missing_body_prevents_seal(self):
        for field in ('bad_header', 'bad_payload', 'bad_body'):
            with self.subTest(field=field):
                setattr(self, field, True)
                with self.assertRaises(AssertionError):
                    self.verify()
                setattr(self, field, False)

    def test_head_notification_without_persistence_is_not_a_fence(self):
        self.assertEqual(module.persisted_head('head updated number=116\nTimings: Post-Forkchoice\nhead updated number=132\n'), 116)
        self.assertEqual(module.persisted_head('head updated number=132\nTimings: Post-Forkchoice\n'), 132)
        self.assertIsNone(module.persisted_head('head updated number=132\n'))

    def test_boundary_wait_ignores_old_log_and_handles_split_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'client.log'
            path.write_text('head updated number=999\n')
            chunks = iter(['head updated number=', '132\n'])
            def append(_):
                with path.open('a') as stream:
                    stream.write(next(chunks))
            with patch.object(module.time, 'sleep', side_effect=append):
                self.assertEqual(module.wait_next_head(path, 116), 132)

    def test_boundary_wait_timeout_does_not_accept_old_head(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'client.log'
            path.write_text('head updated number=132\n')
            with patch.object(module.time, 'monotonic', side_effect=[0, 11]):
                with self.assertRaisesRegex(AssertionError, 'driver was not stopped'):
                    module.wait_next_head(path, 116, timeout=10)


if __name__ == '__main__':
    unittest.main()
