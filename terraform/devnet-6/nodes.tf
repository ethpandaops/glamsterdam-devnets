########################################################################################
#                                    NODE DEFINITIONS
#
# Define your fleet as a list of node entries. Each entry supports:
#
#   Required:
#     - name            : Node type (e.g., "lighthouse-geth-super", "bootnode")
#     - count           : Number of instances
#     - cloud           : "digitalocean" or "hetzner"
#
#   Optional:
#     - validator_start : First validator index (default: 0)
#     - validator_end   : Last validator index (default: 0)
#     - size            : Instance size override (provider-specific)
#     - region          : Region override (digitalocean) or location (hetzner)
#     - supernode       : Force supernode=true/false (auto-detected from name)
#     - builder_start   : First builder index (buildoor nodes only). Exposes a
#                         builder_index=N server tag and inventory var per instance.
#
# Examples:
#   { name = "bootnode", count = 1, cloud = "digitalocean" }
#   { name = "lighthouse-geth-super", count = 2, cloud = "hetzner", validator_start = 0, validator_end = 200 }
#   { name = "mev-relay", count = 1, cloud = "hetzner", size = "ccx53" }
#
########################################################################################

variable "nodes" {
  description = "List of node definitions for the devnet"
  default = [
    { name = "bootnode", count = 1, cloud = "digitalocean" },
    # Buildoor
    { name = "buildoor-prysm-ethrex", count = 1, cloud = "digitalocean", builder_start = 0 },
    { name = "buildoor-lighthouse-geth", count = 1, cloud = "digitalocean", builder_start = 1 },
    { name = "buildoor-lodestar-besu", count = 1, cloud = "digitalocean", builder_start = 2 },

    # Ethrex
    { name = "prysm-ethrex", count = 1, cloud = "digitalocean", validator_start = 0, validator_end = 200 },
    { name = "lodestar-ethrex", count = 1, cloud = "digitalocean", validator_start = 200, validator_end = 400 },
    { name = "lighthouse-ethrex", count = 1, cloud = "digitalocean", validator_start = 400, validator_end = 600 },
    { name = "nimbus-ethrex", count = 1, cloud = "digitalocean", validator_start = 600, validator_end = 800 },
    { name = "teku-ethrex", count = 1, cloud = "digitalocean", validator_start = 800, validator_end = 1000 },

    # Geth
    { name = "prysm-geth", count = 1, cloud = "digitalocean", validator_start = 1000, validator_end = 1200 },
    { name = "lodestar-geth", count = 1, cloud = "digitalocean", validator_start = 1200, validator_end = 1400 },
    { name = "lighthouse-geth", count = 1, cloud = "digitalocean", validator_start = 1400, validator_end = 1600 },
    { name = "nimbus-geth", count = 1, cloud = "digitalocean", validator_start = 1600, validator_end = 1800 },
    { name = "teku-geth", count = 1, cloud = "digitalocean", validator_start = 1800, validator_end = 2000 },

    # Besu
    { name = "prysm-besu", count = 1, cloud = "digitalocean", validator_start = 2000, validator_end = 2200 },
    { name = "lodestar-besu", count = 1, cloud = "digitalocean", validator_start = 2200, validator_end = 2400 },
    { name = "lighthouse-besu", count = 1, cloud = "digitalocean", validator_start = 2400, validator_end = 2600 },
    { name = "nimbus-besu", count = 1, cloud = "digitalocean", validator_start = 2600, validator_end = 2800 },
    { name = "teku-besu", count = 1, cloud = "digitalocean", validator_start = 2800, validator_end = 3000 },

    # Nethermind
    { name = "prysm-nethermind", count = 1, cloud = "digitalocean", validator_start = 3000, validator_end = 3200 },
    { name = "lodestar-nethermind", count = 1, cloud = "digitalocean", validator_start = 3200, validator_end = 3400 },
    { name = "lighthouse-nethermind", count = 1, cloud = "digitalocean", validator_start = 3400, validator_end = 3600 },
    { name = "nimbus-nethermind", count = 1, cloud = "digitalocean", validator_start = 3600, validator_end = 3800 },
    { name = "teku-nethermind", count = 1, cloud = "digitalocean", validator_start = 3800, validator_end = 4000 },

    # NimbusEL
    { name = "prysm-nimbusel", count = 1, cloud = "digitalocean", validator_start = 4000, validator_end = 4200 },
    { name = "lodestar-nimbusel", count = 1, cloud = "digitalocean", validator_start = 4200, validator_end = 4400 },
    { name = "lighthouse-nimbusel", count = 1, cloud = "digitalocean", validator_start = 4400, validator_end = 4600 },
    { name = "nimbus-nimbusel", count = 1, cloud = "digitalocean", validator_start = 4600, validator_end = 4800 },
    { name = "teku-nimbusel", count = 1, cloud = "digitalocean", validator_start = 4800, validator_end = 5000 },

    # Reth
    { name = "prysm-reth", count = 1, cloud = "digitalocean", validator_start = 5000, validator_end = 5200 },
    { name = "lodestar-reth", count = 1, cloud = "digitalocean", validator_start = 5200, validator_end = 5400 },
    { name = "lighthouse-reth", count = 1, cloud = "digitalocean", validator_start = 5400, validator_end = 5600 },
    { name = "nimbus-reth", count = 1, cloud = "digitalocean", validator_start = 5600, validator_end = 5800 },
    { name = "teku-reth", count = 1, cloud = "digitalocean", validator_start = 5800, validator_end = 6000 },

    # Grandine
    { name = "grandine-ethrex", count = 1, cloud = "digitalocean", validator_start = 6000, validator_end = 6200 },
    { name = "grandine-geth", count = 1, cloud = "digitalocean", validator_start = 6200, validator_end = 6400 },
    { name = "grandine-besu", count = 1, cloud = "digitalocean", validator_start = 6400, validator_end = 6600 },
    { name = "grandine-nethermind", count = 1, cloud = "digitalocean", validator_start = 6600, validator_end = 6800 },
    { name = "grandine-nimbusel", count = 1, cloud = "digitalocean", validator_start = 6800, validator_end = 7000 },
    { name = "grandine-reth", count = 1, cloud = "digitalocean", validator_start = 7000, validator_end = 7200 },

    # Erigon
    { name = "prysm-erigon", count = 1, cloud = "digitalocean", validator_start = 7200, validator_end = 7400 },
    { name = "lodestar-erigon", count = 1, cloud = "digitalocean", validator_start = 7400, validator_end = 7600 },
    { name = "lighthouse-erigon", count = 1, cloud = "digitalocean", validator_start = 7600, validator_end = 7800 },
    { name = "nimbus-erigon", count = 1, cloud = "digitalocean", validator_start = 7800, validator_end = 8000 },
    { name = "teku-erigon", count = 1, cloud = "digitalocean", validator_start = 8000, validator_end = 8200 }

  ]

  validation {
    condition = alltrue([
      for n in var.nodes :
      try(n.validator_start, 0) >= 0 && try(n.validator_start, 0) <= try(n.validator_end, 0)
    ])
    error_message = "Each node must satisfy 0 <= validator_start <= validator_end. Omit both fields (or set both to 0) for nodes without validators."
  }

  validation {
    condition = alltrue(flatten([
      for i, a in var.nodes : [
        for j, b in var.nodes :
        i >= j ||
        try(a.validator_end, 0) == 0 ||
        try(b.validator_end, 0) == 0 ||
        try(a.validator_end, 0) <= try(b.validator_start, 0) ||
        try(b.validator_end, 0) <= try(a.validator_start, 0)
      ]
    ]))
    error_message = "Validator ranges overlap between nodes. Each [validator_start, validator_end) interval must be disjoint from every other node's interval."
  }
}
