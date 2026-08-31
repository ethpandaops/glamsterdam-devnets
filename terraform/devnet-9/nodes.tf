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
########################################################################################

variable "nodes" {
  description = "List of node definitions for the devnet"
  default = [
    { name = "bootnode", count = 4, cloud = "digitalocean" },
    # Buildoor
    { name = "buildoor-prysm-ethrex", count = 1, cloud = "digitalocean", builder_start = 0 },
    { name = "buildoor-lighthouse-geth", count = 1, cloud = "digitalocean", builder_start = 1 },
    { name = "buildoor-lodestar-ethrex", count = 1, cloud = "digitalocean", builder_start = 2 },
    { name = "buildoor-teku-nethermind", count = 1, cloud = "digitalocean", builder_start = 3 },

    # 1000-node stress test approximating mainnet client distribution (Aug 2026).
    # CL weights: lighthouse 43%, prysm 31%, teku 14%, nimbus 8%, lodestar 3%, grandine 1%.
    # EL weights: geth 41%, nethermind 30%, reth 14%, besu 8%, erigon 4%,
    #             plus small ethrex 2% / nimbusel 1% slices for coverage.
    # Per-combo counts = CL row total split by EL weights, largest-remainder rounded
    # so rows and columns hit the targets exactly. 1000 validators per node,
    # contiguous ranges in file order over [0,1000000) (NUMBER_OF_VALIDATORS=1000000).

    # Lighthouse (430)
    { name = "lighthouse-geth", count = 176, cloud = "digitalocean", supernode = true, validator_start = 0, validator_end = 176000 },
    { name = "lighthouse-nethermind", count = 129, cloud = "digitalocean", supernode = true, validator_start = 176000, validator_end = 305000 },
    { name = "lighthouse-reth", count = 60, cloud = "digitalocean", supernode = true, validator_start = 305000, validator_end = 365000 },
    { name = "lighthouse-besu", count = 35, cloud = "digitalocean", supernode = true, validator_start = 365000, validator_end = 400000 },
    { name = "lighthouse-erigon", count = 17, cloud = "digitalocean", supernode = true, validator_start = 400000, validator_end = 417000 },
    { name = "lighthouse-ethrex", count = 9, cloud = "digitalocean", supernode = true, validator_start = 417000, validator_end = 426000 },
    { name = "lighthouse-nimbusel", count = 4, cloud = "digitalocean", supernode = true, validator_start = 426000, validator_end = 430000 },

    # Prysm (310)
    { name = "prysm-geth", count = 127, cloud = "digitalocean", supernode = true, validator_start = 430000, validator_end = 557000 },
    { name = "prysm-nethermind", count = 93, cloud = "digitalocean", supernode = true, validator_start = 557000, validator_end = 650000 },
    { name = "prysm-reth", count = 44, cloud = "digitalocean", supernode = true, validator_start = 650000, validator_end = 694000 },
    { name = "prysm-besu", count = 25, cloud = "digitalocean", supernode = true, validator_start = 694000, validator_end = 719000 },
    { name = "prysm-erigon", count = 12, cloud = "digitalocean", supernode = true, validator_start = 719000, validator_end = 731000 },
    { name = "prysm-ethrex", count = 6, cloud = "digitalocean", supernode = true, validator_start = 731000, validator_end = 737000 },
    { name = "prysm-nimbusel", count = 3, cloud = "digitalocean", supernode = true, validator_start = 737000, validator_end = 740000 },

    # Teku (140)
    { name = "teku-geth", count = 57, cloud = "digitalocean", supernode = true, validator_start = 740000, validator_end = 797000 },
    { name = "teku-nethermind", count = 42, cloud = "digitalocean", supernode = true, validator_start = 797000, validator_end = 839000 },
    { name = "teku-reth", count = 20, cloud = "digitalocean", supernode = true, validator_start = 839000, validator_end = 859000 },
    { name = "teku-besu", count = 11, cloud = "digitalocean", supernode = true, validator_start = 859000, validator_end = 870000 },
    { name = "teku-erigon", count = 6, cloud = "digitalocean", supernode = true, validator_start = 870000, validator_end = 876000 },
    { name = "teku-ethrex", count = 2, cloud = "digitalocean", supernode = true, validator_start = 876000, validator_end = 878000 },
    { name = "teku-nimbusel", count = 2, cloud = "digitalocean", supernode = true, validator_start = 878000, validator_end = 880000 },

    # Nimbus (80)
    { name = "nimbus-geth", count = 33, cloud = "digitalocean", supernode = true, validator_start = 880000, validator_end = 913000 },
    { name = "nimbus-nethermind", count = 24, cloud = "digitalocean", supernode = true, validator_start = 913000, validator_end = 937000 },
    { name = "nimbus-reth", count = 11, cloud = "digitalocean", supernode = true, validator_start = 937000, validator_end = 948000 },
    { name = "nimbus-besu", count = 6, cloud = "digitalocean", supernode = true, validator_start = 948000, validator_end = 954000 },
    { name = "nimbus-erigon", count = 3, cloud = "digitalocean", supernode = true, validator_start = 954000, validator_end = 957000 },
    { name = "nimbus-ethrex", count = 2, cloud = "digitalocean", supernode = true, validator_start = 957000, validator_end = 959000 },
    { name = "nimbus-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 959000, validator_end = 960000 },

    # Lodestar (30)
    { name = "lodestar-geth", count = 13, cloud = "digitalocean", supernode = true, validator_start = 960000, validator_end = 973000 },
    { name = "lodestar-nethermind", count = 9, cloud = "digitalocean", supernode = true, validator_start = 973000, validator_end = 982000 },
    { name = "lodestar-reth", count = 4, cloud = "digitalocean", supernode = true, validator_start = 982000, validator_end = 986000 },
    { name = "lodestar-besu", count = 2, cloud = "digitalocean", supernode = true, validator_start = 986000, validator_end = 988000 },
    { name = "lodestar-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 988000, validator_end = 989000 },
    { name = "lodestar-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 989000, validator_end = 990000 },

    # Grandine (10)
    { name = "grandine-geth", count = 4, cloud = "digitalocean", supernode = true, validator_start = 990000, validator_end = 994000 },
    { name = "grandine-nethermind", count = 3, cloud = "digitalocean", supernode = true, validator_start = 994000, validator_end = 997000 },
    { name = "grandine-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 997000, validator_end = 998000 },
    { name = "grandine-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 998000, validator_end = 999000 },
    { name = "grandine-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 999000, validator_end = 1000000 },

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
