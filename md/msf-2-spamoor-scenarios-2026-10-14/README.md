# Spamoor scenarios and newPayload performance on glamsterdam msf 2

The charts align Spamoor scenario IDs with execution-client `newPayload` RPC latency from **12 October 2026 13:03:00 through 14 October 2026 16:43:48 UTC**. They cover the six execution clients across the standard 36 validator nodes. The timeline includes 549,465 deduplicated RPC observations, 69 recorded submission intervals and 607 canonical block samples.

- [Public interactive chart](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/cf2f18/msf-2-spamoor-newpayload.html)
- [Public PNG](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/0834ba/msf-2-spamoor-newpayload.png)
- Local exports: [interactive HTML](msf-2-spamoor-newpayload.html), [PNG](msf-2-spamoor-newpayload.png), [SVG](msf-2-spamoor-newpayload.svg).

Select a scenario number, click **Fit selected scenario**, and choose clients and p50, p95 or maximum latency. Hover over the line chart for versions, call counts, gas use, recorded submitting scenarios and the nearest mined block sample. The separate comparison table computes exact quantiles on the **same attributed canonical block hashes** for each client. Time buttons zoom the timelines; the comparison table uses the full run. VALID, SYNCING and ACCEPTED responses remain separate.

## Scenario attribution

Spamoor's scheduler audit records provide the start/pause timeline, including deleted IDs #104 and #105. Groups #10 and #30 contain several child workloads. A start/pause record controls submission; it does not establish which scenario was executing in a particular block. Queued transactions may continue to land after a pause, and recorded intervals may span daemon restarts or unsuccessful starts.

The mined-workload chart samples one canonical block every 25 block numbers, approximately every five minutes. Sender addresses are matched against public Spamoor wallet metadata. Explicit target addresses from scenario configuration and deployment logs provide additional matches. Conflicting mappings stay unknown. This identifies **64.6% of 381,785 sampled transactions**; the remaining share is grey. Historical wallet changes and deleted scenarios prevent complete attribution. Scenario wallet identity can also label funding traffic; the chart measures transaction counts, not gas shares or isolated attack execution.

No universal on-chain scenario-number field was established in the inspected scenarios or transaction samples. Numeric IDs are present in Spamoor's scheduler and wallet metadata. The report therefore distinguishes recorded submission intervals from verified public address matches; it does not infer transaction identity from a scheduled interval, calldata, fee or value pattern.

The comparison includes blocks where at least 90% of transaction count maps to one scenario. Small samples are marked; missing scenarios have no qualifying comparison rather than an inferred result. Scenarios #108 and #109 each have only one qualifying block and should not support a client ranking. Configuration updates are timeline ticks, and #111 retains an “existing slots” display name across configuration changes.

## Timing interpretation

The line chart uses exact p50/p95/max `duration_ms` aggregates in five-minute bins from Xatu's raw `execution_engine_new_payload` table, source `ENGINE_SOURCE_SNOOPER`. Queries cover disjoint 12-hour intervals and a fixed block/time cutoff. Duplicate records are removed using block hash, request time, node, implementation, version, status, duration and gas used. Repeated real RPC requests remain, including potentially cached VALID responses.

The comparison table computes new exact quantiles from the underlying calls matched to sampled canonical block hashes. It does **not** average bucket percentiles or combine clients on different sampled blocks. Calls and blocks can still differ across clients when telemetry or response statuses differ; each cell shows its observed counts.

RPC latency measures client RPC behavior rather than standalone EVM execution. In particular, a SYNCING response can precede completed execution. VALID results also depend on caching, prior validation, workload mix, state and version. Geth observations include both 1.17.7 and 1.17.8; versions are visible in chart hovers and evidence. These are observational comparisons from a running network.

## Evidence and reproduction

[chart-data.json](chart-data.json) contains the complete sanitized chart data; [newpayload-5min.csv](newpayload-5min.csv) and [scenario-runs.csv](scenario-runs.csv) allow independent plotting. The [evidence directory](evidence/) contains source SQL and raw aggregated results, sanitized Spamoor metadata, public wallet/target mappings and canonical sample block hashes with representative transaction hashes.

Spamoor was snapshot `ac9e1a3`, image digest `sha256:6de803385d3d344b65da5d8916b71c08170f42b27bf2c1621f642939c5b7c02c`. Audit records were read from the daemon's persisted history; public wallet metadata was retrieved through the authenticated UI. Canonical samples were read through `eth_getBlockByNumber` on nimbus-nethermind-1 with two workers. No payload-building requests, client restarts or configuration changes were required.

The public evidence excludes authentication tokens, private keys, wallet seeds, user identities, full database copies and raw pod logs. `spamoor-dashboard-long.json` is only a contemporary 30-minute API snapshot despite its endpoint parameter; it is not the historical scenario timeline source.

Run from this directory with Python 3 and Matplotlib:

```sh
python3 collect_timings.py
python3 collect_mined_samples.py
python3 collect_comparison.py
python3 build_chart.py
```

The collectors require existing Panda ClickHouse access and SSH access to the reference node. `collect_mined_samples.py` uses the captured public sender/configuration mappings and, if present, private local deployment logs to extract only public target addresses. `build_chart.py` runs entirely offline. Collection uses a fixed historical cutoff and preserves existing timing files; remove a timing file explicitly to refresh its query.

Desktop/mobile rendering, all six client paths, scenario selection, time zoom, response selection, p50 selection and public HTTP retrieval were checked. The page has no external scripts or authenticated requests. Public Panda uploads expire after 60 days; the committed HTML and image remain reproducible repository artifacts.
