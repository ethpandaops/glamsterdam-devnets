# PBT-1 Erigon persistence comparison — 2026-10-19

The four source pipelines remain authoritative. The temporary DigitalOcean
probe was deleted at 22:44 UTC; its evidence is archived on the controller.
Replay continues on the original Erigon VM with validated native batching.
The dated measurements below describe the experiments, including rejected and
canceled variants. Final restart, BAL audit and upload remain required.

## Measured bottleneck and batching result

A 45-second sample on the original Erigon VM advanced 16 blocks (0.356/s),
with 31,870 writes/s, 163.4 MiB/s written, 2.86 ms average write latency and an
average device queue of 91.6. Client CPU usage averaged 1.31 cores; host steal
was 0.43%. Native logs locate most block latency in forkchoice flush/commit.
Evidence: `persistence-io-sample.json` and `persistence-io-summary.json` in
`~/.local/state/pbt-1-run/` and the source VM's pipeline directory.

The bounded `probe-erigon-batch-wait.py` required VALID for every payload before
advancing fork choice at the end of a batch. It waited through temporary
SYNCING responses without issuing intermediate fork choices. All 56 headers,
state/BAL commitments and complete bodies matched their replay records.

| Mode | Blocks | Apply seconds | Blocks/s | Body/header audit seconds |
| --- | ---: | ---: | ---: | ---: |
| Sequential | 8 | 19.454 | 0.411 | 1.082 |
| One batch | 16 | 34.715 | 0.461 | 0.356 |
| One batch | 32 | 133.589 | 0.240 | 0.613 |

Execution logs explain why larger batches did not help: the 16-block case
produced 136 block-execution events, and the 32-block case produced 528. Earlier
blocks were executed repeatedly while validating successive uncanonicalized
payloads. Sequential execution produced eight events for eight blocks.
Batched fork choice was not adopted. Normal sequential replay resumed at
20:52:49 UTC, with normal durability and pruning, and background maintenance
disabled. Evidence: `batch-wait-probe.json` and `batch-wait-execution-counts.json`.

## Temporary VM

- Terraform resource: `digitalocean_droplet.erigon_io_probe`.
- Droplet ID: `610654975`; region: `fra1`.
- Size: `so-32vcpu-256gb`, 32 vCPUs, 256 GiB RAM, 4,800 GB disk.
- Public/private IP: `167.172.181.164` / `10.35.0.6`.
- Observed CPU: Intel Xeon Platinum 8358.
- Catalog price at provisioning: $3.11952/hour; treat this as a temporary cost.
- Provisioning: `ansible/pbt-io-probe.yaml`, isolated `pbt_io_probe` inventory.

The size catalog incorrectly included the Intel-labelled variant in `fra1`;
creation returned HTTP 422. The regional size list excluded that variant but
included the selected standard variant, which provisioned successfully. The
failed request created no Droplet. The new VM reported a busy `resizefs` error
during cloud-init, but inspection proved its root filesystem already covered
the expanded partition. Ansible accepts only that specific completed-boot
condition after checking the filesystem size; other boot failures remain fatal.

