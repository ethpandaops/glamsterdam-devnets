# pbt-1 data via panda CLI: metrics, logs, profiles

Every query below was run against pbt-1 on 2026-10-27.

## Where each kind of data lives

| Data | Store | panda command | History |
|---|---|---|---|
| Host and container metrics: CPU, RAM, disk, network, OOM kills | Prometheus, datasource `devnets` | `panda prometheus …` | since 2026-10-20 ~11:00 UTC (network start) |
| EL client metrics: Mgas/s, head, block-processing timers, DB reads/writes, PBT counters | Prometheus, datasource `devnets` | `panda prometheus …` | same |
| Container logs (EL, CL, validator, sentry) | ClickHouse, `clickhouse-raw`, table `external.otel_logs` | `panda clickhouse query …` | since 2026-10-20 10:49 UTC |
| Profiles (pprof, JFR) | **not in panda**; on the hosts, see the last section | — | — |

Metrics are in Prometheus, not ClickHouse. ClickHouse holds the logs and the Xatu chain events.

## Setup

```bash
panda init      # pulls the local server, logs in via the browser (ethpandaops GitHub access needed)
panda auth status
```

## Metrics (PromQL)

- Every series has `network="glamsterdam-pbt-1"`.
- `instance` names the host, e.g. `glamsterdam-pbt-1-lighthouse-geth-1`.
- `execution_client` is one of `geth`, `besu`, `nethermind` or `erigon`.
- Container metrics come from cAdvisor; use `name="execution"` for the EL container.

```bash
N='network="glamsterdam-pbt-1"'

# Find metric names by substring
panda prometheus label-values devnets __name__ --contains mgas --limit 50

# EL memory. Use rss (anon); working_set also counts page cache (it shows Nethermind-2 at 32 GB)
panda prometheus query devnets "container_memory_rss{$N,name=\"execution\"}/1e9"
# Peak over the last 24 h, per host
panda prometheus query devnets "max by (instance) (max_over_time(container_memory_rss{$N,name=\"execution\"}[24h]))/1e9"
# OOM kills (cAdvisor counter; it resets when the container is recreated)
panda prometheus query devnets "max by (instance) (max_over_time(container_oom_events_total{$N,name=\"execution\"}[7d]))"

# EL CPU, in cores
panda prometheus query devnets "rate(container_cpu_usage_seconds_total{$N,name=\"execution\"}[5m])"

# Root disk: used fraction, and growth in GB per hour
panda prometheus query devnets "1-node_filesystem_avail_bytes{$N,mountpoint=\"/\"}/node_filesystem_size_bytes{$N,mountpoint=\"/\"}"
# (a query must not start with "-": panda reads it as a flag)
panda prometheus query devnets "deriv(node_filesystem_avail_bytes{$N,mountpoint=\"/\"}[1h])*-3600/1e9"

# Disk IO, in bytes per second
panda prometheus query devnets "rate(node_disk_written_bytes_total{$N}[5m])"
panda prometheus query devnets "rate(node_disk_read_bytes_total{$N}[5m])"

# Time series to a file (JSON; times are RFC3339, unix, or now-1h)
panda -o json prometheus query-range devnets \
  "max by (instance) (container_memory_rss{$N,name=\"execution\",execution_client=\"geth\"})" \
  --start 2026-10-27T00:00:00Z --end now --step 1m > geth-rss.json
```

### EL throughput metric names (they differ per client)

| Client | Mgas/s | Head / block timing |
|---|---|---|
| Geth | `chain_mgasps` (summary, `quantile` label) | `chain_head_block`, `chain_execution*`, `chain_account_reads*`, `chain_storage_reads*`, `eth_db_state_pbtancient_*` |
| Nethermind | `nethermind_mgas_per_sec` | `ethereum_blockchain_height`, `nethermind_pbt_*` |
| Besu | (none; derive it from gas used and time) | `ethereum_blockchain_height`, `besu_block_processing_*`, `besu_blockchain_chain_head_gas_used`, `besu_executors_pbt_migrator_*` |
| Erigon | `exec_mgas_sec`, `chain_tip_mgas_per_sec` | `chain_execution*`, `commitment_*` |

