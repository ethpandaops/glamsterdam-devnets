////////////////////////////////////////////////////////////////////////////////////////
//                                   DNS NAMES
////////////////////////////////////////////////////////////////////////////////////////

data "cloudflare_zone" "default" {
  name = var.dns_zone
}

resource "cloudflare_record" "server_record_v4" {
  for_each = var.bootnodes
  zone_id  = data.cloudflare_zone.default.id
  name     = "${each.key}.${var.ethereum_network}"
  type     = "A"
  value    = each.value.ipv4
  proxied  = false
  ttl      = 120
}

resource "cloudflare_record" "server_record_v6" {
  for_each = { for k, v in var.bootnodes : k => v if v.ipv6 != null }
  zone_id  = data.cloudflare_zone.default.id
  name     = "${each.key}.${var.ethereum_network}"
  type     = "AAAA"
  value    = each.value.ipv6
  proxied  = false
  ttl      = 120
}

# Delegates srv.<network> to the bind instances the dns_server role runs on the
# bootnodes, which serve every per-node record.
resource "cloudflare_record" "server_record_ns" {
  for_each = var.bootnodes
  zone_id  = data.cloudflare_zone.default.id
  name     = "srv.${var.ethereum_network}"
  type     = "NS"
  value    = "${each.key}.${var.ethereum_network}.${data.cloudflare_zone.default.name}"
  proxied  = false
  ttl      = 120
}

output "bootnode_fqdns" {
  value = [for k, v in var.bootnodes : "${k}.${var.ethereum_network}.${var.dns_zone}"]
}

output "delegated_zone" {
  value = "srv.${var.ethereum_network}.${var.dns_zone}"
}
