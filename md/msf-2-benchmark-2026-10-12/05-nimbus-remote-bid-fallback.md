# Nimbus drops proposer duties when the local payload times out

Nimbus consensus v26.10.0 on `nimbus-reth-1` missed **all 12 assigned proposer duties in completed epochs 88–96**, even though an external builder bid was received and validated before every affected slot. Each duty attempted a local `engine_getPayloadV6` and timed out after approximately 1.5 seconds. The deployed release's proposal path returns on an absent local candidate before selecting the pooled builder bid.

This is additional runtime evidence for the previously investigated Nimbus remote-only proposal gap. It is worth Nimbus consensus attention; Reth's local construction latency should be investigated separately rather than assumed to have the same root cause.

## Environment and impact

The live version endpoint identifies **Nimbus/v26.10.0-657beb-stateofus**, matching release commit `657beb3d6e13fcfddb1a7ca2dbd2d3d0516f8ca8`. Execution is Reth v2.7.0. The node has validator indices **21000–21999** and uses integrated beacon validators. It stays synced, execution-valid and near the canonical head; process/head health therefore does not reveal its proposer failures. The network continues finalizing.

The workload and network conditions are recorded in the [benchmark workload sample](workload.md) and [inventory](../../ansible/inventories/msf-2/). No restart or client configuration change was induced during this observation window.

## Duty census

The [initial reference headers and duties](evidence/slots-epochs88-90.json), [Dora missed-slot records](evidence/missed-slot-details-epochs88-90.json), and later per-epoch captures establish the schedule and absent blocks. The [derived summary](evidence/monitoring-summary.json) combines all nine completed epochs. All 12 Nimbus–Reth assignments were missing:

| Epoch | Missed slots | Proposer indices |
|---|---|---|
| 88 | 2821, 2823, 2844, 2846 | 21061, 21837, 21365, 21889 |
| 89 | 2859, 2879 | 21766, 21009 |
| 90 | 2887, 2895 | 21734, 21772 |
| 91 | 2922 | 21011 |
| 93 | 2981, 2992 | 21131, 21339 |
| 95 | 3051 | 21010 |

There were 16 total missing canonical slots among those 288 network slots; the other four were assigned to Grandine–Besu, Lighthouse–Besu and Lodestar–Erigon. The 12-of-12 figure is limited to these nine completed epochs, not the whole benchmark or all Nimbus pairings. Epochs 92, 94 and 96 had no assigned Nimbus–Reth proposer duties.

## Proposal timeline and source mechanism

The [proposal log query](evidence/nimbus-reth-proposal-logs.json) captures each affected duty's validated external bid and local timeout. For slot 2821:

| Time, UTC October 12 | Event |
|---|---|
| 22:27:10.524 | Reth creates local payload job `0x3f6d2b859c146bc8` |
| 22:27:11.607 | Nimbus validates builder-index-0 bid for slot 2821 and places it in the bid pool; value 101000000 |
| 22:27:12.043 | Nimbus requests the local engine payload and sends `engine_getPayloadV6` |
| 22:27:13.543 | Nimbus logs `Timeout while getting execution payload` |
| Completed-epoch check | Canonical slot 2821 has no beacon block |

The [focused beacon capture](evidence/nimbus-reth-slot2821-beacon.json) and [execution capture](evidence/nimbus-reth-slot2821-execution.json) preserve this sequence. Across 22:24–23:24, the [production error counter](evidence/nimbus-proposal-counters-history.json.gz) increased from 21 to 34 while the proposed-block counter stayed at 69. The log query records 13 local fetches and 13 timeouts, including slot 2808 in the partially observed boundary epoch, which is excluded from the completed-epoch census.

In [the deployed proposal source](https://github.com/status-im/nimbus-eth2/blob/657beb3d6e13fcfddb1a7ca2dbd2d3d0516f8ca8/beacon_chain/validators/beacon_validators.nim#L616), `proposeBlockAux` returns when `engineBid.isNone()`. The Gloas pooled/external bid selection follows that guard. [The EL manager](https://github.com/status-im/nimbus-eth2/blob/657beb3d6e13fcfddb1a7ca2dbd2d3d0516f8ca8/beacon_chain/el/el_manager.nim#L531) uses a one-second payload timeout plus 500 ms processing overhead, consistent with the observed timing. This source ordering explains why an otherwise usable remote candidate cannot rescue a failed local fetch.

## Assessment and next client work

**Suggested priority: high. Confidence: high in missed duties, pre-slot validated bids, and the deployed local-candidate prerequisite; medium in the specific cause of Reth's delayed local result.** This is repeated released-runtime evidence, not a new controlled reproduction or a claim that current trunk was exercised.

Implement and test a complete remote-only Gloas proposal path when the local EL produces no candidate. Preserve bid eligibility, payload-availability/failsafe rules, parent execution requests and signing safety. Removing the early guard alone is insufficient: later code also dereferences the local bid. A private regression should provide an eligible external bid before the slot, force local getPayload to fail or time out, and assert a valid beacon block is signed and published once.

For Reth, trace a matching local payload job's finalization and response timing under the captured workload. The saved [getPayload metrics](evidence/reth-getpayload-history.json.gz) show no new completed V6 responses in the captured interval, but do not identify why those jobs failed to answer before the CL deadline. An operator-injected getPayload was deliberately avoided because resolving an active payload job could affect the live proposal path.

Treat this as a follow-up to the existing fallback investigation, with current-build runtime evidence attached, rather than claiming a distinct new source defect. No upstream issue has been filed.
