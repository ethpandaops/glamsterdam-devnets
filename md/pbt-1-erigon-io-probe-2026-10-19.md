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

## Original-VM buffer qualification and adoption at 23:30 UTC

The recovered pilot completed at head 24,472,498. All 256 headers and complete
bodies/BALs matched the immutable inputs both before native shutdown and after
reopening the pinned image. Native shutdown was clean, normal durability was
retained, and the successful range is sealed as `native-replay-segments/0003/`.
The two rejected attempts remain in the pilot evidence; neither was counted as
a successful batch. Controller evidence is archived in
`native-buffer-pilot-evidence.tar.gz`.

After excluding the 128-block recovery warmup and its persistence, the remaining
128 blocks took 117.051 seconds including final persistence: 1.09354 blocks/s.
The preceding default-buffer segment's last 128 blocks took 160.475 seconds:
0.79763 blocks/s. The rate ratio is 1.371. These are different sequential block
windows, so this is an operational comparison, not a controlled same-input
benchmark. `buffer-pilot-comparison.json` records that limitation explicitly.

At 23:30:32 UTC the full replay service started with the qualified 2-GiB buffer,
batches of 64 and the same continuation binary on the original eight-CPU VM.
The process limit remains 48 GiB, with normal durability and ordinary per-block
VALID/header checks. The remaining range is 24,472,499–24,503,958: 31,460 blocks.
At the pilot's measured rate, replay alone requires roughly eight hours;
final BAL restoration/audit and archive upload follow, so delivery by 09:00 UTC
remains at risk. Sustained replay throughput must be measured separately.

The 23:30 monitor reported no alerts. Geth, Besu and Nethermind uploads are live;
their final restart proofs each cover 51,420 bodies and 50,400 qualifying blocks,
with identical final block hash, state root and BAL hash. This cross-client
comparison is recorded in controller `three-client-final-audits.json`. Upload
completion and remote verification remain outstanding.

## Continued replay profiling at 23:34 UTC

The same native PID (173387) continued without a restart. A 30.02-second CPU
profile collected 54.04 CPU-seconds. `DomainRoTx.getLatestFromFiles` accounted
for 53.85% of sampled CPU cumulatively; binary-fuse filter membership checks
accounted for 37.27%. These percentages overlap and describe CPU samples, not
wall-clock attribution. Source inspection shows the latest-value lookup walks
snapshot files newest first and tests each file's existence filter. This makes
file lookup a concrete optimization candidate; no cache or lookup semantics
were changed in this measurement.

The first two completed 64-block batches spent 23.07/24.86 seconds executing
and 30.67/31.02 seconds in the main shared-domain flush/commit. The latter
included 13.79/18.39 seconds flushing and 16.69/12.44 seconds committing.
Pruning took roughly two additional seconds per batch. These nested timings
must not be added twice. Normal durability remains enabled.

Controller `original-2g-steady.cpu.pprof`, `original-2g-steady-top.txt`, the
before/after process samples and `original-2g-steady-summary.json` preserve the
measurement. The summary measures throughput between completed persistence
events, excludes the first batch, and labels its ETA as replay-only. Short
window variability and profiling overhead limit the estimate; the final full
BAL audit and upload remain necessary before delivery.

## Final BAL restoration decoding at 23:52 UTC

A read-only preflight on 1,008 qualifying records (24,453,559–24,454,566)
took 48.082 seconds with the serial backfill helper, a one-CPU quota and nice 19.
It verified 457,128,186 BAL bytes, found 1,008 missing sidecars and wrote none.
The measured CPU time was 47.078 seconds. Linear extrapolation to both input
passes over 51,420 records is approximately 82 minutes before durable writes;
this exposed additional deadline risk beyond replay throughput.

The helper now decodes records with four workers in batches of at most 128.
Database reads, canonical checks and writes remain serial and ordered. Full
preflight still precedes every production write. The write pass starts a fresh
decoder and checks every record digest again. Ten native tests pass under the
race detector, including corruption after the first batch, mutation between
passes, and persistence/idempotence across a 130-record native reopen.

