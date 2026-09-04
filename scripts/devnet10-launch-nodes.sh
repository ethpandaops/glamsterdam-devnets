#!/usr/bin/env bash
# Fallback launcher for devnet-10: brings up a full node with plain `docker run`,
# reproducing what the ethereum_node role produces, for use if the playbook is still
# grinding as genesis approaches.
#
# Containers: execution (geth), snooper-engine, beacon (prysm), validator (prysm),
# plus xatu-sentry and ethereum-metrics-exporter where their configs are already on
# the host. Runs ON a target host, invoked as root.
#
# Matches what the ethereum_node role produces: same images, args, env, binds, port
# bindings, restart policy and client users. Verified by structural diff against a
# playbook-deployed host.
#
# ADDITIVE. The playbook may be running concurrently, creating users, datadirs and the
# JWT as it reaches each host, so this only fills gaps:
#   * a container already running as the right uid is left strictly alone;
#   * one running as the wrong uid is recreated, which repairs an earlier bad pass;
#   * the JWT is never regenerated -- geth and the beacon must share it.
#
# Client users are created by name (geth, prysm, json_rpc_snooper, xatu-sentry) exactly
# as the roles do, so the uid is whatever useradd picks on that host. It is NOT the same
# number fleet-wide -- 1004 is `geth` on some hosts and `besu` on others -- so the uid is
# always resolved, never hardcoded.
#
# Usage, one pass over the fleet (secrets come from sops at run time, never stored here):
#   ansible ethereum_node -b -f 400 -m script -a \
#     "../scripts/devnet10-launch-nodes.sh {{ inventory_hostname }} {{ ansible_host }} \
#      {{ ipv6 }} {{ ethereum_node_cl_supernode_enabled }} \
#      {{ goldfish_vote_ledger_enabled | default('False') }} \
#      {{ secret_nginx_shared_basic_auth.name }}:{{ secret_nginx_shared_basic_auth.password }} \
#      {{ (xatu_sentry_config_server_auth_user + ':' + xatu_sentry_config_server_auth_password) | b64encode }}"

set -euo pipefail

HOSTNAME_="${1:?hostname}"
IPV4="${2:?ipv4}"
IPV6_BASE="${3:?ipv6 base}"          # host /124 base, e.g. 2400:6180:100:d0:0:1:84dd:4000
SUPERNODE="${4:-False}"
GOLDFISH="${5:-False}"
SNOOPER_AUTH="${6:-}"                # user:pass for the snooper web API
XATU_TOKEN="${7:-}"                  # base64 of user:pass for the xatu ingest

NETWORK=glamsterdam-devnet-10
FQDN="${HOSTNAME_}.srv.${NETWORK}.ethpandaops.io"
XATU_INGEST="${NETWORK}-ingest.xatu.ethpandaops.io:443"
CFG=/data/ethereum-network-config/metadata
JWT=/data/execution-auth.secret
FEE_RECIPIENT=0xf97e180c050e5Ab072211Ad2C213Eb5AEE4DF134

GETH_IMAGE=registry-1.docker.io/ethpandaops/geth:master
PRYSM_IMAGE=registry-1.docker.io/ethpandaops/prysm-beacon-chain:sukunrt-decoupled-casper-a1679c9
PRYSM_VC_IMAGE=registry-1.docker.io/ethpandaops/prysm-validator:sukunrt-decoupled-casper-a1679c9
SNOOPER_IMAGE=registry-1.docker.io/ethpandaops/rpc-snooper:latest
XATU_IMAGE=registry-1.docker.io/ethpandaops/xatu:glamsterdam-devnet-9
METRICS_IMAGE=registry-1.docker.io/ethpandaops/ethereum-metrics-exporter:latest

