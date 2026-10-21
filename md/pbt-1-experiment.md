# PBT-1 experiment: execution plan and coverage

Updated 2026-10-21. This is the current experiment plan. The older process,
dependency graph, instruction audit and source-upgrade notes retain historical
evidence; they do not independently define the next operation.

## Preparation checkpoint, October 21 at 15:15 UTC

All nine recovery volumes are mounted. Erigon-2 now has the verified corrected
v3 recovery archive, with matching worker/controller configuration and automatic
restore disabled. Its original provenance remains preserved; the redundant local archive cache
was reclaimed after volume verification and configuration reconciliation. The other eight original recovery archives remain retained.
Eight workers have passed isolated startup checks at H, including Erigon-2;
Erigon-1 remains pending. The read-only fleet monitor reports no alerts.

| Work | Current evidence | Next gate |
| --- | --- | --- |
| Erigon-1 older exporter | Native export exited 0 at 07:18 UTC; metadata matches N's hash and MPT root | Independent native verifier running |
| Erigon-2 H database | Conversion, both original-binary verifications and H reconstruction passed; two worker opens passed at 09:38 UTC under 16 GiB / 8 CPU and stopped cleanly | Corrected archive published; recovery-volume replacement and configuration reconciliation complete |
| Shared N artifacts | Snapshot is 107,902,638,451 bytes; preimages are 66,850,271,320 bytes; exporter internal validation passed | Independent verifier completed the storage merge and is processing accounts; publication follows full verification |
| Erigon-1 H database | Original H database preserved; verified H release inputs staged, with a 1,192,103,432,995-byte unpacked bound | Finish exporter work, preserve its artifacts, review space, then restore the verified H release and run this worker's own checks |
| Patched H recovery archive | 461,165,199,193 bytes published; full remote SHA-256 passed at 12:11 UTC | Erigon-2 stored-cache and stored-volume SHA-256 passed; controller and worker recovery inputs agree; scoped URL range check passed |
| Genesis configuration | Local test candidate validated; G and S unset | User supplies G, then regenerate and revalidate launch artifacts |

Erigon-2's one-shot recovery replacement completed its full stored-volume checksum
at 15:02 UTC. The worker and controller now identify the same corrected release,
with `restore: false`; the new scoped URL passed a worker range-read check.
Original qualification files remain unchanged. The reviewed eight-file unsqueeze
rollback directory was then removed, reclaiming **148.43 GB**. See
`files/erigon-2-v3-recovery-ready.json` and `files/erigon-2-unsqueeze-cleanup.json`
under the PBT inventory. The redundant local archive cache was subsequently
removed after exact identity, backup-proof and no-owner checks, reclaiming
another **461.17 GB**. Erigon-2 now has about **897.91 GB free locally**. See
`files/erigon-2-cache-cleanup.json`; the recovery-volume archive remains intact.
The replacement procedure is
[`replace-erigon-2-recovery-volume.py`](../scripts/pbt/replace-erigon-2-recovery-volume.py).

At 14:42 UTC, four closed scratch files from the completed bytecode-verification
stage were removed after checking the remaining source code path, exact file
identities, scratch-volume UUID, and absence of open descriptors or mappings.
This reclaimed **259.90 GB**. Native verifier PID 64456 was not restarted and
continued its storage merge; snapshot/preimage artifacts and all active MPT
inputs were preserved. See
`files/erigon-completed-code-scratch-cleanup.json` under the PBT inventory.
This cleanup does not mean the whole artifact verification has passed.

The conversion's frozen checkpoint is not the common launch head H. Native
execution restored the retained tail before Erigon-2's H qualification.
The completed tail run used the same pinned integration binary with a 4-GiB
batch after a recorded graceful stop; see
`files/erigon-tail-performance-20261021.json`. Offline preparation used 112 GiB
and eight CPUs; the subsequent Erigon-2 worker checks used 16 GiB.

Historical memory adjustment:
At 22:12 UTC, Erigon-2's preparation unit was given 112 GiB instead of 96 GiB
on the same VM, with the same native PID and eight-CPU allocation. A ten-second
sample had shown 2.4 million file-cache refault pages and roughly 60% I/O
pressure. A later sample showed fewer refaults and lower pressure, but the
converter also moved from collection into file building, so this is not an
isolated speedup measurement. No OOM events were observed. The separate worker
qualification still uses its assigned 16 GiB limit. Runtime change evidence is
`files/erigon-head-cache-adjustment.json` under the PBT inventory.
The dated machine-readable observation is
[`preparation-checkpoint.json`](../ansible/inventories/pbt-1/files/preparation-checkpoint.json).
The detailed chronology below explains earlier failures and recovery decisions.

The H execution stage returned at 08:20 UTC, but the native command remained in
database close. The pinned aggregator waits for background file building before
closing; profiling showed MDBX cursor reads and domain collation. The last
completed aggregation step took 72 minutes, and the background job's recorded
range still contained hundreds of steps. At 08:57 UTC, the exact native PID
received one SIGINT to cancel this background work through its normal root
context. The wrapper was left running; no forced kill, database deletion or
completion proof was substituted. The native process exited 0 at 08:57:54 UTC;
the same wrapper then started the original commitment verifier at 08:58 UTC.
Subsequent verification exited 0 at 09:37 UTC, and both H startup checks passed
at 09:38 UTC. See `files/erigon-2-v3-head-qualified.json` alongside
`files/erigon-post-head-shutdown.json` and `files/erigon-tail-execution-complete.json`.

The older exporter converter reported 774.83 million v3 records and zero orphans.
Both original `commitment verify` passes fold frozen files at block 24,451,719;
they do not independently fold the mutable tail. `stage_exec` restored O=24,452,538
with pruning disabled, and two native opens confirmed its expected header.
A `Type=simple` namespace race in the audit wrapper was corrected to `Type=exec`;
the repeated checks recorded matching private network namespaces and clean stops.
The initial anchor preflight also mistook the metrics agent’s read-only root mount
for a database user; it was corrected before any client launch. N replay is now
complete through N-1. The intentional exit also rolled back N's header/body,
so the offline stage could not advance. A native Engine commit followed by
one-block native unwind and offline re-execution passed, followed by both exact-N
opens; see the
23:24 UTC correction in the instruction audit. Neither result qualifies either
H worker. The native command result is retained in
`files/erigon-boundary-recovery.json` under `conversion_result`.

## Morning handoff

Before choosing G, require all nine workers' H startup checks, the Erigon
conversion evidence, recoverable snapshots and an explicit status for the shared
N artifacts. The current checkpoint above is dated; use the fleet monitor and
completed proof files to establish readiness. Shared N verification/publication
and Erigon-1 restore are still pending.
The corrected H release is fully verified and published; local recovery-volume
replacement remains pending.
Restore Erigon-1's original ext4 reservation and remove its temporary export
scratch volume before launch. Preserve the verified exporter recovery on Geth-2
until safely redundant; then reclaim it so it does not constrain that worker.
Complete the stopped-worker preparation-cache handoff described under the
worker matrix after the last database/input scan. Record its evidence before
calling the workers ready for the memory-limited experiment.