On the same VM and same 1,008 records, the candidate took 15.355 seconds with a
four-CPU quota and nice 19: 3.131 times faster in wall time. This deliberately
uses more of the existing VM's CPUs, with no new machine. CPU time was 50.778
seconds; peak process RSS was approximately 184 MiB (the service's memory
accounting including file cache peaked near 1 GiB). Both runs produced the same
record-digest hash and all counts matched, with zero writes. The shorter run's
linear estimate is approximately 26 minutes for both input passes, excluding
write costs, restart, exhaustive API audit and upload. It is not a full-range
benchmark or a delivery guarantee.

At 23:52:49 UTC the qualified helper was installed at the final backfill path,
with the serial binary and manifest preserved. Its SHA-256 is
`d7d1f9ed1ff7db5c59a585b69b9afd0cff6c4938d6942710cd81d751a9c84e24`.
The source-client revision, native writer API, exclusive write lock, durability
and final audit requirements are unchanged. Replay continued on its original
PID throughout. Controller and VM evidence is named
`erigon-bal-backfill-{timing,timed-preflight,parallel-timing,parallel-preflight,decoder-adoption}.json`.
Production sidecar restoration remains pending until final replay and clean stop.

## Final upload concurrency qualification at 00:06 UTC, October 20

Three sequential trials on the original Erigon VM uploaded eight 256-MiB parts
each, using four, eight and four workers. The measured upload rates were
70.830, 147.246 and 84.004 MiB/s respectively (28.914, 13.909 and 24.380 seconds
for 2 GiB). Every part supplied Content-MD5; the controller completed each
multipart object, checked its length and read back every byte against the
per-part SHA-256 values. All 6 GiB passed verification, the temporary objects
were deleted, and the probe service exited successfully. Evidence is controller
`erigon-upload-concurrency.json`.

Eight workers were 1.75 times faster than the faster four-worker control. The
future Erigon uploader now uses eight workers, retaining 256-MiB parts, ordered
archive hashing, bounded pending work and the existing verification gates.
The other three running uploads retain their four-worker configuration. The
deployed uploader SHA-256 is
`995c104f6a51d633af5c709e5c4fd1589a0dbee4944e1a81a0e5eba72e7023ac`.
Its final integrity report records the actual worker count. These short tests
measure transfer capacity, not sparse-tar/compression throughput or a full
native archive. Replay remained active throughout; no replacement VM was used.

## Bounded 128-block batch trial at 00:22 UTC, October 20

The 2-GiB-buffer continuous segment was stopped at a fresh head notification
for 24,475,506. The handoff subsequently verified persistence, all 3,008 segment
headers, ordinary VALID results for the final 64 unreported payloads, recent
bodies, clean native shutdown and pinned-image reopen. It is sealed as
`native-replay-segments/0004/`, covering 24,472,499–24,475,506. The baseline's
last 384 blocks took 380.473 seconds between completed persistence events:
1.00927 blocks/s (`wide-pilot-baseline.json`).

The next bounded trial covers 24,475,507–24,476,018, using four batches of 128
with a 4-GiB execution buffer. The first 128 blocks and persistence are warmup;
the remaining 384 form the measured window. It uses the same continuation
binary, eight CPUs, 48-GiB process limit, normal pruning and normal durability.
Before the handoff, cgroup memory included roughly 16.5 GiB anonymous memory
and 29.5 GiB file cache, with zero OOM events. A larger buffer may displace cache;
the trial must establish its actual benefit and memory behavior.

All 512 headers and full bodies must match both before shutdown and after
pinned-image reopen. Successful qualification alone does not select the new
setting; compare the measured rate before resuming full replay. Evidence is
isolated in `native-wide-pilot/`. The monitor follows its live process handles
but excludes bounded trials from the full-replay completion forecast. The trial
completed as recorded below.

