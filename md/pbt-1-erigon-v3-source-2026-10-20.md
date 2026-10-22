# Erigon v3 source snapshot

See the [current experiment plan](pbt-1-experiment.md) for the distinct exporter
and worker roles and the coverage requirements. This file is an operation record.

## Scope correction

The operator clarified that the patched worker snapshot must be the advanced
snapshot at **24,503,958**. The controller service
`pbt-1-v3-source-publication` has been stopped to prevent publishing the older
source as fulfillment of that request. Nothing from this conversion has been
uploaded. The source conversion is exporter preparation;
it does not upgrade either worker's final-head database.

The older copy exists solely to reconstruct the proposed PBT export anchor
24,453,558, leaving 50,400 prepared BALs between that anchor and the workers'
starting head. Workers should retain their advanced native snapshots. My earlier
description incorrectly conflated the exporter anchor with the worker starting
point.

The existing conversion targets the restored Jochemnet source. This remains an MPT database at
block **24,452,538**, not a PBT database and not the final workload head.
The 1,020-block preparation replay to N=24,453,558 remains a subsequent operation.

Status at 19:41 UTC: the native v3 pass failed at 19:26:39 on commitment shard
`1049600-1049728`: the accounts file `1049600-1049856` crosses its ending
boundary (`max step 1049727 splits accounts domain file`). Five v3 shards are
complete, covering 82.3% of input keys. Their output is preserved. This is a
file-layout consistency failure, not an OOM or disk-reserve stop. The guarded
reopen job refused to proceed; no native reopen or anchor replay began.

A read-only filename audit found the same oversized range for storage. Both
domains retain twenty smaller, indexed files covering the range without gaps.
Full record comparisons passed: 262,756 accounts records and 335,569,656
storage records match the newest values in the retained fragments exactly.
The diagnostic uses the pinned Erigon segment reader and opens no database.
A small native v3 fixture also passed cancellation/resume, completed-file reuse,
and block/transaction/state-root preservation; the deployed binaries are unchanged.

At 19:48:22 UTC the reviewed recovery restarted the existing conversion unit.
It moved only the two oversized files and their four indexes into
`v3-source-upgrade/boundary-recovery/hidden-domain-files`, preserving them.
At 19:48:39 the native `--v3 --continue` command confirmed reuse of five shards
covering steps 0–1049600, with 214 files remaining. The older failure evidence
is retained under `boundary-recovery/before-*`. Full v3 verification, execution
restoration and native reopen are still required. At 19:54:18 the same
SHA-pinned reopen guard was explicitly requeued behind this conversion. It
requires successful inactive conversion and all phase proofs before opening
the native client; anchor replay and publication remain unqueued. Public evidence:
`ansible/inventories/pbt-1/files/erigon-boundary-recovery.json`.
At 19:56:07 the formerly failing shard completed with indexes: 82.93 million
records in 7m19s. That is 51.4% of the resumed suffix's input keys, not 51.4%
of the original conversion or total preparation time. Conversion continues;
final root verification and native reopening are still pending.
At 20:05:55 all 214 resumed files finished. Native phase 2 accepted all 219
files; phase 3 preserved 438 original files and phase 4 promoted 657 converted
data/index files by 20:06:00. The native command remained active in final
verification, so this is not a completed conversion proof.

The explicit subsequent `commitment verify` is retained after source review:
`verifyCommitmentV3Files` folds the records and logs the orphan count, whereas
the CLI's `commitmentVerify` additionally rejects nonzero orphan counts and
opens the persisted files in a fresh process. Both use `FoldCommitmentV3` for
the root comparison. This extra validation is not interchangeable with the
converter merely returning success.
Native `snapshots unmerge` supports block snapshots, not these domain files.
Any conversion retry must use `--v3 --continue` to retain completed output;
do not execute the error message's suggested rebuild-directory deletion.

Earlier at 18:27 UTC: schema preparation passed. Unsqueezing stopped at the
150 GB disk reserve at 17:34. An isolated index recovery finished at 17:57,
then unsqueezing resumed with `--continue` at 17:59 and completed at 18:08.
`commitment convert --v3` was running (file 1 of 219, 49.5% of keys).
V3 verification, the `stage_exec` restore, native reopen qualification and
upload have not completed.