# Entry points: bootnode-1 and prysm-geth-1, taken from prysm-geth-2's deployed config.
# The playbook builds this list from discovery facts, so later deploys carry more
# entries than earlier ones; these are the freshest observed.
EL_BOOTNODES='enr:-Iu4QGfx0TAic0NdYF5O3H2u-vD9f1PQnLfSdAE439jXk9UKEcZfOT0kpT7zylBgEe1n2eU0Im4I97BEoYhDpno9Qz2AgmlkgnY0gmlwhNEmKt-Jc2VjcDI1NmsxoQNCFIMEafM7qpPBn57r85qAVLAzibJVt2EO-BuIykMavYN0Y3CCdl-DdWRwgnZf,enr:-Iu4QFu0smn0cpVppOtspVFsw3XNo_frPiDPU500kwCOVrcQPPHhdB4AMb_1-DwCZjtEbbf2vDc4ZPJTGHgulZZgeqKAgmlkgnY0gmlwhKiQvWiJc2VjcDI1NmsxoQJywICPOkuAIHrpSXBUTx4_eew1DWg3w-ZCu4waoB4GAoN0Y3CCdl-DdWRwgnZf'
CL_BOOTNODE_1='enr:-Nm4QJwdWWQpkkkJXuDuWf75Y4EA3Q8f5iHKjpZhzrBjOe3QE0kkknyExHgJswR3A1uPwWoveTblCBVbGnc__VE92vaGAaBubMdfh2F0dG5ldHOIPwAAAAAAAACDY2djgYCEZXRoMpDeV6UakHlTB___________gmlkgnY0gmlwhNEmKt-DbmZkhAAAAACEcXVpY4IyyIlzZWNwMjU2azGhAxDsjUvPaVYk_dkjOHiNOx2AkUm_cXuP63Pxp8Jn59BTiHN5bmNuZXRzAIN0Y3CCIyiDdWRwgiMo'
CL_BOOTNODE_2='enr:-Nm4QK6G7FAK4lyaI1SdV7JSx2E9HsUEvjfhbXl7BNpWHoiJetq7OfXvH5Qi507LGQ6hpgfk-X-eMDTK2mNVmENfF06GAaBufcRgh2F0dG5ldHOIPwAAAAAAAACDY2djgYCEZXRoMpDeV6UakHlTB___________gmlkgnY0gmlwhKiQvWiDbmZkhAAAAACEcXVpY4IyyIlzZWNwMjU2azGhAvcWAyXHCM0Bz1fYet5K0pn_DnicN710GfgWE2Svz-0UiHN5bmNuZXRzAIN0Y3CCIyiDdWRwgiMo'

# Static IPv6 inside the host's /124, matching service_ipv6_offsets: execution :e,
# snooper_engine :d, beacon :b, validator :a.
# IPV6_BASE is the host's own address from the inventory, which is NOT /124-aligned
# (e.g. ...84dd:4001, ...8260:1). The playbook masks it with ipsubnet(124); do the same
# by clearing the low 4 bits, or the offsets land outside the block and collide with
# nginx-proxy at :f.
ip6() { printf '%s:%x' "${IPV6_BASE%:*}" "$(( (0x${IPV6_BASE##*:} & ~0xF) + $1 ))"; }
EXEC_IP6="$(ip6 14)"; SNOOP_IP6="$(ip6 13)"; BEACON_IP6="$(ip6 11)"; VC_IP6="$(ip6 10)"

fail() { echo "[$HOSTNAME_] FATAL: $*" >&2; exit 1; }
note() { echo "[$HOSTNAME_] $*"; }

# ---- preflight: refuse to start half a node -----------------------------------------
[ -f "$CFG/genesis.ssz" ]  || fail "no genesis.ssz in $CFG"
[ -f "$CFG/config.yaml" ]  || fail "no config.yaml in $CFG"
[ -f "$CFG/genesis.json" ] || fail "no genesis.json in $CFG"
[ -f /data/prysm-validator/wallet/direct/accounts/all-accounts.keystore.json ] \
  || fail "validator keys missing"
docker network inspect shared >/dev/null 2>&1 || fail "docker network 'shared' missing"

CHAIN_ID="$(python3 -c "import json;print(json.load(open('$CFG/genesis.json'))['config']['chainId'])")"
[ -n "$CHAIN_ID" ] || fail "could not read chainId"

if [ ! -f "$JWT" ]; then
  printf '0x%s' "$(openssl rand -hex 32)" > "$JWT"
