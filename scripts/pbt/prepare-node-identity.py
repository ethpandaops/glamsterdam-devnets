#!/usr/bin/env python3
"""Prepare a persistent PBT peer identity outside the restored database.

Print public peer information only. Never start a client or replace an existing
identity. Each worker runs this locally, so private keys stay on that worker.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import pwd

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

ROOT = Path('/data/pbt-1/node-identity')


def private_file(path, value, uid, gid):
    # Exclusive creation prevents a repeated preparation from rotating the peer.
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        assert path.read_bytes() == value, f'Existing identity differs: {path}'
    else:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    os.chown(path, uid, gid)
    os.chmod(path, 0o600)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--client', choices=['geth', 'nethermind', 'besu', 'erigon'], required=True)
    p.add_argument('--ip', type=ipaddress.IPv4Address, required=True)
    p.add_argument('--owner', required=True)
    a = p.parse_args()
    user = pwd.getpwnam(a.owner)
    ROOT.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(ROOT, user.pw_uid, user.pw_gid)
    os.chmod(ROOT, 0o750)
    raw_path = ROOT / 'node.key.plain'
    hex_path = ROOT / 'nodekey'
    if raw_path.exists():
        raw = raw_path.read_bytes()
        assert len(raw) == 32
        key = ec.derive_private_key(int.from_bytes(raw, 'big'), ec.SECP256K1())
    else:
        assert not hex_path.exists(), 'Partial identity requires inspection'
        key = ec.generate_private_key(ec.SECP256K1())
        raw = key.private_numbers().private_value.to_bytes(32, 'big')
    private_file(raw_path, raw, user.pw_uid, user.pw_gid)
    private_file(hex_path, raw.hex().encode(), user.pw_uid, user.pw_gid)
    public = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)[1:].hex()
    result = {
        'client': a.client, 'ip': str(a.ip), 'node_id': public,
        'enode': f'enode://{public}@{a.ip}:30303',
        'identity_directory': str(ROOT), 'private_keys_remained_on_worker': True,
        'datadir_changed': False, 'client_started': False,
    }
    report = ROOT / 'public.json'
    report.write_text(json.dumps(result, indent=2) + '\n')
    os.chown(report, user.pw_uid, user.pw_gid)
    os.chmod(report, 0o644)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
