# EIP commit pinning

## Why

Spec sheets historically linked EIPs to `master`:
`https://github.com/ethereum/EIPs/blob/master/EIPS/eip-2780.md`. `master` drifts —
the EIP text moves on after a devnet is cut, so the link no longer reflects what
the devnet actually ran. This breaks automated debugging: an LLM reading the spec
sheet to reason about devnet behaviour sees the wrong EIP content.

Instead, pin to the exact commit the **EELS test release** froze. The test suite
is the source of truth for what the devnet runs, so taking the commit from there
avoids drift by construction:
`https://github.com/ethereum/EIPs/blob/992074053f12f24fed9e6d6bf6099d3a44707dca/EIPS/eip-2780.md`

## How it works

Each execution-specs test directory declares a `ReferenceSpec` in its `spec.py`:

```
https://github.com/ethereum/execution-specs/blob/<release-tag>/tests/<fork>/<eip-name>/spec.py
```

e.g. for `tests-glamsterdam-devnet@v6.1.0`:
`.../blob/tests-glamsterdam-devnet%40v6.1.0/tests/amsterdam/eip2780_reduce_intrinsic_tx_gas/spec.py`

```python
ref_spec_2780 = ReferenceSpec(
    git_path="EIPS/eip-2780.md",
    version="4b612eec2ef70611bba3e0819d137dcfb9b6cd81",
)
```

`version` is the ethereum/EIPs commit hash. Build the pinned link as:

```
https://github.com/ethereum/EIPs/blob/<version>/<git_path>
```

Glamsterdam's EL fork is **amsterdam**, so EL EIP tests are under `tests/amsterdam/`.

## Automated: eip_pins.py

Resolve every EIP at a release in one shot:

```bash
python3 .claude/skills/glamsterdam-devnet-spec/scripts/eip_pins.py tests-glamsterdam-devnet@v6.1.0
# markdown table of EIP -> pinned commit URL

python3 .claude/skills/glamsterdam-devnet-spec/scripts/eip_pins.py tests-glamsterdam-devnet@v6.1.0 --json
# {"release":..., "pins":[{"eip":2780,"git_path":...,"version":...,"eip_url":...}, ...]}
```

Flags: `--fork <name>` (default `amsterdam`), `--json`. Set `GITHUB_TOKEN` (or
`GH_TOKEN`) to avoid unauthenticated rate limits.

Edge cases the script handles:
- **Positional `ReferenceSpec("EIPS/eip-8037.md", "<hash>")`** as well as the
  keyword form — it greps the `EIPS/eip-NNNN.md` path and the 40-hex commit that
  follows it.
- **Placeholder `0000…0000` versions** (EIP not yet merged to master, e.g. a Draft
  like EIP-8282) are reported as "no version pinned" rather than a dead link.

## Manual fallback

If the script can't run, do it by hand for one EIP:

```bash
TAG="tests-glamsterdam-devnet@v6.1.0"
DIR="eip2780_reduce_intrinsic_tx_gas"   # find via the listing below
gh api "repos/ethereum/execution-specs/contents/tests/amsterdam/$DIR/spec.py?ref=$TAG" \
  --jq '.content' | base64 -d | grep -E 'git_path|version'
```

List the EIP test directories at a release:

```bash
gh api "repos/ethereum/execution-specs/contents/tests/amsterdam?ref=$TAG" \
  --jq '.[] | select(.type=="dir") | .name'
```

Note: `@` in the tag URL-encodes to `%40` when building a browser URL by hand; the
`gh api ?ref=` form takes the raw tag.

## Using the pins in the spec sheet

The EIP-list table can keep the human-friendly `https://eips.ethereum.org/EIPS/eip-NNNN`
links for readability. Add the pinned-commit links where implementation fidelity
matters — e.g. an "EIP versions as tested" block tied to the EELS release, which is
what downstream automated debugging consumes. Re-run `eip_pins.py` whenever the
target EELS release changes and update the block.
