# PBT-1 migration process

Updated: 2026-10-20. Status: process draft based on the call notes and the
confirmed nine-machine matrix. This document does not provision the remaining fleet.

## Immediate delivery target: refreshed snapshots

The requested overnight milestone is **additional workload generated on Geth,
replayed on all four clients, and new native snapshots uploaded**. It does not
include completing the nine-worker PBT migration or activating the PBT fork.
Planning deadline: 2026-10-20 09:00 UTC, pending any correction to the morning time.

Delivery requires:

- A pinned workload definition and an archived, checksummed payload/BAL bundle.
- Geth, Nethermind, Besu and Erigon advanced to the identical final block hash and
  MPT state root, with BAL commitments checked and actual BAL retention audited.
- Cleanly stopped databases that reopen at that head before export.
- For Erigon, restore any pruned BAL sidecars from the validated replay inputs
  after the final clean stop, checking every native canonical header commitment.
  Reopen the same image with `--exec.no-prune=true`, retrieve every BAL/body through
  the Engine API, and stop cleanly again. Include the native backfill evidence and
  retention profile with its snapshot.
- Four uploaded native database snapshots, each with client/build provenance,
  head metadata, size and integrity records. Verify remote object sizes and
  uploaded content using the export tooling's integrity checks before release.
- Retained source snapshots and replay inputs so the history can be reproduced.
  Publish under a new immutable PBT preparation prefix/height; preserve the
  existing Jochemnet release and avoid replacing its `latest` pointers.

