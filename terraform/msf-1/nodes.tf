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
    # Every EL except nimbus-el restores a jochemnet snapshot (up to ~1.5 TB on disk),
    # so every node with an EL gets the 1.8 TB storage-optimized size.
    { name = "bootnode", count = 1, cloud = "digitalocean" },
    { name = "buildoor-lighthouse-geth", count = 1, cloud = "digitalocean", size = "so1_5-8vcpu-64gb-intel", builder_start = 0 },
    { name = "buildoor-teku-nethermind", count = 1, cloud = "digitalocean", size = "so1_5-8vcpu-64gb-intel", builder_start = 1 },

    # 12 validator nodes: every CL and every EL client twice, no CL/EL pair repeated, 3000 keys each
    # over [0,36000) (NUMBER_OF_VALIDATORS=36000), so each client holds 1/6 of stake. Names keep the
    # hosts that group_vars reference (EL bootnodes: lighthouse-geth, prysm-geth, teku-nethermind,
    # nimbus-besu, prysm-reth, teku-erigon).

    # Geth
    { name = "lighthouse-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 0, validator_end = 3000 },
    { name = "prysm-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3000, validator_end = 6000 },

    # Nethermind
    { name = "lighthouse-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 6000, validator_end = 9000 },
    { name = "teku-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 9000, validator_end = 12000 },

    # Besu
    { name = "nimbus-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 12000, validator_end = 15000 },
    { name = "lodestar-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 15000, validator_end = 18000 },

    # Reth
    { name = "prysm-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 18000, validator_end = 21000 },
    { name = "nimbus-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 21000, validator_end = 24000 },

    # Erigon
    { name = "teku-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 24000, validator_end = 27000 },
    { name = "grandine-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 27000, validator_end = 30000 },

    # Ethrex
    { name = "lodestar-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 30000, validator_end = 33000 },
    { name = "grandine-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 33000, validator_end = 36000 },

    # Nimbus-el (low priority, one node): no snapshot, snap-syncs from our ELs. No validators.
    { name = "lighthouse-nimbusel", count = 1, cloud = "digitalocean", size = "so1_5-8vcpu-64gb-intel", region = "fra1" },
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