fi
chown root:root "$JWT"; chmod 644 "$JWT"

# Same users the roles create (ansible.builtin.user with just a name), so the uid is
# whatever useradd picks on this host -- it is NOT the same number fleet-wide.
ensure_user() { id -u "$1" >/dev/null 2>&1 || useradd -m "$1"; id -u "$1"; }
GETH_UID="$(ensure_user geth)"
PRYSM_UID="$(ensure_user prysm)"
SNOOP_UID="$(ensure_user json_rpc_snooper)"
XATU_UID="$(ensure_user xatu-sentry)"

# Recursive: `install -d` sets the directory only, and a client started as root in an
# earlier pass leaves root-owned files inside it ("open /data/geth/LOCK: permission
# denied"). validator_keys can likewise land before the prysm user exists.
install -d -m 0750 /data/geth /data/prysm
chown -R geth:geth   /data/geth
chown -R prysm:prysm /data/prysm /data/prysm-validator
chmod 0750 /data/prysm-validator

# A running container is left alone unless it runs as the wrong uid -- which is how a
# root-started container from an earlier pass gets corrected. Compare uid only: the
# roles set User to a bare uid, this script sets uid:gid.
needs_start() {
  local name="$1" want="${2:-0}" st cur
  st="$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null || echo missing)"
  if [ "$st" = running ]; then
    cur="$(docker inspect -f '{{.Config.User}}' "$name" 2>/dev/null || echo)"
    cur="${cur%%:*}"; cur="${cur:-0}"
    case "$cur" in ''|root) cur=0 ;; *[!0-9]*) cur="$(id -u "$cur" 2>/dev/null || echo 0)" ;; esac
    if [ "$cur" = "${want%%:*}" ]; then note "$name already running, left untouched"; return 1; fi
    note "$name runs as uid $cur, want ${want%%:*} -- recreating"
  fi
  [ "$st" = missing ] || docker rm -f "$name" >/dev/null 2>&1 || true
  return 0
}

# `docker run --ip6` fails if the address was already handed out to an auto-assigned
# container. Retry without it rather than leaving the node down; IPv4 still works.
run_with_ip6() {
  local ip6="$1" name="$2"; shift 2
  if docker run --ip6 "$ip6" "$@" >/dev/null 2>&1; then return 0; fi
  note "warn: --ip6 $ip6 rejected, starting $name without a static IPv6"
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run "$@" >/dev/null
}

# ---- execution: geth -----------------------------------------------------------------
if needs_start execution "$GETH_UID"; then
run_with_ip6 "$EXEC_IP6" execution \
  -d --name execution --restart always --network shared \
  --user "$GETH_UID:$GETH_UID" \
  -e "VIRTUAL_HOST=rpc-$FQDN" -e VIRTUAL_PORT=8545 -e "LETSENCRYPT_HOST=rpc-$FQDN" \
  -v /data/geth:/data:rw -v "$JWT:/execution-auth.jwt:ro" -v "$CFG:/network-config:ro" \
  -p 0.0.0.0:30303:30303/tcp -p 0.0.0.0:30303:30303/udp \
  -p 127.0.0.1:8545:8545 -p 127.0.0.1:8551:8551 -p 127.0.0.1:6060:6060 \
  --entrypoint geth "$GETH_IMAGE" \
  --datadir=/data --port=30303 \
  --http --http.addr=0.0.0.0 --http.port=8545 \
  --authrpc.addr=0.0.0.0 --authrpc.port=8551 --authrpc.vhosts='*' \
  --authrpc.jwtsecret=/execution-auth.jwt \
  --nat="extip:$IPV4" \
  --metrics --metrics.port=6060 --metrics.addr=0.0.0.0 \
  --discovery.v5 \
  --nat="extip:$EXEC_IP6" \
  --override.genesis=/network-config/genesis.json \
  --http.api=eth,net,web3,debug,admin,txpool --http.vhosts='*' \
  --networkid="$CHAIN_ID" --syncmode=full \
  --bootnodes="$EL_BOOTNODES" \
  --discovery.v4=false --discovery.v5=true
fi

