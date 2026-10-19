"""Controller-only R2 authorization. Never log or copy the account credentials."""
import hashlib
import json
import os
import urllib.request
import boto3
from botocore.config import Config

ENDPOINT='https://539bc53131934672bf85e7260ec0b218.r2.cloudflarestorage.com'
BUCKET='ethpandaops-shadowfork-images'
PREFIX='pbt-1/20261019-mixed-8037-v2/'


def client():
    token=os.environ['TF_VAR_cloudflare_api_token']
    request=urllib.request.Request('https://api.cloudflare.com/client/v4/user/tokens/verify',
                                   headers={'Authorization':'Bearer '+token})
    with urllib.request.urlopen(request,timeout=30) as response:
        identity=json.load(response)['result']['id']
    return boto3.client('s3',endpoint_url=ENDPOINT,region_name='auto',
                        aws_access_key_id=identity,aws_secret_access_key=hashlib.sha256(token.encode()).hexdigest(),
                        config=Config(signature_version='s3v4',retries={'max_attempts':5}))
