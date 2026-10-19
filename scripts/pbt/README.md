# PBT-1 source preparation

See the [PBT-1 migration process](../../md/pbt-1-migration-process.md) for the
nine-machine test matrix, process memory limits and BAL availability audit.

Seed the dedicated DigitalOcean node before choosing the migration sequence. This restores
Erigon's Jochemnet release at 24452538 into `/data/pbt-1/erigon`, using the existing
parallel streaming downloader. It does not start Erigon or generate network state.

The source metadata reports 428,144,697,343 bytes restored. Require at least 550 GB
free for this restore; PBT conversion needs a separate capacity check. The archive
is streamed directly into extraction with bounded chunk staging on the destination
filesystem. A stopped partial extraction is not automatically resumable or erased.

Terraform in `terraform/pbt-1` provisions four non-validating source nodes in Frankfurt,
using MSF-2's `so1_5-8vcpu-64gb-intel` size (8 vCPU, 64 GiB RAM, 1800 GiB disk per
the DigitalOcean API). There is one source each for Erigon, Geth, Besu and
Nethermind; this preparation starts no Lighthouse or validators. Run from the infra repository:

```sh
cd ansible
ANSIBLE_STRATEGY=linear ANSIBLE_CACHE_PLUGIN_CONNECTION=tmp/pbt-1 \
  ansible-playbook -i inventories/pbt-1/inventory.ini pbt-erigon-seed.yaml \
  -e ansible_user=root
```

The initial root login uses the DigitalOcean-injected shared devops SSH key.
The play installs/enables Docker, verifies source metadata and
checks archive access from the node before starting the detached fetcher. It refuses
to extract over existing data. Container name: `pbt-1-erigon-snapshot`.

## Current deployment (2026-10-19)

`glamsterdam-pbt-1-lighthouse-erigon-1` is at `164.92.239.96` (DigitalOcean ID
610514960). Terraform applied seven new resources with no changes/deletions to
existing infrastructure. The detached restore started at 12:56:50 UTC through
Ansible; runtime extraction and increasing chunk counts were verified.

Completion confirmed at 13:27:44 UTC: the fetcher exited with code 0 and the
`snapshot-fetcher/done` marker exists. Client startup and database validation
remain separate checks.

The public archive currently returns HTTP 403: the Cloudflare rule allows
`snapshot.tar.zst` but omits `snapshot-pruned.tar.zst`. Metadata remains public.
Authenticated R2 access verified the pinned archive size of 276,341,609,865 bytes.
For this run, a 24-hour signed GET URL authorizes only that object. To reproduce
from the repository root, using the existing Cloudflare credential locally:

```sh
python3 scripts/pbt/authorize-snapshot.py \
  --host root@164.92.239.96 --identity ~/.ssh/devops_eth2_shared_key
cd ansible
ANSIBLE_STRATEGY=linear ANSIBLE_CACHE_PLUGIN_CONNECTION=tmp/pbt-1 \
  ansible-playbook -i inventories/pbt-1/inventory.ini pbt-erigon-seed.yaml \
  -e ansible_user=root -e seed_authenticated_source=true \
  --private-key ~/.ssh/devops_eth2_shared_key
```

The helper checks the archive size and stores the URL in a mode-0600 file on the
node. Storage credentials remain on the controller. The downloader reads the URL
when it starts, so renewing the file does not update an already running fetcher.
If a restore fails or exceeds URL expiry, inspect it before restarting; the play
refuses to overwrite partial data. Remove `snapshot-fetcher/source-url` after
completion. Full client deployment and PBT conversion are separate steps.

## Additional source restores

| Client | Inventory host | IP | Restore playbook |
| --- | --- | --- | --- |
| Geth | lighthouse-geth-1 | 46.101.230.44 | pbt-geth-seed.yaml |
| Besu | lighthouse-besu-1 | 138.68.76.218 | pbt-besu-seed.yaml |
| Nethermind | lighthouse-nethermind-1 | 167.172.188.11 | pbt-nethermind-seed.yaml |

