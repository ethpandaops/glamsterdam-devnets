# PBT-1 client migration commands

Updated 2026-10-20 from the operator's Besu release update and
[Geth planning PR #12](https://github.com/misilva73/pbt-planning/pull/12),
observed open at head `ecc562fa83da7588ca6a0a1a9963c28787ce0073`.
These are migration-worker command templates, not commands already deployed on
the native snapshot preparation hosts. Build and compatibility qualification
remain outstanding. Machine-readable pins are in
[`migration-builds.json`](../scripts/pbt/migration-builds.json).

Use `N` for the shared finalized snapshot/preimage anchor and `S` for the agreed
future PBT activation timestamp. Preserve the prepared backlog after `N`.
Use actual finality evidence from the launched network; a stored header alone
does not establish finality. All templates retain the worker's normal network,
Engine API, JWT and consensus-client configuration.

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
[`CPerezz/go-ethereum` at `4f7e4b23c066932bbd399bce94955468d6039bac`](https://github.com/CPerezz/go-ethereum/tree/4f7e4b23c066932bbd399bce94955468d6039bac)
on `pbt`. Pin that commit rather than following the branch during the experiment.

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

The follower runs automatically: after snapshot import it begins at `N+1`;
after self-migration it begins at `P+1`. Record actual BAL consumption and compare
roots at the same canonical block hash. Apply the complete process memory limit
through migration, catch-up and fork activation.
