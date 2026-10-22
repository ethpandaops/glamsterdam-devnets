# PBT-1 instruction cross-check

Checked 2026-10-20 against:

- [Maria's plan at 95ac0b56](https://github.com/misilva73/pbt-planning/blob/95ac0b56c5ad69ca99d3e3e8e77729d541d7a739/outreach/pbt-mainnet-fork-migration-test-plan.md).
- [CPerezz's PR #12 revision b6069c14](https://github.com/CPerezz/pbt-planning/blob/b6069c1411eb0cf5096eeab5e08976bc55ba3a78/outreach/pbt-mainnet-fork-migration-test-plan.md), still open.
- [Geth disk hotfix #69](https://github.com/CPerezz/go-ethereum/pull/69), merged as `84a12eff96347929ab62b65cfeb1194478445518`.
- [Erigon migration documentation](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/docs/pbt-migration.md) and the exact source built on Erigon-1.

## Finding and operational action

The queued original-image replay was a state-reconstruction prototype, not a
qualified implementation of Maria's capture/export procedure. It omitted the
v3 transition and the documented execution-stage boundary. The preparation
service was stopped and disabled while still waiting for its recovery download,
before creating a client container or opening the restored source. A review
marker also blocks direct invocation. All snapshot downloads continue.

## Comparison

| Requirement | Our state / correction |
| --- | --- |
| N and the post-N replay range | N=24,453,558 preserves 50,400 prepared blocks. The 1,020 preceding blocks reconstruct N; they are not the measured PBT catch-up. |
| Erigon source format | Legacy commitment files were observed. Qualify conversion to v3 before selecting the replay/capture sequence. |
| Exact export pin | Verify the persisted commitment's block, last transaction number, hash and MPT root. An RPC head alone is insufficient. |
| Finality | No live CL finality exists yet. Offline artifacts are provisional until checked against the finalized network. |
| Receiving Erigon workers | Verify the shared pair, convert their own v3 state with `--keep-hex`, then attach. Do not substitute the test-only import command. |
| Activation | Erigon's binary-trie override is set after attach; every client must then use the agreed S before activation. |
| Observation | Seven prepared chain-days do not satisfy Maria's separate two-week dual-tree observation requirement. |
| Other clients | Keep the user-supplied Besu pins. Use the updated Geth online import/self-migration procedure. Verify each client's actual anchor requirements; Geth import needs the finalized header, not historical MPT state at N. |

## Corrected Erigon command sequence to qualify

These are templates for the next qualification, not commands already launched.
Both native binaries are built from `372df0e68f52f9975370bff38dee6e41aefff0d7`.

First inspect and qualify the legacy upgrade on the recoverable working source.
The supported command is:

```sh
env -u COMMITMENT_V3 \
  /data/pbt-1/rehearsal-tools/erigon/build/bin/integration commitment convert \
  --datadir=/data/pbt-1/rehearsal-24453558/erigon \
  --chain=mainnet --v3
```

Do not run this blindly: it requires unsqueezed input and calls `ResetExec`.
Determine file encoding, backup capacity, resulting checkpoint, and the stored
fork configuration first. A flag change alone is not an upgrade.
See [conversion implementation](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/cmd/integration/commands/commitment.go).

After qualifying that transition, follow the documented capture boundary with
the pinned native binary and the fork's isolated Engine configuration:

```sh
STOP_AFTER_BLOCK=24453558 \
  /data/pbt-1/rehearsal-tools/erigon/build/bin/erigon \
  --datadir=/data/pbt-1/rehearsal-24453558/erigon \
  --experimental.commitment-v3 <qualified-fork-and-isolation-options>

COMMITMENT_V3=true NO_PRUNE=true \
  /data/pbt-1/rehearsal-tools/erigon/build/bin/integration stage_exec \
  --datadir=/data/pbt-1/rehearsal-24453558/erigon \
  --chain=mainnet --block=24453558 --experimental.commitment-v3

COMMITMENT_V3=true \
  /data/pbt-1/rehearsal-tools/erigon/build/bin/erigon snapshots export-pbt \
  --datadir=/data/pbt-1/rehearsal-24453558/erigon \
  --chain=mainnet \
  --out=/data/pbt-1/artifacts-24453558 \
  --experimental.bin-commitment.hash=blake3
```

The Engine replay driver must expect the intentional stop while submitting N;
it cannot require the same live-RPC acknowledgement as the old prototype.
`STOP_AFTER_BLOCK` exits before commit; the offline stage persists N. The stage
can return without work if execution is already at its target, so appending it
after arbitrary replay is not a demonstrated substitute.
See [serial stop implementation](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/execution/stagedsync/exec3_serial.go)
and [stage implementation](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/cmd/integration/commands/stages.go).

Export has no arbitrary block selector: inspect its metadata and reject anything
other than the agreed N. The source also recognizes legacy checkpoint records;
this audit does not claim all legacy exports are impossible. The missing proof
is that our complete source-upgrade/export/dual-tree path works at N.
See [export pin checks](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/cmd/utils/app/export_pin.go).

### Export acceptance and independent verification

The pinned native `snapshots export-pbt --help` and `snapshots verify-pbt
--help` were inspected on Erigon-1. After the stopped exporter has passed both
opens at N, use a new, empty output directory: the export implementation can
overwrite existing artifacts. It produces `pbt-snapshot.bin`, `framed.bin` and
`pbt-snapshot.meta.json`. Require the metadata to name:

- `block`: `24453558`.
- `blockHash`: `0x331c54fd1b37302697157dec30d2a1e0a13682843301f60d8ebac004f8bc4155`.
- `stateRoot`: `0x90fe96f02a1d1009e48ccfb82d15bdf5aa130907acd6c4ebe2f2624e5a911260`.
- `hashSuite`: `blake3`.

Record `txNum`, `pbtRoot`, record counts, native digests and separate SHA-256
checksums of the complete files. BLAKE3 names the PBT hash suite; do not assume
the artifact metadata digests are BLAKE3 file checksums. In this revision the
preimage file digest is Keccak. Preserve the reported `finalized` value, but
do not treat the isolated exporter's forkchoice as shadowfork finality.

Run this independent native verification before distributing the pair:

```sh
env -u STOP_AFTER_BLOCK COMMITMENT_V3=true \
  /data/pbt-1/rehearsal-tools/erigon/build/bin/erigon snapshots verify-pbt \
  --datadir=/data/pbt-1/rehearsal-24453558/erigon \
  --snapshot=/data/pbt-1/artifacts-24453558/pbt-snapshot.bin \
  --preimages=/data/pbt-1/artifacts-24453558/framed.bin \
  --block=24453558 \
  --tmpdir=/data/pbt-1/artifacts-24453558/verify-tmp
```

The command reconstructs and checks the canonical MPT state against the anchor
header. Exit 0 is required; 1 means rejected artifacts and 2 means another
error. Export and verification need separate free-space checks for their scratch
work. Neither command has run on the full PBT-1 state yet. Cross-client import
acceptance and finalized-anchor acceptance remain additional gates.

The staged `/data/pbt-1/export-erigon-anchor.py` implements this handoff without
reimplementing either native operation. Run it without arguments to check
readiness; use `--run` only after the completed anchor proof is reviewed. It
refuses an existing output or evidence directory and does not retry automatically.
Evidence lives in `/data/pbt-1/pbt-export-24453558`; native logs are `export.log`
and `verify.log`. The initial disk requirement is 450 GB, with a 150 GB reserve
during each command. Use the existing VM with an 8-CPU/32-GiB systemd limit and
private networking; this offline artifact preparation is outside the measured
worker migration. No export job is queued at this checkpoint.

## Live command and queued-boundary review, 18:41 UTC

The running legacy-to-v3 commands were checked against the pinned implementation.
Both processes execute the expected native binary SHA-256
`c55a62b6ef462020fdf825872ac1c8badf34c1e44af33ac17a7115c6e0290e03`,
with `GOMAXPROCS=8` and `COMMITMENT_V3` unset during conversion.
The resumed exporter unsqueeze used the same squeeze/key-encoding options and
completed successfully. Subsequent verification enables `COMMITMENT_V3=true`;
tail reconstruction additionally disables pruning to retain BALs. These are
MPT format preparation steps; neither performs the measured PBT conversion.

Review found that the still-held anchor preparation script had not implemented
the intentional stop described above. It replayed through N with normal RPC
acknowledgements and then invoked `stage_exec`, which could do no work. This
script had not started.

The corrected script is now staged on Erigon-1, with the review hold retained:

1. Start the isolated exporter with `STOP_AFTER_BLOCK=24453558`.
2. Replay the verified prefix normally through N-1, then submit N.
3. Require exit code 0, no OOM, and the exact pre-commit stop marker naming N.
   An RPC disconnect alone is not accepted as success.
4. Run the offline stage at N with `COMMITMENT_V3=true`, `NO_PRUNE=true`, and
   `STOP_AFTER_BLOCK` removed from its environment.
5. Open and cleanly stop the node twice, checking N's hash/root and payload body
   on each open, before permitting export.

Ten focused anchor tests passed, including rejecting a crash, a stop at the wrong
block, and an invalid payload. This qualifies the driver checks only; the full
state run remains pending. The pinned parallel executor also implements this
stop hook, so the procedure does not depend on serial execution of Amsterdam
blocks. See [parallel stop implementation](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/execution/stagedsync/exec3_parallel.go).

## Engine capture correction, 23:24 UTC

The full-state run exposed a difference from the planned capture sequence.
The native node produced the expected clean `STOP_AFTER_BLOCK=N` marker, but
the exit occurred inside Engine fork validation. The transaction containing
N's header and body was also rolled back. A native stage report showed Headers,
Bodies, Senders and Execution all at 24,453,557. `stage_exec --block=24453558`
then repeatedly attempted execution without progress: the execution stage caps
its target at Senders. It was interrupted gracefully; the subsequent exact-N
audit correctly rejected the N-1 head. No export proof was produced.

The recovery uses only the pinned native client/integration binaries:

1. Preserve the original stopped container, stop marker, failed stage logs and
   stage report. Check the unchanged recorded payload and N-1 header.
2. Open an isolated replacement container without `STOP_AFTER_BLOCK`, submit
   exactly N through Engine, require its expected hash/root/BAL body, then stop.
3. Confirm all four native stages are at N. Run `stage_exec --unwind=1` and
   require Execution=N-1 while Headers/Bodies/Senders remain N.
4. Run `stage_exec --block=N`, require all four stages at N, then perform the
   two exact-N clean-open checks before export. Both offline commands set
   `COMMITMENT_V3=true`, `NO_PRUNE=true`, `NO_BACKGROUND_E3_BUILD=true` and
   remove both spellings of the stop environment variable.

This retains actual offline execution of N; it does not count a no-op stage
command as the requested capture. The recovery passed at 23:24 UTC: native re-execution logged one committed block
at N, and both subsequent opens matched its expected header and BAL body.
The shared native export started at 23:25 UTC.
The implementation is `scripts/pbt/recover-erigon-anchor.py`; its stage-position,
isolation and environment guards passed three focused tests. No G or S is set.

## CPerezz update applied

The Geth pin is `84a12eff9`; the build is verified and all three workers have
passed isolated startup checks. Full migration qualification remains outstanding.
The runbook requires independent disposable artifact
copies for default consuming imports, fresh copies for retries after consumption,
and retention of emptied paths after success. Never hardlink writable inputs to
the masters. `--pbt.import.keep-artifacts` is the alternative when preserving inputs
is preferred and the disk budget permits it. Native `.tar.zst` recovery archives
remain separate from these PBT inputs.
