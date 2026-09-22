# Go-live runbook — randomized jumpdest analysis on devnet-8

Everything is verified offline; **nothing has yet run against a live spamoor**. This is the
ordered procedure, with a cheap gate after each step so a mistake costs one transaction
rather than a day of blocks.

Total wall time to a running attack: **~3 transactions, a few minutes.** Scenario C's
attack is ~55 h behind its corpus.

## 0. Before anything

```bash
cd spamoor-configs/glamsterdam-devnet-8
python3 preflight.py
```

Must print `factory ... HAS CODE` and `READY`. If the factory check fails, **stop** — every
address in these configs is derived from that factory, and running anyway burns whole
blocks while analysing nothing. See the note in `README.md`.

You also need:

- **A spamoor bearer token.** The hosted instance verifies a JWT from ethpandaops'
  `service-authenticatoor` (behind Cloudflare Access). The web UI caches nothing — it asks
  the auth client per request (`webui/static/js/spamoor.js:172-175`) — so get one from the
  page console while logged in:
  ```js
  await window.ethpandaops.authenticatoor.getToken()
  ```
  or copy the `Authorization` header off any `/api/` request in the Network tab.
- **Root wallet funding.** The refills these configs request total roughly:
  blob 10 + driver 5 + pre-fund 20 + attack wallets 24×5 = 120, and for C another
  6×20 = 120. Call it **~275 ETH** of headroom if you run everything, ~155 ETH for A and B
  alone. This has not been checked against the actual root balance — if the root is short,
  spamoor will simply fund fewer wallets and throughput will sag.

## 1. Import

Either paste the YAML into the UI, or POST the raw URL (this repo is public):

```bash
curl -sS -X POST https://spamoor.glamsterdam-devnet-8.ethpandaops.io/api/spammers/import \
  -H "Authorization: Bearer $SPAMOOR_TOKEN" -H 'content-type: application/json' \
  --data "$(python3 -c 'import json;print(json.dumps({"input":"https://raw.githubusercontent.com/ethpandaops/glamsterdam-devnets/qu0b/spamoor-jumpdest-configs/spamoor-configs/glamsterdam-devnet-8/jumpdest-analysis-A-direct-port.yaml"}))')"
```

Import creates the spammers **paused**. Nothing runs until you start one.

## 2. Prep 1/3 — the source blob  ← the critical gate

Start only `3631 prep 1/3`. It sends exactly one transaction (~120M gas).

```bash
python3 preflight.py      # must now report the blob DEPLOYED at 0x3b47073b...
```

**This is the step that proves the whole address chain.** If the blob deployed but to a
different address, preflight still reports "NOT deployed" — stop and regenerate, because
the driver references `0x3b47073b...` in its call data and nothing downstream will work.

## 3. Prep 2/3 — the CREATE driver

One transaction. Re-run `preflight.py`; it must report the driver deployed at
`0x100dae30...`. This driver serves every alphabet and both attacks.

## 4. Prep 3/3 — pre-fund (attack A only)

One transaction, ~176.5M gas, funds 900 targets with 1 wei each. Re-run `preflight.py`;
it probes the first 8 targets and they must all be funded.

> **This does not coexist well with a running corpus.** The transaction's `tx.gas` is 190M
> and block validity requires `tx.gas <= state_gas_available`, so it only fits in a block
> where little state gas has been used — while a corpus deploy consumes ~100.45M of it
> every block. Observed on the live run: submitted at 21:43 and still unlanded minutes
> later. Either run the pre-fund before starting the corpus, or split it into 3 smaller
> transactions (~300 targets each, ~65M gas) so it can share a block. **Attack B needs
> none of this** and is the one to reach for while the corpus is building.

**Attack B does not need this step** — start B straight after step 3 if you want to be
running sooner.

## 5. Start an attack

Start `3631 attack A` and/or `3631 attack B`. Expect, per transaction:

