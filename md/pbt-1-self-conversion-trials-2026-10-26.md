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

## Built artifacts (2026-10-26) — done, not deployed

Both trial images exist and are staged. Neither is referenced by any inventory file yet,
so no worker's configuration changed: Besu-1 still runs `sha256:850c5bae…` and
Nethermind-1 still runs `sha256:9ceb3fa7…`.

| artifact | identity | verification |
|---|---|---|
| Besu self-convert image | tag `pbt-1/besu:cc564258-e49e3008`; build host ID `sha256:033612e5cadc421965a46a9a654145cef9df9f9cc0c4e0dabcd75d16ef4aeff8`; loaded on Besu-1 as `sha256:d8013fb001d2241f99c4c816076624c41a7e86e9e1ffa3f84b3b4f746360f83a`; 985 MB | labels `org.opencontainers.image.revision=cc564258…`, `pbt.stateless.revision=e49e3008…`; `besu --version` → `besu/v26.10-develop-cc56425/linux-x86_64/openjdk-java-25`; `sha256sum /opt/besu/lib/besu-stateless-0.1.8-SNAPSHOT.jar` inside the image = `d182e1e86d8ae6ce48e3bcb34f58a3bffc4e579c8e6885ed103d2a9e7a4bae1e`, identical to the JAR published to the isolated Maven cache during the build |
| Nethermind trial image | tag `ethpandaops/nethermind:pbt-1-merge-ten-lights-cover`; registry index digest `sha256:4428e138c00da790860a0dc85e02ac04dbf70b0211ee5e90db2dfbe952c0397b` (pin this one in the inventory — it is multi-arch, matching how the current Nethermind pin is written); amd64 platform manifest `sha256:b464feb8d4e01b6f0b76202e3c8dc3e5262e9974db0da4ba053cf748dc145e56` (665 MB, created 2026-10-26T20:20:54Z), pulled onto Nethermind-1 as `sha256:db64a1985cabf5512a934a264ba3779b5db953d2a7e832828c048ebf0ac46d96` | CI run `40394147124` concluded success; image labels `org.opencontainers.image.revision=3f29bb53ab55297f0f0bb5466e314c84f30fc344`, `ethpandaops.io.commitRef=merge-ten-lights-cover`, `ethpandaops.io.repo=NethermindEth/nethermind`; `--help` from the image lists `--Pbt.MigrationPreimagesPath` whose help text is exactly the preimages-only mode, so no extra self-import flag is needed |

Both images were produced without touching a running node beyond the build host's CPU: the
Besu build ran in a containerified Gradle invocation (8 CPU / 16 GiB) alongside the live
Besu-2 worker, which stayed synced and peering throughout (`Binary.synced`, cursor at head).

The two local Besu image IDs differ because the build loads an attestation manifest list;
identity is carried by the revision labels and the resolved stateless JAR hash, both
checked on the target host after the load.

Flag-surface notes taken from the built images (not from source):
- Nethermind: the import mode is selected purely by omitting `--Pbt.MigrationSnapshotPath`
  and keeping `--Pbt.MigrationPreimagesPath` + `--Pbt.MigrationAnchor`. The image also
  exposes `--Pbt.FakeMatchingStateRoot`, which reports the child header's root instead of the
  computed PBT root and therefore bypasses the very check these trials exist to obtain —
  it must stay `false` in both trials.
