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
    { name = "bootnode", count = 2, cloud = "digitalocean" },
    # Buildoor
    { name = "buildoor-prysm-ethrex", count = 1, cloud = "digitalocean", builder_start = 0 },
    { name = "buildoor-lighthouse-geth", count = 1, cloud = "digitalocean", builder_start = 1 },
    { name = "buildoor-lodestar-ethrex", count = 1, cloud = "digitalocean", builder_start = 2 },
    { name = "buildoor-teku-nethermind", count = 1, cloud = "digitalocean", builder_start = 3 },

    # Validator layout: 6 CL x 7 EL = 42 combos x 2000 keys over [0,84000),
    # same ordering as devnet-7's final grid; grandine and erigon interleaved
    # over [60000,84000). Every key exists at genesis (NUMBER_OF_VALIDATORS=84000,
    # see group_vars/all/all.yaml).

    # Ethrex
    { name = "prysm-ethrex", count = 2, cloud = "digitalocean", supernode = true, validator_start = 0, validator_end = 2000 },
    { name = "lodestar-ethrex", count = 2, cloud = "digitalocean", supernode = true, validator_start = 2000, validator_end = 4000 },
    { name = "lighthouse-ethrex", count = 2, cloud = "digitalocean", supernode = true, validator_start = 4000, validator_end = 6000 },
    { name = "teku-ethrex", count = 2, cloud = "digitalocean", supernode = true, validator_start = 6000, validator_end = 8000 },
    { name = "nimbus-ethrex", count = 2, cloud = "digitalocean", supernode = true, validator_start = 8000, validator_end = 10000 },

    # Geth
    { name = "prysm-geth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 10000, validator_end = 12000 },
    { name = "lodestar-geth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 12000, validator_end = 14000 },
    { name = "lighthouse-geth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 14000, validator_end = 16000 },
    { name = "teku-geth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 16000, validator_end = 18000 },
    { name = "nimbus-geth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 18000, validator_end = 20000 },

    # Nethermind
    { name = "prysm-nethermind", count = 2, cloud = "digitalocean", supernode = true, validator_start = 20000, validator_end = 22000 },
    { name = "lodestar-nethermind", count = 2, cloud = "digitalocean", supernode = true, validator_start = 22000, validator_end = 24000 },
    { name = "lighthouse-nethermind", count = 2, cloud = "digitalocean", supernode = true, validator_start = 24000, validator_end = 26000 },
    { name = "teku-nethermind", count = 2, cloud = "digitalocean", supernode = true, validator_start = 26000, validator_end = 28000 },
    { name = "nimbus-nethermind", count = 2, cloud = "digitalocean", supernode = true, validator_start = 28000, validator_end = 30000 },

    # Reth
    { name = "prysm-reth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 30000, validator_end = 32000 },
    { name = "lodestar-reth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 32000, validator_end = 34000 },
    { name = "lighthouse-reth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 34000, validator_end = 36000 },
    { name = "teku-reth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 36000, validator_end = 38000 },
    { name = "nimbus-reth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 38000, validator_end = 40000 },

    # Besu
    { name = "prysm-besu", count = 2, cloud = "digitalocean", supernode = true, validator_start = 40000, validator_end = 42000 },
    { name = "lodestar-besu", count = 2, cloud = "digitalocean", supernode = true, validator_start = 42000, validator_end = 44000 },
    { name = "lighthouse-besu", count = 2, cloud = "digitalocean", supernode = true, validator_start = 44000, validator_end = 46000 },
    { name = "teku-besu", count = 2, cloud = "digitalocean", supernode = true, validator_start = 46000, validator_end = 48000 },
    { name = "nimbus-besu", count = 2, cloud = "digitalocean", supernode = true, validator_start = 48000, validator_end = 50000 },

    # Nimbusel
    { name = "prysm-nimbusel", count = 2, cloud = "digitalocean", supernode = true, validator_start = 50000, validator_end = 52000 },
    { name = "lodestar-nimbusel", count = 2, cloud = "digitalocean", supernode = true, validator_start = 52000, validator_end = 54000 },
    { name = "lighthouse-nimbusel", count = 2, cloud = "digitalocean", supernode = true, validator_start = 54000, validator_end = 56000 },
    { name = "teku-nimbusel", count = 2, cloud = "digitalocean", supernode = true, validator_start = 56000, validator_end = 58000 },
    { name = "nimbus-nimbusel", count = 2, cloud = "digitalocean", supernode = true, validator_start = 58000, validator_end = 60000 },

    { name = "grandine-ethrex", count = 2, cloud = "digitalocean", supernode = true, validator_start = 60000, validator_end = 62000 },
    { name = "grandine-geth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 64000, validator_end = 66000 },
    { name = "grandine-nethermind", count = 2, cloud = "digitalocean", supernode = true, validator_start = 68000, validator_end = 70000 },
    { name = "grandine-reth", count = 2, cloud = "digitalocean", supernode = true, validator_start = 72000, validator_end = 74000 },
    { name = "grandine-besu", count = 2, cloud = "digitalocean", supernode = true, validator_start = 76000, validator_end = 78000 },
    { name = "grandine-nimbusel", count = 2, cloud = "digitalocean", supernode = true, validator_start = 80000, validator_end = 82000 },

    # Erigon: the block after its grandine neighbor.
    { name = "prysm-erigon", count = 2, cloud = "digitalocean", supernode = true, validator_start = 62000, validator_end = 64000 },
    { name = "lodestar-erigon", count = 2, cloud = "digitalocean", supernode = true, validator_start = 66000, validator_end = 68000 },
    { name = "lighthouse-erigon", count = 2, cloud = "digitalocean", supernode = true, validator_start = 70000, validator_end = 72000 },
    { name = "teku-erigon", count = 2, cloud = "digitalocean", supernode = true, validator_start = 74000, validator_end = 76000 },
    { name = "nimbus-erigon", count = 2, cloud = "digitalocean", supernode = true, validator_start = 78000, validator_end = 80000 },
    { name = "grandine-erigon", count = 2, cloud = "digitalocean", supernode = true, validator_start = 82000, validator_end = 84000 },

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
