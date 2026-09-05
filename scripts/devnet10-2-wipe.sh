#!/usr/bin/env bash
# 2/4  Stop beacon/execution/validator, wipe chain data and slashing protection.
# KEEPS the validator keys, so no key regeneration is needed:
#   wiped : /data/geth, /data/prysm, /data/prysm-validator/validator.db
#   kept  : /data/prysm-validator/wallet, wallet_pass.txt, .validator_keyrange,
#           /data/validator-keys-src, /data/execution-auth.secret
# validator.db MUST go: the new genesis keeps the same validator set, so the
# genesis_validators_root is unchanged and prysm would treat old slots as already signed.
#   ansible 'all:!localhost' -b -f 400 -m script -a ../scripts/devnet10-2-wipe.sh
set -euo pipefail
H=$(hostname)
VD=/data/prysm-validator

for c in validator beacon execution; do docker rm -f "$c" >/dev/null 2>&1 || true; done

rm -rf /data/geth /data/prysm
if [ -d "$VD" ]; then
  rm -f "$VD"/validator.db "$VD"/validator.db-shm "$VD"/validator.db-wal
  rm -rf "$VD"/backups "$VD"/logs
fi

# refuse to continue silently if the keys went missing
K="$VD/wallet/direct/accounts/all-accounts.keystore.json"
[ -f "$K" ] || { echo "[$H] FATAL: validator keys are gone ($K)" >&2; exit 1; }
[ -f "$VD/wallet_pass.txt" ] || { echo "[$H] FATAL: wallet_pass.txt is gone" >&2; exit 1; }
[ ! -e "$VD/validator.db" ] || { echo "[$H] FATAL: validator.db still present" >&2; exit 1; }
[ ! -e /data/geth ] || { echo "[$H] FATAL: /data/geth still present" >&2; exit 1; }

echo "[$H] wiped: containers removed, chain data gone, slashing db gone, keys intact"
