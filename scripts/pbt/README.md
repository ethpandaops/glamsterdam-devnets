# PBT-1 source preparation

## Current preparation boundary

The current task prepares the nine-worker fork through genesis configuration.
No genesis time is selected and no shadowfork is authorized to launch.
The private timestamped validation candidate is archived test evidence only;
regenerate it after the user selects a launch time.

Preparation checkpoint, **2026-10-21 11:13 UTC**:

| Component | Verified so far | Still required |
| --- | --- | --- |
| Three Geth, two Besu, two Nethermind workers | Each passed isolated startup checks at H=24,503,958 with its assigned process limits | Verified migration-file delivery to the seven recipients |
| Erigon-2 | All 4,091 commitment files converted; both original-binary verifications and retained-tail execution passed; two own H opens passed under 16 GiB / 8 CPU at 09:38 UTC | H archive uploaded (461.17 GB); full remote readback and recovery-volume replacement remain |
| Erigon-1 | Original H database and recovery archive preserved; N export (107.90 GB snapshot, 66.85 GB preimages) exited 0 at 07:18 UTC with matching metadata | Independent verification running; then preserve N artifacts, restore the verified v3 H release and run its own 32-GiB startup checks |
| Genesis configuration | Private test candidate loaded in isolated Lighthouse at H with 2,304 validators; all nine inventory reviews passed | Regenerate and validate a fresh candidate after the user chooses G; distribute keys and promote only the public files afterward |

The frozen block in Erigon-2's conversion log is not the launch head. Its
retained tail contained another 35,934 blocks. The native
`stage_exec --block=24503958` reached H and exited successfully at 08:57 UTC;
the second independent verifier passed at 09:37 UTC, followed by two clean
worker opens at 09:38 UTC. The first independent verifier passed at 04:49 UTC.
The corrected H archive is now uploading. See
`files/erigon-2-v3-head-qualified.json`; migration remains unqualified.

At 05:01 UTC, a recorded graceful interruption stopped tail reconstruction at
committed block 24,469,105. `resume-erigon-head-tail.py` resumes only the remaining
stages using the same pinned native binary and changes `--batchSize` from its
512-MiB default to `4G`. The original 112-GiB preparation memory limit, eight CPU
limit, `NO_PRUNE=true`, commitment checks and subsequent qualification gates
remain in place. A wall-clock profile attributed about 299 of 693 seconds to
the main execution caller's `SharedDomains.Commit`; frequent small batches
were a measurable cost. The first larger batch executed 256 blocks with no
invalid results. By 05:06 UTC, the new run committed 1,021 blocks in 175 seconds
between batch starts, about 5.83 blocks/s including database flushes. This is a
short observed interval, not a controlled same-block speed comparison: cache
warming and changes to the file layout also affect throughput.
Later batches include longer database flushes and background index/merge work;
the initial 5.83 blocks/s must not be used as a sustained completion estimate.
This preparation setting does not change the worker's assigned 16-GiB limit.
The former log and completed CPU/heap/mutex/wall-clock profiles are retained
under `v3-head-upgrade/tail-batch-handoff/`. Both qualification and publication
waiters were restored after the intentional handoff. Genesis and PBT times
remain unset.

The remaining preparation order is: finish the shared-artifact verification;
publish and fully read back the shared N artifacts and corrected H archive;
deliver independent inputs to seven workers; restore and qualify Erigon-1;
reconcile recovery archive capacity and temporary storage; then audit all nine
workers. After the last file-content checks/downloads and with preparation and
clients stopped, clear clean preparation page cache and record the per-worker
handoff before measured startup. The experiment document explains why RSS and
cgroup accounting differ; `files/memory-accounting-review.json` records the
observed evidence. No live-job cache eviction has been performed.
The two publication paths can run independently once their respective
proofs pass. Neither path chooses G or the later PBT activation time S.

### Preserve the shared N artifacts before retiring the exporter

`publish-pbt-artifacts.py` is staged on Erigon-1 and the controller. It is
separate from publication of the worker H database archive. The controller
`publish-pbt-artifacts-when-ready.py` now waits in the user unit
`pbt-1-artifact-publication.service`. No multipart upload has started yet.
Its read-only `check` requires the native
export and independent verifier to have completed at N=24,453,558 with the
expected hash/root and unchanged artifact identities. The live check currently
refuses the missing combined export-and-verification completion proof.

The automatic controller waits for successful native exit and the complete
proof, runs those checks, authorizes scoped multipart uploads, starts the worker
upload, and performs the full remote readback. It never restarts failed jobs or
deletes exporter data. Thirteen publication/handoff tests cover incomplete native
proofs, changed artifacts, corrupt remote objects and the three-file release gate.

After that check passes, the controller's `authorize` action creates scoped
multipart uploads for `pbt-snapshot.bin`, `framed.bin` and metadata under
`pbt-1/20261020-pbt-anchor-24453558/`. Account credentials stay on the controller;
only expiring part URLs are transferred to the worker. Run its `stream` action
on Erigon-1 in a separate bounded systemd unit (4 CPUs, 4 GiB). It reads the
existing artifact files directly, verifies their full checksums while streaming,
and records all completed parts. It refuses a second whole-job attempt.

The controller's `finish` action compares the stored multipart lists, completes
the three objects and reads every byte back through the storage API. Only then
does it publish `release.json`. Nine focused tests passed, including changed
source evidence, missing parts, corrupt remote content and checksum mismatch
after successful PUTs. Evidence: `files/pbt-artifact-publication-plan.json`.

This preserves the artifacts; it does not establish cross-client import success
or shadowfork finality. Before reclaiming exporter working data, retain the
verified release and native export provenance, confirm the original source's
recovery location, stop every exporter process and review exact paths and
hardlinks. Keep `/data/pbt-1/erigon`, the H recovery archive and the payload
corpus. Re-measure free space before starting Erigon-1's H conversion.

For the preferred fresh H restore, re-measure after retiring the stopped N
working database. If the measured H unpacked-size bound plus its 150 GB reserve
still does not fit, the local `pbt-snapshot.bin` and `framed.bin` in
`/data/pbt-1/artifacts-24453558` are also reclaimable after their shared release
has passed full remote readback. Keep the metadata, native completion proof,
checksums and publication evidence. Confirm the release's object identities and
that no exporter, verifier or uploader owns either exact file before removal.
Erigon workers use their local conversion path, so these local shared-input
copies are not needed by Erigon-1's later migration. Nothing in this cleanup
permits removal of `/data/pbt-1/erigon` or its original H recovery archive before
the fresh H restore and worker qualification have passed.

The 09:03 UTC capacity review includes the earlier index-recovery datadir,
which shares files with the exporter and must be counted together with it.
The exact candidates are `v3-source-index-recovery/datadir`,
`rehearsal-24453558/erigon` and the two published artifact payload files. Keep
the surrounding logs/proofs, artifact metadata, original H database/archive
and payload corpus. Inode/link accounting estimates 884.91 GB reclaimable and
excludes 4.40 GB still linked outside those paths. With 484.68 GB free and an
estimated H restore bound of 1,192.37 GB, this leaves about 27.22 GB beyond the
150 GB restore reserve. These are provisional measurements, not permission to
remove live files: finish verification/publication, check owners and final
source sizing, then remeasure before cleanup and restore. No additional volume
is required by this projection. Evidence: `files/erigon-1-space-plan.json`.

