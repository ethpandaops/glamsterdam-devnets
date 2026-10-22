# PBT-1 migration process

**Current execution plan and coverage gates:** [PBT-1 experiment](pbt-1-experiment.md).
This document retains the preparation history and earlier planning details.
Use the current plan where sequences or coverage claims differ.

Updated: 2026-10-20. Status: process draft based on the call notes and the
confirmed nine-machine matrix. All nine workers are now provisioned; the deployed
mapping is the [current plan's worker matrix](pbt-1-experiment.md#worker-matrix).

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

### Refreshed snapshot delivery complete at 10:58 UTC, October 20

All four native snapshots and the replay archive are published in the
[final manifest](https://shadowfork-images.ethpandaops.io/pbt-1/20261019-mixed-8037-v2/_snapshot_manifest.json). Publication completed at 10:57:54 UTC;
all seven independent public verification checks passed at 10:58:10 UTC.
The final runtime audit confirms all execution clients remain stopped, no
process holds native database files open, scoped upload credentials are removed
from all four VMs, and the original Jochemnet releases remain unchanged.
**The 09:00 UTC deadline was missed.** The refreshed-snapshot delivery is complete;
the nine-worker migration and PBT fork have not been run.

| Artifact | Compressed bytes | Source database allocated bytes |
|---|---:|---:|
| [Geth](https://shadowfork-images.ethpandaops.io/pbt-1/20261019-mixed-8037-v2/geth/24503958/snapshot.tar.zst) | 1,129,134,606,193 | 1,247,339,806,720 |
| [Besu](https://shadowfork-images.ethpandaops.io/pbt-1/20261019-mixed-8037-v2/besu/24503958/snapshot.tar.zst) | 1,145,428,233,899 | 1,215,262,593,024 |
| [Nethermind](https://shadowfork-images.ethpandaops.io/pbt-1/20261019-mixed-8037-v2/nethermind/24503958/snapshot.tar.zst) | 1,088,763,687,494 | 1,191,796,875,264 |
| [Erigon](https://shadowfork-images.ethpandaops.io/pbt-1/20261019-mixed-8037-v2/erigon/24503958/snapshot.tar.zst) | 534,953,200,071 | 1,054,319,771,648 |
| [Replay bundle](https://shadowfork-images.ethpandaops.io/pbt-1/20261019-mixed-8037-v2/replay/snapshot.tar.zst) | 49,215,859,161 | — |

Database figures are measured allocated bytes before export, not a guarantee
of extracted filesystem usage or migration peak space. Erigon includes the
restored BAL sidecars; its compressed archive is 534.95 GB.

All clients match at block **24,503,958**, with 51,420 retained BAL/body records.
The qualifying range is **24,453,559–24,503,958**: 50,400 blocks covering seven
days of accelerated chain time after qualifying anchor 24,453,558. The preserved
source anchor is 24,452,538; replay its 1,020 preparation blocks to reconstruct
the qualifying anchor. Using the final snapshot head as migration anchor would
leave none of this prepared backlog to replay.

The qualifying averages are 100,078,541.73 execution gas and 99,976,320 state
gas per block against the 200M limit; the smallest qualifying BAL is 450,865
bytes. This is a controlled mixed workload, not a live production traffic trace.

Native uploads used Content-MD5 on every part and SHA-256 readbacks of the
first, last and three sampled parts, followed by public size/ETag and metadata
checks. The 49.22 GB replay archive passed full remote SHA-256 readback. Native
archives were not re-downloaded in full. Exact sizes, checksums, commitments and
requirement-level evidence are recorded in the
[release audit](pbt-1-snapshot-release-2026-10-20.json).

The 15-minute monitor remains enabled. Prometheus, node-exporter and Vector run
on the four source VMs, and production node metrics show all four sources up.
The execution clients remain stopped.

Infrastructure update at 11:35 UTC: the merged
[ethPandaOps #1573](https://github.com/ethpandaops/ethPandaOps/pull/1573) was applied
from commit `475edb9bb299c71e41bee4598fcd99b15582194b`. The scoped apply created
five PBT DNS/Access resources and replaced the existing devnets certificate pack;
no separate PBT certificate pack was created. The replacement pack is active,
covers all 49 hostnames, and the post-apply scoped plan has no changes. Dora and
checkpoint-sync return HTTP 200 with valid public TLS; the auth endpoint redirects
to Cloudflare Access. MSF-2 TLS also recovered after the replacement gap.
[Platform #471](https://github.com/ethpandaops/platform/pull/471) was closed without
merging at the operator's request; existing automatic ingress-user discovery is
already active for PBT-1.

Checkpoint-sync's separate in-cluster certificate also issued successfully.
After the transient IPv6 self-check failure, cert-manager retried and reports
`Ready=True`. A direct request to the services load balancer returned HTTP 200
with successful TLS verification for the checkpoint hostname. VM certificates
under `srv.glamsterdam-pbt-1.ethpandaops.io` still need bootnode DNS delegation and
the wildcard issuer; the launch genesis and remaining fleet are also outstanding.
Controller rollout evidence is `cloudflare-pbt-rollout-verified.json`.

### Earlier milestone at 09:26 UTC, October 20

All four clients have passed their final restart/body audits at block
24,503,958. Erigon restored 51,323 missing native BAL sidecars, retained 97
existing sidecars, and reopened its pinned image with pruning disabled.
Its exhaustive Engine API audit verified all 51,420 bodies and all 50,400
qualifying blocks, then stopped cleanly with exit code 0 at 09:24:58 UTC.
Its head/hash/state/BAL commitments, 19 sampled addresses, transaction and BAL
totals, and qualifying gas measurements match the other three clients.

Controller evidence is `erigon-final-retention/verified.json`,
`erigon-final-reopen.json` and `four-client-final-audits.json`.
Erigon's upload service started at 09:26:09 UTC. Archive completion, remote and
public verification, and the common manifest remain pending. The 09:00 UTC
deadline was missed; `delivery-deadline-outcome.json` records that outcome.
Keep the delivery goal active until publication and the independent final
completion audit pass.

### Earlier milestone at 08:45 UTC, October 20

Erigon finished replay at 08:41:29 UTC, reaching block 24,503,958 with all
50,400 qualifying blocks. Its final block hash, MPT state root and BAL hash
match Geth, Besu and Nethermind. The native driver verified final persistence,
stopped the native client successfully, and reopened the database with the
pinned Erigon image. That reopen passed at 08:42:28 UTC.
Controller evidence is `erigon-final-replay-milestone.json`; VM evidence is
`native-replay/{replay-complete,native-shutdown,complete}.json`.

The final validation service started at 08:43:21 UTC and is checking the
51,420 BAL inputs before native sidecar restoration. The subsequent retained-BAL
restart, exhaustive Engine API body audit, clean stop, archive upload, remote
verification and global publication remain outstanding. The four-client
delivery will miss the 09:00 UTC target. Keep the full validation and publication
requirements; the completed replay alone does not satisfy delivery.

### Prepared range and earlier release status at 04:21 UTC, October 20

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
The final MPT state root and BAL hash also match. Geth and Besu's native
archives completed upload and verification at 02:55 UTC; Nethermind completed
at 04:20 UTC and passed public verification at 04:21 UTC. Erigon is the only
remaining client. The complete four-client release is not yet available.
At the 04:15 monitor check, Erigon had verified 35,388 qualifying blocks and
remained in replay. The 15-minute monitor measured 0.916 blocks/s and projected
replay alone to 08:48 UTC, leaving about 12 minutes for restoration, audit,
upload and verification before the 09:00 target. Full delivery by that time
looks unlikely. Existing phase logs around 04:16 showed independent medians
of 13 seconds executing each 64-block batch, 37 seconds flushing state, and
12 seconds committing; no memory-limit or OOM events were recorded.

After new memory-limit events and longer writes appeared around 04:40, a
48/56/48-GiB live comparison on the same VM measured 1.129 blocks/s at 56 GiB,
19.25% above the faster 48-GiB control. The windows used different successive
blocks. The original limit was restored for comparison, then 56 GiB was retained
at 04:59 for the remaining native replay, without a restart or VM change.
Its qualification and resource adjustment are included in native replay
provenance. The pinned-image final audit and later migration-worker matrix
retain their own resource limits. See the [memory recheck evidence](pbt-1-erigon-io-probe-2026-10-19.md#existing-vm-memory-recheck-at-04450459-utc).

The [Geth metadata](https://shadowfork-images.ethpandaops.io/pbt-1/20261019-mixed-8037-v2/geth/24503958/_snapshot_metadata.json),
[Besu metadata](https://shadowfork-images.ethpandaops.io/pbt-1/20261019-mixed-8037-v2/besu/24503958/_snapshot_metadata.json),
and [Nethermind metadata](https://shadowfork-images.ethpandaops.io/pbt-1/20261019-mixed-8037-v2/nethermind/24503958/_snapshot_metadata.json)
are public. Their archives are 1,129,134,606,193, 1,145,428,233,899 and 1,088,763,687,494 bytes,
respectively. Verification used per-part Content-MD5 during upload, exact object
sizes, and SHA-256 readback of the first, last and three sampled parts. Public
HEAD checks matched the completion ETags and exact lengths; public metadata
matched the archived hashes and common head/state/BAL commitments. Controller
evidence is `published-{geth,besu,nethermind}.json` and
`public-{geth,besu,nethermind}.json`. Nethermind's public integrity report
records the Patricia and both keystore exclusions, and its public FlatDB
cleanup proof matches the completed source cleanup. Its archive SHA-256 is
`925e81f4ccb2dd1464c29e77f5d6b3e361ae80153dbb0f49bf6bd5f34b2ba42c`.

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
**Superseded:** the [current worker matrix](pbt-1-experiment.md#worker-matrix)
maps these roles to `lighthouse-<client>-<n>` inventory hosts. Geth self-migration
runs on `lighthouse-geth-3`, and both Erigon workers use local conversion and
attach. All nine run `so-16vcpu-128gb-intel` (16 vCPU, 128 GiB). The reuse
proposal and Erigon-1 specs below describe the earlier plan.

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

#### Migration disk planning update, October 20

The four source VMs use the same nominal 1800-GiB local disk. That capacity is
not free space. Live filesystem checks around 08:45 UTC measured:

| Client | Native database, approximately | Available filesystem space |
|---|---:|---:|
| Geth | 1.247 TB | 509 GB |
| Besu | 1.215 TB | 558 GB |
| Nethermind, FlatDB only | 1.192 TB | 580 GB |
| Erigon | 1.031 TB, before final BAL restoration | 648 GB |

TB and GB in this table are decimal. Available space includes the effects of
other files and filesystem reservations; do not derive it by subtracting only
the native database size from advertised disk capacity.

The operator supplied a client-team planning figure of approximately 850 GB for
Geth; confirm whether this denotes additional free space. Besu's quoted figures
are 208 GiB permanent growth with approximately 370 GiB temporary import space.
These are planning inputs from another test, not
measured PBT-1 peaks. If both Besu allocations overlap, they total approximately
621 GB; confirm the allocation timeline before treating their sum as a measured
requirement. Peaks for all four clients and both memory limits remain to be
measured. The linked [Besu preflight](https://cperezz.github.io/pbt-website/uploads/benchmarks/import/r1/besu/P1/preflight.txt)
reports 1.5 TiB trimmed by `fstrim`, not a direct available-space measurement.

The proposed capacity mitigation is an **additional 2.5 TB volume per migration
worker**, alongside its existing disk. At the operator's request, one 2500-GiB
volume (~2.68 decimal TB) was attached to the idle Besu source VM on October 20
for a direct comparison with its local disk. The remaining volume rollout is
undecided, as is using volumes for recovery copies versus active databases.
See the [storage benchmark record](pbt-1-storage-benchmark-2026-10-20.md).
All 12 jobs finished successfully at 10:00 UTC: local versus volume sequential
writes were 862 versus 450 MiB/s, mixed 16-KiB I/O was 52,157 versus 9,999 IOPS,
and 4-KiB writes with per-write `fdatasync` were 8,368 versus 1,704 writes/s.
The test files were removed and Besu stayed stopped. These storage measurements
favor local database placement where capacity permits; they do not measure a
client's migration throughput or resolve its peak scratch-space requirement.
Keep storage configuration identical between the 16- and 32-GiB variants.
DigitalOcean sizes volumes in GiB: resolve the intended byte capacity explicitly
when preparing Terraform. Record volume type and actual database, artifact and
scratch placement. A separate mounted filesystem does not increase free space
under a client's existing data path; qualify the client's supported placement
before using it. DigitalOcean volumes are network-attached and have different
IOPS/throughput characteristics from local storage; include these in performance
results. See [volume limits](https://docs.digitalocean.com/products/volumes/details/limits/).

**Larger-local-disk alternative, checked October 20:** the operator is considering
a larger shape instead of putting the active database on a volume. This remains
a proposal; no resize or replacement has been performed.

| Shape | vCPU / RAM GiB | Local disk GiB | Catalog $/month | Listed in `fra1` |
|---|---:|---:|---:|---|
| Actual current `so1_5-8vcpu-64gb-intel` | 8 / 64 | 1800 | 556 | Yes |
| Originally quoted `so1_5-8vcpu-64gb` | 8 / 64 | 1800 | 652 | Yes |
| `c5-32vcpu-64gb` | 32 / 64 | 2000 | 992 | No |
| `m6-16vcpu-128gb` | 16 / 128 | 2400 | 1048 | Yes |
| `so-16vcpu-128gb-intel` | 16 / 128 | 2400 | 1048 | Yes |

The live DigitalOcean size API and the current Besu Droplet response confirmed
these values. Controller evidence: `migration-shape-options.json`.
Catalog regional availability does not reserve capacity. Listed prices exclude
other resources and taxes.

A 2500-GiB volume costs $250/month at the documented
[$0.10/GiB-month rate](https://docs.digitalocean.com/products/volumes/details/pricing/).
Consequently, the actual current shape plus one such volume is $806/month per
worker, versus $1048 for the larger local-storage shape: a $242/month difference,
or $2178/month across nine workers. Relative to the originally quoted $652 shape
plus volume, the difference is $146/month per worker.

The 2400-GiB alternatives add 600 GiB of local disk; the CPU-intensive candidate
adds only 200 GiB. Prefer qualifying the larger storage-optimized shape for
local active databases: its capacity increase addresses migration scratch space,
while the extra CPU on the 2000-GiB option does not resolve that constraint.
This is a proposed choice, not proof that its I/O matches the measured current
shape. Benchmark a candidate and measure peak migration disk use before rollout.
Keep recovery archives off the active filesystem when budgeting scratch space.
Apply the original 8-vCPU and 16-/32-GiB workload limits, including charged page
cache, on the larger host; its installed RAM is not the experimental RAM limit.
Use identical shape and storage placement for each client's comparison pair.

Aggressive history expiry is a separate optional experiment, not a prerequisite
for publishing the refreshed snapshots. Before enabling it on a migration
worker, validate the exact pinned client's flags, retain the common anchor and
all required replay bodies/BALs, measure reclaimed space, and repeat the
restart/retention audit. The supplied Besu pruning flags are a client-team
proposal and have not been applied or qualified on these sources.

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

**Snapshot refresh update (02:57 UTC, 2026-10-20):** Geth, Besu and Nethermind
have reached 24,503,958, passed all 51,420 body/BAL comparisons after restart,
and stopped cleanly for native archive upload. Geth and Besu are now uploaded,
remotely verified and publicly accessible; Nethermind's upload is still running.
The replay archive has completed upload and full remote checksum readback;
final delivery still requires all four verified native snapshots.

Erigon passed a 256-block trial of an optional in-memory storage filter,
including all bodies before shutdown and after pinned-release restart. Its
trial ended at 24,480,306 (26,748 qualifying blocks). Full replay continues
on the original VM with that build. Measured trial throughput was 1.21694 blocks/s,
21–31% above the earlier sequential baselines; this is not a same-input controlled
comparison. CPU/RAM limits remain eight CPUs and 48 GiB during preparation.
See the [native optimization and qualification evidence](pbt-1-erigon-io-probe-2026-10-19.md).
Final BAL restoration, exhaustive restart audit and native upload remain after
Erigon replay, so the 09:00 UTC delivery deadline is still at risk. The temporary
32-vCPU/256-GiB benchmark VM has been deleted.

As of 02:53 UTC, the final-stage tooling is prepared with an eight-worker, bounded BAL decoder,
four-thread input prefetch for the exhaustive body audit, and thirty-two concurrent
upload parts. Each change passed its relevant tests and bounded VM comparison.
These improvements preserve the canonical checks, full body comparisons and
clean-stop requirements. They do not establish a final-stage completion time;
archive production and network transfer must both be included in that time.

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

The [rehearsal DAG and history-expiry trial](pbt-1-rehearsal-dag.md) records
the October 20 source review, pivot alternatives, parallel work and storage
measurement gates. It also identifies the Besu BAL-retention minimum mismatch
and the newer Geth disk-saving candidate. Those Geth `84a12eff` and Besu
`39377a26` builds have since passed isolated startup checks on the full-state
workers. Expiry has not been trialed, and no build is migration-qualified.

### 1. Qualify source data and builds

Finish the Jochemnet restore. Open the source in isolation and verify its release
block 24452538 against the retained metadata. Record the head hash, state root,
database layout and recovery location before changing formats.

Pin every client image and migration tool by digest/commit. Establish the Erigon
database upgrade procedure and qualify each client's execution downtime.
The [Besu and Geth migration command update](pbt-1-client-migration-commands.md)
records the operator's exact Besu/library pins and Geth planning PR #12,
including both Geth online migration paths. The
[migration build pins](../scripts/pbt/migration-builds.json) are separate from
native snapshot preparation provenance. All five builds are now pinned and
build-verified, and seven workers passed isolated startup checks; migration
compatibility trials remain required. Run a small compatibility trial before
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

For `geth-self-16`, use the shared preimage file and anchor `N`, but omit the
PBT snapshot flag. The updated online procedure converts the worker's own
persisted state at `P >= N`, incorporating keys from BALs `N+1..P`, and attests
at finalized `P`. Record both anchors and compare roots with the import workers
at `P` or a later identical block hash. Use the same workload; do not require
its first attestation to be at `N` when `P` is later.

**Evidence:** nine individually identified results, peak memory/disk, elapsed
time, OOM/failure/retry records, actual attestation anchors and matching roots
at common block hashes.

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
- Test the Geth self-migration command and its anchor behavior (build pinned at `84a12eff`).
- Confirm storage capacity after measured Nethermind cleanup and conversion scratch.
- Set the pre-fork observation duration; the upstream two-week window remains
  the reference until explicitly revised.
- Preserve enough active stake during import/restarts for finality. The roles are
  mapped to inventory hosts with Lighthouse, at 256 validators each (2,304 total).