Run these playbooks from `ansible/` with the same explicit PBT-1 inventory, cache
and root SSH login. They share `pbt-source-seed.yaml`, which waits for cloud-init,
validates each client's pinned metadata and refuses nonempty destinations or
failed partial restores. The public URLs for these three clients work without a
signed URL. Fetchers are named `pbt-1-<client>-snapshot`; databases are under
`/data/pbt-1/<client>`. Their restores were started on 2026-10-19.

Nethermind's archive contains `mainnet/` beneath that destination. Its obsolete
Patricia data is scheduled for removal after restoration using
[`nethermind-flatdb-cleanup.py`](nethermind-flatdb-cleanup.py). The operator explicitly
requested this cleanup before uploading the refreshed snapshot. The job runs in
a detached systemd service on its VM and performs baseline validation, client-managed
deletion, and clean restart verification with networking disabled for the checks.
It uses the native `FlatDb.DropPruningTrieState` flag and a pinned image digest.
Inspect with:

```sh
systemctl status pbt-1-nethermind-flatdb-cleanup
journalctl -u pbt-1-nethermind-flatdb-cleanup --no-pager
cat /data/pbt-1/nethermind-flatdb-cleanup/complete.json
```

The report records allocated Patricia bytes before/after cleanup. If the job fails,
inspect its phase logs before retrying; a diagnostic container may remain stopped.
Only a successful `complete.json` qualifies the cleanup for snapshot publication.
The live deployment uses a Geth-format copy of MSF-2's source genesis (same mainnet
genesis and Amsterdam schedule, alloc addresses prefixed with `0x`) at
`/data/pbt-1/pbt-1-source-genesis.json`. The script records its SHA-256 in the report.

Monitor on the VM:

```sh
sudo docker logs --tail 30 -f pbt-1-erigon-snapshot
sudo docker inspect --format '{{json .State}}' pbt-1-erigon-snapshot
df -h /data/pbt-1
test -f /data/pbt-1/snapshot-fetcher/done
```

After restore, verify an isolated Erigon node's head/hash/root against the retained
metadata before any conversion. Choose the PBT build and commitment upgrade path
separately. Do not let the restored chain-id-1 database peer with mainnet.

Check download status on that node; it runs independently of this workspace session.

## Continuous monitoring

[`monitor.py`](monitor.py) runs read-only checks against all four source VMs.
It also checks controller disk headroom for the replay bundle, estimating remaining
records at 125% of the observed average size plus a 10 GiB reserve. Bundle upload
streams tar/zstd output and does not require a second complete archive on disk.
The controller's enabled user timer `pbt-1-monitor.timer` runs it at :00, :15,
:30 and :45 UTC. User lingering is enabled, so checks survive shell logout.
Each run records progress, free disk, container failures/OOMs, restore completion,
and the Nethermind cleanup service/result. During generation/replay,
`bal-sentinel.py` retrieves the first generated body, first qualifying body and
a recent body, comparing BAL bytes, transactions and withdrawals with the saved
records. This detects retention problems before the final exhaustive audit.
A running restore with no chunk
progress between checks, low disk, failed SSH or failed cleanup raises an alert.

Reports are local to the controller:

- `~/.local/state/pbt-1-monitor/status.md`: latest readable report and alerts.
- `~/.local/state/pbt-1-monitor/latest.json`: latest machine-readable evidence.
- `~/.local/state/pbt-1-monitor/history.jsonl`: full check history.

```sh
systemctl --user list-timers pbt-1-monitor.timer
journalctl --user -u pbt-1-monitor.service --no-pager
python3 scripts/pbt/monitor.py
```

Alerts are recorded in these reports and the systemd journal; this timer does not
send chat/email notifications. Failed checks do not disable subsequent timer runs.
Generation/replay/upload runners can publish `/data/pbt-1/pipeline/status.json`
on their VMs; absent that evidence, the report leaves those phases unverified.
Stop recurring checks when no longer needed with
`systemctl --user disable --now pbt-1-monitor.timer`.

## Overnight workload and publication

