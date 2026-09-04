////////////////////////////////////////////////////////////////////////////////////////
//                        DEVNET-10 — DNS ONLY, NO COMPUTE
//
// The devnet-10 fleet is the devnet-9 fleet, still owned by terraform/devnet-9. Compute
// is not managed here. Only the bootnode A/AAAA records and the NS delegation for
// srv.glamsterdam-devnet-10 live in this state; every per-node name is served from the
// delegated zone, which the dns_server role generates from the ansible inventory.
////////////////////////////////////////////////////////////////////////////////////////

terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 3.0"
    }
  }
}

terraform {
  backend "s3" {
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    endpoints                   = { s3 = "https://fra1.digitaloceanspaces.com" }
    skip_requesting_account_id  = true
    skip_s3_checksum            = true
    region                      = "us-east-1"
    bucket                      = "merge-testnets"
    key                         = "infrastructure/devnet-10/terraform.tfstate"
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

////////////////////////////////////////////////////////////////////////////////////////
//                                        VARIABLES
////////////////////////////////////////////////////////////////////////////////////////
variable "cloudflare_api_token" {
  type        = string
  sensitive   = true
  description = "Cloudflare API Token"
}

variable "ethereum_network" {
  type    = string
  default = "glamsterdam-devnet-10"
}

variable "dns_zone" {
  type    = string
  default = "ethpandaops.io"
}

# Keep in sync with the bootnode entries in
# ansible/inventories/devnet-10/inventory.ini.
variable "bootnodes" {
  description = "Bootnode hostname => public addresses. ipv6 may be null."
  type = map(object({
    ipv4 = string
    ipv6 = string
  }))
  default = {
    "bootnode-1" = { ipv4 = "209.38.42.223", ipv6 = "2a03:b0c0:2:f0:0:1:ea77:f001" }
    "bootnode-2" = { ipv4 = "168.144.78.231", ipv6 = "2400:6180:100:d0:0:1:84cc:6001" }
    "bootnode-3" = { ipv4 = "134.199.192.48", ipv6 = "2604:a880:5:1::436c:0" }
    "bootnode-4" = { ipv4 = "159.203.83.209", ipv6 = "2604:a880:800:14:0:3:71fb:f000" }
  }
}