# ---- engine-API snooper (sits between beacon and execution) --------------------------
if needs_start snooper-engine "$SNOOP_UID"; then
SNOOP_ENV=(-e SNOOPER_JWT_SECRET=/execution-auth.jwt)
if [ -n "$SNOOPER_AUTH" ]; then SNOOP_ENV+=(-e "SNOOPER_API_PORT=8961" -e "SNOOPER_API_AUTH=$SNOOPER_AUTH"); fi
if [ -n "$XATU_TOKEN" ]; then
  SNOOP_ENV+=(
    -e SNOOPER_XATU_ENABLED=true
    -e "SNOOPER_XATU_NAME=$NETWORK-$HOSTNAME_"
    -e "SNOOPER_XATU_NETWORK_NAME=$NETWORK"
    -e "SNOOPER_XATU_NETWORK_ID=$CHAIN_ID"
    -e "SNOOPER_XATU_OUTPUTS=xatu:$XATU_INGEST"
    -e SNOOPER_XATU_TLS=true
    -e "SNOOPER_XATU_HEADERS=authorization=Basic $XATU_TOKEN"
  )
else
  note "warn: no xatu token given, snooper runs without the xatu output"
fi
run_with_ip6 "$SNOOP_IP6" snooper-engine \
  -d --name snooper-engine --restart always --network shared \
  --user "$SNOOP_UID:$SNOOP_UID" \
  "${SNOOP_ENV[@]}" \
  -v "$JWT:/execution-auth.jwt:ro" \
  -p 127.0.0.1:8561:8561 -p 0.0.0.0:8961:8961 \
  "$SNOOPER_IMAGE" \
  ./json_rpc_snoop -b=0.0.0.0 -p=8561 http://execution:8551
fi

# ---- consensus: prysm beacon ---------------------------------------------------------
# Plain `[ x ] && arr+=(...)` returns non-zero on a non-supernode and, under `set -e`,
# would abort for every home staker.
BEACON_EXTRA=()
if [ "$SUPERNODE" = "True" ]; then BEACON_EXTRA+=(--subscribe-all-data-subnets); fi
if [ "$GOLDFISH" = "True" ];  then BEACON_EXTRA+=(--goldfish-vote-ledger); fi

if needs_start beacon "$PRYSM_UID"; then
run_with_ip6 "$BEACON_IP6" beacon \
  -d --name beacon --restart always --network shared -t \
  --user "$PRYSM_UID:$PRYSM_UID" \
  -e "VIRTUAL_HOST=bn-$FQDN" -e VIRTUAL_PORT=5052 -e "LETSENCRYPT_HOST=bn-$FQDN" \
  -v /data/prysm:/data:rw -v "$JWT:/execution-auth.jwt:ro" -v "$CFG:/network-config:ro" \
  -p 0.0.0.0:9000:9000/tcp -p 0.0.0.0:9000:9000/udp \
  -p 127.0.0.1:5052:5052 -p 127.0.0.1:5054:5054 -p 127.0.0.1:6061:6061 \
  --entrypoint /app/cmd/beacon-chain/beacon-chain "$PRYSM_IMAGE" \
  --accept-terms-of-use=true --datadir=/data \
  --p2p-host-ip="$IPV4" --p2p-tcp-port=9000 --p2p-udp-port=9000 \
  --rpc-host=0.0.0.0 --rpc-port=4000 \
  --jwt-secret=/execution-auth.jwt \
  --execution-endpoint=http://snooper-engine:8561 \
  --http-host=0.0.0.0 --http-port=5052 \
  --monitoring-host=0.0.0.0 --monitoring-port=5054 \
  --pprof --pprofport=6061 --pprofaddr=0.0.0.0 \
  --grpc-gateway-corsdomain='*' \
  --chain-config-file=/network-config/config.yaml \
  --genesis-state=/network-config/genesis.ssz \
  --contract-deployment-block=0 \
  --verbosity=INFO \
  "${BEACON_EXTRA[@]}" \
  --bootstrap-node="$CL_BOOTNODE_1" \
  --bootstrap-node="$CL_BOOTNODE_2"
fi

