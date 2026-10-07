#!/usr/bin/env bash
# Fund a shadowfork's tooling wallets from the genesis withdrawal sweep.
#
# Shadowfork genesis adds no premines. Instead every genesis validator starts with
# VALIDATOR_BALANCE (10000 ETH) and 0x01 credentials to mnemonic index 0, so the
# excess above 32 ETH is swept there (16 validators per block, ~160k ETH/block).
# This tops up the wallets devnet-8 premined - mnemonic accounts 1-20 (faucet,
# spamoor/goomy, assertoor, buildoor wallet, mev-flood, ...), the two faucet-agents
# wallets and the L2 addresses - from index 0, as far as the sweep has paid out so
# far. Re-run until nothing is left short; it only ever sends the shortfall.
#
# Usage: scripts/fund-shadowfork.sh <inventory dir, e.g. sepsf-1> [--dry-run]
# Env:   RPC_ENDPOINT (default: rpc-bootnode-1 of the network), FUND_EACH_ETH,
#        FUND_AGENTS_ETH, FUND_STATIC_ETH, FUND_RESERVE_ETH
set -euo pipefail

net="${1:?usage: $0 <inventory dir, e.g. sepsf-1> [--dry-run]}"
dry_run=false; [ "${2:-}" = "--dry-run" ] && dry_run=true
root="$(cd "$(dirname "$0")/.." && pwd)"
vars="$root/ansible/inventories/$net/group_vars/all"

each_eth="${FUND_EACH_ETH:-2000000}"     # mnemonic accounts 1-20
agents_eth="${FUND_AGENTS_ETH:-5000000}" # faucet-agents wallets
static_eth="${FUND_STATIC_ETH:-100000}"  # arbitrum / optimism / lido
reserve_eth="${FUND_RESERVE_ETH:-1000}"  # left on index 0 for gas

die() { echo "error: $*" >&2; exit 1; }

# Secrets stay off argv: the mnemonic goes to a 0600 file cast reads, the basic
# auth into ETH_RPC_URL.
tmp="$(mktemp -d)"; chmod 700 "$tmp"; trap 'rm -rf "$tmp"' EXIT
sops -d --extract '["secret_genesis_mnemonic"]' "$vars/all.sops.yaml" > "$tmp/mnemonic"
user="$(sops -d --extract '["secret_nginx_shared_basic_auth"]["name"]' "$vars/all.sops.yaml")"
pass="$(sops -d --extract '["secret_nginx_shared_basic_auth"]["password"]' "$vars/all.sops.yaml")"
rpc_prefix="$(yq '.ethereum_node_rpc_prefix' "$vars/all.yaml")"
export ETH_RPC_URL="${RPC_ENDPOINT:-https://$user:$pass@${rpc_prefix}bootnode-1.srv.glamsterdam-$net.ethpandaops.io}"

# The shadowfork keeps the parent chain's id, so the chain id alone cannot tell it
# from the real network. The block right after shadowfork_height can: on the
# shadowfork it was built after our genesis, on the parent chain long before.
chain_id="$(yq '.ethereum_genesis_chain_id' "$vars/all.yaml")"
height="$(yq '.shadowfork_height' "$vars/all.yaml")"
genesis="$(yq '.ethereum_genesis_timestamp' "$vars/all.yaml")"
[ "$(cast chain-id)" = "$chain_id" ] || die "RPC chain id is not $chain_id"
ts_hex="$(cast block $((height + 1)) --json 2>/dev/null | jq -r '.timestamp // empty')" \
  || die "block $((height + 1)) not found: the shadowfork has not produced a block yet"
[ -n "$ts_hex" ] || die "block $((height + 1)) not found: the shadowfork has not produced a block yet"
[ "$(printf '%d' "$ts_hex")" -ge "$genesis" ] \
  || die "block $((height + 1)) predates genesis $genesis: this RPC is on the parent chain, not the shadowfork"

wallet=(--mnemonic "$tmp/mnemonic" --mnemonic-index 0)
treasury="$(cast wallet address "${wallet[@]}")"

