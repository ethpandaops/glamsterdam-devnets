# PBT-1 Erigon preparation

Seed the dedicated DigitalOcean node before choosing the migration sequence. This restores
Erigon's Jochemnet release at 24452538 into `/data/pbt-1/erigon`, using the existing
parallel streaming downloader. It does not start Erigon or generate network state.

The source metadata reports 428,144,697,343 bytes restored. Require at least 550 GB
free for this restore; PBT conversion needs a separate capacity check. The archive
is streamed directly into extraction with bounded chunk staging on the destination
filesystem. A stopped partial extraction is not automatically resumable or erased.

Terraform in `terraform/pbt-1` provisions one non-validating source node in Frankfurt,
using MSF-2's `so1_5-8vcpu-64gb-intel` size (8 vCPU, 64 GiB RAM, 1800 GiB disk per
the DigitalOcean API). The generated inventory names it `lighthouse-erigon-1`;
this preparation starts no Lighthouse or validators. Run from the infra repository:

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
