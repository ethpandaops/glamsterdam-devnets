# PBT-1: preparation, genesis and operation handoff

Status observed **2026-10-21 17:47 UTC**. This is the current operational
handoff; older dated notes describe history. Live job status takes precedence
over this checkpoint. Preparation is authorized. **Genesis time G and PBT
activation time S remain unset; launching the network is not yet authorized.**

## Where we are

- Nine workers and their recovery volumes are provisioned. Eight workers have
  passed isolated startup at the common head H; Erigon-1 is the remaining worker.
- Erigon legacy commitments → v3 is complete. This is MPT database preparation;
  **Erigon `convert-pbt` / `attach-pbt` is still a separate operation.**
- The shared PBT snapshot (107,902,638,451 bytes) and preimages
  (66,850,271,320 bytes) at N were published at 17:34 UTC. The
  [release receipt](../ansible/inventories/pbt-1/files/pbt-anchor-24453558-release.json)
  records checksums, object identities and the verification deferrals.
- Geth-3 has completed its preimages/metadata download and stopped-worker cache
  handoff. The other six recipient downloads are running. Erigon-1 reclaimed its obsolete
  exporter data and started the corrected H restore at 17:35 UTC. Its own
  isolated startup check is queued afterward. Do not start duplicate jobs.
- Erigon-2 has the corrected H database and recovery archive. The temporary
  1,500-GiB exporter scratch volume and Geth-2's redundant exporter copy are
  removed. Erigon-1's temporary ext4 reservation adjustment still needs reversal.
- Infrastructure DNS, proxy certificates and node metrics were checked. Running
  EL/CL endpoints, their metrics and the actual network still need launch checks.
  Platform PR #1573 was rolled out; #471 was closed. Reuse the existing certificate pack.

**Verification policy:** proceed from the successful native N export. Its
independent MPT reconstruction was stopped at the user's request and did not pass.
The optional standalone shared-pair check on Erigon-2 is also deferred. Publication
retains source SHA-256 and multipart transfer checks; recipients hash while
downloading. Extra full object and recipient disk readbacks are deferred. Record
these exceptions honestly; investigate actual import/startup failures rather than
adding more prelaunch verification. The corrected H archive's already completed
full verification is a separate result and remains valid.

## Anchors and experiment layout

| Name | Block | Purpose |
| --- | ---: | --- |
| O | 24,452,538 | Older exporter recovery point; not the network launch head |
| N | 24,453,558 | Shared PBT snapshot and preimages anchor |
| H | 24,503,958 | Common native MPT database head for all nine launch workers |
| G | Unset | CL genesis time; the shadowfork builds on H |
| S | Unset | Later PBT activation time |

N hash: `0x331c54fd1b37302697157dec30d2a1e0a13682843301f60d8ebac004f8bc4155`.
H hash: `0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216`.
The prepared range N+1…H contains 50,400 mixed-load blocks. CL genesis does not
replay that range: import migrations catch up from N while the shadowfork extends
H. Self-converting workers record their actual conversion point separately.
Seven days of prepared block timestamps is not seven days of live observation.

All workers are FRA1 `so-16vcpu-128gb-intel`: 16 vCPU, 128 GiB RAM and 2,400 GB
local SSD. **EL processes are limited to eight CPUs and the RAM below.** Recovery
volumes hold compressed backups; active databases run on local SSD.

| Worker | IP | EL RAM GiB | Recovery GiB | Migration path |
| --- | --- | ---: | ---: | --- |
| Geth-1 | 46.101.230.44 | 16 | 1,100 | Import |
| Geth-2 | 46.101.159.233 | 32 | 1,100 | Import |
| Geth-3 | 164.92.171.244 | 16 | 1,100 | Self-migration |
| Besu-1 | 138.68.76.218 | 16 | 1,100 | Import |
| Besu-2 | 164.92.248.222 | 32 | 1,100 | Import |
| Nethermind-1 | 167.172.188.11 | 16 | 1,050 | Import, FlatDB |
| Nethermind-2 | 201.79.83.218 | 32 | 1,050 | Import, FlatDB |
| Erigon-1 | 164.92.239.96 | 32 | 550 | Local conversion |
| Erigon-2 | 159.89.21.191 | 16 | 550 | Local conversion |

