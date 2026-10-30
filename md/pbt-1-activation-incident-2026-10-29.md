# PBT-1 activation at S: Geth-1/Geth-3 lost (2026-10-29)

S = `1793264400` (09:00:00 UTC) = slot 50400. Evidence:
`~/.local/state/pbt-1-run/flip/` (`events.log`, `rounds.jsonl`, `pre-S-baseline.json`,
`incident-geth-oom/`). Geth source: CPerezz/go-ethereum `pbt` @ `91b1f422a` (the deployed image),
worktree `~/repos/worktrees/geth-pbt-1-recovery`.

## 24 h after S (2026-10-30 09:00 UTC)

- **The binary trie is canonical and the chain is healthy.** 5,830 blocks since F (24,551,102 →
  24,556,931 `0xa36fbcc9…`); slots 50400–57604 = 7,205, so 1,375 missed (19 %), almost all during the
  outage windows below. Finalized 1798 / justified 1799, advancing one epoch per ~6.4 min.
- **8/9 workers canonical at S+24h** (Besu-1/2, Nethermind-1/2, Geth-1/3, Erigon-1/2); **Geth-2 rejoined at 11:47 on 10-30 → 9/9.** At S+24h Geth-2 was still down (exited; merkle state disposed at 09:19 on 10-29, so the
  merkle-based `--pbt.recover` path does not apply — needs binary-only recovery or a copy from Geth-1/3).
- Finality history: normal 09:00–10:12 → **exactly 2/3 (6/9)** 10:12–11:59 with all Geth down →
  **lost (4/9)** 11:59–12:41 when both Erigon split off → 6/9 from 12:41 (Geth-1/3 recovered, finality
  resumed 13:10) → 7/9 from 15:04 (Erigon-1) → **8/9 from ~17:00** (Erigon-2).
- Client issues found (details below): Geth import flags fatal after S; Geth unclean-stop recovery
  rewinds toward genesis (fixed by the `--pbt.recover` build `local/geth:pbt-9acab9ef9`); Geth heap
  spikes after S (all three OOM-killed at 16/32 GiB; Geth-1/3 now 64 GiB, ~9.4 GiB used); Erigon
  step-boundary compute on the stopped hex domain (cleared by a rollback/re-execute on both Erigons);
  Lighthouse holding a stale `el_offline` for 1–4 min after an EL restart.
- Nethermind moved to `pbt-state` afc0e1f9 at 04:10–04:13 on request; memory 12.0/13.0 GiB of 16/32
  (was 14.5/29.4 before), flat for the last two hours.
- Resources at 09:00: anon Geth-1/3 9.3/9.5 of 64, NM-1/2 12.0/13.0 of 16/32, Besu 6.2/12.1 of 16/32,
  Erigon 14.9/12.6 of 32/16 GiB; free disk ≥ 365 GB everywhere. No restarts since 04:13.
- Uncommitted: this doc, `group_vars/geth.yaml` (`pbt_geth_import_retired`), both Nethermind host_vars
  (afc0e1f9 digest). Monitors: `~/.local/state/pbt-1-run/flip/` (12 s → 60 s rounds) and `watch/` (5 min).

## Transition summary (as of 10:16 UTC; 17:00: 8/9 canonical, only Geth-2 down — see status notes below)

| | |
| --- | --- |
| F (first PBT block) | 24,551,102, slot 50400, ts 1793264400; hash `0xf883dc642fd51c29ab5216542b80e4fa3c31e535c065d424dccd5c36c79b37bc`; stateRoot `0x2b44f899b6c8f20fab8ca1abf7686ade17f379f4251bce80db247e62f0afcaa1`; parent 24,551,101 (ts S-12) |
| Agreement on F | Besu, Erigon, Nethermind at 09:00:00; Geth-1/2/3 at 09:00:12 (still importing at the first round). No hash disagreement at any height since. |
| Blocks since S | 287 in slots 50400–50783; 97 missed (25 %); all 22 checked in 50400–50485 were Geth-1/Geth-3 proposals |
| Finality | 1573 at S, then one epoch every ~6.4 min: 1575 at 09:12:53 (first post-S epoch), 1576 09:19:17, … 1584 at 10:10:42; justified 1585. With all 3 Geth down 6/9 is **exactly** 2/3 (justification needs `3·attesting ≥ 2·total`), so finality still advances (1588 finalized / 1590 justified at 10:49; 1590 / 1592 at 11:02) but any single missed attestation round from the six stalls it. |

Per-client transition (from `debug_migrationProgress`, 12 s rounds):

| Client | Switch-over at S | Migration window closes (epoch 1576 finalized) | Later |
| --- | --- | --- | --- |
| Besu-1/2 | 09:00:00 follower `parked` (cursor F); `PBT migrator retired` | 09:19:17 `phase: done` | healthy; anon 7.9 / 18.4 GiB of 16 / 32 |
| Nethermind-1/2 | 09:00:00 binary `parked` (cursor F-1), merkle follower starts | 09:19:17 `done`; NM-1 anon 15.9 → 13.9 GiB | healthy; anon 13.8 / 29.8 GiB of 16 / 32 |
| Erigon-1/2 | 09:00:00 `flipped: true` | 09:34:24 / 09:35:00 `hex shadow commitment stopped` (`shadowStopped: true`) | healthy; anon 17.5 / 12.7 GiB of 32 / 16 |
| Geth-1 | 09:00:12 `parked` | — OOM 09:02:03 | stopped, merkle not disposed |
| Geth-3 | 09:00:12 `parked` | — OOM 09:04:08 | stopped, merkle not disposed |
| Geth-2 | 09:00:12 `parked` | 09:19:17 `done`, merkle disposed (disk free 641 → 998 GB) | OOM 10:12:34 at 32 GiB; crash-loops on the import guard |