## Wider trial verified; 64-block replay resumed at 00:35 UTC

The 512-block trial passed all header and full-body comparisons before native
shutdown and after reopening the pinned release image. The native service
stopped successfully, and the range is sealed as `native-replay-segments/0005/`.
The 384 measured blocks took 399.920 seconds including final persistence:
0.96019 blocks/s, compared with 1.00927 blocks/s in the preceding 384-block
64-batch window. This is 4.9% lower throughput across different sequential
block windows, not a controlled same-input comparison. No OOM events occurred.

The larger setting was not adopted. Full replay was resumed from 24,476,019
using the existing qualified 64-block, 2-GiB-buffer configuration, unchanged
continuation binary, normal durability and the original eight-CPU VM. All 512
trial blocks remain validated progress toward the target, bringing the sealed
head to 24,476,018 and the qualifying count to 22,460 of 50,400.

Controller evidence is `native-wide-pilot-evidence.tar.gz` (SHA-256
`352dbb33471b20e6ec092ebb2cd570e0eb6b8f8ac94597017a0dafda47fa004e`)
and `wide-pilot-comparison.json`. At the prior sustained rate, replay alone
would finish around 08:15 UTC. BAL restoration, exhaustive restart audit,
archive upload and remote verification still follow, making delivery by
09:00 UTC unlikely. The complete target and publication gates remain required.

## Compiler profile-guided build screened at 01:00 UTC

The existing 30-second CPU profile attributed 53.85% of sampled CPU time to
latest-file lookup, including 41.56% reached through execution storage reads.
The data directory contains 4,880 storage domain files; 4,086 recent files
account for 6,439,975,428 bytes of `.kv` data. The workload's new slot keys are
random hashes in already-used contracts, so a simple address-absence or key-range
cache was not implemented. Background merging also has documented shutdown and
throughput costs; it remains disabled during this replay.

A compiler-only candidate used Go 1.26.0, AMD64 v2, the unchanged source commit
`72b4a99bbb46a61ce3ab0932111533da8cb9fcda`, and
`GO_FLAGS=-pgo=original-2g-steady.cpu.pprof`. Its binary SHA-256 is
`59fa021b75d9d35ffea7a862555bed62a89f4848f65f54f49a68479e9e420db8`.
Selected Engine API insertion and execution-module batch, invalid-state,
bad-block recovery, changeset and shallow-reorg tests passed with PGO enabled.
No client source changes were made.

The existing sharded-filter benchmark ran baseline/PGO/baseline on the original
VM, with one CPU quota, nice 19 and three repetitions per case. Median
nanoseconds per lookup were:

| Filter size | Baseline first | PGO | Baseline second |
| --- | ---: | ---: | ---: |
| 100,000 keys | 6.742 | 7.193 | 10.300 |
| 1,000,000 keys | 8.257 | 12.230 | 8.788 |

The smaller case was variable; the larger case did not improve. This is a
microbenchmark during live replay, not an end-to-end throughput comparison.
It did not justify interrupting replay, and the candidate was **not deployed**.
The same replay PID advanced from 24,477,298 to 24,477,362 during the bounded
comparison. Build, test logs, checksums and benchmark evidence are retained in
controller `pgo-build/`; VM evidence is `/data/pbt-1/pgo-probe/`.

The 00:45–01:00 progress samples advanced 896 blocks in 927.641 seconds,
0.96589 blocks/s. The resulting replay-only estimate is approximately 08:40
UTC, before all final validation and native upload work. The monitor now uses
the result receipt time for freshness checks, since a remote sample may be
newer than the controller check's start time. Its stale, future-time, restarted
process and bounded-trial rejection gates remain in place.

## Combined storage-filter candidate prepared at 01:44 UTC

A read-only probe built a 128-MiB Bloom filter over 4,086 recent storage
files, including tombstones. It visited 75,735,117 keys and checked every key
again in a second pass, with no false negatives and unchanged source-file
hashes. The union SHA-256 is
`57e86073c576570b00ef4a82b525e3af1bb22d0a6faf96b84e2f6a79a8713b24`.
The source datadir was mounted read-only for the probe; MDBX was never opened.