The active exporter uses a temporary 1,500-GiB scratch volume for new ETL files
and the future verifier's temporary directory. Its existing native process was
not restarted. The volume was expanded online from 550 GiB at 05:18 UTC after
reviewing the pinned verifier: earlier sorted outputs remain while it builds
additional MPT storage and account representations. This is extra temporary
capacity, not a measured peak-space guarantee; the existing guard stays active.
Both mounts of this same device must be unmounted before detachment:
`/mnt/pbt-export-scratch` and
`/mnt/glamsterdam_pbt_1_erigon_export_scratch`.
See `files/erigon-export-scratch-resize.json` for the exact resize and source
review. At 03:44 UTC on October 21, snapshot writing finished and the
exporter entered preimage generation. Once all owning descriptors closed, the
scratch guard reclaimed 345,446,531,072 bytes from the recorded original local
ETL files. This raised local free space to about 551 GB. The snapshot is about
107.9 GB. Framed preimages finished at 05:37 UTC (66.85 GB), followed by the
exporter's internal readback. Independent verification and publication remain.
The native preimage hashing counter is reported from `nextAccount`, so it can
stay unchanged while many slots under one account are processed. Fresh
`Flushed buffer file` entries and growing scratch files establish ongoing
activity during that interval; a quiet summary line alone is not a restart
condition.
The later framed writer similarly reports only on account boundaries (every
4,096 accounts once its log interval expires). It validates and buffers a
large account's slots in a scratch file before appending that account to
`framed.bin`. During that work both the account counter and final-file size can
stay unchanged while native CPU time and the owned scratch file keep growing.
The root guard remains 150 GB and the scratch-volume guard remains 50 GB.
After snapshot readback, `JoinAt` first builds a `pbt-preimage-expected-*`
temporary file and sorts the actual preimage keys before its periodic join
counter begins. The last readback log can therefore remain visible during
active preimage validation. At 05:49 UTC the unchanged native PID held a growing
expected-key file on the scratch volume. This is progress evidence, not a
completed export or verification proof.
The comparison began logging at 06:35 UTC. Its two record counters measure
different things: `PBT preimage join progress` counts every compared key,
whereas `PBT export progress phase="preimage join"` counts storage-slot
callbacks. Alternating lines can show a smaller count without any restart or
lost work; compare each counter only with earlier lines of the same kind.
`files/erigon-export-storage-capacity-bound.json` records a conservative bound
for the remaining snapshot storage section, with no credit for that reclamation.
It does not cover the later preimage or independent-verification stages.

Before launch, finish and preserve the export, verification and uploads; stop
the scratch guard; confirm there are no remaining owners of the temporary
paths; remove the two recorded scratch symlinks; and unmount and remove only
the temporary export-scratch volume and its Terraform attachment/membership.
The recovery volume is separate and stays attached. Restore Erigon-1's root
filesystem reservation to its original 25,171,402 blocks after preparation
space is reclaimed. The exact identities and original settings are recorded in
`files/erigon-export-scratch-routing.json`,
`files/erigon-verify-scratch-routing.json` and
`files/erigon-export-filesystem-reserve.json`. These cleanup actions are still
pending while native export/verification owns the files.

### Deliver independent worker inputs after the shared release is verified

`authorize-migration-inputs.py` checks `release.json` and all three stored object
identities. Its default is read-only and currently reports that the verified
release is still missing. `--stage` creates private, expiring GET jobs for seven
workers: both Geth importers, both Besu and both Nethermind workers get the pair
and metadata; Geth self-migration gets preimages and metadata only. Erigon's
local PBT conversion path does not use this download job.

After publication:

```sh
/usr/bin/python3 scripts/pbt/authorize-migration-inputs.py --stage
cd ansible
ANSIBLE_STRATEGY=linear ansible-playbook -i inventories/pbt-1/inventory.ini \
  pbt-stage-migration-inputs.yaml \
  -e @/home/ubuntu/.local/state/pbt-1-run/migration-inputs/ansible-vars.json \
  -e ansible_user=root --private-key ~/.ssh/devops_eth2_shared_key
```

The downloader preserves 600 GB of local space for migration, uses ETag-bound
ordered ranges, checks received bytes and re-reads the stored files for SHA-256,
then atomically promotes `/data/pbt-1/migration-input-24453558`. Files belong to
the qualified client's service user and are writable independent copies.
Existing or partial inputs require inspection; it never overwrites them or
starts a client. Nine delivery tests and the Ansible syntax check passed.
The fleet monitor tracks the download unit and its completion proof. No input
authorization has been issued and no worker input download has started yet.

The client inventory also supports `pbt_migration_input_mount_enabled=true`
for the later migration restart. It binds each verified host input directory
at `/pbt-migration-input` inside the seven recipient containers. Use that
container path in migration flags. Leave the switch off until each recipient's
`ready.json` exists, so Docker cannot create the downloader's final directory
prematurely. The default-off and future-enabled controller reviews both passed
for all nine workers; the enabled review contains exactly seven input mounts,
with none on Erigon. No enabled mounts have been deployed and this switch does
not select a genesis or activation time.

Geth-2 temporarily holds the checksum-verified older Erigon exporter checkpoint
at `/data/pbt-1/erigon-exporter-recovery/tree`. At 02:00 UTC on October 21 it
had 753 GB free, leaving only about 152 GB for inputs after the downloader's
reserve and margin. Keep that checkpoint while the N export is unfinished.
After the shared release has passed full remote readback, retain its provenance,
confirm the original O recovery object and stopped copy service, then review and
remove only this temporary checkpoint tree. Re-measure Geth-2 before staging
its inputs. Its Geth database and native recovery archive remain protected.

Before launch, also review the corrected native H archive's actual compressed
size against each 550-GiB Erigon recovery volume. Keep the original archives
until the replacement is fully verified and fits. Erigon-1's preserved old H
directory can be reclaimed only after its fresh H database passes its own
restore/reopen checks, the v3 release has passed full remote readback, and the
original compressed H recovery archive remains intact. Review the exact
preserved directory and confirm no process owns it before removal. This frees
room to cache the new archive without deleting the original compressed backup
first. Keep any new local cache until the recovery-volume copy also passes its
full checksum; retain the original download proofs as historical provenance.
Do not leave two complete databases competing for migration scratch. This is
separate from the shared N inputs above.

The corrected H upload finished on October 21 at 11:12 UTC with **461,165,199,193 compressed bytes (429.49 GiB)**. Full remote checksum verification is still running. Both existing 550-GiB recovery volumes fit this archive after the reviewed replacement, with about 124.51 GB free afterward; no volume expansion is required. Erigon-2 has room for the local cache plus its 150-GB reserve while retaining its original backup. Erigon-1 still needs the restore/qualification/cleanup sequence above before caching the replacement.

The first H remote readback ended with a transport `ProtocolError` at 11:18 UTC. The upload remains complete. Both publication tools now hash ordered, ETag-bound 64-MiB ranges using four workers and up to five attempts per range. A short or interrupted range is retried before its bytes enter the hash; changed object identities and mismatched checksums still prevent publication. The H controller was restarted with `finish`, without repeating the upload. The N publication waiter was updated before authorization; native verification was not restarted. Six range-transfer tests and the existing publication/handoff tests passed. Full remote checksum verification remains required.

The cache downloader also accepts the separate, download-only profile
`verified-erigon-v3-head-recovery-cache` on Erigon-2, restricted to
`/data/pbt-1/v3-head-recovery/cache`. Erigon-1's existing restore-cache profile
and path remain separate. Both local cache modes preserve 150 GB of root-disk
space in addition to the remaining archive and range buffers. The new
Erigon-2 mode is prepared locally, not staged or running. It does not delete,
extract or replace anything. Seven downloader tests and eleven related restore
tests passed after this change.

