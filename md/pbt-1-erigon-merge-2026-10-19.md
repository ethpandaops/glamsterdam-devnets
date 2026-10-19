# PBT-1 Erigon shutdown and merge tuning — 2026-10-19

Erigon v3.7.1 replay slowed from approximately 1.5 to 1.28 blocks/s while a
background state-file merge accumulated work. The 8-vCPU source VM had spare
CPU and memory. At 16:20 UTC replay was paused to raise `COMPRESS_WORKERS`
and `MERGE_WORKERS` from one to two, preserving the pinned image and workload.

## Shutdown failure

After SIGTERM, RPC endpoints closed but shutdown stalled with no CPU or file-write
progress. At 16:24 UTC, SIGQUIT captured the goroutine dump and terminated the
process with exit code 2. This intermediate shutdown was **not clean**. The tuning
job correctly rejected that exit rather than accepting it as restart evidence.

The dump identifies a channel send in `db/seg.(*Compressor).advanceScan`
(`compress.go:279`), called by `AddWord` during a domain merge. Other goroutines
wait in the merge group and `Ethereum.Stop`. In the pinned source, pattern workers
can exit on context cancellation while `advanceScan` sends unconditionally to
their channel. This explains the observed cancellation deadlock.

## Verified recovery

At 16:25:52 UTC the same image reopened at exactly **24,459,075**. Before/after
commitments matched:

- Block hash: `0x9d79a221d0bc2f800bc8295926f9b923d3342bc478f6b7a30c5d5bf429da410b`
- State root: `0xcf2cf5410c2d4f052c172ce63ec85d5532e5d8822da8c6a77edf7aca69f8eee2`
- BAL hash: `0xb13fc772392e68eba0de2a3fcdc97dad4e493e9f9a47a47cd725f6cb510ffc2d`

The oldest generated BAL, first qualifying BAL and a recent BAL were retrieved
and compared byte-for-byte with saved records. Replay resumed with both worker
counts set to two; the startup log confirms those settings. Throughput impact
remains under observation, since restarting also restarts unfinished merging.

## Final snapshot gate

`scripts/pbt/erigon_idle.py` uses Erigon's supported SIGUSR1 goroutine profile to
wait for merge/compression work to finish before SIGTERM. It requires two idle
profiles, records the evidence, and refuses to send SIGTERM if work remains
after two hours. Both clean stops in the final restart audit use this check.
The live probe detected the active merger correctly. The final clean-stop/reopen
gate is still pending; the recovery above does not satisfy it.

No source release was modified. The stopped original container remains as
`pbt-1-erigon-execution-before-merge-tuning`. Host evidence:

- `/data/pbt-1/pipeline/merge-tuning-before.json`
- `/data/pbt-1/pipeline/merge-shutdown-stack.log`
- `/data/pbt-1/pipeline/merge-tuning-recovery.json`

Controller copies are retained under `~/.local/state/pbt-1-run/` as
`erigon-merge-recovery.json` and `erigon-merge-shutdown-stack.log`.

## Fork-choice response handling

A bounded batching probe on the same immutable payload stream exposed another
runner issue: Erigon can return `SYNCING` from fork choice while its asynchronous
commit is still in progress. The driver now retries that response until `VALID`
with the expected hash; `INVALID` remains fatal. Canonical hash, state root and
BAL hash checks still follow.

The successful probe covered blocks 24,459,446–24,459,485. Every header and BAL
body matched the saved records. Eight ordinary blocks took 10.71 seconds before
body auditing; 32 blocks in batches of eight took 55.15 seconds including header
and body audits and seven single-block fallbacks. These timings are not an
isolated benchmark of fork-choice overhead, and did not justify adopting batching.
Ordinary replay resumed automatically at 16:36:26 UTC. The full probe record is
`/data/pbt-1/pipeline/batch-probe.json`, with a controller copy at
`~/.local/state/pbt-1-run/erigon-batch-probe.json`.

A later review of the pinned v3.7.1 source supports retaining the single-block
path. `execution/execmodule/exec_module.go:ValidateChain` clears the previous
validation state and creates a new validation context. In
`execution/execmodule/fork_validator.go:ValidatePayload`, a noncanonical parent
causes the uncommitted ancestor chain to be collected and passed to the executor
again. Delaying fork choice can therefore add repeated execution, rather than
simply amortizing commit overhead. `SYNCING` can also be returned by the Engine
readiness check before a payload is inserted, so accepting it as proof that a
whole batch was queued would be incorrect. No further batching change was applied.

