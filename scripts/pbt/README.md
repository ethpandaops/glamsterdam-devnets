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
