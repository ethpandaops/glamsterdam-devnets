# GitHub lookups for glamsterdam devnet specs

All lookups use the `gh` CLI (authenticated via `gh auth login`). These are the
glamsterdam-specific conventions; adjust EIP/devnet numbers per target.

## Conventions

| Thing | Pattern | Example |
|-------|---------|---------|
| EELS test release tag | `tests-glamsterdam-devnet@vX.Y.Z` | `tests-glamsterdam-devnet@v6.1.0` |
| EELS devnet branch | `devnets/glamsterdam/N` | `devnets/glamsterdam/6` |
| EELS fork branch | `forks/amsterdam` | (EL fork is "amsterdam") |
| Client devnet branch | `glamsterdam-devnet-N` | |
| Client docker image | `ethpandaops/<client>:glamsterdam-devnet-N` | |
| Consensus-specs release | `vX.Y.Z-alpha.N` | `v1.7.0-alpha.10` |

EL fork = **amsterdam**, CL fork = **gloas**.

## Repositories tracked in the PR tables

Section names must match `REPO_SECTIONS` in `md/sync.py` for the `pr` command to
find the heading:

| Section heading (in md) | Repo |
|-------------------------|------|
| Beacon API | `ethereum/beacon-APIs` |
| Builder Specs | `ethereum/builder-specs` |
| Consensus Specs | `ethereum/consensus-specs` |
| EIPs | `ethereum/EIPs` |
| Execution APIs | `ethereum/execution-apis` |
| Execution Spec PRs | `ethereum/execution-specs` |

Networking PRs (`ethereum/devp2p`) appear in some sheets under a **Networking**
heading but aren't in `REPO_SECTIONS`, so add those bullets by hand.

EL clients: `ethereum/go-ethereum`, `hyperledger/besu`, `paradigmxyz/reth`,
`NethermindEth/nethermind`, `erigontech/erigon`, `lambdaclass/ethrex`,
`status-im/nimbus-eth1`.
CL clients: `sigp/lighthouse`, `ChainSafe/lodestar`, `prysmaticlabs/prysm`,
`Consensys/teku`, `status-im/nimbus-eth2`, `grandinetech/grandine`.

## EELS test releases

```bash
# Latest glamsterdam test releases
gh release list --repo ethereum/execution-specs --limit 30 | grep 'glamsterdam'

# Does the devnet branch exist yet?
gh api repos/ethereum/execution-specs/branches/devnets/glamsterdam/6 --jq '.name' 2>/dev/null \
  && echo exists || echo "not found"

# PRs merged into execution-specs since a tag's date
TAG=tests-glamsterdam-devnet@v6.0.0
DATE=$(gh api repos/ethereum/execution-specs/git/ref/tags/$TAG --jq '.object.sha' \
  | xargs -I{} gh api repos/ethereum/execution-specs/git/commits/{} --jq '.committer.date')
gh pr list --repo ethereum/execution-specs --state merged --search "merged:>$DATE" --limit 50
```

→ To pin EIPs to a release, see `eip-commit-pinning.md`.

## EIP PR triage (the "EIPs" table)

```bash
# Open PRs for one EIP
gh pr list --repo ethereum/EIPs --search '8037 in:title' --state open \
  --json number,title,author,state,createdAt

# Scan all devnet EIPs for open PRs
for eip in 2780 7708 7778 7843 7928 7954 7976 7981 7997 8024 8037 8038 8246 8282; do
  count=$(gh pr list --repo ethereum/EIPs --search "$eip in:title" --state open --json number --jq 'length')
  [ "$count" -gt 0 ] && echo "EIP-$eip: $count open PRs"
done

# Recently merged (may belong in the spec's merged section)
gh pr list --repo ethereum/EIPs --search '8037 in:title merged:>2026-06-01' \
  --state merged --json number,title,mergedAt
```

## Client readiness matrix

```bash
# Does each EL client have the devnet branch?
for repo in ethereum/go-ethereum hyperledger/besu paradigmxyz/reth \
            NethermindEth/nethermind erigontech/erigon lambdaclass/ethrex \
            status-im/nimbus-eth1; do
  b=$(gh api "repos/$repo/branches/glamsterdam-devnet-6" --jq '.name' 2>/dev/null)
  echo "$repo: ${b:-NOT FOUND}"
done

# Is the docker image published?
curl -s "https://hub.docker.com/v2/repositories/ethpandaops/geth/tags/glamsterdam-devnet-6" \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('name','NOT FOUND'))"

# Per-client EIP work
gh pr list --repo ethereum/go-ethereum --search 'EIP-8037 OR state creation gas' --state all --limit 20
```

## Per-repo PR status (what md/sync.py automates)

`md/sync.py sync-prs <network>` refreshes the status emoji on every
`[PR-N ...](.../pull/N)` bullet by querying the GitHub API. To check one PR by hand:

```bash
gh pr view 2999 --repo ethereum/execution-specs --json state,merged,isDraft,title
```

Status legend used in the sheets: `Merged :heavy_check_mark:`, `Open :exclamation:`,
`Draft :exclamation:`, `Closed :x:`.
