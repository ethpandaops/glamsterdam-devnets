# PBT-1 self-conversion trials — task sheet (2026-10-26)

Two implementation requests arrived for the **self-conversion** path, i.e. building the
partitioned binary trie from a node's own flat state instead of loading the shared
EIP-8347 snapshot. Each trial consumes one of the nine workers; the other eight stay
canonical and act as the state-root oracle. Both were requested as "as soon as possible"
against a running network with a fixed `S = 1793264400` (2026-10-29 09:00 UTC), so run
them **sequentially, one worker at a time**, and do not let either trial reach `S`.

Common constants: anchor `N = 24453558`,
hash `0x331c54fd1b37302697157dec30d2a1e0a13682843301f60d8ebac004f8bc4155`,
preimage file already delivered to every worker at
`/data/pbt-1/migration-input-24453558/framed.bin` (66.85 GB, mounted read/write as
`/pbt-migration-input`), snapshot `pbt-snapshot.bin` (107.9 GB) **not needed by either
trial**.

---

## TODO A — Besu-1: self-conversion from the node's own flat database

### Goal
Exercise the new `--Xpbt-migration-self-convert` mode, which builds the binary column from
the node's own flat DB, the anchor preimages and the BALs of the blocks after the anchor.
Secondary goal: obtain an **independent state-root check**, because this mode has no
built-in root comparison (the snapshot path gets one for free by verifying the snapshot
against the anchor's MPT root).

### Pins (verified to exist)
| component | pin | note |
|---|---|---|
| besu | `cc5642583b802f8af31c58386d13429fd098d5e5` | commit: *"Build the PBT from the node's own flat database"*; adds `selfconvert/{SelfConversion,FlatState,BalPreimages,StateLeaves,CodeLeaves,RangeScan,TargetPriors}` |
| besu-stateless | `e49e3008ef35a6127850b66d01ada4da46adff88` | single-chunk BLAKE3 hashing of PBT keys/nodes |

Flag surface at that commit is unchanged from the current deployment
(`--Xpbt-migration-threads`, `-blocks-per-roll`, `-sort-buffer`, `-roll-pause`,
`-snapshot-anchor-block-hash`, `--Xpbt-preimages-file`, `--Xpbt-snapshot-file`,
`--Xpbt-migration-from-genesis`) plus `--Xpbt-migration-self-convert`. The option parser
rejects `--Xpbt-migration-self-convert` together with `--Xpbt-snapshot-file`, and allows
exactly one migration source.

### Build steps
Reuse the reviewed local recipe (`scripts/pbt/build-pinned-besu.py`) with the pins
updated — it builds in an `eclipse-temurin:25-jdk` container with an isolated Maven cache,
`test publishToMavenLocal` for the library, `installDist -x test` for Besu, then asserts
that the resolved `*stateless*.jar` SHA-256 matches the locally published artifact.
1. Check out both repos at the pins under `/data/pbt-1/migration-builds/` on a build host.
2. Run the library publish + Besu distribution build; record the resolved stateless JAR SHA-256.
3. Build the runtime image, tag `pbt-1/besu:cc564258-e49e3008`, save + load onto Besu-1.
4. Pin the loaded **image ID** in `ansible/inventories/pbt-1/host_vars/lighthouse-besu-1.yaml`
   (`besu_container_image`), as done for the current `39377a26-62b75234` pair.

### Flags for the migration restart
```
--Xpbt-migration-self-convert=true
--Xpbt-preimages-file=/pbt-migration-input/framed.bin
--Xpbt-snapshot-anchor-block-hash=0x331c54fd1b37302697157dec30d2a1e0a13682843301f60d8ebac004f8bc4155
--Xpbt-migration-threads=4 --Xpbt-migration-blocks-per-roll=128
--Xpbt-migration-sort-buffer=64 --Xpbt-migration-roll-pause=2000
# no --Xpbt-snapshot-file
```
The requested path `/data/pbt/preimages.bin` does not exist on these workers; the delivered
preimage artifact is `framed.bin` above.

### Inventory work required
`ansible/inventories/pbt-1/group_vars/besu.yaml` currently hardcodes `--Xpbt-snapshot-file`
in `pbt_besu_migration_args`. Branch it the way the Geth role already does
(`pbt_geth_migration_args` keys off `pbt_migration_role == 'import'`): when
`pbt_migration_role == 'self'`, emit `--Xpbt-migration-self-convert=true` and omit the
snapshot flag, keeping preimages + anchor hash + tuning flags. Then set
`pbt_migration_role: self` on Besu-1 only.

### Data prerequisite — found during preparation, resolve before starting
`SelfConversion.Collect` reads `chain.bals(blocks)` for every block from `anchor+1` to the
conversion target in 128-block batches, and that interface **throws if a BAL is missing**.
BALs are served from local block storage (`DefaultBlockchain.getBlockAccessList` →
`blockchainStorage`), not fetched from peers (unlike the Geth self-converter).

Consequences:
- **A truly empty "sync from scratch" does not work** with the artifacts we hold: a Besu
  snap sync keeps neither the 76k blocks' BALs between `N = 24453558` and today's head, nor
  history to regenerate them, so the conversion aborts on the first missing BAL.
- The workable shape is the reset we already know how to do: wipe the datadir, re-restore
  `/mnt/pbt-recovery/besu-24503958.tar.zst` (state at `N`), let the node execute
  `N+1 … head` itself — that execution is what materialises the BALs — then arm
  self-convert with the target at the then-current finalized head.
- The anchor cannot be moved to the genesis block or to head: `framed.bin` holds preimages
  for `N` only.

If a genuine from-scratch sync is still wanted for a peak-disk measurement, treat it as a
separate experiment: it needs a preimage file generated at the block the sync starts from.

### Disk / memory pre-check (measured 2026-10-26)
- `/` on Besu-1: 2.4 TB, 1.7 TB used, **602 GB free**; `/mnt/pbt-recovery` 1.1 TB (98 %,
  holds `besu-24503958.tar.zst`).
- `/data/pbt-1` 1.6 TB, of which `migration-input-24453558` 170 GB: **delete
  `pbt-snapshot.bin` (−108 GB), keep `framed.bin`**. After the datadir wipe ≈ 1.9 TB free,
  restore + re-execution ≈ 1.4 TB → feasible but tight; re-check `df` immediately before.
- Trial budget: Besu-1 runs 16 GiB / 8 GiB heap today. A restore plus a full range scan and
  sort is the heaviest thing this worker has done; allocate 32 GiB / 24 GiB heap for the
  trial (the host has 128 GiB) unless a deliberate 16 GiB run is wanted.

### Verification (this is the deliverable, not the conversion itself)
The conversion prints the PBT root it wrote but nothing compares it. Use the fleet:
1. At ≥3 consecutive common block hashes, compare Besu-1's `stateRoot` from
   `eth_getBlockByNumber` against the other eight workers (MPT root must match).
2. Compare the binary root: `debug_migrationProgress` `Binary.ShadowRoot` on Besu-1 vs
   `debug_shadowStateRoot(blockHash)` on Geth/Besu-2/Nethermind and the Erigon
   `[commitment] … mode=bin-patricia-hashed rootHash=` log line at the same block.
3. Restart Besu-1 and repeat (1) and (2) — a converted-but-wrong root usually only shows
   after the follower re-reads the column.
4. Record: conversion start/end, target block, leaf count, codes count, peak RSS, peak
   disk, BAL batches consumed, and every root compared.

### Rollback
Re-extract the `N` archive, restore the previous `besu_container_image` pin and
`pbt_migration_role: import`, redeploy. The current snapshot-import state is reproducible
from the archive plus the delivered artifacts.

---

## TODO B — Nethermind-1: preimages-only import on the new branch

### Goal
Re-run the Nethermind migration **without** `--Pbt.MigrationSnapshotPath`, so the binary
state is imported from the node's own persisted flat state, with keys resolved through the
preimages and, for keys created after the anchor, through the BALs since the anchor. The
branch is also expected to carry a reworked flat implementation that cuts allocations —
measure that, since this worker is the one with a history of heap trouble (28 container
restarts to date).

### Pin
`NethermindEth/nethermind` @ `merge-ten-lights-cover` =
`3f29bb53ab55297f0f0bb5466e314c84f30fc344`. At that commit `IPbtConfig` documents exactly
this mode: with `MigrationSnapshotPath` absent, "the PBT state is imported from this node's
own persisted hash-keyed flat state, whose keys are resolved through the preimages and, for
the keys written after the anchor, through the BALs of the blocks since".

### Build steps (image builder)
```sh
panda build nethermind \
  --repo NethermindEth/nethermind \
  --ref merge-ten-lights-cover \
  --tag pbt-1-merge-ten-lights-cover \
  --wait
panda build status <run-id>            # if not waiting
```
This dispatches `build-push-nethermind.yml` in the image-builder repo. Then:
1. Verify the image label records commit `3f29bb53…`, not just the branch name.
2. Resolve the digest (`docker manifest inspect ethpandaops/nethermind:pbt-1-merge-ten-lights-cover`)
   and pin it in `ansible/inventories/pbt-1/group_vars/all/images.yaml` **and** in
   `host_vars/lighthouse-nethermind-1.yaml` (`nethermind_container_image`), which currently
   pins a digest directly and would otherwise mask the fleet-wide default.
3. Keep the other worker on the current image — the trial is single-worker.

### Flags
```
--Pbt.Enabled=true --FlatDb.Enabled=true --FlatDb.Layout=Flat --FlatDb.HistoryEnabled=false
--Pbt.MigrationAnchor=24453558
--Pbt.MigrationPreimagesPath=/pbt-migration-input/framed.bin
# no --Pbt.MigrationSnapshotPath
```
Note this worker currently runs with `pbt_nethermind_migration_preimages: false`; the trial
needs the opposite (preimages present, snapshot absent).

### Inventory work required
`group_vars/nethermind.yaml` has a toggle that can only drop the preimages. Add the mirror
image — e.g. `pbt_nethermind_migration_snapshot` (default `true`) that removes
`--Pbt.MigrationSnapshotPath=` — and set it `false` on Nethermind-1 for the trial.

### Data prerequisite
The existing PBT column was built from the snapshot, and a populated PBT database seeded
from another anchor is rejected by the configuration validator, so the migration namespace
has to go: wipe `/data/pbt-1/nethermind`, re-extract
`/mnt/pbt-recovery/nethermind-24503958.tar.zst`, let the node re-execute `N+1 … head`
(this creates the BALs the import consumes), then restart with the flags above.
Disk check (2026-10-26): `/` 2.4 TB, 1.8 TB used, **426 GB free**; DB 1.6 TB; archive
1.01 TB on `/mnt` (98 % used, 28 GB free); `migration-input` 163 GB (delete
`pbt-snapshot.bin`, keep `framed.bin`). Extract + DB peak needs the DB space freed first.

### Measurement plan
Same restore, same flags, current image vs branch image, one worker at a time:
peak RSS and container memory, GC/alloc counters if exposed, import duration, peak disk,
and whether the "Pbt compaction/persistence is not keeping up …" stall messages
(the earlier symptom) still appear. Record the `PBT verify preimages` gate result.

### Verification
Same fleet comparison as TODO A (MPT `stateRoot` and binary shadow root at identical block
hashes, before and after a restart), plus the Nethermind-specific `PBT verify preimages`
step in the logs.

### Rollback
Re-extract the archive, restore the previous image digest and
`pbt_nethermind_migration_snapshot: true`.

---

## Shared pre-flight, sequencing and acceptance

**Before each trial**
- [ ] Finality advancing, no other worker mid-restart, `S` still ahead of the expected end.
- [ ] Only one worker degraded at a time; the fleet keeps eight workers and > 2/3 stake.
- [ ] Disk pre-check executed, superseded artifacts deleted (both `pbt-snapshot.bin` copies).
- [ ] New image digest/ID recorded and verified against the intended commit.
- [ ] Inventory change reviewed before the restart, so the deployed args are auditable.

**Acceptance for both**
- MPT `stateRoot` and binary root agree with the fleet at ≥3 consecutive common blocks,
  before and after a restart.
- Worker rejoins with peers, same head, engine API healthy; no state-root mismatch in logs.
- Trial image stays on that single worker; the other eight keep the current images.
- Numbers recorded: conversion duration, target block, peak RSS, peak disk, BAL batches,
  leaf/code counts, every compared root.

**Deliberately out of scope** — the EIP text describing the migration steps is a separate
documentation task, and neither trial blocks `S`; if a trial is still running near
`S − 12 h`, abort it, roll back, and return the worker to the canonical configuration.

## Open questions to close before the runs
1. Besu: does the converter accept an anchor older than the point the restored DB starts
   re-executing, i.e. is re-execution from `N` sufficient for the `N+1 … target` BALs, or
   must the DB hold blocks from before `N` as well?
2. Besu: memory needed for the range scan + sort on a 1.4 TB flat DB (proxy: 32 GiB/24 GiB
   heap, confirm against the branch's benchmark notes).
3. Nethermind: whether the preimage-flat layout requirement that `MigrationExportPath`
   documents also constrains this import path (the config text says import resolves through
   the preimages, but the branch should be confirmed once on a throwaway DB).
4. Whether either trial should stop short of `S` on purpose (i.e. do we want a worker that
   converts and then crosses `S` in self-conversion mode, or only a pre-`S` root check?).
