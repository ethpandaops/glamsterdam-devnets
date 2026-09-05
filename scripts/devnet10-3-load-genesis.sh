#!/usr/bin/env bash
# 3/4  Replace the network config with the new genesis from R2.
# args: ACCESS_KEY SECRET_KEY BUCKET ENDPOINT PREFIX
#   ansible 'all:!localhost' -b -f 400 -m script -a "../scripts/devnet10-3-load-genesis.sh \
#     {{ secret_r2.access_key_id }} {{ secret_r2.secret_access_key }} {{ secret_r2.bucket }} \
#     {{ secret_r2.account_id }}.r2.cloudflarestorage.com genesis-files/{{ ethereum_network_name }}/metadata"
set -euo pipefail
ACCESS="${1:?access key}"; SECRET="${2:?secret key}"; BUCKET="${3:?bucket}"
ENDPOINT="${4:?endpoint}"; PREFIX="${5:?prefix}"
DEST=/data/ethereum-network-config/metadata
H=$(hostname)

command -v s3cmd >/dev/null 2>&1 || { apt-get install -y -qq s3cmd >/dev/null 2>&1 || \
  { echo "[$H] FATAL: s3cmd missing and install failed" >&2; exit 1; }; }

# full replace, not sync: a stale file from the old genesis must not survive
rm -rf "$DEST"; mkdir -p "$DEST"
AWS_ACCESS_KEY_ID="$ACCESS" AWS_SECRET_ACCESS_KEY="$SECRET" \
  s3cmd sync --no-progress --region=auto --host="$ENDPOINT" --host-bucket="$ENDPOINT" \
    "s3://$BUCKET/$PREFIX/" "$DEST/" >/dev/null

chown -R root:root "$DEST"; chmod -R u=rwX,g=rX,o=rX "$DEST"
for f in genesis.ssz genesis.json config.yaml deposit_contract_block.txt genesis_validators_root.txt; do
  [ -s "$DEST/$f" ] || { echo "[$H] FATAL: $f missing or empty after sync" >&2; exit 1; }
done
echo "[$H] genesis loaded: ssz=$(stat -c %s "$DEST/genesis.ssz") gvr=$(cut -c1-18 "$DEST/genesis_validators_root.txt") time=$(grep -E '^MIN_GENESIS_TIME:' "$DEST/config.yaml" | awk '{print $2}')"
