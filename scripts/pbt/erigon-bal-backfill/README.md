# Native Erigon BAL sidecar backfill

Erigon v3.7.1 prunes stored BAL sidecars behind its finalized head and regenerates
them from historical execution state when requested. During PBT-1, retrieving
16 older qualifying BALs took 20.10 seconds. Repeating execution for every BAL
would make the final exhaustive audit much slower than reading retained sidecars.

This utility restores the exact sidecars already supplied and validated during
Engine replay, using the pinned client's `rawdb.WriteBlockAccessListBytes` API.
Each input must match the native canonical block hash, state root and BAL hash.
It validates the entire input range before writing, refuses conflicting native
sidecars, detects changed input files, and writes only missing BAL sidecars in
bounded durable transactions. The native head and state root must remain unchanged.
Repeated runs are idempotent. The final API audit remains mandatory.

Input decoding uses eight workers and retains at most 128 decoded records.
Canonical checks and MDBX access stay serial and ordered. The write pass creates
a fresh decoder and re-reads the records before comparing their preflight
digests; cached decoded input cannot hide a change between passes.

Build from an untouched checkout of Erigon commit
`8c1e3893d77d230720d172f1492d95b5777a862c` (v3.7.1):

```bash
bash scripts/pbt/erigon-bal-backfill/build.sh /path/to/erigon-v3.7.1 /path/to/erigon-bal-backfill
```

The build runs native MDBX tests under Go's race detector for corruption/conflict
rejection, canonical identity, dry runs, idempotence and persistence across an
exclusive native reopen. Tests also cover corruption beyond the first 128-record
batch, input mutation between preflight and writes, and ordered parallel decoding.
It produces the binary and a `.json` manifest with its SHA-256, dependency/build
information and source digests. The Erigon checkout is left unchanged.

A `--dry-run` opens the database read-only and may verify an older prefix while
the client is live. A write requires an exclusive database open, a final block
equal to the native head, and a stopped node. `retain-erigon-bals.py` additionally
checks container state, database mounts, the build digest, the final workload
count and the prior head/state audit before invoking the writer.

```bash
GOMEMLIMIT=4GiB ./erigon-bal-backfill \
  --db /data/pbt-1/erigon/chaindata \
  --records /data/pbt-1/pipeline/blocks \
  --start 24452539 --end 24503958 \
  --report /data/pbt-1/pipeline/erigon-bal-backfill.json
```

For PBT-1, `reopen.py` invokes the wrapper after the first final clean shutdown.
The wrapper restores the sidecars and creates the same pinned container profile
with `--exec.no-prune=true`; the stopped original container is retained. The
restart then verifies every BAL/body through the Engine API and stops cleanly
again before export. The benchmark snapshot's startup profile must retain this
flag to prevent immediate sidecar pruning. This is an isolated benchmark profile;
the flag also disables other database pruning and is not a production default.

In the pinned source, `PruneExecutionStage` checks `dbg.NoPrune()` before
pruning the BAL table. `SnapshotsPrune` also checks it before
`PruneAncientBlocks`, which otherwise deletes sidecars together with frozen
block bodies. The other native sidecar-deletion paths remove or truncate the
blocks themselves; they are not normal restart housekeeping. The final API
audit still checks actual retention rather than relying on these source guards.

Publication includes `_snapshot_bal_backfill.json` and
`_snapshot_bal_backfill_build.json`, alongside the exhaustive restart/API proof.
The report clearly identifies restoration from validated replay inputs.