## Live heap-size trial

At 17:34–17:40 UTC, a runtime-only probe sampled two minutes at the original
GC target of 100, then four minutes at 50 through `debug_setGCPercent`. It
restored 100 at 17:40:21 UTC. The execution container and replay process stayed
running; every sampled head's hash, state root and BAL commitment matched the
archived record. No database settings or client image changed.

Observed rates were 0.592 blocks/s before and 0.692 blocks/s during the trial.
Mean sampled heap allocation decreased from 16.02 to 14.75 GiB; mean file cache
increased from 30.77 to 34.51 GiB. GC's cumulative CPU fraction remained below
0.253%. The temporary commitment merge file also completed processing during
this interval, so these sequential samples do not establish a GC-related speedup.
The default GC target remains in use. Evidence and restoration confirmation are
`gc-probe.json` and `gc-probe-restored.json` in the VM pipeline directory and the
controller's `~/.local/state/pbt-1-run/` directory.

The 17:15–17:30 monitoring interval advanced 667 blocks (0.741 blocks/s).
Holding that rate constant projects replay alone to 2026-10-20 09:09 UTC,
excluding restart validation, exhaustive BAL retrieval, compression and upload.
The 09:00 delivery deadline was therefore reported as unlikely at that rate.
Future merge completion can change throughput; the complete 50,400-block target
and all final publication gates remain required.

## BAL retrieval cost and native retention

At 18:51 UTC, 16 older qualifying BALs took **20.10 seconds** through
`engine_getPayloadBodiesByRangeV2`; a range 128 blocks behind the head took
**11.81 seconds**. All bytes, transactions and withdrawals matched their saved
records. This exposed a potentially many-hour final audit: the pinned client
prunes sidecars behind the finalized head and regenerates them by replaying
historical state. Evidence is `~/.local/state/pbt-1-run/erigon-bal-range-throughput.json`.

A read-only native preflight against blocks 24,453,559–24,453,622 verified all
64 canonical header/state/BAL commitments and confirmed that all 64 sidecars
were absent from native storage. It wrote no data. The utility uses Erigon
v3.7.1's `rawdb.WriteBlockAccessListBytes`, whose secondary-storage use includes
backfill. Native MDBX tests cover corrupt inputs, conflicts, noncanonical records,
wrong heads, dry runs, idempotence and persistence across an exclusive reopen.

The final restart sequence now restores the validated sidecars only after clean
shutdown, using an exclusive database open and bounded durable transactions.
The complete input range is checked before the first write, and existing
conflicting bytes cause failure. The same pinned image then starts with
`--exec.no-prune=true` so the cache is retained. The mandatory exhaustive Engine
API audit verifies all bodies/BALs after restart, followed by another clean stop.
Publication records the backfill explicitly and includes its build provenance.
This final production backfill/restart/API gate remains pending while replay runs.

## Live memory-limit probe

At 19:16–19:22 UTC, a reversible live probe compared the existing 48 GiB
container limit for 120 seconds against 56 GiB for 240 seconds. The execution
PID and replay process remained unchanged, and the background merge continued.
Replay advanced at 0.5833 versus 0.5917 blocks/second, respectively (about 1.4%).
Average file-cache residency changed from 15.98 to 16.37 GiB; file-cache refaults
changed from about 9,002 to 8,685 pages/second. There were no OOM events.

This short, sequential comparison does not establish a useful speedup, especially
with the merge still progressing. The probe restored the original 48 GiB limit
at 19:22:34 UTC; Docker inspection verified that limit and the unchanged live
execution PID. The saved startup command remains consistent with the container.
Evidence is `~/.local/state/pbt-1-run/memory-probe.json`; the probe did not change
workload targets, replay validation, database contents outside normal execution,
or the final snapshot gates.

## Merge backlog and bounded preparation profile

The code-compression pass for range 1,049,600–1,050,624 reached EOF at about
19:51 UTC. Its final code segment and indexes were created, but the client
immediately began range 1,050,624–1,051,648. That range contained 14,342 domain
files totaling 21,079,793,905 bytes. Completion of one compression pass therefore
did not mean that background maintenance was finished. Evidence is
`~/.local/state/pbt-1-run/merge-range-transition.json`.

