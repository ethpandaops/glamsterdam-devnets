#!/usr/bin/env bash
# Recreate the validator container with --decoupled-ffg-vote-at-slot-start added.
#
# Touches ONLY the validator: beacon and execution are left running. Every other setting
# is read back off the live container (image, user, tty, restart policy, binds, network,
# static IPv6, entrypoint and the full existing argv), so nothing is reconstructed from
# assumptions and per-host values like --graffiti survive untouched.
#
# Idempotent: a validator that already carries the flag is left alone.
#
#   ansible ethereum_node -b -f 400 -m script -a ../scripts/devnet10-restart-vc.sh
#
# Optional arg 1: the flag to add (default --decoupled-ffg-vote-at-slot-start), so the
# same script can apply the other decoupled-research flags later, e.g.
#   -a "../scripts/devnet10-restart-vc.sh --decoupled-ffg-head-source=head-at-round-start"

set -euo pipefail

FLAG="${1:---decoupled-ffg-vote-at-slot-start}"
NAME=validator
H=$(hostname)

note() { echo "[$H] $*"; }
fail() { echo "[$H] FATAL: $*" >&2; exit 1; }

st=$(docker inspect -f '{{.State.Status}}' "$NAME" 2>/dev/null || echo missing)
[ "$st" = missing ] && { note "no $NAME container (bootnode/buildoor?), nothing to do"; exit 0; }

# Read the live container back rather than rebuilding from assumptions.
mapfile -t CMD  < <(docker inspect -f '{{range .Config.Cmd}}{{println .}}{{end}}'        "$NAME")
mapfile -t ENTR < <(docker inspect -f '{{range .Config.Entrypoint}}{{println .}}{{end}}' "$NAME")
mapfile -t BIND < <(docker inspect -f '{{range .HostConfig.Binds}}{{println .}}{{end}}'  "$NAME")
IMAGE=$(docker inspect -f '{{.Config.Image}}'              "$NAME")
USERSPEC=$(docker inspect -f '{{.Config.User}}'            "$NAME")
TTY=$(docker inspect -f '{{.Config.Tty}}'                  "$NAME")
RESTART=$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "$NAME")
NET=$(docker inspect -f '{{.HostConfig.NetworkMode}}'      "$NAME")
IP6=$(docker inspect -f '{{with index .NetworkSettings.Networks "shared"}}{{.GlobalIPv6Address}}{{end}}' "$NAME" 2>/dev/null || true)

[ -n "$IMAGE" ] || fail "could not read image from $NAME"

# `docker inspect -f` adds a trailing newline on top of {{println}}, so mapfile yields a
# final empty element. Passing that through becomes an empty argv entry and prysm exits
# with "unrecognized argument:". Strip empties, and drop any pre-existing copy of the
# flag so a rebuild cannot accumulate duplicates.
CLEAN=()
for a in "${CMD[@]}"; do
  [ -n "$a" ] || continue
  case "$a" in "${FLAG%%=*}"|"${FLAG%%=*}"=*) continue ;; esac
  CLEAN+=("$a")
done
CMD=("${CLEAN[@]}")
[ "${#CMD[@]}" -gt 0 ] || fail "could not read argv from $NAME"

# Only a HEALTHY container carrying the flag is left alone. A crash-looping one is
# rebuilt even though its argv already contains the flag.
if [ "$st" = running ]; then
  if docker inspect -f '{{range .Config.Cmd}}{{println .}}{{end}}' "$NAME" | grep -qx -- "${FLAG%%=*}"; then
    note "$NAME already running with ${FLAG%%=*}, left untouched"; exit 0
  fi
fi

# if-blocks, not `[ x ] && arr+=(...)`: that returns non-zero when the test fails and
# under `set -e` aborts the script (e.g. a validator with no static IPv6).
ARGS=(-d --name "$NAME" --restart "${RESTART:-always}" --network "${NET:-shared}")
if [ -n "$USERSPEC" ]; then ARGS+=(--user "$USERSPEC"); fi
if [ "$TTY" = true ];  then ARGS+=(-t); fi
if [ -n "$IP6" ];      then ARGS+=(--ip6 "$IP6"); fi
for b in "${BIND[@]}"; do if [ -n "$b" ]; then ARGS+=(-v "$b"); fi; done
if [ "${#ENTR[@]}" -gt 0 ] && [ -n "${ENTR[0]}" ]; then ARGS+=(--entrypoint "${ENTR[0]}"); fi

docker rm -f "$NAME" >/dev/null 2>&1 || true
if ! docker run "${ARGS[@]}" "$IMAGE" "${CMD[@]}" "$FLAG" >/dev/null 2>&1; then
  # A static IPv6 can be refused if the address was not released yet; retry without it
  # rather than leaving the validator down.
  note "warn: run with --ip6 $IP6 failed, retrying without a static IPv6"
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  PRUNED=(); for a in "${ARGS[@]}"; do [ "$a" = "--ip6" ] && skip=1 && continue
    [ "${skip:-0}" = 1 ] && skip=0 && continue; PRUNED+=("$a"); done
  docker run "${PRUNED[@]}" "$IMAGE" "${CMD[@]}" "$FLAG" >/dev/null \
    || fail "could not start $NAME"
fi

sleep 2
s=$(docker inspect -f '{{.State.Status}}' "$NAME" 2>/dev/null || echo missing)
[ "$s" = running ] || fail "$NAME is '$s' after restart"
note "OK $NAME restarted with $FLAG (user=${USERSPEC:-root} ipv6=${IP6:-none})"