- Besu: `--Xpbt-migration-self-convert` is mutually exclusive with `--Xpbt-snapshot-file`
  (the option parser rejects the pair), so the inventory branch must remove the snapshot
  flag rather than add the new one alongside it.

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
> **Correction (2026-10-27, read at cc564258):** `Chain.bals` is backed by
> `PbtMigrator.storedOrFetchedBals`, which fetches the BALs missing from local storage from
> peers before it throws, so a missing local BAL is not fatal by itself. The target is the
> latest finalized block once the head is < 2 min old and ≤ 128 blocks ahead of it; the flat DB
> is read at the head and rewound to the target through trie logs (`TargetPriors`, ≤ 2M changed
> keys). The migrator also stops unless the DB is `FlatDbMode.FULL` with code by hash
> (`JumpDestCodeStorageStrategy` qualifies: it extends `CodeHashCodeStorageStrategy`); the H
> restore is both. A from-scratch snap sync is therefore possible in principle, but it was not
> attempted: on this 9-peer shadowfork it also downloads ~24.5M mainnet headers and ~1 TB of
> state, which may not finish before S. The trial uses the H restore, as below.

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
> **Correction (2026-10-27, read at 3f29bb53):** no re-extract is needed. `PbtSelfImport.Import`
> imports at the node's *current* persisted flat state (`reader.CurrentState`, pinned for the
> scan), resolves the keys the anchor lacked through the BALs N+1 … that state
> (`balFetcher.EnsureRange` fetches missing ones from peers), and skips only if the PBT DB is
> already valid. Removing `mainnet/pbt/` (376 GB) is enough; flat state, blocks and BALs stay.
> `PbtMigrationConfigValidator` requires `FlatLayout.Flat` for this mode (open question 3:
> satisfied), and rejects `FakeMatchingStateRoot` with a scheduled binaryTrieTime. The import
> passes `expectedRoot: null`, so like Besu it has no built-in root check.

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

---

## Run log (2026-10-27)

Monitor: user unit `pbt-1-selfconvert-trials` →
`~/.local/state/pbt-1-run/migration/selfconvert-trials/{trials.jsonl,events.log}` (5 min:
state, memory, disk, restarts, OOM, `debug_migrationProgress`, PBT log lines). Fleet watch
keeps running alongside. Pre-flight 00:19 UTC: nine workers at 24,534,265, finalized epoch
1041, 80 shadow roots compared, no alerts. Abort line: S − 12 h = 10-28 21:00 UTC.

**Nethermind-1 (TODO B)**
- Final state of the snapshot-import run: `synced`, cursor 24,534,311 (`0xcded5ad7…`), shadow
  root `0x784ab6f9…`, RestartCount 29. Evidence:
  `/data/pbt-1/nethermind-1-snapshot-run-evidence/` (inspect, progress, logs since 10-26 11:29).
- EL stopped 00:28:41–45 (clean: "All DBs closed"). `mainnet/pbt/` (376 GB) deleted 00:29:19;
  795 GB free; `pbt-snapshot.bin` kept for the rollback. Check-mode diff: snapshot flag out,
  preimages flag in, image `79ff97fa…` → `4428e138…`; nothing else.
- Deployed 00:29:27 (`2.3.0-preview+3f29bb53`, 16 GiB, 2.5 GB memory hint). **Self import
  started 00:29:52** at flat state 24,534,182 (`0x2489b215…`) through the preimages of N.
- Phases: the scan ran 00:29:52 to about 02:47 (~2 h 17 m), then Account (~03:20), Code
  (to about 04:05), then Storage (2.6 % at 04:18, 68 % at 05:09, ~370k leaves/s, 3.21 B leaves).
  The follower stayed at head the whole time.
- Memory (cgroup): anon 14.2 GB at 05:10, page cache squeezed to 1.3 GB, memory.peak at the
  16 GiB limit, `max` events 2.39 M, oom_kill 0. Docker stats: 7.4 → 11.8 GiB during the
  scan, then 14.3 → 15.3 GiB from Code onward.
- Disk free: 801 → 608 GB over the scan, then 254 GB at 05:10 (migration-work 228 GB +
  pbt/ 316 GB), falling about 2.5 GB/min during Storage.
