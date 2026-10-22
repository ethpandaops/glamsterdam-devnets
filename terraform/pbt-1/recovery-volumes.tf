# One compressed native snapshot per worker. Keep active databases on local SSD.
# Sized from the 2026-10-20 release, plus 2% and rounded up to 50 GiB.
# Ansible sets ext4 reserved blocks to 0 on these dedicated archive volumes.
# The benchmark volume was deleted and its absence verified already. Forget its
# old project-membership record without asking DO to reassign a deleted volume
# to the default project (which failed during the earlier cleanup).
removed {
  from = digitalocean_project_resources.benchmark_volume
  lifecycle {
    destroy = false
  }
}

locals {
  recovery_volume_sizes = {
    lighthouse-geth-1       = 1100
    lighthouse-geth-2       = 1100
    lighthouse-geth-3       = 1100
    lighthouse-besu-1       = 1100
    lighthouse-besu-2       = 1100
    lighthouse-nethermind-1 = 1050
    lighthouse-nethermind-2 = 1050
    lighthouse-erigon-1     = 550
    lighthouse-erigon-2     = 550
  }
}

resource "digitalocean_volume" "recovery" {
  for_each                 = local.recovery_volume_sizes
  region                   = "fra1"
  name                     = "${var.ethereum_network}-${each.key}-recovery"
  size                     = each.value
  initial_filesystem_type  = "ext4"
  initial_filesystem_label = "pbt-recovery"
  description              = "PBT-1 compressed snapshot recovery archive for ${each.key}"
  tags                     = ["Owner:Devops", "EthNetwork:${var.ethereum_network}", "Purpose:snapshot-recovery"]
}

resource "digitalocean_volume_attachment" "recovery" {
  for_each   = local.recovery_volume_sizes
  droplet_id = digitalocean_droplet.main[each.key].id
  volume_id  = digitalocean_volume.recovery[each.key].id
}

resource "digitalocean_project_resources" "recovery" {
  for_each  = digitalocean_volume.recovery
  project   = data.digitalocean_project.main.id
  resources = [each.value.urn]
}