Use the pinned digests in [migration-builds.json](../scripts/pbt/migration-builds.json)
and inventory, including Besu `39377a2659…` with stateless `62b752345c…`.
Do not replace them with floating tags during launch.

## Active jobs and where to follow them

Controller: `/home/ubuntu/repos/glamsterdam-devnets`; private state:
`/home/ubuntu/.local/state/pbt-1-run/`. SSH uses root and
`/home/ubuntu/.ssh/devops_eth2_shared_key`.

```sh
# Controller: observe, do not restart these one-shot workflows blindly.
systemctl --user status pbt-1-artifact-publication-export-only pbt-1-post-publication
journalctl --user -fu pbt-1-post-publication
cat ~/.local/state/pbt-1-run/artifact-publication/auto-status.json
cat ~/.local/state/pbt-1-run/post-publication/status.json

# On Erigon-1:
systemctl status pbt-1-pbt-artifact-upload
cat /data/pbt-1/pbt-artifact-publication/status.json
journalctl -fu pbt-1-pbt-artifact-upload
# Once restore has started:
journalctl -fu pbt-1-v3-head-restore
```

The 15-minute fleet monitor writes `fleet/latest.json` under the private state
directory. Post-publication step logs are in `post-publication/`. Signed URLs,
authorization files and storage credentials stay private.

## Remaining work before choosing genesis

1. **N publication — complete.** The release is recorded in
   `artifact-publication/release.json`. The controller's terminal label
   `published_verified` means the selected transfer checks passed; under this
   mode it does not mean independent reconstruction or full remote readback.

2. **Finish recipient transfers — Geth-3 complete, six running.** The post-publication controller
   ran `authorize-migration-inputs.py --stage` and
   `ansible/pbt-stage-migration-inputs.yaml`. Geth-1/2, Besu-1/2 and Nethermind-1/2
   receive the snapshot, preimages and metadata; Geth-3 receives preimages and
   metadata. Each receives an independent writable copy under
   `/data/pbt-1/migration-input-24453558`. Follow
   `pbt-1-migration-input-download` and
   `/data/pbt-1/migration-input-24453558/ready.json`. Wait for all seven to finish.
   Migration mounts stay disabled until the migration restart.

3. **Restore Erigon-1 at H — running.**
   The controller reclaimed only its listed obsolete exporter data, then started
   `pbt-1-v3-head-restore` with streaming extraction, 8 GiB RAM and eight CPUs.
   The [cleanup receipt](../ansible/inventories/pbt-1/files/erigon-1-published-exporter-cleanup.json)
   records 1.37 TB local free space afterward. The original H database and
   recovery archive remain preserved while the corrected release is restored.
   The current signed restore URL expires around October 22 12:17 UTC; refresh
   it if needed, preserving the same release identity. A failed step stops the
   controller: read its step log before resuming. Its final
   `inputs_downloading_and_erigon_restore_started` status means jobs started,
   **not that they completed**.

4. **Run Erigon-1's own H startup check — now queued automatically.** Controller
   unit `pbt-1-erigon-1-restored-qualification` waits for successful restore and
   promotion, then starts the following once on Erigon-1. Do not duplicate it:

   ```sh
   python3 /data/pbt-1/qualify-restored-worker.py \
     /data/pbt-1/qualification/job.json --from-verified-release
   ```

   Read `/data/pbt-1/qualification/result.json`; confirm this worker's assigned
   32-GiB/eight-CPU startup and clean stop. Erigon-2's result cannot substitute.
   Controller status is in `erigon-1-restored-qualification/status.json` under
   the private state directory. The 15-minute fleet monitor follows it. Failure
   stops this handoff for inspection; it does not retry startup or launch CL.