After the H release passes full remote readback, use its actual size, checksum
and ETag for the cache job with `restore: false`. Keep the original recovery
archive until a complete corrected cache has been independently hashed and
the worker has passed its own H qualification. Then preserve the original job
and download/restore proofs, verify no process owns the old archive, and review
its exact path before reclaiming it. Copy the corrected cache to a temporary
file on the recovery volume, flush and hash the stored copy, then rename it
into place and update the recovery job/status/checksum proof to the corrected
release. Preserve the cache until that final copy passes. A failed copy must
leave the verified local cache available for retry. Do not infer replacement
success from a successful download or reuse the original archive's proof.
The actual archive must fit the recovery filesystem with operating headroom;
if it does not, resize to the measured requirement before replacement.

After the H release passes full remote verification, the controller command
`prepare-erigon-release-restore.py --stage-recovery-cache` stages Erigon-2's
download-only cache. It checks the published release against the stopped,
qualified source, requires the current worker proof to match, and checks room
for the compressed archive plus 150 GB and range buffers before issuing a URL.
It writes private inputs and a checksum-pinned downloader under
`/data/pbt-1/v3-head-recovery`; it does not start a service or touch the recovery
volume. After reviewing the staged inputs, run `download.py` from that directory
in the `pbt-1-v3-head-recovery-cache` preparation unit (4 GiB RAM, 4 CPU).
The existing 15-minute fleet monitor records its service and download progress,
and reports failures or a stopped/inactive transfer; it never restarts jobs.
Successful download is only
the cache step: independently hash the stored cache before proceeding with the
reviewed backup replacement above. The E1 restore staging option `--stage`
remains separate. Neither option can choose genesis time or launch a client.

The October 20 exporter boundary recovery is recorded in
`files/erigon-boundary-recovery.json` and `md/pbt-1-erigon-v3-source-2026-10-20.md`.
`verify-erigon-domain-fragments.go` is a read-only diagnostic built against the
pinned Erigon checkout; it compares every merged accounts/storage record with
the newest retained fragment value. `erigon-v3-resume-fixture_test.go` is injected
into the pinned source through a Go overlay for a small interrupted-v3-resume
test. Neither changes the deployed Erigon binary.
`resume-erigon-v3-boundaries.py` is restricted to the reviewed older exporter:
it requires successful comparisons, unchanged input identities, retained backups,
successful native fixtures, and no database owner. It preserves six files outside
the scanned domain directory and invokes native `commitment convert --v3
--continue`, followed by the existing verification and execution-restore stages.
It refuses repeated application. Do not use it against either worker H database.
`resume-erigon-head-boundaries.py` is the separate, staged Erigon-2 recovery for
the expected `1050624-1051648` accounts/storage mismatch. It defaults to a
read-only check and refuses the current active conversion. Six focused guard
tests passed, and all 6,144 candidate fragment/index identities were checked
on the worker. It requires the exact stopped failure, the six completed native
shards, matching full-record comparisons and the verified H recovery archive.
`--apply` must only follow a successful full preflight. It preserves merged
files and invokes the unchanged native converter; it does not start a client,
publish an archive, set genesis time or activate PBT. No recovery is queued.

Controller-only review (no timestamp or remote startup required):

```sh
cd ansible
ANSIBLE_STRATEGY=linear ANSIBLE_CACHE_PLUGIN_CONNECTION=tmp/pbt-1 \
  ansible-playbook -i inventories/pbt-1/inventory.ini pbt-review-configuration.yaml
```