The active goal is delivery by **2026-10-20 09:00 UTC**: generate the workload,
replay it on all four clients, verify restarts and BAL availability, and upload
four native snapshots plus the replay bundle. The remaining five migration-test
VMs are a subsequent stage. Preparation clients use a 48 GiB container limit;
the agreed 16/32 GiB budgets apply to the later nine-worker migration trials.

The first pilot (1,000 blocks, approximately 29.7M gas) remains a recorded
preparation prefix. The operator subsequently required approximately **50%
occupancy in both EIP-8037 dimensions**, with substantial BALs. Version 2 uses:

- 200M block gas limit, targeting 100M execution gas and 100M state gas.
- 900 mixed ETH/WETH/single-storage transactions, eight batches creating 1,021
  fresh slots, and 34 batches updating 4,300 existing slots: 942 transactions.
- Eight batch-storage contracts and a separately seeded existing-state working
  set. Fresh slots have unique hashed keys; existing slots and values are nonzero.
- 99,976,320 state gas (`1021 * 64 * 1530`) and measured execution gas near
  100,532,000. Every qualifying block must stay within 5M of each 100M target.
- At least 300 KiB of encoded BAL per qualifying block. The first ten measured
  approximately 453,500 bytes each (~443 KiB), versus ~57 KiB in the first pilot.

