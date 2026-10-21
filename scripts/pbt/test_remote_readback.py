import hashlib
import io
import threading
import time
import unittest
from unittest.mock import patch

from botocore.exceptions import ClientError
from urllib3.exceptions import ProtocolError

import remote_readback as reader


class RemoteChecksum(unittest.TestCase):
    def setUp(self):
        self.payload = bytes(range(251)) * 37
        self.calls = {}
        self.closed = []
        self.completed = []
        self.lock = threading.Lock()
        self.failure = None

    def get_object(self, **request):
        self.assertEqual(request['IfMatch'], '"fixed-object"')
        self.assertEqual((request['Bucket'], request['Key']), ('bucket', 'archive'))
        start, end = map(int, request['Range'].removeprefix('bytes=').split('-'))
        with self.lock:
            attempt = self.calls[start] = self.calls.get(start, 0) + 1
        data = self.payload[start:end + 1]
        test = self

        class Body(io.BytesIO):
            def read(self, size=-1):
                if start == 0 and attempt == 1 and test.failure == 'protocol':
                    raise ProtocolError('connection interrupted')
                if start == 0 and attempt == 1 and test.failure == 'short':
                    return data[:len(data)//2]
                if test.failure == 'persistent':
                    raise ProtocolError('do not expose request credentials')
                if start == 0:
                    time.sleep(0.01)
                test.completed.append(start)
                return super().read(size)

            def close(self):
                test.closed.append((start, attempt))
                super().close()

        return {'Body': Body(data), 'ETag': '"changed"' if self.failure == 'etag' else '"fixed-object"',
                'ContentRange': f'bytes {start}-{end}/{len(self.payload)}',
                'ContentLength': len(data)}

    def run_readback(self):
        progress = []
        with patch.object(reader, 'PART', 1024):
            result = reader.readback(self, 'bucket', 'archive', '"fixed-object"',
                                     len(self.payload), progress.append)
        self.assertEqual(result, (len(self.payload), hashlib.sha256(self.payload).hexdigest()))
        self.assertEqual(progress[-1], len(self.payload))
        self.assertEqual(progress[:-1], list(range(1024, len(self.payload), 1024)))
        self.assertEqual(len(self.closed), sum(self.calls.values()))

    def test_out_of_order_reads_hash_in_original_order(self):
        self.run_readback()
        self.assertNotEqual(self.completed[0], 0)
        self.assertTrue(all(count == 1 for count in self.calls.values()))

    def test_disconnection_retries_only_failed_range_without_duplicate_hashing(self):
        self.failure = 'protocol'
        with patch.object(reader.time, 'sleep'):
            self.run_readback()
        self.assertEqual(self.calls[0], 2)
        self.assertTrue(all(count == 1 for start, count in self.calls.items() if start))

    def test_short_range_is_retried_before_hashing(self):
        self.failure = 'short'
        with patch.object(reader.time, 'sleep'):
            self.run_readback()
        self.assertEqual(self.calls[0], 2)

    def test_changed_identity_fails_without_retry(self):
        self.failure = 'etag'
        with self.assertRaises(AssertionError):
            reader.fetch(self, 'bucket', 'archive', '"fixed-object"', 0, 31, len(self.payload))
        self.assertEqual(self.calls[0], 1)
        self.assertEqual(self.closed, [(0, 1)])

    def test_precondition_failure_is_not_retried(self):
        error = ClientError({'Error': {'Code': 'PreconditionFailed'},
                             'ResponseMetadata': {'HTTPStatusCode': 412}}, 'GetObject')
        with patch.object(self, 'get_object', side_effect=error) as get:
            with self.assertRaises(ClientError):
                reader.fetch(self, 'bucket', 'archive', '"fixed-object"', 0, 31, len(self.payload))
        self.assertEqual(get.call_count, 1)

    def test_exhausted_retries_do_not_return_a_checksum(self):
        self.failure = 'persistent'
        with patch.object(reader.time, 'sleep'), self.assertRaisesRegex(RuntimeError, '^Remote checksum range transfer failed$'):
            reader.readback(self, 'bucket', 'archive', '"fixed-object"', len(self.payload), lambda _: None)
        self.assertEqual(self.calls[0], reader.ATTEMPTS)


if __name__ == '__main__':
    unittest.main()
