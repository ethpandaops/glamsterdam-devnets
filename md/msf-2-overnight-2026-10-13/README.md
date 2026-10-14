# Glamsterdam msf 2 overnight monitoring October 13 to 14 2026

Monitoring is running for **2026-10-13T21:48:30+00:00 to 2026-10-14T08:00:00+00:00**. Last tick: **2026-10-14T08:04:01.711783+00:00**. The latest full check found **36/36 validator pairings** healthy at **2026-10-14T08:04:01.711783+00:00**. Reference finalized epoch advanced from **305** to **401**. This is sampled health, not a claim of uninterrupted operation.

The initial baseline found all 36 validator pairings healthy. Two unstaked Nimbus EL observers retained their previously documented optimistic or Engine offline state. These are tracked as known conditions. [Baseline](evidence/baseline.json). All six Besu hosts also retained afternoon OOM artifacts discovered at startup; these predate the overnight window and are detailed in [the Besu follow-up](besu-oom-followup.md). [Existing client reports](../msf-2-issue-reports-2026-10-13/README.md).

## Findings requiring review

Events are evidence for investigation. Threshold crossings and log errors are candidates; they do not establish a new client defect. Counts are sampled observations or distinct retained log excerpts, not outage counts. Recovery can occur between samples. Known conditions remain labelled separately.

