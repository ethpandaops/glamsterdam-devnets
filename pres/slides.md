---
marp: true
theme: default
paginate: true
title: ePBS → BAL → Glamsterdam Devnets
style: |
  :root {
    --bal:   #2563eb;
    --epbs:  #9333ea;
    --glams: #0d9488;
    --d6:    #0d9488;
    --gas:   #ea580c;
    --evm:   #16a34a;
    --muted: #475569;
  }
  section {
    font-size: 22px;
    padding: 50px 60px;
    justify-content: flex-start;
    background: linear-gradient(135deg, #fafafa 0%, #f1f5f9 100%);
  }
  section.lead {
    justify-content: center;
    text-align: center;
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    color: #f8fafc;
  }
  section.lead h1 { color: #f8fafc; }
  section.lead h2 { color: #94a3b8; }
  section.lead code {
    background: rgba(255,255,255,0.08);
    color: inherit;
    padding: 2px 8px;
    border-radius: 4px;
  }
  h1 { font-size: 38px; margin-bottom: 0.3em; color: #0f172a; }
  h2 { font-size: 30px; margin-bottom: 0.3em; color: #0f172a; }
  h3 { font-size: 24px; color: var(--muted); }
  strong { color: #0f172a; }
  a { color: var(--bal); }
  table {
    font-size: 18px;
    width: 100%;
    border-collapse: collapse;
  }
  th { background: #e2e8f0; color: #0f172a; }
  th, td { padding: 4px 8px; vertical-align: top; border-bottom: 1px solid #cbd5e1; }
  pre, code {
    font-size: 16px;
    line-height: 1.25;
  }
  code { background: #e2e8f0; padding: 1px 5px; border-radius: 3px; }
  pre {
    padding: 8px 12px;
    overflow: hidden;
    background: #1e293b;
    color: #e2e8f0;
    border-radius: 6px;
  }
  pre code { background: transparent; color: inherit; padding: 0; }
  ul, ol { margin: 0.3em 0; }
  li { margin: 0.15em 0; }
  p { margin: 0.4em 0; }
  .bal   { color: var(--bal);   font-weight: 600; }
  .epbs  { color: var(--epbs);  font-weight: 600; }
  .glams { color: var(--glams); font-weight: 600; }
  .gas   { color: var(--gas);   font-weight: 600; }
  .evm   { color: var(--evm);   font-weight: 600; }
  .d6    { color: var(--d6);    font-weight: 700; }
  .stat {
    display: inline-block;
    padding: 10px 22px;
    margin: 6px 4px;
    border-radius: 10px;
    background: #fff;
    border: 2px solid #cbd5e1;
    font-size: 18px;
  }
  .stat .num { font-size: 38px; font-weight: 800; display: block; line-height: 1; margin-bottom: 4px; }
  .stat.total { border-color: var(--glams); }
  .stat.total .num { color: var(--glams); }
  .stat.bal-c   { border-color: var(--bal); }
  .stat.bal-c .num   { color: var(--bal); }
  .stat.epbs-c  { border-color: var(--epbs); }
  .stat.epbs-c .num  { color: var(--epbs); }
  .stat.d6-c    { border-color: var(--d6); }
  .stat.d6-c .num    { color: var(--d6); }
  .eip-grid {
    display: flex;
    gap: 40px;
    margin-top: 10px;
  }
  .eip-grid .col { flex: 1; min-width: 0; }
  .eip-grid h4 {
    margin: 0 0 6px 0;
    font-size: 22px;
    font-weight: 700;
  }
  .eip-grid ul {
    margin: 0 0 16px 0;
    padding-left: 22px;
    font-size: 19px;
    color: #0f172a;
  }
  .eip-grid li { margin: 3px 0; line-height: 1.35; }
  .eip-grid li strong { color: #0f172a; }
  .eip-grid li .d6 { color: var(--d6); font-weight: 700; }
---

<!-- _class: lead -->

# From <span style="color:#60a5fa">`bal-`</span> to <span style="color:#c084fc">`epbs-`</span> to <span style="color:#5eead4">`glamsterdam-`</span>
## A short history of the Glamsterdam fork devnets

ethPandaOps · 2026-06-04

---

## Why three repos?

Glamsterdam = <span class="epbs">ePBS</span> (EIP-7732) **+** <span class="bal">BAL</span> (EIP-7928) **+** <span class="gas">state-growth gas reform</span>.

Each big feature got its **own devnet line** first to debug in isolation, then the two tracks **merged** into the joint `glamsterdam-` line.

```
  bal-devnets    ─┐
                  ├─► glamsterdam-devnets
  epbs-devnets   ─┘
```

Two early feature tracks, one combined Glamsterdam track.

---

## <span class="bal">Track 1 — `bal-devnets`</span> (early)

**Scope:** Block-Level Access Lists (EIP-7928) + state-growth gas EIPs.
Ran for **~7 months** total.

| Devnet   | Genesis    | Killed     | Headline change                          |
| -------- | ---------- | ---------- | ---------------------------------------- |
| devnet-0 | 2025-11-04 | 2025-12-18 | First BAL end-to-end                     |
| devnet-1 | 2025-12-18 | 2026-02-06 | Stress tools, debug RPCs for BAL diffs   |
| devnet-2 | 2026-02-06 | 2026-04-08 | +7708, 7778, 7843, 8024                  |
| devnet-3 | 2026-04-08 | 2026-04-29 | +7954, 7976, 7981, 8037 (state-gas)      |

Fork epochs: Fulu @ 0, **Gloas @ 1** early → **Gloas @ 2** from devnet-3.

---

## <span class="bal">Track 1 — `bal-devnets`</span> (late)

| Devnet   | Genesis    | Killed/Replaced | Headline change                                   |
| -------- | ---------- | --------------- | ------------------------------------------------- |
| devnet-5 | 2026-04-29 | 2026-05-01      | EIP-8037 v2 + frame accounting                    |
| devnet-6 | 2026-05-01 | 2026-05-18      | EIP-8037 stabilisation (cpsb = 1174)              |
| devnet-7 | 2026-05-18 | current         | **Last `bal-`** — cpsb 1174→1530, gas 96M→150M    |

- EL clients grew from 5 → 7 (added Erigon, Nimbus-EL, Ethrex).
- CL stayed lean: Lodestar, Lighthouse, Prysm (partial).
- `eth/70` + `eth/71` promoted from optional → mandatory in devnet-7.

---

## bal-devnet feature creep

```
devnet-0 : 7928
devnet-1 : 7928
devnet-2 : 7928 7708 7778 7843 8024
devnet-3 : 7928 7708 7778 7843 8024 7954 8037           (+opt 7975/8159)
devnet-5 : 7928 7708 7778 7843 8024 7954 8037 7976 7981 (+opt 7975/8159)
devnet-6 : 7928 7708 7778 7843 8024 7954 8037 7976 7981 (cpsb=1174 stable)
devnet-7 : 7928 7708 7778 7843 8024 7954 8037 7976 7981
            + 7975 + 8159 mandatory
```

Each devnet layered one more state-gas / network-protocol EIP onto the BAL base.

---

## <span class="epbs">Track 2 — `epbs-devnets`</span>

**Scope:** EIP-7732 (Enshrined Proposer–Builder Separation) only.
Self-built payloads, minimal preset, consensus-specs **v1.7.0-alpha.2**, engine V5 APIs.

| Devnet   | Genesis    | Killed     | EL              | CL                                       |
| -------- | ---------- | ---------- | --------------- | ---------------------------------------- |
| devnet-0 | 2026-03-04 | 2026-03-31 | Geth            | Lighthouse, Lodestar, Nimbus, Prysm, Teku |
| devnet-1 | 2026-03-31 | 2026-04-17 | Geth, Nethermind| Prysm, Lodestar                          |

Track retired once ePBS folded into the Glamsterdam line.

---

## <span class="glams">Track 3 — `glamsterdam-devnets`</span>

**Scope:** Everything from `bal-devnet-7` **+ ePBS (EIP-7732)** under one roof.

| Devnet   | Genesis        | Killed/Replaced | Notes                                                |
| -------- | -------------- | --------------- | ---------------------------------------------------- |
| devnet-2 | 2026-04-30     | ~2026-05-06     | First glamsterdam spin; CL-focused, Gloas @ 1        |
| devnet-3 | 2026-05-06     | still up        | Same spec as devnet-2 — infra reroll                 |
| devnet-4 | 2026-05-22     | 2026-06-04      | bal-d7 EL set + EIP-8037 cpsb 1174→1530, gas →150M   |
| devnet-5 | 2026-06-04     | just launched   | **First glamsterdam CL+EL** — dynamic `targetGasLimit` |
| devnet-6 | mid-June 2026  | planned         | +EIP-2780, 7997, 8038, 8070, 8246; ePBS (7732) updated |

Repo skips `devnet-0/1`: numbering inherited from earlier ePBS attempts.

---

## What changed across glamsterdam devnets

**devnet-2 / devnet-3** — consensus-specs v1.7.0-alpha.8, ePBS-focused, EL feature set still light.

**devnet-4** — adopted bal-devnet-7 EL feature set in full:
- EIP-8037 params tightened (cpsb 1174→1530, storage set 32→64, per-account 112→120)
- `eth/70` + `eth/71` mandatory
- Reference gas limit 96M → 150M

**devnet-5** *(today)* — consensus-specs v1.7.0-alpha.10:
- CL now passes per-validator **target gas limit** to EL via `PayloadAttributesV4` (no more static EL flag)
- ePBS (7732) implementation still incomplete across clients — payloads self-built

**devnet-6** *(mid-June)* — execution-specs `tests-bal@v7.2.0` on `devnets/bal/7`:
- New EIPs: **2780, 7997, 8038, 8070, 8246**; ePBS (7732) spec bump
- EIP-8037 holds at cpsb = 1530; open networking PR for BAL (7928)

---

## All devnets, one timeline

```
2025-Nov ─ bal-d0
2025-Dec ─ bal-d1
2026-Feb ─ bal-d2
2026-Mar ─ epbs-d0   ┐
2026-Mar ─ epbs-d1   ┘  (track retired)
2026-Apr ─ bal-d3
2026-Apr ─ bal-d5    ┐
2026-Apr ─ glams-d2  │  (tracks converge)
2026-May ─ bal-d6    │
2026-May ─ glams-d3  │
2026-May ─ bal-d7    ┘  (last bal-)
2026-May ─ glams-d4
2026-Jun ─ glams-d5  ← we are here
2026-Jun ─ glams-d6  (planned, mid-June)
```

---

## EL / CL client coverage

| Track          | EL clients (latest)                                     | CL clients (latest)                    |
| -------------- | ------------------------------------------------------- | -------------------------------------- |
| bal-d7         | Geth, Besu, Reth, Nethermind, Erigon, Nimbus-EL, Ethrex | Lighthouse, Lodestar (Prysm partial)   |
| epbs-d1        | Geth, Nethermind                                        | Prysm, Lodestar                        |
| glamsterdam-d5 | Geth, Besu, Reth, Nethermind, Erigon, Nimbus-EL, Ethrex | Lodestar, Lighthouse, Prysm            |

Glamsterdam inherits BAL's broad EL coverage and ePBS's CL diversity push.

---

## Glamsterdam EIPs — full menu

<div style="text-align:center;">
<span class="stat total"><span class="num">19</span>EIPs total</span>
<span class="stat bal-c"><span class="num">11</span>from bal-</span>
<span class="stat epbs-c"><span class="num">1</span>from epbs-</span>
<span class="stat d6-c"><span class="num">+5</span>new in d6</span>
</div>

<div class="eip-grid">
<div class="col">

<h4 class="epbs">Consensus / ePBS</h4>

- **7732** Enshrined PBS
- **8045** Exclude slashed validators
- **8061** Increase exit & churn

<h4 class="bal">BAL & networking</h4>

- **7928** Block-Level Access Lists
- **7975** eth/70 partial block receipts
- **8159** eth/71 BAL exchange
- **8070** <span class="d6">(d6)</span> eth/72 Sparse Blobpool

</div>
<div class="col">

<h4 class="gas">State-growth gas reform</h4>

- **2780** <span class="d6">(d6)</span> Reduce intrinsic tx gas
- **7778** Block gas accounting w/o refunds
- **7976** Calldata floor cost (64/64)
- **7981** Access list cost
- **8037** State creation gas
- **8038** <span class="d6">(d6)</span> State-access gas update

<h4 class="evm">EVM additions</h4>

- **7708** ETH transfers emit a log
- **7843** SLOTNUM opcode
- **7954** Increase max contract size
- **8024** SWAPN/DUPN/EXCHANGE
- **7997** <span class="d6">(d6)</span> Deterministic Factory Predeploy
- **8246** <span class="d6">(d6)</span> Remove SELFDESTRUCT burn

</div>
</div>

---

## Takeaways

1. **Two parallel feature tracks** (`bal-` and `epbs-`) de-risked Glamsterdam before merging.
2. **bal- did the heavy lifting**: 7 devnets, ~7 months, drove gas-accounting EIPs (8037, 7976, 7981) to stability.
3. **epbs- was short**: 2 devnets, ~6 weeks. EIP-7732 still not fully implemented across clients.
4. **glamsterdam-devnet-5** is the **first true CL+EL combined Glamsterdam** spin — dynamic gas limit handoff is the new shiny.
5. **Next**: get all clients past ePBS implementation, then ramp validator count.

---

<!-- _class: lead -->

# Questions?

`github.com/ethpandaops/{bal,epbs,glamsterdam}-devnets`
Specs: `notes.ethereum.org/@ethpandaops/<network>`