`files/configuration-review.json` contains public image/resource/validator/peer
configuration. `files/peer-identities.json` contains public enodes and ENRs only.
Geth-1 is the DNS/certificate and metadata host as well as an EL/CL worker.
Terraform assigns it the `dns_server` inventory group, delegates the `srv`
zone to it and opens DNS only on that VM. It is not in the `bootnode` group,
which would inherit a second client configuration.
All nine workers now have Docker 29.9.1, the shared routed IPv6 bridge and
active route services. The four older distro installations needed an upgrade:
routed IPv6 was introduced in [Docker 27](https://docs.docker.com/engine/release-notes/27/).
The PBT inventory enables
`docker_remove_distro_buildx`, a tagged pre-task before the Docker CE role,
because that role's own Debian vars override its obsolete-package inventory
setting. Inspect stopped-client restart policies before any runtime upgrade.
`files/runtime-review.json` records preserved images and stopped-client states.
`files/proxy-review.json` records valid nginx configuration and the same loaded
origin certificate on all nine workers; it does not assert live client HTTPS
endpoints before client deployment.

The identities are prepared on each VM, outside its restored database:

```sh
ANSIBLE_STRATEGY=linear ANSIBLE_CACHE_PLUGIN_CONNECTION=tmp/pbt-1 \
  ansible-playbook -i inventories/pbt-1/inventory.ini pbt-prepare-identities.yaml \
  -e ansible_user=root --private-key ~/.ssh/devops_eth2_shared_key
```

This creates service accounts and persistent peer identities without starting
clients. Repeating it keeps the keys. Private keys stay on the worker. Never
copy a peer identity from another VM or restore a database's cloned node key
over the prepared identity directory.

`pbt-prepare-genesis.yaml` requires an explicit future timestamp and fresh
private workspace. Do not invoke it until the user selects that time.
`validate-genesis.py` can recheck the existing archived candidate without
choosing a new time. It records structural/key checks and, when present and
matching, the isolated Lighthouse SSZ-load evidence.

`check-genesis-with-lighthouse.py <candidate-workspace>` makes that isolated
load check repeatable. It copies the nine public metadata files into a new
private evidence directory, uses the pinned Lighthouse image with no network,
EL or validators, checks the decoded Gloas state/H/public keys through its API,
then stops the container. It refuses to replace an existing report; use a
different `--report-name` for a deliberate recheck. The archived candidate
passed this path with 2,304 validators and clean shutdown.

For a future selected launch candidate, promote only the checked
`network-config/` subset named by its `lighthouse-validation.json`, comparing
its recorded file checksums. The generator's original metadata also contains
`mnemonics.yaml`, which stays private. PBT validator key paths now require the
explicit `pbt_genesis_workspace` and use that candidate's private key directory.
The controller review checks the nine key ranges when that workspace is supplied.
See the morning handoff in `md/pbt-1-experiment.md`; G remains unset.

`migration-builds.json` records the intended client commits and qualified build
artifacts. Besu is built with `build-pinned-besu.py` against the exact stateless
library; its image archive is loaded on both workers and pinned by host-local
image ID. Keep the archive available for recovery; that image is not published
to a registry.

`check-monitoring.py` verifies fresh node metrics for all nine workers through
the central gateway. It uses an existing worker's configured credentials on
that worker; credentials never appear in the controller report. Node metrics
do not qualify EL/CL metrics or block production.

`check-migration-image.py` is a stopped-source-worker startup check for Geth
and Nethermind. It requires a verified local recovery archive, runs with
networking disabled, checks H/N, state reads and three retained BAL bodies,
and stops the client. It does not qualify migration or all deployment flags.

The held `prepare-erigon-anchor.py` now follows the documented capture boundary:
replay through N-1, submit N with `STOP_AFTER_BLOCK=N`, verify the intentional
exit marker and stopped state, then persist N using offline `stage_exec` with
the stop variable unset. Two opens must agree on N's hash, root and payload
body. A dropped RPC connection, ordinary shutdown, crash or wrong-block marker
does not qualify the boundary. Its instruction-review hold remains in place
until the older exporter conversion and native reopen evidence are reviewed.

`qualify-worker.py` extends that check to restored Geth, Besu and Nethermind
workers and their intended service accounts and unique peer keys. It also
supports both Erigon workers after their own H conversion: require successful v3
verification and tail reconstruction, open with the pinned image at the assigned
limit (Erigon-1: 32 GiB; Erigon-2: 16 GiB),
verify H/N, code, identity and three BAL bodies, then repeat after a clean stop.
This Erigon path rejects the older exporter proof, a proof copied from the other
worker, or a mismatched H/hash/root/build/recovery archive. Erigon-1's job is
prepared but held until its own H conversion completes. The reviewed driver
supports both workers, with a separate preserved-producer preflight for
Erigon-1; it has only been started on Erigon-2.
`files/qualification-jobs.json` records its public pinned inputs and sampled
payload-body digests. Each VM's staged job is
`/data/pbt-1/qualification/job.json` when staged. It checks the local recovery archive's
recorded SHA-256, size and modification time before opening a database.
`--wait-for-restore` waits only while the recovery service is active, with a
six-hour limit, and refuses failed/stopped restores. It never launches a CL,
submits a payload or selects a genesis timestamp.
`--wait-for-erigon-conversion` is queued on Erigon-2. It polls the actual
conversion service and requires successful completion before touching the
database. A failed, missing or prematurely stopped conversion prevents startup.

The isolated checks are units named `pbt-1-worker-qualification.service`.
Read `qualification/result.json` and `qualification/container.log` on the VM;
do not restart a failed check until its cause and stopped-container state have
been inspected. In particular, Besu's normal startup may upgrade its native
database format; the original archive is retained for recovery.
The fleet monitor includes qualification failures and live compressed-input
progress for active extractions. These are startup gates, not migration results.
It separately monitors the older exporter and H conversion, including unit
state, conversion log progress, disk space and OOM events.

`upgrade-erigon-head-v3.py` upgrades the selected worker's H database using its
verified recovery archive for rollback. It does not qualify or publish the
result. `protect-erigon-bal-retention.py` installed an atomic launcher for the
two live drivers so their future `stage_exec` children use `NO_PRUNE=true`.
The SHA-verified executable remains at `integration.pinned`; the current
conversion process keeps its inode and continues uninterrupted. The corrected
drivers set that environment variable directly for future fresh runs.
Keep the launcher and its evidence until these one-shot jobs have completed;
do not rerun a driver against the launcher as if it were the native binary.

The updated `verify-erigon-v3-source.py` is staged on Erigon-1 as
`/data/pbt-1/verify-erigon-v3-source-guarded.py`. Its read-only `--check-only`
mode requires the source converter to be stopped successfully, the exact older
exporter identity, successful v3 verification and BAL-preserving tail
reconstruction. A premature call does not overwrite the live conversion's
status. The actual reopen holds the conversion lock and keeps pruning disabled.
Use this guarded copy for the later two-open exporter check. The obsolete
source-publication controller remains stopped; this validation does not publish
the older exporter as a worker snapshot.

`recover-erigon-unsqueeze-index.py` is a narrow recovery experiment for the
older exporter's disk-reserve interruption. It copies mutable chain metadata,
links immutable snapshot context into an isolated directory, excludes the old
converted-range accessors, and builds missing indexes for the completed data
file. It never promotes files or resumes conversion. Its first attempt lacked
snapshot context; the explicit `--retry-with-source-files` retry preserves that
failure evidence and supplies the correct snapshot settings. Review completed
accessors and the conversion continuation requirements before any promotion.
The restored H worker database and recovery archive are retained.

After the index job stops successfully, `upgrade-erigon-v3.py
--check-index-recovery` performs a read-only check of its result, data-file
identity, original checkpoint, database settings and generated accessor.
Only after reviewing that result, `--resume-after-index-recovery` links the
new accessor into the interrupted rebuild directory and resumes the identical
`--squeeze=false` conversion with `--continue`. The original interruption logs
are preserved. The driver then performs the existing v3 conversion, verification
and O-tail reconstruction sequence, with the same 150 GB disk-reserve stop.
No index result alone qualifies conversion or permits artifact publication.

`prepare-erigon-anchor.py` remains held pending the older exporter's completed
v3 conversion and two-open proof. Its updated path uses the pinned v3 image,
replays only the verified 1,020-block prefix from O to N, stops, runs
`NO_PRUNE=true integration stage_exec --block=24453558`, then reopens and checks
N's hash, MPT root and BAL body. Only the separate exporter database is writable.
Do not remove `instruction-review-hold.json` or start the procedure before
reviewing the actual source proof. Export and artifact verification follow;
finality must still be checked against the eventual running shadowfork.

For the next experiment steps and per-worker acceptance criteria, use
[PBT-1 experiment](../../md/pbt-1-experiment.md). Preparation and publication
success do not establish PBT migration or replay coverage.

## Nine-worker recovery fleet (October 20)

The operator selected `so-16vcpu-128gb-intel` for all nine workers and a dedicated
compressed-snapshot recovery volume for each. Terraform defines Geth ×3 and
Besu/Nethermind/Erigon ×2. Volume sizes are 1,100 GiB for Geth/Besu, 1,050 GiB
for Nethermind and 550 GiB for Erigon. Active databases stay on local SSD.

`ansible/pbt-recovery-fleet.yaml` mounts each Terraform-assigned volume by UUID,
removes ext4's root-only reserve on that archive filesystem, installs the
checksummed download job and starts it. The controller supplies a public job
manifest and a separate mode-0600 object-scoped URL. No account credential goes
to a worker. Configuration and source URLs are under `/etc/pbt-recovery`.

`fetch-recovery-snapshot.py` uses four 64-MiB HTTP ranges in parallel, checkpoints
durable contiguous progress, and verifies the full published SHA-256 before
extraction. Existing databases are preserved: only the five newly provisioned
workers have extraction enabled. Partial extraction is not automatically retried
or overwritten. Inspect failure evidence before recovering it.

Worker status: `/mnt/pbt-recovery/status.json`.
Recovery archives: `/mnt/pbt-recovery/<client>-24503958.tar.zst`.
Service: `pbt-recovery-snapshot.service`.
The `restored_unopened` phase means extraction completed, not that the client
passed a database reopen or migration check.

The read-only controller `pbt-1-fleet-monitor.timer` checks all nine hosts every
15 minutes using `monitor-fleet.py`. Reports are under
`~/.local/state/pbt-1-run/fleet/`. The separate rehearsal monitor tracks the
Erigon restore for N=24,453,558. Completed generation/relay timers are disabled.

The first Terraform rollout holds Erigon-1 at its old size while the anchor
restore finishes, resizes the other three original machines and creates five
workers. A final reconciliation upgrades Erigon-1 after its jobs stop cleanly.
The temporary stage-one variable file lives on the controller; the committed
`nodes.tf` describes the final nine-worker shape.

The full experiment and remaining gates are in the
[rehearsal DAG](../../md/pbt-1-rehearsal-dag.md).

See the [PBT-1 migration process](../../md/pbt-1-migration-process.md) for the
nine-machine test matrix, process memory limits and BAL availability audit.

Seed the dedicated DigitalOcean node before choosing the migration sequence. This restores
Erigon's Jochemnet release at 24452538 into `/data/pbt-1/erigon`, using the existing
parallel streaming downloader. It does not start Erigon or generate network state.

The source metadata reports 428,144,697,343 bytes restored. Require at least 550 GB
free for this restore; PBT conversion needs a separate capacity check. The archive
is streamed directly into extraction with bounded chunk staging on the destination
filesystem. A stopped partial extraction is not automatically resumable or erased.

Terraform in `terraform/pbt-1` provisions four non-validating source nodes in Frankfurt,
using MSF-2's `so1_5-8vcpu-64gb-intel` size (8 vCPU, 64 GiB RAM, 1800 GiB disk per
the DigitalOcean API). There is one source each for Erigon, Geth, Besu and
Nethermind; this preparation starts no Lighthouse or validators. Run from the infra repository:

```sh
cd ansible
ANSIBLE_STRATEGY=linear ANSIBLE_CACHE_PLUGIN_CONNECTION=tmp/pbt-1 \
  ansible-playbook -i inventories/pbt-1/inventory.ini pbt-erigon-seed.yaml \
  -e ansible_user=root
```

The initial root login uses the DigitalOcean-injected shared devops SSH key.
The play installs/enables Docker, verifies source metadata and
checks archive access from the node before starting the detached fetcher. It refuses
to extract over existing data. Container name: `pbt-1-erigon-snapshot`.

## Current deployment (2026-10-19)

`glamsterdam-pbt-1-lighthouse-erigon-1` is at `164.92.239.96` (DigitalOcean ID
610514960). Terraform applied seven new resources with no changes/deletions to
existing infrastructure. The detached restore started at 12:56:50 UTC through
Ansible; runtime extraction and increasing chunk counts were verified.

Completion confirmed at 13:27:44 UTC: the fetcher exited with code 0 and the
`snapshot-fetcher/done` marker exists. Client startup and database validation
remain separate checks.

The public archive currently returns HTTP 403: the Cloudflare rule allows
`snapshot.tar.zst` but omits `snapshot-pruned.tar.zst`. Metadata remains public.
Authenticated R2 access verified the pinned archive size of 276,341,609,865 bytes.
For this run, a 24-hour signed GET URL authorizes only that object. To reproduce
from the repository root, using the existing Cloudflare credential locally:

```sh
python3 scripts/pbt/authorize-snapshot.py \
  --host root@164.92.239.96 --identity ~/.ssh/devops_eth2_shared_key
cd ansible
ANSIBLE_STRATEGY=linear ANSIBLE_CACHE_PLUGIN_CONNECTION=tmp/pbt-1 \
  ansible-playbook -i inventories/pbt-1/inventory.ini pbt-erigon-seed.yaml \
  -e ansible_user=root -e seed_authenticated_source=true \
  --private-key ~/.ssh/devops_eth2_shared_key
```

The helper checks the archive size and stores the URL in a mode-0600 file on the
node. Storage credentials remain on the controller. The downloader reads the URL
when it starts, so renewing the file does not update an already running fetcher.
If a restore fails or exceeds URL expiry, inspect it before restarting; the play
refuses to overwrite partial data. Remove `snapshot-fetcher/source-url` after
completion. Full client deployment and PBT conversion are separate steps.

## Additional source restores

| Client | Inventory host | IP | Restore playbook |
| --- | --- | --- | --- |
| Geth | lighthouse-geth-1 | 46.101.230.44 | pbt-geth-seed.yaml |
| Besu | lighthouse-besu-1 | 138.68.76.218 | pbt-besu-seed.yaml |
| Nethermind | lighthouse-nethermind-1 | 167.172.188.11 | pbt-nethermind-seed.yaml |

Run these playbooks from `ansible/` with the same explicit PBT-1 inventory, cache
and root SSH login. They share `pbt-source-seed.yaml`, which waits for cloud-init,
validates each client's pinned metadata and refuses nonempty destinations or
failed partial restores. The public URLs for these three clients work without a
signed URL. Fetchers are named `pbt-1-<client>-snapshot`; databases are under
`/data/pbt-1/<client>`. Their restores were started on 2026-10-19.

Nethermind's archive contains `mainnet/` beneath that destination. Its obsolete
Patricia data is scheduled for removal after restoration using
[`nethermind-flatdb-cleanup.py`](nethermind-flatdb-cleanup.py). The operator explicitly
requested this cleanup before uploading the refreshed snapshot. The job runs in
a detached systemd service on its VM and performs baseline validation, client-managed
deletion, and clean restart verification with networking disabled for the checks.
It uses the native `FlatDb.DropPruningTrieState` flag and a pinned image digest.
Inspect with:

```sh
systemctl status pbt-1-nethermind-flatdb-cleanup
journalctl -u pbt-1-nethermind-flatdb-cleanup --no-pager
cat /data/pbt-1/nethermind-flatdb-cleanup/complete.json
```

The report records allocated Patricia bytes before/after cleanup. If the job fails,
inspect its phase logs before retrying; a diagnostic container may remain stopped.
Only a successful `complete.json` qualifies the cleanup for snapshot publication.
The live deployment uses a Geth-format copy of MSF-2's source genesis (same mainnet
genesis and Amsterdam schedule, alloc addresses prefixed with `0x`) at
`/data/pbt-1/pbt-1-source-genesis.json`. The script records its SHA-256 in the report.

Monitor on the VM:

```sh
sudo docker logs --tail 30 -f pbt-1-erigon-snapshot
sudo docker inspect --format '{{json .State}}' pbt-1-erigon-snapshot
df -h /data/pbt-1
test -f /data/pbt-1/snapshot-fetcher/done
```

After restore, verify an isolated Erigon node's head/hash/root against the retained
metadata before any conversion. Choose the PBT build and commitment upgrade path
separately. Do not let the restored chain-id-1 database peer with mainnet.

Check download status on that node; it runs independently of this workspace session.

## Continuous monitoring

[`monitor.py`](monitor.py) runs read-only checks against all four source VMs.
It also checks controller disk headroom for the replay bundle, estimating remaining
records at 125% of the observed average size plus a 10 GiB reserve. Bundle upload
streams tar/zstd output and does not require a second complete archive on disk.
The controller's enabled user timer `pbt-1-monitor.timer` runs it at :00, :15,
:30 and :45 UTC. User lingering is enabled, so checks survive shell logout.
Each run records progress, free disk, container failures/OOMs, restore completion,
and the Nethermind cleanup service/result. During generation/replay,
`bal-sentinel.py` retrieves the first generated body, first qualifying body and
a recent body, comparing BAL bytes, transactions and withdrawals with the saved
records. This detects retention problems before the final exhaustive audit.
A running restore with no chunk
progress between checks, low disk, failed SSH or failed cleanup raises an alert.

Reports are local to the controller:

- `~/.local/state/pbt-1-monitor/status.md`: latest readable report and alerts.
- `~/.local/state/pbt-1-monitor/latest.json`: latest machine-readable evidence.
- `~/.local/state/pbt-1-monitor/history.jsonl`: full check history.

```sh
systemctl --user list-timers pbt-1-monitor.timer
journalctl --user -u pbt-1-monitor.service --no-pager
python3 scripts/pbt/monitor.py
```

