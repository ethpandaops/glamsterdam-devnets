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
    { name = "buildoor-lodestar-ethrex", count = 1, cloud = "digitalocean", builder_start = 2 },
    { name = "buildoor-teku-nethermind", count = 1, cloud = "digitalocean", builder_start = 3 },

    # Validator layout: 6 CL x 7 EL = 42 combos over [0,3600), key ranges carried
    # over unchanged from devnet-7's final grid so the two grids stay comparable.
    # Unlike devnet-7 every key exists at genesis (NUMBER_OF_VALIDATORS=3600, see
    # group_vars/all/all.yaml) — devnet-7 only had [0,3000) at genesis because
    # grandine and erigon joined mid-devnet by deposit.
    # 30 nodes x 100 keys over [0,3000); grandine and erigon 50 keys per node,
    # interleaved over [3000,3600).

    # Ethrex
    { name = "prysm-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 0, validator_end = 100 },
    { name = "lodestar-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 300, validator_end = 400 },
    { name = "lighthouse-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 600, validator_end = 700 },
    { name = "teku-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 900, validator_end = 1000 },
    { name = "nimbus-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1400, validator_end = 1500 },

    # Geth
    { name = "prysm-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1200, validator_end = 1300 },
    { name = "lodestar-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1500, validator_end = 1600 },
    { name = "lighthouse-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1800, validator_end = 1900 },
    { name = "teku-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2100, validator_end = 2200 },
    { name = "nimbus-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1700, validator_end = 1800 },

    # Nethermind
    { name = "prysm-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2400, validator_end = 2500 },
    { name = "lodestar-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2700, validator_end = 2800 },
    { name = "lighthouse-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2900, validator_end = 3000 }, # still live-holds [2900,3600) until the combined grandine+erigon reshuffle; sole donor of that wave
    { name = "teku-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2500, validator_end = 2600 },
    { name = "nimbus-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2800, validator_end = 2900 },

    # Reth
    { name = "prysm-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 100, validator_end = 200 },
    { name = "lodestar-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 400, validator_end = 500 },
    { name = "lighthouse-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 700, validator_end = 800 },
    { name = "teku-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1000, validator_end = 1100 },
    { name = "nimbus-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2000, validator_end = 2100 },

    # Besu
    { name = "prysm-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 200, validator_end = 300 },
    { name = "lodestar-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 500, validator_end = 600 },
    { name = "lighthouse-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 800, validator_end = 900 },
    { name = "teku-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1100, validator_end = 1200 },
    { name = "nimbus-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2300, validator_end = 2400 },

    # Nimbusel
    { name = "prysm-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1300, validator_end = 1400 },
    { name = "lodestar-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1600, validator_end = 1700 },
    { name = "lighthouse-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1900, validator_end = 2000 },
    { name = "teku-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2200, validator_end = 2300 },
    { name = "nimbus-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2600, validator_end = 2700 },

    # Grandine: 50 keys per node, interleaved with erigon.
    # NOTE BUG-005 (carried from devnet-7, open at the time of writing): grandine
    # BLS-verifies the G2-infinity self-build bid signature instead of the spec
    # equality check and minority-forks on self-built Gloas blocks from peers —
    # watch these nodes closely.
    { name = "grandine-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3000, validator_end = 3050 },
    { name = "grandine-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3100, validator_end = 3150 },
    { name = "grandine-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3200, validator_end = 3250 },
    { name = "grandine-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3300, validator_end = 3350 },
    { name = "grandine-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3400, validator_end = 3450 },
    { name = "grandine-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3500, validator_end = 3550 },

    # Erigon: 50 keys per node, the block after its grandine neighbor.
    { name = "prysm-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3050, validator_end = 3100 },
    { name = "lodestar-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3150, validator_end = 3200 },
    { name = "lighthouse-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3250, validator_end = 3300 },
    { name = "teku-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3350, validator_end = 3400 },
    { name = "nimbus-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3450, validator_end = 3500 },
    { name = "grandine-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3550, validator_end = 3600 },

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
