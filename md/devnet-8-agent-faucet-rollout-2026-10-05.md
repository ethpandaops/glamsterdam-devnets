# Devnet-8 agent faucet rollout — 2026-10-05

## Changes

- [Faucet PR #1](https://github.com/qu0b/PoWFaucet/pull/1): exact partial payouts, claim-time limit checks, per-session REST throttling, nonce replay prevention and conservative balances across available RPCs.
- [Panda PR #364](https://github.com/ethpandaops/panda/pull/364): bounded asynchronous claims, duplicate recovery, receipt tracking, CLI funding and local wallet generation, timeout termination and recovery documentation.
- [Devnet PR #88](https://github.com/ethpandaops/glamsterdam-devnets/pull/88): 100 ETH claim/wallet/history limits, 20 ETH share rewards and persistent session storage.

The agent faucet runs `ghcr.io/qu0b/powfaucet:v2.5.0-agent.6`, pinned to
`sha256:0b92c3b8853d445f697979db7465c3ea33d7945a14ba003be2152b2fee34fded`.
The [image build](https://github.com/qu0b/PoWFaucet/actions/runs/37328251365)
published amd64 and arm64 images from merged commit
`6a97107bdeae2f712eaf5d6676a2416acdc21b75`.

The local Panda CLI/server run the tested PR build
`0.39.0-faucet-devnet8`, with sandbox image
`ethpandaops/panda:sandbox-faucet-devnet8`. This is a local build; a new stable
Panda release was not published as part of the devnet rollout.

## Storage migration

The old pod used `emptyDir`, which would discard quota history on replacement.
Created a retained 5 GiB PVC, `powfaucet-agents-data`, before changing the pod.
Paused the faucet process, copied its complete SQLite state, checked integrity,
and verified identical source/destination SHA-256 checksums:
`a10f234bd5966c139d4440b36a33a9ea0f0522b830cdba985eb6e6fe4897f9fa`.
All 30 historical sessions survived the migration: 21 finished and 9 failed.

GitOps briefly reapplied a cached older revision during the switch. Verification
waited for the actual pod image, PVC mount and StatefulSet revisions to match
the merged configuration before starting claims. The final pod is ready on the
pinned image, with no container restarts. The browser faucet is a separate
deployment.

After the manual checks the database remained valid and contained 34 sessions:
24 finished, 9 failed and 1 claimable. The claimable session is the rejected
wallet-ceiling probe's earned reward; it was not paid. No running or claiming
sessions remained. Preserve the PVC and database during any rollback.

## Manual verification

All successful transactions below have `status: 0x1` receipts, queried through
the network's `lb` execution endpoint.

| Check | Result | Transaction / block |
| --- | --- | --- |
| Fresh exact 100 ETH | Address balance exactly `100000000000000000000` wei | [0x4e8ecded…](https://dora.glamsterdam-devnet-8.ethpandaops.io/tx/0x4e8ecdedee1a5bddfefe37ef4a0a078135523aa9644be05b20629bc6b459edac), block 329496 |
| Default minimum | Exactly 1 ETH | [0x7fc75bd6…](https://dora.glamsterdam-devnet-8.ethpandaops.io/tx/0x7fc75bd68d1e50cc91cc4f626f4b5376c510b18ce0c24ad064428194e4aaf28a), block 329493 |
| Exact top-up | 99 ETH added to the 1 ETH wallet; balance verified at exactly 100 ETH | [0x301dcf7e…](https://dora.glamsterdam-devnet-8.ethpandaops.io/tx/0x301dcf7e8418a2351707c76057f6687bbd4d34805a1597e0616504ec5cee2c2c), block 329500 |
| Duplicate recovery | Repeated 100 ETH start returned the original job ID and hash | Job `b39bfbb0-9665-4a44-97a3-102a6f601235` |
| Timed out CLI wait | Forced a 1 ms wait timeout; recovered the still-mining 99 ETH job and waited for its receipt | Job `6c468e97-94a8-4b1f-84cc-1d209d3f2485` |
| History quota after spending | After the top-up wallet sent 99 ETH elsewhere, another claim was rejected: “already requested 100 ETH in the last 1d” | Job `c447ebe0-b5cc-42ea-bb01-a165bf7a4825` |
| Wallet ceiling | A 99 ETH recipient requested 2 ETH; claim rejected immediately with `BALANCE_LIMIT`, without payment | Job `7101b028-3bf4-4440-91f8-952217183561` |
| Authentication | Direct unauthenticated access to agent faucet config returned HTTP 401 | Ingress auth remains active |

The funded address is `0xd25C816b38666C84965d135D3CC5a34F44a2Cc42`.
Its 100 ETH claim started at 15:16:11 UTC and was included in a block timestamped
15:17:00 UTC. Its balance remained exactly 100 ETH after all checks.
The key is saved locally, outside this repository, in a mode-0600 wallet file;
no private keys or decrypted configuration are included in this record.

The top-up recipient was
`0x2E5d41e7C42BBbB75E8debeF9A6BA1AB66F96458`. Its subsequent 99 ETH
transfer to `0x194da0E5Aa7585A23c541fA1639483F7178f2267` has receipt
[0xfed2de8c…](https://dora.glamsterdam-devnet-8.ethpandaops.io/tx/0xfed2de8cb2bedce0330fddd9086dffb93c1944582e59caf0258fd1b727fb505d),
block 329504. The recipient stayed at exactly 99 ETH after the rejected probe.

## Funding algorithm and limits

Panda opens a PoW session for the saved address and mines Argon2id shares in
the local server. Difficulty remains 8. Each valid share earns 20 ETH; an exact
100 ETH claim needs five shares. The client closes the session and requests
the exact decimal wei payout, so a minimum claim can receive 1 ETH despite
earning a 20 ETH share. The faucet checks payout limits before submission.
Panda distinguishes submission from a successful on-chain receipt.

- Minimum payout: 1 ETH; maximum per claim: 100 ETH.
- Wallet guard: current checked balance plus requested payout must not exceed 100 ETH.
- History guard: 100 ETH over the configured 24-hour session-history window, checked at session start and again at claim time. The database filters by session **start** timestamp and includes claimable, claiming and finished rewards. This is not a separate quota measured from transaction inclusion time.
- Address concurrency: one active session per wallet. PoW REST throttling is 10 requests per 10 seconds per validated session, avoiding interference through a shared proxy IP.
- Proxy session creation has a separate authenticated-user quota; its code default is 30 starts per hour. There is no per-user ETH allowance across multiple recipient addresses, and the global faucet-outflow module is disabled.

## Timeout and recovery checks

Execution defaults to 60 seconds, with CLI/MCP support up to 600 seconds.
`evm.faucet_start` returns a job immediately; `evm.faucet_status` reads its
mining/submitted/confirmed/failed state and available session/hash. Jobs own a
12-minute server lifetime and recover repeated requests for one hour after
background work ends. The registry bounds work to eight active jobs, 256
retained jobs and 1,024 recovery keys.

Jobs survive execution timeouts and HTTP disconnects. Server shutdown cancels
work, and the job registry is in memory: after restart or expiry, check the
original address balance and receipt before another claim. Faucet session
history on the PVC is independent of this local job registry.

Tests cover disconnects, duplicate requests, shutdown, resource bounds, delayed
receipts and recovery after background expiry. Actual Docker integration tests
also verified that timed out/disconnected Python processes and their children
stop, the session remains usable, and failed cleanup after success preserves
the session:

```bash
PANDA_TEST_DOCKER_IMAGE=ethpandaops/panda:sandbox-faucet-devnet8 go test -count=1 -race ./pkg/sandbox -run TestDockerSessionExecutionTerminates -v
```

Passed on the final commit at 15:40–15:41 UTC, in 16.5 seconds. The fixture
creates its failure marker inside the running script, after the runner's
cancellation check. A review comment interpreting it as pre-created was
resolved using this execution evidence.

Local CLI wallet generation was independently checked with `eth_account`:
address derivation matched, file permissions were private, and the command
printed only the address and path. Existing wallet files cannot be overwritten.

Final Panda CI is green, including all nine smoke cases:
[smoke run](https://github.com/ethpandaops/panda/actions/runs/37334013936).
An earlier storage case failed when its agent chose a new session; its rerun
passed. The faucet smoke case passed. Helm lint and published image builds also
passed.
