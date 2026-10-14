# Glamsterdam msf 2 overnight monitoring October 13 to 14 2026

Monitoring is running for **2026-10-13T21:48:30+00:00 to 2026-10-14T08:00:00+00:00**. Last tick: **2026-10-14T06:03:01.717069+00:00**. The latest full check found **36/36 validator pairings** healthy at **2026-10-14T05:59:01.720468+00:00**. Reference finalized epoch advanced from **305** to **382**. This is sampled health, not a claim of uninterrupted operation.

The initial baseline found all 36 validator pairings healthy. Two unstaked Nimbus EL observers retained their previously documented optimistic or Engine offline state. These are tracked as known conditions. [Baseline](evidence/baseline.json). All six Besu hosts also retained afternoon OOM artifacts discovered at startup; these predate the overnight window and are detailed in [the Besu follow-up](besu-oom-followup.md). [Existing client reports](../msf-2-issue-reports-2026-10-13/README.md).

## Findings requiring review

Events are evidence for investigation. Threshold crossings and log errors are candidates; they do not establish a new client defect. Counts are sampled observations or distinct retained log excerpts, not outage counts. Recovery can occur between samples. Known conditions remain labelled separately.

| Signal | Host | Classification | First observed UTC | Last observed UTC | Observations | Latest detail |
|---|---|---|---|---|---:|---|
| besu_heap_dump | grandine-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T05:59:01.720468+00:00 | 98 | {"path": "/data/besu-profiling/runs/20261013T100640Z-94444f52-6769-4dcb-ba01-6ef765f9d254/heap.hprof", "bytes": 26973208860, "mtime": "2026-10-13T16:44:12.603203+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T055901Z.json) |
| besu_heap_dump | lighthouse-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T05:59:01.720468+00:00 | 98 | {"path": "/data/besu-profiling/runs/20261013T095939Z-7b2c4fe2-30bd-4cd2-9731-8cf6c93e0e38/heap.hprof", "bytes": 26748214310, "mtime": "2026-10-13T17:00:47.594610+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T055901Z.json) |
| besu_heap_dump | lodestar-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T05:59:01.720468+00:00 | 98 | {"path": "/data/besu-profiling/runs/20261013T095722Z-6609d3b1-3e74-4749-89d9-9c826158ed9c/heap.hprof", "bytes": 27729214978, "mtime": "2026-10-13T20:23:26.367896+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T055901Z.json) |
| besu_heap_dump | nimbus-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T05:59:01.720468+00:00 | 98 | {"path": "/data/besu-profiling/runs/20261013T094449Z-42cf0cfb-966d-41d6-806d-9342b1b27159/heap.hprof", "bytes": 26750411558, "mtime": "2026-10-13T16:29:56.446991+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T055901Z.json) |
| besu_heap_dump | prysm-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T05:59:01.720468+00:00 | 98 | {"path": "/data/besu-profiling/runs/20261013T095310Z-c72db8ba-9f15-452d-8e29-3a5839a7052b/heap.hprof", "bytes": 27409332283, "mtime": "2026-10-13T19:03:22.903096+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T055901Z.json) |
| besu_heap_dump | teku-besu-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T05:59:01.720468+00:00 | 98 | {"path": "/data/besu-profiling/runs/20261013T095500Z-7e634ded-1958-42a6-b8d0-82a1cf01136a/heap.hprof", "bytes": 26811699345, "mtime": "2026-10-13T16:35:45.675959+00:00", "privacy": "Host-local metadata only; no dump uploaded"} [evidence](evidence/profiling/20261014T055901Z.json) |
| health | lighthouse-nimbusel-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T05:59:01.720468+00:00 | 98 | ["is_optimistic", "el_syncing_or_unknown"] [evidence](evidence/health/20261014T055901Z.json) |
| health | nimbus-nimbusel-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T05:59:01.720468+00:00 | 98 | ["is_optimistic", "el_offline"] [evidence](evidence/health/20261014T055901Z.json) |
| log_engine_timeout | nimbus-nimbusel-1 | Known recurrence | 2026-10-13T21:52:45.932727+00:00 | 2026-10-14T05:59:01.720468+00:00 | 490 | {"timestamp": "2026-10-14 05:56:59.000997294", "container": "beacon", "body": "DBG 2026-10-14 05:56:58.995+00:00 Failed EL Request                          topics=\"elman\" requestName=newPayload statusCode=0 err=\"Request timed out\"", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T055901Z.json) |
| collection_gap | collector | Review candidate | 2026-10-13T21:55:59.688146+00:00 | 2026-10-13T21:55:59.688146+00:00 | 1 | {"last_health_at": "2026-10-13T21:52:45.932727+00:00", "seconds": 193.755419} collector state |
| metric_besu_heap_fraction | glamsterdam-msf-2-nimbus-besu-1 | Review candidate | 2026-10-13T21:58:23.318033+00:00 | 2026-10-14T00:04:01.724568+00:00 | 21 | {"value": 0.9425172843039036, "labels": {"area": "heap", "consensus_client": "nimbus", "execution_client": "besu", "ingress_user": "glamsterdam-msf-2", "instance": "glamsterdam-msf-2-nimbus-besu-1", "ip_address": "168.144.244.100", "job": "execution", "network": "glamsterdam-msf-2", "supernode": "True", "tenant_tier": "external", "testnet": "glamsterdam-msf-2", "vm_account_id": "1", "vm_project_id": "0"}, "interpretation": "threshold observation, not proof of a client defect"} [evidence](evidence/metrics/20261014T000401Z.json) |
| metric_besu_heap_fraction | glamsterdam-msf-2-teku-besu-1 | Review candidate | 2026-10-13T22:19:01.716249+00:00 | 2026-10-14T00:54:01.717906+00:00 | 20 | {"value": 0.9078083923086524, "labels": {"area": "heap", "consensus_client": "teku", "execution_client": "besu", "ingress_user": "glamsterdam-msf-2", "instance": "glamsterdam-msf-2-teku-besu-1", "ip_address": "167.99.59.150", "job": "execution", "network": "glamsterdam-msf-2", "supernode": "True", "tenant_tier": "external", "testnet": "glamsterdam-msf-2", "vm_account_id": "1", "vm_project_id": "0"}, "interpretation": "threshold observation, not proof of a client defect"} [evidence](evidence/metrics/20261014T005401Z.json) |
| metric_besu_heap_fraction | glamsterdam-msf-2-grandine-besu-1 | Review candidate | 2026-10-13T22:59:01.723872+00:00 | 2026-10-13T23:44:01.722242+00:00 | 7 | {"value": 0.9117392916232347, "labels": {"area": "heap", "consensus_client": "grandine", "execution_client": "besu", "ingress_user": "glamsterdam-msf-2", "instance": "glamsterdam-msf-2-grandine-besu-1", "ip_address": "165.22.7.245", "job": "execution", "network": "glamsterdam-msf-2", "supernode": "True", "tenant_tier": "external", "testnet": "glamsterdam-msf-2", "vm_account_id": "1", "vm_project_id": "0"}, "interpretation": "threshold observation, not proof of a client defect"} [evidence](evidence/metrics/20261013T234401Z.json) |
| log_engine_timeout | prysm-besu-1 | Review candidate | 2026-10-14T02:34:01.716226+00:00 | 2026-10-14T02:34:01.716226+00:00 | 1 | {"timestamp": "2026-10-14 02:31:55.036265517", "container": "execution", "body": "2026-10-14 02:31:55.036+0000 \| vert.x-eventloop-thread-1 \| WARN  \| JsonRpcExecutorHandler \| Timeout (30000 ms) occurred in JSON-RPC executor for method {\"jsonrpc\":\"2.0\",\"id\":10115,\"method\":\"engine_getPayloadBodiesByHashV2\",\"params\":[[\"0xf5e4a1434de3a03334e58ffac94c089efd2ef304921c4e6c22e72555b36ee589\"]]}", "requires": "correlate with duties and health; logs alone do not prove a new defect"} [evidence](evidence/logs/20261014T023401Z.json) |
| logs_collection_error | duty_loss | Review candidate | 2026-10-14T03:49:01.716728+00:00 | 2026-10-14T03:49:01.716728+00:00 | 1 | "panda exited 1: P 500: Code: 241. DB::Exception: Received from chi-clickhouse-raw-replicated-1-1:9000. DB::Exception: (total) memory limit exceeded: would use 89.50 GiB (attempt to allocate chunk of 0.00 B), current RSS: 189.07 GiB, maximum: 188.56 GiB.. (MEMORY_LIMIT_EXCEEDED) (version 26.2.5.45 (official build))\n" [evidence](evidence/logs/20261014T034901Z.json) |
| logs_collection_error | optimistic_activation | Review candidate | 2026-10-14T03:49:01.716728+00:00 | 2026-10-14T03:49:01.716728+00:00 | 1 | "panda exited 1: Error: HTTP 500: Code: 241. DB::Exception: (total) memory limit exceeded: would use 89.65 GiB (attempt to allocate chunk of 0.00 B), current RSS: 189.19 GiB, maximum: 188.56 GiB. (MEMORY_LIMIT_EXCEEDED)\n" [evidence](evidence/logs/20261014T034901Z.json) |

## Finalized proposer duty census

Only finalized epochs fully contained in the monitoring window enter the census. A 404 for a finalized canonical slot is counted as missing. Other API failures leave the epoch pending. Missing canonical data does not establish that no block was signed; late and orphaned proposals require log follow-up. The current incomplete epoch and unfinalized tail are excluded.

| Pairing | Missing canonical slots | Assigned duties |
|---|---:|---:|
| grandine-besu-1 | 0 | 71 |
| grandine-erigon-1 | 0 | 77 |
| grandine-ethrex-1 | 0 | 80 |
| grandine-geth-1 | 0 | 60 |
| grandine-nethermind-1 | 0 | 55 |
| grandine-reth-1 | 0 | 60 |
| lighthouse-besu-1 | 0 | 60 |
| lighthouse-erigon-1 | 0 | 70 |
| lighthouse-ethrex-1 | 0 | 70 |
| lighthouse-geth-1 | 0 | 53 |
| lighthouse-nethermind-1 | 0 | 51 |
| lighthouse-reth-1 | 0 | 65 |
| lodestar-besu-1 | 0 | 65 |
| lodestar-erigon-1 | 0 | 54 |
| lodestar-ethrex-1 | 0 | 67 |
| lodestar-geth-1 | 0 | 72 |
| lodestar-nethermind-1 | 0 | 65 |
| lodestar-reth-1 | 0 | 77 |
| nimbus-besu-1 | 0 | 74 |
| nimbus-erigon-1 | 0 | 72 |
| nimbus-ethrex-1 | 0 | 67 |
| nimbus-geth-1 | 0 | 85 |
| nimbus-nethermind-1 | 0 | 76 |
| nimbus-reth-1 | 0 | 71 |
| prysm-besu-1 | 0 | 49 |
| prysm-erigon-1 | 0 | 69 |
| prysm-ethrex-1 | 0 | 59 |
| prysm-geth-1 | 0 | 59 |
| prysm-nethermind-1 | 0 | 58 |
| prysm-reth-1 | 0 | 60 |
| teku-besu-1 | 0 | 76 |
| teku-erigon-1 | 0 | 64 |
| teku-ethrex-1 | 0 | 70 |
| teku-geth-1 | 0 | 66 |
| teku-nethermind-1 | 0 | 66 |
| teku-reth-1 | 0 | 55 |

## Collection and coverage

Three independent client pairings provide minute-level reference head and finality checks. All 41 hosts are sampled every five minutes, including container image IDs, lifecycle, sync status, peers and execution height. Same-slot validated head differences are candidates for a persistent divergence check; differing finalized roots at the same epoch are recorded separately. A wall-clock head gap over three slots, finality lag over three epochs, or no finality advance for 15 minutes is recorded.

Every five minutes, bounded ClickHouse queries retain counts and up to five recent distinct examples per host and container for critical failures, Engine timeouts, lost duties and optimistic activation. Queries lag wall time by two minutes and replay five minutes for late ingestion. Saved count windows overlap and must not be summed. Log samples are selective and may omit incidents; collector failures are recorded separately. Logs arriving more than five minutes late can be missed.

Prometheus captures Besu heap fraction, GC time, payload latency, scrape health, available memory, CPU steal and gas used every five minutes. Besu checkpoint freshness, timer state, free disk and heap dump metadata are checked every five minutes. Heap dumps and raw JFR files remain private on their nodes. No client restarts or configuration changes are performed by this monitor. Watchtower deployments may cause image or container changes and require operational attribution.

The user systemd timer on the monitoring workstation survives the chat session, with login lingering enabled. It publishes sanitized captures to branch **qu0b/msf-2-overnight-20261013** hourly and on completion. It stops after the final ingestion catch-up at **2026-10-14T08:05:00+00:00**. Health snapshots in the five-minute ingestion catch-up can extend beyond the requested window. A workstation outage creates a coverage gap; this does not send unattended alerts or file upstream issues.

[Machine readable summary](summary.json) includes exact event details and every missing slot. [Configuration](config.json) records the window and source baseline. The checked-in collector is [monitor.py](../../scripts/msf2-monitor/monitor.py).