Starting at block **24,467,832**, `v2.packing_revisions` reduces the existing-slot
updates to **4,252** while preserving the 942 transactions and 1,021 fresh slots.
The ten-block calibration measured approximately **99.90M execution gas**,
**99.98M state gas**, and BALs of at least **450,889 bytes**. This keeps header
gas below the 100M fee target, preventing the gradual base-fee increase observed
with the initial 100.53M execution load. Generation and final audits enforce the
new header-gas ceiling from the revision's effective index. Earlier qualifying
records are retained unchanged. Calibration evidence is included in the replay
bundle; see the [pilot report](../../md/pbt-1-8037-pilot-2026-10-19.md#fee-stable-packing-adjustment).

Execution gas is derived from the receipt gas sum minus state gas. This workload
has no storage clears/refunds or calldata-floor-bound transactions; the derived
`max(execution,state)` must equal the header's `gasUsed` on every block. A separate
Geth prestate trace of block 24,453,559 confirmed 1,021 fresh slots, zero clears,
zero new accounts and 942 transactions. This is a synthetic mixed workload,
not a measured reproduction of mainnet traffic. No blobs or CL consensus run.

The source anchor is **24,452,538**. The original 1,003 records plus 17 version-2
setup records form a **1,020-block preparation prefix**. The qualifying anchor is
**24,453,558**; the 50,400 qualifying blocks end at **24,503,958**. Twelve seconds
per block provide 604,800 seconds from qualifying anchor to final head. The
original source releases and the complete prefix remain recoverable; a new
native copy at the qualifying anchor can be reconstructed by replaying the prefix.

`source-client.py` starts pinned images with Docker networking disabled. The
driver joins the container's network namespace; RPC is not exposed externally.
`generate.py` saves a pending replay record before canonicalizing it, verifies
all receipts, checks both gas dimensions and the BAL hash/size, and atomically
publishes an immutable `blocks/<height>.json.gz`. `replay.py` requires Engine
`VALID`, then matching canonical hash, state root and BAL hash. Erigon's RPC view
may lag its Engine acknowledgement briefly; the driver waits for that view.

`reopen.py` performs a clean stop/restart, compares state samples, and retrieves
**every** generated BAL body and transaction list through
`engine_getPayloadBodiesByRangeV2`. The initial version-2 pilot requires 1,000
qualifying blocks to pass this gate on all four clients before the full run.
The legacy `--workload-blocks` argument counts records after the first three
setup blocks, so the version-2 pilot uses **2017** and the full run **51417**.
The report's `qualifying_blocks` is the operator-facing workload count.

Erigon uses two merge and two compression workers after the observed slowdown.
Before either final shutdown, `erigon_idle.py` waits for merge/compression work
to finish using SIGUSR1 goroutine profiles; it refuses SIGTERM after two hours
without an idle result. This avoids the observed compressor cancellation
deadlock. The intermediate forced-stop recovery preserved exact commitments
but does not qualify as a clean shutdown. See the
[incident and recovery evidence](../../md/pbt-1-erigon-merge-2026-10-19.md).

Controller user timers:

- `pbt-1-monitor.timer`: read-only status/alert report every 15 minutes.
- `pbt-1-relay.timer`: copy completed payload records to consumers every 20
  seconds after the previous transfer completes; SSH keys stay on the controller.
- `pbt-1-advance.timer`: inspect evidence gates every 30 seconds, run restart
  checks, start the qualified full run, and schedule verified publication.

Failures stop the affected stage for inspection; the controller does not
automatically retry failed database operations. Inspect
`~/.local/state/pbt-1-run/advance-status.json` and the corresponding systemd
journals. `full-run-gate.json` records the four passing pilot gates. Sensitive
controller storage authorization is in a mode-0600 file outside the repository.

Publication is under the new immutable prefix
`s3://ethpandaops-shadowfork-images/pbt-1/20261019-mixed-8037-v2/`.
Each native archive is `<client>/<head>/snapshot.tar.zst`. Geth remains a flat
instance directory and must be restored under `<datadir>/geth`. Nethermind
retains its required native databases under `mainnet/`; obsolete Patricia state
is omitted. Nethermind's client-managed cleanup reclaimed **341,910,994,944 bytes**
and passed state/head/restart validation on 2026-10-19. Its original cleanup
evidence is published beside the native archive as `_snapshot_flatdb_cleanup.json`,
linked from the snapshot metadata. Erigon's disposable `temp/` merge directory
is also omitted; the pinned client clears that directory on startup.

Erigon's finalized-head pruning also removes BAL sidecars. A live sample took
20.10 seconds to regenerate 16 older qualifying BALs. After its final clean stop,
[`retain-erigon-bals.py`](retain-erigon-bals.py) restores the already-validated
sidecars through a [pinned native backfill utility](erigon-bal-backfill/README.md).
Every sidecar must match the canonical native header, and the entire input range
is checked before any write. The same image then reopens with
`--exec.no-prune=true` and passes the unchanged exhaustive Engine body/BAL audit
before its second clean stop. Preserve this benchmark retention flag when using
the snapshot. Publication includes the backfill and build evidence; it explicitly
records restoration from validated replay inputs.

After the first large Erigon merge completed, another 20 GiB merge range began.
[`suppress-erigon-maintenance.py`](suppress-erigon-maintenance.py) checkpointed the
paused datadir, verified a separate mutable MDBX copy and preserved immutable
snapshot files, then restarted the same image with background maintenance and
pruning disabled for the bounded preparation run. Shutdown was clean (exit 0),
and the exact head and sampled BALs matched after restart. Replay resumed at
20:00:31 UTC. This keeps new state and BALs in native storage; monitor database
growth. The final startup profile and maintenance-restart evidence are published
with the snapshot. These diagnostic preparation flags are not an operational
network default; retain `--exec.no-prune=true` when native BAL retention is needed.

`prepare-upload.py` issues only object-scoped presigned multipart PUTs to the
VM. `upload.py` requires the final stopped/reopened proof, streams sparse tar
through zstd level 1, and uploads bounded 256 MiB parts with Content-MD5 checks.
`finish-upload.py` completes the object, checks size, verifies first/last and
sampled part SHA-256 values by remote readback, and publishes provenance. No
account storage credentials are copied to a source VM. Original Jochemnet
objects and latest pointers are preserved.

After all four native snapshots pass, `publish-bundle.py` uploads
`replay/snapshot.tar.zst` containing `blocks/`, `workload.json`, `manifest.json`
and the source genesis. It verifies the **entire** replay archive by remote
readback and publishes `_snapshot_manifest.json` and `_snapshot_workload.json`.
Only `~/.local/state/pbt-1-run/delivery-complete.json` establishes completion of
the full requested delivery. Snapshot publication alone does not establish that
the separate replay bundle has completed.