Shared across clients: `rpc_duration_debug_shadowStateRoot_success*` and `rpc_duration_debug_migrationProgress_success*`.

## Logs (ClickHouse SQL)

- Filter by network, host and container.
- Always bound `Timestamp`; the table is large.
- Container: `ServiceName = 'execution'` (or `'beacon'`, `'validator'`).
- Host: `ResourceAttributes['host.name'] = 'lighthouse-geth-1'`.
- Client: `ResourceAttributes['ethereum_el'] = 'geth'`.

```bash
# Last EL log lines on one host
panda clickhouse query clickhouse-raw "
SELECT Timestamp, Body FROM external.otel_logs
WHERE ResourceAttributes['network'] = 'glamsterdam-pbt-1'
  AND ResourceAttributes['host.name'] = 'lighthouse-geth-1'
  AND ServiceName = 'execution'
  AND Timestamp >= now() - INTERVAL 10 MINUTE
ORDER BY Timestamp DESC LIMIT 50"

# Per-block Mgas/s from Geth's import lines (exact per block, unlike the metric summary)
panda clickhouse query clickhouse-raw "
SELECT ResourceAttributes['host.name'] host, count() blocks,
       quantile(0.5)(toFloat64OrZero(extract(Body, 'mgasps=([0-9.]+)'))) p50_mgasps,
       quantile(0.99)(toFloat64OrZero(extract(Body, 'elapsed=([0-9.]+)ms'))) p99_elapsed_ms
FROM external.otel_logs
WHERE ResourceAttributes['network'] = 'glamsterdam-pbt-1'
  AND ResourceAttributes['ethereum_el'] = 'geth' AND ServiceName = 'execution'
  AND Timestamp >= now() - INTERVAL 1 HOUR
  AND Body LIKE '%Imported new%chain segment%'
GROUP BY host ORDER BY host"

# Errors and warnings (SeverityText is often empty; match on Body)
#   ... AND match(Body, '(?i)(crit|error|fatal|panic|warn)')
```

Notes:

- `elapsed=` can be printed as `ms` or `s`; the second query only catches `ms`.
- For bigger pulls, `panda clickhouse query-raw clickhouse-raw "<sql>"` returns JSON.

## Profiling: not collected centrally

The metrics above are not profiles. Sampling profilers need no code changes or labels:

- **Go pprof** interrupts the process about 100 times a second and records the call stack. A 30 s CPU profile from a node that has been running for weeks shows which functions use the CPU.
- **Heap profiles** sample allocations by call site.
- `pprof.Do` labels are optional; they only add your own tags on top.

What exists on pbt-1 today:

| Client | Status | How to get it |
|---|---|---|
| Geth (1–3) | **pprof off** (only `--metrics` on :6060) | Ask us to add `--pprof --pprof.addr=0.0.0.0 --pprof.port=6061`; this needs an EL restart. Then `go tool pprof http://<host>:6061/debug/pprof/profile?seconds=30` (also `heap`, `allocs`, `goroutine`) through an SSH tunnel. |
| Erigon (1–2) | pprof on, bound to host `127.0.0.1:6060` | Through an SSH tunnel: `curl -o cpu.pprof 'localhost:6060/debug/pprof/profile?seconds=30'`. Erigon-1 also writes heap snapshots (`SAVE_HEAP_PROFILE`) to `/tmp/erigon-mem.prof` inside the container. |
| Besu (1–2) | continuous JFR plus GC logs | Under `/data/besu-profiling/runs/<run>/` on the host. A timer dumps a `checkpoints/*.jfr` every 5 min and keeps the last 24 (about 2 h). There is a `gc-*.log`, and `heap.hprof` on OOM. Open them with JDK Mission Control or `jfr print`. |
| Nethermind (1–2) | nothing | Needs `dotnet-trace` / `dotnet-counters` in the container; ask if wanted. |

The hosts need SSH access, so we pull the files for you: send the host, the time window and the profile type.
