# pbt-1 final-head snapshots — upload report (2026-10-30)

Final-head EL snapshots for Geth, Besu, Nethermind and Erigon at pbt-1 block **24,558,379** are public on
`shadowfork-images.ethpandaops.io` as of 2026-10-30 20:16 UTC. Each one passed sampled sha256 checks on R2
and through the CDN.

- **State:** binary trie (EIP-8347) canonical. The switch was at `binary_trie_time` 1793264400
  (2026-10-29 09:00 UTC); the head is 1.3 days later.
- **Agreement:** all nine ELs (3 Geth, 2 Besu, 2 Nethermind, 2 Erigon) had the same head hash and state
  root when the fleet was frozen at 2026-10-30 14:15:22 UTC.
- **Head:** hash `0x0fb2f11e5cafa964ca8a160868edfb08b2ded517c9380de595cc859cebfbb252`, state root
  `0x9df0d77a295cc903091bb8acaed65cb1a7e223866f101a11cd61d28819ea7097`, timestamp 1793369508, CL slot
  59159 (head root `0x12e6243c75738c029c7627faae353c61daa20fc5b8c5fc09ebc8b74c7ffec6a9`).
- **Chain:** chain id 1, gas limit 200M, `amsterdam_time` 1769856769.

The upload log (freeze, readback, CDN findings, the reboot that dropped the completion job) is in
[pbt-1-activation-incident-2026-10-29.md](pbt-1-activation-incident-2026-10-29.md#shutdown-and-final-head-snapshots-2026-10-30).
Tooling: [`scripts/pbt/final-head-snapshot.py`](../scripts/pbt/final-head-snapshot.py).

## Snapshots

Base URL: `https://shadowfork-images.ethpandaops.io/pbt-1/20261030-final-head/`. Each client folder
`<client>/24558379/` holds `snapshot.tar.zst`, `_snapshot_metadata.json` and
`_snapshot_eth_getBlockByNumber.json` (the head block with its 1,234 transactions). The shared genesis is
`_snapshot_genesis.json` in the base folder (sha256 `6f4750fb…`, identical to `genesis-pbt.json`).

| Client | Archive (bytes) | On disk (bytes) | archive sha256 | Image the source ran | Source revision |
|---|---|---|---|---|---|
| [Geth](https://shadowfork-images.ethpandaops.io/pbt-1/20261030-final-head/geth/24558379/snapshot.tar.zst) | 1,107,449,574,513 | 1,218,225,794,997 | `6583b4bfe6134f754280cffd7a3df32f168616b76f5f3e6d7f35c4cb551a5a92` | `local/geth:pbt-fb9925472` (not pushed) | CPerezz/go-ethereum `pbt` @ `fb9925472f8b68792dc9e24bad63b9ac74a4b248` |
| [Besu](https://shadowfork-images.ethpandaops.io/pbt-1/20261030-final-head/besu/24558379/snapshot.tar.zst) | 1,110,292,670,367 | 1,184,265,683,481 | `eb57c0034f9f39b6e4cf13587ffdb074ea1d0f59d9dd99391e9b1a59be9aa464` | `pbt-1/besu:cc564258-e49e3008` (local build, not pushed) | `cc5642583b802f8af31c58386d13429fd098d5e5` |
| [Nethermind](https://shadowfork-images.ethpandaops.io/pbt-1/20261030-final-head/nethermind/24558379/snapshot.tar.zst) | 1,533,536,026,987 | 1,679,863,097,220 | `a99c39f8df81909b8236c3a0ca80bd440bdb8b6c9fdec9046519f0f6698250ae` | `ethpandaops/nethermind@sha256:6a570a4038248460f066907702dcbe1cff9809e9df411d9c30173d5d33d505f0` | `afc0e1f9b8a96a6b2058d33d7013175f2277d81c` (`pbt-state`) |
| [Erigon](https://shadowfork-images.ethpandaops.io/pbt-1/20261030-final-head/erigon/24558379/snapshot.tar.zst) | 496,696,979,735 | 667,726,643,789 | `98e657ba41dda602f091ed33920a766db947bc2a5b1f33a5a923de83ae217526` | `ethpandaops/erigon@sha256:977277f3f1c559d01d262994e3f2ca019bb517541553066a6e7e04d1efc46f6a` (`pbt-1-9ac7b462`) | binary-trie `9ac7b46` |

Each archive was taken from the `-1` node of its client type after a clean stop and the offline steps
listed in its metadata (Geth and Erigon `db compact`, Besu trie-log prune keeping 512 layers). The datadir
was then reopened at the frozen head with no rewind and stopped cleanly.

## How to use

Download, extract into the client's datadir, and start with the genesis plus the client flags below.
Those flags are what the source node last ran with; the readback of every archive's datadir used them.

1. Download and extract in one pass. Plan for about 1.1× the archive size free on disk. The CDN blocks
   Python's default user agent, so use curl or set a curl user agent:

   ```bash
   B=https://shadowfork-images.ethpandaops.io/pbt-1/20261030-final-head
   C=geth   # besu | nethermind | erigon
   curl -s "$B/_snapshot_genesis.json" -o genesis-pbt.json   # sha256 6f4750fb…
   curl -s "$B/$C/24558379/_snapshot_metadata.json" -o metadata.json
   mkdir -p /data/$C && curl -sL "$B/$C/24558379/snapshot.tar.zst" | zstd -d -T0 | tar -x -C /data/$C
   ```

2. Point the client at the extracted directory:

   | Client | Extracted directory is | Required PBT flags (as run on the source) |
   |---|---|---|
   | Geth | the `geth/` instance dir; mount under `<datadir>/geth` | `--override.genesis=genesis-pbt.json --networkid=1 --syncmode=full --history.chain=all`; **no** `--pbt.import.*` flags (Geth refuses them after the switch) |
   | Besu | the `--data-path` (`database/`, `caches/`) | `--genesis-file=genesis-pbt.json --data-storage-format=BONSAI --sync-mode=FULL --version-compatibility-protection=false`, plus the `--Xpbt-*` migration flags with `--Xpbt-migration-self-convert=true` |
   | Nethermind | the `--datadir`; DBs under `mainnet/` | `--config=mainnet --Init.ChainSpecPath=genesis-pbt.json --Init.BaseDbPath=<datadir>/mainnet --FlatDb.Enabled=true --FlatDb.Layout=Flat --FlatDb.HistoryEnabled=false --Pbt.Enabled=true --Pbt.MigrationAnchor=24453558 --Pruning.Mode=None --Sync.FastSync=false --Sync.SnapSync=false` |
   | Erigon | the `--datadir` (`chaindata/`, `snapshots/`) | `--networkid=1 --experimental.commitment-v3 --override.binary-trie=1793264400 --keep.stored.chain.config=true --externalcl --db.size.limit=2TB` |

3. Add a CL. The network ran Lighthouse
   (`ethpandaops/lighthouse@sha256:2104aed4cdec152fa4ee1abb407a11e7bc65ebe0da9eb290509182be96f36529`).
   For a single-node benchmark, the EL can run alone and you feed blocks in over the Engine API. To check
   the import, call `eth_getBlockByNumber("latest")`: it should return block 24,558,379 with the state
   root above. Compare it against `_snapshot_eth_getBlockByNumber.json`.

For Besu and Nethermind, the source node still had the anchor-24453558 migration inputs mounted
(`framed.bin`, `pbt-snapshot.bin`; flags `--Xpbt-preimages-file` and `--Pbt.MigrationPreimagesPath`). It has
not been tested whether either client starts without them. Those inputs are in R2 under
`pbt-1/20261020-pbt-anchor-24453558/`, but the CDN does not serve them (403), so getting them needs R2
access. Full flag lists: `ansible/inventories/pbt-1/group_vars/<client>.yaml`.

## PBT resources

**Snapshot releases** on `shadowfork-images.ethpandaops.io/pbt-1/`, newest first:

| Release | Head | What it is | Public |
|---|---|---|---|
| `20261030-final-head/` | 24,558,379 | Binary trie canonical, all four ELs (this report) | yes |
| `20261020-pbt-anchor-24453558/` | anchor 24,453,558 | Migration inputs: `pbt-snapshot.bin` (108 GB), `framed.bin` preimages (67 GB), `release.json` | **no**: R2 only; the CDN 403s these names |
| `20261020-erigon-v3-head/erigon/` | 24,503,958 | Erigon v3 conversion of the pre-switch head | yes |
| `20261019-mixed-8037-v2/` | 24,503,958 | Pre-switch (MPT) launch snapshots for all four ELs, `replay/` bundle (49 GB) and `_snapshot_manifest.json` with workload/BAL commitments ([release record](pbt-1-snapshot-release-2026-10-20.json)) | yes |

**In this repo:**

| Path | What |
|---|---|
| [pbt-1-experiment.md](pbt-1-experiment.md), [pbt-1-launch-handoff.md](pbt-1-launch-handoff.md) | Plan, launch record, run sheet, wave log |
| [pbt-1-client-migration-commands.md](pbt-1-client-migration-commands.md) | Per-client migration commands and flags |
| [pbt-1-activation-incident-2026-10-29.md](pbt-1-activation-incident-2026-10-29.md) | Switch-day timeline, client bugs, final snapshot log |
| [pbt-1-panda-data-guide.md](pbt-1-panda-data-guide.md) | Metrics, logs and profiles through `panda` (Prometheus `devnets`, ClickHouse `external.otel_logs`) |
| [pbt-1-storage-benchmark-2026-10-20.md](pbt-1-storage-benchmark-2026-10-20.md), [pbt-1-self-conversion-trials-2026-10-26.md](pbt-1-self-conversion-trials-2026-10-26.md), [pbt-1-8037-pilot-2026-10-19.md](pbt-1-8037-pilot-2026-10-19.md) | Benchmarks and trials |
| [`scripts/pbt/`](../scripts/pbt) | Controller tooling: presigned R2 uploads (`final-head-snapshot.py`, `storage.py`), migration-input publishing, fleet monitors, Erigon conversion helpers; `migration-builds.json` pins every client build |
| [`ansible/inventories/pbt-1/`](../ansible/inventories/pbt-1) | Inventory, images (`group_vars/all/images.yaml`), per-client flags, per-host roles |
| [`network-configs/pbt-1/`](../network-configs/pbt-1), [`terraform/pbt-1/`](../terraform/pbt-1), [`kubernetes-archive/pbt-1/`](../kubernetes-archive/pbt-1) | Genesis/config, DO infrastructure, k8s tooling |

**Client sources:** [CPerezz/go-ethereum](https://github.com/CPerezz/go-ethereum) `pbt`;
[besu-eth/besu-stateless](https://github.com/besu-eth/besu-stateless) and [matkt/besu](https://github.com/matkt/besu);
[NethermindEth/nethermind](https://github.com/NethermindEth/nethermind) `pbt-state`;
[erigontech/erigon](https://github.com/erigontech/erigon) binary-trie `9ac7b46`. Planning and procedure:
[misilva73/pbt-planning](https://github.com/misilva73/pbt-planning) (migration test plan) and
[CPerezz/pbt-devnet](https://github.com/CPerezz/pbt-devnet) (Kurtosis package).

## Notes for future benchmarks and shadowforks

- **CDN naming:** `shadowfork-images.ethpandaops.io` serves only `snapshot.tar.zst` and `_snapshot_*` keys
  and returns 403 for anything else. It also blocks Python-urllib's user agent. Name every public artifact
  to fit, and test with a curl user agent.
- **Uploads:** VMs get presigned multipart `UploadPart` URLs only; account credentials stay on the
  controller. With `zstd -1` and 256 MiB parts, each node streamed at about 70 MB/s. That took 1.9 h for
  Erigon (497 GB) and 5.9 h for Nethermind (1.53 TB). zstd shrank archives to 0.74–0.94× their size on
  disk. Mind the 10,000-part limit.
- **Controller jobs:** run long jobs as unit files, not `systemd-run`. A host reboot at 14:45 dropped the
  transient completion job, and two finished uploads sat uncompleted for up to 2.5 h.
- **Geth after the switch:**
    - `--pbt.import.*` flags are fatal.
    - An unclean stop could rewind toward genesis until the `--pbt.recover` build.
    - Heap spiked past 16/32 GiB (OOM); Geth now runs with 64 GiB.
    - Stop with a long timeout, and let it settle for about 45 s after start before any stop.
- **Benchmark baseline:** Geth block execution went from about 200 ms to 1.6–1.7 s for full (about
  194 Mgas) blocks after the switch. Per-client numbers are in Prometheus; see the panda data guide.
- **Finality margin:** with 9 ELs in 4 client types, losing all 3 Geth left exactly 2/3 (6/9). The two
  Erigons then split off and finality was lost for 42 min. Spread validators so no client type holds more
  than 1/3.
- **Erigon on chain id 1** injects the mainnet DNS tree whatever `--discovery.dns` says. Only
  `--nodiscover` with `--staticpeers` keeps it off mainnet.
