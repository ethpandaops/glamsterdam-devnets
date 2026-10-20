# PBT-1 attached-volume comparison

Status at 09:21 UTC: volume attached; small smoke run passed; full benchmark
started. Performance results are pending. This experiment does not change the
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
Besu remains cleanly stopped. Erigon continues validation on a separate VM.

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
together. The two filesystems have different occupancy and mount defaults, which
are recorded in the manifest. This is a comparison of the deployed storage
paths, not a raw-device test or a measurement of any client's migration speed.
Direct I/O bypasses guest page cache; provider-side caching and throttling can
still affect the measurements. The warm-up reduces sensitivity to brief bursts.
The new volume's measured behavior should inform, rather than replace, a
client-specific import trial.

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
- Controller: `~/.local/state/pbt-1-run/besu-volume-provisioned.json` and
  `besu-volume-attachment-verified.json`.
- Terraform's plan was checked for exactly three creates and the intended
  2500-GiB size and droplet ID before applying.

Do not treat a recovery copy on the added volume as extra free space under the
local database path. Conversely, an actively used database on the volume is not
its own recovery copy. Besu stages files under its data path and links them into
the database, so splitting that staging directory across filesystems requires
separate qualification.
