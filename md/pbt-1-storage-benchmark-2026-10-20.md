# PBT-1 attached-volume comparison

Status at 10:01 UTC: all 12 timed jobs completed successfully at 10:00:21 UTC.
Both 64-GiB test files and the smoke-test directories have been removed.
The volume remains attached and mounted; Besu remains stopped at its original
shutdown timestamp. This experiment does not change the
database placement or provision the remaining migration workers.

## Host and volume

| Item | Value |
|---|---|
| Host | `glamsterdam-pbt-1-lighthouse-besu-1`, `138.68.76.218` |
| Droplet | `610526051`, `fra1`, `so1_5-8vcpu-64gb-intel` |
| Resources | 8 vCPU, 64 GiB RAM, nominal 1800-GiB local disk |
| Local filesystem | `/dev/vda1`, ext4, mounted at `/` |
| Added volume | `glamsterdam-pbt-1-besu-benchmark`, 2500 GiB (~2.68 TB) |
| Volume ID | `fda4407e-cc66-11f1-b20f-de3ab6cd27a3` |
| Volume filesystem | `/dev/sda`, ext4, UUID `125b91a3-eb46-41f9-bfc1-29a3ecf21a81` |
| Mount | `/mnt/glamsterdam_pbt_1_besu_benchmark` |
| fio | 3.39 |

The operator authorized one attached volume and a benchmark against the local
disk. Terraform created only the volume, its Besu attachment, and its project
association; no existing resources were changed or destroyed. Configuration:
[`benchmark-volume.tf`](../terraform/pbt-1/benchmark-volume.tf).
The API attachment and mounted filesystem identity were independently checked.
Besu remains cleanly stopped. Erigon completed validation and is uploading its
snapshot on a separate VM.

## Measurements

| Workload | Local disk | Attached volume | Local / volume |
|---|---:|---:|---:|
| Sequential read, 1 MiB, QD32 | 8,640.98 MiB/s | 499.89 MiB/s | 17.29× |
| Sequential write, 1 MiB, QD32 | 861.77 MiB/s | 450.11 MiB/s | 1.91× |
| Random read, 4 KiB, QD1 | 11,804 IOPS | 2,596 IOPS | 4.55× |
| Random read, 16 KiB, QD32 | 130,160 IOPS | 10,000 IOPS | 13.02× |
| Mixed random, 16 KiB, QD32, total | 52,157 IOPS | 9,999 IOPS | 5.22× |
| Durable write, 4 KiB, QD1, `fdatasync=1` | 8,368 writes/s | 1,704 writes/s | 4.91× |

| Latency measurement | Local disk | Attached volume |
|---|---:|---:|
| 4-KiB QD1 read completion, median / p99 | 84.48 / 136.19 µs | 358.40 / 757.76 µs |
| 16-KiB QD32 read completion, median / p99 | 0.239 / 0.399 ms | 3.162 / 3.686 ms |
| Mixed read completion, median / p99 | 0.569 / 0.889 ms | 4.358 / 5.538 ms |
| Mixed write completion, median / p99 | 0.668 / 1.319 ms | 0.379 / 1.204 ms |
| Durable test `fdatasync`, median / p99 | 0.0366 / 0.0550 ms | 0.5018 / 1.3517 ms |

Mixed throughput was 570.37 MiB/s read plus 244.59 MiB/s write locally, versus
109.36 plus 46.88 MiB/s on the volume. Individual mixed writes returned faster
on the volume, despite lower total throughput. Those writes are not individually
synchronized; the separate durable test measures writes with `fdatasync=1`.
Its sync latency is reported separately from write completion, and percentile
values must not be added to derive an end-to-end percentile.

These are measured rates for the warm 64-GiB working set described below.
In particular, the high local read rate does not establish cold-read throughput
for a full 1.2-TB database: direct I/O bypasses guest page cache, but does not
exclude provider caching. The sequential writes do not synchronize each write.

For performance, prefer the local disk for the active database where the full
migration peak fits. The volume is a plausible place for a recovery copy.
This is an inference from the storage measurements, not a measured client import
speedup: actual client behavior, caches, batching and scratch requirements still
need an import trial. If capacity requires placing the active database on the
volume, expect a different storage-performance profile and use the same placement
for both RAM limits when comparing them.

Keeping a recovery copy on the volume does not resolve local migration capacity.
After cleanup, available space was 557,593,370,624 bytes (~557.6 GB) locally and
2,528,727,785,472 bytes (~2.53 TB) on the volume. No recovery copy or database
relocation has been started; the operator's placement choice remains open.

