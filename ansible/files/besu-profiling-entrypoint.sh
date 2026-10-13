#!/bin/sh
set -eu
umask 077
profile_root=${BESU_PROFILING_DIR:-/profiling}
run_id=$(date -u +%Y%m%dT%H%M%SZ)-$(cat /proc/sys/kernel/random/uuid)
run_dir="$profile_root/runs/$run_id"
mkdir -p "$run_dir/repository" "$run_dir/checkpoints"
printf '%s\n' "$run_id" > "$profile_root/active-run.tmp"
mv "$profile_root/active-run.tmp" "$profile_root/active-run"
export BESU_OPTS="${BESU_OPTS:-} -XX:HeapDumpPath=$run_dir/heap.hprof -XX:FlightRecorderOptions=repository=$run_dir/repository -XX:StartFlightRecording=name=besu,settings=default,disk=true,maxage=30m,maxsize=256m,dumponexit=true,filename=$run_dir/exit.jfr -Xlog:gc*,safepoint:file=$run_dir/gc-%p-%t.log:time,uptime,level,tags:filecount=10,filesize=50M"
printf 'Besu profiling run: %s\n' "$run_id"
exec /opt/besu/bin/besu "$@"