A second benchmark included all 4,880 physical storage files. Across 8,192
random hash queries and 1,024 known-present samples, baseline/union/baseline
times were 18.703 / 1.214 / 5.608 seconds. The union skipped 33,472,512 of
44,974,080 per-file checks while retaining searches in older uncovered files.
The warmed comparison is 4.62 times faster for this filter loop. These are
physical-file microbenchmarks, not the client's visible-file set or replay
throughput. The first full-file attempt was stopped before measurements to
replace repeated directory scans with one indexed scan. The final benchmark
used one CPU quota and a 6-GiB process cap on the original VM; it exited
successfully after 34 seconds. No VM resources were added.

Native candidate commit `88b2bb172592c460d546d776f9ceb295a7e569c3` extends
continuation commit `72b4a99bbb46a61ce3ab0932111533da8cb9fcda`. It defaults off
and is enabled by `DOMAIN_STORAGE_UNION=true`. Each visible storage-file
generation builds its own in-memory filter from a suffix bounded to 8 GiB of
source data, requiring at least 512 files. The filter is capped at 128 MiB.
Negative results skip only that covered suffix; positive results use the
existing lookup. Tombstones, bounded reads, source-file lifetime and salt
matching remain required. No database format changes are made.

Tests for tombstones, older values, historical bounds and concurrent shared
construction passed under the race detector. `make lint` and both Erigon and
integration builds passed. The final Go 1.26.0 / AMD64-v2 binary SHA-256 is
`dc375f32df43fe8132b4e988b31f052ae1dfb0414fe5d35ac82e346a3515a6ed`.
Controller evidence and the candidate are in `storage-union-probe/`.

The prepared `union-64` pilot uses 256 blocks, 64-block batches, a 2-GiB buffer,
the existing eight CPUs and the existing 48-GiB client limit. A read-only WETH
storage query must match the pinned image and preserve the audited head before
replay starts. All 256 bodies and headers must match before clean shutdown and
after pinned-image reopen. The first 64 blocks are warmup; the remaining 192
form the measured window. The extended workflow's 39 tests passed. The monitor
recognizes this bounded trial and excludes it from full-replay forecasts.
The candidate is staged but has not yet replayed blocks or been adopted for
the full run.

## Storage union passed replay qualification at 01:56 UTC

The preceding full segment sealed at 24,480,050 after all 4,032 headers, the
unreported tail's VALID responses, recent bodies, normal persistence and pinned
restart checks. It is retained as `native-replay-segments/0006/`.

The union candidate then replayed 24,480,051–24,480,306. All 256 headers and
full bodies matched before clean native shutdown and after reopening the
pinned release. The trial is sealed as segment `0007`. The RPC storage filter
built in 60.704 seconds; execution's separate reader generation built its filter
in 11.578 seconds during the excluded first 64 blocks. Each covered 4,085
visible files and used 128 MiB.

The remaining 192 blocks took 157.773 seconds including final persistence:
**1.21694 blocks/s**. The preceding 384-block window was 0.93010 blocks/s,
and the earlier quieter 384-block baseline was 1.00927 blocks/s. These are
30.8% and 20.6% higher throughputs, respectively, across different sequential
windows. The recent baseline included concurrent read-only probes. The
filter-loop microbenchmark gain must not be substituted for this replay result.

This qualifies adoption on the original VM with 64-block batches, a 2-GiB
buffer, normal durability, eight CPUs and the existing 48-GiB process limit.
Full replay must carry the exact qualified environment and repeat the
pinned/native read-only warmup. Final publication requires this qualification
and full-run warmup evidence. The extended workflow's 41 tests passed.
Controller evidence is `storage-union-probe/native-union-pilot-evidence.tar.gz`,
`union-pilot-proof.json` and `union-pilot-comparison.json`.

