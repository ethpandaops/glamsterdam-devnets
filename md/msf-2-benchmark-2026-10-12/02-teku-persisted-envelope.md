# Teku rejects a persisted payload envelope during restart

Teku 26.10.0 repeatedly failed to initialize storage on `teku-erigon-1` because reconstruction of a stored blinded envelope yielded a zero parent execution hash. The corresponding canonical beacon block and independently retrieved payload both contain the same nonzero parent hash. A finalized checkpoint restore recovered the node while preserving its validator keys and slashing protection.

## Environment and impact

The node runs 1,000 validators on `glamsterdam-msf-2`, a mainnet-preset network starting on Gloas and Amsterdam. Teku was upgraded from 26.9.1 to 26.10.0 at approximately 21:36 UTC on October 12, 2026. Its execution client remained Erigon v3.7.1. See the [image pins](../../ansible/inventories/msf-2/group_vars/all/images.yaml) and [validator allocation](../../ansible/inventories/msf-2/inventory.ini).

The initial upgrade left the node optimistic. A subsequent beacon restart exposed the storage failure and a restart loop. This made the node's validators unavailable until recovery. Network-wide finality continued.

## Exact failure and independent block evidence

[Preserved startup logs](evidence/teku-startup-failure.log) show the exception repeatedly:

```text
Blinded execution payload envelope parent block hash 0x0000000000000000000000000000000000000000000000000000000000000000 does not match GLOAS block bid parent block hash 0x04da4849f769bf233751505c809d291d8ab70f91cccdcd46909b4bb55c649f7b for block root 0x3c681a001b2ec71bf23d98c8b1b963b756d53477cb9a4daa52f65c71f25c6549
```

The stack reaches `StoredBlockMetadata.getValidatedPayloadHeader`, `extractGloasForkChoiceRebuildData`, `KvStoreDatabase.buildHotBlockMetadata`, and `createMemoryStore`. This places the failure in reconstruction of stored hot-block metadata during startup, before normal validator operation resumes.

The affected root is beacon slot **2559**, execution block **24455040**, with builder registry index **0**. Slot 2559 began at **21:34:48 UTC**, before the approximately 21:36 upgrade. That establishes the block's age, not when the failing local metadata was written or converted. The [canonical beacon block](evidence/teku-slot2559-block.json) commits to:

| Field | Value |
|---|---|
| Parent execution hash | `0x04da4849f769bf233751505c809d291d8ab70f91cccdcd46909b4bb55c649f7b` |
| Execution hash | `0x1cc802c819736d0a4b484f814d563e63c891fbb5dcb7b0a2f515ab7c097eb7dd` |
| Gas limit | 200000000 |

The [signed envelope retrieved from teku-nethermind-1](evidence/teku-slot2559-envelope.json) has those same parent and execution hashes. Thus, a globally unavailable or zero-parent payload does not explain this local startup exception. This does not prove when or how the local stored header became inconsistent.

## Timeline

All times below are UTC on October 12, 2026. The [rollout timeline](evidence/rollout-timeline.log) and [initial optimistic-startup logs](evidence/teku-optimistic-startup.log) preserve the original observations.

| Time | Event |
|---|---|
| 21:36–21:38 | Updated Teku starts, follows beacon head, and stays optimistic while execution returns SYNCING |
| Around 21:40 | Beacon restart attempted after execution imports; storage initialization begins failing |
| 21:41 | Repeated startup exceptions identify the same root and zero parent hash |
| 21:43 | Beacon database preserved; fresh beacon starts from a canonical finalized SSZ state |
| 21:50 | Node exits optimistic mode and resumes validator duties after additional engine recovery |
| 21:51–21:56 | Temporary initial-state option removed; a further restart succeeds and health checks pass |

The preserved beacon database is on the node at `/data/teku/beacon.before-release-recovery-20261012`. Validator data under `/data/teku/validator` and keys under `/data/teku-validator` were retained. The recovery sequence included both checkpoint restoration and execution-engine intervention; it is not an isolated test of one fix.

## Assessment and next client work

**Suggested priority: high. Confidence: high in the startup failure and stored-header disagreement; medium in its creation mechanism.** This is a released-runtime occurrence, **not** a new controlled reproduction or proof that the version upgrade introduced the defect.

[The 26.10.0 source](https://github.com/Consensys-Incorporated/teku/blob/26.10.0/storage/api/src/main/java/tech/pegasys/teku/storage/api/StoredBlockMetadata.java) checks the envelope's root, parent hash, block hash and gas limit against the beacon bid during metadata reconstruction. The observed stack reaches that check. The unresolved question is the writer or conversion path that supplied the zero header.

Inspect the saved database in an isolated environment with validators disabled. Compare the stored blinded envelope for slot 2559 with the attached canonical envelope. Check serialization round trips and the handling of optimistic, incomplete and pre-upgrade envelopes. Add a restart regression test using this storage record. Preserve the validation checks: repairing or refetching inconsistent metadata must not accept a mismatching payload.

## Rechecking the evidence

```bash
panda dora slot glamsterdam-msf-2 2559
ssh glamsterdam-msf-2-teku-nethermind-1 'curl -fsS http://127.0.0.1:5052/eth/v2/beacon/blocks/2559'
ssh glamsterdam-msf-2-teku-nethermind-1 'curl -fsS http://127.0.0.1:5052/eth/v1/beacon/execution_payload_envelopes/2559'
panda clickhouse query-raw clickhouse-raw "SELECT Timestamp, Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name']='teku-erigon-1' AND ResourceAttributes['container.name']='beacon' AND Timestamp >= toDateTime('2026-10-12 21:40:00') AND Timestamp < toDateTime('2026-10-12 21:43:00') AND Body LIKE '%Blinded execution payload envelope parent block hash%' ORDER BY Timestamp ASC LIMIT 20"
```