- **Import done 05:27:31** after 4 h 57 m 38 s at 24,534,182 (`0xa20fd86e…`). It imported
  355,693,479 accounts and 1,877,822,062 slots (3,609,274,444 leaves in 36,093 windows).
  Root `0xa477d05c5532ae670a8e6bbf61e6d9c9eee3380de51c89c23bb98f8300b05924`.
  **Independent check: Geth-1/2/3 and Besu-2 report the same binary root at 24,534,182.**
  The Nethermind workers return null for that older block. The follower reached `following`
  at once (cursor 24,535,554 at 05:28). Peak: anon 16.0 GB at the limit, memory.peak
  16 GiB, `max` events 2.90 M, oom_kill 0, RestartCount 0. Scratch freed: 429 GB free and
  pbt/ 368 GB afterwards; disk low point about 250 GB.
- Root check before restart (`verify-nm1-pre-restart-1.json`): all eight non-trial workers
  agree on hash, stateRoot and binary root at 24,535,644–46. Besu-1 was skipped because it
  is converting.
- Restarted 05:28:48–57: a clean shutdown ("All DBs closed"), then "PBT state already
  populated; skipping the self import", flat and PBT both at 24,535,494, and `synced` at
  05:29:27.
- Root check after restart (`verify-nm1-post-restart-2.json`, blocks processed after it):
  the eight workers agree at 24,535,662–64 (binary root at 24,535,664 is
  `0x636bfcd9…f1`). **TODO B acceptance met for the eight non-trial workers.** The
  nine-way check including Besu-1 follows once its conversion is done.

**Besu-1 (TODO A)**
- Final state of the snapshot-import run 3: `synced`, cursor 24,534,301 (`0xe277fce7…`),
  shadow root `0xefd79651…`. Evidence: `/data/pbt-1/besu-1-run3-evidence/`.
- EL stopped 00:26:23–26; restore unit `pbt-1-besu-1-restore-selfconvert` (same
  `restore.sh` as run 3) started 00:26:26, DB deleted 00:26:41 (1,956 GB free).
  `pbt-snapshot.bin` kept: the work dir needs ~4 × preimages and the post-restore disk
  (877 GB in run 3) covers it. Check-mode diff: `--Xpbt-snapshot-file` →
  `--Xpbt-migration-self-convert=true`, image `850c5bae…` → `d8013fb0…`; nothing else.
- Memory kept at 16 GiB / 8 GiB heap, the same as Geth-3's self-migration, for comparison.
- H restore done 02:35:19 (1,132 GB extracted, 824 GB free). The check-mode diff was re-run
  at 02:35 and was unchanged. Deployed 02:36:03 (`26.10-develop-cc56425`). It logs "Flat db
  mode found FULL" and "code stored using code hash enabled = true". RPC was up at H
  (24,503,958) at 02:37:10, and `admin_changeLogLevel DEBUG …PbtMigrator` was sent then.
  Backward sync to head (~30k blocks) comes next, then the finality wait, then self-conversion.
- Backward sync H → head took about 2 h 30 m (02:37 to 05:07). The migrator started at
  05:07:28. **Self-conversion started 05:07:36** at flat block 24,535,469 (`0x3ea4bf0b…`),
  using the preimages of N and the BALs of the 81,911 blocks after N. At 05:10 cgroup anon was
  8.3 GB (page cache 5.6 GB), oom_kill 0, 795 GB free.
- **Self-conversion done 07:46:41** in 2 h 39 m 05 s, at target block 24,535,469 (`0x3ea4bf0b…`):
  - BAL preimages of the 81,911 blocks after N: 9 m 33 s.
  - Flat DB read (4 ranges at a time): 33 m 43 s.
  - New keys: 1 m 37 s.
  - Codes of 69,059,319 contracts: 8 m 23 s.
  - PBT build from 3,610,963,005 leaves: 1 h 45 m 47 s.
- Bootstrapped 07:46:58 with leaves 3,610,963,005, codes 3,150,083, root
  `0x8acd5af00d843d6f21b1ae791d1826bd495e53f555539653245fc9fc73744a7c`.
  **Independent check: Geth-1/2/3 and Besu-2 report the same binary root at 24,535,469**
  (`verify-besu1-bootstrap-block.json`, MPT stateRoot `0x873725ec…`). It then rolled in
  128-block steps, about 13 s per roll.
