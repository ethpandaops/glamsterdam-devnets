#!/usr/bin/env bash
# Deploy a shadowfork's own (ungated) deposit contract.
#
# Sepolia's deposit contract is also the BEPOLIA ERC-20 and burns one token per
# deposit, which nobody on a shadowfork holds. Networks that set
# `shadowfork_deposit_contract_address` (see ansible/tasks/shadowfork_deposit_contract.yaml)
# point every EL at the standard mainnet deposit contract instead, deployed through
# the CREATE2 deployer 0x4e59b448...4956C with a fixed salt - so the address below is
# the same on every shadowfork. Nothing exists there at genesis; run this once the
# withdrawal sweep has funded mnemonic index 0 (minutes after genesis). Deposits
# (and pre-Gloas builder onboarding) work from the block it lands in. Re-running is a
# no-op once the code is there.
#
# Usage: scripts/deploy-shadowfork-deposit-contract.sh <inventory dir, e.g. sepsf-2> [--dry-run]
# Env:   RPC_ENDPOINT (default: rpc-bootnode-1 of the network)
set -euo pipefail

net="${1:?usage: $0 <inventory dir, e.g. sepsf-2> [--dry-run]}"
dry_run=false; [ "${2:-}" = "--dry-run" ] && dry_run=true
root="$(cd "$(dirname "$0")/.." && pwd)"
vars="$root/ansible/inventories/$net/group_vars/all"
initcode="$(tr -d '[:space:]' < "$root/scripts/shadowfork/deposit_contract.creation.hex")"

create2_deployer=0x4e59b44847b379578588920cA78FbF26c0B4956C
salt="$(cast keccak "ethpandaops/shadowfork-deposit-contract")"
# keccak256 of the mainnet deposit contract's runtime code (0x00000000219ab540...05Fa)
runtime_hash=0x6c029a231254fadb724d63be769f75eedd66362df034a3e663252b49d062a666

die() { echo "error: $*" >&2; exit 1; }

address="$(cast create2 --deployer "$create2_deployer" --salt "$salt" --init-code "$initcode")"
configured="$(yq '.shadowfork_deposit_contract_address // ""' "$vars/all.yaml")"
[ -n "$configured" ] || die "$net does not set shadowfork_deposit_contract_address (its ELs watch another deposit contract)"
[ "${configured,,}" = "${address,,}" ] || die "shadowfork_deposit_contract_address is $configured, the CREATE2 address is $address"
genesis_file="$root/network-configs/${net}/metadata/genesis.json"
if [ -f "$genesis_file" ]; then
  in_genesis="$(jq -r '.config.depositContractAddress' "$genesis_file")"
  [ "${in_genesis,,}" = "${address,,}" ] || die "$genesis_file uses deposit contract $in_genesis, not $address"
fi

# Secrets stay off argv: the mnemonic goes to a 0600 file cast reads, the basic
# auth into ETH_RPC_URL.
tmp="$(mktemp -d)"; chmod 700 "$tmp"; trap 'rm -rf "$tmp"' EXIT
sops -d --extract '["secret_genesis_mnemonic"]' "$vars/all.sops.yaml" > "$tmp/mnemonic"
user="$(sops -d --extract '["secret_nginx_shared_basic_auth"]["name"]' "$vars/all.sops.yaml")"
pass="$(sops -d --extract '["secret_nginx_shared_basic_auth"]["password"]' "$vars/all.sops.yaml")"
rpc_prefix="$(yq '.ethereum_node_rpc_prefix' "$vars/all.yaml")"
export ETH_RPC_URL="${RPC_ENDPOINT:-https://$user:$pass@${rpc_prefix}bootnode-1.srv.glamsterdam-$net.ethpandaops.io}"

# Same guard as fund-shadowfork.sh: only ever send on the shadowfork, never on the
# parent chain (same chain id, same pre-fork state).
chain_id="$(yq '.ethereum_genesis_chain_id' "$vars/all.yaml")"
height="$(yq '.shadowfork_height' "$vars/all.yaml")"
genesis="$(yq '.ethereum_genesis_timestamp' "$vars/all.yaml")"
[ "$(cast chain-id)" = "$chain_id" ] || die "RPC chain id is not $chain_id"
ts_hex="$(cast block $((height + 1)) --json 2>/dev/null | jq -r '.timestamp // empty')" || true
[ -n "$ts_hex" ] || die "block $((height + 1)) not found: the shadowfork has not produced a block yet"
[ "$(printf '%d' "$ts_hex")" -ge "$genesis" ] \
  || die "block $((height + 1)) predates genesis $genesis: this RPC is on the parent chain, not the shadowfork"

[ "$(cast code "$create2_deployer")" != "0x" ] || die "CREATE2 deployer $create2_deployer has no code on this chain"

code="$(cast code "$address")"
if [ "$code" != "0x" ]; then
  [ "$(cast keccak "$code")" = "$runtime_hash" ] || die "$address has code, but not the deposit contract's"
  echo "deposit contract already deployed at $address"
  exit 0
fi

wallet=(--mnemonic "$tmp/mnemonic" --mnemonic-index 0)
deployer="$(cast wallet address "${wallet[@]}")"
echo "deploying the deposit contract to $address from $deployer (balance $(cast from-wei "$(cast balance "$deployer")") ETH)"
if $dry_run; then echo "dry run: nothing sent"; exit 0; fi

# The CREATE2 deployer takes salt ++ initcode as calldata.
cast send "${wallet[@]}" "$create2_deployer" "${salt}${initcode#0x}" --gas-limit 3000000 > /dev/null
code="$(cast code "$address")"
[ "$code" != "0x" ] || die "deployment transaction mined, but $address still has no code"
[ "$(cast keccak "$code")" = "$runtime_hash" ] || die "$address has unexpected code"
echo "deposit contract deployed at $address (deposit root $(cast call "$address" 'get_deposit_root()(bytes32)'))"
