# Temporary preparation-only space. Remove after the native N export and
# verification finish and its scratch files have been safely reclaimed.
# This is not part of the nine workers' migration storage configuration.
resource "digitalocean_volume" "export_scratch" {
  region                   = "fra1"
  name                     = "glamsterdam-pbt-1-erigon-export-scratch"
  size                     = 1500
  initial_filesystem_type  = "ext4"
  initial_filesystem_label = "pbt-export-tmp"
  description              = "Temporary Erigon N export scratch; remove before shadowfork launch"
  tags                     = ["Owner:Devops", "EthNetwork:glamsterdam-pbt-1", "Purpose:temporary-export-scratch"]
}

resource "digitalocean_volume_attachment" "export_scratch" {
  droplet_id = digitalocean_droplet.main["lighthouse-erigon-1"].id
  volume_id  = digitalocean_volume.export_scratch.id
}

resource "digitalocean_project_resources" "export_scratch" {
  project   = data.digitalocean_project.main.id
  resources = [digitalocean_volume.export_scratch.urn]
}
