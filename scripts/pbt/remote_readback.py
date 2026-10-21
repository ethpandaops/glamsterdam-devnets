"""Full remote SHA-256 with bounded, ordered, retryable S3 range reads."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import time

from botocore.exceptions import BotoCoreError, ClientError
from urllib3.exceptions import HTTPError

PART = 64 * 1024**2
WORKERS = 4
ATTEMPTS = 5


def fetch(s3, bucket, key, etag, start, end, total):
    for attempt in range(ATTEMPTS):
        try:
            response = s3.get_object(Bucket=bucket, Key=key, IfMatch=etag,
                                     Range=f'bytes={start}-{end}')
            body = response['Body']
            try:
                assert response['ETag'] == etag, 'Remote object identity changed'
                assert response['ContentRange'] == f'bytes {start}-{end}/{total}', 'Unexpected remote range'
                assert response['ContentLength'] == end - start + 1, 'Unexpected remote range size'
                data = body.read(end - start + 2)
                if len(data) != end - start + 1:
                    raise OSError('Incomplete remote range')
                return data
            finally:
                body.close()
        except ClientError as exc:
            status = exc.response.get('ResponseMetadata', {}).get('HTTPStatusCode', 0)
            if status not in (408, 429) and not 500 <= status <= 599:
                raise
        except (BotoCoreError, HTTPError, OSError):
            pass
        if attempt + 1 == ATTEMPTS:
            raise RuntimeError('Remote checksum range transfer failed') from None
        time.sleep(min(2**attempt, 8))


def readback(s3, bucket, key, etag, total, progress):
    """Hash every byte once, in order; incomplete ranges never reach the hash."""
    assert total > 0
    digest, length = hashlib.sha256(), 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        starts = iter(range(0, total, PART))
        pending = {}

        def submit():
            start = next(starts, None)
            if start is not None:
                pending[start] = pool.submit(fetch, s3, bucket, key, etag, start,
                                              min(start + PART, total) - 1, total)

        for _ in range(WORKERS):
            submit()
        while pending:
            data = pending.pop(min(pending)).result()
            digest.update(data)
            length += len(data)
            progress(length)
            submit()
    assert length == total
    return length, digest.hexdigest()
