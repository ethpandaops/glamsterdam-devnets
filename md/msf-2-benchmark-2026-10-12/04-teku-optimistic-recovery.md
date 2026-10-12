# Optimistic recovery delays during rollout and live operation

During the release rollout, Teku 26.10.0 on the Geth and Erigon pairings followed the beacon head but remained optimistic for several minutes and skipped validator attestations. The ELs continued importing canonical execution blocks while Engine interactions returned SYNCING. During later read-only monitoring, both Teku–Erigon and Lodestar–Erigon temporarily returned to optimism without a restart. This is worth a focused synchronization and recovery test with the consensus and execution-client teams; the current evidence does not identify a single faulty component.

## Environment and impact

Both nodes have 1,000 validators and run the msf-2 Gloas and Amsterdam configuration, with 12-second slots and a 200-million-gas limit. The pairings are Teku 26.10.0 with Geth v1.17.8 and Teku 26.10.0 with Erigon v3.7.1. Images and validator ranges are recorded in the [deployment pins](../../ansible/inventories/msf-2/group_vars/all/images.yaml) and [inventory](../../ansible/inventories/msf-2/inventory.ini).

The later Lodestar pairing reports `Lodestar/v1.50.0/003bd66` and `erigon/3.7.1/linux-amd64/go1.27.1`. Its [runtime command](evidence/lodestar-erigon-runtime.json) confirms discovery is disabled and three static shadowfork seed peers are configured. The direct samples recorded three EL peers on both Erigon pairings. Preserve this topology in a reproduction and compare it with broader peering when evaluating download delays.

The initial restart incidents below are **historical rollout occurrences**. The later recurrence was observed during read-only monitoring and was not induced by an operator intervention.

## Observed sequence

All times are UTC on October 12, 2026. The [rollout timeline](evidence/rollout-timeline.log) preserves each held health check and the final recovery.

| Pairing | Observations |
|---|---|
| Teku and Erigon | After the 21:36 upgrade, CL head followed the network while `is_optimistic=true`; validators skipped attestations. Engine calls returned SYNCING while Erigon downloaded and imported the requested blocks. The first recovery attempt also exposed the separately documented stored-envelope failure. After checkpoint and engine recovery, a further clean beacon restart at 21:51 again stayed optimistic until approximately 21:55. |
| Teku and Geth | Following the 21:58 upgrade, optimistic/offline health checks persisted from 21:59 through 22:02. Geth repeatedly requested sync to the new fork-choice head and imported the requested chain segment within roughly three to five seconds. Teku still skipped attestations. The first passing sample was at 22:03:08; an execution restart then reset the stability period, and the final gate passed at 22:04:51. |

[Initial Erigon pairing logs](evidence/teku-optimistic-startup.log) include `Skipped producing attestation while node is syncing` and `Waiting for execution layer sync`. The Geth and Erigon pairings eventually resumed attestations and passed direct sync, canonical-head and finality checks.

## Unprompted recurrence during monitoring

At 22:58:37, both Teku–Erigon and Lodestar–Erigon started receiving SYNCING statuses. Erigon then requested backward downloads of recent parent/head blocks, completed small batches within a few seconds, and again needed additional recent blocks on later fork-choice calls. The [bounded recurrence capture](evidence/erigon-optimistic-recurrence.json) records the hashes, download completion, and subsequent VALID responses.

Teku skipped **31 attestations at slot 2982**, logged at 22:59:24.124, as well as some aggregate, sync-contribution and payload-attestation duties during this interval. A 23:00 direct monitoring sample found Lodestar optimistic; the following minute's sample and independent follow-up checks found both pairings execution-valid at the same canonical root. Neither client was restarted or sent an operator fork-choice retry. This later episode recovered unaided and demonstrates that the liveness symptom is not confined to the rollout's restart sequence.

