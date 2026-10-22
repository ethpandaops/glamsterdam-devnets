#!/usr/bin/env python3
"""Read-only workload count from the completed, sorted native ETL files.

Counts records before native duplicate elimination, not unique emitted leaves.
Searches zone boundaries using the pinned exporter's fixed-width record format;
this is a workload measurement, not a replacement for native verification.
"""
import concurrent.futures
import io
import json
from pathlib import Path
import random
import socket
import struct
import time

WIDTH = {0: 34, 1: 34, 255: 66}


def frame_at_or_after(stream, size, offset):
    if offset >= size:
        return size, 256
    stream.seek(offset)
    data = stream.read(512)
    for index in range(min(113, len(data))):
        if index + 3 > len(data):
            break
        width = int.from_bytes(data[index:index + 2], 'little')
        zone = data[index + 2]
        if WIDTH.get(zone) != width or index + width + 46 > len(data):
            continue
        if int.from_bytes(data[index + width + 2:index + width + 6], 'little') != 40:
            continue
        end = index + width + 46
        if offset + end != size:
            if end + 3 > len(data):
                continue
            following_width = int.from_bytes(data[end:end + 2], 'little')
            following_zone = data[end + 2]
            if (WIDTH.get(following_zone) != following_width or following_zone < zone
                    or end + following_width + 46 > len(data)):
                continue
            if int.from_bytes(data[end + following_width + 2:end + following_width + 6], 'little') != 40:
                continue
        return offset + index, zone
    if size - offset < 112:
        return size, 256
    raise ValueError('No valid ETL frame near offset ' + str(offset))


def boundary(stream, size, zone):
    lower, upper = 0, size
    while lower < upper:
        middle = (lower + upper) // 2
        _, actual = frame_at_or_after(stream, size, middle)
        if actual < zone:
            lower = middle + 1
        else:
            upper = middle
    return frame_at_or_after(stream, size, lower)[0]


def counts(stream, size):
    edges = [0, boundary(stream, size, 1), boundary(stream, size, 255), size]
    result = {}
    for index, zone in enumerate(WIDTH):
        start, end = edges[index:index + 2]
        width = WIDTH[zone] + 46
        assert (end - start) % width == 0
        if end > start:
            assert frame_at_or_after(stream, size, start) == (start, zone)
            assert frame_at_or_after(stream, size, end - width) == (end - width, zone)
        result[str(zone)] = (end - start) // width
    assert sum(result[str(zone)] * (WIDTH[zone] + 46) for zone in WIDTH) == size
    return result


def fixtures():
    rng = random.Random(31)
    for trial in range(80):
        expected = {str(zone): rng.randrange(0, 100) for zone in WIDTH}
        if trial < 3:
            expected = {str(zone): 20 if index == trial else 0 for index, zone in enumerate(WIDTH)}
        chunks = []
        for zone, width in WIDTH.items():
            for _ in range(expected[str(zone)]):
                chunks.append(struct.pack('<H', width) + bytes([zone]) + bytes(width - 1)
                              + struct.pack('<i', 40) + rng.randbytes(40))
        data = b''.join(chunks)
        assert counts(io.BytesIO(data), len(data)) == expected


def measure(path):
    before = path.stat()
    with path.open('rb') as stream:
        result = counts(stream, before.st_size)
    after = path.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
    return {'name': str(path), 'inode': before.st_ino, 'bytes': before.st_size, 'records': result}


if __name__ == '__main__':
    fixtures()
    assert socket.gethostname() == 'glamsterdam-pbt-1-lighthouse-erigon-1'
    base = Path('/data/pbt-1')
    roots = [base / 'rehearsal-24453558/erigon/temp-before-volume-routing',
             Path('/mnt/pbt-export-scratch/native-temp')]
    paths = sorted(path for root in roots for path in root.glob('erigon-sortable-buf-*'))
    assert paths
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(measure, paths))
    total = {str(zone): sum(row['records'][str(zone)] for row in rows) for zone in WIDTH}
    result = {'time': time.time(), 'seconds': time.time() - started, 'files': len(rows),
              'bytes': sum(row['bytes'] for row in rows), 'records_by_zone': total,
              'total_records_before_duplicate_elimination': sum(total.values()),
              'method': 'Binary search of sorted fixed-width native ETL zone boundaries; boundary frames, range alignment and unchanged file identities validated. Not a full content checksum audit.',
              'synthetic_fixtures_passed': 80, 'unique_emitted_leaves_not_proven_by_this_count': True}
    (base / 'export-record-count.json').write_text(json.dumps(result, indent=2) + '\n')
    (base / 'export-record-count-files.json').write_text(json.dumps(rows) + '\n')
    print(json.dumps(result, indent=2))