5. **Replace Erigon-1's recovery archive — helper staged, execution pending.** Preserve
   original provenance, confirm its own H startup succeeded and the corrected
   published H object/Erigon-2 backup remain available. The 550-GiB recovery
   volume cannot hold both archives. Reconcile worker and controller recovery
   jobs to the corrected release, set `restore: false`, and replace the old
   archive by downloading directly to that volume, hashing during transfer.
   The helper is now staged at
   `/data/pbt-1/direct-recovery-replacement/prepare.py`, with original provenance.
   Its preflight correctly refuses before the H restore completes. After own H
   startup, run the helper without arguments, then with `--run` after its
   preflight succeeds. A single-object `source-url` is already staged in that
   directory and valid until October 22 at 17:49 UTC; refresh it if necessary.
   The latter removes the exact old archive and stages the corrected job with
   `restore: false`; it starts no service and changes no database. Then start
   `pbt-recovery-snapshot.service`, follow `/mnt/pbt-recovery/status.json`, and
   reconcile controller recovery inputs when it finishes. This operation is
   **not queued**; do not blindly restart the service with its old job. Source:
   [replacement helper](../scripts/pbt/prepare-erigon-1-recovery-replacement.py).

   Corrected H object:
   `pbt-1/20261020-erigon-v3-head/erigon/24503958/snapshot.tar.zst`,
   461,165,199,193 bytes, SHA-256
   `b4ab8e0831bd95ddce05b9f52c040de7eaf4a9b8b1fa49106cb3e9cd88938146`.

6. **Finish local cleanup and memory preparation.** After the new H database,
   own startup and corrected backup are ready, remove only explicitly obsolete
   preserved Erigon-1 copies. Restore its original ext4 reservation with
   `tune2fs -r 25171402 /dev/vda1`, after confirming the root device. Do this
   **after restore/cleanup**, since doing it earlier removes needed free space.
   Check free space on each actual database filesystem. With preparation jobs
   and clients stopped, finish the documented clean page-cache handoff on the
   remaining seven workers (`sync`, then `echo 1 > /proc/sys/vm/drop_caches`).
   Erigon-2 and Geth-3 already completed this; repeat only if later preparation
   rereads their database or input contents. Record the memory/cgroup baseline
   without another full database scan. The six pending non-Erigon recipients
   have `/data/pbt-1/prepare-cache-handoff.py` staged: default is preflight;
   `--run` clears clean cache after it passes. Do not repeat Geth-3's completed
   handoff. Source: [recipient cache handoff](../scripts/pbt/handoff-recipient-cache.py).

At this point: nine H startup results, nine usable recovery archives, seven
ready migration-input sets, no conflicting preparation writers, and sufficient
local migration space. These are the remaining preparation outcomes, not a
request for another comprehensive verification campaign.

## Configure genesis once G is chosen

Use a fresh private workspace under
`/home/ubuntu/.local/state/pbt-1-run/genesis/`. The archived test candidate is not a launch
configuration. Set `PBT_LAUNCH_VARS` to a private JSON file containing the chosen
`pbt_genesis_timestamp` and new `pbt_genesis_workspace`; set `PBT_CANDIDATE_DIR`
to that workspace. From `ansible/`:

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