# address target_eth label, in funding order: while the sweep is still paying out,
# the wallets devnet-8's tooling actually sends from come first - 12 and 21 buildoor wallets
# (builders must deposit and finalize before the fork), 9 goomy/spamoor, 4 faucet,
# 10 assertoor, 3 mev-flood user, 7 manual deposits, 20 - then the agent faucet,
# then the remaining premine accounts.
{
  for i in 12 21 9 4 10 3 7 20; do
    echo "$(cast wallet address --mnemonic "$tmp/mnemonic" --mnemonic-index "$i") $each_eth mnemonic-$i"
  done
  echo "0x877d64e72b7e1f5034aec55d910c877b2b7104da $agents_eth faucet-agents-claims"
  echo "0x2aa5f02f347089910eea88279c405149ec8540d5 $agents_eth faucet-agents-status"
  for i in 1 2 5 6 8 11 13 14 15 16 17 18 19; do
    echo "$(cast wallet address --mnemonic "$tmp/mnemonic" --mnemonic-index "$i") $each_eth mnemonic-$i"
  done
  echo "0x9a97ee9d32a0d68406e32b34c92afb81ce2bc467 $static_eth arbitrum"
  echo "0x107781Bc6FA8f66B843f4216fd6D5862D3aa4fcd $static_eth optimism"
  echo "0x118A1030baf8Fa56f9B8235C163d3112FA8c3b89 $static_eth lido"
} > "$tmp/recipients"

wei() { cast to-wei "$1" ether; }
available="$(echo "$(cast balance "$treasury") - $(wei "$reserve_eth")" | bc)"
echo "treasury $treasury (mnemonic 0): $(cast from-wei "$(cast balance "$treasury")") ETH, spendable $(cast from-wei "${available#-}") ETH$([ "${available:0:1}" = "-" ] && echo ' (negative)')"

nonce="$(cast nonce "$treasury" --block pending)"
sent=0; short=0; : > "$tmp/txs"
while read -r addr target label; do
  # Skip EIP-7702-delegated wallets inherited from the parent chain: sepolia's mnemonic-1/2
  # and mainnet's mnemonic-4 (faucet) delegate to sweepers that forward every deposit away.
  code="$(cast code "$addr")"
  if [ "${code:0:8}" = "0xef0100" ]; then
    printf '  %-22s %s skipped: EIP-7702-delegated to 0x%s\n' "$label" "$addr" "${code:8}"
    continue
  fi
  balance="$(cast balance "$addr")"
  deficit="$(echo "$(wei "$target") - $balance" | bc)"
  if [ "$(echo "$deficit <= 0" | bc)" = 1 ]; then
    printf '  %-22s %s ok (%s ETH)\n' "$label" "$addr" "$(cast from-wei "$balance")"
    continue
  fi
  amount="$deficit"
  if [ "$(echo "$amount > $available" | bc)" = 1 ]; then
    amount="$available"; short=$((short + 1))
  fi
  if [ "$(echo "$amount <= 0" | bc)" = 1 ]; then
    printf '  %-22s %s needs %s ETH, nothing spendable yet\n' "$label" "$addr" "$(cast from-wei "$deficit")"
    continue
  fi
  printf '  %-22s %s +%s ETH\n' "$label" "$addr" "$(cast from-wei "$amount")"
  available="$(echo "$available - $amount" | bc)"
  if ! $dry_run; then
    cast send "${wallet[@]}" --async --nonce "$nonce" --value "$amount" "$addr" >> "$tmp/txs"
    nonce=$((nonce + 1)); sent=$((sent + 1))
  fi
done < "$tmp/recipients"

if $dry_run; then echo "dry run: nothing sent"; exit 0; fi
failed=0
while read -r tx; do
  # A dropped tx never gets a receipt and cast would wait forever; count it as
  # failed so the next run re-sends from the pending nonce.
  status="$(timeout 120 cast receipt "$tx" status 2>/dev/null || echo "no receipt after 120s")"
  case "$status" in 1|1*\(success\)*|success) ;; *) echo "  tx $tx: $status" >&2; failed=$((failed + 1)) ;; esac
done < "$tmp/txs"
echo "sent $sent transfer(s), $failed failed; $short recipient(s) not fully funded yet"
[ "$failed" -eq 0 ] || exit 1
[ "$short" -eq 0 ] || echo "the sweep has not paid out enough yet: re-run in a few minutes"
