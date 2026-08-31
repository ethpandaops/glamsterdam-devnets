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
    # Bootnodes: 2 (not 4) — enough to keep the DNS master/slave split exercised,
    # since dns_server_slave = bootnode group minus primary_bootnode.
    { name = "bootnode", count = 2, cloud = "digitalocean" },
    # Buildoor — all four CL/EL pairs kept; builder indices must stay 0..3.
    { name = "buildoor-prysm-ethrex", count = 1, cloud = "digitalocean", builder_start = 0 },
    { name = "buildoor-lighthouse-geth", count = 1, cloud = "digitalocean", builder_start = 1 },
    { name = "buildoor-lodestar-ethrex", count = 1, cloud = "digitalocean", builder_start = 2 },
    { name = "buildoor-teku-nethermind", count = 1, cloud = "digitalocean", builder_start = 3 },

    # SMOKE TEST GRID — tooling shakeout before the 1000-node run.
    # Every CL/EL combination of the mainnet-weighted grid is kept, one node each
    # (39 combos), so every client role, image and config path is exercised. Only the
    # per-combo multiplicity is dropped, i.e. the shape of the matrix is identical,
    # the weights are not. 1000 validators per node, contiguous ranges in file order
    # over [0,39000) (NUMBER_OF_VALIDATORS=39000, see group_vars/all/all.yaml) so
    # every genesis validator is online and the chain can finalise.
    # Restore the weighted 1000-node grid with `git checkout` on this file (and reset
    # NUMBER_OF_VALIDATORS back to 1000000).

    # Lighthouse (7)
    { name = "lighthouse-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 0, validator_end = 1000 },
    { name = "lighthouse-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 1000, validator_end = 2000 },
    { name = "lighthouse-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2000, validator_end = 3000 },
    { name = "lighthouse-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3000, validator_end = 4000 },
    { name = "lighthouse-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 4000, validator_end = 5000 },
    { name = "lighthouse-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 5000, validator_end = 6000 },
    { name = "lighthouse-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 6000, validator_end = 7000 },

    # Prysm (7)
    { name = "prysm-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 7000, validator_end = 8000 },
    { name = "prysm-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 8000, validator_end = 9000 },
    { name = "prysm-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 9000, validator_end = 10000 },
    { name = "prysm-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 10000, validator_end = 11000 },
    { name = "prysm-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 11000, validator_end = 12000 },
    { name = "prysm-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 12000, validator_end = 13000 },
    { name = "prysm-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 13000, validator_end = 14000 },

    # Teku (7)
    { name = "teku-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 14000, validator_end = 15000 },
    { name = "teku-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 15000, validator_end = 16000 },
    { name = "teku-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 16000, validator_end = 17000 },
    { name = "teku-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 17000, validator_end = 18000 },
    { name = "teku-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 18000, validator_end = 19000 },
    { name = "teku-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 19000, validator_end = 20000 },
    { name = "teku-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 20000, validator_end = 21000 },

    # Nimbus (7)
    { name = "nimbus-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 21000, validator_end = 22000 },
    { name = "nimbus-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 22000, validator_end = 23000 },
    { name = "nimbus-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 23000, validator_end = 24000 },
    { name = "nimbus-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 24000, validator_end = 25000 },
    { name = "nimbus-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 25000, validator_end = 26000 },
    { name = "nimbus-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 26000, validator_end = 27000 },
    { name = "nimbus-nimbusel", count = 1, cloud = "digitalocean", supernode = true, validator_start = 27000, validator_end = 28000 },

    # Lodestar (6)
    { name = "lodestar-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 28000, validator_end = 29000 },
    { name = "lodestar-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 29000, validator_end = 30000 },
    { name = "lodestar-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 30000, validator_end = 31000 },
    { name = "lodestar-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 31000, validator_end = 32000 },
    { name = "lodestar-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 32000, validator_end = 33000 },
    { name = "lodestar-ethrex", count = 1, cloud = "digitalocean", supernode = true, validator_start = 33000, validator_end = 34000 },

    # Grandine (5)
    { name = "grandine-geth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 34000, validator_end = 35000 },
    { name = "grandine-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 35000, validator_end = 36000 },
    { name = "grandine-reth", count = 1, cloud = "digitalocean", supernode = true, validator_start = 36000, validator_end = 37000 },
    { name = "grandine-besu", count = 1, cloud = "digitalocean", supernode = true, validator_start = 37000, validator_end = 38000 },
    { name = "grandine-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 38000, validator_end = 39000 },

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
