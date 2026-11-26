
////////////////////////////////////////////////////////////////////////////////////////
//                                   DNS NAMES
////////////////////////////////////////////////////////////////////////////////////////

data "cloudflare_zone" "default" {
  name = "ethpandaops.io"
}

locals {
  # Combine bootnodes from both providers
  bootnodes = merge(
    {
      for vm in local.digitalocean_vms : vm.id => {
        name     = vm.name
        has_ipv6 = vm.ipv6
        ipv4     = digitalocean_droplet.main[vm.id].ipv4_address
        ipv6     = try(digitalocean_droplet.main[vm.id].ipv6_address, null)
      } if can(regex("bootnode", vm.name))
    },
    {
      for vm in local.hcloud_vms : vm.id => {
        name     = vm.name
        has_ipv6 = vm.ipv6_enabled
        ipv4     = hcloud_server.main[vm.id].ipv4_address
        ipv6     = try(hcloud_server.main[vm.id].ipv6_address, null)
      } if can(regex("bootnode", vm.name))
    }
  )
}

resource "cloudflare_record" "server_record_v4" {
  for_each = local.bootnodes
  zone_id  = data.cloudflare_zone.default.id
  name     = "${each.value.name}.${var.ethereum_network}"
  type     = "A"
  value    = each.value.ipv4
  proxied  = false
  ttl      = 120
}

resource "cloudflare_record" "server_record_v6" {
  for_each = { for k, v in local.bootnodes : k => v if v.has_ipv6 }
  zone_id  = data.cloudflare_zone.default.id
  name     = "${each.value.name}.${var.ethereum_network}"
  type     = "AAAA"
  value    = each.value.ipv6
  proxied  = false
  ttl      = 120
}

resource "cloudflare_record" "server_record_ns" {
  for_each = local.bootnodes
  zone_id  = data.cloudflare_zone.default.id
  name     = "srv.${var.ethereum_network}"
  type     = "NS"
  value    = "${each.value.name}.${var.ethereum_network}.${data.cloudflare_zone.default.name}"
  proxied  = false
  ttl      = 120
}

////////////////////////////////////////////////////////////////////////////////////////
//                                 PUBLIC HOSTS
////////////////////////////////////////////////////////////////////////////////////////

# <network>.ethpandaops.io and *.<network>.ethpandaops.io go through the services
# cluster's Cloudflare tunnel, which sends every *.ethpandaops.io host it
# receives to traefik-devnets (ethPandaOps services-cluster/terraform). The
# devnet's charts in kubernetes/<devnet> serve them from namespace <network>.
locals {
  services_tunnel_cname = "68eb8c26-dcfb-4f80-aab1-3263154e76f2.cfargotunnel.com"
}

resource "cloudflare_record" "public" {
  zone_id = data.cloudflare_zone.default.id
  name    = "${var.ethereum_network}.${data.cloudflare_zone.default.name}"
  type    = "CNAME"
  value   = local.services_tunnel_cname
  proxied = true
}

resource "cloudflare_record" "public_star" {
  zone_id = data.cloudflare_zone.default.id
  name    = "*.${var.ethereum_network}.${data.cloudflare_zone.default.name}"
  type    = "CNAME"
  value   = local.services_tunnel_cname
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

# Adopts the records ethPandaOps' cloudflare Terraform created for this network.
# Import IDs are <zone_id>/<record_id>. An imported record reads back with its
# full name, and provider v3 replaces a record whose name differs from it, so
# both records above use full names.
import {
  to = cloudflare_record.public
  id = "68c1026fd88dcae8bf2dfa38025ea155/1bc825c40cae7ed6697cb52cede0cc05"
}

import {
  to = cloudflare_record.public_star
  id = "68c1026fd88dcae8bf2dfa38025ea155/cbae5b7bf9b4e4271ee1d1bee81fb143"
}
