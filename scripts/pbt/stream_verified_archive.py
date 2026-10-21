"""Ordered, ETag-bound ranges for a fresh restore; no account credentials."""
from concurrent.futures import ThreadPoolExecutor
import time
import urllib.error
import urllib.request

PART = 64 * 1024 * 1024
WORKERS = 4


def fetch_range(url, etag, start, end, total):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={
                'Range': f'bytes={start}-{end}', 'If-Match': etag,
                'Accept-Encoding': 'identity'})
            with urllib.request.urlopen(request, timeout=120) as response:
                assert response.status == 206, 'Server ignored archive range'
                assert response.headers['ETag'] == etag, 'Archive identity changed'
                assert response.headers['Content-Range'] == f'bytes {start}-{end}/{total}'
                data = response.read(end - start + 2)
                assert len(data) == end - start + 1, 'Incomplete or oversized range'
                return data
        except (OSError, urllib.error.URLError):
            if attempt == 2:
                raise RuntimeError('Archive range transfer failed') from None
            time.sleep(attempt + 1)


def ordered_ranges(url, etag, total):
    assert total > 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        pending = {}
        starts = iter(range(0, total, PART))
        def submit():
            start = next(starts, None)
            if start is not None:
                pending[start] = pool.submit(fetch_range, url, etag, start,
                                              min(start + PART, total) - 1, total)
        for _ in range(WORKERS):
            submit()
        while pending:
            start = min(pending)
            data = pending.pop(start).result()
            yield data
            submit()
