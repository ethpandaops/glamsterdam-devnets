"""Protect exhaustive, ordered audits when expected inputs load concurrently."""
import threading
import unittest
from unittest.mock import patch

import audit


class Bodies:
    def __init__(self, truncate=False):
        self.calls = []
        self.truncate = truncate

    def call(self, method, params, engine):
        assert method == 'engine_getPayloadBodiesByRangeV2' and engine
        start, size = map(lambda value: int(value, 16), params)
        self.calls.append((start, size))
        return [{'number': n} for n in range(start, start+size-self.truncate)]


class AuditInputPrefetch(unittest.TestCase):
    def test_every_record_is_paired_in_order_across_partial_last_batch(self):
        second_started = threading.Event()
        reads = []

        def record(number):
            reads.append(number)
            if number == 101:
                self.assertTrue(second_started.wait(5))
            if number == 102:
                second_started.set()
            return {'expected_number': number}

        rpc = Bodies()
        with patch.object(audit, 'ANCHOR', 100), patch.object(audit, 'record', record):
            rows = list(audit.body_records(rpc, 135))
        self.assertEqual(rpc.calls, [(101, 16), (117, 16), (133, 3)])
        self.assertEqual(sorted(reads), list(range(101, 136)))
        self.assertEqual(rows, [(n, {'number': n}, {'expected_number': n})
                                for n in range(101, 136)])

    def test_missing_or_corrupt_input_fails_the_audit(self):
        for error in [FileNotFoundError('missing record'), ValueError('corrupt record')]:
            with self.subTest(error=type(error).__name__):
                def record(number):
                    if number == 117:
                        raise error
                    return number
                rpc = Bodies()
                with patch.object(audit, 'ANCHOR', 100), patch.object(audit, 'record', record):
                    with self.assertRaises(type(error)):
                        list(audit.body_records(rpc, 135))
                self.assertEqual(rpc.calls, [(101, 16), (117, 16)])

    def test_short_rpc_response_cannot_truncate_verification(self):
        with patch.object(audit, 'ANCHOR', 100), patch.object(audit, 'record', lambda n: n):
            with self.assertRaises(AssertionError):
                list(audit.body_records(Bodies(truncate=True), 116))

    def test_prefetch_does_not_read_the_next_batch_early(self):
        reads = []
        rpc = Bodies()
        with patch.object(audit, 'ANCHOR', 100), patch.object(audit, 'record', lambda n: reads.append(n)):
            rows = audit.body_records(rpc, 1000)
            next(rows)
            rows.close()
        self.assertEqual(sorted(reads), list(range(101, 117)))
        self.assertEqual(rpc.calls, [(101, 16)])


if __name__ == '__main__':
    unittest.main()
