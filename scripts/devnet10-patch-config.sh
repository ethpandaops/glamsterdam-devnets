#!/usr/bin/env bash
# Patch config.yaml in place and restart the beacon so it re-reads it.
#
# Only for keys that are NOT baked into genesis.ssz: networking/timing params. The
# fork digest is fork_version + genesis_validators_root, neither of which changes, so
# peers stay compatible. Does NOT touch anything in the EL genesis or the CL state.
#
# args: KEY=VALUE [KEY=VALUE ...]
#   ansible ethereum_node -b -f 400 -m script -a "../scripts/devnet10-patch-config.sh SUBNETS_PER_NODE=2 AGGREGATE_DUE_BPS_GLOAS=6667"

set -euo pipefail
CFG=/data/ethereum-network-config/metadata/config.yaml
H=$(hostname)
[ $# -gt 0 ] || { echo "[$H] FATAL: no KEY=VALUE given" >&2; exit 1; }
[ -f "$CFG" ] || { echo "[$H] FATAL: $CFG missing" >&2; exit 1; }

cp -a "$CFG" "$CFG.bak.$(date +%s)"
CHANGED=0
for kv in "$@"; do
  K=${kv%%=*}; V=${kv#*=}
  grep -qE "^$K:" "$CFG" || { echo "[$H] FATAL: key $K not in $CFG" >&2; exit 1; }
  OLD=$(grep -E "^$K:" "$CFG" | head -1 | sed "s/^$K:[[:space:]]*//")
  if [ "$OLD" = "$V" ]; then echo "[$H] $K already $V"; continue; fi
  sed -i "s|^$K:.*|$K: $V|" "$CFG"
  NEW=$(grep -E "^$K:" "$CFG" | head -1 | sed "s/^$K:[[:space:]]*//")
  [ "$NEW" = "$V" ] || { echo "[$H] FATAL: $K did not take ($NEW)" >&2; exit 1; }
  echo "[$H] $K: $OLD -> $NEW"; CHANGED=1
done

if [ "$CHANGED" = 1 ]; then
  if docker ps --filter name=beacon --filter status=running -q | grep -q .; then
    docker restart beacon >/dev/null
    sleep 3
    s=$(docker inspect beacon 2>/dev/null | jq -r '.[0].State.Status')
    [ "$s" = running ] || { echo "[$H] FATAL: beacon is '$s' after restart" >&2; exit 1; }
    echo "[$H] beacon restarted, running"
  else
    echo "[$H] beacon not running, config patched only"
  fi
fi
