#!/usr/bin/env bash
# Pre-genesis gate for a shadowfork: run after playbook.yaml started the ELs and before the
# CL genesis time. Exits non-zero if any check fails; every line says which host and why.
#   genesis.json: alloc keys 0x, request contract addresses, only the expected fork keys
#   per EL host:  head == shadowfork_height with the shadowfork_block.json hash, eth_config
#                 next activation == amsterdamTime, unique node id, peers only fleet IPs,
#                 /data < 85%, erigon snapshots/preverified.toml, ethrex chain-1/metadata.json
#
# Usage: scripts/shadowfork-pregenesis-check.sh <inventory dir, e.g. msf-1>
# Env:   RPC_URL_FMT  a host's RPC URL with {host} as placeholder (default: our public rpc-<host> URL)
set -euo pipefail

net="${1:?usage: $0 <inventory dir, e.g. msf-1>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
inv="$root/ansible/inventories/$net/inventory.ini"
vars="$root/ansible/inventories/$net/group_vars/all"
block_json="$root/ansible/inventories/$net/files/shadowfork_block.json"
meta="$root/network-configs/$net/metadata"
for f in "$inv" "$block_json" "$meta/genesis.json"; do [ -f "$f" ] || { echo "error: $f not found" >&2; exit 2; }; done

fail=0
bad() { echo "FAIL $*"; fail=1; }
ok() { echo "ok   $*"; }

height="$(yq '.shadowfork_height' "$vars/all.yaml")"
want_hash="$(jq -r '.result.hash' "$block_json")"
amsterdam="$(jq -r '.config.amsterdamTime' "$meta/genesis.json")"
printf 'expect head %s %s, amsterdamTime %s\n' "$height" "$want_hash" "$amsterdam"

# --- genesis.json / CL genesis ---
jq -e '[.alloc | keys[] | select(startswith("0x") | not)] | length == 0' "$meta/genesis.json" >/dev/null \
  && ok "genesis.json alloc keys 0x-prefixed" || bad "genesis.json alloc keys without 0x (run scripts/normalize-shadowfork-genesis.py)"
jq -e '.config.withdrawalRequestContractAddress and .config.consolidationRequestContractAddress' "$meta/genesis.json" >/dev/null \
  && ok "genesis.json request contract addresses" || bad "genesis.json lacks withdrawal/consolidation request addresses (besu)"
extra="$(jq -r '.config | keys[] | select(endswith("Time"))' "$meta/genesis.json" \
  | grep -vxE 'shanghaiTime|cancunTime|pragueTime|osakaTime|bpo1Time|bpo2Time|amsterdamTime' || true)"
[ -z "$extra" ] && ok "genesis.json fork times" || bad "genesis.json has unexpected fork times: $extra"
blobs="$(jq -r '.config.blobSchedule | keys[]' "$meta/genesis.json" | grep -vxE 'cancun|prague|osaka|bpo1|bpo2' || true)"
[ -z "$blobs" ] && ok "genesis.json blobSchedule" || bad "genesis.json has unexpected blobSchedule entries: $blobs"
cl_hash="$(cat "$meta/deposit_contract_block_hash.txt" 2>/dev/null || true)"
[ "$cl_hash" = "$want_hash" ] && ok "CL genesis builds on $want_hash" || bad "deposit_contract_block_hash.txt '$cl_hash' != block file hash"
fee="$(jq -r '.result.baseFeePerGas' "$block_json")"
echo "info head gasLimit $(( $(jq -r '.result.gasLimit' "$block_json") )) baseFee $(( fee )) wei"
[ $(( fee )) -lt 100000000000 ] || echo "warn baseFee >= 100 gwei: the 8282 deploy txs (100 gwei cap) wait for it to decay"

