---
marp: true
theme: default
paginate: true
title: From bal- and epbs- to Glamsterdam Devnets
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

# From <span style="color:#60a5fa">`bal-`</span> and <span style="color:#c084fc">`epbs-`</span> to <span style="color:#5eead4">`glamsterdam-`</span>
## A short history of the Glamsterdam fork devnets

Barnabas Busa · ethPandaOps · 2026-06-04

---

## Why three repos?

Glamsterdam = <span class="epbs">ePBS</span> (EIP-7732) **+** <span class="bal">BAL</span> (EIP-7928) **+** <span class="gas">gas repricings</span>.

Each big feature got its **own devnet line** first to debug in isolation, then the two tracks **merged** into the joint `glamsterdam-` line.

```
  bal-devnets    ─┐
                  ├─► glamsterdam-devnets
  epbs-devnets   ─┘
```

Two early feature tracks, one combined Glamsterdam track.

---

## <span class="bal">Track 1 — `bal-devnets`</span>

**7 devnets · ~7 months · 11 EIPs landed**

```
bal-devnet-0 : 7928
bal-devnet-1 : 7928
bal-devnet-2 : 7708 7778 7843 7928 8024
bal-devnet-3 : 7708 7778 7843 7928 7954 8024 8037           (+opt 7975/8159)
bal-devnet-5 : 7708 7778 7843 7928 7954 7976 7981 8024 8037 (+opt 7975/8159)
bal-devnet-6 : 7708 7778 7843 7928 7954 7976 7981 8024 8037 (cpsb=1174 stable)
bal-devnet-7 : 7708 7778 7843 7928 7954 7975 7976 7981 8024 8037 8159
```

- **d0–d1** — first BAL end-to-end (just 7928)
- **d2** — EVM extras layered on (7708, 7778, 7843, 8024)
- **d3 → d7** — repricings stabilise; cpsb **1174 → 1530**, gas **96M → 150M**, `eth/70` + `eth/71` promoted to mandatory

EL fleet grew **5 → 7** (added Erigon, Nimbus-EL, Ethrex). CL stayed lean: **Lighthouse + Lodestar only**.

---

## <span class="epbs">Track 2 — `epbs-devnets`</span>

**Scope:** EIP-7732 (Enshrined PBS) only. **2 devnets · ~6 weeks.**

<div style="text-align:center;">
<span class="stat epbs-c"><span class="num">2</span>ELs (Geth + Nethermind)</span>
<span class="stat epbs-c"><span class="num">5</span>CLs touched ePBS</span>
</div>

Narrow EL set on purpose — ePBS lives in the CL.
**Lighthouse · Lodestar · Nimbus · Prysm · Teku** all took a turn.

**Honest caveat:** 7732 still not fully implemented across clients. Payloads self-built.

Track retired once ePBS folded into Glamsterdam.

---

## <span class="glams">Track 3 — `glamsterdam-devnets`</span>

**Scope:** Everything from `bal-devnet-7` **+ ePBS (EIP-7732)** under one roof.