At 17:00 UTC, Erigon-2 independently started the H conversion using
`upgrade-erigon-head-v3.py`. Its datadir is `/data/pbt-1/erigon`, evidence is
`/data/pbt-1/v3-head-upgrade`, and its verified compressed H archive is the
rollback copy. This does not change the older exporter's role. The H startup
and persistence check is queued behind conversion and verifies the pinned
image under Erigon-2's 16 GiB limit. Publication remains gated.
At 18:19 UTC its unsqueeze was on file 1 of 4,091 (60.7% of keys).
Erigon-2 completed unsqueezing at approximately 19:28:50 and entered the native
v3 pass at 19:28:54. At 19:41 its process was live, clearing mutable execution
tables as the native converter requires. A full filename-range audit found a
potential later accounts/storage boundary conflict at `1050624-1051648`;
retained one-step files cover that range. This is a predicted compatibility
issue, not an observed Erigon-2 conversion failure. No files were moved on
either node during the initial audit. The subsequently reviewed file selection
change applies only to the older exporter, as recorded above. Erigon-2's
read-only full-record comparison completed at 19:49:48: all 66 accounts records
and 3,489,808 storage records match the newest values from their respective
1,024 one-step fragments. Index files are present and the range is fully
covered. Its files remain unchanged by the boundary review; conversion is
still running. Evidence is in
`ansible/inventories/pbt-1/files/erigon-head-boundary-review.json`. An actual
failure, a confirmed stopped converter, and fresh file-identity checks are required
before applying any recovery to the worker database.
The worker-specific `resume-erigon-head-boundaries.py` is now staged. Six
focused tests cover rejection of a live owner, unrelated failures, gaps,
overlaps, wrong accessors and mismatched comparison proofs. Its live read-only
invocation refused the active conversion lock and preserved status and file
selection. A separate read-only check verified all 6,144 fragment/index
identities and the six candidate files. The script and native/driver/fixture
hashes are recorded in the head boundary review. No recovery is queued.
After the exact expected failure, inspect the stopped state, run the script
without arguments for its full preflight, and only then use `--apply` via the
existing conversion service with its preparation resource limits. It preserves
the six merged files, requires the expected six-shard completed prefix, uses
native `--v3 --continue`, and restores H with `NO_PRUNE=true`. Requeue worker
qualification separately after reviewing the resumed conversion.

Erigon-2 began reporting v3 record progress at 20:08:29 on the first commitment
file, after the execution reset and file-opening work. At 20:08:59 it reported
3.14 million of approximately 1.05 billion input keys. Read-only process
sampling during the preceding quiet interval confirmed 22.7 GiB of disk reads
over 76 seconds; the converter remained live and was not restarted.

## Bounded lookup optimization review

At 20:26 UTC, the independent candidate review established matching logical
records for all five shards in a deterministic small conversion, including
the initial full shard and incremental shards. The original and candidate
were tested separately against the same pinned source fixture. This is a
small-state equivalence check, not proof of a full-state conversion.

`scripts/pbt/erigon-v3-bounded-view.patch` narrows each conversion worker's
private file view before its first lookup. It removes only trailing files
whose starting transaction is after that conversion's maximum step. It leaves
crossing files in place so the existing split-boundary rejection still applies;
it does not solve the independent merged-file layout problem. The aggregator's
shared generation, file indices, encoding and root algorithms are unchanged.

The candidate passed the v3 conversion/restore, cancellation/resume and bounded
lookup tests, including preserving the split-boundary error and reopening a
fresh full view after closing the narrowed view. A lookup-only microbenchmark
measured 18,318 ns with 3,068 visible file descriptors versus 87 ns after
trimming to the one eligible file. This isolates metadata-scan overhead and
must not be presented as an end-to-end conversion speedup.

