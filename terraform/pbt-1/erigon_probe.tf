# Temporary capacity probe. Keep the four source VMs running while measuring
# whether a larger local NVMe device can reduce Erigon's persistence latency.
# Remove this resource after the preparation experiment is finished.
resource "digitalocean_droplet" "erigon_io_probe" {
  name       = "${var.ethereum_network}-erigon-io-probe"
  region     = "fra1"
  image      = local.digitalocean_default_image
  size       = "so-32vcpu-256gb"
  ssh_keys   = [data.digitalocean_ssh_key.main.fingerprint]
  vpc_uuid   = digitalocean_vpc.main["fra1"].id
  monitoring = true
  backups    = false
  ipv6       = false
  tags       = ["EthNetwork:${var.ethereum_network}", "Owner:Devops", "Purpose:pbt-erigon-io-probe"]
}

resource "digitalocean_project_resources" "erigon_io_probe" {
  project   = data.digitalocean_project.main.id
  resources = [digitalocean_droplet.erigon_io_probe.urn]
}

output "erigon_io_probe" {
  value = {
    id         = digitalocean_droplet.erigon_io_probe.id
    public_ip  = digitalocean_droplet.erigon_io_probe.ipv4_address
    private_ip = digitalocean_droplet.erigon_io_probe.ipv4_address_private
    size       = digitalocean_droplet.erigon_io_probe.size
  }
}
