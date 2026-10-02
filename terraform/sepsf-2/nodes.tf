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
    # Every EL node restores a ~1 TB sepolia snapshot (11820000), so every node with
    # an EL - bootnode and buildoors included - gets the 1.8 TB storage-optimized size.
    { name = "bootnode", count = 1, cloud = "digitalocean" },
    { name = "buildoor-lighthouse-geth", count = 1, cloud = "digitalocean", size = "so1_5-8vcpu-64gb-intel", builder_start = 0 },
    { name = "buildoor-teku-nethermind", count = 1, cloud = "digitalocean", size = "so1_5-8vcpu-64gb-intel", builder_start = 1 },

    # Full 6 CL x 6 EL matrix, every pair once: 36 x 1000 keys over [0,36000)
    # (NUMBER_OF_VALIDATORS=36000). Nimbus-el (no validators) below the ethrex nodes.

    # Geth
    { name = "lighthouse-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 0, validator_end = 1000 },
    { name = "prysm-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1000, validator_end = 2000 },
    { name = "teku-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2000, validator_end = 3000 },
    { name = "nimbus-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3000, validator_end = 4000 },
    { name = "lodestar-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 4000, validator_end = 5000 },
    { name = "grandine-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 5000, validator_end = 6000 },

    # Nethermind
    { name = "lighthouse-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 6000, validator_end = 7000 },
    { name = "prysm-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 7000, validator_end = 8000 },
    { name = "teku-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 8000, validator_end = 9000 },
    { name = "nimbus-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 9000, validator_end = 10000 },
    { name = "lodestar-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 10000, validator_end = 11000 },
    { name = "grandine-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 11000, validator_end = 12000 },

    # Besu
    { name = "lighthouse-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 12000, validator_end = 13000 },
    { name = "prysm-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 13000, validator_end = 14000 },
    { name = "teku-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 14000, validator_end = 15000 },
    { name = "nimbus-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 15000, validator_end = 16000 },
    { name = "lodestar-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 16000, validator_end = 17000 },
    { name = "grandine-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 17000, validator_end = 18000 },

    # Reth
    { name = "lighthouse-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 18000, validator_end = 19000 },
    { name = "prysm-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 19000, validator_end = 20000 },
    { name = "teku-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 20000, validator_end = 21000 },
    { name = "nimbus-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 21000, validator_end = 22000 },
    { name = "lodestar-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 22000, validator_end = 23000 },
    { name = "grandine-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 23000, validator_end = 24000 },

    # Erigon
    { name = "lighthouse-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 24000, validator_end = 25000 },
    { name = "prysm-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 25000, validator_end = 26000 },
    { name = "teku-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 26000, validator_end = 27000 },
    { name = "nimbus-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 27000, validator_end = 28000 },
    { name = "lodestar-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 28000, validator_end = 29000 },
    { name = "grandine-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 29000, validator_end = 30000 },

    # Ethrex
    # ethrex: no sepolia snapshot exists, so these snap-sync the state from the
    # restored geth/nethermind/besu peers (pivot is fixed at shadowfork_height until
    # genesis). Their validators miss duties until synced (1/6 of stake).
    { name = "lighthouse-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 30000, validator_end = 31000 },
    { name = "prysm-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 31000, validator_end = 32000 },
    { name = "teku-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 32000, validator_end = 33000 },
    { name = "nimbus-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 33000, validator_end = 34000 },
    { name = "lodestar-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 34000, validator_end = 35000 },
    { name = "grandine-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 35000, validator_end = 36000 },

    # Nimbus-el (added after genesis, 2026-10-02): no sepolia snapshot either; snap-syncs from
    # the restored ELs with the experimental --debug-snap-sync. No validators (all 36000 assigned).
    { name = "lighthouse-nimbusel", count = 1, cloud = "digitalocean", size = "so1_5-8vcpu-64gb-intel", region = "fra1" },
    { name = "nimbus-nimbusel", count = 1, cloud = "digitalocean", size = "so1_5-8vcpu-64gb-intel", region = "lon1" },
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
