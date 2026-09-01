////////////////////////////////////////////////////////////////////////////////////////
//                                        VARIABLES
////////////////////////////////////////////////////////////////////////////////////////
variable "digitalocean_project_name" {
  type    = string
  default = "glamsterdam-devnets"
}

variable "digitalocean_ssh_key_name" {
  type    = string
  default = "shared-devops-eth2"
}

variable "digitalocean_supernode_size" {
  type    = string
  default = "s-8vcpu-32gb-640gb-intel"
}

variable "digitalocean_fullnode_size" {
  type    = string
  default = "s-8vcpu-16gb"
}

variable "digitalocean_regions" {
  default = [
    "nyc3",
    "sgp1",
    "lon1",
    "sfo2",
    "ams3",
    "fra1",
    "atl1",
    "blr1",
    "sfo3",
    "syd1"
  ]
}

variable "digitalocean_region_overrides" {
  description = "Per-instance region overrides for instances whose hashed region had no capacity at deploy time. Keys are instance ids (name-index). Only add instances that do not exist yet; changing an existing instance region forces destroy/recreate."
  default = {
    "buildoor-teku-nethermind-1" = "ams3"
    "grandine-besu-1" = "blr1"
    "grandine-nethermind-3" = "fra1"
    "lighthouse-besu-11" = "lon1"
    "lighthouse-besu-21" = "ams3"
    "lighthouse-besu-31" = "sfo2"
    "lighthouse-erigon-16" = "sfo3"
    "lighthouse-erigon-6" = "sgp1"
    "lighthouse-ethrex-2" = "syd1"
    "lighthouse-ethrex-9" = "ams3"
    "lighthouse-geth-1" = "blr1"
    "lighthouse-geth-100" = "blr1"
    "lighthouse-geth-106" = "lon1"
    "lighthouse-geth-111" = "sfo2"
    "lighthouse-geth-121" = "sfo2"
    "lighthouse-geth-128" = "sfo3"
    "lighthouse-geth-133" = "sgp1"
    "lighthouse-geth-14" = "syd1"
    "lighthouse-geth-140" = "ams3"
    "lighthouse-geth-165" = "blr1"
    "lighthouse-geth-169" = "sfo3"
    "lighthouse-geth-20" = "lon1"
    "lighthouse-geth-5" = "sgp1"
    "lighthouse-geth-57" = "sfo2"
    "lighthouse-geth-59" = "sfo3"
    "lighthouse-geth-6" = "sgp1"
    "lighthouse-geth-63" = "syd1"
    "lighthouse-geth-64" = "ams3"
    "lighthouse-geth-77" = "blr1"
    "lighthouse-nethermind-104" = "fra1"
    "lighthouse-nethermind-105" = "lon1"
    "lighthouse-nethermind-111" = "nyc3"
    "lighthouse-nethermind-126" = "sfo2"
    "lighthouse-nethermind-23" = "sfo3"
    "lighthouse-nethermind-3" = "sgp1"
    "lighthouse-nethermind-40" = "syd1"
    "lighthouse-nethermind-44" = "ams3"
    "lighthouse-nethermind-5" = "blr1"
    "lighthouse-nethermind-52" = "syd1"
    "lighthouse-nethermind-56" = "lon1"
    "lighthouse-nethermind-57" = "nyc3"
    "lighthouse-nethermind-65" = "sfo2"
    "lighthouse-nethermind-75" = "sfo3"
    "lighthouse-nethermind-86" = "sgp1"
    "lighthouse-nethermind-90" = "syd1"
    "lighthouse-nethermind-93" = "ams3"
    "lighthouse-reth-20" = "blr1"
    "lighthouse-reth-25" = "fra1"
    "lighthouse-reth-33" = "lon1"
    "lighthouse-reth-34" = "ams3"
    "lighthouse-reth-37" = "sfo2"
    "lighthouse-reth-40" = "sfo3"
    "lighthouse-reth-54" = "sgp1"
    "lighthouse-reth-55" = "syd1"
    "lighthouse-reth-58" = "ams3"
    "lighthouse-reth-7" = "blr1"
    "lodestar-besu-1" = "blr1"
    "lodestar-besu-2" = "lon1"
    "lodestar-geth-12" = "sfo2"
    "lodestar-nethermind-2" = "sfo2"
    "nimbus-besu-5" = "sfo3"
    "nimbus-geth-12" = "sgp1"
    "nimbus-geth-31" = "syd1"
    "nimbus-nethermind-10" = "ams3"
    "nimbus-nethermind-17" = "blr1"
    "nimbus-nethermind-23" = "fra1"
    "nimbus-nethermind-24" = "lon1"
    "nimbus-reth-7" = "sfo3"
    "prysm-besu-8" = "sfo2"
    "prysm-erigon-1" = "sfo3"
    "prysm-erigon-5" = "sgp1"
    "prysm-geth-106" = "syd1"
    "prysm-geth-109" = "ams3"
    "prysm-geth-119" = "blr1"
    "prysm-geth-125" = "sgp1"
    "prysm-geth-21" = "lon1"
    "prysm-geth-27" = "syd1"
    "prysm-geth-3" = "sfo2"
    "prysm-geth-30" = "sfo3"
    "prysm-geth-46" = "sgp1"
    "prysm-geth-49" = "syd1"
    "prysm-geth-5" = "ams3"
    "prysm-geth-6" = "blr1"
    "prysm-geth-61" = "ams3"
    "prysm-geth-76" = "lon1"
    "prysm-geth-85" = "blr1"
    "prysm-geth-95" = "sfo2"
    "prysm-geth-97" = "sfo3"
    "prysm-nethermind-15" = "sgp1"
    "prysm-nethermind-18" = "syd1"
    "prysm-nethermind-25" = "ams3"
    "prysm-nethermind-30" = "blr1"
    "prysm-nethermind-36" = "fra1"
    "prysm-nethermind-39" = "lon1"
    "prysm-nethermind-4" = "nyc3"
    "prysm-nethermind-64" = "sfo2"
    "prysm-nethermind-68" = "sfo3"
    "prysm-nethermind-71" = "sgp1"
    "prysm-nethermind-77" = "syd1"
    "prysm-nethermind-78" = "ams3"
    "prysm-nethermind-80" = "blr1"
    "prysm-nethermind-83" = "fra1"
    "prysm-nethermind-86" = "sfo2"
    "prysm-nethermind-91" = "sfo3"
    "prysm-nimbusel-1" = "sfo2"
    "prysm-reth-10" = "sfo3"
    "prysm-reth-16" = "sgp1"
    "prysm-reth-23" = "syd1"
    "prysm-reth-24" = "ams3"
    "prysm-reth-3" = "blr1"
    "prysm-reth-31" = "fra1"
    "prysm-reth-4" = "lon1"
    "prysm-reth-41" = "sgp1"
    "prysm-reth-7" = "sfo2"
    "teku-erigon-3" = "sfo3"
    "teku-geth-35" = "sgp1"
    "teku-geth-37" = "syd1"
    "teku-geth-41" = "ams3"
    "teku-geth-46" = "blr1"
    "teku-geth-49" = "fra1"
    "teku-geth-5" = "lon1"
    "teku-geth-56" = "syd1"
    "teku-geth-6" = "sfo2"
    "teku-geth-7" = "sfo3"
    "teku-nethermind-2" = "sgp1"
    "teku-nethermind-20" = "syd1"
    "teku-nethermind-29" = "ams3"
    "teku-nethermind-33" = "blr1"
    "teku-nethermind-36" = "ams3"
    "teku-nethermind-37" = "blr1"
    "teku-nethermind-42" = "sfo2"
    "teku-nethermind-8" = "sfo2"
    "teku-nethermind-9" = "sfo3"
    "teku-reth-10" = "sgp1"
  }
}

