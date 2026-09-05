#!/usr/bin/env bash
# 1/4  Dump logs from every running eth container to /data/logstore/<devnet>/<container>.log
# Run BEFORE the wipe: `docker rm` discards the log.
#   ansible 'all:!localhost' -b -f 400 -m script -a "../scripts/devnet10-1-dump-logs.sh devnet-10"
set -euo pipefail
DEVNET="${1:-devnet-10}"
DIR="/data/logstore/$DEVNET"
H=$(hostname)
mkdir -p "$DIR"
n=0
for c in execution beacon validator snooper-engine snooper-rpc xatu-sentry buildoor bootnodoor; do
  docker inspect "$c" >/dev/null 2>&1 || continue
  # both streams; || true so a container dying mid-dump does not abort the run
  docker logs "$c" > "$DIR/$c.log" 2>&1 || true
  n=$((n+1))
done
echo "[$H] dumped $n logs -> $DIR ($(du -sh "$DIR" 2>/dev/null | cut -f1)), free: $(df -h /data | awk 'NR==2{print $4}')"