| Signal | Host | Classification | First observed UTC | Last observed UTC | Observations | Latest detail |
|---|---|---|---|---|---:|---|
| besu_heap_dump | grandine-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T08:04:01.711783+00:00 | 123 | {"path": "/data/besu-profiling/runs/20261013T100640Z-94444f52-6769-4dcb-ba01-6ef765f9d254/heap.hprof", "bytes": 26973208860, "mtime": "2026-10-13T16:44:12.603203+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T080401Z.json) |
| besu_heap_dump | lighthouse-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T08:04:01.711783+00:00 | 123 | {"path": "/data/besu-profiling/runs/20261013T095939Z-7b2c4fe2-30bd-4cd2-9731-8cf6c93e0e38/heap.hprof", "bytes": 26748214310, "mtime": "2026-10-13T17:00:47.594610+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T080401Z.json) |
| besu_heap_dump | lodestar-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T08:04:01.711783+00:00 | 123 | {"path": "/data/besu-profiling/runs/20261013T095722Z-6609d3b1-3e74-4749-89d9-9c826158ed9c/heap.hprof", "bytes": 27729214978, "mtime": "2026-10-13T20:23:26.367896+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T080401Z.json) |
| besu_heap_dump | nimbus-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T08:04:01.711783+00:00 | 123 | {"path": "/data/besu-profiling/runs/20261013T094449Z-42cf0cfb-966d-41d6-806d-9342b1b27159/heap.hprof", "bytes": 26750411558, "mtime": "2026-10-13T16:29:56.446991+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T080401Z.json) |
| besu_heap_dump | prysm-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T08:04:01.711783+00:00 | 123 | {"path": "/data/besu-profiling/runs/20261013T095310Z-c72db8ba-9f15-452d-8e29-3a5839a7052b/heap.hprof", "bytes": 27409332283, "mtime": "2026-10-13T19:03:22.903096+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T080401Z.json) |
| besu_heap_dump | teku-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T08:04:01.711783+00:00 | 123 | {"path": "/data/besu-profiling/runs/20261013T095500Z-7e634ded-1958-42a6-b8d0-82a1cf01136a/heap.hprof", "bytes": 26811699345, "mtime": "2026-10-13T16:35:45.675959+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T080401Z.json) |
| health | lighthouse-nimbusel-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T08:04:01.711783+00:00 | 123 | ["is_optimistic"] [evidence](evidence/health/20261014T080401Z.json) |
| health | nimbus-nimbusel-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T08:04:01.711783+00:00 | 123 | ["is_optimistic", "el_offline"] [evidence](evidence/health/20261014T080401Z.json) |
| log_engine_timeout | nimbus-nimbusel-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T08:04:01.711783+00:00 | 615 | {"timestamp": "2026-10-14 07:59:59.001238768", "container": "beacon", "body": "DBG 2026-10-14 07:59:58.999+00:00 Failed EL Request                          topics=\"elman\" requestName=newPayload statusCode=0 err=\"Request timed out\"", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T080401Z.json) |
| collection_gap | collector | Review candidate | 2026-10-13T21:55:59.688146+00:00 | 2026-10-13T21:55:59.688146+00:00 | 1 | {"last_health_at": "2026-10-13T21:52:45.932727+00:00", "seconds": 193.755419} collector state |
| metric_besu_heap_fraction | glamsterdam-msf-2-nimbus-besu-1 | Review candidate | 2026-10-13T21:58:23.318033+00:00 | 2026-10-14T00:04:01.724568+00:00 | 21 | {"value": 0.9425172843039036, "labels": {"area": "heap", "consensus_client": "nimbus", "execution_client": "besu", "ingress_user": "glamsterdam-msf-2", "instance": "glamsterdam-msf-2-nimbus-besu-1", "ip_address": "168.144.244.100", "job": "execution", "network": "glamsterdam-msf-2", "supernode": "True", "tenant_tier": "external", "testnet": "glamsterdam-msf-2", "vm_account_id": "1", "vm_project_id": "0"}, "interpretation": "threshold observation, not proof of a client defect"} [evidence](evidence/metrics/20261014T000401Z.json) |
| metric_besu_heap_fraction | glamsterdam-msf-2-teku-besu-1 | Review candidate | 2026-10-13T22:19:01.716249+00:00 | 2026-10-14T00:54:01.717906+00:00 | 20 | {"value": 0.9078083923086524, "labels": {"area": "heap", "consensus_client": "teku", "execution_client": "besu", "ingress_user": "glamsterdam-msf-2", "instance": "glamsterdam-msf-2-teku-besu-1", "ip_address": "167.99.59.150", "job": "execution", "network": "glamsterdam-msf-2", "supernode": "True", "tenant_tier": "external", "testnet": "glamsterdam-msf-2", "vm_account_id": "1", "vm_project_id": "0"}, "interpretation": "threshold observation, not proof of a client defect"} [evidence](evidence/metrics/20261014T005401Z.json) |
| metric_besu_heap_fraction | glamsterdam-msf-2-grandine-besu-1 | Review candidate | 2026-10-13T22:59:01.723872+00:00 | 2026-10-13T23:44:01.722242+00:00 | 7 | {"value": 0.9117392916232347, "labels": {"area": "heap", "consensus_client": "grandine", "execution_client": "besu", "ingress_user": "glamsterdam-msf-2", "instance": "glamsterdam-msf-2-grandine-besu-1", "ip_address": "165.22.7.245", "job": "execution", "network": "glamsterdam-msf-2", "supernode": "True", "tenant_tier": "external", "testnet": "glamsterdam-msf-2", "vm_account_id": "1", "vm_project_id": "0"}, "interpretation": "threshold observation, not proof of a client defect"} [evidence](evidence/metrics/20261013T234401Z.json) |
| log_engine_timeout | prysm-besu-1 | Review candidate | 2026-10-14T02:34:01.716226+00:00 | 2026-10-14T02:34:01.716226+00:00 | 1 | {"timestamp": "2026-10-14 02:31:55.036265517", "container": "execution", "body": "2026-10-14 02:31:55.036+0000 \| vert.x-eventloop-thread-1 \| WARN  \| JsonRpcExecutorHandler \| Timeout (30000 ms) occurred in JSON-RPC executor for method {\"jsonrpc\":\"2.0\",\"id\":10115,\"method\":\"engine_getPayloadBodiesByHashV2\",\"params\":[[\"0xf5e4a1434de3a03334e58ffac94c089efd2ef304921c4e6c22e72555b36ee589\"]]}", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T023401Z.json) |
| logs_collection_error | duty_loss | Review candidate | 2026-10-14T03:49:01.716728+00:00 | 2026-10-14T03:49:01.716728+00:00 | 1 | "panda exited 1: P 500: Code: 241. DB::Exception: Received from chi-clickhouse-raw-replicated-1-1:9000. DB::Exception: (total) memory limit exceeded: would use 89.50 GiB (attempt to allocate chunk of 0.00 B), current RSS: 189.07 GiB, maximum: 188.56 GiB.. (MEMORY_LIMIT_EXCEEDED) (version 26.2.5.45 (official build))\n" [evidence](evidence/logs/20261014T034901Z.json) |
| logs_collection_error | optimistic_activation | Review candidate | 2026-10-14T03:49:01.716728+00:00 | 2026-10-14T03:49:01.716728+00:00 | 1 | "panda exited 1: Error: HTTP 500: Code: 241. DB::Exception: (total) memory limit exceeded: would use 89.65 GiB (attempt to allocate chunk of 0.00 B), current RSS: 189.19 GiB, maximum: 188.56 GiB. (MEMORY_LIMIT_EXCEEDED)\n" [evidence](evidence/logs/20261014T034901Z.json) |
| log_duty_loss | prysm-besu-1 | Review candidate | 2026-10-14T06:29:01.720584+00:00 | 2026-10-14T06:39:01.715806+00:00 | 9 | {"timestamp": "2026-10-14 06:36:57.001412359", "container": "validator", "body": "\u001b[90m[2026-10-14 06:36:57.00]\u001b[0m \u001b[32m INFO\u001b[0m\u001b[36m client:\u001b[0m Skipping payload attestation: no block for slot \u001b[32merror\u001b[0m=PayloadAttestationData: rpc error: code = NotFound desc = no block found at slot=12469 \u001b[32mretried\u001b[0m=false \u001b[32mslot\u001b[0m=12469", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T063901Z.json) |
| log_duty_loss | prysm-erigon-1 | Review candidate | 2026-10-14T06:29:01.720584+00:00 | 2026-10-14T06:39:01.715806+00:00 | 10 | {"timestamp": "2026-10-14 06:36:57.001846875", "container": "validator", "body": "\u001b[90m[2026-10-14 06:36:57.00]\u001b[0m \u001b[32m INFO\u001b[0m\u001b[36m client:\u001b[0m Skipping payload attestation: no block for slot \u001b[32merror\u001b[0m=PayloadAttestationData: rpc error: code = NotFound desc = no block found at slot=12469 \u001b[32mretried\u001b[0m=false \u001b[32mslot\u001b[0m=12469", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T063901Z.json) |
| log_duty_loss | prysm-ethrex-1 | Review candidate | 2026-10-14T06:29:01.720584+00:00 | 2026-10-14T06:39:01.715806+00:00 | 10 | {"timestamp": "2026-10-14 06:36:57.002362038", "container": "validator", "body": "\u001b[90m[2026-10-14 06:36:57.00]\u001b[0m \u001b[32m INFO\u001b[0m\u001b[36m client:\u001b[0m Skipping payload attestation: no block for slot \u001b[32merror\u001b[0m=PayloadAttestationData: rpc error: code = NotFound desc = no block found at slot=12469 \u001b[32mretried\u001b[0m=false \u001b[32mslot\u001b[0m=12469", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T063901Z.json) |
| log_duty_loss | prysm-geth-1 | Review candidate | 2026-10-14T06:29:01.720584+00:00 | 2026-10-14T06:39:01.715806+00:00 | 10 | {"timestamp": "2026-10-14 06:36:57.001639478", "container": "validator", "body": "\u001b[90m[2026-10-14 06:36:57.00]\u001b[0m \u001b[32m INFO\u001b[0m\u001b[36m client:\u001b[0m Skipping payload attestation: no block for slot \u001b[32merror\u001b[0m=PayloadAttestationData: rpc error: code = NotFound desc = no block found at slot=12469 \u001b[32mretried\u001b[0m=false \u001b[32mslot\u001b[0m=12469", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T063901Z.json) |
| log_duty_loss | prysm-nethermind-1 | Review candidate | 2026-10-14T06:29:01.720584+00:00 | 2026-10-14T06:39:01.715806+00:00 | 10 | {"timestamp": "2026-10-14 06:36:57.002014461", "container": "validator", "body": "\u001b[90m[2026-10-14 06:36:57.00]\u001b[0m \u001b[32m INFO\u001b[0m\u001b[36m client:\u001b[0m Skipping payload attestation: no block for slot \u001b[32merror\u001b[0m=PayloadAttestationData: rpc error: code = NotFound desc = no block found at slot=12469 \u001b[32mretried\u001b[0m=false \u001b[32mslot\u001b[0m=12469", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T063901Z.json) |
| log_duty_loss | prysm-reth-1 | Review candidate | 2026-10-14T06:29:01.720584+00:00 | 2026-10-14T06:39:01.715806+00:00 | 10 | {"timestamp": "2026-10-14 06:36:57.002901685", "container": "validator", "body": "\u001b[90m[2026-10-14 06:36:57.00]\u001b[0m \u001b[32m INFO\u001b[0m\u001b[36m client:\u001b[0m Skipping payload attestation: no block for slot \u001b[32merror\u001b[0m=PayloadAttestationData: rpc error: code = NotFound desc = no block found at slot=12469 \u001b[32mretried\u001b[0m=false \u001b[32mslot\u001b[0m=12469", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T063901Z.json) |
| missing_canonical_proposal | nimbus-reth-1 | Known recurrence | 2026-10-14T06:34:01.720280+00:00 | 2026-10-14T06:49:01.721630+00:00 | 2 | {"slot": 12469, "epoch": 389, "validator": 21631, "host": "nimbus-reth-1", "evidence": "evidence/epochs/389.json", "interpretation": "A missing canonical slot; may include a late or orphaned attempted proposal"} [evidence](evidence/epochs/389.json) |
| log_engine_timeout | lighthouse-reth-1 | Review candidate | 2026-10-14T06:44:01.722749+00:00 | 2026-10-14T06:44:01.722749+00:00 | 2 | {"timestamp": "2026-10-14 06:38:50.019652353", "container": "beacon", "body": "Oct 14 06:38:50.019 ERROR Local execution payload build failed; falling back to an external bid  error: GetPayloadFailed(EngineError(Api { error: HttpClient(url: http://snooper-engine:8561/, kind: timeout, detail: operation timed out) })), slot: 12479", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T064401Z.json) |

## Finalized proposer duty census

Only finalized epochs fully contained in the monitoring window enter the census. A 404 for a finalized canonical slot is counted as missing. Other API failures leave the epoch pending. Missing canonical data does not establish that no block was signed; late and orphaned proposals require log follow-up. The current incomplete epoch and unfinalized tail are excluded.

| Pairing | Missing canonical slots | Assigned duties |
|---|---:|---:|
| grandine-besu-1 | 0 | 90 |
| grandine-erigon-1 | 0 | 86 |
| grandine-ethrex-1 | 0 | 100 |
| grandine-geth-1 | 0 | 72 |
| grandine-nethermind-1 | 0 | 72 |
| grandine-reth-1 | 0 | 78 |
| lighthouse-besu-1 | 0 | 75 |
| lighthouse-erigon-1 | 0 | 83 |
| lighthouse-ethrex-1 | 0 | 89 |
| lighthouse-geth-1 | 0 | 73 |
| lighthouse-nethermind-1 | 0 | 69 |
| lighthouse-reth-1 | 0 | 75 |
| lodestar-besu-1 | 0 | 83 |
| lodestar-erigon-1 | 0 | 79 |
| lodestar-ethrex-1 | 0 | 84 |
| lodestar-geth-1 | 0 | 91 |
| lodestar-nethermind-1 | 0 | 78 |
| lodestar-reth-1 | 0 | 102 |
| nimbus-besu-1 | 0 | 96 |
| nimbus-erigon-1 | 0 | 89 |
| nimbus-ethrex-1 | 0 | 87 |
| nimbus-geth-1 | 0 | 99 |
| nimbus-nethermind-1 | 0 | 87 |
| nimbus-reth-1 | 2 | 97 |
| prysm-besu-1 | 0 | 68 |
| prysm-erigon-1 | 0 | 90 |
| prysm-ethrex-1 | 0 | 75 |
| prysm-geth-1 | 0 | 75 |
| prysm-nethermind-1 | 0 | 82 |
| prysm-reth-1 | 0 | 84 |
| teku-besu-1 | 0 | 91 |
| teku-erigon-1 | 0 | 84 |
| teku-ethrex-1 | 0 | 86 |
| teku-geth-1 | 0 | 81 |
| teku-nethermind-1 | 0 | 85 |
| teku-reth-1 | 0 | 73 |

## Collection and coverage

Three independent client pairings provide minute-level reference head and finality checks. All 41 hosts are sampled every five minutes, including container image IDs, lifecycle, sync status, peers and execution height. Same-slot validated head differences are candidates for a persistent divergence check; differing finalized roots at the same epoch are recorded separately. A wall-clock head gap over three slots, finality lag over three epochs, or no finality advance for 15 minutes is recorded.

Every five minutes, bounded ClickHouse queries retain counts and up to five recent distinct examples per host and container for critical failures, Engine timeouts, lost duties and optimistic activation. Queries lag wall time by two minutes and replay five minutes for late ingestion. Saved count windows overlap and must not be summed. Log samples are selective and may omit incidents; collector failures are recorded separately. Logs arriving more than five minutes late can be missed.

Prometheus captures Besu heap fraction, GC time, payload latency, scrape health, available memory, CPU steal and gas used every five minutes. Besu checkpoint freshness, timer state, free disk and heap dump metadata are checked every five minutes. Heap dumps and raw JFR files remain private on their nodes. No client restarts or configuration changes are performed by this monitor. Watchtower deployments may cause image or container changes and require operational attribution.

The user systemd timer on the monitoring workstation survives the chat session, with login lingering enabled. It publishes sanitized captures to branch **qu0b/msf-2-overnight-20261013** hourly and on completion. It stops after the final ingestion catch-up at **2026-10-14T08:05:00+00:00**. Health snapshots in the five-minute ingestion catch-up can extend beyond the requested window. A workstation outage creates a coverage gap; this does not send unattended alerts or file upstream issues.

[Machine readable summary](summary.json) includes exact event details and every missing slot. [Configuration](config.json) records the window and source baseline. The checked-in collector is [monitor.py](../../scripts/msf2-monitor/monitor.py).