At 19:57 UTC, `suppress-erigon-maintenance.py` stopped only the replay driver,
checked the canonical head and four historical/current BAL samples, and paused
the container while creating a local checkpoint. Mutable files were copied to
separate inodes, including a SHA-256-verified copy of `chaindata/mdbx.dat`;
completed immutable snapshot files were hard-linked. The checkpoint contains
179,485 files, 497,051,488,017 bytes of linked immutable data and 18,003,076,119
bytes of copied mutable data. A read-only native open verified its canonical
head and state/BAL commitments. The original container was then unpaused.

Normal SIGTERM shutdown completed at 19:59:34 UTC with **exit code 0**. No SIGQUIT
or forced recovery was needed. The same pinned image reopened with
`--exec.no-background-maintenance=true --exec.no-prune=true`, retaining the
48 GiB memory limit, network isolation and existing database. Head 24,468,025,
hash `0x28573936f78bbd655b0487f59cb5c59874197a81c79e05aed09d4e0989d36082`,
state root `0x0037ffe36558ce8f8dc49a34b1819a1c9029ce7eb6e38345b3807c5842cd52b4`,
and all four sampled BALs matched before and after restart. Replay resumed at
20:00:31 UTC. A subsequent goroutine profile showed no active merge/compressor.

This is a bounded preparation profile: state remains in the native database
without background aggregation or pruning, so disk growth must be monitored.
The snapshot startup command and `_snapshot_maintenance_restart.json` disclose
the profile and transition evidence. All final clean-restart, exhaustive BAL
audit and upload gates remain required. The local checkpoint is retained outside
the exported datadir. Suppression does not establish a throughput improvement;
that requires subsequent measurement.

At approximately 20:03 UTC, a 20-second attached syscall trace recorded 84 timed
sync calls totaling 9.774 seconds, including 12 data `msync(MS_SYNC)` calls of
0.749–0.887 seconds each. Replay advanced 11 blocks during tracing. The observer
can affect throughput, so this is evidence of sync cost, not an uncontaminated
rate comparison. No durability setting was changed. Evidence is
`~/.local/state/pbt-1-run/fsync-trace{,-summary}.json` and `fsync-trace.log`.
At head 24,468,158, native chaindata occupied 19,847,458,816 allocated bytes,
with 1,252,372,062,208 bytes free on the host. Growth without background
maintenance/pruning must be tracked before projecting remaining disk needs.

## Sync-policy failure, recovery and isolated reproduction

Native table measurements between heads 24,468,025 and 24,468,232 showed
5,746,946,048 bytes of net growth: about 2.51 GB in `CommitmentVals` and
2.33 GB in `ChangeSets3`. Normal pruning was therefore restored; background
maintenance remains disabled. The final BAL-restoration workflow will disable
pruning again for the final restart and exhaustive BAL audit.

At 20:13 UTC a bounded delayed-flush pilot selected native `MDBX_SAFE_NOSYNC`
through `MDBX_NO_FSYNC=true`. The host-run configuration helper aborted in
`mdbx_env_sync_ex` with a futex error before any pilot blocks ran. At 20:16:25 UTC,
recovery had cleanly stopped that client and reopened the same pinned image
without the delayed-flush environment variable or the no-prune flag. Head
24,468,423, hash
`0xae8cb3a6f831edbd63a0b6a4a359c7b41cecb6b579cd8377eae05cad2f2bb9b6`,
state root
`0xab24f1c094a188aff007e7e9fd941394de432edafc5bc47b947d95ba71ae6529`,
and four sampled BALs matched. Replay resumed with normal durability.
Evidence: `sync-policy-pilot-failure.log`, `sync-policy-recovery-complete.json`
and `sync-policy-recovery-reopened.json` in the controller evidence directory.

An initial disposable namespace test passed but had not exercised contention:
the owner had no previously committed dirty transaction. Strengthening it to
commit data before holding the next writer transaction reproduced a futex
failure with the helper outside the owner's PID namespace. The in-container
helper instead waited about 15 seconds, applied the thresholds, and the owner
read them back and exited 0. A new guard rejects a different PID namespace and
requires the owner to hold the exact database inode before MDBX is opened.
The guarded fixture rejected the host invocation and passed inside the
container at 20:29 UTC. These results justify testing the guarded approach;
they do not establish a successful production pilot or an adopted sync policy.
