#!/usr/bin/env zsh
# Throwaway: deploy the EIP-8282 builder deposit/exit contracts on a live
# devnet BEFORE the gloas fork. devnet-7 genesis omits them on purpose
# (DEPLOY_EIP8282_CONTRACTS=false) so this manual workflow gets exercised.
#
# Deployment goes through the deterministic CREATE2 factory
# (0x4e59b4...956C, predeployed in devnet genesis as a well-known contract)
# with the vanity-mined salts from ethereum/execution-specs#3091 — the same
# salt+initcode pairs the EL clients' `glamsterdam-devnet-7` branches expect.
# CREATE2(factory, salt, initcode) == the addresses below; the initcode's
# runtime is byte-identical to the egg v6.1.3 genesis predeploy, and the exit
# contract's constructor sets the slot-0 excess inhibitor.
#
# Usage:  ./deploy-eip8282.zsh [check]
#   check   only report on-chain state, do not send anything
#   FORCE=1 skip the pre-gloas epoch guard

set -u

node="${NODE:-bootnode-1}"
network="${NETWORK:-devnet-7}"
domain="ethpandaops.io"
srv="srv"
prefix="glamsterdam"

sops_name=$(sops --decrypt ../ansible/inventories/$network/group_vars/all/all.sops.yaml | yq -r '.secret_nginx_shared_basic_auth.name')
sops_password=$(sops --decrypt ../ansible/inventories/$network/group_vars/all/all.sops.yaml | yq -r '.secret_nginx_shared_basic_auth.password')
sops_mnemonic=$(sops --decrypt ../ansible/inventories/$network/group_vars/all/all.sops.yaml | yq -r '.secret_genesis_mnemonic')
rpc_endpoint="${RPC_ENDPOINT:-https://$sops_name:$sops_password@rpc-$node.$srv.$prefix-$network.$domain}"
bn_endpoint="${BEACON_ENDPOINT:-https://$sops_name:$sops_password@bn-$node.$srv.$prefix-$network.$domain}"

factory="0x4e59b44847b379578588920cA78FbF26c0B4956C"

# ethereum/execution-specs#3091: builder_deposit_factory_deploy.json /
# builder_exit_factory_deploy.json. Runtime = initcode minus the constructor
# prefix (10 bytes for deposit, 45 for exit — the exit ctor is
# PUSH32 <2^256-1> PUSH0 SSTORE followed by the codecopy-return).
typeset -A name address salt initcode ctor_hexlen
contracts=(deposit exit)

name[deposit]="EIP-8282 builder deposit (request type 0x03)"
address[deposit]="0x0000bFF46984e3725691FA540a8C7589300D8282"
salt[deposit]="1f4f2c41c28e816e259b621c58b94b37309c8dec42c8f6e400001a46c9d96bf7"
ctor_hexlen[deposit]=20
initcode[deposit]="61027480600a5f395ff33373fffffffffffffffffffffffffffffffffffffffe1461011c575f54807fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff146102705760015460088111605257506058565b60089003015b601190600182026001905f5b5f821115607f57810190830284830290049160010191906064565b90939004925050503660b814609f57366102705734610270575f5260205ff35b8034106102705760383567ffffffffffffffff1680633b9aca001161027057633b9aca00029034031061027057600154600101600155600354806006026004015f358155600101602035815560010160403581556001016060358155600101608035815560010160a035905560b85f5f3760b85fa0600101600355005b60035460025480820380604011610131575060405b5f5b8181146101d7578281016006026004018160b8028154815260200181600101548152602001816002015480825260401c67ffffffffffffffff16816010018160381c81600701538160301c81600601538160281c81600501538160201c81600401538160181c81600301538160101c81600201538160081c816001015353602001816003015481526020018160040154815260200190600501549052600101610133565b91018092146101e957906002556101f4565b90505f6002555f6003555b36610242575f54600154817fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff1461023057600882820111610238575b50505f610264565b0160089003610264565b7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff5b5f555f60015560b8025ff35b5f5ffd"

name[exit]="EIP-8282 builder exit (request type 0x04)"
address[exit]="0x000064D678505ad48F8cCb093BC65613800E8282"
salt[exit]="89abb1878437213f971f849327423ed1d9c5cdb03970cd8f0000318b3ff10119"
ctor_hexlen[exit]=90
initcode[exit]="7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff5f556101ca80602d5f395ff33373fffffffffffffffffffffffffffffffffffffffe1460e1575f54807fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff146101c65760015460028111605157506057565b60029003015b601190600182026001905f5b5f821115607e57810190830284830290049160010191906063565b909390049250505036603014609e57366101c657346101c6575f5260205ff35b34106101c657600154600101600155600354806003026004013381556001015f35815560010160203590553360601b5f5260305f60143760445fa0600101600355005b6003546002548082038060101160f5575060105b5f5b81811461012d5782810160030260040181604402815460601b8152601401816001015481526020019060020154905260010160f7565b910180921461013f579060025561014a565b90505f6002555f6003555b36610198575f54600154817fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff146101865760028282011161018e575b50505f6101ba565b01600290036101ba565b7fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff5b5f555f6001556044025ff35b5f5ffd"

inhibitor="0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"

code_at() { cast code "$1" --rpc-url "$rpc_endpoint" 2>/dev/null }

