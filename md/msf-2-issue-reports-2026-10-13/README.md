# msf-2 client investigations — 13 October 2026

[Public Panda report index](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/56c640/index.html)

**Panda uploads expire 60 days after publication, approximately December 12, 2026.** Complete reports and artifacts are preserved in this directory. No upstream issues or comments were submitted.

| Investigation | Verification | Public report | Evidence |
|---|---|---|---|
| Besu | Live repeat; allocation cause open | [Panda](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/9434dc/01-besu-heap-exhaustion.html) · [Markdown](reports/01-besu-heap-exhaustion.md) | [ZIP](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/5ef401/01-besu-heap-exhaustion-evidence.zip) |
| Teku | Offline restore + portable record reproduction | [Panda](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/066deb/02-teku-persisted-envelope.html) · [Markdown](reports/02-teku-persisted-envelope.md) | [ZIP](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/a204ef/02-teku-persisted-envelope-evidence.zip) |
| Nimbus EL | Private reset/FIN control + syscall trace | [Panda](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/3d9931/03-nimbus-engine-listener.html) · [Markdown](reports/03-nimbus-engine-listener.md) | [ZIP](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/7161cf/03-nimbus-engine-listener-evidence.zip) |
| Erigon / Teku / Lodestar | Live recurrence; controlled reorg replay pending | [Panda](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/137ede/04-teku-optimistic-recovery.html) · [Markdown](reports/04-teku-optimistic-recovery.md) | [ZIP](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/ca7d48/04-teku-optimistic-recovery-evidence.zip) |
| Nimbus CL / Reth | Live duties + source path; private proposal regression pending | [Panda](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/01ae74/05-nimbus-remote-bid-fallback.html) · [Markdown](reports/05-nimbus-remote-bid-fallback.md) | [ZIP](https://panda-uploads-production.devops-539.workers.dev/panda/uploads/3374d4/05-nimbus-remote-bid-fallback-evidence.zip) |

Teku’s failing database also fails under 26.9.1; the relevant reader source is identical in 26.10.0. The portable fixture exercises the actual released metadata reader and includes a passing canonical-envelope control. Nimbus EL’s listener failure reproduces on the deployed image after a queued reset, while a queued FIN and the other RPC listener survive. Besu and Nimbus EL are marked as occurrence follow-ups to existing upstream issues #11248 and #4923.

The other reports distinguish runtime confirmation from unresolved causal paths. Overnight Nimbus–Reth logs contain 75 additional timeouts and six successful proposals; this is not a canonical-duty census. Teku–Erigon logs contain 22 further optimistic activations; these are not 22 measured outage durations.

## Evidence and checks

The original observation window is October 12, 22:24–23:24 UTC, using inventory commit `60a8cf5`. Follow-up queries cover through October 13, 08:30 UTC. Network snapshots, independent probes, pinned release/upstream source revisions, private-test transcripts and public-chain SSZ fixtures are in [evidence](evidence). The full saved database, validator keys, node-key directories and authentication tokens are not uploaded.

Each evidence ZIP includes a SHA-256 manifest. [Public-upload verification](evidence/public-upload-verification.json) confirms unauthenticated HTTP 200, matching archive contents and manifests, and complete matching HTML followed by Panda’s static publication footer. [Browser checks](evidence/browser-verification.json) cover all five reports at a 390 px viewport, without page overflow or relative issue-Markdown links; desktop and mobile Teku screenshots were inspected, and copy fallback was exercised.

The source/evidence commit is `146667c5881c1d1a764fc32c5083d8c451a9404c`. Later publication metadata is in [publication.json](publication.json) and individual URLs are in [uploads.json](uploads.json). Local HTML and ZIP copies are in [artifacts](artifacts).

## Reproducing the portable Teku case

Extract its evidence ZIP and run with Docker and a JDK 25 compiler:

```bash
TEKU_REPRO_JAVAC=/path/to/jdk25/bin/javac bash tests/teku_reproduce.sh .
```

The tested 26.10.0 run reproduces the stored-record mismatch and passes with the independently fetched canonical envelope. The separate full-database restores were performed on disposable, offline containers for both 26.9.1 and 26.10.0. See the Nimbus EL report for the named disposable-container FIN/RST test; no live benchmark client was paused, restarted or reconfigured by these experiments.

## Configuration changes and final operational check

Concurrent commits `2fcb448` (08:25 UTC) and `912a959` (08:37 UTC) raise EL txpool limits and spamoor memory. They were preserved when integrating these report commits. Their repository timestamps alone do not establish exact deployment times or causality; follow-up samples should not be treated as a constant-workload comparison.

The [08:59 all-node snapshot](evidence/final-network.json) caught Lighthouse–Nethermind with EL offline and a 32-slot distance. Its execution container had started at 08:58:30 with the new txpool setting. A subsequent direct check found head distance zero and EL online; an independent authenticated capability probe answered in 13.3 ms. [The follow-up snapshot](evidence/lighthouse-nethermind-followup.json) preserves recovery. No operator intervention was made by this investigation. This is logged as a transient operational observation, not an additional proven client defect.

Both Nimbus EL observers remain optimistic while experimentally snap syncing; the Nimbus–Nimbus EL observer additionally retains its documented Engine listener outage. Neither has validator allocation.

## Rebuilding reports

`build_reports.py` uses Python Markdown and Pillow to create self-contained HTML with a losslessly compressed embedded plot and copyable Markdown whose evidence links are absolute. ZIPs contain curated original evidence and follow-up evidence. The canonical Teku JSON envelope is separate from the portable fixture ZIP to fit the upload gateway limit. Regenerate with:

```bash
python3 build_reports.py 146667c5881c1d1a764fc32c5083d8c451a9404c
```

ZIP metadata timestamps may differ across rebuilds; compare members against their manifests. Publicly uploaded archive bytes are preserved in artifacts.
