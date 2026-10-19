#!/usr/bin/env python3
"""Install a 24-hour, single-object read URL on the PBT-1 source node.

Requires AWS CLI and the existing TF_VAR_cloudflare_api_token locally. The token
and derived storage credentials never leave the controller. No bucket/WAF changes.
"""
import argparse
import hashlib
import json
import os
import subprocess
import urllib.request

ENDPOINT = 'https://539bc53131934672bf85e7260ec0b218.r2.cloudflarestorage.com'
BUCKET = 'ethpandaops-shadowfork-images'
OBJECT = 'jochemnet/erigon/24452538/snapshot-pruned.tar.zst'
SIZE = 276341609865


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='SSH destination, e.g. root@164.92.239.96')
    parser.add_argument('--identity', required=True, help='SSH private key path')
    args = parser.parse_args()
    token = os.environ['TF_VAR_cloudflare_api_token']
    request = urllib.request.Request(
        'https://api.cloudflare.com/client/v4/user/tokens/verify',
        headers={'Authorization': 'Bearer ' + token},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        identity = json.load(response)['result']['id']
    env = os.environ.copy()
    env.update(
        AWS_ACCESS_KEY_ID=identity,
        AWS_SECRET_ACCESS_KEY=hashlib.sha256(token.encode()).hexdigest(),
        AWS_DEFAULT_REGION='auto',
    )
    def aws(*arguments):
        result = subprocess.run(
            ['aws', '--endpoint-url', ENDPOINT, *arguments],
            env=env, capture_output=True, text=True, check=True,
        )
        return result.stdout

    metadata = json.loads(aws('s3api', 'head-object', '--bucket', BUCKET, '--key', OBJECT))
    if metadata['ContentLength'] != SIZE:
        raise RuntimeError('Archive size differs from the pinned release; inspect before restoring')
    signed_url = aws('s3', 'presign', f's3://{BUCKET}/{OBJECT}', '--expires-in', '86400')
    subprocess.run(
        ['ssh', '-i', args.identity, '-o', 'BatchMode=yes', '--', args.host,
         'umask 077; mkdir -p /data/pbt-1/snapshot-fetcher; '
         'cat > /data/pbt-1/snapshot-fetcher/source-url; '
         'chmod 600 /data/pbt-1/snapshot-fetcher/source-url'],
        input=signed_url, text=True, check=True,
    )
    print(f'Verified {SIZE} bytes; installed a 24-hour read URL on {args.host}.')


if __name__ == '__main__':
    main()
