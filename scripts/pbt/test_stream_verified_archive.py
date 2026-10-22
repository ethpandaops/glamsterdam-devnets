from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
import threading
import unittest
from unittest.mock import patch
import stream_verified_archive as stream


class RangeTransfer(unittest.TestCase):
    def setUp(self):
        self.payload = bytes(range(256)) * 4096
        self.mode = 'normal'
        test = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                test.assertEqual(self.headers['If-Match'], '"fixture"')
                start, end = map(int, re.fullmatch(r'bytes=(\d+)-(\d+)', self.headers['Range']).groups())
                data = test.payload[start:end + 1]
                self.send_response(200 if test.mode == 'ignored' else 206)
                self.send_header('ETag', '"changed"' if test.mode == 'etag' else '"fixture"')
                self.send_header('Content-Range', f'bytes {start}-{end}/{len(test.payload)}')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/archive'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_concurrent_ranges_are_yielded_in_original_order(self):
        with patch.object(stream, 'PART', 65536):
            result = b''.join(stream.ordered_ranges(self.url, '"fixture"', len(self.payload)))
        self.assertEqual(result, self.payload)

    def test_identity_change_or_ignored_range_is_rejected(self):
        for mode in ('etag', 'ignored'):
            self.mode = mode
            with self.subTest(mode=mode), self.assertRaises(AssertionError):
                stream.fetch_range(self.url, '"fixture"', 0, 31, len(self.payload))


if __name__ == '__main__':
    unittest.main()