# ---- validator -----------------------------------------------------------------------
if needs_start validator "$PRYSM_UID"; then
run_with_ip6 "$VC_IP6" validator \
  -d --name validator --restart always --network shared -t \
  --user "$PRYSM_UID:$PRYSM_UID" \
  -v /data/prysm-validator:/validator-data:rw -v "$CFG:/network-config:ro" \
  --entrypoint /app/cmd/validator/validator "$PRYSM_VC_IMAGE" \
  --accept-terms-of-use=true \
  --datadir=/validator-data \
  --wallet-dir=/validator-data/wallet \
  --wallet-password-file=/validator-data/wallet_pass.txt \
  --beacon-rpc-provider=beacon:4000 \
  --suggested-fee-recipient="$FEE_RECIPIENT" \
  --monitoring-host=0.0.0.0 --monitoring-port=5054 \
  --chain-config-file=/network-config/config.yaml \
  --graffiti="$HOSTNAME_" \
  --enable-builder
fi

# ---- observability, only where the playbook already wrote the configs -----------------
if [ -n "$XATU_TOKEN" ]; then
  # Same config the xatu_sentry role templates, including the Gloas/Heze SSE topics
  # that the sentry's default subscription set leaves out.
  install -d -o xatu-sentry -g xatu-sentry -m 0777 /data/xatu-sentry
  cat > /data/xatu-sentry/config.yaml <<XATUEOF
logging: "info"
metricsAddr: ":9090"
name: "$NETWORK-$HOSTNAME_"
ntpServer: time.google.com
ethereum:
  beaconNodeAddress: http://beacon:5052
  overrideNetworkName: $NETWORK
  beaconSubscriptions:
    - attestation
    - single_attestation
    - block
    - block_gossip
    - chain_reorg
    - finalized_checkpoint
    - head
    - head_v2
    - voluntary_exit
    - contribution_and_proof
    - blob_sidecar
    - data_column_sidecar
    - execution_payload
    - execution_payload_gossip
    - execution_payload_available
    - execution_payload_bid
    - payload_attestation_message
    - proposer_preferences
outputs:
- name: grpc
  type: xatu
  config:
    address: $XATU_INGEST
    tls: True
    maxQueueSize: 100000
    workers: 5
    headers:
      authorization: "Basic $XATU_TOKEN"
XATUEOF
  chown xatu-sentry:xatu-sentry /data/xatu-sentry/config.yaml
  chmod 0640 /data/xatu-sentry/config.yaml
  if needs_start xatu-sentry "$XATU_UID"; then
    docker run -d --name xatu-sentry --restart always --network shared \
      --user "$XATU_UID:$XATU_UID" \
      -e SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
      -v /data/xatu-sentry/config.yaml:/config.yaml:ro \
      --entrypoint /xatu "$XATU_IMAGE" sentry --config=/config.yaml >/dev/null
  fi
else
  note "skip xatu-sentry: no xatu token passed"
fi

if [ -f /data/ethereum-metrics-exporter/ethereum-metrics-exporter.yaml ]; then
  if needs_start ethereum-metrics-exporter; then
    docker run -d --name ethereum-metrics-exporter --restart always --network shared \
      --user root \
      -e SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
      -v /data/ethereum-metrics-exporter/:/config:ro \
      -v /var/run/docker.sock:/var/run/docker.sock:ro \
      -v /data:/data:ro \
      --entrypoint /ethereum-metrics-exporter "$METRICS_IMAGE" \
      --metrics-port=9090 --config=/config/ethereum-metrics-exporter.yaml >/dev/null
  fi
else
  note "skip ethereum-metrics-exporter: config not templated yet"
fi

sleep 3
CHECK=(execution snooper-engine beacon validator)
if [ -n "$XATU_TOKEN" ]; then CHECK+=(xatu-sentry); fi
for c in "${CHECK[@]}"; do
  s="$(docker inspect -f '{{.State.Status}}' "$c" 2>/dev/null || echo missing)"
  [ "$s" = running ] || fail "$c is '$s', not running"
done
note "OK ${CHECK[*]} running (supernode=$SUPERNODE goldfish=$GOLDFISH chain=$CHAIN_ID)"