An in-place resize was avoided because DigitalOcean documents disk-dependent
downtime, including for CPU/RAM-only changes when a VM moves hypervisors.
[Resize guidance](https://docs.digitalocean.com/products/droplets/how-to/resize/).

The isolated eight-GiB scratch benchmark completed successfully:

| Test | Write IOPS | Write MiB/s |
| --- | ---: | ---: |
| Sequential one-MiB writes | 2,088 | 2,087.7 |
| Direct random four-KiB writes, queue depth 128 | 112,907 | 441.1 |
| Buffered random four-KiB writes, fdatasync every 8,192 writes | 58,280 | 227.7 |

These are capacity measurements on an idle candidate, not a controlled
comparison with Erigon's live workload. The script removed only its own scratch
file after success. Reports remain in `/data/pbt-1/io-probe/`, with copies on the
controller. An actual replay comparison is still required.

## Copy and next gates

At 20:52:45 UTC, `pbt-1-checkpoint-copy.service` began copying the preserved
checkpoint from the original VM at `10.35.0.2`. It contains 179,485 files and
515,054,564,136 logical bytes, at head 24,468,025. The expected MDBX SHA-256 is
`b799a0df4b18dcbd5c662640eca94c6b3913027a43d1375dc8aceb4766c725ce`.
The copy preserves sparse files and hard links, initially used idle IO priority
on the source, and caps transfer at 256 MiB/s. Its status file and live systemd handle
are included in the existing 15-minute monitor. The monitor computes progress
against the full checkpoint size; rsync's incremental file-list percentages
and ETA are not full-transfer estimates.

A bounded IO-priority experiment completed at 21:03:17 UTC and restored idle
priority afterward. Over 45 seconds at idle priority, the copy read 57.49 MiB/s
and canonical replay advanced at 0.333 blocks/s. Over 90 seconds with the copy
sender at best-effort priority 7, it read 214.97 MiB/s while replay advanced at
0.289 blocks/s. At 21:06:18 UTC, best-effort priority 7 was adopted for that
specific, identity-checked rsync sender to shorten the checkpoint transfer.
This changes only the copy process and expires when it exits; client durability
and process priority are unchanged. These short windows indicate a tradeoff,
not a precise long-term replay forecast. Evidence: controller/source pipeline
`checkpoint-copy-priority-probe.json` and `checkpoint-copy-priority-adopted.json`.

The probe holds a temporary SSH key. The original VM accepts it only from
`10.35.0.6`, with a forced read-only `rrsync` command restricted to the checkpoint
directory. The source host key is pinned. The shared administrative private
key remains on the controller. The access entry is labelled
`pbt-1-erigon-checkpoint-probe-20261019` for exact removal after the copy.

The candidate already pulled the same pinned Erigon image. The controller's
`pbt-1-probe-records.service` separately seeds immutable replay records; it does
not block the existing three-consumer relay. Candidate activation remains gated:

1. Require successful copy, exact file count and MDBX SHA-256 match.
2. Revoke the checkpoint-read key and remove its private key from the probe.
3. Open the same pinned client in network isolation with normal durability.
   Verify the checkpoint head/hash/state root and historical/current BAL samples.
4. Measure replay of identical records, validating each block's commitments.
   Keep the original source until the candidate catches up and proves suitable.
5. If promoted, record host-transition provenance and update relay/monitor/upload
   routing together. Preserve all existing final restart, exhaustive BAL audit,
   native sidecar-restoration and immutable publication gates.
6. Remove the temporary VM if it is not useful. Remove its Terraform resources,
   temporary count contribution and controller `erigon-io-probe.json` only when
   the final use/cleanup decision has been executed and verified.

`activate-erigon-probe.py` implements the candidate's bounded activation gate.
It refuses to open before verified copy and revoked-key evidence, rechecks the
MDBX digest, and requires the needed immutable replay records. It starts the
same pinned image with a 224 GiB memory limit, normal durability and pruning,
and background maintenance disabled. The larger memory limit is for source
preparation, not the eventual 16/32 GiB migration measurements. It checks the
exact checkpoint header and historical BAL samples, replays 256 identical
blocks through 24,468,281, verifies every pilot body/commitment, and repeats
those checks after a clean shutdown/reopen. It records timing separately from
the audits and leaves canonical routing unchanged. It does not automatically
retry failed activation or promote the probe.

Controller provisioning/access records are in `erigon-io-probe.json` and
`io-probe-ansible.log`. Copy failures stop for inspection; neither the copy
script nor monitoring automatically restarts failed database work.

## Native profiling and source optimization

The user redirected the investigation toward source profiling and direct Go
builds on the VM. No Panda build was dispatched. The earlier Docker activation
path above remains unused; the next experiment uses native binaries, private
network namespaces, eight allowed CPUs and a 48 GiB memory limit. The larger
VM is now a checkpoint-isolated test environment; no hardware promotion has
been approved by the evidence or performed.

The original source restarted cleanly with the same pinned image, memory,
pruning and normal durability, adding only `MDBX_TRACE_TX=true`. Exact head and
four complete BAL samples matched before/after. Replay resumed with driver PID
148290. The initial trace contains 49 commits; the 16 commits over 100 ms
averaged 2.023 seconds, including 2.021 seconds of native sync and 1.562 ms of
GC. This isolates the wait within those commits, not the entire block latency.
The sample includes startup/cache warming and competing checkpoint-copy IO.
Evidence: `native-profile-complete.json`, `native-profile-shutdown.json` and
`erigon-native-commit-profile.{log,json}` in the controller run directory.

Opt-in `REPLAY_PROFILE=true` instrumentation adds timing boundaries around
forkchoice transaction acquisition, reader release, shared-domain commit,
head notification and the extra durability update; shared-domain flushing,
native commit and cache publication; and temporal changeset/writer flushing.
It changes logging only, not validation or durability. This exploratory logging
change uses existing commit/forkchoice tests rather than new behavior tests.
Both lint passes, `make erigon integration`, and focused commit/forkchoice tests
passed. Source branch: `qu0b/erigon:pbt-1-replay-profile`, commit
`cb002d6581`.

`build-erigon-native.py` cloned upstream tag `v3.7.1` on the probe, verified
commit `8c1e3893d77d230720d172f1492d95b5777a862c`, and built directly with Go
1.26.0, `GOAMD64_VERSION=v2`, and `BUILD_TAGS=nosqlite,noboltdb`:

| Binary | Build seconds | SHA-256 |
| --- | ---: | --- |
| `/data/pbt-1/native/erigon-stock` | 117.04 | `3209fc200fc2e84a9d9748b028037f5fd050c86f700894c9f9c7ffad77b13ec5` |
| `/data/pbt-1/native/erigon-profile` | 64.41 | `aa7cf967d9b6250fde93a7a8f85fe5b049e89dccaf3989bfb01ca1f115242c9c` |

The instrumented binary was built from the pinned revision plus patch SHA-256
`8830903b2c876dee4877be1eb94c5496cab0d35aea61be900caec2cd47c4e0d4`;
the patch is represented by the branch commit above. Its embedded version still
reports the base revision, so use the binary and patch hashes as provenance.
The build manifest is `/data/pbt-1/native/build-report.json` and controller
`erigon-native-build-report.json`. Initial setup failures occurred before cloning
or compiling: the bootstrap Go binary was older and systemd provided no module
cache home. Explicit `GOTOOLCHAIN=go1.26.0`, `GOPATH` and `GOCACHE` fixed these;
the final native build service completed successfully.

`probe-erigon-native.py` is staged for bounded 64–256 block trials. It requires
verified transfer and revoked checkpoint-key evidence, preserves the transferred
checkpoint, copies mutable files into each fresh trial directory, and hardlinks
only immutable snapshot files. Each native client runs under a persistent
systemd unit with private networking and identical CPU/RAM limits. Trials
record CPU profiles and replay timings, then verify every pilot body and
commitment before and after a clean restart. No final upload or canonical-host
transition is performed by the harness.

The first configuration candidate is `--db.writemap=false`, compared on the
same VM and starting checkpoint with normal durability retained. This is a
hypothesis based on the observed sync wait, not an established speedup. No
native replay trial or write-mode optimization has passed yet. The existing
15-minute monitor now also reports native build/trial status and failures.

The controller's `pbt-1-native-probe-preparation.service` is now waiting on the
live copy handle. On successful copy verification it removes only the exact
restricted checkpoint key from the original VM, deletes the corresponding
private/public key files from the probe, saves revocation evidence on both
hosts and the controller, and starts `pbt-1-native-probe-profile.service` for
one 64-block trial. It does not retry failed copy, revocation or trial work.
The monitor reports preparation and trial-job failures, including failures
before a client starts. Trial timing separates the first eight warmup blocks
and records per-block apply durations plus process/device IO counters.

A longer original-source trace collected after 21:20 UTC contained 336 commits,
including 112 over 100 ms. Those slow commits averaged 2.063 seconds, with
2.061 seconds in sync and 1.593 ms in GC. Copy IO still competes with replay;
the result confirms the location of the wait, not uncontended throughput.
Evidence: `erigon-native-commit-steady.{log,json}`. MDBX's pinned source routes
WRITE_MAP commits through `msync` and non-WRITE_MAP commits through its file-sync
path; both preserve normal durability in the planned comparison.

The transfer finished at 21:39:42 UTC. Its count gate stopped because the
checkpoint's earlier read-only native validation had created an empty
`chaindata/mdbx.lck` after the checkpoint manifest was recorded. Source and
destination inventories matched exactly: 179,486 paths and 515,054,564,136
bytes, with no path or size differences. The original manifest excluded lock
files and counted 179,485 files. The empty copied lock was archived outside
the data directory after checking that neither it nor MDBX was open. Database
checksum verification was resumed without retransferring or changing data
files. The original failure and inventory comparison remain recorded. Future
copies explicitly exclude this one lock file.

Native measurements now record log byte offsets around the replay window.
`summarize-erigon-native.py` reports stage timings from that window separately
from startup/restart audits. Nested timings overlap and must not be summed;
device IO covers the whole VM. The existing native batched-insert/forkchoice
tests also passed, but no batch API or replay behavior has been changed.

## Native baseline and batch prototype

The 64-block native profile baseline reached 24,468,089. All replayed bodies,
BALs and commitments matched both before and after a clean restart; the
pristine checkpoint checksum remained unchanged. Excluding the first eight
blocks, replay averaged 0.9993 blocks/second. The first block took 39.65 seconds
to warm up. The measured window wrote about 202.3 MiB per block at the VM's
block device. Shared-domain commit averaged 594 ms: about 188 ms flushing,
391 ms native commit and 16 ms cache publication. These nested measurements
must not be added again to the enclosing forkchoice time. This result uses
the probe hardware and a less advanced checkpoint than the authoritative
source; it is not evidence of a software speedup on the original VM.

The first shutdown check incorrectly required systemd's transient exit fields
to survive unit unloading. The journal recorded successful deactivation, but
those fields had reset to zero. The harness now verifies the journal's
successful-deactivation event for the exact invocation ID and records that
proof. The completed replay was retained, the original reporting failure was
archived, and its restart audit completed successfully. The `profile` trial's
final phase is `verified_stopped`.

The `profile-no-writemap` comparison uses the identical checkpoint, block range,
binary, CPU/RAM limits and durability. A separate native batch build waits on
the benchmark lock until this comparison is fully verified and stopped.

Source commit `a7d50626108b2428d5cd0b65089330fee6b357d8` adds
`testing_insertRawBlocksV1` for isolated replay experiments. It accepts 1–16
contiguous raw blocks extending the current head, with one structurally valid,
hash-matching BAL per block. It decodes and checks the entire input before
insertion. Its returned hashes acknowledge staging only; normal forkchoice
execution must still return VALID. No ordinary Engine API validation behavior
was changed. Admission tests followed a failing-test/implementation cycle;
existing execution tests and an additional intermediate-state-root rejection
check verify the unchanged batch execution path. Lint and both binaries built.

The staged `profile-batch` harness uses eight-block batches, requires VALID
forkchoice and VALID Engine API checks for every block, checks every header
commitment and full body, and repeats the body audit after restart. Raw input
for the 64-block pilot was exported from the canonical Geth source and has a
checksum manifest. Batch timing divides elapsed batch time across its blocks;
those values are not individual block latency. No batch pilot or authoritative
replay transition has run yet.

The write-mode comparison completed its 64 replayed blocks at 0.7894 measured
blocks/second after the eight-block warmup, versus 0.9993 for the baseline:
about 21% lower throughput. Its first block took 37.84 seconds. This option is
rejected for adoption; the original source retains its write mode. Restart
audit and pristine-checkpoint verification remain separate completion gates.
The baseline CPU profile includes the first-block warmup and therefore is not
a steady-replay CPU profile; its snapshot filename/filter work must not be
treated as evidence of the steady-state bottleneck.

Both comparison trials subsequently reached `verified_stopped`, with identical
head/hash/state/BAL commitments at 24,468,089 and matching pristine-checkpoint
checksums. Device writes were 202.29 MiB/block for baseline and 203.59 MiB/block
without WRITE_MAP. Controller evidence: `native-write-mode-comparison.json`.

The batch binary built directly on the probe in 30.97 seconds. Its SHA-256 is
`b1c3fc01aff41318597763c2b5b9c46ee16354995c279000ef4ac4b8db443403`;
the build manifest records source file Git blobs, the base revision and both
patches. Its embedded version still reports the pinned base revision.
`pbt-1-native-probe-profile-batch.service` has started the 64-block private-clone
pilot. No batch performance result or authoritative cutover is established.

## Batch pilot result and next gate

The batch pilot reached `verified_stopped` at 22:03 UTC. All 64 bodies, BALs and
header commitments matched before and after restart; the pristine checkpoint
checksum was unchanged. All three trials end at the same head/hash/state/BAL.

Engine API acknowledgements can precede completion of the final persistence
operation. The original timer ended at that acknowledgement, missing 0.779 s
of final persistence/pruning in baseline, 0.822 s without WRITE_MAP, and 1.993 s
for batching. Exact final `headBefore` and post-forkchoice log timestamps give
corrected measured rates of **0.9856**, **0.7803**, and **1.6350 blocks/second**,
respectively. Batching improves this same-VM comparison by about 66%. Original
timings remain preserved alongside `persistence-timing.json`; millisecond log
timestamps limit the correction's precision. The harness now waits for final
persistence/pruning before stopping its timer and sampling device IO. Earlier
IO counters omit that final tail and are not complete per-block write totals.

This is not yet a result on the authoritative VM. Its MDBX file is now about
48 GiB, larger than the pilot checkpoint, and its observed replay remains
about 0.31 blocks/second. The next gate is a bounded same-hardware comparison
on that VM's current state: preserve a recoverable checkpoint, cleanly stop the
pinned client, run the native binary with the same 48 GiB limit and normal
durability, compare sequential and eight-block replay, verify every pilot
body/commitment, then cleanly reopen with the pinned client and resume the
authoritative run. Any transition to continuous native batch replay requires
those results, native-runtime monitoring and final pinned-client reopen
provenance. No authoritative client transition has occurred yet.

## Original-VM comparison completed at 22:26 UTC

The source VM preserved a separately copied mutable checkpoint at 24,470,563,
verified its MDBX SHA-256 and checked its head/root with the native read-only
helper. It then ran the native batch binary with the original eight CPUs,
48 GiB memory limit and normal durability:

| Mode | Range | Measured blocks after warmup | Blocks/second |
| --- | --- | ---: | ---: |
| Sequential | 24,470,564–24,470,627 | 56 | 0.272274 |
| Batch of eight | 24,470,628–24,470,755 | 120 | 0.554971 |

Both timings include final persistence and pruning. The batch result is 2.0383×
the sequential result. These are consecutive ranges on advancing state, not
identical starting databases. All 192 new bodies and commitments were checked,
then the native client stopped cleanly and the pinned Docker image reopened with
the same head, state root and BALs. Normal replay resumed. Controller evidence:
`native-source-pilot-complete.json`; remote evidence:
`/data/pbt-1/native-source-pilot/`.

Eight-block commits on the original VM still spent roughly 4–8.5 seconds in
native MDBX synchronization, plus about 2.6–3.2 seconds flushing state and
execution time. This remains the main measured reason to test larger batches.

## Larger-batch work at 22:33 UTC

The probe's 16-block trial passed all 64 body/commitment checks after a clean
restart. It measured 1.85093 blocks/second over 48 blocks after excluding its
first full 16-block batch and including final persistence. The earlier eight-block
trial used an eight-block warmup; do not treat their published rates as a matched
measurement window. An externally launched steady CPU capture was interrupted
by shutdown and is unusable; it is not performance evidence.

Source commit `72b4a99bbb46a61ce3ab0932111533da8cb9fcda` adds
`testing_insertRawBlocksV2`: requests still contain at most 16 blocks, but can
extend already staged descendants within 128 blocks of the current canonical
head. It checks the ancestry before admission. This keeps requests under the
HTTP body limit while allowing one normal forkchoice execution for a longer
chain. Execution, intermediate-root validation, payload validation and durability
remain enabled. Tests first failed for the missing endpoint and then for missing
ancestry/distance guards; both cycles passed after implementation. Existing batch
execution/bad-block/intermediate-root tests, `make lint` and
`make erigon integration` passed.

The direct VM build took 29.64 seconds after correcting the build service's Go
PATH. The failed launch log is preserved as `build-continuation-path-failure.log`.
Binary SHA-256: `f5feda744e0db70f49fc1ddf9bbc02cfcdd0bbabbb78fb8b07f0ab47b7f5e475`.
The 256-block, batch-of-64 trial is running on a private checkpoint clone;
no source VM uses this new binary yet. Its CPU profile begins after the warmup
batch, and the harness waits for profiling before shutdown.

The remaining raw-block stream starts at 24,470,756. Export and hash-checked
transfer are running. The continuous native driver and publication/monitoring
support are prepared but activation awaits the selected probe's completed
validation. Four driver failure-path tests pass. Final snapshots and the replay
bundle are still unpublished; the morning deadline remains at risk.

The batch-of-64 trial completed 256 blocks at 22:37 UTC. Its 192-block measured
window after a 64-block warmup averaged **1.68506 blocks/second**, including final
persistence. This does not establish an improvement over the shorter batch-of-16
trial. The internal 512 MiB execution limit caused additional commits within
each 64-block request. A follow-up variant keeps the same 256 blocks, batch size,
binary and 48 GiB process limit, changing only `--batchSize=2G`.

The valid 20-second CPU profile started after the warmup batch. Snapshot-file
existence-filter lookup (`ReaderSharded.ContainsHash`) accounted for 53.21% of
sampled CPU cumulatively; `DomainRoTx.lookupLatestFromFiles` accounted for 64.67%.
These CPU fractions overlap and do not measure time blocked on disk sync. No
filter-cache change has been made. Controller evidence is under
`native-profile-batch64/` and `native-profile-batch64-summary.json`.

## Probe retired at 22:44 UTC

At the user's request, the temporary 32-vCPU, 256-GiB probe was deleted.
DigitalOcean returns HTTP 404 for droplet `610654975` (`167.172.181.164`).
Terraform removed the droplet and its project association; the subsequent full
plan contained only output changes. The saved server count is now four.
The active probe monitoring entry was retired, and its temporary source SSH key
was confirmed absent.

Before deletion, 123 build, benchmark, log and profile evidence files were saved
in the controller's `retired-probe-evidence.tar.gz` (4,164,423 bytes), with SHA-256
`ae5aa42077c690b94a667d76d2436814a7517773c4969626862eaa6cd58461ab`.
The source commits and native binaries are also preserved. The batch-of-64,
2-GiB-buffer experiment was canceled for cleanup and was not adopted. Its
disposable database was removed with the VM.

Authoritative replay remains on the original Erigon VM, `164.92.239.96`.
The continuous native driver started at 22:43:58 UTC with the validated
`a7d50626108b2428d5cd0b65089330fee6b357d8` build, batches of 16, the default
512-MiB execution buffer, eight CPUs, a 48-GiB process limit and normal
durability. At 22:46:38 it had validated 48 additional blocks and reached
24,471,106. The initial cumulative rate was 0.534 blocks/second; this short
startup window is not a reliable completion forecast. Final pinned-image
restart, exhaustive BAL audit and publication gates remain required.

## Original-VM profiling and writeback trial at 22:57 UTC

A 20-second CPU capture on the live original VM collected 42.93 CPU-seconds.
Snapshot-file lookup accounted for 67.37% cumulatively; sharded existence-filter
checks accounted for 55.72%. These overlapping CPU samples do not include time
blocked on storage. Native timing logs separately measured approximately
4–5 seconds flushing state and 9 seconds in MDBX synchronization per batch of 16.
The profile and summaries are preserved as `steady-original-cpu.pprof` and
`steady-original-cpu-{flat,cumulative}.txt` on the controller.

`probe-erigon-writeback.py` compared earlier kernel background writeback while
the same native process and validated replay continued. It changed only
`vm.dirty_background_bytes` to 64 MiB for three minutes, then restored the
original ratio of 10% and byte setting of zero. Database durability remained
normal throughout; the client PID remained `164768`.

| Window | Seconds | Validated blocks advanced | Blocks/second |
| --- | ---: | ---: | ---: |
| Original setting | 120.02 | 96 | 0.79987 |
| Earlier writeback | 180.02 | 144 | 0.79989 |
| Original setting restored | 120.03 | 80 | 0.66652 |

Mean sampled dirty memory fell from 852 to 520 MiB during the trial, but the
replay rate matched the initial baseline. These short windows use consecutive
blocks and vary with batch boundaries and storage timing; no useful speedup was
established. The tuning was not adopted. The service exited successfully at
22:56:49 UTC and restoration was independently checked through `sysctl`.
Evidence: `writeback-probe.json` and `writeback-probe-summary.json` on the controller.

Geth finished generation at 22:57:10 UTC: head 24,503,958 and exactly 50,400
qualifying blocks. Raw export completed at 22:57:19 UTC with 33,203 blocks covering
24,470,756–24,503,958. Geth then entered its final restart/BAL gate. Erigon was at
24,471,570 (18,012 qualifying blocks) at 22:56:58 UTC; its observed rate still
puts full delivery beyond the 09:00 target. Replay, final audits and uploads
remain incomplete; generation completion is not snapshot completion.

## Original-VM batch-of-64 handoff at 23:05 UTC

The native batch-of-16 segment covered 24,471,059–24,471,794: 736 validated
blocks. `handoff-erigon-native.py` stopped its driver, required a completed
post-forkchoice persistence record, rechecked every segment header and the last
16 full bodies, and cleanly stopped the native client. There was no unreported
payload tail. The pinned Docker image reopened with exactly the same head and
body. All segment evidence is retained under
`/data/pbt-1/native-replay-segments/0001/`; final publication now checks continuity
and includes earlier segments and their build manifests.

The first replacement-driver launch failed before touching the database because
systemd had collected the old `pbt-1-full-run` transient service. The driver now
accepts that specific missing-service case while retaining fatal handling for a
failed stop of an existing service. Regression tests first failed and then passed.
The failed start was archived under `native-replay-failed-starts/0001/` after
confirming that the pinned head was unchanged and no blocks had been replayed.

At 23:05:07 UTC, the corrected driver started the previously probe-verified
continuation build (`72b4a99bbb46a61ce3ab0932111533da8cb9fcda`) on the original VM.
It uses batches of 64, the default 512-MiB execution buffer, normal durability,
eight CPUs and the same 48-GiB process limit. The canceled 2-GiB-buffer experiment
has not been adopted. Original-VM performance of this configuration remains to
be measured. Eleven driver/handoff checks pass, covering validation gaps,
incorrect commitments/bodies, invalid payloads, persistence fencing and the
missing-service regression. Final pinned-image reopen and exhaustive BAL checks
remain required after the entire replay.

By 23:11:51 UTC, the batch-of-64 driver had validated 256 more blocks and reached
24,472,050. Its startup-inclusive rate was 0.689 blocks/second. Individual later
64-block intervals took approximately 83–92 seconds; this is only a small gain
over the preceding batch-of-16 segment's final 256-block persistence-inclusive
window (380.751 seconds, 0.672 blocks/second). The 512-MiB buffer still forces
intermediate commits near 31 blocks. A larger buffer remains an unvalidated
candidate for a bounded original-VM trial; no such setting has been adopted.

At 23:11:45 UTC, Nethermind completed its final restart and exhaustive audit:
51,420 bodies, 50,400 qualifying blocks, 22,832,500,199 BAL bytes and a minimum
qualifying BAL size of 450,865 bytes. Average qualifying execution/state gas was
100,078,541.73 / 99,976,320. Its final clean stop passed. The multipart upload
started by 23:12:22 UTC under
`pbt-1/20261019-mixed-8037-v2/nethermind/24503958/snapshot.tar.zst`, with its first
256-MiB part acknowledged. This does not establish upload completion. The
Patricia directory is excluded; Geth/Besu audits and Erigon replay remain active.

## Bounded original-VM buffer pilot at 23:18 UTC

The default-buffer batch-of-64 segment ended at 24,472,242 after 448 validated
blocks. The handoff checked all segment headers, the last 16 bodies and clean
shutdown, then verified the same pinned-image head/body. It is preserved under
`native-replay-segments/0002/`. Its final 192 blocks took 242.463 seconds between
post-forkchoice persistence events: 0.79187 blocks/second. This is the baseline
for the next trial, with evidence in controller `buffer-pilot-baseline.json`.

At 23:18:04 UTC, `pilot-erigon-buffer.py` started on the original VM. It advances
24,472,243–24,472,498 using the same continuation build, batches of 64 and a
2-GiB execution buffer. CPU allocation, memory limit, durability and pruning are
unchanged. The first 64 blocks and their persistence are excluded from the
measured window; final persistence is included. The complete 256-block range
must pass header/body checks before shutdown and after pinned-image reopen.
Only that evidence can qualify the buffer for the remaining full replay.

Sixteen Python driver/handoff/pilot checks pass, including a regression that
first rejected a bounded prefix of the full raw stream, warmup persistence,
wrong older BALs and wrong intermediate roots. Monitoring follows the live
pilot service/client, and publication retains successful pilot evidence in the
native segment history. The pilot result is pending.

The initial pilot rejected its first staging request: the execution module's
`CurrentHeader` uses `ReadHeadHeaderHash`, whereas RPC `latest` still reported the
last forkchoice head. Sixty-four blocks previously staged by the interrupted
driver were ahead of that forkchoice head. The guard correctly refused insertion
below its current header; it was not loosened. The failure occurred before any
pilot batch completed, and its log is retained as `staging-guard-failure.log`.

All 64 stored headers and complete bodies/BALs were then retrieved by hash and
matched to the immutable input records, with the RPC head unchanged. A first
recovery through ordinary forkchoice returned VALID but did not update RPC
`latest`; the driver's exact-head assertion caught this and stopped. Source
inspection found that the duplicate-FCU path writes forkchoice metadata into an
overlay and returns before the normal flush/publish path. This is evidence of a
head disagreement, not a successful replay. The second failure is retained as
`duplicate-forkchoice-head-failure.log`.

At 23:25 UTC, inspected recovery resumed on the same native PID. Its first batch
combines the verified 64-block stored prefix with 64 newly staged blocks, then
uses normal forward forkchoice, ordinary VALID checks and all header checks.
The staging guard is unchanged. The first 128 blocks and their persistence are
warmup; only the final 128 of the unchanged 256-block pilot are measured. The
complete pilot still requires both full body audits and a pinned-image reopen.
Seventeen tests pass, including the stored-prefix forward-execution regression.
No failed trial has been accepted as qualification evidence.

Geth's final restart/body gate passed at 23:18:22 UTC and Besu's at 23:22:17 UTC.
Both verified all 51,420 bodies and 50,400 qualifying blocks before clean stop.
All three completed clients are now uploading under the immutable release
prefix. The replay bundle remains gated on all four verified native uploads.