Promote only the nine public files identified in `lighthouse-validation.json`
from its `evidence_directory/network-config/` into
`network-configs/pbt-1/metadata/`. Keep `mnemonics.yaml` and validator signing
files private. Confirm 2,304 validators, 256 unique assignments per worker.
Regenerate the 15 tooling values for actual G and review the resulting config.
Keep S unset. Preparation changes are in
[PR #99](https://github.com/ethpandaops/glamsterdam-devnets/pull/99);
review the final revision before launch deployment.

## Launch sequence — after explicit launch authorization

1. Deploy the prepared public config using `ansible/playbook.yaml`, skipping
   `ethereum_genesis` so it cannot regenerate the reviewed artifacts. Use the
   PBT-specific fact cache above and the chosen launch variables.
2. Start only the Geth-1 seed's EL/beacon with
   `ethereum_node_cl_validator_enabled=false`. Collect its live
   `/eth/v1/node/identity` ENR and check the expected genesis root.
3. Start the other eight EL/beacon pairs with that seed and validators disabled.
   Collect their CL identities, then render/apply peer lists again using all
   nine fresh records. The EL peer manifest alone does not bootstrap CL peers.
4. Check Engine/JWT connectivity, actual EL/CL peers, HTTPS and metrics. Run
   `scripts/shadowfork-pregenesis-check.sh pbt-1` from the repository root.
   Deploy the regenerated tooling config with load generation disabled.
5. Distribute the prepared signing keys to their assigned hosts and enable the
   nine validator sets before G. Never run a second copy of a signing set.
6. At G, watch the first payloads extend H, then check all clients follow the
   same canonical chain and finality advances. Check validator participation,
   Engine errors, process limits, free disk and EL/CL metrics before adding load.

## Fund and run the workload

Use the MSF-2 withdrawal route: genesis validators' `0x01` withdrawals pay the
mnemonic-index-0 treasury, which funds index 9 for Spamoor. The fee recipient is
separate. Wait for actual withdrawals and a shadowfork block after H.

```sh
# From repository root; first inspect amounts and available treasury balance.
scripts/fund-shadowfork.sh pbt-1 --only-spamoor --dry-run
# Once launched and the funding output is correct, this sends the shortfall:
scripts/fund-shadowfork.sh pbt-1 --only-spamoor
```

The default Spamoor target is 2,000,000 ETH, leaving 1,000 ETH treasury reserve.
**Omitting `--dry-run` sends transactions.** The script checks chain ID, H hash
and the first post-H timestamp to distinguish this fork from the parent chain.
Fund other tooling only as needed; do not start every generator at once.

Load the prepared [Spamoor calibration](../scripts/pbt/spamoor-calibration.yaml)
after checking the deployed Spamoor build accepts it. Its four scenarios are
initially disabled. Enable a short calibration, then tune sustained load toward
50% execution gas **and** 50% state gas under EIP-8037. Record both dimensions,
BAL bytes/block, transaction mix and block timing; aggregate `gasUsed` alone
does not demonstrate both targets. Back off if block production or finality
falls behind, and record the changed rate.

## Start migration and keep the network healthy

Use [the pinned client command sheet](pbt-1-client-migration-commands.md), cross-
referenced to [Maria's guide](https://github.com/misilva73/pbt-planning/blob/95ac0b56c5ad69ca99d3e3e8e77729d541d7a739/outreach/pbt-mainnet-fork-migration-test-plan.md).
After the MPT baseline is healthy, choose future S with time for import, catch-up
and the agreed dual-tree observation period. Maria's two-week observation goal
is not satisfied by the accelerated historical corpus. Stage consistent S
configuration, then restart one worker at a time while retaining validator quorum.

| Client path | Operation and observable result |
| --- | --- |
| Geth-1/2 | Import independent N snapshot/preimages copies with N hash; monitor `debug_migrationProgress` and binary cursor/root. Inputs may be consumed, so retries need fresh copies. |
| Geth-3 | Self-migrate with preimages/anchor and no snapshot flag; record actual finalized persisted seed point P. |
| Besu-1/2 | Set genesis `config.binaryTrieTime=S` and all three snapshot flags. Besu waits for sync and N finality, then loads in the background. Track migration progress and shadow roots. |
| Nethermind-1/2 | Keep FlatDB-only layout, set PBT/S and N import paths/anchor, with fast sync disabled. Preserve the already prepared FlatDB. |
| Erigon-1/2 | Stop one worker, run native `commitment convert-pbt --keep-hex`, record actual block/transaction checkpoint, then `attach-pbt` with matching state salt. Follow pinned alignment instructions. Restart with `--override.binary-trie=S`; require `mode: hex+bin`, `shadowStopped: false`. |

Keep the prepared BAL history available: Erigon currently uses
`--exec.no-prune=true` and Geth `--history.chain=all`. Do not introduce aggressive
expiry during catch-up. Report these settings and monitor disk growth. Besu may
use trie logs with BAL fallback; Erigon catch-up uses native re-execution. Record
the actual replay mechanism rather than claiming identical BAL import coverage.

Every 15 minutes, record block/finality progress, migration cursor lag, shadow
roots at the **same block hash**, RSS/cgroup peaks, disk free space and errors.
PBT roots are compared with PBT roots; they are not expected to equal MPT roots.
Watch more closely during startup, import transitions and activation at S.

If a worker fails, preserve its error/log and cursor, stop only that worker,
and fix the concrete failure. For restore, stop its EL and preserve evidence
before replacing its local database from the matching recovery archive. Never
restore over an open database or reuse consumed Geth import inputs. Avoid
placing only Besu's SST scratch on another filesystem: its load depends on
same-filesystem operations. Revisit disk placement only from an actual need.

Ready to activate means all nine migration paths have caught up, matching PBT
roots are observed at common canonical hashes, the network remains healthy,
and the planned observation period is complete. After S, confirm all clients
continue on one chain with advancing finality under the sustained workload;
retain logs, configuration, resource peaks and explicit coverage exceptions.
