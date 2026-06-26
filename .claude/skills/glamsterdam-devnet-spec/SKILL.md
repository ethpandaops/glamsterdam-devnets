---
name: glamsterdam-devnet-spec
description: Build, update, and publish glamsterdam devnet spec sheets — the md/glamsterdam-devnet-N.md notes synced to notes.ethereum.org/@ethpandaops. Use when drafting or revising a glamsterdam devnet spec, assembling its EIP list and per-repo PR-status tables, pinning EIPs to the exact commit the EELS test release targets, or pushing/pulling the note to/from HackMD.
---

# Glamsterdam devnet spec sheets

Spec sheets describe what a glamsterdam devnet runs: the EIP list, the test
releases (EELS + consensus-specs) it targets, and the open/merged PRs per repo.
They live as HackMD notes at `notes.ethereum.org/@ethpandaops/glamsterdam-devnet-N`,
with the canonical markdown checked into this repo at `md/glamsterdam-devnet-N.md`.

Glamsterdam = **gloas** (CL fork) + **amsterdam** (EL fork). In execution-specs,
EL EIP tests live under `tests/amsterdam/`.

## Where things live

| Path | What |
|------|------|
| `md/glamsterdam-devnet-N.md` | Canonical spec markdown (source of truth) |
| `md/sync.py` | Push/pull to HackMD + auto-refresh PR statuses |
| `.claude/skills/glamsterdam-devnet-spec/scripts/eip_pins.py` | Resolve EIP commit pins from an EELS release |
| `.claude/skills/glamsterdam-devnet-spec/references/` | Detailed lookup recipes |

## Workflow

1. **Start from the previous devnet.** Copy `md/glamsterdam-devnet-(N-1).md` to
   `md/glamsterdam-devnet-N.md`, or `python3 md/sync.py from-remote glamsterdam-devnet-N`
   if the note already exists on HackMD. State the diff vs the prior devnet up top
   (new / changed / dropped EIPs) — that's what readers scan for first.
2. **Gather context from public sources.** What changed since the last devnet, what
   PRs are open/merged, what client branches and images exist.
   → `references/github-lookups.md` (PRs, branches, releases, client readiness).
3. **Pin the EIP list to the EELS release.** The test release is the source of
   truth for what the devnet actually runs. Resolve each EIP to the exact
   ethereum/EIPs commit and link to that, not `master`.
   → `references/eip-commit-pinning.md`
4. **Fill the PR tables.** One bullet per PR per repo section. Use the canonical
   `https://github.com/<owner>/<repo>/pull/<n>` URL so `md/sync.py` can keep the
   status emoji current.
5. **Publish.** `python3 md/sync.py to-remote glamsterdam-devnet-N`, then verify at
   `notes.ethereum.org/@ethpandaops/glamsterdam-devnet-N`.
   → `references/hackmd-sync.md`

## Syncing (md/sync.py)

Requires `HACKMD_TOKEN` (generate at notes.ethereum.org/settings#api). Optional
`GITHUB_TOKEN` lifts the GitHub rate limit for PR-status refresh.

```
python3 md/sync.py from-remote <network>          # pull HackMD -> md/<network>.md
python3 md/sync.py to-remote   <network>          # push md/<network>.md -> HackMD
python3 md/sync.py sync-prs    <network>          # refresh every PR's status emoji, then push
python3 md/sync.py pr <network> [true] <pr-url>   # add a PR to its repo section (true = also push)
```

`<network>` is the note permalink, e.g. `glamsterdam-devnet-6`.

## EIP commit pinning (the key step)

Link each EIP to the commit its EELS test release froze, so a reader (or an LLM
debugging the devnet) sees the EIP text *as implemented*, not whatever `master`
drifted to:

```
python3 .claude/skills/glamsterdam-devnet-spec/scripts/eip_pins.py tests-glamsterdam-devnet@v6.1.0
```

This reads every `tests/amsterdam/<eip>/spec.py` `ReferenceSpec` at that release
tag and emits `https://github.com/ethereum/EIPs/blob/<commit>/EIPS/eip-NNNN.md`
links. Add `--json` for machine consumption. Full mechanism and the manual
fallback: `references/eip-commit-pinning.md`.

## References

- `references/eip-commit-pinning.md` — EELS release → exact EIP commit
- `references/github-lookups.md` — `gh` recipes for PRs, branches, releases, client matrix
- `references/hackmd-sync.md` — HackMD API details behind `md/sync.py`
