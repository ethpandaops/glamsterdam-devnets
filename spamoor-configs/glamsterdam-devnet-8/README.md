# spamoor configs — randomized jumpdest analysis (devnet-8)

Hand-maintained spammer configs for <https://spamoor.glamsterdam-devnet-8.ethpandaops.io>.
Import them through the UI; nothing here is deployed automatically.

> The `kubernetes/devnet-8/spamoor/values.yaml` in this repo is **Ansible-generated** from
> `ethpandaops.general.generate_kubernetes_config` and carries only the deployment (image,
> ingress, RPC endpoints, auth provider). Neither that template nor the upstream
> `spamoor` Helm chart has a field for declaring spammers, so spammers are runtime state
> in spamoor's own database — created through the UI or `POST /api/spammers/import`.
> That is why these live in a plain directory rather than in the k8s values.

## What they are

A port of [`execution-specs#3631`](https://github.com/ethereum/execution-specs/pull/3631)
(randomized jumpdest-analysis arms) to live spammers, plus a cross with the existing
spamoor-108 ring. The PR's point is that the analysis loop's branch predictor can be
defeated by a byte alphabet straddling `0x5b`/`0x60` — its own measurements put those arms
2–3× slower than periodic patterns. Everything devnet-8 has stressed so far, including the
whole spamoor-100 corpus behind BUG-897, is `0x5b`: the friendliest possible input.

| file | what it does | per 200M block | prep |
|---|---|---|---|
| `...-A-direct-port.yaml` | CREATE loop over 128 KiB of random initcode, STOP tail, account **is** created — faithful to the PR | 1.29 GB analysed | self-contained (3 prep spammers) |
| `...-B-revert-tail.yaml` | same, but the initcode tail REVERTs so the account-creation charge is refilled | 1.29 GB analysed | needs A's prep 1/3 + 2/3 |
| `...-C-random-ring.yaml` | spamoor-108 ring over a corpus of 64 KiB random-alphabet contracts | 4.14 GB analysed | needs A's prep 1/3, then ~13.7 h of corpus build |

Measured on geth's Amsterdam EVM (`evm t8n`): **20,286 execution gas per 131,072-byte
analysis** (6.46 bytes/gas) for A and B, **3,163 gas per 64 KiB cold code load**
(20.7 bytes/gas) for C. A and B consume **zero net state gas and leave nothing in state**.

Full design, verification table and the generator: `~/devnets/glamsterdam-devnet-8/work/jumpdest-3631/`.

## Importing

The UI's import accepts pasted YAML. The API accepts **either YAML or a URL**
(`ImportSpammersRequest.Input`), and this repo is public, so the raw URL avoids pasting
190 KB:

```
https://raw.githubusercontent.com/ethpandaops/glamsterdam-devnets/qu0b/spamoor-jumpdest-configs/spamoor-configs/glamsterdam-devnet-8/jumpdest-analysis-A-direct-port.yaml
```

(verified reachable: `200`. Swap the branch for `master` once this lands there.)

`jumpdest-analysis-A-direct-port.yaml` is large because the 64 KiB random source travels
as `init_code` (131 KB) and the pre-fund target list as call data (58 KB). B and C are
small — they reference the same blob by its CREATE2 address.

## Run order

1. **A prep 1/3** — deploys the 64 KiB random-alphabet source blob to
   `0x3b47073bd0313c8e775e215cb80d85b7c6990e61` (one tx, 120M gas). Shared by A, B and C.
2. **A prep 2/3** — deploys the CREATE driver to
   `0x100dae30856f1b5b689b1a88c8ddf18fc83bfbcf` (one tx). Arm- and tail-independent: the
   source and the initcode tail are call-data parameters, so this one driver serves every
   alphabet and both A and B.
3. **A prep 3/3** — pre-funds 900 CREATE targets (one tx, ~176.5M gas measured). Required
   by A only; without it every CREATE pays `NEW_ACCOUNT` = 183,600 state gas, ~9× the
   analysis itself. B does not need it.
4. **Attack A and/or B** — `throughput: 12` fills a 200M block (200M / 16,777,216 = 11.9 tx).
5. **C** — start the corpus deployer first; it is the long pole at ~2 contracts per block.

All addresses are CREATE2 off spamoor's well-known factory
(`0xe883a4ac7904c5b91faaec2ceccb236d985fc329`, verified live), so they are fixed and
computable before anything is deployed — that is what makes the pre-funding in step 3
possible. `addresses.json` lists every one of them, including the 900 pre-fund targets.

## Things that will silently waste a block

- **Do not start attack C before the corpus covers the ring driver's `n`.** Calling a ring
  slot with no code costs 3,000 gas and analyses nothing. Three ring drivers are
  pre-generated for n = 4096 / 8192 / 16384; point the attack at the one already covered.
  `monitor_corpus.py` in the work dir reports the frontier straight off the public RPC.
- **Do not skip A's prep 3/3 for attack A.** It still burns a full block of gas, but at
  183,600 state gas per CREATE it manages ~1,089 analyses per block instead of ~9,900, and
  leaves junk accounts behind. Symptom: transactions end in out-of-gas at exactly the gas
  limit instead of reverting below it.
- **Watch the balance reservation, not just the fee.** A pending transaction reserves
  `gas_limit × base_fee`: 2.4 ETH for a 120M-gas deploy, 3.8 ETH for the 190M-gas pre-fund
  at the configured 20 gwei. The refill amounts in these configs account for that.

## Later

If these earn a permanent place, the upstream home is `spammer-configs/` in
`ethpandaops/spamoor`, which the UI exposes as "Spammer Library". A packaged version of
A + B is parked on the branch `qu0b/spammer-configs-randomized-jumpdest` of
`qu0b/spamoor`; no PR has been opened.