Once the user supplies G, put `pbt_genesis_timestamp` and a **new** private
`pbt_genesis_workspace` in a private JSON variables file. Set `PBT_LAUNCH_VARS`
to that file and `PBT_CANDIDATE_DIR` to the same workspace. From `ansible/`, the
local preparation sequence is:

```sh
export ANSIBLE_STRATEGY=linear
export ANSIBLE_CACHE_PLUGIN_CONNECTION=tmp/pbt-1
ansible-playbook -i inventories/pbt-1/inventory.ini pbt-prepare-genesis.yaml -e @"$PBT_LAUNCH_VARS"
/usr/bin/python3 ../scripts/pbt/validate-genesis.py "$PBT_CANDIDATE_DIR"
ansible-playbook -i inventories/pbt-1/inventory.ini pbt-prepare-validator-keys.yaml -e @"$PBT_LAUNCH_VARS"
/usr/bin/python3 ../scripts/pbt/check-genesis-with-lighthouse.py "$PBT_CANDIDATE_DIR"
/usr/bin/python3 ../scripts/pbt/validate-genesis.py "$PBT_CANDIDATE_DIR"
ansible-playbook -i inventories/pbt-1/inventory.ini pbt-review-configuration.yaml -e @"$PBT_LAUNCH_VARS"
```

The Lighthouse check uses a fresh, isolated database, checks the Gloas state,
H anchor and all 2,304 public keys through its API, and stops the container. Its
`lighthouse-validation.json` records `evidence_directory` and the checksums of
the nine public files in that directory's `network-config/`. Promote that
checked subset to `network-configs/pbt-1/metadata/` and compare every checksum
before deployment. The generator's original metadata directory also contains
`mnemonics.yaml`; keep it private. Validator signing files stay in the selected
candidate's `validator-keys/<host>/` directories. The inventory now selects
these private paths explicitly, and its controller-only review checks the ranges.

After launch authorization, use the selected variables file throughout and
skip `ethereum_genesis` in the deployment playbook. Start the Geth-1 seed's
EL/beacon with validators disabled, collect its fresh CL identity in the PBT
fact cache, start the other eight EL/beacon pairs, then refresh all CL peers.
Check Engine/JWT access, peer connectivity, HTTPS/metrics and
`scripts/shadowfork-pregenesis-check.sh pbt-1` before enabling the nine assigned
validator sets. Keep S unset until the separate migration scheduling step.
No network deployment or validator-key distribution has occurred.

The repeatable Lighthouse check passed on the existing validation candidate,
and the updated private key-path review passed on all nine workers. This
rehearses the local handoff without choosing a launch time. Evidence:
`files/genesis-handoff-review.json` under the PBT inventory.

## Objective and present state

Launch the live shadowfork from H, then exercise migration, catch-up, dual-tree
operation and PBT activation on all nine workers under their assigned process
limits. The earlier mandatory checkpoint/restore benchmark was an unnecessary
addition and is withdrawn. Replay here is part of migration on the running fork. Report the actual client path and
block range. An exporter finishing, a native snapshot downloading, or ordinary
MPT execution passing does not establish migration coverage.

Completed: workload preparation and publication of four native MPT snapshots at
the same head. Pending: full-state PBT migration, per-worker replay evidence,
cross-client PBT root agreement, dual-tree observation and fork activation.
Downloads and conversion progress are operational status, recorded separately.

The existing Erigon source conversion is preparation only. Automatic publication
of that older source has been stopped. Its output must not be released as the
updated worker snapshot.

## Timeline around shadowfork genesis

**No genesis time is selected.** The user explicitly requested leaving it unset.
Timestamped local validation artifacts are not launch artifacts and must be
regenerated and revalidated once the launch time is chosen.

There are two separate events: **G**, the new consensus genesis time, and **S**,
the later PBT activation time. Execution history is retained: CL genesis is
anchored to H, not execution block zero. Preserve the inherited EL genesis
identity and historical fork schedule. New execution payloads extend H.

### Launch gates versus migration gates

Launch requires nine usable MPT databases at the same H, compatible client
builds, the reviewed CL genesis, working Engine/peer connections and validators.
Successful PBT import, catch-up and PBT root agreement are later experiment
results, not prerequisites for the first shadowfork block. Shared artifact
verification and delivery gate migration, not ordinary MPT block production.
In this deployment there is still a practical dependency: Erigon-1 hosts the
exporter, so finish and preserve that work before reclaiming its space and
preparing this worker's H database. Do not mistake this storage dependency for
a protocol requirement to complete PBT migration before CL genesis.

After genesis, check actual finality and each client's acceptance of N as a
canonical finalized ancestor. N precedes the new CL genesis; stored headers and
offline artifact verification do not prove those live migration checks pass.
The CL extends H rather than replaying the historical N-to-H backlog. Migration
followers process that backlog separately while MPT execution follows new blocks.

The live transaction sender remains to be configured and qualified. CL genesis
alone does not recreate the prepared workload or fill blocks. Before measured
migration, establish mixed execution/state transactions and measure the requested
50% utilization under EIP-8037 and the resulting BAL sizes.

Use the same Spamoor funding path as MSF-2. Every genesis validator has 0x01
withdrawal credentials to mnemonic account 0,
`0x454b0EA7d8aD3C56D0CF2e44Ed97b2Feab4D7AF2`. Each starts with 10,000 ETH and
a 32 ETH effective balance, providing 22,966,272 ETH of initial excess across
2,304 validators. After the CL drives the ELs, observe actual canonical
withdrawals and the recipient's balance before funding tooling. This initial
funding does not depend on accumulating new validator rewards. Fee-recipient
payments are separate from these withdrawal credentials.

Spamoor's configured root wallet is mnemonic account 9,
`0x455f42d91096c4Aa708D7Cbcb2DC499dE89C402c`; the existing platform secret
reference matches MSF-2. After launch, run
`scripts/fund-shadowfork.sh pbt-1 --only-spamoor --dry-run`, inspect the shortfall,
then run the same command without `--dry-run` to top it up. The default target is
2,000,000 ETH, adjustable with `FUND_EACH_ETH`; only the missing amount is sent,
and account 0 retains its gas reserve. The script checks the reviewed H hash
and first post-H block timestamp before sending. It uses Geth-1 as the inventory
seed and requires the promoted launch CL configuration when G is templated.
It currently refuses to proceed because no launch genesis has been promoted.
Keep workloads stopped until the transfer receipt and Spamoor balance are
confirmed. The Spamoor endpoint list now contains only the nine PBT workers.
Evidence: `files/tooling-funding-review.json`. No funding transaction was sent.