| | expected |
|---|---|
| status | **0 (reverted)** — this is correct, the driver reverts to roll back its CREATEs |
| gas used | ~16,728,000 of the limit, i.e. a clean exit, **not** the full limit |
| analyses | ~820 per transaction, ~9,800 per block, ~1.28 GB |

**Health check in one line:** a receipt whose `gasUsed` equals the gas limit exactly means
the transaction ran out of gas rather than reverting — for A that means the pre-funding did
not take, and the block is doing ~1/9th of the intended work.

## 6. Scenario C

**Start this as early as you can** — it is a ~55 h build, so every hour it is not running
is an hour added to when scenario C can attack. It does not need steps 3-5; it needs only
the blob from step 2.

> **The corpus must not start before the blob exists.** The corpus initcode EXTCODECOPYs
> the blob and RETURNs 65,536 bytes unconditionally, so if the blob is not deployed yet
> every contract is built from **zeros** — still unique, still 100.45M state gas each,
> still ~55 h, and useless, because there are no random bytes to analyse. It looks exactly
> like success. `start_corpus.sh` refuses to proceed until the blob is confirmed on-chain,
> and deploys it first if it is missing, which makes it safe to run as the very first
> command:
>
> ```bash
> SPAMOOR_TOKEN=ey... ./start_corpus.sh
> ```
>
> It imports A (for prep 1/3 only), starts the blob deploy, waits for it to land, then
> imports C and starts the corpus and the three ring drivers — never the attack.

Then:

```bash
python3 ../../../devnets/glamsterdam-devnet-8/work/jumpdest-3631/monitor_corpus.py --interval 300
```

One contract lands per block — two max-size deploys cannot share a 200M block — and
**devnet-8 runs 12-second slots** (`SECONDS_PER_SLOT=12`), so 16,384 contracts is
**~54.6 h at best; ~65 h at the rate observed on the first run (~250/h)**. Milestones from
a standing start: n=4096 after ~16 h, n=8192 after ~33 h. Before starting attack C:

```bash
monitor_corpus.py --verify 16384     # exits non-zero until every slot exists
```

The attack ships pointing at the n=16384 ring (1.07 GB working set). Attacking a ring
larger than the corpus is not an error, it is a quiet no-op: missing slots cost 3,000 gas
and analyse nothing.

**Run the corpus alongside attack A or B.** EIP-8037 meters execution and state separately
and a block is full when the bottleneck dimension hits the limit, so the state-bound corpus
and the execution-bound attacks do not compete — verified: one block carried a corpus
deploy (100.5M state) plus 11 attack transactions (184M execution, 9,020 analyses).

## What to expect on the network

- **Blocks go full, then the attack throttles itself.** A full block raises the base fee
  12.5%; at ~184M against a 100M target that is about +10.5% per block, so roughly **20
  minutes** from devnet-8's idle 8 wei to the configs' 20 gwei cap. Past that the
  transactions stop being includable, blocks empty, the fee decays, and the spammer picks
  up again — a duty cycle rather than a failure. No fixed fee cap avoids this: the rise is
  exponential, so each doubling of the cap buys only ~7 more blocks.
- **Expect orphans and missed attestations if it works.** That is the point — a 200M block
  of this workload is 2.7–5.6 s of `engine_newPayload` extrapolated from the PR's numbers.
- Nothing is left in state by A or B (verified: 0 accounts). C's corpus is permanent state
  growth — 16,384 × 64 KiB ≈ 1.07 GB of code, deliberately.

## Abort

Pause the spammer in the UI. There is nothing to clean up for A and B. The corpus contracts
persist; that is intended, and a later run can reuse them by pointing a ring driver at them.

**Resuming the corpus is not automatic:** `factorydeploytx` derives each salt as
`start_salt + <transaction index in this run>`, so a restarted spammer re-deploys from the
beginning at ~100M gas a block, making no progress. Set `start_salt` to the frontier
`monitor_corpus.py` reports, and reduce `total_count` to match, before restarting.