The isolated native build uses a Go source overlay, separate output directory
and `pbt-bounded-view-experiment` version label. Production binaries and both
running conversions remain unchanged. Evidence, patch/source checksums and
per-shard record checksums are in
`ansible/inventories/pbt-1/files/erigon-bounded-view-review.json`.
Any later use must record the candidate binary and patch separately and keep
the pinned original verifier; do not reuse original-only provenance for a
modified converter. No candidate has been deployed at this checkpoint.
The candidate native build subsequently completed with SHA-256
`1f807caefedc534ae837641ebff1dfdc37c0378ea8e3556263bddd1eb276e9f3`.
Its post-build `--version` probe failed because integration has no such flag;
the error is preserved. Supported `commitment convert --help` and Go build-info
checks then passed, including GOAMD64 v2 and the jsonv2 experiment. The original
native binary's SHA-256 was rechecked unchanged. This build is available only
under `/data/pbt-1/boundary-review/candidate-bin/integration` on Erigon-1.

At 20:38:16 UTC the original Erigon-2 conversion was deliberately interrupted
with SIGINT to adopt this reviewed optimization. It exited with `context
canceled`; the parent stopped at 20:38:24. This was an operator-directed
performance change, not a spontaneous failure. The unfinished first shard
had reached 157.40 million input keys (14.9% of total keys); no complete v3
shard existed, so that partial work must be repeated. The old log and status
are preserved under `v3-head-upgrade/bounded-view-handoff/before-*`.

At 20:39:02, after fresh checks of the original recovery archive, file identities
and prior equivalence evidence, `resume-erigon-bounded-conversion.py` resumed
with the separate optimized native binary and `--v3 --continue`. The existing
unit retains its 8-CPU/96-GiB limit and private network. Its native PID was
23770 at the recorded check. The six oversized accounts/storage files and
indexes were preserved in `bounded-view-handoff/hidden-domain-files`, selecting
the previously verified equivalent fragments before the predicted boundary
conflict. The earlier failure-only recovery script was not used.

Only the conversion pass uses the patched native binary. Both independent
verification passes, head restoration, and the measured worker image remain
the original pinned builds. Qualification now checks the exact candidate and
patch identity plus original-verifier phase evidence. The qualification waiter
was requeued at 20:39:20; its eventual native opens retain the 16-GiB/8-CPU
limits. Publication now requires matching converter provenance in qualification
and conversion records and includes it in release metadata. Ten handoff and
qualification identity tests plus thirteen archive/publication tests passed.
No full-state candidate success or end-to-end speedup is claimed yet.

At 20:53:08 the next offline anchor step was queued conditionally in the
existing `pbt-1-erigon-anchor-preparation.service` using
`handoff-erigon-anchor.py --wait` (PID 38731 at the recorded check). It does
not remove the instruction-review hold while conversion or qualification is
active. All predecessor units must finish successfully; exact O reopen proofs,
the reviewed driver checksum, replay-prefix hash, recovery proof and disk space
must pass before the hold is archived and the existing N driver runs once.
Its default read-only check correctly refused the live predecessor without
changing the hold or starting a client. Three handoff tests passed.
The service now has an 8-CPU/32-GiB private-network cap for its future offline
stage, replacing the earlier waiter-only 1-CPU/2-GiB limits. The original
unit configuration is preserved in the anchor evidence directory. The first
attempt to create a transient service found that existing unit and changed
nothing; a reviewed runtime override starts the guarded handoff instead.
No genesis time, shadowfork launch or PBT activation is part of this handoff.

Erigon-2's restart automatically compacted the mutable database from 518.0 GB
to 60.0 GB by 20:43:55. Its reset completed and native `--continue` confirmed
there were no complete prior shards at 20:44:42. The first subsequent record
progress showed approximately 375 thousand keys/s; at 20:54:22 it reported
44.77 million keys (4.2% overall) at 373.15 thousand keys/s. The original run's
last rate was 87.44 thousand keys/s at a later point in the first shard. The
observed ratio is about 4.27, but positions/cache state differ and compaction
also occurred; it is not a controlled full-conversion speedup or a completion
estimate. Original-verifier checks are still outstanding. The raw progress
lines and comparison are retained in the bounded-view review evidence.

## Source and recovery