Disk free on the six running workers: 376–1,433 GB. No OOM or restart on any non-Geth EL.
No strong-error log lines (bad block, INVALID, panic, root mismatch) on any client after S.

**Open issues** (details below): Geth Bug 1 (import flags fatal after S), Bug 2 (unclean stop
after S is unrecoverable; repair rewinds to genesis), Geth heap spikes after S (all three Geth
OOM-killed, 16 and 32 GiB). Geth-1/3 keep the merkle state an in-place recovery needs.
**12:00 update:** Erigon-1/2 cannot execute any block that crosses a commitment step boundary
once the hex shadow is stopped (section below). Since 11:59:24 only Besu-1/2 and Nethermind-1/2
(4/9) follow the canonical chain; finality stopped at epoch 1599.

## Outcome

- **Activation succeeded.** First PBT block F = 24,551,102 (slot 50400, ts = S),
  hash `0xf883dc64…b37bc`, stateRoot `0x2b44f899…afcaa1` (= Besu's binary shadow root at F).
  All nine agreed by 09:00:12. Epoch 1575 (first post-S epoch) finalized at ~09:12.
- Per client at S: Erigon `flipped: true`, shadow not stopped; Besu/Nethermind/Geth follower
  `Binary.Phase: parked` (Besu cursor F, Geth/Nethermind cursor F-1); Nethermind starts a Merkle
  follower (`merkle.phase: synced`). Besu logs `Binary-trie column claimed by the chain; PBT migrator retired`.
- Geth block execution went from ~200 ms to 1.6–1.7 s for full (~194 Mgas) blocks after S.
- **Geth-1 OOM 09:02:03, Geth-3 OOM 09:04:08** (16 GiB cgroups; both had sat at 15.7 GiB before S).
  Geth-2 (32 GiB, ~14.5 GiB anon) is running. 7/9 = 77.8 % of stake online; 1 proposal slot
  in 9 now misses.

- **Migration window closed at 09:19:13** when epoch 1576 finalized: Besu, Nethermind and Geth-2
  report `phase: done`; Geth-2 logs `Disposing of the merkle state` and its anon memory dropped
  14.6 → 12.7 GiB; Nethermind-1 15.9 → 13.9 GiB. All 22 missed slots in 50400–50485 were Geth-1 (8)
  and Geth-3 (14) proposals. Geth-1/3 are stopped, so their merkle state is **not** disposed — it
  is the input the in-place recovery (Bug 2) needs; Geth-2 can no longer serve merkle state.

- Erigon-1/2 stop the hex shadow at 09:34:24/09:35:00 (`hex shadow commitment stopped:
  binary-trie activation block is finalized activation=24551102 finalized=24551171`);
  `debug_migrationProgress.shadowStopped` turns true. Expected; heads stay aligned.

## 12:21 — Geth-1/3 restarted with a recovery build (not by this session)

Image `local/geth:pbt-9acab9ef9`, args `--override.genesis=genesis-pbt.json --pbt.recover`,
restart policy `always` (Geth-1 12:21:13, Geth-3 12:21:59). This is the fix for Bug 2:

```
WARN Recovering below the fork on the merkle trie head=24,551,112
INFO Load database journal from file path=/data/geth/triedb/merkle.journal   (stale, discarded)
WARN Head state missing, repairing number=24,551,112
INFO Rewound to block with available state number=24,550,939 hash=c57cd9..94f836
ERROR SetHead invalidated finalized block
```

Both land on 24,550,939 (163 blocks before F) with the binary follower `synced` at the same block
(shadow root `0xae0f4935…`), i.e. the merkle trie Geth-1/3 kept is what made this possible. Their
Lighthouse CLs then range-sync (`distance: 1014 slots`) to feed the missing blocks; Geth must
re-execute 24,550,940 … F-1 on MPT, flip at F, and continue on binary. Watch for the OOM again.

Catch-up, both workers: 24,550,939 → F-1 on MPT in ~3 min; the binary follower then replayed BALs to
F-1 (`activation waits on the shadow tree` until it parked) and reproduced the fleet's shadow root at
F-1 exactly (`0xb9f5a…`). F 24,551,102 `0xf883dc64…` / stateRoot `0x2b44f899…` and 24,551,168
`0xbe70625b…` / `0x49394e92…` match Besu. Post-F import ran at ~100–135 Mgas/s (vs ~700+ on MPT);
Geth-1 stalled briefly on cold-cache disk reads (io.pressure full ≈ 55 %, 7 Mgas/s) and recovered.
Geth-1 memory limit is now 64 GiB (set by whoever recreated it); anon ~7.5 GiB during catch-up.
**Geth-3 reached the head at ~12:39, Geth-1 at ~12:41 → 6/9 on the canonical chain again.**

## Erigon stuck at a commitment step boundary, 11:59:24 — finality lost (4/9 canonical)

Both Erigon workers fail to execute canonical block 24,551,730 `0x01527f1c…f8afa`
(slot 51297, 1,467 txs, proposer 2283 = Nethermind-2) on their own head 24,551,729:

```
[5/5 Execution] commitment compute failed block=24551730 txNum=3374524999
  err="commitmentCalculator: step-boundary compute failed: commitment domain commitment is stopped"
Could not validate block ... engine_newPayloadV5 err=validateAndStorePayload: ...
```

Erigon-1 then built and validated its own 24,551,730 `0xe831cfdb…` (slot 51298, 298 txs,
validator 159), which does not cross the step boundary, and both Erigons continue on that branch
(24,551,731 `0x36a64738…`) while Besu/Nethermind follow `0x01527f1c…` → `0x39d4591d…`. Besu
imported both blocks as valid, so this is an Erigon execution failure, not a root disagreement.
Every retry (unwind to 24,551,729, re-execute) fails identically on both workers.

Cause (from the log): the hex shadow was stopped at 09:34/09:35, but the step-boundary commitment
pass still computes that stopped domain. Any block crossing step 1,079,848 → next fails, on any
branch. Needs an Erigon fix (binary-trie build; image `ethpandaops/erigon@sha256:977277f3…`).
Evidence: `incident-erigon-reorg/erigon-{1,2}.log`. With 3 Geth + 2 Erigon off the canonical
chain only 4/9 = 44 % attest to it: **no finality** after epoch 1599.

**13:05 status.** Both Erigon ELs were restarted in place at 12:53:09 / 12:54:07 (same container,
same image `977277f3…`, not by this monitoring session). The `commitment domain commitment is
stopped` loop is gone, but they remain on their own branch (24,551,800 at 13:05 vs canonical
24,551,894); their Lighthouse CLs are `Synced` with 3 peers, finalized 1600, building on the Erigon
fork. Canonical (Besu-1/2, Nethermind-1/2, Geth-1/3 = 6/9): justified 1603 → 1610 → 1611 after
Geth-1/3 returned; finalized still 1601 at 13:05; **finality resumed at 13:10:10: finalized 1610, justified 1612**
on all six canonical nodes. Erigon needs a reorg back onto canonical (probably a resync or a fixed build).

**14:23 status.** Canonical 6/9 finalizing steadily: finalized 1610 (13:10) → 1619 (14:12) → 1621 /
justified 1623 (14:23), head 24,552,139 on all six. Geth-1/3 (64 GiB, `--pbt.recover` build) at
~8.5 GiB anon, full blocks ~0.6–1.0 s. Besu-2's EL process was restarted in place at 14:15:18 (same
container, no OOM, not this session); back at head within ~20 s; disk free 606 → 828 GB.
Erigon-2 still on its own branch (24,551,862, 2 CL peers). **Erigon-1 now cannot start**:
`torn commitment datadir: commitment is at block 24551169 tx 3374184374, commitment-bin is at block
24548987 tx 3372799999` → `halting process` (2 restarts, last 14:22:40). The binary commitment on disk
is ~2,180 blocks behind the hex one, likely left by the unwind/stopped-domain loop. Evidence:
`incident-erigon-reorg/erigon-1-torn-1422.log`.