The operator additionally requires approximately 50% utilization of **both**
EIP-8037 gas dimensions at the 200M block limit and substantial BALs. The revised
pilot measured ~100.53M execution gas, 99.98M state gas and ~443 KiB BALs per block.
From block 24,467,832, existing-slot updates are slightly reduced to keep execution
gas near 99.90M and prevent base-fee growth; state gas stays at 99.98M and BALs
remain about 451 KB. The full run enforces both dimensions, a 300 KiB BAL minimum,
and a 100M header-gas ceiling for this packing revision. It archives the dimension
measurements and the effective revision in the replay bundle.
The first low-load pilot is retained only as a preparation prefix, outside the
50,400 qualifying blocks. See the [active workload and automation procedure](../scripts/pbt/README.md#overnight-workload-and-publication)
for exact anchors, validation gates, live evidence paths and publication layout.

This is a target, not a guaranteed completion forecast. Restore the other
clients while Geth prepares the workload; replay consumers concurrently and upload
each snapshot as soon as its own validation completes. The 1,000-block pilot must
measure producer/consumer throughput, BAL sizes and database growth. Include both
archive compression and upload in the finish-time projection. Do not silently
reduce the 50,400-block target to meet the deadline.

### Prepared range and release status at 00:00 UTC, October 20

The generated stream is complete. Its preserved Jochemnet source anchor is
24,452,538. The next 1,020 blocks are preparation; the qualifying anchor is
24,453,558, timestamp 1,770,370,818. The qualifying range is
**24,453,559–24,503,958 inclusive: 50,400 blocks**. The final timestamp is
1,770,975,618. Anchor-to-head coverage is exactly 604,800 seconds (seven days);
the first-to-last qualifying block timestamps span 604,788 seconds. These
figures describe accelerated chain time, not elapsed live operation.

Geth, Besu and Nethermind have reached the final head, passed clean restart and
retrieval/comparison of all 51,420 generated bodies, and stopped cleanly for
export. Their final block hash is
`0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216`.
The final MPT state root and BAL hash also match. Their native archives are
uploading; no completed release is claimed. At the midnight monitor check,
Erigon had verified 20,732 qualifying blocks and remained in replay. The
15-minute monitor measured 1.047 blocks/s and projected replay alone to 07:52
UTC; final restoration/audit and upload make the 09:00 delivery target uncertain.

The intended release prefix is
`pbt-1/20261019-mixed-8037-v2/`, with native archives at
`<client>/24503958/snapshot.tar.zst`. Use the final manifest only after all four
native uploads and the replay bundle pass publication checks. Controller
`delivery-complete.json` is the completion marker; individual upload progress
and the presence of a partial release prefix are not sufficient.

At 01:03 UTC the [replay archive](https://shadowfork-images.ethpandaops.io/pbt-1/20261019-mixed-8037-v2/replay/snapshot.tar.zst)
completed full remote readback verification. It contains all 51,420 records,
including the 50,400 qualifying blocks. Every compressed input file matched
the audited Geth source before upload and was checked again while archiving.
The archive is 49,215,859,161 bytes, with SHA-256
`746ade7c018b644de66df47dc23cc477da98333aaf5230e065ce7e2112be8ccc`.
Its embedded replay manifest has SHA-256
`c51eda562cc882fa2ba87bd110fb9156def42d7a9588d05a977b9729965bed01`.
Public HEAD returned HTTP 200 with the verified length and ETag. Controller
evidence is `replay-bundle-ready.json`; this establishes the replay artifact
only. Native snapshot publication and the final delivery manifest remain
pending. Preparing this archive early removes its upload/readback from the
work that must follow Erigon's completion.

At 01:05 UTC an archive review found Nethermind's nested
`mainnet/keystore/node.key.plain` was missing from the uploader's exclusions.
The still-unpublished multipart upload was stopped and aborted; storage
confirmed that the archive object did not exist and the old multipart upload
was gone. The key and native database remain on the VM. A fresh upload started
at 01:08 UTC with both keystore locations and Patricia data excluded, and its
live tar arguments were checked. Publication now requires those exclusions in
the upload integrity report. The archive-content regression test first
reproduced the omission, then passed with the fix; all 32 Python workflow
tests passed. Evidence is controller
`retired-nethermind-upload-keystore/abort-verified.json`. Geth and Besu's
observed key paths were already excluded, so their uploads continued.

For the later migration/backlog experiment, the qualifying anchor can be
reconstructed from the preserved source release and the 1,020 preparation
records. Qualify that reconstruction and produce the PBT artifacts at the
chosen anchor before consuming the tail. Do not assume that a refreshed native
snapshot at 24,503,958 exposes historical MPT state at 24,453,558. Selecting the
refreshed head as the migration anchor would remove this prepared replay backlog.

## Decisions from the call

- Nine machines: eight import-path workers and one Geth self-migration worker.
- Each of Geth, Nethermind, Besu and Erigon gets one 16 GiB and one 32 GiB
  import-path worker. Enforce the memory budgets at the process/container level.
- The additional Geth worker runs self-migration with a 16 GiB limit.
- Complete migration and catch-up before the PBT fork.
- Check how many days of BALs are actually available. Target at least one week
  of usable, continuous history, and preserve the required range through catch-up.

## Machine matrix

Names below are proposed experiment identifiers, not deployed inventory names.

| Machine | Client | Path | EL/migration memory limit |
| --- | --- | --- | --- |
| geth-import-16 | Geth | Shared artifact import | 16 GiB |
| geth-import-32 | Geth | Shared artifact import | 32 GiB |
| nethermind-import-16 | Nethermind | Shared artifact import | 16 GiB |
| nethermind-import-32 | Nethermind | Shared artifact import | 32 GiB |
| besu-import-16 | Besu | Shared artifact import | 16 GiB |
| besu-import-32 | Besu | Shared artifact import | 32 GiB |
| erigon-import-16 | Erigon | Consumer qualification; see Erigon note below | 16 GiB |
| erigon-import-32 | Erigon | Consumer qualification; see Erigon note below | 32 GiB |
| geth-self-16 | Geth | Local self-migration | 16 GiB |

**Proposed reuse to keep the total at nine:** use the existing DigitalOcean
Erigon source machine for artifact generation first, then as `erigon-import-32`.
Retain the artifacts and a recoverable source before reusing its working database.
Run generation and the measured consumer trial sequentially on that machine.
There is no permanent tenth generator in this proposal.

The existing source is `164.92.239.96`, with 8 vCPU, 64 GiB physical RAM and
1800 GiB nominal local disk. Its current inventory name is `lighthouse-erigon-1`.
The [restore procedure](../scripts/pbt/README.md) describes its setup.

### Geth workload producer and later reuse

The Geth preparation VM uses the same DigitalOcean storage-optimized class.
It can later become `geth-import-32`, preserving the nine-machine benchmark
matrix. It must finish generation and retain the replay bundle before that reuse;
keeping a separate live producer during all nine trials would require a tenth
machine. Geth (`46.101.230.44`), Besu (`138.68.76.218`), Nethermind
(`167.172.188.11`) and Erigon have now restored successfully. Nethermind's
client-managed Patricia deletion and FlatDB restart verification are complete.
Geth generation and the Besu/Nethermind final replay audits are complete;
Erigon remains in replay.

Use the existing Geth-first payload-generation / cross-client replay pattern
from the snapshot build tooling. Qualify its current build and configuration on
a short trial before producing the full history. An execution client also needs
a block-production driver: use the recorded Engine API workflow for offline
preparation, or a CL/validator network for live finality testing.

1. Restore Geth at the same release head as Erigon. Establish usable workload
   accounts and contracts through recorded transactions. Replay this setup prefix
   on all clients, compare heads/roots and choose the migration anchor `N`.
2. Retain a recoverable native database at `N` for each client, including the
   Erigon exporter. Generate PBT artifacts from that anchor. Any offline anchor
   remains a prototype anchor until the live-finality requirements are satisfied.
3. On the producer, generate a proposed **50,400 additional blocks after `N`**,
   advancing block timestamps by 12 seconds. This gives a full seven days from
   the anchor to the end, independent of the inherited BAL count. Accelerated
   generation represents seven days of chain time, not a week of live operation.
4. Record the exact payloads, forkchoice inputs, BAL bodies, block hashes, state
   roots and BAL commitments. Preserve a checksummed bundle outside the producer
   VM and confirm that the migration followers can consume its BALs. Storing
   Engine API requests alone does not establish a supported follower data source.
5. First qualify roughly 1,000 blocks on each client, checking payload validity,
   head/root agreement, BAL availability and restart. Use the same canonical
   stream on every client; do not generate independent chains per client.
6. For the measured trial, import/migrate at `N`, then replay the generated tail
   under the assigned memory limits. If MPT execution is advanced ahead of PBT
   to model an online migration, preserve verification access at `N` and measure
   the PBT backlog separately. Advancing everything and moving `N` to the new
   head would discard the intended backlog.

Define "typical load" using a recorded mix of ETH/token transfers, contract calls
and storage reads/writes, including both repeated and new state accesses. Use
[Spamoor's transaction scenarios](https://github.com/ethpandaops/spamoor) as inputs
where supported by the production driver. Choose the mixture and occupancy from
a representative reference sample; do not silently reuse the most adversarial
MSF-2 stress scenarios. Record gas-used distribution, transactions per block,
distinct accounts/storage keys, BAL sizes and database growth. Set the full-run
disk and runtime budget from the short trial before generating all 50,400 blocks.

Pass this backlog trial before the live network's BAL catch-up and PBT activation
rehearsal. An offline payload replay alone does not demonstrate CL finality or
the agreed pre-fork observation period.

## Measurement controls

Use the same 8-vCPU and storage class across workers where possible. Record
physical RAM separately from the enforced 16/32 GiB limit; these are process-budget
experiments. Leave host capacity for the OS, consensus client and monitoring.

Apply a hard cgroup memory limit to the complete measured workload, including
importer/converter subprocesses. If migration and execution run in separate
containers, enforce their combined budget with a common parent cgroup. A runtime
heap setting alone is insufficient. Record the effective limit, peak cgroup usage,
file-cache accounting and OOM events. Use zero swap allowance for the measured
workload so swapping cannot silently turn the trial into a larger-memory run.

Record application cache/heap settings and keep them consistent between repeat
runs. Start measurement after artifact download, unless transfer is explicitly
part of the trial. Measure transfer separately. Keep the memory limit in place
through import/self-migration, catch-up and fork activation.

Before each trial, record free and allocated disk space. Budget the source DB,
new PBT DB, artifacts, temporary files, retained BALs and recovery copy together.
Nethermind's obsolete Patricia store **must be removed before upload**, as requested
by the operator. Validate the flat database, measure the reclaimed space and retain
the active flat data plus headers, blocks, BALs and other required native data. Do not
assume every client's full experiment fits the source machine's disk size.

The dedicated Nethermind VM completed `pbt-1-nethermind-flatdb-cleanup` on
2026-10-19. After a successful restore, it checked the pinned head/root and
sample state reads, invoked the pinned 2.1.0 image with
`--FlatDb.DropPruningTrieState=true`, then verified another clean restart with
that flag disabled. It reclaimed 341,910,994,944 bytes using the client's FlatDB
ownership checks. Evidence and the success marker are under
`/data/pbt-1/nethermind-flatdb-cleanup/`; require `complete.json` before export.
An empty Patricia database stub may be recreated by the client; the obsolete
Patricia data is gone, and the exporter also excludes the empty stub.

## Relationship to the upstream plan

The [upstream rehearsal plan](https://github.com/misilva73/pbt-planning/blob/main/outreach/pbt-mainnet-fork-migration-test-plan.md)
uses a finalized anchor `N`, a dedicated Erigon artifact producer, consumer
verification/import, catch-up and a later activation timestamp `S`. It assumes
18 days of BAL retention and at least two weeks maintaining both trees before
activation. Neither assumption establishes our actual retained history. The call's
one-week BAL requirement does not by itself shorten that testing window.

**Erigon qualification:** the plan's supported rehearsal path verifies the shared
artifacts, then converts and attaches local state. Its direct shared-snapshot
import is described as test-only. Keep both Erigon machines in the requested
matrix, but confirm with the pinned build whether they will exercise literal
import or conversion/attach. Label their results accordingly. The
[pinned Erigon runbook](https://github.com/erigontech/erigon/blob/06d0833e3d2/docs/pbt-migration.md)
requires v3 hex commitment state for conversion; our v3.7.1 Jochemnet archive's
upgrade path still needs qualification.

## BAL availability audit — required before selecting the anchor

### Confirmed snapshot history

The [release bundle](https://github.com/ethpandaops/benchmarkoor-tests/releases/tag/eest-payloads-jochemnet-v1-amsterdam-stateful-e269bb44-20260916-124530)
was inspected on 2026-10-19. Its first two payloads, blocks 24402728 and
24402729, use `engine_newPayloadV4` at timestamps 1769856767 and 1769856768.
The first `engine_newPayloadV5` is block **24402730**, timestamp **1769856780**,
after the configured Amsterdam time 1769856769.

The [published release head](https://shadowfork-images.ethpandaops.io/jochemnet/erigon/24452538/_snapshot_eth_getBlockByNumber.json)
is block **24452538**, timestamp **1770358578**. Thus the inherited chain contains
**49,809 Amsterdam blocks including the activation block**:
`24452538 - 24402730 + 1`. This is the expected BAL count if all bodies are retained,
not a measured count of retrievable BALs in any client's database.

The first-to-last BAL block timestamp span is **501,798 seconds (5.80785 days)**.
At a hypothetical steady 12 seconds per block, 49,809 blocks represent 6.918 days;
the actual preparation history has different intervals. A seven-day count at
12 seconds per block is 50,400, or 591 more blocks, but that count comparison does
not establish seven days of timestamp coverage.

If migration anchor `N` is the restored head 24452538, the inherited blocks are
at or before `N`: the initial replay backlog **after that anchor is zero**.
Use a recoverable earlier anchor or accumulate new blocks/BALs after preserving
`N` to construct the intended replay trial. Retained BALs alone do not establish
that a client's historical MPT state at an earlier anchor is still accessible.

### Retention measurements still required

**Initial finding (13:18 UTC):** the checked PBT-1/MSF-2 per-client inventory files do not
explicitly configure BAL retention. Effective defaults, retained ranges and
retrieval support remain unmeasured. At 13:18 UTC on 2026-10-19, the source restore
was still running (3190/4118 chunks); it had no execution client serving BALs.

**Preparation update (20:30 UTC):** all four source restores are complete.
Nethermind's native Patricia cleanup and FlatDB restart passed, reclaiming
341,910,994,944 bytes. All four clients passed the 1,000 qualifying-block pilot,
including clean restart and exhaustive retrieval/comparison of 2,020 generated
bodies. See [pilot evidence and effective retention findings](pbt-1-8037-pilot-2026-10-19.md).
This proves that generated interval; it does not establish complete historical
coverage before the downloaded source anchor.

The full run targets 50,400 qualifying blocks ending at 24,503,958, with 51,420
total replay records including preparation. At the scheduled 20:30 check, Geth
had generated 35,231 qualifying blocks, Besu had replayed 35,117, Nethermind's
head was 24,488,717, and Erigon had replayed 15,164. All four passed the oldest
generated, first qualifying and recent BAL spot checks. Full-range final audits
and native snapshot uploads remain pending. Erigon throughput puts the
2026-10-20 09:00 UTC delivery target at risk; its experiments and recovery
evidence are recorded in the [Erigon preparation report](pbt-1-erigon-merge-2026-10-19.md).

Audit the actual source network and every service that will supply replay data:

1. Record client build/digest, effective retention and pruning settings, the units
   used by those settings, and the oldest/latest retrievable canonical BAL blocks.
   Obtain the retrieval method from the pinned client's implementation; do not
   assume all clients expose the same RPC.
2. Fetch a recent known block first to validate the retrieval method. Then locate
   the retention boundary and retrieve the proposed replay interval. Distinguish
   missing/pruned data from unsupported methods and transport errors.
3. Check canonical block hashes, parent continuity and BAL validity using the
   pinned client's supported verifier. Boundary samples estimate coverage; only
   a complete range check establishes that the replay interval has no gaps.
4. Report coverage using block timestamps:
   `available_days = (latest_timestamp - earliest_timestamp) / 86400`.
   Also record the wall-clock age of the oldest BAL. One week is 604800 seconds;
   block counts alone are insufficient when slots can be missed.
5. Preserve the interval before pruning can remove it. Continue collecting new
   BALs until the slowest worker catches up. If using an external archive, test
   that the pinned replay implementation can actually consume that archive.
6. Repeat the retrieval check from a consumer and record its sustained throughput.

| BAL evidence | Result |
| --- | --- |
| Source network and provider(s) | To measure |
| Client builds and retrieval methods | To qualify |
| Effective retention/pruning settings | To measure |
| Earliest/latest retrievable block, hash and timestamp | To measure |
| Continuous usable history in days | To measure; target >= 7 |
| Missing blocks or invalid BALs | To measure; required interval must have none |
| Preserved interval and storage location | To establish |
| Retrieval/replay throughput and oldest-data expiry | To measure |

For an anchor already a week behind the head, a rolling seven-day retention limit
provides essentially no preparation margin. Size retention for anchor age plus
generation, distribution, the slowest import, catch-up and retries, or preserve
the interval independently. If the required data is absent, move the anchor or
accumulate the history before starting the measured replay trial.

## Execution sequence and completion evidence

### 1. Qualify source data and builds

Finish the Jochemnet restore. Open the source in isolation and verify its release
block 24452538 against the retained metadata. Record the head hash, state root,
database layout and recovery location before changing formats.

Pin every client image and migration tool by digest/commit. Establish the Erigon
database upgrade procedure, the exact Geth self-migration command and whether
each client requires execution downtime. Run a small compatibility trial before
the full-state measurement. Preserve finality when scheduling worker downtime.

**Evidence:** source validation, build manifest, per-client commands, memory-limit
inspection, storage budget and a completed BAL audit.

### 2. Choose and preserve the experiment anchor

Choose a common block after checking both state access and BAL coverage. Preserve
the state required by every worker. Obtain finality evidence from the running
network and record the exact block hash/root; the static downloaded release alone
does not establish finality for a new PBT-1 network.

**Evidence:** anchor manifest, preserved-state locations and recoverable replay
data beginning with the next block. For a one-week backlog experiment, explicitly
record the timestamp span of that backlog.

### 3. Produce and retain the shared inputs

Use the source Erigon machine to generate the artifact pair. Record file sizes,
checksums, format, anchor and generation resource usage. Test access from a worker.
Retain the inputs before switching this machine to its 32 GiB consumer role.

**Evidence:** immutable artifact manifest, accessible copies and a source recovery
path that fits the measured storage budget.

### 4. Run the two migration paths

For the eight consumer workers, record the chosen import or Erigon-specific
procedure and its start/end times under the assigned memory limit. Verify each
result at the common anchor. Record any required pause in normal execution.

For `geth-self-16`, generate PBT state locally from its own preserved source using
the qualified self-migration procedure. Do not seed this trial from the shared
PBT artifact. Use the same anchor and workload as the Geth import workers so the
comparison is meaningful. Compare its resulting root with the consumer results.

**Evidence:** nine individually identified results, peak memory/disk, elapsed
time, OOM/failure/retry records and matching roots at the anchor.

### 5. Catch up, then evaluate fork readiness

Exercise the intended catch-up mechanism on every worker. Record whether progress
came from BAL replay, local trie logs or Erigon re-execution; distinguish these in
the results. To claim a BAL replay test, demonstrate actual BAL consumption.

Measure initial backlog, replay throughput, remaining lag and concurrent live
processing. Compare roots at identical block hashes. Continue the agreed
pre-fork observation period after catching up; do not equate one week of stored
BALs with one week of successful runtime testing.

**Evidence:** all nine workers caught up, matching roots, no missing replay data,
healthy finality, and the agreed observation period completed.

### 6. Activate and retain results

Prepare the activation configuration in advance using each pinned client's
required ordering. Record how to postpone activation before its timestamp if
any worker is not ready. Reach the fork only after the readiness evidence passes.
Observe all nine workers across activation, then test restart and continued
agreement. Retain native PBT database backups for later benchmarks.

**Evidence:** activation block/hash, post-fork finality and root agreement,
restart results, resource measurements and database-backup locations.

## Items still to resolve

- Measure the actual BAL window and preservation mechanism on the chosen network.
- Qualify Erigon's source-format upgrade and consumer path.
- Pin and test the Geth self-migration command and its anchor behavior.
- Confirm storage capacity after measured Nethermind cleanup and conversion scratch.
- Set the pre-fork observation duration; the upstream two-week window remains
  the reference until explicitly revised.
- Map these nine logical roles to inventory names, consensus clients and validator
  assignments. Preserve enough active stake during import/restarts for finality.
