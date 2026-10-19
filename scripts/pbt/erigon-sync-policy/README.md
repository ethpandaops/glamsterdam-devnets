# Bounded Erigon preparation sync policy

This helper uses the same `mdbx-go v0.43.0` dependency as the pinned Erigon
v3.7.1 image. It configures shared autosync thresholds on a database whose live
owner already selected `MDBX_SAFE_NOSYNC`. It does not enable that mode or write
execution keys. It rejects durable mode, standalone `NOMETASYNC`,
`UTTERLY_NOSYNC`, missing databases and thresholds beyond 10 seconds / 256 MiB.
Before opening MDBX, it requires an explicit live owner PID, the same PID
namespace, and an owner file descriptor for the exact database inode.

MDBX's safe delayed-flush mode preserves a previous durable transaction so a
crash can roll back recent work without corrupting that checkpoint. The immutable
replay records permit replaying the lost prefix. This is a preparation tradeoff;
normal durability remains the final snapshot profile.

The helper forces an initial sync, sets both thresholds and reads them back.
The period is evaluated on commits/sync calls, not by a background timer; an
idle database still needs an explicit sync or clean close. MDBX shares these
settings across processes until the last handle closes, so they must be
configured again after each client restart. Native clock conversion can round
the period down by less than 100 microseconds; a longer period is rejected.

```bash
bash scripts/pbt/erigon-sync-policy/build.sh /path/to/erigon-sync-policy
docker cp /path/to/erigon-sync-policy CONTAINER:/tmp/pbt-erigon-sync-policy
docker exec --user 0:0 CONTAINER /tmp/pbt-erigon-sync-policy \
  --db /data/chaindata --owner-pid 1
```

Run the helper inside the database owner's container. The static build avoids
requiring the controller's newer glibc in the pinned Debian client image.
`--verify-owner-only` checks namespace and inode without opening MDBX.

The build runs cross-process native tests with `SAFE_NOSYNC|WRITEMAP`, proving
that the owning process sees the new thresholds. Tests also cover mode rejection
without changing thresholds and refusal to create missing databases. The build
manifest records dependency/build information and binary/source SHA-256 hashes.

[`probe-erigon-sync-policy.py`](../probe-erigon-sync-policy.py) runs a one-time
128-block pilot, restoring normal pruning and keeping background maintenance
disabled. Every block must return VALID with the expected commitments, and every
body/BAL must match the replay record. The first eight blocks are warmup; the
reported rate for the remaining 120 includes body verification. Afterward, a
clean stop and reopen without `MDBX_NO_FSYNC` must preserve the exact head and
sampled BALs. Only then does normal-durability replay resume. The pilot itself
does not adopt delayed flushing for the remaining run.

The initial host-run production attempt aborted in `mdbx_env_sync_ex` before
replaying any pilot blocks. Normal-durability recovery preserved the head and
sampled BALs. A disposable test with committed dirty data and a held writer
transaction reproduced a futex failure across PID namespaces; running inside
the owner's container waited for the writer and succeeded. The guarded build
rejected the host invocation before opening MDBX and passed the in-container
test, including owner threshold readback and exit code 0. This is scratch-test
evidence, not proof that a production pilot has passed.

The revised pilot uses separate `sync-policy-v2-*` evidence and backup names,
requires the guarded fixture proof for the exact binary, and verifies owner
identity before pausing production. It still requires its full 128-block and
normal-durability restart gates before reporting success.

Evidence is saved under `/data/pbt-1/pipeline/sync-policy-*.json`. Failures stop
progress for inspection; the script does not automatically retry database work.
