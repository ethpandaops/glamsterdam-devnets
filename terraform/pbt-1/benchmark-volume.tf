# One operator-requested volume for comparing network storage with local NVMe.
# Placement of migration data/recovery copies remains undecided.
resource "digitalocean_volume" "besu_benchmark" {
  region                   = "fra1"
  name                     = "glamsterdam-pbt-1-besu-benchmark"
  size                     = 2500 # GiB (~2.68 decimal TB)
  initial_filesystem_type  = "ext4"
  initial_filesystem_label = "pbt-bench"
  description              = "PBT-1 storage comparison on the idle Besu source VM"
  tags                     = ["Owner:Devops", "EthNetwork:pbt-1", "Purpose:storage-benchmark"]
}

resource "digitalocean_volume_attachment" "besu_benchmark" {
  droplet_id = digitalocean_droplet.main["lighthouse-besu-1"].id
  volume_id  = digitalocean_volume.besu_benchmark.id
}

resource "digitalocean_project_resources" "benchmark_volume" {
  project   = data.digitalocean_project.main.id
  resources = [digitalocean_volume.besu_benchmark.urn]
}
