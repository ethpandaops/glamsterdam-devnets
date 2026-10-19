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
