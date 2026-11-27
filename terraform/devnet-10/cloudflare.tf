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

////////////////////////////////////////////////////////////////////////////////////////
//                                 PUBLIC HOSTS
////////////////////////////////////////////////////////////////////////////////////////

# <network>.ethpandaops.io and *.<network>.ethpandaops.io, proxied by Cloudflare
# to the cluster that runs the devnet's charts in kubernetes/<devnet>.
locals {
  tunnel_cname = "68eb8c26-dcfb-4f80-aab1-3263154e76f2.cfargotunnel.com"
}

resource "cloudflare_record" "public" {
  zone_id = data.cloudflare_zone.default.id
  name    = "${var.ethereum_network}.${data.cloudflare_zone.default.name}"
  type    = "CNAME"
  value   = local.tunnel_cname
  proxied = true
}

resource "cloudflare_record" "public_star" {
  zone_id = data.cloudflare_zone.default.id
  name    = "*.${var.ethereum_network}.${data.cloudflare_zone.default.name}"
  type    = "CNAME"
  value   = local.tunnel_cname
  proxied = true
}

# Universal SSL covers only one level below ethpandaops.io, so the second level
# needs its own certificate.
resource "cloudflare_certificate_pack" "public" {
  zone_id                = data.cloudflare_zone.default.id
  type                   = "advanced"
  hosts                  = ["*.${var.ethereum_network}.${data.cloudflare_zone.default.name}"]
  validation_method      = "txt"
  validity_days          = 90
  certificate_authority  = "lets_encrypt"
  cloudflare_branding    = false
  wait_for_active_status = true
}