- Resources during the conversion:
  - Memory: Docker stats peaked at 14.57 GiB (5-min samples). cgroup memory.peak reached
    the 16 GiB limit, including page cache; anon was 8.3 GB at the start and 10.1 GB after
    the bootstrap. oom_kill 0.
  - Disk: free fell from 795 GB to a low of 542 GB at 07:46, so the work dir peaked at about
    253 GB. It was 4 KB after the bootstrap, with 600 GB free.
- Caught up with head at 07:48:43 (24,536,349, 880 blocks rolled, ~2 min), then `synced`.
- Nine-worker root check before restart (`verify-besu1-pre-restart-1.json`): all nine agree
  on hash, stateRoot and binary root at 24,536,350–52 (binary root at 24,536,352 is
  `0x931333c0…`).
- Restarted 07:50:27–31 (shutdown hooks ran). Startup again logged FULL with code by hash.
  "PBT migrator resuming from previously-materialised base block 24536358" (no
  re-conversion), `synced` at 07:50:46, DEBUG log level re-sent.
- Nine-worker root check after restart (`verify-besu1-post-restart-1.json`, blocks after
  the restart): all nine agree at 24,536,364–66 (binary root at 24,536,366 is
  `0x7568d303…`). **TODO A acceptance met.** This check also covers Nethermind-1 in the
  nine-way comparison.

**Summary (both trials accepted, 2026-10-27)**

| | Besu-1 self-convert (cc564258) | Nethermind-1 self import (3f29bb53) |
|---|---|---|
| Start → bootstrap | 05:07:36 → 07:46:58 (2 h 39 m) | 00:29:52 → 05:27:31 (4 h 58 m) |
| Target block | 24,535,469 | 24,534,182 (flat state at start) |
| Leaves / codes | 3,610,963,005 / 3,150,083 | 3,609,274,444 (355.7 M accounts, 1.878 B slots) |
| Root at target | `0x8acd5af0…4a7c` = Geth-1/2/3, Besu-2 | `0xa477d05c…5924` = Geth-1/2/3, Besu-2 |
| Peak memory (16 GiB limit) | anon ~10 GB, no OOM | anon 16.0 GB at the limit, 2.9 M `max` events, no OOM |
| Peak scratch | ~253 GB work dir | ~228 GB migration-work + pbt/ growth; low point ~250 GB free |
| Before restart / after restart | 9/9 agree / 9/9 agree | 8/8 agree (Besu-1 converting) / 9/9 agree |
| Extra | 2 h 30 m backward sync from the H restore first | No re-extract; the node stayed at head throughout |

Evidence: `~/.local/state/pbt-1-run/migration/selfconvert-trials/` (`trials.jsonl`,
`events.log`, `verify-*.json`).

**Nethermind-1 image update (2026-10-27, on request)**
- `merge-ten-lights-cover` moved 3f29bb53 → f609f2fd. That is a fast-forward of 28 files:
  in-memory trie node buffer compaction (new `FlatDb.CompressedNodeRecordBufferMemoryBudget`,
  default 500 MiB) and persisted snapshot sizing. No on-disk PBT change.
- Built with `panda build nethermind --repo NethermindEth/nethermind --ref f609f2fd37f4a3a731d861b4cab4903de8fc8307 --tag pbt-1-merge-ten-lights-cover-f609f2fd`
  (run 40485234454, success). The index digest `sha256:c8025812…` carries revision label
  f609f2fd, and the binary reports `2.3.0-preview+f609f2fd`.
- Deployed 10:17:19–32; the check-mode diff showed the image only. "PBT state already
  populated; skipping the self import", flat and PBT both at 24,536,934, `synced` at 10:18:18.
  All nine workers agree at 24,537,098–100 (`verify-nm1-f609f2fd.json`).
