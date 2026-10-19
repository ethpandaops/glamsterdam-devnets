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
The copy preserves sparse files and hard links, uses idle IO priority on the
source, and caps transfer at 256 MiB/s. Its status file and live systemd handle
are included in the existing 15-minute monitor. The monitor computes progress
against the full checkpoint size; rsync's incremental file-list percentages
and ETA are not full-transfer estimates.

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

Controller provisioning/access records are in `erigon-io-probe.json` and
`io-probe-ansible.log`. Copy failures stop for inspection; neither the copy
script nor monitoring automatically restarts failed database work.