# Sanity: the CREATE2 factory must exist (devnet genesis predeploys it).
if [[ "$(code_at $factory)" == "0x" ]]; then
  echo "CREATE2 factory $factory has no code on this network — cannot deploy." >&2
  exit 1
fi

# Sanity: each salt+initcode must still map to its expected vanity address.
for c in "${contracts[@]}"; do
  computed=$(cast create2 --deployer "$factory" --salt "0x${salt[$c]}" --init-code "0x${initcode[$c]}" 2>/dev/null | grep -oE '0x[0-9a-fA-F]{40}' | head -1)
  if [[ "${computed:l}" != "${address[$c]:l}" ]]; then
    echo "CREATE2 mismatch for $c: computed $computed, expected ${address[$c]} — refusing to deploy." >&2
    exit 1
  fi
done

report() {
  local c code slot0
  for c in "${contracts[@]}"; do
    code=$(code_at "${address[$c]}")
    slot0=$(cast storage "${address[$c]}" 0 --rpc-url "$rpc_endpoint" 2>/dev/null)
    if [[ "$code" == "0x${initcode[$c]:${ctor_hexlen[$c]}}" ]]; then
      printf "  \033[32m✓\033[0m %s at %s (runtime matches, slot0=%s)\n" "$c" "${address[$c]}" "${slot0:0:10}..."
    elif [[ "$code" == "0x" ]]; then
      printf "  \033[31m✗\033[0m %s at %s — no code\n" "$c" "${address[$c]}"
    else
      printf "  \033[31m✗\033[0m %s at %s — UNEXPECTED code (%d bytes)\n" "$c" "${address[$c]}" $(( (${#code} - 2) / 2 ))
    fi
  done
}

if [[ "${1:-}" == "check" ]]; then
  echo "State on $prefix-$network:"
  report
  exit 0
fi

# Guard: the deployments must land before the gloas fork activates.
gloas_epoch=$(curl -s "$bn_endpoint/eth/v1/config/spec" | jq -r '.data.GLOAS_FORK_EPOCH')
head_slot=$(curl -s "$bn_endpoint/eth/v1/beacon/headers/head" | jq -r '.data.header.message.slot')
if [[ -z "$gloas_epoch" || "$gloas_epoch" == "null" || -z "$head_slot" || "$head_slot" == "null" ]]; then
  echo "Could not read GLOAS_FORK_EPOCH/head slot from $node's beacon API." >&2
  [[ "${FORCE:-0}" == "1" ]] || exit 1
else
  head_epoch=$((head_slot / 32))
  echo "Head epoch: $head_epoch | gloas fork epoch: $gloas_epoch"
  if (( head_epoch >= gloas_epoch )) && [[ "${FORCE:-0}" != "1" ]]; then
    echo "Gloas is already active — deploying now is too late (every block since activation is invalid without these contracts). FORCE=1 to override." >&2
    exit 1
  fi
fi

deployer_key=$(ethereal hd keys --path="m/44'/60'/0'/0/7" --seed="$sops_mnemonic" | awk '/Private key/{print $NF}')
deployer_addr=$(ethereal hd keys --path="m/44'/60'/0'/0/7" --seed="$sops_mnemonic" | awk '/Ethereum address/{print $NF}')

echo "Deploying EIP-8282 contracts on $prefix-$network via CREATE2 factory $factory"
echo "  from: $deployer_addr (mnemonic account 7 / manual-deposits)"
for c in "${contracts[@]}"; do
  echo "  ${name[$c]} -> ${address[$c]}"
done
echo "Continue? (y/n)"
read -r response
[[ "$response" == "y" ]] || { echo "Aborted."; exit 0 }

for c in "${contracts[@]}"; do
  if [[ "$(code_at ${address[$c]})" != "0x" ]]; then
    echo "$c already has code at ${address[$c]} — skipping."
    continue
  fi
  echo "Deploying $c..."
  # The factory takes raw calldata of salt (32 bytes) ++ initcode.
  out=$(cast send "$factory" "0x${salt[$c]}${initcode[$c]}" \
    --private-key "$deployer_key" \
    --rpc-url "$rpc_endpoint" \
    --gas-limit 1500000 2>&1)
  tx_status=$(echo "$out" | awk '/^status/{print $2}' | head -1)
  txhash=$(echo "$out" | awk '/^transactionHash/{print $2}' | head -1)
  if [[ "$tx_status" != "1" && "$out" != *'"status":"0x1"'* ]]; then
    echo "$c deployment tx failed (tx=${txhash:-none}):" >&2
    echo "$out" | grep -iE 'error|revert' | head -3 >&2
    exit 1
  fi
  echo "  tx: $txhash"
done

echo ""
echo "Post-deploy verification:"
report

# The exit contract must hold the excess inhibitor until the first gloas
# system call clears it; the deposit contract intentionally has no inhibitor.
exit_slot0=$(cast storage "${address[exit]}" 0 --rpc-url "$rpc_endpoint" 2>/dev/null)
if [[ "${exit_slot0:l}" != "$inhibitor" ]]; then
  echo "WARNING: exit contract slot0 is $exit_slot0, expected the excess inhibitor $inhibitor" >&2
  exit 1
fi
echo "Exit contract inhibitor armed. Done — contracts are live ahead of gloas."