////////////////////////////////////////////////////////////////////////////////////////
//                                        LOCALS
////////////////////////////////////////////////////////////////////////////////////////
locals {
  # Replacement regions get fresh CIDR slots; the original nyc1/tor1 slots (0, 6)
  # must not be reused (DO rejects overlapping VPC ranges account-wide).
  digitalocean_vpc_cidr_slot_override = {
    nyc3 = 10
    atl1 = 11
  }

  digitalocean_vpcs = {
    for region in var.digitalocean_regions : region => {
      name     = "${var.ethereum_network}-${region}"
      region   = region
      ip_range = cidrsubnet(var.base_cidr_block, 8, lookup(local.digitalocean_vpc_cidr_slot_override, region, index(var.digitalocean_regions, region)))
    }
  }
}

locals {
  digitalocean_vm_groups = flatten([
    for node in local.digitalocean_nodes : [
      for i in range(0, node.count) : {
        group_name = node.name
        id         = "${node.name}-${node.start_index + i + 1}"
        vms = {
          "${i + 1}" = {
            # Validator range for this instance
            val_start = node.validator_start + (i * (node.validator_end - node.validator_start) / node.count)
            val_end = min(
              node.validator_start + ((i + 1) * (node.validator_end - node.validator_start) / node.count),
              node.validator_end
            )
            validator_count = node.count > 0 ? (node.validator_end - node.validator_start) / node.count : 0

            # Builder index for buildoor nodes (start index + instance offset); null = no tag
            builder_index = node.builder_start != null ? node.builder_start + i : null

            # Supernode: explicit > bootnode/mev > validator_count >= 128
            supernode = (
              node.supernode != null ? node.supernode :
              can(regex("(bootnode|mev)", node.name)) ? true :
              (node.count > 0 ? (node.validator_end - node.validator_start) / node.count >= 128 : false)
            )

            region = node.region != null ? node.region : lookup(
              var.digitalocean_region_overrides,
              "${node.name}-${node.start_index + i + 1}",
              var.digitalocean_regions[
                parseint(substr(md5("${node.name}-${node.start_index + i + 1}"), 0, 8), 16) % length(var.digitalocean_regions)
              ]
            )
            ipv6 = node.ipv6
            arch = "amd64"
          }
        }
      }
    ]
  ])
}