The verified head now contains 26,748 of 50,400 qualifying blocks. At the trial
rate, the remaining 23,652 blocks take about 5 hours 24 minutes, before final
BAL restoration, restart audit and native upload. Delivery by 09:00 UTC remains
at risk. All other native snapshot uploads continue.

The controller's build caches briefly crossed the relay's 30-GB free-space
guard. All 51,420 input records were already present on Erigon. Removing the
oldest 14 GiB of reproducible Go cache entries restored about 37 GiB free,
without removing source, binaries, replay inputs, snapshots or evidence. The
relay then completed successfully, and the 01:48 monitor reported no alerts.

## Remaining flush cost after union adoption, 02:13 UTC

The full replay is running the qualified union binary on the original VM,
with client PID `193436` and invocation `1dca0152c5ff472e885444544e9ee7bb`.
At 02:12:25 UTC it reached 24,481,138, or 27,580 qualifying blocks. Geth,
Besu and Nethermind's upload processes were independently confirmed active.

A 60-second read-only `/proc` and block-device sample recorded 106.3 MiB/s
of device writes, approximately 17,487 write operations/s, a mean queue depth
of 38.9 and 40.1% full I/O pressure. Device busy time was 58.2%; this does not
establish a provider throughput ceiling. CPU steal was 0.17%. The client's
memory cgroup reported no limit hits, OOM events or current memory pressure.
These measurements support investigating database I/O before increasing RAM.

The last 450 log lines contained 14 substantial flush/commit samples and 15
execution samples, including startup. Their independent medians were 11.41
seconds executing 64 blocks, 19.69 seconds flushing and 17.66 seconds in the
native commit. Writer flushing accounted for 13.33 seconds within the flush.
These are overlapping, independently sampled phases, not an additive batch
latency calculation. A representative commit logged 18.017 seconds total,
of which 17.996 seconds was synchronization.

Source inspection confirms that domain flushing includes history and inverted
index writes. The `loadFunc` wrapper intentionally prevents the ETL append
fast path because duplicate values are not sorted for `AppendDup`; replacing
it with the identity function would require proving those ordering constraints.
No writer, durability, memory or kernel tuning was changed. Earlier write-mode,
writeback and wider-batch trials did not establish an improvement.

Controller evidence is under `storage-union-probe/`: `io-sample.jsonl`,
`io-analysis.json`, `io-cgroup.json`, `io-window-client.log` and
`phase-analysis.json`. A bounded two-minute CPU capture completed at 02:14:16
UTC with the same live client PID and invocation before and after. Its SHA-256
is `377f350323690784f458b6b490b9913900d676a07626c27f3f9bb2174c556939`;
the downloaded copy was checked against that digest. Evidence and `pprof`
summaries are in `storage-union-probe/cycle-profile/`.

The capture collected 141.33 CPU-seconds over 120 wall seconds. Snapshot-file
lookup accounted for 14.89% cumulatively, writer flushing for 12.23%, and all
shared-domain flushing for 18.55%. MDBX cursor puts accounted for 13.35%; Cgo
also includes signature recovery and reads, so its 31.64% must not be assigned
entirely to writes. These overlapping CPU percentages do not measure storage
wait. Together with the timing and I/O evidence, they show that reducing writer
CPU work alone would leave the substantial synchronization cost. No further
native change has been qualified from this evidence yet.

## Final audit input prefetch qualified at 02:19 UTC

The full Geth restart/BAL audit took 1,251.95 seconds from the before-audit
report to the after-audit report. To reduce Erigon's remaining final-stage
cost, `audit.py` now decodes expected records with four threads while requesting
the corresponding 16 bodies. It retains at most one batch of expected records,
yields them in block order and keeps every BAL, transaction, withdrawal, gas,
packing and state-sample comparison. Input errors and short RPC responses remain
fatal; there is no sampling or skipped record.

