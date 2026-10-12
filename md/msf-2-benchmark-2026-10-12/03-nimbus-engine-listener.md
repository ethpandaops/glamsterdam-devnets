# Nimbus execution Engine API listener stops serving requests

`nimbus-nimbusel-1` has a persistent outage of its Engine API listener while ordinary execution RPC, peer activity and the process remain live. The engine listener's internal accept queue is full. This adds runtime evidence to the Nimbus HTTP accept-loop failure class investigated on devnet-8. Attribution to a particular listener-exit branch remains unconfirmed.

## Environment and scope

The execution client is Nimbus v0.4.2, build `705f4d9a`, paired with Nimbus consensus v26.10.0 on `glamsterdam-msf-2`. The container started at 12:53:22 UTC on October 12 and had zero recorded restarts during the initial checks. Both Nimbus execution observers are deliberately configured for experimental snap sync from an empty database, with static shadowfork peers and discovery disabled. They hold no validator allocation. See [Nimbus execution configuration](../../ansible/inventories/msf-2/group_vars/nimbusel.yaml) and [inventory](../../ansible/inventories/msf-2/inventory.ini).

Execution height zero during that sync is insufficient by itself to establish a defect. The distinguishing evidence is that independent lightweight Engine requests cannot be served, while the other RPC listener answers.

## Runtime evidence

The [onset query](evidence/nimbus-engine-outage-onset.json) finds the last completed engine requests in its 15:35–15:39 UTC window:

```text
DBG 2026-10-12 15:35:50.633+00:00 Processed JSON-RPC request                 topics="jsonrpc router" id=ok(1614) methodName=engine_newPayloadV5 len=66
DBG 2026-10-12 15:35:50.697+00:00 Processed JSON-RPC request                 topics="jsonrpc router" id=ok(1615) methodName=engine_forkchoiceUpdatedV4 len=101
```

At 15:39:10.995, the CL logged `Connection to EL node degraded`, `failedRequest=newPayload`, and `Request timed out`. Later [execution status samples](evidence/nimbus-snap-current.json) still reported `syncState=idle`, target 24453294, and a last-FCU age exceeding six hours.

An authenticated loopback `engine_exchangeCapabilities` request timed out after **10.018 seconds**. On the other observer, `lighthouse-nimbusel-1`, the same read-only method returned in **0.009 seconds**. [Probe results](evidence/nimbus-engine-capabilities.json) retain the response and timing; the probe's approximate capture time is explicitly identified in that file. No build or fork-choice request was injected during these checks.

A [repeat probe at 23:22 UTC](evidence/nimbus-engine-capabilities-final.json) again timed out on `nimbus-nimbusel-1` after **10.011 seconds**, while the other observer responded in **0.010 seconds**. Regular execution RPC and the process remained responsive in the monitoring samples.

[Socket evidence](evidence/nimbus-engine-sockets.txt) is from **inside** the execution container, not only Docker's host-side proxy. Its `/proc/net/tcp` listener on hexadecimal port `2167` (8551) has `rx_queue=00000065` (101), while port `2161` (8545) has a zero queue. A [network-namespace check at 22:40:34 UTC](evidence/nimbus-engine-accept-queue.txt) independently reports `LISTEN 101 100` for 8551 and `LISTEN 0 100` for 8545. Host-side Docker proxy queues remained empty and would have hidden this distinction.

The regular execution RPC responds to block-number and peer-count reads. The CL continues following the beacon chain optimistically and reports `el_offline=true`. This is an execution-validation outage on an unstaked observer; it does not explain network-wide finality loss.

## Assessment and duplicate handling

**Suggested priority: high for listener supervision and service health. Confidence: high in the persistent engine-listener outage; medium in the precise internal exit cause.** The full queue, timed-out independent request, stale engine activity and responsive other listener narrow the failure below the external proxy. They do not introspect the listener's accept future.

[The deployed release source](https://github.com/status-im/nimbus-eth1/blob/705f4d9aced29de0049d7ad5f686b0e585f3f38d/execution_chain/rpc/rpc_server.nim) contains an accept-loop exit on an accepted transport identification error. That source path is a candidate mechanism, not a demonstrated trigger in this run. The prior devnet-8 investigation found both RPC listeners affected on the same release; this occurrence supplies a variant with only the Engine listener visibly blocked.

Capture accept-loop completion reasons and verify that an individual connection failure cannot permanently stop later acceptance. Add a private regression test with a failed accepted transport followed by a second ordinary client. Service health should test request completion separately for execution RPC and Engine RPC.

[Issue 4881](https://github.com/status-im/nimbus-eth1/issues/4881) concerns slow synchronous payload construction. This observer has no validator or builder duties, and the captured engine silence lasts hours. A short build stall has not been established as the cause of this listener outage.

## Rechecking the evidence

```bash
ssh glamsterdam-msf-2-nimbus-nimbusel-1 'docker exec execution cat /proc/net/tcp'
ssh glamsterdam-msf-2-nimbus-nimbusel-1 'curl -fsS http://127.0.0.1:5052/eth/v1/node/syncing'
panda clickhouse query-raw clickhouse-raw "SELECT Timestamp, Body FROM external.otel_logs WHERE ResourceAttributes['network']='glamsterdam-msf-2' AND ResourceAttributes['host.name']='nimbus-nimbusel-1' AND ResourceAttributes['container.name']='execution' AND Timestamp >= toDateTime('2026-10-12 15:35:00') AND Timestamp < toDateTime('2026-10-12 15:39:00') AND Body LIKE '%engine_%' ORDER BY Timestamp DESC LIMIT 30"
```

The observation window is read-only. The node was not restarted or reconfigured to prove a recovery or re-induce the failure.