**14:42 — Erigon-1 recovered (not by this session).** Restarted 14:42:31 (same container/image) from
24,550,047 (pre-S, below the torn commitment-bin point), re-executing at ~6 blk/s. Verified against
Besu: F 24,551,102 `0xf883dc64…`/`0x2b44f899…`, 24,551,168 `0xbe70625b…`/`0x49394e92…`, and at
**24,551,730 it now executes the canonical `0x01527f1c…` (stateRoot `0x1c1d9d23…`)** — the block it
failed on at 11:59 — and 24,551,803 `0x3ea26297…`/`0x892989fd…`. No `commitment domain ... stopped`,
torn-commitment or halt lines since. Erigon-2 is still on its own branch.

**15:22 status.** 7/9 canonical (Besu-1/2, Nethermind-1/2, Geth-1/3, Erigon-1), head 24,552,348,
finalized 1632 / justified 1633 (consecutive again); 13/64 slots missed (≈ Erigon-2 + Geth-2).
Erigon-1 reached the canonical head at ~15:04. Besu-1 was also restarted in place at 14:30:55 (no OOM,
not this session); after the Besu restarts free disk rose 558 → 773 GB (Besu-1) and 606 → 827 GB
(Besu-2). Anon: Geth-1/3 8.7/9.0 of 64 GiB, NM-1 14.7/16, NM-2 29.0/32, Besu 4.7/10.6, Erigon-1 11.7/32.
Remaining off-chain: Erigon-2 (own branch, 24,551,893, finalized 1600) and Geth-2 (exited, merkle disposed).

**16:16 status.** 7/9 canonical, head 24,552,549, finalized 1641 / justified 1642. No new restarts
or memory highs on the seven (NM-1 14.5/16, NM-2 29.0/32 GiB). Erigon-2 was restarted at 15:37:28
(not this session) and rolled back to 24,550,999 like Erigon-1, but its Lighthouse CL is still on the
Erigon side branch (2 peers, finalized 1600) and keeps sending FCU for side-branch head
`0xfd74b0…`; the EL's backward downloader cannot fetch it from canonical peers
(`could not process backward download request`), so it does not advance. Its CL needs to be moved
back onto the canonical chain (e.g. CL resync / checkpoint sync from a canonical node).
Geth-2 still exited.

