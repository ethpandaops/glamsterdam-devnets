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

    # Validator layout (2026-07-16, "fair 100 grid"): 5 CL x 7 EL = 35 combos.
    # All 6 READY ELs (ethrex/geth/nethermind/reth/besu/nimbusel): 30 nodes x
    # 100 keys over [0,3000) - every ready combo is live from day one.
    # Erigon (the only EL not ready) gets the 600 post-genesis deposit keys
    # (3000-3599) as 5 x 120 on erigon-day.
    # Final grid: every CL exactly 720 (20%); ready ELs 500 (13.9%) each,
    # erigon 600 (16.7%).
    # Interim exception: lighthouse-nethermind babysits [2900,3600) - its own
    # 100-key block plus the 600 depositing keys (which it partly holds
    # today; they trickle-activate ~28/day until ~Aug 5). On erigon-day it
    # shrinks to 2900-3000 and erigon x5 take 3000-3600 (120 each, prysm
    # first). Land erigon-day before ~Aug 5: at full trickle the babysitter
    # pushes lighthouse CL to exactly 1/3 until erigon takes over.
    # Migration from the 300-key layout: waves A-H, one per ethrex/geth donor
    # (LCM(300,100)=300; donor keeps its head block, 2 recipients each;
    # 300 keys = 10% offline per wave) + wave I covering [2400,3600) (the
    # nethermind segment: quartet moves + 2 recipients; 20% offline) - see
    # ~/devnets/glamsterdam-devnet-7/VALIDATOR_RESHUFFLE.md.

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
    { name = "lighthouse-nethermind", count = 1, cloud = "digitalocean", supernode = true, validator_start = 2900, validator_end = 3600 }, # babysitter: own 2900-3000 + 600 depositing keys; shrinks to 2900-3000 on erigon-day
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

    # Erigon (erigon-day, requires wave I): uncomment the five nodes below AND
    # shrink lighthouse-nethermind to validator_start = 2900, validator_end = 3000
    # in the same edit — terraform's overlap validation will refuse anything else.
    # Then: apply -> bootstrap + keyless-provision -> reshuffle
    # (-l 'localhost,erigon,lighthouse_nethermind') -> playbook -l 'erigon'.
    # { name = "prysm-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3000, validator_end = 3120 },
    # { name = "lodestar-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3120, validator_end = 3240 },
    # { name = "lighthouse-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3240, validator_end = 3360 },
    # { name = "teku-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3360, validator_end = 3480 },
    # { name = "nimbus-erigon", count = 1, cloud = "digitalocean", supernode = true, validator_start = 3480, validator_end = 3600 },

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
