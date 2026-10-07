#!/usr/bin/env bash
# Firewall the ethrex hosts' EL p2p port (30303 tcp/udp, IPv4 + IPv6) to the shadowfork's own
# droplets. Until amsterdamTime, real-network peers have a compatible fork ID and answer header and
# state requests with the real chain, which derails ethrex's snap sync onto the wrong state
# (seen on sepsf-1). Docker-published ports bypass INPUT, so the rules go in the DOCKER-USER chain.
# Idempotent: re-running rebuilds the chain from the current inventory.
#
# Usage: scripts/shadowfork-ethrex-firewall.sh <inventory dir, e.g. sepsf-2> [--remove]
# Hosts: FW_HOSTS (ansible pattern, default "ethrex:nimbusel" - every EL that snap-syncs;
# msf-1 uses 'ethereum_node:bootnode'). Matches --dport and --sport 30303, so our own
# discovery/dials from the p2p socket are filtered too, plus everything leaving the EL container's
# IP: its TCP dials use ephemeral source ports and real peers listen on other ports too (msf-1
# dialed mainnet nodes on 30304/30404). Re-run after an EL container is recreated (its IP can
# change). Rules do not survive a reboot.
# Needs docker on the hosts (run right after `playbook.yaml -t init-server`).
set -euo pipefail

net="${1:?usage: $0 <inventory dir, e.g. sepsf-2> [--remove]}"
root="$(cd "$(dirname "$0")/.." && pwd)"
inv="$root/ansible/inventories/$net/inventory.ini"
[ -f "$inv" ] || { echo "error: $inv not found (run terraform apply first)" >&2; exit 1; }
chain="SF-P2P"

script="$(mktemp)"; trap 'rm -f "$script"' EXIT
{
  echo '#!/bin/sh'
  echo 'set -e'
  echo "C=$chain"
  # remove existing jumps + chain (both families)
  echo 'for t in iptables ip6tables; do $t -S DOCKER-USER | grep -- "-j $C\$" | sed "s/^-A/-D/" | while read -r r; do $t $r; done; $t -F $C 2>/dev/null || true; $t -X $C 2>/dev/null || true; done'
  if [ "${2:-}" = "--remove" ]; then
    echo 'echo removed'
  else
    echo 'for t in iptables ip6tables; do $t -N $C; done'
    grep -oE "ansible_host=[0-9.]+" "$inv" | cut -d= -f2 | sort -u | while read -r ip; do
      echo "iptables -A \$C -s $ip -j RETURN"
      # ethrex's own dials and discv4 pings leave the container from its bridge IP, so match the
      # destination too: outbound to our droplets passes, to anything else on 30303 is dropped.
      echo "iptables -A \$C -d $ip -j RETURN"
    done
    # the EL's traffic to its own containers (snooper, nginx) and the VPC
    echo 'for n in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 127.0.0.0/8; do iptables -A $C -d $n -j RETURN; done'
    echo 'iptables -A $C -j DROP'
    echo 'ip6tables -A $C -j DROP'
    echo 'for t in iptables ip6tables; do for p in tcp udp; do for d in --dport --sport; do $t -I DOCKER-USER 1 -p $p $d 30303 -j $C; done; done; done'
    echo 'el=$(docker inspect execution --format "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}" 2>/dev/null | cut -d" " -f1)'
    echo '[ -z "$el" ] || iptables -I DOCKER-USER 1 -s "$el" -j $C'
    echo 'echo "allowed=$(iptables -S $C | grep -c -- "-s .* RETURN") docker-user-jumps=$(iptables -S DOCKER-USER | grep -c $C)+$(ip6tables -S DOCKER-USER | grep -c $C) el=${el:-none}"'
  fi
} > "$script"

cd "$root/ansible"
# One line per host; hosts that failed or were unreachable are listed as such.
ansible -i "$inv" "${FW_HOSTS:-ethrex:nimbusel}" -b -o -m script -a "$script" 2>/dev/null \
  | sed -nE 's/^([^ ]+) \| [A-Z]+ .*(allowed=[0-9]+ docker-user-jumps=[0-9]+\+[0-9]+ el=[0-9a-z.]+|removed).*/\1 \2/p; t; s/^([^ ]+) \| (FAILED|UNREACHABLE).*/\1 \2/p' | sort