Alerts are recorded in these reports and the systemd journal; this timer does not
send chat/email notifications. Failed checks do not disable subsequent timer runs.
Generation/replay/upload runners can publish `/data/pbt-1/pipeline/status.json`
on their VMs; absent that evidence, the report leaves those phases unverified.
Stop recurring checks when no longer needed with
`systemctl --user disable --now pbt-1-monitor.timer`.

## Historical workload generation and publication

This section records the earlier October 19–20 source-generation stage:
generate the workload, replay it on all four clients, verify restarts and BAL
availability, and publish native snapshots plus the replay bundle. Those H
snapshots are now restored on all nine workers. The current remaining work is
listed at the top of this document, including Erigon's v3 correction. The old
preparation clients used a 48 GiB container limit; the agreed 16/32 GiB budgets
apply to the nine-worker migration trials.

The first pilot (1,000 blocks, approximately 29.7M gas) remains a recorded
preparation prefix. The operator subsequently required approximately **50%
occupancy in both EIP-8037 dimensions**, with substantial BALs. Version 2 uses:

- 200M block gas limit, targeting 100M execution gas and 100M state gas.
- 900 mixed ETH/WETH/single-storage transactions, eight batches creating 1,021
  fresh slots, and 34 batches updating 4,300 existing slots: 942 transactions.
- Eight batch-storage contracts and a separately seeded existing-state working
  set. Fresh slots have unique hashed keys; existing slots and values are nonzero.
- 99,976,320 state gas (`1021 * 64 * 1530`) and measured execution gas near
  100,532,000. Every qualifying block must stay within 5M of each 100M target.
- At least 300 KiB of encoded BAL per qualifying block. The first ten measured
  approximately 453,500 bytes each (~443 KiB), versus ~57 KiB in the first pilot.