Lodestar's validator logs quantify proposer impact too: at **23:00:36**, its slot-**2988** `produceBlockV4` request failed with **HTTP 503**, because the parent execution payload was not yet validated. The [focused duty capture](evidence/lodestar-erigon-slot2988.json) records the refusal and resumed payload attestations at slot 2989. The [completed epoch-93 census](evidence/proposal-epoch-93.json) independently identifies 2988 as a missing canonical slot, assigned to validator **28504** on this host.

The report does not infer a protocol violation merely from SYNCING while a parent is unavailable. The investigation should explain the repeated recent-parent downloads and lost duty time, including the order in which each CL supplies envelopes and retries engine calls.

The [initial transition](evidence/erigon-initial-syncing-transition.json) provides a more specific test condition: both ELs unwind from execution height **24455426** toward **24455424** while applying fork choice at height **24455425**. A new payload for the replacement height-24455426 block arrives while that work is in progress and receives a quick SYNCING response. [Independent canonical chain context](evidence/erigon-recurrence-chain-context.json) identifies that replacement as slot **2978**, hash `0xbd0610bd473b200aa2126362d3f5a310cde6aef72b7b5f3322c19d43fc518954`, following the missing canonical slot 2977.

In [Erigon v3.7.1's Engine server](https://github.com/erigontech/erigon/blob/8c1e3893d77d230720d172f1492d95b5777a862c/execution/engineapi/engine_server.go#L493), a quick status can return before the supplied new payload reaches `HandleNewPayload`. The helper can report SYNCING for download/readiness conditions. This narrows the code and timing to instrument; the captured logs do not prove which helper branch fired, nor that returning SYNCING itself was wrong. A private test should overlap a fork-choice unwind with a replacement payload, then verify prompt import/retry and validator recovery once execution is ready.

## What remains uncertain

**Suggested priority: medium. Confidence: high in the skipped duties and prolonged optimistic state; medium in the recovery mechanism.** The EL returning SYNCING for an unknown or in-flight head is not itself a protocol violation. The actionable question is whether the CL and EL make timely progress out of that state after a restart under this workload.

Several interventions occurred: authenticated fork-choice retries for already canonical execution heads, execution restarts, and—in the Erigon pairing—a checkpoint restore and additional beacon restart. A VALID response to an operator request does not prove the CL consumed that response. Recovery after these interventions cannot establish which one was necessary, or whether the node would eventually have recovered unaided.

## Next client work

On a private restore, keep execution running and restart only the consensus client while the same workload and external builders continue. Trace each FCU and newPayload request, response, parent hash and retry. Check the CL's handling of pending optimistic envelopes and whether it retries or imports them when their execution parents become available. Repeat with both ELs, include the Lodestar–Erigon pairing, and compare a quiescent workload. Also run the live workload without a restart to cover the later recurrence. Use resumed validator duties and fully validated canonical heads as the success condition, rather than beacon head advancement alone.

The saved Erigon database failure has its [own report](02-teku-persisted-envelope.md); it must not be treated as proof of the cause of this broader liveness symptom. The post-rollout watcher leaves the live benchmark unchanged and does not perform the proposed restart experiments.

## Rechecking the evidence

```bash
panda clickhouse query-raw clickhouse-raw "SELECT Timestamp, ResourceAttributes['host.name'] AS host, Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name'] IN ('teku-erigon-1','teku-geth-1') AND ResourceAttributes['container.name']='beacon' AND Timestamp >= toDateTime('2026-10-12 21:36:00') AND Timestamp < toDateTime('2026-10-12 22:05:00') AND (Body LIKE '%Skipped producing attestation%' OR Body LIKE '%Waiting for execution layer sync%' OR Body LIKE '%Syncing completed%') ORDER BY Timestamp ASC LIMIT 200"
panda clickhouse query-raw clickhouse-raw "SELECT Timestamp, Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name']='teku-geth-1' AND ResourceAttributes['container.name']='execution' AND Timestamp >= toDateTime('2026-10-12 21:59:00') AND Timestamp < toDateTime('2026-10-12 22:03:00') AND (Body LIKE '%Forkchoice requested sync%' OR Body LIKE '%Imported new chain segment%') ORDER BY Timestamp ASC LIMIT 80"
```