On the original Erigon VM, serial/prefetch/serial decoding of the same 128
records took 1.492 / 0.619 / 1.291 seconds. Every field of every decoded record
matched. This is about 2.1 times faster than the warmed serial reader, not a
measurement of full-audit throughput. A separate live Engine API check matched
all transactions, withdrawals and BALs for blocks 24,481,571–24,481,586 in
0.203 seconds. It did not alter the database or interrupt replay.

Four new tests cover ordered pairing across a partial final batch, missing or
corrupt records, truncated RPC responses and the prefetch bound. They failed
before implementation; all 45 workflow tests then passed. The qualified script
was atomically deployed for Erigon's future final audit, with its previous
version preserved. Its SHA-256 is
`3968b8d9dd94a793c566df1aabf308451d768ee52f975c54c386cfffea937d3a`.
Controller evidence is `audit-decode-probe/adoption.json` and `rpc-proof.json`;
the final-stage readiness report records the updated script digest. Existing
completed client audits and the running Erigon replay are unchanged.

## Eight-worker BAL restoration decoder qualified at 02:28 UTC

The post-replay sidecar helper now uses eight decoder workers on the original
eight-CPU VM, retaining the existing 128-record batch bound. Native canonical
checks and database writes remain serial and ordered. The full-input preflight,
fresh second-pass input digest checks, exclusive write access and normal
durability remain required. The extended ordering/digest test failed against
the four-worker limit; the candidate then passed the race-enabled helper suite.

A read-only baseline/candidate/baseline comparison on identical records
24,453,559–24,454,566 took 13.980 / 9.403 / 13.808 seconds. All three checked
1,008 records with input digest
`168a387fad52154da24cab206eb62370d76e5f3d41bd4a60d2bb687de0c824a8`
and wrote zero sidecars. The candidate was 1.47 times faster than the faster
baseline. Each run had the same eight-CPU quota, 6-GiB process limit, 4-GiB Go
memory limit and low scheduling priority. Peak service memory was 1.1 GiB.
The live Erigon process and invocation remained unchanged throughout.

The new helper SHA-256 is
`a629abf89b6bc0398bd05e3cea02edb85d916036e181c1e79c71cb2d5b6d70dc`.
It was installed with matching build metadata; the prior binary and metadata
remain as `/data/pbt-1/erigon-bal-backfill-four{,.json}`. Controller evidence is
under `backfill-eight-worker/`, and `erigon-final-stage-readiness.json` records
the adoption. The measured decoding rate extrapolates to approximately 16
minutes for two full input passes, excluding sidecar writes, restart, API audit
and upload. This is not a measured final-stage completion time. Production
sidecar restoration has not run yet.

## Mutable database size inspection at 02:34 UTC

A short read-only probe using the pinned MDBX Go dependency, v0.43.0, collected
table page statistics. It opened existing tables with `MDBX_DB_ACCEDE` so their
stored flags were preserved. An initial attempt with default table flags was
rejected on the first DupSort table; that attempt made no database writes.

At the successful sample, the file was 229,092,884,480 bytes, the read
transaction's committed geometry was 228,086,251,520 bytes, and reported table
pages accounted for 222,727,368,704 bytes. Live replay can grow the file between
the filesystem sample and the pinned read transaction. More than 97% of the
file was accounted for by table pages. `CommitmentVals` alone held about
146.82 GiB and 228,787,949 entries. Immutable snapshot files separately occupied
497,525,137,408 bytes at the preceding size check.

MDBX compact copy omits free pages and renumbers retained pages; these figures
do not support spending time copying, switching and revalidating the database
for the small possible free-page reduction. No compaction or deletion was
performed. Replay continued on the same process and invocation. Source, binary,
raw statistics and the decision report are preserved in the controller's
`mdbx-size-probe/` directory.

## Sixteen-transfer upload qualified at 02:41 UTC

A transport-only comparison uploaded 4 GiB per trial using the same 256-MiB
parts and original Erigon VM. Eight/sixteen/eight concurrent transfers measured
128.00 / 225.43 / 177.22 MiB/s. Sixteen transfers were 27.2% faster than the
faster control. The variation between controls matters: the larger gain against
the first control must not be presented as the conservative result.

