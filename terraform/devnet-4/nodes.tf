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
    { name = "bootnode", count = 1, cloud = "hetzner" },
    { name = "buildoor-prysm-ethrex", count = 1, cloud = "hetzner" },
    { name = "prysm-ethrex", count = 2, cloud = "hetzner", validator_start = 0, validator_end = 400 },
    { name = "lodestar-ethrex", count = 2, cloud = "hetzner", validator_start = 400, validator_end = 800 },
    { name = "grandine-ethrex", count = 1, cloud = "hetzner", validator_start = 800, validator_end = 1000 },
    { name = "prysm-nethermind", count = 2, cloud = "hetzner", validator_start = 1000, validator_end = 1400 },
    { name = "lodestar-nethermind", count = 2, cloud = "hetzner", validator_start = 1400, validator_end = 1800 },
    { name = "grandine-nethermind", count = 1, cloud = "hetzner", validator_start = 1800, validator_end = 2000 },
    { name = "lighthouse-nethermind", count = 1, cloud = "hetzner", validator_start = 2000, validator_end = 2200 },
    { name = "lighthouse-ethrex", count = 1, cloud = "hetzner", validator_start = 2200, validator_end = 2400 },
    { name = "nimbus-ethrex", count = 1, cloud = "hetzner", validator_start = 2400, validator_end = 2600 },
    { name = "nimbus-nethermind", count = 1, cloud = "hetzner", validator_start = 2600, validator_end = 2800 },
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