`scripts/pbt/spamoor-calibration.yaml` prepares four stopped, finite scenarios:
ETH transfers, ERC20 transfers, Uniswap V2 swaps and fresh storage writes.
Their initial rates are 20, 20, 2 and 1 transactions per slot, with counts of
1,200, 1,200, 120 and 60 respectively and a 20-minute timeout. These are initial
calibration rates, not the final 50% workload. Submit through Geth-1 and observe
canonical inclusion and agreement across all nine workers. Do not use the CLI
`spamoor run` as a validation command: it runs entries even when the daemon's
import configuration says `start: false`.

The file passed Spamoor's native configuration resolver, field checks and
typed parsing against source `dabf895fa1891a93a654ae7201515045ca989167` without
initializing wallets or contacting an RPC. Before import, record the deployed
Spamoor image digest/version and confirm it supports these options and the
Amsterdam storage gas-estimation fix. Import stopped; inspect the four entries;
start only after the launch and funding checks above. No scenarios have been
imported or started.

Exclude contract deployment, wallet funding and pending-transaction drain from
the steady-state window. Tune swap/transfer rates for execution pressure and
fresh-storage traffic for state pressure, measuring both dimensions and BAL
bytes on the same canonical block hashes. Keep the requested target of about
100 million execution gas and 100 million state gas per 200-million-gas block;
the historical pilot's +/-5 million tolerance and 300 KiB BAL floor are useful
acceptance thresholds. Header `gasUsed` alone cannot establish both dimensions:
the pinned Geth [gas pool implementation](https://github.com/CPerezz/go-ethereum/blob/84a12eff96347929ab62b65cfeb1194478445518/core/gaspool.go)
uses the larger cumulative dimension. Do not reuse the historical generator's
fixed-state-cost receipt subtraction for arbitrary swaps/refunds. The live
dimension measurement and sustained target qualification remain pending;
record actual results before starting the measured migration phase.

Erigon's actual PBT conversion point is the file commitment block and transaction
number, which can precede its stopped head or fall within a block. Record it and
follow the pinned attach alignment instructions; do not assume it equals H or
N. Stagger offline conversion/restart operations to preserve finality.

| Phase | Action | Gate |
| --- | --- | --- |
| Before G: databases | Restore all workers at H, qualify builds and Erigon v3 format, preserve recovery archives and retained BALs | All nine open at the same H hash and MPT root |
| Before G: artifacts | Reconstruct N on the separate exporter; prepare and verify the PBT/preimage pair | Exact N hash/root and artifact digests recorded; offline work is provisional |
| Before G: network | Generate fresh CL genesis anchored to H; choose future G; reconcile validator assignments, builders, peers, JWTs, monitoring and historical fork schedule | Genesis header matches H; enough assigned validators can propose and finalize; clients are ready |
| At G | Start the live fork using MPT as canonical state | New execution blocks extend H; the CL progresses |
| After G: baseline | Produce workload, check agreement and actual finality; verify clients accept N as the canonical finalized ancestor | Healthy live network and qualified anchor checks before migration |
| After G: migration | Start six imports, Geth self-migration and the two Erigon conversion/attach paths; coordinate offline phases to preserve finality | Every worker has measured migration progress, its actual anchor and resource limits |
| After G: replay | Keep producing blocks; each PBT state catches its moving target through the client's supported path | Each worker shows real catch-up and matching PBT roots at common block hashes |
| Before S | Continue dual-tree operation, restart checks and the required observation window | All workers ready; otherwise coordinate postponement before S |
| At and after S | PBT becomes canonical; verify continued blocks, finality and agreement, then archive databases | Cross-client post-fork success and verified PBT backups |

Schedule the same sufficiently distant S before enabling online migration where
required. For Erigon, set it after attach and before rejoining. Do not activate
PBT at G or treat a configured future S as evidence that migration has completed.

For an importer, the initial PBT gap is N to the current live head, so it includes
the prepared 50,400 blocks plus blocks produced since G. Self-converters start
at their measured P_i instead. Erigon conversion requires a stopped source;
the remaining shadowfork keeps advancing while that worker is offline, and its
supported attach/restart sequence must demonstrate catch-up.

### Launch configuration findings, October 20

The preparation worktree now anchors CL genesis at H=24,503,958, selects the
`pbt-1/20261019-mixed-8037-v2` recovery release, and assigns 256 validators to
each of the nine workers (2,304 total, without gaps or overlap). Terraform has
applied the range tags; the follow-up plan reports no infrastructure changes.
`lighthouse-geth-1` is the seed node, so no separate bootnode VM is needed.

The inherited execution genesis is preserved byte-for-byte. Amsterdam remains
at 1769856769, Gloas is at CL epoch zero, and PBT activation remains unset.
`ethereum_genesis_timestamp` requires an explicit `pbt_genesis_timestamp`;
there is no default or selected launch time.

An archived local test candidate passed structural checks and validator
public-key/range checks. The pinned Lighthouse build loaded its SSZ in an
isolated container and returned the expected Gloas state, H hash and 2,304
validators through its API. That container is stopped. This establishes
format compatibility, not live Engine API, block production or finality.
The legacy Lighthouse execution-genesis log skips Gloas states; direct checks
of the decoded Gloas execution anchor are required.

The candidate and its keys remain private under
`~/.local/state/pbt-1-run/genesis/candidate-20261020-a/`. Its historical test
timestamp is not a launch decision. Regenerate and revalidate launch artifacts
once the user chooses G; do not publish this candidate.

For that future deployment, use the PBT preparation playbook and validator-key
mapping checks, then promote only the validated candidate's metadata into
`network-configs/pbt-1/metadata/`. The standard deployment invocation must skip
`ethereum_genesis` (`--skip-tags ethereum_genesis`): its generic generator path
does not perform the PBT preparation playbook's byte-for-byte preservation of
the inherited execution genesis. Recheck the promoted files against the validated
artifact hashes before deploying. No promotion has occurred.

The Kubernetes tooling inventory was regenerated on October 21 against the
nine PBT workers. The metadata upstream is Geth-1; Dora, Checkpointz, Dugtrio,
eRPC, Forkmon, Assertoor, Slashoor and Spamoor now reference this fleet.
Forky retains the generator's one-source-per-client selection. All 15 existing
charts passed local Helm rendering; this is not a live endpoint check or a
deployment. The empty `bootnode` inventory group is required by the tooling
templates and contains no extra worker.

The copied MSF-2 timestamps have been removed. Until G is chosen, Forky's
`genesis_time` is null and Spamoor's activation argument is absent. Regenerate
both from the validated launch CL configuration before deploying tooling.
Keep the existing Dora deployment-block overrides at 24,452,538 and the agent
faucet's `NODE_OPTIONS` IPv4 fallback when regenerating; the generic templates
currently omit these overrides. Evidence: `files/tooling-configuration-review.json`.

The shared pre-genesis checker now checks the PBT datadir path, MPT root and
inherited execution genesis; it has not yet been run against a deployed fleet.
Before G, rejecting `binaryTrieTime` is consistent with this staged plan;
after G, a separate migration gate must verify the coordinated future S.
The pinned local block file avoids the checker's legacy metadata URL fallback.
All nine workers now have distinct EL node identities under
`/data/pbt-1/node-identity`, outside restored databases. A repeated preparation
preserved the keys. The public peer manifest supplies eight other fleet peers
per worker, without reliance on cached Ansible facts. The inherited msf-2
static peers have been removed. Client mounts and key options select these
new identities; runtime confirmation of each client's advertised identity
remains a startup gate.
No genesis deployment has been performed.

### Preparation evidence and remaining gates

The public `ansible/inventories/pbt-1/files/configuration-review.json` records
all nine worker image pins, datadir paths, process limits, validator ranges,
and EL peers. Its genesis time is null. The controller-only configuration
review passed for all nine workers.

- Geth `84a12eff` and Nethermind `f4e29519` reopened the original workers'
  databases at H with 8 CPUs and a 16 GiB process limit, no swap and no
  networking. N matched, code reads succeeded, and BAL bodies at N+1, the
  midpoint and H matched the prepared payloads. Both stopped cleanly.
  These are sampled startup checks, not a full migration or deployment test.
- The exact Besu `39377a26` / stateless `62b75234` pair is built and loaded on
  both Besu workers. The library tests passed. Both loaded copies have matching
  filesystem layers, source labels, version output and stateless JAR SHA-256.
  Host variables pin each engine's local image ID. The worker-group image pull
  policy overrides the shared default, including the umbrella deployment role.
  Both Besu workers have now passed startup checks after the ordinary BONSAI v3-to-v4
  code-storage rewrite; the original recovery archive remains intact.
  The deployment profiling wrapper was separately checked on both pinned images
  with an 8 GiB heap and their 16/32 GiB process limits. Isolated `--version`
  runs produced nonempty JFR recordings and GC logs using temporary storage
  and no database mounts. This checks JVM/profiling compatibility; live P2P,
  Engine API and metrics endpoints remain deployment gates. Evidence:
  `ansible/inventories/pbt-1/files/besu-profiling-review.json`.
- The Erigon migration image is pinned and its native preparation binaries
  passed small fixtures. The older exporter conversion stopped at the 150 GB
  disk-reserve threshold at 17:34 UTC. It retained a completed 167 GiB
  unsqueezed data file with incomplete indexes. The corrected isolated
  index-recovery job finished successfully at 17:57 UTC. Its 4.10 GB index
  passed the read-only identity/settings/checksum checks; the data file was
  unchanged. Conversion resumed at 17:59 UTC with `--squeeze=false --continue`.
  The converter confirmed one complete shard reused and 218 remaining files.
  The resumed preparation has an 8-CPU/96-GiB cap on the existing VM; this is
  outside measured migration. Full v3 verification and native opens remain.
  Unsqueezing completed at 18:08 UTC and v3 conversion started
  (18:27 UTC: file 1 of 219, 49.5% of keys).
  At 19:02 UTC the largest v3 file completed, including indexes: 645.09 million
  legacy records, 70.9% of the conversion's input keys, in 51m30s. The remaining
  218 files and final verification were still pending. Free space recovered to
  about 514 GB after temporary files were released.
  At 19:26:39 the native converter failed on shard 6: commitment range
  `1049600-1049728` ends inside accounts range `1049600-1049856`.
  Five completed shards (82.3% of input keys) remain preserved. The queued
  reopen guard failed closed. Read-only recovery review found twenty retained
  accounts files and twenty storage files covering the conflicting range,
  with index files present. Full-record equality passed for 262,756 accounts
  and 335,569,656 storage entries. A native v3 resume fixture passed. At
  19:48:22 UTC the existing unit resumed with the two larger files and their
  indexes preserved outside the scanned domain directory. Native `--continue`
  confirmed five completed shards reused and 214 remaining files. Full
  conversion/root verification and native reopen remain pending. Evidence:
  `ansible/inventories/pbt-1/files/erigon-boundary-recovery.json`.
  At 19:56:07 the previously failing shard completed with indexes (82.93 million
  records in 7m19s). The converter has progressed past the original failure;
  complete root verification remains outstanding.
  At 20:06 all 219 converted files had been accepted and promoted by the native
  converter. At 20:24 its process was still running final verification. The
  subsequent independent verification, execution restoration and two native
  opens remain required; file promotion alone is not conversion completion.
  The current H worker database and verified recovery archive remain intact.
  Erigon-2 independently started converting its H database at 17:00 UTC on
  October 20. Its verified H recovery archive is the rollback copy; it does
  not duplicate the 517 GiB mutable database locally. Preparation uses 8 CPUs.
  Its memory cap was raised from 32 to 96 GiB on the existing VM after observing
  memory-reclaim stalls and more than 100 GiB available. This offline format
  preparation is outside the measured migration experiment. At 18:19 UTC it
  was still unsqueezing (file 1 of 4,091, 60.7% of keys). At 18:25 UTC both
  conversions were at their 96 GiB cgroup limit with repeated `memory.max`
  events and no OOM kills.
  Erigon-2 confirmed its largest unsqueezed shard complete at 19:11:42 UTC,
  including its index: 645.09 million keys, 61.2% of this stage's input keys,
  after 2h4m. Remaining unsqueeze shards, the v3 pass and verification were
  still pending; this is not 61.2% completion of the whole preparation job.
  Erigon-2 finished unsqueezing around 19:28:50, then started native v3 conversion
  at 19:28:54. It was confirmed live at 19:41, clearing execution tables.
  A filename audit predicts a later boundary conflict at `1050624-1051648`;
  no conversion failure has yet been observed on this worker.
  A read-only full-record comparison completed at 19:49:48: all 66 accounts
  and 3,489,808 storage entries match the retained 1,024 fragments per domain.
  No files were moved on Erigon-2. See
  `ansible/inventories/pbt-1/files/erigon-head-boundary-review.json`.
  That describes the initial read-only review. At 20:38 the original first-shard
  pass was deliberately interrupted for the tested bounded-view optimization;
  at 20:39 it restarted with the candidate binary. The six oversized files were
  preserved outside the scanned directory, selecting the already verified
  fragments before the predicted conflict. No completed v3 shard existed;
  the unfinished first shard restarts. Both original-verifier passes and
  restoration remain mandatory. The 16-GiB qualification waiter was requeued
  with explicit candidate-provenance checks. See
  `ansible/inventories/pbt-1/files/erigon-bounded-view-review.json` and the dated
  source operation record. This does not change the pinned worker image.
  The queued worker startup/reopen check uses its intended 16 GiB
  limit. Erigon-1's H database still requires separate preparation. Its 32 GiB
  startup job is now defined, but not started. Qualification requires conversion
  evidence naming that same host, the H datadir, block/hash/root, pinned build
  and recovery archive; the older exporter and Erigon-2 evidence are rejected.
  The job, source genesis and validation script are staged on Erigon-1.
  Its H conversion entry point is also staged as
  `/data/pbt-1/upgrade-erigon-worker-head-v3.py --worker=lighthouse-erigon-1`.
  It uses the existing checksum-verified native binaries and the preserved
  producer's H/hash/root, full 51,420-BAL audit and stopped-container evidence.
  Eleven focused identity/provenance tests passed. The read-only preflight
  correctly refused the still-active exporter without changing conversion status.
  A new H conversion requires the exporter to be stopped and more than 1 TB
  free locally: Erigon-2's first unsqueeze temporarily used about 735 GB above
  baseline. This gate has not passed on Erigon-1; its H conversion has not started.
  The exporter resumed at 19:48 following the reviewed boundary recovery and
  remains active. Erigon-1 had 439 GiB free at 20:23, so both the active exporter
  and the disk condition still prevent starting its separate H conversion.
  A 20:41 allocation audit counted the exporter upgrade/recovery directory and
  separate restore together at 823.6 GB, with hardlinks counted once. The
  filesystem had 469.2 GB free. After N export, native artifact verification
  and safe preservation of the artifact pair and provenance, retiring the
  exporter data could yield about 1.293 TB free before subtracting retained
  artifacts and subsequent growth. This is a capacity plan, not permission
  to remove active recovery data: nothing has been reclaimed. Preserve the H
  database, its compressed recovery archive, and the payload corpus. Require
  an actual `df` result above 1 TB before its H conversion. Evidence:
  `ansible/inventories/pbt-1/files/erigon-1-space-plan.json`.
  A separate read-only check of the preserved H database found the same later
  domain boundary conflict as Erigon-2. Full comparison passed for 66 accounts
  and 3,489,808 storage records against its own retained fragments; file
  identities stayed unchanged. Its staged `--bounded-view` driver can preserve
  the merged files and use the tested conversion optimization only after
  Erigon-2 completes original-binary verification, H restoration and two worker
  opens. Erigon-1 must still pass its own verification and 32-GiB opens.
  Eight handoff/provenance tests passed. Both live readiness checks refused
  their unmet gates without changing the H database. No H conversion is queued
  here. Evidence: `ansible/inventories/pbt-1/files/erigon-1-head-conversion-plan.json`.
  At 22:03 UTC a faster preparation option was staged: restore the fully
  published and checksum-verified H release into a fresh directory, then
  preserve the original H database under `erigon-original-h-preserved` before
  promoting the restored copy. Prefer this route if the measured archive,
  unpacked database and 150 GB reserve fit after exporter work is safely
  finished. The native conversion driver remains a fallback. The local cache
  is on the VM's local disk; the original recovery-volume archive stays intact.
  This avoids repeating v3 format preparation, not the worker's actual PBT
  migration after launch. It still requires Erigon-1's own 32 GiB / 8 CPU
  startup, state/BAL samples and clean reopen checks. The report explicitly
  attributes source conversion to the released snapshot. Thirty targeted
  checks passed; the live read-only preflight refused the missing published
  release. No restore or qualification job has been queued for this route.
  Neither H worker is qualified yet, and no patched H archive is uploaded.
- The H publication streamer is staged on Erigon-2. The separate controller
  `scripts/pbt/publish-erigon-v3-head.py` checks the exact H qualification proof,
  issues scoped multipart authorization, then requires a full remote SHA-256
  readback before publishing metadata. Twelve archive/proof/part-list tests
  passed. Its live read-only check refused because conversion and qualification
  are incomplete; no multipart upload was authorized. See
  `ansible/inventories/pbt-1/files/erigon-v3-publication-plan.json`.
  Keep original recovery archives until the patched archive is verified and its
  compressed size is known; the existing 550-GiB volumes may need adjustment.
  The controller's `auto` mode is now queued as the controller user service
  `pbt-1-v3-head-publication`. It waits for stopped, successful H conversion
  and qualification, runs the same full publication preflight, authorizes one
  immutable upload, starts the bounded remote streamer once, and requires a
  complete remote archive SHA-256 readback before release. Seventeen combined
  archive/publication tests passed, including missing-proof, failed-upload and
  observation-timeout cases. The live observer sees both preparation units
  running; no multipart authorization or upload has been created. Account
  credentials remain in the controller's private environment. Monitoring now
  includes this controller and flags failure or premature exit.
- All nine recovery archives are downloaded, checksum-verified and restored;
  Geth-2 finished extracting at 18:23 UTC.
- All three Geth workers and both Nethermind and Besu workers passed the expanded
  worker checks using their service users, 8 CPUs, assigned 16/32 GiB process
  limits and no network access. H/N,
  actual node identity, state-code samples and three BAL bodies matched.
  Both builder-request contracts are present, and all seven workers stopped
  cleanly. Geth-3's first attempt failed at shutdown; the retry waits for
  Geth's signal-handler goroutine before stopping and exited successfully.
  Geth-2 (32 GiB) passed at 18:24 UTC. Only the two Erigon workers remain.
- All nine qualification job definitions now match the deployment inventory's
  client/image, assigned memory, peer identity and H block/hash/root. The
  controller-only review passed with genesis time still unset.
- The exporter reopen handoff checks now require a successfully stopped
  converter and matching phase evidence. Six focused tests passed; a read-only
  invocation on the live VM correctly refused to start a client and preserved
  conversion status. The guarded script is staged for use after conversion.
  `pbt-1-v3-source-qualification.service` was queued on Erigon-1. It waits
  for the converter to stop (up to 24 hours), checks the guarded script's
  checksum, then requires successful phase evidence before two native opens.
  The native client runs in its own private network with 8 CPUs and 32 GiB.
  The waiting service was confirmed live when queued. It later refused the
  failed conversion at 19:26:39; no native reopen has begun. The identical
  SHA-pinned guard was requeued at 19:54:18 behind the resumed conversion.
  Successful stopped conversion and all phase proofs remain mandatory.
  Publication remains unqueued. At 20:53 UTC, the offline anchor handoff was
  queued in `pbt-1-erigon-anchor-preparation`. It waits for all three exporter
  predecessor units to stop successfully, rechecks exact O reopen evidence,
  the reviewed driver SHA-256, verified replay prefix, recovery archive and
  free space, then archives the existing instruction-review hold and runs the
  N preparation once. Its live readiness check refused the still-active
  predecessor and preserved the hold. Three handoff tests passed. The queued
  service is capped at 8 CPUs/32 GiB with private networking; the higher cap
  than its former waiter-only service also covers the future offline stage.
  No anchor replay has begun at this checkpoint. Fleet monitoring now includes
  the handoff and native-client services and alerts on their failure.
- Prepare CL peer discovery when a launch candidate is authorized. The CL
  starts with fresh databases. Check the actual EL/JWT connections, advertised
  identities, connected fleet peers, proposal path and finality at the relevant
  startup/after-genesis stage. None is established by the isolated SSZ test.
- Shared N migration artifacts remain gated on exporter preparation and exact
  anchor verification. Their acceptance as a finalized pre-genesis ancestor
  must be tested after the fork is running.
  The held capture driver now uses Maria's `STOP_AFTER_BLOCK=N` boundary,
  checks the intentional exit, persists N offline with `stage_exec`, and
  requires two matching N opens before export. The earlier held driver replayed
  through N normally; it never ran. See the dated instruction audit.
  `export-erigon-anchor.py` is staged on Erigon-1. Its default readiness check
  is read-only and currently refuses the missing completed N preparation proof.
  Eight guard tests passed. Explicit `--run`, after the predecessor checks pass,
  invokes the unchanged pinned native `snapshots export-pbt` and `verify-pbt`
  commands, checks N/hash/root/BLAKE3 metadata, checks file identities and
  records full-file SHA-256 checksums. It retains the conversion and anchor
  locks throughout, requires 450 GB free initially and stops its native child
  below a 150 GB reserve. There is no automatic export start or upload.
  Evidence: `ansible/inventories/pbt-1/files/erigon-export-plan.json`.
  The shared-artifact publisher is also staged. It requires the completed
  native export/verification proof and unchanged files before authorizing
  multipart uploads. The worker streams directly to scoped storage URLs;
  the controller verifies every remote file's SHA-256 before publishing a
  release manifest. Nine publication guard tests passed. Its live readiness
  check refused the missing export proof, and no upload was authorized.
  Preserve this verified artifact release before reclaiming exporter working
  data. This is separate from publishing the H worker recovery archive.
  Evidence: `ansible/inventories/pbt-1/files/pbt-artifact-publication-plan.json`.

Build provenance and startup evidence are in
[`migration-builds.json`](../scripts/pbt/migration-builds.json) and
[`pbt-1-worker-preparation.json`](pbt-1-worker-preparation.json). The latter is a
dated observation, not a live status endpoint. The 15-minute fleet monitor
checks recovery and qualification services and now measures extraction input
progress. It also checks both Erigon conversion services independently.
All full-state migration qualification flags remain false.

The pinned Erigon `stage_exec` command invokes execution pruning after batches.
For preparation only, its tail reconstruction must run with `NO_PRUNE=true`
to preserve the BAL corpus. The H conversion driver uses an atomic launcher
for its future `stage_exec` child; the original native binary is preserved as
`integration.pinned` with the same SHA-256. The resumed exporter driver uses
that pinned binary directly and sets the environment itself. Phase evidence
records the setting; later retention checks must still verify the data itself.
The pinned [`ResetExec` implementation](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/execution/stagedsync/rawdbreset/reset_stages.go)
clears state-domain tables, execution indexes and stage progress; its cleanup
list does not include `BlockAccessList`. This supports the retention design
but is not a new full-range runtime audit. The patched H release must distinguish
the original 51,420-body audit from its three sampled post-conversion checks.

The Erigon launch configuration also sets `--exec.no-prune=true`, matching the
isolated worker checks. In this pinned build the Execution stage prunes
`BlockAccessList` using its finality cutoff independently of history-file
retention. Keeping snapshots alone would not preserve the prepared BAL corpus.
This flag disables all database pruning, not just BAL pruning; report that
setting with the experiment and monitor disk growth. Changing it requires a
retention review after migration catch-up. See the pinned
[pruning implementation](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/execution/stagedsync/stage_execute.go)
and [flag definition](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/cmd/utils/flags.go).

The shared playbook's inventory-web step now includes worker hosts but still
runs the role only on `primary_bootnode`, so Geth-1 can serve metadata without
a tenth VM. CL discovery still needs its own prepared peers after an actual
launch candidate is authorized; the new EL peer manifest does not cover CL.
The launch procedure needs two discovery passes with the PBT-specific Ansible
fact cache. First start only the Geth-1 seed's EL/beacon with
`ethereum_node_cl_validator_enabled=false`, collect its fresh
`/eth/v1/node/identity` ENR, and verify its genesis root. Start the other
beacons with that seed ENR and validators still disabled, collect their
identities, then render the peer lists again using the nine fresh records.
Check actual peer connections and Engine/JWT access before enabling validators.
The vendored discovery role caches these ENRs only after the beacon is running;
an all-at-once first deployment with an empty cache would not supply bootstrap
peers. None of these launch steps has been executed.

The seed's authoritative DNS and delegation are deployed and checked over
UDP and TCP. Its origin wildcard certificate is issued and loaded into all
nine worker proxies; their nginx configuration checks passed. The existing
Cloudflare certificate pack is reused. Serving
worker HTTPS endpoints remains a deployment gate. Fresh node metrics from all
nine workers were verified centrally; EL/CL metrics remain unqualified.
All nine VMs now run Docker 29.9.1 with the shared routed IPv6 bridge and active
route services. The four older Docker 26 installations were upgraded; their
images and stopped-client states were preserved, and the native Erigon source
driver kept its PID. The PBT-only Docker preparation removes Debian's conflicting
buildx package before the Docker CE role runs.
The dated evidence is in `files/infrastructure-review.json`,
`files/runtime-review.json`, `files/proxy-review.json` and
`files/monitoring-review.json` under the PBT-1 inventory.

## Names with one meaning

| Name | Block / value | Meaning |
| --- | --- | --- |
| O | 24,452,538 | Original Jochemnet state; separate exporter working copy only |
| N | 24,453,558 | Proposed shared PBT export anchor, reconstructed using 1,020 preparation blocks |
| H | 24,503,958 | Published native MPT snapshot head for all nine workers |
| Historical test range | N+1 through H | 50,400 prepared blocks; seven days of chain time at 12 seconds |
| P_i | Measured per worker | Actual persisted state/conversion point used by a self-converting worker |
| S | Not scheduled yet | Future PBT activation timestamp, distinct from every block number above |

Every block reference in evidence includes its hash. Erigon also requires the
actual commitment transaction number: its conversion point can fall inside a
block and behind the RPC head. Record that point; do not label it H by assumption.
See the pinned [Erigon procedure](https://github.com/erigontech/erigon/blob/372df0e68f52f9975370bff38dee6e41aefff0d7/docs/pbt-migration.md).

There are three different artifacts:

1. **Worker recovery archive:** a compressed native MPT database at H, kept on
   the recovery volume and restored to local SSD.
2. **Exporter working database:** the separate older Erigon copy used to
   reconstruct N. It is not a replacement worker database.
3. **Shared migration input:** `pbt-snapshot.bin` and `framed.bin` at N, plus
   metadata and checksums. These seed PBT migration, not the worker's MPT chain.

Legacy-to-v3 Erigon commitment conversion remains MPT format preparation.
`convert-pbt --keep-hex` is the separate PBT migration operation.

## Worker matrix

All execution processes get 8 CPUs, the complete process memory limit below,
and no swap. The larger host capacity is not the experiment memory allowance.
Exporter preparation must finish or stop before measuring Erigon-1, to avoid
CPU, memory and disk contention with the measured worker.

Memory accounting also needs a preparation-to-experiment handoff. At 06:41 UTC,
the exporter had 42.3 GiB RSS while its cgroup reported about 32 GiB charged
against a 32-GiB limit, with zero OOM kills. These are different measurements:
Linux retains a memory charge with the cgroup that instantiated the pages, so
file-cache pages created by earlier preparation can be used from another group.
See [kernel memory ownership](https://docs.kernel.org/admin-guide/cgroup-v2.html#memory-ownership)
and `files/memory-accounting-review.json`. This observation does not prove a
broken limit or qualify a migration memory result.

After the last restore, checksum readback and input download on each worker,
and with all preparation jobs and execution clients stopped, record the cache
baseline, run `sync`, then write `1` to `/proc/sys/vm/drop_caches` before the
first measured client startup. Record completion and the resulting baseline.
This clears clean preparation page cache so the limited client can populate
its own cache; see [kernel cache-drop semantics](https://docs.kernel.org/admin-guide/sysctl/vm.html#drop-caches).
Do not do this while the current exporter/replay is running or during measured
migration. Any later out-of-cgroup scan of database/input contents requires
repeating that stopped-worker handoff. This step is pending on all nine workers.
Record `memory.current`, `memory.peak`, `memory.stat`, `memory.events` and process
RSS/PSS during the experiment. Existing startup checks remain startup evidence,
not a completed memory benchmark.

| Worker | GiB | Migration path | Initial coverage to demonstrate |
| --- | ---: | --- | --- |
| lighthouse-geth-1 | 16 | Shared PBT import at N | Import and follower catch-up N+1 through H |
| lighthouse-geth-2 | 32 | Shared PBT import at N | Import and follower catch-up N+1 through H |
| lighthouse-nethermind-1 | 16 | Shared PBT import at N | Import and follower catch-up N+1 through H |
| lighthouse-nethermind-2 | 32 | Shared PBT import at N | Import and follower catch-up N+1 through H |
| lighthouse-besu-1 | 16 | Shared PBT import at N | Import and catch-up N+1 through H; distinguish trie-log and BAL use |
| lighthouse-besu-2 | 32 | Shared PBT import at N | Import and catch-up N+1 through H; distinguish trie-log and BAL use |
| lighthouse-erigon-1 | 32 | Local PBT conversion and attach | Record actual P_i and native re-execution after attach |
| lighthouse-erigon-2 | 16 | Local PBT conversion and attach | Record actual P_i and native re-execution after attach |
| lighthouse-geth-3 | 16 | Geth self-migration | Record actual persisted P_i, conversion and follower replay after P_i |

All nine additionally participate in the common workload, restart, root
comparison and activation checks below. A result on the 32 GiB worker cannot
substitute for its 16 GiB counterpart.

These paths follow [Maria's plan](https://github.com/misilva73/pbt-planning/blob/95ac0b56c5ad69ca99d3e3e8e77729d541d7a739/outreach/pbt-mainnet-fork-migration-test-plan.md)
and [Carlos's Geth revision](https://github.com/CPerezz/pbt-planning/blob/b6069c1411eb0cf5096eeab5e08976bc55ba3a78/outreach/pbt-mainnet-fork-migration-test-plan.md).
Geth self-migration can use BALs between N and P_i to discover keys; that is
distinct from its follower replay after P_i. Erigon's documented path performs
re-execution; do not report that as a BAL-only follower benchmark.

## Execution order and gates

### 1. Finish preparation

- Finish and checksum the H recovery archives; validate each restored database's
  head hash and MPT root with its intended client build.
- Qualify the latest-head Erigon v3 upgrade separately from the older exporter
  conversion. Keep the H archive recoverable throughout. A qualified local
  conversion can avoid redownloading a converted H archive.
- Build and pin all migration clients and dependencies. Resolve the Nethermind
  pin explicitly. Verify flags and phase/root observability before full-state use.
- Prepare CL, validator and bootnode configuration anchored to H. Actual finality
  and client acceptance of N must be checked after the network launches.
- Audit usable disk and retention for each client. Protect N, all required
  bodies/BALs and recovery copies. Do not introduce history expiry mid-measurement.

### 2. Produce the shared migration input

Use the separate Erigon exporter to reconstruct and pin N, export the matching
artifact pair, and verify it. Before G this is provisional preparation; after
launch, associate its hash/root with the finalized chain before measured imports.
Stop exporter work before measuring the Erigon worker on the same VM.
Use independent writable artifact copies where an importer consumes its inputs.
Do not distribute the older native database as the nine-worker starting image.

### 3. Launch the shadowfork and start migration

Start the nine MPT workers from H with their qualified configurations. Record
memory/CPU limits before migration starts. First establish normal block production,
finality and acceptance of N as a canonical finalized ancestor. Do not bypass
an importer's anchor checks if this pre-genesis ancestor is unsupported.
Schedule a sufficiently distant S,
respecting Erigon's requirement to attach before setting its activation override.

The six shared-import workers construct PBT state at N and catch up to H while
their existing MPT state is at H or later. Observe their migration cursors, not
only `eth_blockNumber`. Verify the required historical data is locally available
and usable by each pinned implementation before claiming this gate is ready.

The two Erigon workers and Geth self-migration worker convert their own state;
record the actual P_i and subsequent replay range. Do not claim they replayed
N+1 through H merely because the six import workers did.

Continue normal network load during online migration where supported. Record
any offline phase, downtime, and whether replay used BALs, trie logs or execution.
At a shared finalized block, compare all available PBT roots. Missing historical
root access requires a qualified capture method, not substitution of an MPT root.

### 4. Measure migration replay on the running shadowfork

The CL and validators produce and finalize new shadowfork blocks. Until S, MPT
remains canonical. Each migrating client builds PBT state and brings it toward
the moving head using its supported migration path. Blocks already processed
for MPT can still require processing for the new PBT state.

For example, a shared importer can have MPT at H+100 while PBT is initially at N.
Its PBT follower traverses N+1 onward, including the retained historical backlog
and newly produced fork blocks. Completion means catching the current head,
not merely reaching the original launch head H.

For every worker, record:

- Its real seed/conversion block and transaction point where applicable.
- MPT head, PBT progress and their lag over time, with canonical hashes.
- Its actual replay mechanism and processed ranges, successful convergence,
  matching cross-client PBT roots, and sustained progress under live load.
- Migration resource peaks and normal block/finality performance.

Use the requested mixed execution/state workload on the live fork and measure
actual EIP-8037 utilization and BAL size. Do not substitute artificial Engine
replay for a functioning CL/validator network in the main rehearsal.

The six shared imports have the prepared N+1 through H backlog available.
Erigon and Geth self-migration have different seed points; they do not inherit
that exact replay range merely by being members of this network. Measure the
backlog created by their conversion/attachment and ongoing fork production.
Qualify each client's supported sequence before promising a minimum range.
If any worker has no measurable catch-up, leave its catch-up gate pending and
qualify how to create a backlog on that path while the rest of the fork keeps
running. Ordinary dual-tree progress alone does not prove catch-up.

Besu may use trie logs; claim BAL replay only with evidence of that path.
Erigon uses native re-execution after attach. Report those distinctions rather
than claiming identical BAL-only processing across all clients.

There is no requirement to rewind all nine workers, generate a second fixed
50,400-block dataset, or run a separate offline benchmark. Such a benchmark would
be a distinct future experiment with its own scope, time and storage budget.

### 5. Observe, activate, verify and archive

Complete the agreed dual-tree observation window under load. Maria's plan calls
for at least two weeks; 50,400 accelerated blocks do not satisfy it. Record wall
time and chain time separately.

Before S, require every worker's migration, catch-up, root, resource and restart
checks to pass. If not ready, use the qualified coordinated postponement
procedure before S. After activation, require continuing finality and matching
canonical PBT roots, then retain new native PBT database backups for all clients.

## Evidence required for coverage

Keep one row per worker in `pbt-1-coverage.json`. Initial values are pending,
not inferred from preparation success. Each claimed pass links to retained
evidence containing:

- Exact binary/dependency hashes, genesis and fork schedule, resource limits,
  migration mode, artifact checksums and actual anchor/conversion point.
- Before/after migration cursors and block hashes, input availability, errors,
  replay mechanism, processed range/count and timing. Input files existing is
  not evidence that a follower consumed them.
- PBT roots paired with the same canonical block hash across workers. Capture
  checkpoints at initialization, at least every 1,024 live blocks, at
  catch-up/restart boundaries, and around activation. These are sampled
  root comparisons; retain per-block roots if the clients support them.
- Process memory peak, OOM counters, CPU, disk peak/free space and I/O;
  normal head/finality lag while migration or catch-up runs.
- Clean restart with retained progress and matching roots; post-fork finality
  and backup integrity records.

Any missing range, unobserved mechanism or absent root
leaves the corresponding coverage gate pending. Do not mark the entire experiment
complete from a healthy dashboard, matching MPT heads or an exporter success.

## Immediate next work

1. Keep the old-source upload controller stopped; retain its useful exporter
   preparation and all existing H recovery copies.
2. Finish build/format qualification and implement per-client evidence collection.
3. Qualify the backlog controls, root capture and historical-anchor requirements
   on small fixtures. Resolve Besu BAL-path coverage and the supported live
   catch-up sequence for the self-converting workers before migration.
4. Complete network/finality setup and exporter artifacts, then execute the gates
   above. Do not start an improvised nine-node migration from legacy templates.

Command templates remain in [client migration commands](pbt-1-client-migration-commands.md).
The [older process](pbt-1-migration-process.md) records snapshot-generation results;
the [instruction audit](pbt-1-instruction-audit-2026-10-20.md) records procedure
differences. Changing this document does not launch, stop or delete worker data.

### Fresh H restore without a second compressed copy

The staged restore helper also supports `--stream`. After the H release has
passed remote SHA-256 readback, it can extract into a fresh directory while
hashing ETag-bound ordered ranges. Promotion requires the full compressed
archive checksum, successful extraction and unchanged source identity. The
original H directory is preserved in full and the original recovery-volume
archive stays intact. Capacity must cover the measured unpacked upper bound
plus 150 GB reserve. This option is staged only; no H download has started.
Eighteen restore/controller/range tests passed, including real tar extraction
and refusal to promote corrupt, truncated or identity-changed input.

The recovery-tree copy from Erigon-1 to spare local storage on Geth-2 completed
and passed a full file-checksum comparison at 00:25 UTC. It preserves 428 GB of
older exporter recovery data and its hard links. The two redundant checkpoint
directories on Erigon-1 were then removed, reclaiming 115.97 GB of exclusive
files. Shared inodes, the live N exporter, original H database and original H
archive remain intact. Both temporary transfer keys were removed. Geth's own
database and recovery archive are untouched. Evidence:
`files/erigon-exporter-checkpoint-offload.json` under the PBT inventory.

At 23:55 UTC, Erigon-1’s ext4 root reservation was temporarily reduced from
25,171,402 blocks to 6,291,125 blocks (4,096 bytes each). This exposed another
77.33 GB of existing capacity to the preparation free-space check; the native
export wrapper’s separate 150 GB reserve remains unchanged. No client or
conversion was restarted. Restore the original reservation with
`tune2fs -r 25171402 /dev/vda1` after preparation space is reclaimed and before
launch, then record `restored: true` in the reserve evidence. No other worker’s
filesystem reservation was changed.

At 00:37 UTC a temporary 550 GiB volume was attached to Erigon-1 because the
native exporter retains its sort files while writing the snapshot. An atomic
directory exchange routes future temporary files to this volume. The existing
1,370 files (345.44 GB at routing) remain at `temp-before-volume-routing` and
their open descriptors remain valid. The native process was briefly suspended
for the exchange and continued with the same PID and binary; it was not restarted.
A filesystem smoke test checked old-descriptor mmap access and new-file routing.
The guard watches the new filesystem's 50 GB reserve and reclaims retained sort
files only after all descriptors close. The original root guard retains its
150 GB reserve. Active database files and worker storage configuration are
unchanged. This volume is preparation-only and must be detached and deleted
after export scratch is no longer needed, before launch. Evidence:
`files/erigon-export-scratch-routing.json`; Terraform: `export-scratch.tf`.

The native exporter's completed ETL files contain 4,664,061,353 input records
before duplicate removal: 768,546,234 account records, 2,130,999,178 code records
and 1,764,515,941 storage records. This is a workload measurement from the sorted
record boundaries, not a full content audit or a count of unique snapshot leaves.
Shared code can be deduplicated during loading, and phase throughput varies;
the account scan finishing does not mean the snapshot is almost complete.
The read-only counter passed 80 generated boundary fixtures and checked all
1,705 file identities remained unchanged. Evidence: `files/erigon-export-record-count.json`.

The following independent native `verify-pbt` stage now has its existing
`--tmpdir` path routed to `verify-temp` on the same temporary volume. The pinned
native source creates a child scratch directory there and removes that child
after verification. The disk guard now covers both native phases, validates
the child's parent, command, cgroup and binary before signalling it, and retains
the 50 GB scratch and 150 GB local-root reserves. Four guard tests passed.
Only the guard was restarted; the native exporter was not restarted.
Evidence: `files/erigon-verify-scratch-routing.json`. Remove both temporary path
links, once no native owner remains, before detaching the volume.
