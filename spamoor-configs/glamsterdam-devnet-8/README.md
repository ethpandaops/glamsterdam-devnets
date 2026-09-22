# spamoor configs — randomized jumpdest analysis (devnet-8)

Hand-maintained spammer configs for <https://spamoor.glamsterdam-devnet-8.ethpandaops.io>.
Import them through the UI; nothing here is deployed automatically.

> `kubernetes/devnet-8/spamoor/values.yaml` in this repo is **Ansible-generated** from
> `ethpandaops.general.generate_kubernetes_config` and carries only the deployment (image,
> ingress, RPC endpoints, auth provider). Neither that template nor the upstream `spamoor`
> Helm chart has a field for declaring spammers — spammers are runtime state in spamoor's
> own database, created through the UI or `POST /api/spammers/import`. Hence a plain
> directory rather than anything in the k8s values.

## What these do

A port of [`execution-specs#3631`](https://github.com/ethereum/execution-specs/pull/3631)
(randomized jumpdest-analysis arms) to live spammers, plus a cross with the existing
spamoor-108 ring.

Every transaction CREATEs 128 KiB of initcode whose first bytes are `PUSH3 131041 ; JUMP`
— a jump to the last byte — so the EVM must run a full jumpdest analysis over the whole
thing while executing almost nothing. A counter written at offset 32 changes the code hash
on every iteration, so no client-side analysis cache can serve it. The bytes are drawn
from `{STOP, JUMPDEST, PUSH1}`, an alphabet that straddles the thresholds an analysis loop
branches on; the PR measures those arms **2–3× slower** than the equivalent periodic
pattern. Everything devnet-8 has stressed so far, including the whole spamoor-100 corpus
behind BUG-897, is `0x5b` — the friendliest possible input to that loop.

| file | what it does | analysed per 200M block | prep |
|---|---|---|---|
| `...-A-direct-port.yaml` | CREATE loop, STOP tail, the account **is** created — faithful to the PR | **1.28 GB** | self-contained (3 prep spammers) |
| `...-B-revert-tail.yaml` | same, but the initcode tail REVERTs, so the account-creation charge is refilled | **1.28 GB** | needs A's prep 1/3 + 2/3 |
| `...-C-random-ring.yaml` | the spamoor-108 ring over a corpus of 64 KiB random-alphabet contracts | **4.14 GB** | needs A's prep 1/3, then a ~13.7 h corpus build |

Measured on geth's Amsterdam EVM (`evm t8n`, 1.17.6-unstable), not modelled:

- **20,286 execution gas per 131,072-byte analysis** = 6.46 bytes/gas (A and B)
- **820 CREATEs per transaction**, 107.5 MB analysed, 16,728,106 gas used (A) /
  16,728,927 (B), both exiting through the driver's own REVERT
- **3,163 gas per 64 KiB cold code load** = 20.7 bytes/gas (C)
- A and B consume **zero net state gas and leave nothing in state** — verified: 0 accounts
  left behind

Extrapolating the PR's 35.8–74.9 MGas/s to a 200M block puts A and B at 2.7 s (erigon) to
5.6 s (nethermind) of `engine_newPayload`. That assumes MGas/s is flat in block size,
which should hold for a CPU-bound loop with no state access, but has not been measured
at 200M.

## Why B does not need pre-funding, and why its gas limit is odd

Under EIP-8037 a CREATE into a non-existent account costs `NEW_ACCOUNT` =
`STATE_BYTES_PER_NEW_ACCOUNT` 120 × `CPSB` 1530 = **183,600 state gas**, roughly 9× the
analysis it is hiding. A pre-funds its targets to avoid it (prep 3/3). B instead ends the
initcode in `REVERT`: in EELS `generic_create`
(`amsterdam/vm/instructions/system.py:186-189`) a failing child refills the whole charge,
and the analysis has already happened by then — `valid_jump_destinations` is computed when
the child frame is constructed, before any opcode runs.

B's `gas_limit` is **17,000,000**, not the EIP-7825 cap of 2²⁴. EIP-8037 splits `tx.gas`
into an execution budget capped at `TX_MAX_GAS_LIMIT` and a **state-gas reservoir** holding
the overflow. The extra 222,784 becomes reservoir, so each `NEW_ACCOUNT` charge is taken
from there and refilled when the child reverts, instead of spilling into execution gas. At
exactly 2²⁴ the reservoir is zero, the charge spills, the loop cannot finish its last
iteration and the transaction dies of out-of-gas — burning the limit and telling you
nothing. Measured: 16,728,927 via a clean REVERT (~820 CREATEs) versus an OOG at
16,777,216 (~822). It costs 0.29% of the gas to get a receipt that shows whether the loop
actually ran.

Block packing is unchanged either way: only `min(TX_MAX_GAS_LIMIT, tx.gas)` counts against
the block's execution dimension, so ~11.9 transactions fill a 200M block.

## Verifying before you import

The configs carry ~190 KB of hex, and every address in them is derived from that hex.
Two scripts (PyYAML only, no web3/eth-utils) let you check rather than trust:

```bash
python3 verify_config.py     # re-derives every address from the bytes; 911 checks
python3 disassemble.py       # the drivers, disassembled; --blob summarises the 64 KiB source
```

`verify_config.py` re-derives the CREATE2 addresses from each `init_code`, confirms the
blob address embedded in the attacks' `call_data`, confirms the pre-fund list really is
`CREATE(driver, 1..900)`, and checks the two invariants that otherwise fail silently:
that A's gas budget fits inside the pre-funded range, and that B's reservoir covers a
`NEW_ACCOUNT` charge. It catches the failure mode that matters — an edited `init_code`
with a stale address elsewhere, which still burns a full block while analysing nothing.

## Importing

The UI import accepts pasted YAML. The API accepts **either YAML or a URL**
(`ImportSpammersRequest.Input`), and this repo is public, so the raw URL avoids pasting
190 KB:

```
https://raw.githubusercontent.com/ethpandaops/glamsterdam-devnets/qu0b/spamoor-jumpdest-configs/spamoor-configs/glamsterdam-devnet-8/jumpdest-analysis-A-direct-port.yaml
```

(verified reachable: `200`. Swap the branch for `master` once this lands there.)
Only the A file is large — the 64 KiB random source travels as `init_code` (131 KB) and
the pre-fund list as call data (58 KB). B and C reference the same blob by its address.

## Run order

1. **A prep 1/3** — deploys the 64 KiB random-alphabet source blob to
   `0x3b47073bd0313c8e775e215cb80d85b7c6990e61` (one tx, 120M gas). Shared by A, B and C.
2. **A prep 2/3** — deploys the CREATE driver to
   `0x100dae30856f1b5b689b1a88c8ddf18fc83bfbcf` (one tx). Arm- and tail-independent: the
   source and the tail word are call-data parameters, so this one driver serves every
   alphabet and both A and B.
3. **A prep 3/3** — pre-funds 900 CREATE targets (one tx, ~176.5M gas measured). A only.
4. **Attack A and/or B** — `throughput: 12` fills a 200M block.
5. **C** — start the corpus deployer first; it is the long pole at ~2 contracts per block.

All addresses are CREATE2 off spamoor's well-known factory
(`0xe883a4ac7904c5b91faaec2ceccb236d985fc329`, verified live), so they are fixed before
anything is deployed — which is what makes step 3 possible at all. `addresses.json` lists
every one, including the 900 pre-fund targets.

## Things that silently waste blocks

- **Restarting the corpus spammer starts it over.** `factorydeploytx` derives each salt as
  `start_salt + <transaction index within this run>`, so a restarted spammer re-deploys
  contracts that already exist — full blocks at ~100M gas each, zero progress. To resume,
  set `start_salt` to the current frontier and reduce `total_count` to match, before
  restarting.
- **Do not point attack C at a ring larger than the corpus.** A ring slot with no code
  costs 3,000 gas and analyses nothing. The config ships pointing at the **smallest** ring
  (n=4096) on purpose; move it to n=8192 / n=16384 as the corpus grows, and confirm the
  prefix is gap-free first — deployments run concurrently across wallets, so the deployed
  set can have holes that a sampled check will miss.
- **Do not skip prep 3/3 for attack A.** It still burns a full block, but manages ~1,089
  analyses per block instead of ~9,900 and leaves junk accounts behind. Symptom: the
  transaction ends in out-of-gas at exactly its limit instead of reverting below it.
- **Watch the balance reservation, not just the fee.** A pending transaction reserves
  `gas_limit × base_fee`: 2.4 ETH for a 120M-gas deploy, 3.8 ETH for the 190M-gas pre-fund
  at the configured 20 gwei. The refill amounts here account for that. Live base fee is
  8 wei, so 20 gwei leaves ample headroom for the rise these spammers cause.

## Provenance

Generated and verified by the toolkit in the devnet-8 knowledge base (not in this repo):
generator, the three `evm t8n` verification suites, a corpus monitor with an exact
gap check, and the same configs for the other three alphabets in the PR
(`stop_jumpdest`, `jumpdest_push1`, `stop_jumpdest_2push1`). The corpus initcode and the
ring driver are reused unchanged from the BUG-897 work; the ring-driver generator
reproduces the live spamoor-108 driver byte for byte.

If these earn a permanent place, the upstream home is `spammer-configs/` in
`ethpandaops/spamoor`, which the UI exposes as "Spammer Library". A packaged version of
A + B is parked on `qu0b/spammer-configs-randomized-jumpdest` in `qu0b/spamoor`; no PR has
been opened.