# --- per EL host, over RPC ---
user="$(sops -d --extract '["secret_nginx_shared_basic_auth"]["name"]' "$vars/all.sops.yaml")"
pass="$(sops -d --extract '["secret_nginx_shared_basic_auth"]["password"]' "$vars/all.sops.yaml")"
fmt="${RPC_URL_FMT:-}"
[ -n "$fmt" ] || fmt="https://$user:$pass@rpc-{host}.srv.glamsterdam-$net.ethpandaops.io"
fleet="$(grep -oE 'ansible_host=[0-9.]+' "$inv" | cut -d= -f2 | sort -u)"
hosts="$(cd "$root/ansible" && ansible -i "$inv" 'ethereum_node:bootnode' --list-hosts 2>/dev/null | tail -n +2 | tr -d ' ')"
rpc() { curl -sf --max-time 15 -X POST -H 'content-type: application/json' \
  --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":$3}" "${fmt//\{host\}/$1}"; }
ids="$(mktemp)"; trap 'rm -f "$ids"' EXIT
for h in $hosts; do
  b="$(rpc "$h" eth_getBlockByNumber '["latest",false]' || true)"
  num="$(jq -r '.result.number // empty' <<<"$b" 2>/dev/null)"; hash="$(jq -r '.result.hash // empty' <<<"$b" 2>/dev/null)"
  if [ -z "$num" ]; then bad "$h: no RPC answer"; continue; fi
  [ "$(( num ))" = "$height" ] && [ "$hash" = "$want_hash" ] && ok "$h head $height" \
    || bad "$h head $(( num )) $hash"
  next="$(rpc "$h" eth_config '[]' | jq -r '.result.next.activationTime // empty' 2>/dev/null || true)"
  if [ -z "$next" ]; then echo "warn $h: no eth_config, check amsterdamTime in its startup log"
  elif [ "$(( next ))" = "$amsterdam" ]; then ok "$h eth_config next $amsterdam"
  else bad "$h eth_config next activation $(( next )) != $amsterdam"; fi
  rpc "$h" admin_nodeInfo '[]' | jq -r --arg h "$h" '.result.id // empty | "\(.) \($h)"' >> "$ids" 2>/dev/null || true
  # every public IPv4 in admin_peers must be ours (private/container addresses are skipped)
  foreign="$(rpc "$h" admin_peers '[]' 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | sort -u \
    | grep -vE '^(10|127)\.|^172\.(1[6-9]|2[0-9]|3[01])\.|^192\.168\.' | grep -vxF "$fleet" || true)"
  [ -z "$foreign" ] && ok "$h peers fleet-only" || bad "$h non-fleet peers: $(echo $foreign)"
done
dups="$(awk '{print $1}' "$ids" | sort | uniq -d)"
answered="$(wc -l < "$ids")"; total="$(wc -w <<<"$hosts")"
if [ -n "$dups" ]; then bad "shared node ids: $(grep -F "$dups" "$ids" | awk '{print $2}' | tr '\n' ' ')"
elif [ "$answered" -lt "$total" ]; then bad "admin_nodeInfo answered by $answered/$total hosts"
else ok "node ids unique ($answered hosts)"; fi

# --- per host, on disk ---
cd "$root/ansible"
ansible -i "$inv" 'ethereum_node:bootnode' -b -o -m shell -a '
  u=$(df -P /data | awk "NR==2{print int(\$5)}"); [ "$u" -lt 85 ] && echo "disk=${u}%" || echo "BAD disk=${u}%"
  [ ! -d /data/erigon ] || { [ -f /data/erigon/snapshots/preverified.toml ] && echo erigon-preverified || echo "BAD no erigon preverified.toml"; }
  [ ! -d /data/ethrex/chain-1 ] || { [ -f /data/ethrex/chain-1/metadata.json ] && echo ethrex-metadata || echo "BAD no ethrex metadata.json"; }' 2>/dev/null \
  | sed -nE 's/^([^ ]+) \| [A-Z]+.*\(stdout\) (.*)$/\1 \2/p; t; s/^([^ ]+) \| (FAILED|UNREACHABLE).*/\1 BAD \2/p' \
  > "$ids.disk" || true
while read -r h rest; do
  case "$rest" in *BAD*) bad "$h $rest";; *) ok "$h $rest";; esac
done < "$ids.disk"
rm -f "$ids.disk"

[ "$fail" = 0 ] && echo "PASS: all pre-genesis checks" || { echo "NOT READY: fix the FAIL lines"; exit 1; }
