# PBT-1 client migration commands

Use these templates with the [current experiment plan and coverage gates](pbt-1-experiment.md).
They do not establish that every client uses the same replay mechanism or anchor.

Updated 2026-10-21 from the operator's Besu release update and
[Geth planning PR #12](https://github.com/misilva73/pbt-planning/pull/12),
observed open at head `b6069c1411eb0cf5096eeab5e08976bc55ba3a78`.
These are migration-worker command templates, not commands already deployed on
the native snapshot preparation hosts. All five client builds are now pinned and
build-verified. Seven non-Erigon workers and Erigon-2 passed isolated startup checks at H
([evidence](pbt-1-worker-preparation.json)). Migration qualification remains
outstanding for every client. Machine-readable pins are in
[`migration-builds.json`](../scripts/pbt/migration-builds.json).

Use `N` for the shared finalized snapshot/preimage anchor and `S` for the agreed
future PBT activation timestamp. Preserve the prepared backlog after `N`.
Use actual finality evidence from the launched network; a stored header alone
does not establish finality. All templates retain the worker's normal network,
Engine API, JWT and consensus-client configuration.

The prepared delivery path on each host is
`/data/pbt-1/migration-input-24453558`. Use it only after that worker's
`ready.json` confirms verified downloads. For containerized migration, enable
`pbt_migration_input_mount_enabled=true` with the migration restart: the inventory
binds that worker's directory read/write at `/pbt-migration-input`. Use
`/pbt-migration-input` as `<artifact-dir>` inside the container, or the host path
for a native command. The mount is disabled by default so baseline startup
cannot create an empty directory before the verified download is promoted.
Enabling the mount alone does not set `S` or start migration; apply it alongside
the reviewed client flags and fork configuration below.
The six import workers receive both files; Geth self-migration
receives the preimages and metadata. Delivery is staged but awaits the verified
shared release; it does not start migration or establish finality.

## Besu

Required source:

- [matkt/besu](https://github.com/matkt/besu/tree/39377a2659f63c3bb230a5f57b4ef6846348f876):
  `39377a2659f63c3bb230a5f57b4ef6846348f876` (`main-pbt`).
- [besu-eth/besu-stateless](https://github.com/besu-eth/besu-stateless/tree/62b752345cce00d9119f37c37d56eb9566269578):
  `62b752345cce00d9119f37c37d56eb9566269578`
  (`feat/partitioned-binary-trie`).

The pinned Besu `gradle.properties` requests `besuStatelessVersion=0.1.8-SNAPSHOT`;
the pinned library declares that same version. Besu's repositories include
`mavenLocal()` before remote repositories. Build the library at the exact commit
and publish into an isolated Maven-local repository used by the Besu build.
Verify dependency resolution and record the actual JAR SHA-256 in the build
manifest; a matching SNAPSHOT version string alone does not prove the requested
library commit. The library declares Java 25. Record toolchains, build commands,
binary/container digest, and qualification evidence before deployment.

Set `config.binaryTrieTime` to `S` in the genesis configuration before restarting.
Without this schedule, the PBT migrator is not enabled. Supply all three artifact
options together:

```text
besu --data-path=<datadir> --genesis-file=<genesis-with-S> \
  --Xpbt-snapshot-file=<artifact-dir>/pbt-snapshot.bin \
  --Xpbt-preimages-file=<artifact-dir>/framed.bin \
  --Xpbt-snapshot-anchor-block-hash=<hash-of-N> \
  --Xpbt-migration-threads=4 \
  --Xpbt-migration-blocks-per-roll=128 \
  --Xpbt-migration-sort-buffer=64 \
  <normal node options>
```

Four migration threads are the explicit initial setting for an eight-core worker.
Keep these settings identical for the 16- and 32-GiB process-budget trials.
Leave the roll pause at its automatic default initially; changing it is a
separate tuning trial.

| Option | Default / supported bound |
|---|---|
| `--Xpbt-migration-threads` | Half the cores; 1 through the available core count |
| `--Xpbt-migration-blocks-per-roll` | 128; maximum 512 |
| `--Xpbt-migration-roll-pause` | Previous roll duration, capped at 10 seconds; explicit value in milliseconds, 0 disables the pause |
| `--Xpbt-migration-sort-buffer` | 64 MiB per sort buffer; maximum 1024 MiB |
| `--Xpbt-migration-from-genesis` | Off; incompatible with the snapshot options |

The snapshot path waits for synchronization and finality of `N`, then verifies
and loads while MPT execution continues. Do not select migration from genesis
for these restored mainnet-derived databases. Monitor `debug_migrationProgress`
and query `debug_shadowStateRoot(blockHash)` through the restricted DEBUG RPC.
Compare roots at identical block hashes.

With the node stopped, artifact verification and conversion commands are:

```text
besu <normal data/genesis options> storage pbt verify \
  --snapshot <snapshot> --preimages <preimages> --anchor <hash-or-number>

besu <normal data/genesis options> storage pbt convert \
  --preimages <preimages> --snapshot <output-snapshot> --anchor <hash-or-number>
```

Conversion can instead use `--preimages-out <output-preimages>`. Verification
exits 0 when accepted, 1 for rejection and 2 for other errors; it writes no state.
The shared artifact producer remains Erigon unless the experiment explicitly
selects a separate conversion comparison.

Scratch and staged column files live under `<data-path>/pbt-migration`.
The pinned implementation stages SST files there and links them into the
database, so storage placement must preserve the required filesystem semantics.
Do not move only this directory onto a separate volume without qualifying that
layout. Enlarging capacity may require placing the whole data path on the volume.
Measure peak allocation and cleanup, including the final binary column.

Source reference:
[pinned migration README](https://github.com/matkt/besu/blob/39377a2659f63c3bb230a5f57b4ef6846348f876/ethereum/core/src/main/java/org/hyperledger/besu/ethereum/trie/pathbased/bonsai/migration/eip8347/README.md).

## Geth

The updated procedure identifies
[`CPerezz/go-ethereum` at `84a12eff96347929ab62b65cfeb1194478445518`](https://github.com/CPerezz/go-ethereum/tree/84a12eff96347929ab62b65cfeb1194478445518)
on `pbt`. Pin that commit rather than following the branch during the experiment.
This supersedes candidate `4f7e4b23c` and includes the merged
[peak-disk hotfix #69](https://github.com/CPerezz/go-ethereum/pull/69).
This build is pinned and build-verified, and all three Geth workers passed their
isolated H startup checks. Migration qualification remains outstanding.

Both modes require `config.binaryTrieTime = S`, with `S >= amsterdamTime`.
Supply the updated genesis through `--override.genesis` on every start, or
persist it with `geth --datadir <datadir> init <genesis-with-S>` while stopped.
Keep the agreed activation time far enough ahead for migration, catch-up and
the observation window.

For `geth-import-16` and `geth-import-32`, restart once with:

```text
geth --datadir <datadir> --syncmode=full \
  --override.genesis <genesis-with-S> \
  --pbt.import.snapshot <artifact-dir>/pbt-snapshot.bin \
  --pbt.import.preimages <artifact-dir>/framed.bin \
  --pbt.import.anchor <hash-of-N> \
  --pbt.import.workers=4 \
  <normal node options>
```

For `geth-self-16`, use the same template **without**
`--pbt.import.snapshot`. It still needs the shared preimages and their anchor.
This replaces an offline-import/restart sequence: both paths run in the node
while normal MPT processing continues.

Snapshot import waits for canonical, finalized `N` and checks the artifact
against that header; local historical MPT state at `N` is unnecessary.
Self-migration instead needs a complete persisted path-scheme flat state at
`P >= N`. It augments the preimage keys with writes from BALs `N+1..P`,
can retrieve missing BALs from peers, and attests at finalized `P`.
Record `P`, its hash and the attested root separately from the input anchor `N`.
Compare with the import workers at `P` or a later common block.
The pinned implementation's
[self-converter and BAL key collection](https://github.com/CPerezz/go-ethereum/blob/84a12eff96347929ab62b65cfeb1194478445518/cmd/geth/bintrie_selfconvert.go#L44)
confirm this handling of keys created or deleted after `N`. This source review
does not prove a completed migration on the worker.
The staged Geth inventory explicitly sets `--history.chain=all`, matching this
pin's `KeepAll` default. Preserve the required BAL interval through self-conversion;
the native reader uses either the BAL freezer table or the active key-value
store and validates each list against its canonical header. The controller-only
configuration review checks this setting on all three Geth workers.

With light traffic, persistence can lag behind `N`. The upstream procedure
describes `--history.state=8` as a devnet option that reduces state-history
retention and triggers persistence after a 136-block lag. Do not silently apply
that retention change; first verify that required source state and recovery
points remain available.

Scratch is on disk at `<datadir>/geth/pbt-import`, not tmpfs. Files are released
as consumed. Use `--pbt.import.force` only for a deliberate replacement of an
existing PBT; it is unnecessary for a fresh namespace.

Monitor `debug_migrationProgress`: `Phase=importing` during import, then
`Phase=running` while the follower advances `Binary.Cursor` and
`Binary.ShadowRoot`. A failure reports `Phase=importFailed` and `Binary.Error`;
preserve diagnostics before retrying. Failed work is removed and a stopped
attempt restarts from the beginning. After success, retain the flags on later
starts so completed work is recognized.

The current online importer consumes writable artifact files by default:
it punches holes while reading and ultimately truncates them. Use independent
per-worker copies of `pbt-snapshot.bin` and `framed.bin`; never hardlink the
immutable masters. A retry after consumption needs fresh copies. Alternatively,
`--pbt.import.keep-artifacts` preserves the inputs at the cost of additional disk.
After successful import, retain the emptied paths as well as the startup flags.
This applies to the PBT artifact pair, not the compressed native database
recovery archives on `/mnt/pbt-recovery`.

The follower runs automatically: after snapshot import it begins at `N+1`;
after self-migration it begins at `P+1`. Record actual BAL consumption and compare
roots at the same canonical block hash. Apply the complete process memory limit
through migration, catch-up and fork activation.

## Nethermind

Use `NethermindEth/nethermind` at
`f4e295193e426230547c59dcdb8decb25d725418`. For each import worker, schedule the
agreed future `S` through `config.binaryTrieTime` in Geth-style genesis, or
`params.eip8347TransitionTimestamp` in a native chainspec. Supply the updated
chainspec when restarting:

```text
nethermind --config <node-config> \
  --Init.ChainSpecPath=<chainspec-with-S> \
  --Pbt.Enabled=true --FlatDb.Enabled=true --FlatDb.Layout=Flat \
  --FlatDb.HistoryEnabled=false \
  --Pbt.MigrationSnapshotPath=<artifact-dir>/pbt-snapshot.bin \
  --Pbt.MigrationPreimagesPath=<artifact-dir>/framed.bin \
  --Pbt.MigrationAnchor=24453558 --Sync.FastSync=false \
  <normal node options>
```

The [pinned mode selector](https://github.com/NethermindEth/nethermind/blob/f4e295193e426230547c59dcdb8decb25d725418/src/Nethermind/Nethermind.State.Pbt/PbtPlugin.cs)
requires both the scheduled transition and PBT opt-in. The
[configuration validator](https://github.com/NethermindEth/nethermind/blob/f4e295193e426230547c59dcdb8decb25d725418/src/Nethermind/Nethermind.State.Pbt/PbtMigrationConfigValidator.cs)
requires `S` after the execution genesis, with EIP-7928 and EIP-6780 active before
it. It rejects native FlatDB history mode and artifact paths overlapping the
writable database. Our separate `/pbt-migration-input` mount preserves that path
separation; retain the existing FlatDB database and layout.

Supply both artifacts: without preimages, the
[pinned configuration](https://github.com/NethermindEth/nethermind/blob/f4e295193e426230547c59dcdb8decb25d725418/src/Nethermind/Nethermind.State.Pbt/IPbtConfig.cs)
allows an import without tying the snapshot to the anchor's MPT root. Keep
`Pbt.ImportConcurrency` at its default of one for the initial pair of trials;
record any later tuning. The running node handles import and subsequent BAL
following, as described in [Maria's consumer procedure](https://github.com/misilva73/pbt-planning/blob/95ac0b56c5ad69ca99d3e3e8e77729d541d7a739/outreach/pbt-mainnet-fork-migration-test-plan.md#commands).
Actual progress/root capture and migration success remain live qualification
gates. A restart or a populated PBT directory is not sufficient evidence.

## Erigon

Use `erigontech/erigon` at `372df0e68f52f9975370bff38dee6e41aefff0d7` for
both the client and integration tool. The completed legacy-to-v3 upgrade is
separate from this PBT migration.

After the live baseline, stop one worker at a time and run:

```text
integration commitment convert-pbt \
  --datadir=<stopped-worker-datadir> --chain=<chain> \
  --output.datadir=<new-converted-dir> --keep-hex \
  --experimental.bin-commitment.hash=blake3
```

Record the output's block and transaction checkpoint. The pinned documentation
calls the transaction number `S`; in our runbook call it `conversion_tx_num`
to distinguish it from the activation timestamp. It may be mid-block. Review
the exact alignment remedy from the tool before any reset, unwind or file
removal; do not substitute H or N. Then, while stopped:

```text
integration commitment attach-pbt \
  --datadir=<worker-datadir> --chain=<chain> --from=<new-converted-dir> \
  --experimental.bin-commitment.hash=blake3
```

Keep the output settings and matching state salt. After successful attach,
restart with the agreed `--override.binary-trie=<S>` on every start and the
normal v3/node options. The
[pinned conversion/attach procedure](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/docs/pbt-migration.md)
defines alignment and restart recovery; do not use its test-only import path.
[Maria's procedure](https://github.com/misilva73/pbt-planning/blob/95ac0b56c5ad69ca99d3e3e8e77729d541d7a739/outreach/pbt-mainnet-fork-migration-test-plan.md#commands)
requires `debug_migrationProgress` to show `mode: "hex+bin"` and
`shadowStopped: false` before activation. Catch-up is native re-execution after
attach, not an asserted N-to-H BAL-import result.

Maria also specifies standalone verification of the shared snapshot on receiving
Erigon nodes. The current seven-recipient delivery job does not cover Erigon-2.
The user has explicitly deferred this extra shared-pair check so preparation
can proceed; record it as a coverage exception, not a passed check or remaining
launch gate. Erigon-2's successful native H startup is a separate result. See the
[launch handoff](pbt-1-launch-handoff.md) for current sequencing. No extra
verification job or PBT conversion is started by this command sheet.
