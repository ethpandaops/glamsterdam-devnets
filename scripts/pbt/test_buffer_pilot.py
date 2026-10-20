"""The buffer pilot must validate the entire range, including bodies before the tip."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('buffer_pilot', Path(__file__).with_name('pilot-erigon-buffer.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class BufferBodyChecks(unittest.TestCase):
    def setUp(self):
        self.headers = []
        self.bad_body = False
        self.bad_header = False
        self.head = self.header(118)
        self.rpc = SimpleNamespace(head=lambda: self.head, call=self.call)

    def header(self, n):
        return {'number': hex(n), 'hash': str(n), 'stateRoot': 's'+str(n), 'blockAccessListHash': 'b'+str(n)}

    def record(self, n):
        return {'hash': str(n), 'state_root': 's'+str(n), 'bal_hash': 'b'+str(n),
                'new_payload': [{'transactions': [str(n)], 'withdrawals': [], 'blockAccessList': 'bal'+str(n)}]}

    def call(self, method, params, engine=False):
        if method == 'eth_getBlockByNumber':
            n = int(params[0], 16)
            self.headers.append(n)
            header = self.header(n)
            if self.bad_header and n == 105:
                header['stateRoot'] = 'incorrect'
            return header
        if method == 'engine_getPayloadBodiesByRangeV2':
            start, count = (int(x, 16) for x in params)
            bodies = [self.record(n)['new_payload'][0] for n in range(start, start+count)]
            if self.bad_body and start == 101:
                bodies[4]['blockAccessList'] = 'incorrect'
            return bodies
        raise AssertionError(method)

    def test_checks_full_range_and_short_last_batch(self):
        self.assertEqual(module.verify_bodies(self.rpc, self.record, 101, 118, self.head), 18)
        self.assertEqual(self.headers, list(range(101, 119)))

    def test_wrong_older_bal_is_fatal(self):
        self.bad_body = True
        with self.assertRaises(AssertionError):
            module.verify_bodies(self.rpc, self.record, 101, 118, self.head)

    def test_wrong_intermediate_root_is_fatal(self):
        self.bad_header = True
        with self.assertRaises(AssertionError):
            module.verify_bodies(self.rpc, self.record, 101, 118, self.head)

    def test_wide_profile_has_separate_evidence_and_checks_all_512_bodies(self):
        try:
            module.configure('wide-128')
            self.assertEqual((module.PILOT.name, module.BATCH_SIZE, module.BUFFER, module.BLOCKS),
                             ('native-wide-pilot', 128, '4G', 512))
            self.rpc.head = lambda: self.header(612)
            self.assertEqual(module.verify_bodies(self.rpc, self.record, 101, 612, self.header(612)), 512)
            self.assertEqual(self.headers, list(range(101, 613)))
        finally:
            module.configure('buffer-64')
        self.assertEqual((module.PILOT.name, module.BATCH_SIZE, module.BUFFER, module.BLOCKS),
                         ('native-buffer-pilot', 64, '2G', 256))


if __name__ == '__main__':
    unittest.main()
