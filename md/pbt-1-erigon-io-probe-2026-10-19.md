# PBT-1 Erigon persistence comparison — 2026-10-19

The four source pipelines remain authoritative. A fifth, temporary DigitalOcean
VM is testing whether faster local storage can shorten Erigon preparation.
It is separate from the planned nine migration workers. No source cutover has
occurred, and neither its scratch benchmark nor its checkpoint copy establishes
that the final Erigon snapshot is ready.

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