Every byte of all three temporary objects was read back and checked against
the source part SHA-256 values. Content-MD5 was also supplied for every PUT.
Each object was deleted and its absence verified before the trial report was
marked complete. The probe used generated payloads, so these measurements
exclude native archive reading, tar, compression and production stream hashing.

The Erigon uploader now uses sixteen transfers, bounding simultaneous PUT
buffers to 4 GiB; its producer and compression buffers are additional. The
source client will be stopped before upload. Other clients retain four
transfers and their running uploads were not changed. Archive exclusions,
clean-restart prerequisites and verification gates are unchanged. Both existing
archive-layout tests passed. The prior Erigon script is preserved as
`/data/pbt-1/upload-eight.py`.

Uploader SHA-256:
`c470d345e4402f25646739b4313b9751bb48bffd895a39211253a15ee0d36f7f`.
Evidence is `erigon-upload-concurrency-16.json` and
`erigon-upload-concurrency-16-adoption.json` on the controller. The current
adoption and final-stage readiness reports name sixteen transfers. The full
native upload is still pending; this is not a delivered snapshot or a measured
end-to-end upload duration.

## Bounded archive-production sample at 02:46 UTC

A read-only sample streamed three immutable storage-domain files through sparse
tar, `zstd -1 -T4` and sequential SHA-256 hashing. Its 4,289,037,732 input bytes
produced 2,838,744,298 compressed bytes in 104.732 seconds: 39.06 MiB/s input and
25.85 MiB/s compressed output, a 0.662 output/input ratio. No archive data was
retained or uploaded. File sizes and modification times matched afterwards;
the live Erigon PID and invocation stayed unchanged.

The sample ran alongside replay with idle I/O priority, nice level 19, an
eight-CPU quota and a 2-GiB memory cap. It used 29.075 CPU-seconds and reached
the memory cap including file cache. This measurement includes contention and
does not establish throughput on the stopped source VM. It covers three storage
files, not the entire database layout, and excludes staging and per-part hashes.
The network-only transfer rate must not be used as the full archive rate.

The first sample selection allowed only files up to 512 MiB and found too
little eligible data; it failed before starting tar. The completed second
attempt allowed larger individual files while retaining the 4-GiB total cap.
Controller source, file list and completion report are in
`archive-throughput-probe/`; the successful VM service was
`pbt-1-archive-throughput-probe-v2`, invocation
`3214a8736c9c45dfb969c1e2284b353a`.

## Final upload concurrency comparison at 02:53 UTC

The final transport test used 8 GiB per trial with 256-MiB parts. Sixteen /
thirty-two / sixteen transfers measured 300.78 / 365.24 / 278.48 MiB/s.
Thirty-two transfers were 21.4% faster than the faster control. All 24 GiB passed
full remote readback against source part digests. Every temporary object was
deleted and its absence checked. The test service exited successfully; the live
Erigon process remained active without cgroup memory-limit or OOM events.

The Erigon uploader now uses thirty-two transfers, with 8 GiB of simultaneous
PUT buffers plus producer, compression and filesystem-cache memory. It runs
after the source client stops on the existing 64-GiB VM. Other clients continue
using four transfers. Both archive-layout tests passed, and the prior script is
preserved as `/data/pbt-1/upload-sixteen.py`. No further throughput probes are
planned during replay.

Uploader SHA-256:
`422e0851e5bcade358de5d6cdaf21d88cee8ed41550eca0cbd7d729bba8dc5fc`.
Evidence is `erigon-upload-concurrency-32.json` and
`erigon-upload-concurrency-32-adoption.json`; the current adoption and final-stage
readiness reports name thirty-two transfers. The storage-file sample and these
transport tests measure different parts of the pipeline. Full native archive
throughput and completion remain unproven until the actual stopped-source export.
