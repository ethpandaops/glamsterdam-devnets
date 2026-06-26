# HackMD sync (md/sync.py)

Spec sheets are HackMD notes under the `ethpandaops` team at
`notes.ethereum.org/@ethpandaops/<permalink>`. `md/sync.py` is the canonical tool;
this doc covers what it does and the API details behind it.

## Auth

```bash
export HACKMD_TOKEN=...   # generate at https://notes.ethereum.org/settings#api
export GITHUB_TOKEN=...   # optional, lifts GitHub rate limit for sync-prs
```

`md/sync.py` reads the `HACKMD_TOKEN` env var; it must have write access to the
`ethpandaops` team notes.

## Commands

```bash
python3 md/sync.py from-remote <network>          # pull HackMD note -> md/<network>.md
python3 md/sync.py to-remote   <network>          # push md/<network>.md -> HackMD note
python3 md/sync.py sync-prs    <network>          # refresh every PR status emoji, then push
python3 md/sync.py pr <network> [<push?>] <url>   # insert a PR into its repo section
```

- `<network>` is the note permalink, e.g. `glamsterdam-devnet-6`. The note must
  already exist on HackMD with that permalink (sync.py resolves the note id by
  listing team notes and matching `permalink`).
- `sync-prs` rewrites `[PR-N - title](.../pull/N) <status>` bullets in place by
  querying the GitHub API, then pushes. Statuses: `Merged :heavy_check_mark:`,
  `Open :exclamation:`, `Draft :exclamation:`, `Closed :x:`.
- `pr` maps the PR's repo to a section heading (EIPs, Execution Spec PRs, Consensus
  Specs, Beacon API, Builder Specs, Execution APIs — see `REPO_SECTIONS` in
  `md/sync.py`) and inserts the bullet in PR-number order. Pass a truthy second arg
  to also push.

## PR-table format the tooling expects

For `sync-prs`/`pr` to manage a PR, write the bullet as a canonical pull URL:

```markdown
- [PR-2999 - EIP-8037 source-based refunds](https://github.com/ethereum/execution-specs/pull/2999) Open :exclamation:
```

A bare `[#2999](...pull/2999)` style link is also matched for status refresh, but
new entries via `pr` are written in the `PR-N - title` form.

## Creating a brand-new devnet note

`md/sync.py` updates existing notes; it doesn't create them. To create one:

```bash
TOKEN="$HACKMD_TOKEN"
BASE="https://notes.ethereum.org/api/OpenAPI/v1"   # the /OpenAPI segment is required
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"glamsterdam-devnet-7 spec","content":"# glamsterdam-devnet-7 spec\n","permalink":"glamsterdam-devnet-7"}' \
  "$BASE/teams/ethpandaops/notes"
```

Then `python3 md/sync.py to-remote glamsterdam-devnet-7` going forward.

## Gotchas

- **Cloudflare WAF** blocks JSON request bodies over ~8 KB. Spec sheets are
  15-25 KB, so payloads must be gzipped — `md/sync.py` does this automatically
  (`Content-Encoding: gzip` when the body exceeds 8000 bytes).
- **API base path** is `/api/OpenAPI/v1` on this instance; HackMD's public docs
  show `/api/v1`, which 404s here.
- HTTP codes: `202` = PATCH accepted, `201` = note created, `204` = deleted,
  `401` = token expired (regenerate), `403` = payload too large (gzip).

## Read-only download (no auth)

```bash
curl -s "https://notes.ethereum.org/<noteId>/download" > out.md
```