| Devnet   | Genesis        | Killed/Replaced | Notes                                                |
| -------- | -------------- | --------------- | ---------------------------------------------------- |
| [devnet-2](https://notes.ethereum.org/@ethpandaops/glamsterdam-devnet-2) | 2026-04-30     | ~2026-05-06     | First glamsterdam spin; CL-focused, Gloas @ 1        |
| [devnet-3](https://notes.ethereum.org/@ethpandaops/glamsterdam-devnet-3) | 2026-05-06     | 2026-05-20      | Same spec as devnet-2 — infra reroll                 |
| [devnet-4](https://notes.ethereum.org/@ethpandaops/glamsterdam-devnet-4) | 2026-05-22     | 2026-06-04      | bal-devnet-7 EL set + EIP-8037 cpsb 1174→1530, gas →150M |
| [devnet-5](https://notes.ethereum.org/@ethpandaops/glamsterdam-devnet-5) | 2026-06-04     | just launched   | **First glamsterdam CL+EL** — dynamic `targetGasLimit`, gas 190M |
| [devnet-6](https://notes.ethereum.org/@ethpandaops/glamsterdam-devnet-6) | mid-June 2026  | planned         | +EIP-2780, 7997, 8038, 8070, 8246; ePBS (7732) updated |

Repo skips `devnet-0/1`: numbering inherited from earlier ePBS attempts.

---

## What changed across glamsterdam devnets

<div class="eip-grid">
<div class="col">

<h4 class="glams">devnet-2 / -3</h4>

- ePBS-focused
- EL feature set still light

<h4 class="glams">devnet-4</h4>

- Adopted **bal-d7 EL set in full**
- cpsb 1174 → 1530
- `eth/70` + `eth/71` mandatory
- Gas 96M → 150M

</div>
<div class="col">

<h4 class="glams">devnet-5 <em>(today)</em></h4>

- CL passes per-validator **target gas limit** via `PayloadAttributesV4`
- Gas 150M → **190M**
- ePBS still self-built across clients

<h4 class="glams">devnet-6 <em>(mid-June)</em></h4>

- +5 EIPs: **2780, 7997, 8038, 8070, 8246**
- ePBS (7732) spec bump
- BAL networking PR open

</div>
</div>

---

## All devnets, one timeline

```
2025-Nov ─ bal-devnet-0
2025-Dec ─ bal-devnet-1
2026-Feb ─ bal-devnet-2
2026-Mar ─ epbs-devnet-0         ┐
2026-Mar ─ epbs-devnet-1         ┘  (track retired)
2026-Apr ─ bal-devnet-3
2026-Apr ─ bal-devnet-5          ┐
2026-Apr ─ glamsterdam-devnet-2  │  (tracks converge)
2026-May ─ bal-devnet-6          │
2026-May ─ glamsterdam-devnet-3  │
2026-May ─ bal-devnet-7          ┘  (last bal-)
2026-May ─ glamsterdam-devnet-4
2026-Jun ─ glamsterdam-devnet-5  ← we are here
2026-Jun ─ glamsterdam-devnet-6  (planned, mid-June)
```

---

## Glamsterdam scope — per [EIP-7773](https://eips.ethereum.org/EIPS/eip-7773)

<div style="text-align:center;">
<span class="stat total"><span class="num">10</span>SFI — locked in</span>
<span class="stat bal-c"><span class="num">3</span>PFI — proposed</span>
<span class="stat epbs-c"><span class="num">13</span>CFI — still in flight</span>
</div>

<div class="eip-grid">
<div class="col">

<h4 class="glams">SFI — Scheduled, locked in</h4>

- **[7708](https://eips.ethereum.org/EIPS/eip-7708)** ETH transfers emit a log
- **[7732](https://eips.ethereum.org/EIPS/eip-7732)** Enshrined PBS
- **[7778](https://eips.ethereum.org/EIPS/eip-7778)** Block gas accounting w/o refunds
- **[7843](https://eips.ethereum.org/EIPS/eip-7843)** SLOTNUM opcode
- **[7928](https://eips.ethereum.org/EIPS/eip-7928)** Block-Level Access Lists
- **[7954](https://eips.ethereum.org/EIPS/eip-7954)** Increase max contract size
- **[7976](https://eips.ethereum.org/EIPS/eip-7976)** Calldata floor cost
- **[7981](https://eips.ethereum.org/EIPS/eip-7981)** Access list cost
- **[8024](https://eips.ethereum.org/EIPS/eip-8024)** SWAPN/DUPN/EXCHANGE
- **[8037](https://eips.ethereum.org/EIPS/eip-8037)** State creation gas

<h4 class="bal">PFI — Proposed, not yet on devnet</h4>

- **[7610](https://eips.ethereum.org/EIPS/eip-7610)** Revert creation w/ non-empty storage
- **[7979](https://eips.ethereum.org/EIPS/eip-7979)** Call & Return opcodes
- **[8163](https://eips.ethereum.org/EIPS/eip-8163)** Reserve `EXTENSION (0xae)` opcode

</div>
<div class="col">

<h4 class="epbs">CFI — Still being considered</h4>

- **[2780](https://eips.ethereum.org/EIPS/eip-2780)** <span class="d6">(on d6)</span> Reduce intrinsic tx gas
- **[7688](https://eips.ethereum.org/EIPS/eip-7688)** Forward-compatible CL data structures
- **[7904](https://eips.ethereum.org/EIPS/eip-7904)** General Repricing
- **[7997](https://eips.ethereum.org/EIPS/eip-7997)** <span class="d6">(on d6)</span> Deterministic Factory Predeploy
- **[8038](https://eips.ethereum.org/EIPS/eip-8038)** <span class="d6">(on d6)</span> State-access gas update
- **[8045](https://eips.ethereum.org/EIPS/eip-8045)** Exclude slashed validators
- **[8061](https://eips.ethereum.org/EIPS/eip-8061)** Increase exit & churn
- **[8080](https://eips.ethereum.org/EIPS/eip-8080)** Exits via consolidation queue
- **[8246](https://eips.ethereum.org/EIPS/eip-8246)** <span class="d6">(on d6)</span> Remove SELFDESTRUCT burn

<h4 class="bal">CFI — Networking</h4>

- **[7975](https://eips.ethereum.org/EIPS/eip-7975)** <span class="d6">(on d7)</span> eth/70 partial block receipts
- **[8070](https://eips.ethereum.org/EIPS/eip-8070)** <span class="d6">(on d6, opt)</span> eth/72 Sparse Blobpool
- **[8136](https://eips.ethereum.org/EIPS/eip-8136)** Cell-Level Deltas for Data Column Broadcast
- **[8159](https://eips.ethereum.org/EIPS/eip-8159)** <span class="d6">(on d7)</span> eth/71 BAL exchange

</div>
</div>

**Scope still in flight** — more PFI promotions expected; some CFI items may DFI before fork freeze.

---

## Day-to-day devnet tooling

<div class="eip-grid">
<div class="col">

<h4>Spin up &amp; drive</h4>

- **ethereum-genesis-generator** — one source of truth for fork params
- **Assertoor** — continuous test scenarios
- **spamoor** — tx, blob, MEV load gen
- **buildoor** — ePBS bid generator
- **Benchmarkoor** — client performance benchmarking

</div>
<div class="col">

<h4>Watch &amp; debug</h4>

- **Xatu** — beacon + execution event capture
- **Dora** — per-devnet block explorer (now supports EL and BAL data too)
- **panda CLI** — fetch + read compact logs across every devnet, no SSH

</div>
</div>

Same stack will be ran on mainnet shadowforks, public testnets, these devnets, and all future devnets — Glamsterdam isn't a one-off.

---

<!-- _class: lead -->

# Questions?

`github.com/ethpandaops/{bal,epbs,glamsterdam}-devnets`
Specs: `notes.ethereum.org/@ethpandaops/<network>`
