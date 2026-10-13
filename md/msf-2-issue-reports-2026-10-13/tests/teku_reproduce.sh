#!/usr/bin/env bash
set -euo pipefail
# Run from an extracted evidence ZIP; requires Docker and a JDK 25 compiler.
case_root=$(cd "${1:-.}" && pwd)
teku_image=${TEKU_REPRO_IMAGE:-consensys/teku:26.10.0}
task_javac=${TEKU_REPRO_JAVAC:-javac}
test_dir=$(mktemp -d /tmp/msf2-teku-record.XXXXXX)
test_container="msf2-teku-record-jars-$$"
trap 'docker rm -f "$test_container" >/dev/null 2>&1 || true; rm -rf "$test_dir"' EXIT
docker create --name "$test_container" --network none --entrypoint /bin/true "$teku_image" >/dev/null
docker cp "$test_container:/opt/teku/lib" "$test_dir/lib"
docker rm "$test_container" >/dev/null
cp "$case_root/tests/CheckStoredRecord.java" "$test_dir/"
cp "$case_root/network/config.yaml" "$test_dir/config.yaml"
cp "$case_root/follow-up-evidence/teku-slot2559-stored-block.ssz" "$test_dir/block.ssz"
cp "$case_root/follow-up-evidence/teku-slot2559-stored-envelope.ssz" "$test_dir/stored.ssz"
cp "$case_root/follow-up-evidence/teku-slot2559-canonical-envelope.ssz" "$test_dir/canonical.ssz"
"$task_javac" -cp "$test_dir/lib/*" -d "$test_dir" "$test_dir/CheckStoredRecord.java"
docker run --rm --network none --memory 4g --cpus 2 --entrypoint java \
  --hostname msf2-record-test --add-host msf2-record-test:127.0.0.1 \
  --user "$(id -u):$(id -g)" -v "$test_dir:/case:ro" "$teku_image" \
  --class-path '/case:/opt/teku/lib/*' CheckStoredRecord \
  /case/config.yaml /case/block.ssz /case/stored.ssz /case/canonical.ssz