- Worker: Erigon-1, `164.92.239.96`.
- Working source: `/data/pbt-1/rehearsal-24453558/erigon`.
- Evidence: `/data/pbt-1/v3-source-upgrade`.
- Original rollback checkpoint: `original-checkpoint` under the evidence path.
  Immutable snapshot files are hardlinked; mutable databases were copied
  independently. Do not open or modify this checkpoint during conversion.
- The original remote Jochemnet release remains available.
- The final-head database `/data/pbt-1/erigon` is separate and unchanged.
- Its downloaded recovery archive has passed full SHA-256 verification.
- Local source upgrade is capped at 8 CPUs, with no swap. The memory cap was
  32 GiB at first and 96 GiB from the 17:59 resume until the 19:26 failure.
  The driver interrupts a conversion if local free disk falls below 150 GB.

## Qualified build and command sequence

Native Erigon and integration commit:
`372df0e68f52f9975370bff38dee6e41aefff0d7`.

Upstream `TestConvertCommitmentFiles_V3*` and
`TestRestoreCommitmentFiles_V3*` fixtures passed. Initial preflight found missing
`CommitmentBinHistoryKeys` tables; the supported `run_migrations` command
resolved this before any commitment conversion. The earlier failed attempt
and its log are retained.

The original driver implementation is `scripts/pbt/upgrade-erigon-v3.py`;
it stopped at stage 6 at 19:26. The current `resume-erigon-v3-boundaries.py`
recovery invokes its stage runner after the reviewed file-selection checks.
The complete sequence is:

1. Preserve the rollback checkpoint.
2. `integration run_migrations`.
3. Record current commitments with `integration commitment print`.
4. `integration commitment convert --squeeze=false`.
5. Move the unsqueeze backup to the evidence directory; retain it there.
6. `integration commitment convert --v3`, without `COMMITMENT_V3=true`.
7. Verify v3 commitments.
8. Restore execution to the original source block using
   `NO_PRUNE=true integration stage_exec --block=24452538 --experimental.commitment-v3`.
9. Verify and record commitments again.

All commands target only the working source, with `--chain=mainnet`.
The no-prune setting preserves retained BALs: the pinned integration command
otherwise invokes execution pruning after batches. Because the live Python
drivers had already loaded their code, `protect-erigon-bal-retention.py`
installed atomic launchers at their integration paths for future children.
The native binaries remain unchanged as `integration.pinned`; SHA-256 and
launcher evidence are recorded in `bal-retention-launcher.json`. Current
unsqueeze processes were not interrupted.
After conversion, `verify-erigon-v3-source.py` starts the pinned native binary
twice in a private network namespace. Both opens must report:

- Hash: `0x0fd7242bab5055dda36f374f352c78cae381daae9b3e8febe895dce35c907591`.
- MPT root: `0xecf809f327549d4a93eeae29252e8f33b0e9f188cba92f0bb43207d4c7a9c9ca`.
- Block: `24,452,538`.

Graceful stops and successful full commitment verification are required before
the controller authorizes upload. A failed stage stops progression.

## Publication

`publish-erigon-v3-source.py` was launched as the controller user service
`pbt-1-v3-source-publication`. It waits for conversion, starts native qualification,
then authorizes scoped multipart PUT URLs. Storage account credentials stay on
the controller. This service is now stopped following the scope correction above.

Planned immutable object key, **not yet published**:

```text
pbt-1/20261020-erigon-v3-source/erigon/24452538/snapshot.tar.zst
```

The archive excludes rollback backups, rebuild intermediates, temporary files,
logs and node secrets. It includes the converted state and `erigondb.toml`.
After multipart completion, the controller reads the entire remote archive
and checks SHA-256 before publishing metadata, startup instructions, source
genesis, conversion evidence and reopen evidence.

The publication controller's `~/.local/state/pbt-1-run/v3-source/status.json`
stopped updating at 15:30 UTC with the service. Live upgrade status is in the
remote `/data/pbt-1/v3-source-upgrade/status.json` and the 15-minute rehearsal
and fleet monitors. Remote logs: `unsqueeze.log` (the pre-recovery attempt is
`before-index-recovery-unsqueeze.log`), followed by `convert-v3.log`.