**17:00 status — 8/9 canonical.** Erigon-2 is back on the canonical chain (head 24,552,717
`0x69ba113f…`, same as all others; CL 9 peers, finalized 1647; no backward-download failures in the
last 5 min). Finalized 1647 / justified 1648; 14/64 slots missed. No restarts or memory highs on any
running EL (NM-1 14.7/16, NM-2 28.9/32, Geth-1/3 8.7/9.0 of 64, Erigon-2 11.1/16 GiB).
Only Geth-2 remains down (exited; merkle state disposed, so `--pbt.recover` from merkle is not
available to it — needs a binary-only recovery or a resync/copy from Geth-1/3).

**18:00 status — stable at 8/9.** Head 24,552,979 `0x1467d841…` on all eight; finalized 1657 /
justified 1658; 9/64 slots missed (≈ Geth-2's share). No restarts since 15:37. Anon: NM-1 15.2/16
(peak 15.8 at ~17:20), NM-2 29.7/32, Geth-1/3 9.1/8.9 of 64, Erigon-1/2 12.9/32 and 11.7/16,
Besu 5.4/11.3 GiB. Geth-2 still exited on the original image.

**19:00 status — stable at 8/9.** Head 24,553,250 `0xa1768255…` on all eight; finalized 1666 /
justified 1667; 5/64 slots missed. No restarts. Anon: NM-1 15.0/16, NM-2 29.6/32, Erigon-2 12.3/16
(rising ~0.6 GiB/h since 17:00), Erigon-1 13.6/32, Geth-1/3 9.2/9.5 of 64, Besu 5.6/12.2 GiB.
Geth-2 still exited.

**20:00 status — stable at 8/9.** Head 24,553,513 `0xcabb45f7…` on all eight; finalized 1676 /
justified 1677; 7/64 slots missed. No restarts. Anon: NM-1 14.1/16, NM-2 29.3/32, Erigon-2 12.6/16
(growth slowed to ~0.3 GiB/h), Erigon-1 13.8/32, Geth-1/3 9.5/9.2 of 64, Besu 5.7/11.9 GiB.
Geth-2 still exited.

**21:00 status — stable at 8/9.** Head 24,553,763 `0x14abf9ab…`; finalized 1685 / justified 1686;
7/64 missed; no restarts. Anon: NM-1 14.9/16, NM-2 29.8/32, Erigon-2 12.7/16 (flat), Erigon-1 13.5/32,
Geth-1/3 8.9/9.2 of 64, Besu 7.1/11.6 GiB. Geth-2 still exited.

**22:00 status — stable at 8/9.** Head 24,554,037 `0xc925dde7…`; finalized 1694 / justified 1695;
5/64 missed; no restarts. Anon: NM-1 14.6/16, NM-2 29.6/32, Erigon-2 12.7/16 (flat), Erigon-1 13.8/32,
Geth-1/3 8.9/9.7 of 64, Besu 5.8/11.7 GiB. Geth-2 still exited.

**23:00 status — stable at 8/9.** Head 24,554,299 `0xcbe90820…`; finalized 1704 / justified 1705;
10/64 missed; no restarts. Anon: NM-1 14.2/16, NM-2 30.0/32, Erigon-2 12.6/16, Erigon-1 13.2/32,
Geth-1/3 9.5/10.0 of 64, Besu 5.9/15.3 GiB. Geth-2 still exited. (A 22:48 "bad block" alert on Geth-1
was a regex false positive on a hash ending in `…bad` before `blocks=1`; the pattern now needs a
word boundary.)

**10-30 00:00 status — stable at 8/9.** Head 24,554,555 `0x8de6e67a…`; finalized 1713 / justified
1714; 9/64 missed; no restarts. Anon: NM-1 14.5/16, NM-2 29.1/32, Erigon-2 12.6/16, Erigon-1 14.0/32,
Geth-1/3 9.5/9.3 of 64, Besu 5.9/15.5 GiB. Geth-2 still exited.

**01:00 status — stable at 8/9.** Head 24,554,813 `0xef6be844…` (Geth-1/3 one block behind,
still importing — binary import is ~1 s/full block); finalized 1723 / justified 1724; 9/64 missed; no
restarts. Anon: NM-1 14.6/16, NM-2 29.7/32, Erigon-2 12.6/16, Erigon-1 13.4/32, Geth-1/3 9.4/9.3 of 64,
Besu 6.0/11.9 GiB. Geth-2 still exited.

**02:00 status — stable at 8/9.** Head 24,555,080 `0xc6f5a942…` (Geth-1/3 importing it, one behind);
finalized 1732 / justified 1733; 7/64 missed; no restarts. Anon: NM-1 14.4/16, NM-2 29.2/32,
Erigon-2 12.7/16, Erigon-1 13.9/32, Geth-1/3 9.4/9.4 of 64, Besu 6.0/12.0 GiB. Geth-2 still exited.

**03:00 status — stable at 8/9.** Head 24,555,329 `0x463e8adc…` on all eight; finalized 1741 /
justified 1742; 11/64 missed; no restarts. Anon: NM-1 14.6/16, NM-2 29.7/32, Erigon-2 12.6/16,
Erigon-1 13.5/32, Geth-1/3 9.4/10.2 of 64, Besu 6.1/11.8 GiB. Geth-2 still exited.

**04:00 status — stable at 8/9.** Head 24,555,601 `0x80ea147a…` (Geth-1/3 importing it); finalized
1751 / justified 1752; 6/64 missed; no restarts. Anon: NM-1 14.5/16, NM-2 29.4/32, Erigon-2 12.6/16,
Erigon-1 14.0/32, Geth-1/3 9.3/10.2 of 64, Besu 6.1/14.5 GiB. Geth-2 still exited.

**04:10–04:15 — both Nethermind updated to `pbt-state` afc0e1f9 (Nethermind request).** Built with
`panda build nethermind --repo NethermindEth/nethermind --ref afc0e1f9b8a96a6b2058d33d7013175f2277d81c
--tag pbt-1-pbt-state-afc0e1f9` (run 41000659662, success); index digest `sha256:6a570a40…` with revision
label afc0e1f9, pinned in both host_vars (NM-2 was on the group default f4e29519 `60bb6209…`, NM-1 on
merge-ten-lights-cover f609f2fd `c8025812…`). Check-mode diff: image only. Deployed one at a time with
`-t ethereum_node_el`: NM-2 04:10:29 (`PBT migration anchor 24453558 … was imported earlier; reusing it`,
flat state frozen at F-1 24,551,101), NM-1 04:13:12 (`PBT state already populated; skipping the self
import`). Container StopTimeout 300 s, so both stops were clean. Each caught up within ~1.5 min; at
24,555,660 NM-1, NM-2 and Besu-1 agree on `0x19269495…` / stateRoot `0xa21b5632…`. Only socket
(`No route to host`) errors in the EL logs. 7/9 stayed online during each restart.
NM-1 then sat at 24,555,660 for ~4 min (04:14:40–04:18:24): its Lighthouse kept logging `Synced` but held
its head at slot 56166 with `el_offline=true` after an `engine upcheck` 500 during the EL restart
(04:14:24), while the snooper already reached the new Nethermind. At 04:18:24 Lighthouse jumped to slot
56192 and resumed feeding payloads; Nethermind imported them at once (`slot 223,407 ms` = the wait).
A Lighthouse EL-offline recovery delay, not a Nethermind fault; NM-2 showed a ~1 min version of it.

**05:00 status — stable at 8/9.** Head 24,555,865 `0x871d6dde…` (Geth-1/3 importing it); finalized
1760 / justified 1761; 3/64 missed; no restarts since the Nethermind update. Nethermind on pbt-state
afc0e1f9 uses far less memory so far: NM-1 11.3/16 GiB (was 14.5), NM-2 12.0/32 GiB (was 29.4) — partly
fresh caches after restart; watch the trend. Others: Erigon-1/2 15.1/12.6, Geth-1/3 10.1/10.1 of 64,
Besu 6.1/12.0 GiB. Geth-2 still exited.

**06:00 status — stable at 8/9.** Head 24,556,130 `0xca73808c…` (Geth-1/3 importing it); finalized
1770 / justified 1771; 6/64 missed; no restarts. Nethermind on afc0e1f9 grows slowly, ~0.4–0.5 GiB/h:
NM-1 11.6/16 (05:00 11.3), NM-2 12.6/32 (05:00 12.0). Others: Erigon-1/2 15.3/12.7, Geth-1/3 9.5/9.8 of
64, Besu 6.1/12.0 GiB. Geth-2 still exited.

**07:00 status — stable at 8/9.** Head 24,556,400 `0x23e361c0…` on all eight; finalized 1779 /
justified 1780; 6/64 missed; no restarts. Nethermind afc0e1f9: NM-1 12.3/16 (+0.7 GiB/h), NM-2 12.8/32
(+0.2). Others: Erigon-1/2 15.2/12.6, Geth-1/3 9.8/9.6 of 64, Besu 6.2/12.0 GiB. Geth-2 still exited.

**08:00 status — stable at 8/9.** Head 24,556,669 `0x324a86fb…` (Geth-1/3 importing it); finalized
1788 / justified 1789; 4/64 missed; no restarts. Nethermind afc0e1f9 levelled off: NM-1 12.3/16 (flat
since 07:00), NM-2 12.9/32. Others: Erigon-1/2 15.2/12.6, Geth-1/3 9.2/9.7 of 64, Besu 8.5/12.1 GiB.
Geth-2 still exited.

**09:53 — Geth-1 redeployed on `local/geth:pbt-c44a5c12f` (not by this session), clean restart after S.**
Same args (`--override.genesis=genesis-pbt.json --pbt.recover`). `Load database journal from file
path=…/pbt.journal` succeeded (no `unmatched journal`), no `Head state missing`/rewind, head loaded at
24,557,156 and import resumed — the first confirmed clean post-S Geth restart. Geth-3 followed at 09:55:11
on the same image: pbt.journal loaded, head 24,557,163, at the canonical head (24,557,167 `0xd576df12…`)
within ~30 s.

**10:00 status — stable at 8/9.** Head 24,557,189 `0x47bd1a51…` on all eight; finalized 1807 /
justified 1808; 7/64 missed. Restarts only the two Geth redeploys (09:53, 09:55). Anon: Geth-1/3 4.8/3.4
of 64 (fresh after restart), NM-1/2 12.4/12.7, Besu 6.2/16.4, Erigon 15.5/12.7 GiB. Geth-2 still exited
on the original image.

**11:00 status — 8/9 canonical; Geth-2 restarted (not by this session).** Head 24,557,450 `0xadfcaba1…`
on all eight; finalized 1816 / justified 1817; 9/64 missed; no restarts on the eight. Geth-1/3 regrowing
after their 09:53/09:55 restarts (7.2/5.8 GiB of 64); NM-1/2 11.7/12.4, Besu 6.3/12.2, Erigon 17.0/12.7 GiB.
Geth-2 was started at 10:59:19 on `local/geth:pbt-9b5dfd0dc` (64 GiB, `--override.genesis=genesis-pbt.json`,
no `--pbt.recover`): `pbt.journal` loaded, head 24,550,937 `0xf073a2…` (pre-S, below its 10-29 stop at
24,551,374, so it was rolled back), `debug_migrationProgress` `done`. Its Lighthouse is range-syncing
(distance 1,195 slots) and the EL is waiting for payloads. Its merkle state was disposed on 10-29, so
re-executing 24,550,938…F-1 needs whatever this build or a data copy provides — watch whether it crosses F
and matches the canonical hashes.

**11:47 — Geth-2 back at the head: 9/9 canonical** (first time since Geth-1's OOM at 09:02 on 10-29).
On `local/geth:pbt-9b5dfd0dc` from pre-S 24,550,937 with its merkle state disposed: the binary
follower replayed block access lists fetched from peers (`Migration direction stalled … access list
missing` while they arrived), F 24,551,102 matched `0xf883dc64…` / `0x2b44f899…`, then canonical import
ran at ~150–235 blocks/min (one 4-min lull) and reached 24,557,660 at 11:47:10. At 24,557,404 Geth-2,
Geth-1 and Besu-1 agree on `0xf43c8c11…` / stateRoot `0xe1605edd…`; its Lighthouse is synced. Memory
~9.3 GiB of 64. A background follower kept logging `replaying block 24550947 …: missing trie node` for a
while after canonical import had passed F — harmless here, but worth reporting to the Geth devs.

**11:56 — Geth-1 redeployed again on `local/geth:pbt-c9474454d`** (not by this session; now without
`--pbt.recover`). Clean: `pbt.journal` loaded, head 24,557,707, back at the canonical head (24,557,710
`0x65a5a863…`) within ~30 s. Geth-3 followed at 11:57:32 on the same image (pbt.journal loaded, head
24,557,711, clean). Geth images now: Geth-1/3 c9474454d, Geth-2 9b5dfd0dc.

**12:00 status — 9/9 canonical, all producing.** Head 24,557,757 `0xea54c04b…` on all nine; finalized
1827 / justified 1828; **0/64 missed**. Geth-2's process was also restarted in place at 11:18:01 during
its catch-up (container created 10:59:19; not visible at the time because Geth-2 was muted in the events
filter); no `Migration direction stalled` lines in the last 10 min. Anon: Geth-1/2/3 4.3/10.6/4.3 of 64,
NM-1/2 12.2/12.5, Besu 6.3/12.3, Erigon 16.5/12.6 GiB.

**12:20 — Geth-2 redeployed on `local/geth:pbt-fb9925472`** (not by this session). Clean: pbt.journal
loaded, head 24,557,825, at the canonical head (24,557,826 `0x99f2be3f…`) immediately. Geth images now:
Geth-1/3 c9474454d, Geth-2 fb9925472.

**13:27–13:30 — Geth-1/3 moved to `local/geth:pbt-fb9925472`** (Geth request: latest `pbt` before
shutdown). Image copied from Geth-2 (`docker save | docker load`; same commit fb9925472f8b and build
time, the ID differs only between the overlay2 and containerd image stores). Each container was
recreated from its own `docker inspect` with only the image changed (`~/.local/state/pbt-1-run/geth-fb99/`).
The old ones are kept as `execution-c9474454d-old` (restart=no) for rollback. Geth-1: `docker stop -t 300`
exit 0, journal 518 MiB persisted at 24,558,158, reloaded with no rewind; it imported again after about 80 s
(the usual Lighthouse catch-up). Geth-3: journal 292.8 MiB at 24,558,169, reloaded, at the canonical head
in 50 s. **13:31: 9/9 on 24,558,174 `0x8207aa0c…`**, stateRoot `0x1c647dfd…`; all Geth on fb9925472.

**13:00 check (run 13:33) — 9/9 canonical, finalized 1840** (up from 1827 at 12:07). The 2/64 missed slots (58945,
58951) and Geth-3's beacon `CRIT Failed to update execution head` (FCU 500 via snooper) fall within the
Geth-1/3 restart windows. Restarts 0 and no OOMs. Memory: Geth-1/2/3 4.4/7.4/2.6 of 64 GiB (fresh
restarts); NM-1 anon 12.1 GiB of 16, flat (docker stats shows 14.2 GiB with page cache; it hits the cgroup
max but reclaims, oom_kill 0); Besu-1 8.6/16, Erigon-1 23.6/32 GiB.

## Shutdown and final-head snapshots (2026-10-30)

**14:14–14:15 — frozen at a common head.** All nine validators were stopped (restart=no), then two checks
24 s apart showed the same head: **24,558,379 `0x0fb2f11e5cafa964…`, stateRoot `0x9df0d77a295cc903…`**, CL slot
59159. All nine ELs agreed on it. The script that did this is `~/.local/state/pbt-1-run/final-head/freeze.sh`;
its log is `freeze-20261030T141420Z.log`. The CLs were stopped first, then the ELs (`-t 300`): no OOMs. Geth
exited 0 with the journal persisted; Besu exited 143 (SIGTERM); Nethermind exited 130 after "All DBs closed …
is shut down"; Erigon exited 0.

**Prune and compact** (`offline.sh`, one detached container per source node):
- Geth-1: `geth db compact`, started 14:15:47.
- Besu-1: `storage trie-log prune` keeping 512 layers. It had run with `--bonsai-limit-trie-logs-enabled=false`; this freed about 42 GiB.
- Erigon-1: `db compact`. chaindata went from 5.2 to 1.4 GB, migrations from 1.0 GB to 256 KB.
- Nethermind-1: none. There is no offline compaction. `flat` (325 GB, pre-migration state) is kept, and so is `pbt` (377 GB).
- Geth `prune-history` was skipped, keeping the full history.

**Reopen readback** (EL started alone, no CL): Besu-1 and Erigon-1 both serve 24,558,379 with the same hash
and stateRoot after the offline step.

**Uploads** to `ethpandaops-shadowfork-images/pbt-1/20261030-final-head/<client>/24558379/snapshot.tar.zst`:
- Nethermind 1.68 TB, Besu 1.18 TB and Erigon 0.67 TB were streaming from 14:20.
- Geth follows once its compaction and readback are done.
- The archives exclude node keys, logs, txpool/blobpool data and Erigon's `chaindata.sidefork-20261029T1159Z`.

**Geth:**
- `db compact` ran 14:15:47–14:33:49 (exit 0).
- The first readback stopped Geth 2 s after RPC came up, before its signal handler was installed. Geth exited 2 without persisting the journal. No blocks had been processed, and the 14:15 `pbt.journal` was untouched.
- A second readback (45 s settle): reopened at 24,558,379 with no rewind, served state, then stopped clean (exit 0, journal 430 MiB). `reopen.sh` now always settles 45 s.
- The Geth upload started at 14:37.

**Head block:** `_snapshot_eth_getBlockByNumber.json` (full txs, 1,234) was taken from Geth-2, which is not a source. It was started without its CL and stopped cleanly.

**Public CDN** (`shadowfork-images.ethpandaops.io`):
- It serves only `snapshot.tar.zst` and `_snapshot_*` keys; every other key returns 403 (Cloudflare "Attention Required").
- It also 403s Python-urllib's user agent.
- So the genesis is published as `_snapshot_genesis.json` (sha256 `6f4750fb…`). `complete` checks the public URLs with a curl user agent.

**Auto-complete:**
- The user unit `pbt-1-final-complete` (`finish-all.sh`, log `finish-all.log`) runs `complete` as each stream ends.
- `complete` does a multipart complete plus sampled part sha256 checks on R2, publishes the metadata and head block, then verifies the archive's public Content-Length, the first part's sha256 over the CDN, and that both JSON files are readable.
- At 65–69 MB/s per node, with archives about 0.9× raw, the uploads should finish around 17:30 (Erigon) to 21:00 (Nethermind).
- ethereum-node1 was rebooted at 14:45:14 (`sudo systemctl reboot`). The first auto-complete unit was a `systemd-run` transient, so it did not come back; `pbt-1-selfconvert-trials` (also transient) was lost the same way. The VM streams were unaffected.
- 18:46: the Erigon (stream done 16:14) and Besu (18:37) uploads were completed by hand. Since then the unit is a real one (`~/.config/systemd/user/pbt-1-final-complete.service`, enabled) and reads the R2 token from `~/.bashrc` itself.

| Client | Archive | Raw | Ratio | archive sha256 | Published |
|---|---|---|---|---|---|
| Erigon | 496,696,979,735 | 667,726,643,789 | 0.74 | `98e657ba…7526` | 18:47 |
| Besu | 1,110,292,670,367 | 1,184,265,683,481 | 0.94 | `eb57c003…a464` | 18:49 |
| Geth | 1,107,449,574,513 | 1,218,225,794,997 | 0.91 | `6583b4bf…5a92` | 19:00 (unit) |
| Nethermind | 1,533,536,026,987 | 1,679,863,097,220 | 0.91 | `a99c39f8…50ae` | 20:16 (unit) |

All four published by 20:16. A final pass with curl showed each public archive's Content-Length matches, the metadata and head-block files return 200, and the genesis sha256 is still `6f4750fb…`. The unit was then disabled.

## Bug 1 — import flags are fatal after S

Every restart with `--pbt.import.*` exits:
`binary tree import refused: the head block already commits the binary tree` (`core/blockchain.go:462`).
The command sheet's "keep the flags on every later start" is wrong past S for Geth. Fix (uncommitted):
`pbt_geth_import_retired: true` in `ansible/inventories/pbt-1/group_vars/geth.yaml` drops them and
keeps `genesis-pbt.json`. **Necessary but not sufficient** — see Bug 2.

## Bug 2 — unclean stop after S cannot be recovered; repair rewinds to genesis

Restarting Geth-1 without the import flags (09:06:57):

```
Load database journal from file path=/data/geth/triedb/pbt.journal
Failed to load journal, discard it err="unmatched journal want 23e35b0b… got dbafba9e…"
Head state missing, repairing number=24,551,112
Block state missing, rewinding further ... number=23,077,447 (stopped here by us, 09:07:40)
```

- Binary disk-layer root `0x23e35b0b…` = the fleet's shadow root at **block 24,550,675**
  (07:34 UTC, 427 blocks before F; matched in `rounds.jsonl`). The binary state is intact up to
  there; post-S diff layers were in memory only (< 128 blocks, never flushed) and the OOM wrote no
  journal. The stale `pbt.journal` is from an earlier clean stop.
- `NewBlockChain` repairs the head (`blockchain.go:536-575`) **before** it creates the follower
  (`blockchain.go:671`). `HasState` (`blockchain_reader.go:383`) reaches the merkle trie only via
  `bc.follower`, so during repair it sees only the binary `bc.triedb`. Pre-S headers carry MPT roots,
  post-S roots are not on disk, so `rewindPathHead` walks to the snap pivot 22,882,515 and returns
  **genesis** ("Pivot block reached, resetting to genesis") — it would have wiped the chain.
- Geth-1 was stopped mid-search (read-only phase); Geth-3 was never started without the flags.
  Both: container `exited`, restart policy `no`. **Do not run `-t ethereum_node(_el)` on them** —
  it recreates the container and re-enters the rewind.
- Intended recovery the code already supports once the merkle tree is visible: rewind to a block M
  with merkle state, re-execute pre-S blocks on MPT while the follower replays BALs onto the binary
  tree from 24,550,675 to F-1, park, then execute F… on binary (`execParentRoot` reads the shadow
  root). A fix must expose the merkle tree to `HasState`/`StateRecoverable`/`Recover` during repair
  without starting the follower loop (`newBintrieFollower` starts `go f.loop()` immediately, which
  would race `setHead`). For the Geth team (CPerezz); not attempted here.

## Geth-2 OOM 10:12:34 — all three Geth down (6/9 = exactly 2/3; finality continues but has no margin)

Kernel: `Killed process (geth) anon-rss:33296168kB` at the 32 GiB limit. Container memory
(watch, 5 min) was 27–31 GiB until the 09:19 merkle disposal, then 16–19 GiB through 10:09 —
the final ~16 GiB came within ~3 minutes, so it is a spike rather than steady growth. Its last
payload build ended 10:10:12. Geth-1 was killed 3 s after delivering its own payload 24,551,112
(09:01:56–09:02:00). Suggestive, not proven: payload building on the binary tree may allocate a
large transient heap. (The root SSH sessions from 84.242.15.77 are this controller's own watch
probes — 84.242.15.77 is ethereum-node1's public IP — not an outside operator.) Geth-2 then crash-looped on the import guard, which exits
before head repair, so it is safe to leave; **do not restart it without the flags** (Bug 2).
Evidence: `incident-geth-oom/geth-2.log`.

**11:52:29 — Geth-2 recreated without the import flags** (`--override.genesis=genesis-pbt.json`
only, restart policy `no`), not by this monitoring session; the only SSH source is this controller
host. It hit the same repair: `pbt.journal` mismatch (want `215197f0…`), state-history freezer
truncated by 142 items (normal pathdb open), `Head state missing, repairing number=24,551,374`,
`rewinding further` down to 23,725,049, then **stopped at 11:53:03 (exit 2) during the read-only
search** — no `Rewound`/`resetting to genesis` line, so the chain is not truncated. Container is
`exited`. Bug 2 therefore also applies to a worker whose merkle state is already disposed.

## Why the OOMs

Before S the node ran one pathdb (merkle) with the binary shadow follower. Past S execution
commits the follower-owned binary pathdb (`triecache=614MiB statecache=409MiB buffer=256MiB`)
while the merkle handle and its caches are still alive, and blocks take ~8x longer. With
~300 MiB headroom under 16 GiB, both 16 GiB workers died within 4 minutes; the 32 GiB worker has
~17 GiB headroom. This looks like a budget problem, not a leak — keep watching Geth-2's anon trend.

## Recovery options (need remote writes + owner go-ahead)

1. ~~Clone Geth-2 → Geth-1/3~~ — no longer possible: Geth-2 was OOM-killed at 10:12 too.
2. **Geth fix for Bug 2**, then restart Geth-1/3 in place (binary data to 24,550,675 + merkle
   state + BALs are on disk). Geth-2 has disposed of its merkle state, so it needs a binary-only
   recovery path.
4. **Erigon fix** for the stopped-domain step-boundary compute; until then neither Erigon can
   follow the canonical chain. Finality returns only when at least two of Geth/Erigon are back
   (≥ 6/9).
3. Raise Geth limits (and Nethermind-1/2: 15.3/16 and 30.3/32 GiB anon at 09:12) live with
   `docker update --memory`; it needs no restart. Blocked in this session by the permission policy.
