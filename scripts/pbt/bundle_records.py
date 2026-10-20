"""Index immutable replay inputs and stream an archive with per-file checks."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile


def index_records(root, first, last):
    files = sorted((root/'blocks').glob('*.json.gz'))
    assert [int(p.name.split('.')[0]) for p in files] == list(range(first, last+1)), 'Replay range has gaps or extra records'
    entries = []
    for path in files:
        assert path.is_file() and not path.is_symlink(), path
        before = path.stat()
        data = path.read_bytes()
        after = path.stat()
        assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns), path
        entries.append({'file': 'blocks/'+path.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
    return entries


def index_digest(entries):
    return hashlib.sha256(json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def stream_archive(root, staging, output):
    manifest_bytes = (staging/'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    with tarfile.open(fileobj=output, mode='w|') as archive:
        def add(name, data):
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            archive.addfile(info, io.BytesIO(data))
        add('manifest.json', manifest_bytes)
        for entry in manifest['records']+manifest['artifacts']:
            relative = Path(entry['file'])
            assert not relative.is_absolute() and '..' not in relative.parts
            path = (root if relative.parts[0] == 'blocks' else staging)/relative
            assert not path.is_symlink()
            data = path.read_bytes()
            assert len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256'], f'Changed input: {relative}'
            add(str(relative), data)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--first', type=int)
    parser.add_argument('--last', type=int)
    parser.add_argument('--proof', type=Path)
    parser.add_argument('--staging', type=Path)
    args = parser.parse_args()
    if args.staging:
        stream_archive(args.root, args.staging, sys.stdout.buffer)
    else:
        entries = index_records(args.root, args.first, args.last)
        result = {'records': len(entries), 'bytes': sum(e['bytes'] for e in entries), 'index_sha256': index_digest(entries)}
        if args.proof:
            proof = json.loads(args.proof.read_text())
            result['proof'] = {k: proof[k] for k in ('client', 'stopped', 'verified_bal_bodies', 'qualifying_blocks', 'image')}
            result['proof']['head'] = {k: proof['head'][k] for k in ('number', 'hash', 'stateRoot', 'blockAccessListHash')}
        print(json.dumps(result))