Starting at block **24,467,832**, `v2.packing_revisions` reduces the existing-slot
updates to **4,252** while preserving the 942 transactions and 1,021 fresh slots.
The ten-block calibration measured approximately **99.90M execution gas**,
**99.98M state gas**, and BALs of at least **450,889 bytes**. This keeps header
gas below the 100M fee target, preventing the gradual base-fee increase observed
with the initial 100.53M execution load. Generation and final audits enforce the
new header-gas ceiling from the revision's effective index. Earlier qualifying
records are retained unchanged. Calibration evidence is included in the replay
bundle; see the [pilot report](../../md/pbt-1-8037-pilot-2026-10-19.md#fee-stable-packing-adjustment).

Execution gas is derived from the receipt gas sum minus state gas. This workload
has no storage clears/refunds or calldata-floor-bound transactions; the derived
`max(execution,state)` must equal the header's `gasUsed` on every block. A separate
Geth prestate trace of block 24,453,559 confirmed 1,021 fresh slots, zero clears,
zero new accounts and 942 transactions. This is a synthetic mixed workload,
not a measured reproduction of mainnet traffic. No blobs or CL consensus run.

The source anchor is **24,452,538**. The original 1,003 records plus 17 version-2
setup records form a **1,020-block preparation prefix**. The qualifying anchor is
**24,453,558**; the 50,400 qualifying blocks end at **24,503,958**. Twelve seconds
per block provide 604,800 seconds from qualifying anchor to final head. The
original source releases and the complete prefix remain recoverable; a new
native copy at the qualifying anchor can be reconstructed by replaying the prefix.

`source-client.py` starts pinned images with Docker networking disabled. The
driver joins the container's network namespace; RPC is not exposed externally.
`generate.py` saves a pending replay record before canonicalizing it, verifies
all receipts, checks both gas dimensions and the BAL hash/size, and atomically
publishes an immutable `blocks/<height>.json.gz`. `replay.py` requires Engine
`VALID`, then matching canonical hash, state root and BAL hash. Erigon's RPC view
may lag its Engine acknowledgement briefly; the driver waits for that view.

`reopen.py` performs a clean stop/restart, compares state samples, and retrieves
**every** generated BAL body and transaction list through
`engine_getPayloadBodiesByRangeV2`. The initial version-2 pilot requires 1,000
qualifying blocks to pass this gate on all four clients before the full run.
The legacy `--workload-blocks` argument counts records after the first three
setup blocks, so the version-2 pilot uses **2017** and the full run **51417**.
The report's `qualifying_blocks` is the operator-facing workload count.

Erigon uses two merge and two compression workers after the observed slowdown.
Before either final shutdown, `erigon_idle.py` waits for merge/compression work
to finish using SIGUSR1 goroutine profiles; it refuses SIGTERM after two hours
without an idle result. This avoids the observed compressor cancellation
deadlock. The intermediate forced-stop recovery preserved exact commitments
but does not qualify as a clean shutdown. See the
[incident and recovery evidence](../../md/pbt-1-erigon-merge-2026-10-19.md).

Controller user timers:

- `pbt-1-monitor.timer`: read-only status/alert report every 15 minutes.
- `pbt-1-relay.timer`: copy completed payload records to consumers every 20
  seconds after the previous transfer completes; SSH keys stay on the controller.
- `pbt-1-advance.timer`: inspect evidence gates every 30 seconds, run restart
  checks, start the qualified full run, and schedule verified publication.

Failures stop the affected stage for inspection; the controller does not
automatically retry failed database operations. Inspect
`~/.local/state/pbt-1-run/advance-status.json` and the corresponding systemd
journals. `full-run-gate.json` records the four passing pilot gates. Sensitive
controller storage authorization is in a mode-0600 file outside the repository.

The monitor reports a replay-only ETA after at least five minutes of advancing
native replay from the same live service/client invocations and client memory
limit. Stale observations, restarts, changed targets and unknown or changed
memory limits invalidate the estimate. It shows the time left
before the 09:00 UTC deadline after replay and excludes final restart, BAL
restoration/audit, upload and remote verification; it is not a delivery promise.

Publication is under the new immutable prefix
`s3://ethpandaops-shadowfork-images/pbt-1/20261019-mixed-8037-v2/`.
Each native archive is `<client>/<head>/snapshot.tar.zst`. Geth remains a flat
instance directory and must be restored under `<datadir>/geth`. Nethermind
retains its required native databases under `mainnet/`; obsolete Patricia state
is omitted. Nethermind's client-managed cleanup reclaimed **341,910,994,944 bytes**
and passed state/head/restart validation on 2026-10-19. Its original cleanup
evidence is published beside the native archive as `_snapshot_flatdb_cleanup.json`,
linked from the snapshot metadata. Erigon's disposable `temp/` merge directory
is also omitted; the pinned client clears that directory on startup.

Erigon's finalized-head pruning also removes BAL sidecars. A live sample took
20.10 seconds to regenerate 16 older qualifying BALs. After its final clean stop,
[`retain-erigon-bals.py`](retain-erigon-bals.py) restores the already-validated
sidecars through a [pinned native backfill utility](erigon-bal-backfill/README.md).
Every sidecar must match the canonical native header, and the entire input range
is checked before any write. The same image then reopens with
`--exec.no-prune=true` and passes the unchanged exhaustive Engine body/BAL audit
before its second clean stop. Preserve this benchmark retention flag when using
the snapshot. Publication includes the backfill and build evidence; it explicitly
records restoration from validated replay inputs.

If the original Erigon database was advanced by the native replay comparison,
publication also requires its completed pinned-image reopen proof and matching
binary build manifest. These are published as `_snapshot_native_replay_probe.json`
and `_snapshot_native_replay_build.json`, linked from the snapshot metadata.
An incomplete comparison prevents publication; the final pinned-image validation
remains required.

`export-raw-stream.py` exports the remaining Geth raw blocks into bounded,
hashed chunks. `relay-raw-stream.py` streams each chunk through the controller,
verifies every compressed file on Erigon, and atomically exposes the chunk.
The controller retains no full second raw-block stream. Geth's final shutdown
waits for its requested export to complete, so the export cannot lose its RPC
source during publication preparation.

`replay-erigon-native.py` is the continuous native driver. Activation requires
a completed original-VM pilot, a matching binary/build manifest, and a completed
probe of the selected batch size with persistence and restart checks. It verifies
raw-file hashes before staging and requires ordinary Engine `VALID` responses and
matching commitments for every block. Its final clean stop and pinned-image reopen
precede the existing exhaustive BAL audit and upload gates. The monitor follows
the native systemd PID while Docker is stopped. Publication includes the continuous
run's build and completion evidence whenever its work directory exists.

`handoff-erigon-native.py` changes a running native replay's build/batch size only
after verifying the candidate's completed probe. It stops the replay driver,
waits for the last forkchoice to persist, checks every segment header and any
unreported payloads, and compares recent bodies. A clean native shutdown and
exact pinned-image reopen precede archiving the segment under
`/data/pbt-1/native-replay-segments/`. The continuous driver then starts from that
head. Publication checks segment continuity and includes each prior build and
sealed-segment proof. A failure requires inspection; it does not automatically
retry or overwrite the preserved evidence.

`pilot-erigon-buffer.py` qualifies a 2-GiB execution buffer over exactly 256
blocks after `handoff-erigon-native.py --seal-only` has verified the pinned
reopen. It keeps the verified continuation binary, batches of 64, eight CPUs,
48-GiB process limit and normal durability. The first 64 blocks are warmup;
timing waits for their persistence before measuring the remaining 192. Every
pilot body and header is checked before native shutdown and after pinned-image
reopen. A successful pilot becomes a contiguous sealed segment and leaves the
pinned client running. Continuing with the new buffer still requires explicitly
starting the continuous driver with the pilot's `proof.json`; failure never
automatically retries the database operation.

An inspected startup mismatch can use `--resume-staged` only before any pilot
batch completes. It requires a same-PID proof that all 64 already-stored headers
and bodies match the inputs and that the forkchoice head is unchanged. Recovery
adds 64 new blocks to that stored prefix for a 128-block warmup, retaining normal
forkchoice, per-payload VALID checks, header checks and persistence. This avoids
re-inserting below the header-sync tip and advances beyond the duplicate-FCU
path. The final two 64-block batches form the 128-block measured window; all 256
pilot bodies still require both audits. The original guard remains unchanged.

The `--profile wide-128` pilot uses a separate `native-wide-pilot/` evidence
directory, a 4-GiB execution buffer and four batches of 128 blocks. It excludes
the first 128 blocks and their persistence from its measured window, then checks
all 512 headers and bodies before shutdown and after pinned-image reopen. CPU,
48-GiB process limit and normal durability remain unchanged. Success qualifies
that configuration; a measured gain is still required before adopting it for
the remaining replay. The continuous driver requires the matching proof.

For a planned handoff, `handoff-erigon-native.py --seal-only --wait-next-head`
waits for a fresh head-update notification before stopping the replay driver.
This reduces the chance of leaving a later batch staged beyond the head. The
notification is not a persistence proof: the handoff still waits for the
post-forkchoice event, audits every segment header and any unreported payloads,
and verifies pinned-image reopen before sealing the segment.

After the first large Erigon merge completed, another 20 GiB merge range began.
[`suppress-erigon-maintenance.py`](suppress-erigon-maintenance.py) checkpointed the
paused datadir, verified a separate mutable MDBX copy and preserved immutable
snapshot files, then restarted the same image with background maintenance and
pruning disabled for the bounded preparation run. Shutdown was clean (exit 0),
and the exact head and sampled BALs matched after restart. Replay resumed at
20:00:31 UTC. This keeps new state and BALs in native storage; monitor database
growth. The final startup profile and maintenance-restart evidence are published
with the snapshot. These diagnostic preparation flags are not an operational
network default; retain `--exec.no-prune=true` when native BAL retention is needed.
Normal pruning was subsequently restored for ongoing replay to control database
growth. The final backfill/retention procedure applies `--exec.no-prune=true`
again before the exhaustive pinned-image restart audit.

`prepare-upload.py` issues only object-scoped presigned multipart PUTs to the
VM. `upload.py` requires the final stopped/reopened proof, streams sparse tar
through zstd level 1, and uploads bounded 256 MiB parts with Content-MD5 checks.
Erigon uses thirty-two upload workers after a verified sixteen/thirty-two/sixteen-worker
throughput comparison on its original VM; the other clients use four. This
bounds PUT buffers at 8 GiB for Erigon, plus stream/compression overhead. The
integrity report records the worker count used for newly started uploads.
`finish-upload.py` completes the object, checks size, verifies first/last and
sampled part SHA-256 values by remote readback, and publishes provenance. No
account storage credentials are copied to a source VM. Original Jochemnet
objects and latest pointers are preserved.

Native archives omit node keys, JWT secrets, root keystores and Nethermind's
`mainnet/keystore`, as well as its Patricia `mainnet/state` directory. The
uploader records its actual exclusion arguments in the integrity report.
Nethermind publication requires the keystore and Patricia exclusions. The
archive-content tests exercise GNU tar against both flat and nested fixtures.

Once the complete producer stream has passed its final restart audit,
`publish-bundle.py --prepare-only` can upload `replay/snapshot.tar.zst` while
the other clients finish. It compares all compressed record hashes with the
audited Geth source, then checks each hash again while streaming the archive.
The archive contains `blocks/`, `workload.json`, `manifest.json`, the source
genesis and calibration artifacts. Its embedded manifest describes the replay
artifact and explicitly does not claim completed snapshot delivery.

The **entire** replay archive is verified by remote readback before writing
`replay-bundle-ready.json`. After all four native snapshots pass, the normal
`publish-bundle.py` invocation checks their head/hash/state/BAL against the
prepared artifact, and rechecks storage and public archive sizes and ETags for
all four native snapshots and the replay bundle. Native ETags must match their
multipart completion records. These checks precede publication of
`_snapshot_manifest.json` and `_snapshot_workload.json`; a mismatch prevents
the final manifest and delivery marker. The final manifest records these
identity checks and binds the embedded replay manifest by SHA-256. Existing bundle
objects are never overwritten by the preparation path; failures need inspection.
Only `~/.local/state/pbt-1-run/delivery-complete.json` establishes completion of
the full requested delivery. Snapshot publication alone does not establish that
the separate replay bundle has completed.

For the patched **H = 24,503,958 v3 MPT** archive, use the separate
`publish-erigon-v3-head.py` controller. The older `publish-erigon-v3-source.py`
targets the exporter at 24,452,538 and must not be used for worker publication.

Run the controller with `/usr/bin/python3`, which has the storage SDK installed;
the interactive shell's Python currently does not.
The H controller has `check`, `authorize`, `finish`, and guarded `auto` actions;
it never starts conversion or a client. `check` requires Erigon-2's completed
conversion and two successful pinned-image reopenings with the exact H hash
and state root, then checks that the database is stopped.

After a successful check, `authorize` creates scoped multipart URLs bound to
the qualification report's SHA-256. Start the staged
`/data/pbt-1/upload-v3-head-stream.py --v3-head` on Erigon-2 only after
authorization. The streamer holds conversion and qualification locks and uses
eight upload workers. `finish` checks the uploaded part list, reads back the
entire compressed object, checks its SHA-256 and source genesis, then publishes
metadata under `pbt-1/20261020-erigon-v3-head/erigon/24503958/`.
The original release and recovery archives remain intact. Post-conversion BAL
validation currently samples three bodies; it is not a new full-range audit.
Measure the new compressed size before planning a replacement on the existing
550-GiB recovery volumes. No genesis time or PBT activation is set by these tools.

The queued `auto` action performs those same publication steps after observing
successful inactive conversion and qualification units. It starts exactly one
`pbt-1-v3-head-upload` service (16 GiB, four CPU equivalents), keeps its exit
state until the controller observes success and the completed-parts report,
then performs the full readback and release. A lost SSH observation re-polls
the same unit; it never starts a second uploader. Any failed predecessor,
missing proof, existing authorization or existing destination stops the
operation for inspection. Storage credentials stay in the controller-only
environment file. Current progress is in the controller's
`~/.local/state/pbt-1-run/v3-head-publication/status.json` and fleet monitoring.

`upgrade-erigon-head-v3.py --worker=lighthouse-erigon-1` supports converting the
preserved H producer after exporter work is stopped and sufficient disk is
available. The default worker remains Erigon-2. `--check-only` checks host,
source provenance, exporter inactivity and startup capacity without changing
conversion status; binary checks and full recovery-archive metadata checks
also run before actual conversion. Erigon-1 uses its original stopped H
producer proof; Erigon-2 requires its archive restoration proof. Neither accepts
the older exporter as its H source. Fresh conversions require more than 1 TB
free, based on observed scratch growth plus the 150-GB interruption reserve.

For Erigon-1, the staged `--bounded-view` option additionally requires the
completed Erigon-2 H conversion, both original-binary verifier passes, H
restoration with BAL retention, and two successful worker opens. Capture that
worker's qualification result, conversion result and four phase records in
`/data/pbt-1/worker-head-review/qualified-erigon-2.json` as `proof`, `conversion`
and `phases`; this evidence does not exist yet. It qualifies reuse of the
converter, not Erigon-1 itself. Erigon-1 still runs its own complete preparation
and two opens under its assigned 32-GiB worker limit.

An independent read-only comparison on Erigon-1 verified all 66 accounts and
3,489,808 storage records against its own 1,024 retained fragments per domain.
It checked unchanged file identities; no files moved. The optimized driver
rechecks those identities after unsqueezing, preserves the six merged files
outside the domain directory, and uses the candidate only for v3 conversion.
Verification and restoration use the original pinned binary. Per-phase and
completion evidence record both binary checksums and patch provenance.
Eight preserved-head/handoff tests passed. The live worker preflight refused
the active exporter; the candidate check separately refused the missing peer
qualification. No H conversion is queued on Erigon-1. See
`files/erigon-1-head-conversion-plan.json`.

The optional `erigon-v3-bounded-view.patch` is a separately built conversion
optimization against the pinned Erigon revision, not an updated worker pin.
`erigon-bounded-view-fixture_test.go` checks boundary and private-view behavior;
`erigon-v3-record-equivalence_test.go` compares all logical output records from
the original and candidate converters on the same deterministic fixture.
Apply them through Go overlays in an isolated test/build directory. Keep the
running binaries unchanged until a separate deployment decision with candidate
provenance and independent original-verifier checks. The current review and
binary checksum are in `ansible/inventories/pbt-1/files/erigon-bounded-view-review.json`.
The reviewed handoff was performed on Erigon-2 at 20:39 UTC using
`resume-erigon-bounded-conversion.py`. Its original first-shard work was
interrupted deliberately and its evidence retained. The candidate performs only
v3 conversion; the original binaries perform verification and restoration.
Qualification and publication preserve and compare this converter provenance.
The handoff script is single-use and must not be used as a generic restart tool.

`export-erigon-anchor.py` is the separate shared-artifact handoff on Erigon-1.
Without arguments it checks readiness without starting a process or creating
output. After reviewed, stopped preparation at N=24,453,558, `--run` invokes
the pinned native `erigon snapshots export-pbt`, validates exact anchor metadata,
then invokes `erigon snapshots verify-pbt`. It rejects existing attempts and
records checksums only after successful verification and unchanged file
identities. It does not upload, establish shadowfork finality or qualify the
other clients' importers. See `test_export_anchor.py` and the dated instruction
audit for the commands and acceptance checks.

`handoff-erigon-anchor.py` checks the stopped older exporter and the reviewed
N driver. Its default mode is read-only. The queued `--wait` mode waits up to
24 hours for successful conversion and two native opens, revalidates their
proofs and the retained replay prefix, archives the preparation-created review
hold, and runs the N reconstruction once. A failed predecessor or mismatched
proof stops the handoff. This starts only isolated offline preparation; it
does not launch consensus or choose genesis/PBT activation times.

`erigon_verified_restore.py` is an optional faster H preparation path for
Erigon-1 after Erigon-2's verified H archive has been published. Its default is
a read-only check. A controller must first populate the private
`/data/pbt-1/v3-head-restore/release-bundle.json` with the published metadata and
integrity record, Erigon-2's qualification/conversion/phase proofs, object key
and ETag, and a conservative measured unpacked-size bound from the stopped
source. The bundle must prove full remote checksum readback and exact H.
The download URL goes separately in the private `source-url` file.

Use the controller's `prepare-erigon-release-restore.py` for that handoff.
Without arguments it only checks the published release and stopped source;
`--stage` writes the validated bundle and a scoped GET URL to Erigon-1. It
measures the source while holding its existing qualification/conversion locks,
uses the publisher's archive exclusions, and adds a conservative allocation
allowance. It requires the current source proof to equal the published proof.
It does not queue a service. Load the existing private storage environment on
the controller; account credentials are never copied to the worker.

Only after reviewing space and completed exporter work, run `--run --stream`
in the `pbt-1-v3-head-restore` unit. This is the preferred path: ETag-bound
ranges feed a fresh extraction while computing the entire compressed archive's
SHA-256. Successful extraction and the exact published checksum are both
required before promotion. It needs the measured unpacked-size bound plus a
150 GB reserve, without keeping another compressed archive on the root disk.
The original recovery-volume archive remains intact throughout. Run the
read-only `--stream` preflight first; inspect a failed check before starting.

The alternative `--run` without `--stream` caches the compressed archive first
and needs that additional space. Its scoped local-cache downloader cannot
extract or replace a database. Both paths extract under `erigon-v3-restored`, keep
the original directory as `erigon-original-h-preserved`, and promote the fresh
directory. It never deletes the old directory or the original recovery archive.
An interrupted attempt requires inspection rather than an automatic retry.

The new files are staged as `erigon_verified_restore.py`,
`fetch-verified-erigon-release.py` and `qualify-restored-worker.py` on Erigon-1;
the existing conversion helpers and running worker programs remain unchanged.
After the restore unit finishes successfully, invoke the staged qualifier with
`/data/pbt-1/qualification/job.json --from-verified-release`. It validates the
release and promoted directory identities, then performs the worker's own
32 GiB / 8 CPU two-open checks. Results record
`preparation_path=restored_verified_H_release` and
`local_v3_conversion_performed=false`. Tests cover HTTP/checksum failures,
partial extraction, failed promotion, preservation, source-verifier failures,
directory substitution and worker identity/resource limits. This route is
staged only; no restore is queued while the source release is incomplete.