locals {
  digitalocean_default_region = "ams3"
  digitalocean_default_size   = var.digitalocean_fullnode_size
  digitalocean_default_image  = "debian-13-x64"
  digitalocean_global_tags = [
    "Owner:Devops",
    "EthNetwork:${var.ethereum_network}"
  ]

  digitalocean_vms = flatten([
    for group in local.digitalocean_vm_groups : [
      for vm_key, vm in group.vms : {
        id        = group.id
        group_key = group.group_name
        vm_key    = vm_key

        name        = group.id
        ssh_keys    = [data.digitalocean_ssh_key.main.fingerprint]
        region      = vm.region
        image       = local.digitalocean_default_image
        size        = vm.supernode ? var.digitalocean_supernode_size : var.digitalocean_fullnode_size
        resize_disk = true
        monitoring  = true
        backups     = false
        ipv6        = vm.ipv6
        vpc_uuid    = digitalocean_vpc.main[vm.region].id

        tags = concat(local.digitalocean_global_tags, [
          "group_name:${group.group_name}",
          "val_start:${vm.val_start}",
          "val_end:${vm.val_end}",
          "supernode:${vm.supernode ? "True" : "False"}",
          "arch:${vm.arch}",
          ], compact([
            can(regex("bootnode", group.group_name)) ? "bootnode:${var.ethereum_network}" : null,
            can(regex("mev-relay", group.group_name)) ? "mev-relay:${var.ethereum_network}" : null,
            vm.builder_index != null ? "builder_index:${vm.builder_index}" : null
        ]))
      }
    ]
  ])
}

////////////////////////////////////////////////////////////////////////////////////////
//                                  DIGITALOCEAN RESOURCES
////////////////////////////////////////////////////////////////////////////////////////
data "digitalocean_project" "main" {
  name = var.digitalocean_project_name
}

data "digitalocean_ssh_key" "main" {
  name = var.digitalocean_ssh_key_name
}

resource "digitalocean_vpc" "main" {
  for_each = local.digitalocean_vpcs

  name     = each.value["name"]
  region   = each.value["region"]
  ip_range = each.value["ip_range"]
}

resource "digitalocean_droplet" "main" {
  for_each = {
    for vm in local.digitalocean_vms : vm.id => vm
  }
  name        = "${var.ethereum_network}-${each.value.name}"
  region      = each.value.region
  ssh_keys    = each.value.ssh_keys
  image       = each.value.image
  size        = each.value.size
  resize_disk = each.value.resize_disk
  monitoring  = each.value.monitoring
  backups     = each.value.backups
  ipv6        = each.value.ipv6
  vpc_uuid    = each.value.vpc_uuid
  tags        = each.value.tags
}

resource "digitalocean_project_resources" "droplets" {
  for_each  = digitalocean_droplet.main
  project   = data.digitalocean_project.main.id
  resources = [each.value.urn]
}