## Method

The [benchmark runner](../scripts/pbt/benchmark-storage.py) checks the exact
volume UUID, different filesystem devices, and the stopped Besu container.
It waits for ext4 lazy initialization to end before measurements.
It creates a dedicated 64-GiB file on each filesystem, fills every byte before
reads, uses direct I/O, and alternates which disk is measured first.
Every timed job has a 60-second warm-up followed by 120 seconds of measurement.
The full benchmark runs in `pbt-1-storage-benchmark.service` with a 4-GiB memory
limit. That is the benchmark runner's budget, not a migration-worker limit.

| Workload | Block size | Queue depth | Purpose |
|---|---:|---:|---|
| Sequential read | 1 MiB | 32 | Reading recovery copies/artifacts |
| Sequential write | 1 MiB | 32 | Writing recovery copies/artifacts |
| Random read | 4 KiB | 1 | Serial lookup latency |
| Random read | 16 KiB | 32 | Concurrent lookup throughput |
| Mixed random, 70% read / 30% write | 16 KiB | 32 | Mixed I/O comparison |
| Write with `fdatasync` after every write | 4 KiB | 1 | Small durable-write latency |

Use throughput, IOPS, completion-latency percentiles, sync latency and CPU use
together. The two filesystems have different mount defaults, recorded in the
manifest: local uses `relatime`, while the volume uses `noatime`; both use
`discard`. The 09:49 UTC `during-run-environment.json` records occupancy with
the two 64-GiB test files present: local used 1,335,966,732,288 bytes of
1,902,190,370,816 bytes (~70%), versus 68,721,610,752 of 2,662,964,412,416 bytes
(~2.6%) on the new volume. It also verifies that the remote runner's SHA-256
matches the committed script and records the service's 4-GiB memory limit.
This is a comparison of the deployed storage
paths, not a raw-device test or a measurement of any client's migration speed.
Direct I/O bypasses guest page cache; provider-side caching and throttling can
still affect the measurements. The warm-up reduces sensitivity to brief bursts.
The new volume's measured behavior should inform, rather than replace, a
client-specific import trial.

DigitalOcean documents dedicated-Droplet volume limits of 10,000 IOPS and
450 MB/s, with burst limits of 15,000 IOPS and 525 MB/s. The measured concurrent
random-read rate is near the documented non-burst IOPS limit. The measured
sequential rates must not be treated as a guarantee of indefinitely sustained
throughput after provider burst allowances are exhausted.
Source: [DigitalOcean volume limits](https://docs.digitalocean.com/products/volumes/details/limits/),
checked October 20, 2026.

On successful completion, the runner removes only its own test files and leaves
the volume mounted. A failure preserves those files for diagnosis. The first
smoke attempt stopped before I/O because fio's no-create setting requires a
pre-sized file. The runner was corrected to pre-size files created exclusively
by that run; `smoke-v2-20261020` passed four jobs and removed its test files.
Its one-second measurements are not performance results.

## Evidence

- Besu VM: `/data/pbt-1/storage-benchmark/full-20261020/`.
- That directory contains the environment manifest, exact fio commands, complete
  fio JSON output, incremental `results.json`, and `status.json`.
- [Validated measurements and evidence hashes](pbt-1-storage-benchmark-2026-10-20-results.json)
  contain all 12 result rows, both latency distributions, per-job raw-output
  checksums, environment observations and the final cleanup checks.
  Both 64-GiB prefills, all 12 zero-error jobs, the requested job options and
  measurement durations were checked against raw fio JSON.
- fio 3.39 reported `sync.total_ios=0` with nonzero `sync.lat_ns.N`. The original
  summary extractor consequently omitted sync latency. The corrected extractor
  uses the sample count too; the linked measurements were re-extracted from
  unchanged raw output. Local sync latency has 1,004,183 samples versus 1,004,184
  measured writes; the volume has 204,540 of each. The running test was unchanged.
  Both the executed runner hash and corrected extractor hash are recorded.
- `postflight.json` confirms the volume UUID and mount, service success, removal
  of all test directories, and Besu's unchanged stopped state.
- Controller: `~/.local/state/pbt-1-run/besu-volume-provisioned.json` and
  `besu-volume-attachment-verified.json`.
- Terraform's plan was checked for exactly three creates and the intended
  2500-GiB size and droplet ID before applying.

Do not treat a recovery copy on the added volume as extra free space under the
local database path. Conversely, an actively used database on the volume is not
its own recovery copy. Besu stages files under its data path and links them into
the database, so splitting that staging directory across filesystems requires
separate qualification.
