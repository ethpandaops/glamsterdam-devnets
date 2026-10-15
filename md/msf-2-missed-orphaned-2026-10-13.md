# msf-2 missed and orphaned blocks — 2026-10-13 (genesis → slot 8156, 16:14 UTC)

Source: Dora `/api/v1/slots` (with_missing/with_orphaned), ClickHouse `external.otel_logs`.
**202 missing, 21 orphaned** out of 8,158 slots. Network stayed finalizing throughout.

Dora caveat: `/api/v1/epoch/N` (and `panda dora epoch`) reports `orphanedblocks: 0` and counts
orphans as `missedblocks` — use `/api/v1/slots?with_orphaned=2` for orphans.

## 1. Nimbus CL skips the slot when local getPayload times out (ongoing) — 160+ misses

| Pairing | Missed | getPayload timeouts |
|---|---:|---:|
| nimbus-reth-1 | 114 | 114 |
| nimbus-besu-1 | 29 | 27 |
| nimbus-erigon-1 / nimbus-ethrex-1 (since 15:47) | 4 / 4 | 4 / 4 |
| nimbus-geth-1 / nimbus-nethermind-1 | 0 | 0 |

Every miss: `engine_getPayloadV6` at slot start → `WRN Timeout while getting execution payload`
1.5 s later → no block, although a builder-0 bid was validated ~0.4 s before the slot (e.g.
nimbus-erigon-1 slot 8129, 16:08:47.606 bid / 16:08:49.550 timeout). Known mechanism —
[report 05](msf-2-benchmark-2026-10-12/05-nimbus-remote-bid-fallback.md). New today: it spread
from Reth to Erigon/Ethrex/Besu once the workload moved to ~199M-gas blocks at 16:06
(slots 8118+). Nimbus–Reth misses had dropped to ~1/h while load was lower (08:00–14:00).

## 2. Erigon fell behind under the 14:17 high-tx-count load — 12 misses on Erigon-paired validators (14:18–14:42)

Load step at slot 7570 (14:17:00): 127–199M gas blocks with 6–9.5k txs each.
prysm-erigon-1: block 24459869 (6.05k txs) took **11.65 s**; `warmBAL commitment warmup`
spent 7.9 s then `context canceled`; the same block was then re-executed (11.7 s, 4.0 s, 6.5 s within the first minute; **12 runs in total**,
`isForkValidation=true`) as new payloads arrived, followed by a backward block download.
Slowest block: 24459888 (18.8 s median) — see the [Erigon slowest-block report](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/810443/msf-2-erigon-slowest-block-2026-10-13.html). All six Erigon ELs returned `SYNCING` from 14:13–14:17;
LH/Lodestar/Teku pairings recovered ~14:28, Nimbus/Prysm ~14:43, Grandine later.
CLs then correctly refused to propose (lodestar-erigon-1 slot 7619: `produceBlockV4 503 Node is
syncing - Parent block's execution payload not yet validated`).
Misses: prysm-erigon 5/6, lodestar-erigon 3/5, nimbus-erigon 3/3, teku-erigon 1/3.
No EL restarts in 13:30–15:00. Erigon follow-up: why validated fork blocks are re-executed.

## 3. Orphans — all 21 from Besu-backed proposers except one; none since 10:03

| Class | Slots | Mechanism |
|---|---|---|
| Late, correct parent | grandine-besu ×11 (22:02–07:04, 3.2–4.8 s), lodestar-besu ×3 (3.1–4.4 s), nimbus-besu 2629 (1.1 s), lighthouse-besu 2885 (6.1 s) | see below |
| Stale parent | 2343 LH–Besu (4 slots), 3918 LH–Besu (8), 6304 LH–Besu (21), 6127 LH–Erigon (60 slots; a canonical block also exists at 6127) | lagging EL/CL proposed on an old head |

Grandine–Besu slot 5409 (07:04:48): Besu finished importing #24457756 at 47.932 (82.6M gas,
**6.35 s exec**), 70 ms before the slot. Grandine's getPayload hit its 1 s timeout at 49.008
(`all Eth1 RPC endpoints exhausted`); Besu answered at 52.004 with an **empty** payload
(0 tx) while the cancelled build task for the previous payloadId `0x24790bd56aad794d` was still
running (`New proposal ... block 24457756` at 52.241). Grandine retried and published the
builder-0 block at 52.534 (**4.5 s late**) → orphaned. Overlaps with the Besu execution delays in
[report 01](msf-2-benchmark-2026-10-12/01-besu-heap-exhaustion.md).

## Re-check

```bash
D=https://dora.glamsterdam-msf-2.ethpandaops.io
curl -s "$D/api/v1/slots?limit=1000&with_orphaned=2"   # orphans
curl -s "$D/api/v1/slots?limit=1000&with_missing=2"    # missing
panda clickhouse query clickhouse-raw "SELECT ResourceAttributes['instance'] i, toStartOfHour(Timestamp) h, count() FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['container.name']='beacon' AND ResourceAttributes['ethereum_cl']='nimbus' AND Timestamp > now() - INTERVAL 1 DAY AND Body LIKE 'WRN%Timeout while getting execution payload%' GROUP BY i,h ORDER BY h,i"
```
