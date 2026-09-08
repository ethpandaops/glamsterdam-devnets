# Progressive delivery for Ethereum client images

## Status

Design proposal. The shared platform pieces described here do not exist yet, so
this repository does not enable automatic client updates. Until they do,
execution, beacon, and validator images remain explicit Ansible operations.

The node-side updater is the maintained
[Nicholas Fedor Watchtower fork](https://github.com/nicholas-fedor/watchtower),
which is already deployed by `ethpandaops.general`. The design deliberately
keeps its best property: install it once and let it pull and replace containers
locally without SSH or an Ansible run for every release.

## Decision

Keep Watchtower as the node-local actuator. Add rollout safety by controlling
which immutable digest each node is allowed to see, rather than replacing
Watchtower with a remote deployment agent.

Each managed container follows a deterministic, per-node **release channel**
in a dedicated rollout registry namespace. For example:

```text
registry.example/rollouts/grandine:devnet-8-grandine-geth-1
```

The channel is a normal OCI tag, but only the delivery controller may move it.
The existing builder continues to publish its floating branch tag and
commit-qualified tag. Every six hours, the controller resolves a completed
commit-qualified image to an immutable registry digest, advances the canary's
channel to it, and waits. Watchtower sees an ordinary tag update, pulls it, and
restarts the local container exactly as it does today. The controller advances
the next node's channel only after the previous node is healthy.

This gives a small Netflix-style control plane without putting Spinnaker or a
custom state machine on every server:

| Concern | Owner |
| --- | --- |
| Build and immutable source digest | `eth-client-docker-image-builder` |
| Local pull and container replacement | Nicholas Fedor Watchtower |
| Per-node release channel | rollout registry namespace |
| Durable orchestration and audit | Argo Workflows, deployed by Argo CD |
| Canonical-chain and client readiness | Assertoor |
| Canary/control comparison | VictoriaMetrics |
| Deployment and one-time configuration | `ethpandaops.general` |
| Network-specific policy | devnet inventory |

Here, "Argo" means **Argo Workflows**, not Argo CD. Both are Kubernetes-native,
but have different jobs. Argo CD already deploys the platform's Argo Workflows
Helm release and would deploy this WorkflowTemplate. Argo Workflows runs the
durable steps as pods. Those pods call the registry, Assertoor, and
VictoriaMetrics APIs; the Ethereum nodes do not become Kubernetes workloads.
Argo Workflows never logs in to a node, runs Ansible, or receives access to
Docker. Its only mutation is copying an already-built digest to a
release-channel tag.

## Why a channel per node

A shared `canary`, `10-percent`, or `stable` tag is simpler initially, but
every Watchtower following that tag may update before the controller can stop
the wave. A deterministic tag per node lets the controller advance one node at
a time, construct any compatibility ring, enforce an availability budget, and
abort immediately. The tags are generated from inventory and require no
operator maintenance.

This is control-plane state, not a second source of configuration. Inventory
still decides which client a host runs. A channel records only the accepted
digest for that host and component.

## One-time setup and steady-state operation

Opting a network in should remain one normal stack deployment:

1. The platform reconciler derives component/host channels from rendered
   inventory and seeds each new channel with the network's currently accepted
   digest.
2. The Ansible collection changes managed client image references from direct
   trunk tags to those deterministic channels, includes the client containers
   in Watchtower's allowlist, and configures the existing 15-minute scan.
3. The collection exposes only Watchtower's read-only `containers` endpoint on
   the operations network, with authentication and TLS. It does not enable the
   `update` endpoint or expose the Docker socket. The Nicholas Fedor fork's
   `/v1/containers/details` response includes both image ID and registry
   manifest digest, so the controller can verify what actually started.
4. Assertoor and the existing metrics pipeline provide application and network
   health. No second node agent is installed.

After bootstrap there are no per-release playbooks, SSH sessions, inventory
commits, or manual commands. If Argo Workflows, Assertoor, or the metrics
backend is down, the channel tags do not move; Watchtower keeps running but
finds no new client digest. Failure is therefore closed and existing nodes
remain stable.

Watchtower may scan every 15 minutes without creating churn. A scan only
restarts a client when its release-channel digest changes. The controller
enforces both a six-hour intake interval and a six-hour per-host quiet period;
hourly trunk builds are coalesced and do not reach nodes directly.

## Minimal network policy

Hosts and EL/CL pairings come from rendered inventory rather than being copied
into rollout configuration. A network supplies only policy and exceptions:

```yaml
ethereum_client_delivery:
  enabled: true
  intake_interval: 6h
  minimum_candidate_age: 15m
  observation_epochs: 2
  max_unavailable_nodes: 1
  clients:
    grandine:
      builder_image: registry-1.docker.io/ethpandaops/grandine:develop
    erigon:
      builder_image: registry-1.docker.io/ethpandaops/erigon:main
    ethrex:
      builder_image: registry-1.docker.io/ethpandaops/ethrex:main
    prysm:
      enabled: false
      reason: failed NFT devnet
```

The shared schema provides safe defaults. Optional overrides select or exclude
canaries, special-purpose hosts, maintenance windows, and rollback-unsafe
releases. Enabling another devnet must not involve copying scripts, timers, or
PromQL.

## Builder contract

This design consumes the current
[`eth-client-docker-image-builder`](https://github.com/ethpandaops/eth-client-docker-image-builder)
model rather than inventing a second build pipeline:

- `branches.yaml` is the source catalog and `generate_config.py` expands it into
  concrete source repository/ref and target repository/tag combinations. It
  already expands Prysm and Nimbus into separate beacon and validator images.
- The scheduled workflow runs at minute 45 of every hour, resolves the upstream
  branch head, and builds only when `<branch-tag>-<7-char-commit>` is absent.
  Thus it checks hourly; it does not rebuild an unchanged commit every hour.
- Each architecture is first published under
  `<branch-tag>-linux-{amd64,arm64}` and a commit-qualified variant. The manifest
  action then publishes the multi-architecture floating branch tag and
  `<branch-tag>-<7-char-commit>`.
- Standard builds add source/ref/commit labels. Custom build scripts are not
  guaranteed to add them. Docker Hub is currently authoritative; the Harbor
  copy is explicitly best-effort.

The current output is close, but it is not yet a safe release-candidate
contract. Before automatic rollout, make these narrow builder changes:

1. Assemble the top-level manifest from the **commit-qualified per-platform
   tags**, not the moving per-platform branch tags. This prevents a concurrent
   build from producing a mixed-commit index.
2. Require every platform from `platforms.yaml`. The current manifest action
   skips a missing platform and succeeds if any image remains; that is fine for
   best-effort publishing but not for promotion.
3. Add OCI index annotations for the full source SHA, source repository/ref,
   GitHub run ID, and build time. This gives custom-script images the same
   provenance as standard builds.
4. Expose the final index digest as an action/job output. Keep the existing
   commit-qualified tag for discovery, but treat the resolved digest—not the
   tag—as the candidate identity.
5. Mark related outputs such as Prysm beacon and validator as one release set
   and publish it only after every component manifest succeeds at the same full
   source SHA.

No new build service or candidate webhook is required. The six-hour intake can
read the builder catalog, list completed commit-qualified tags, validate their
annotations and required platforms, and freeze the newest eligible digest. A
future webhook may reduce latency, but it must not become correctness-critical.

## Artifact and promotion flow

1. The builder's hourly check publishes per-platform images and finally the
   branch plus commit-qualified multi-architecture tags.
2. Six-hour intake chooses the newest commit-qualified release set older than
   `minimum_candidate_age`, verifies all required components/platforms, and
   resolves every tag to a digest. A missing or failed build is skipped without
   affecting running nodes.
3. The workflow freezes those digests and full source SHA for the entire
   rollout. A newer build waits for the next intake.
4. Promotion copies `builder-image@sha256:...` to one host's release-channel
   tag. There is no rebuild and no floating branch tag is resolved again.
5. Watchtower observes the moved tag during its next local scan, pulls it, and
   replaces the selected container.
6. The controller requires the read-only Watchtower endpoint to report the
   expected manifest digest, then evaluates Assertoor and VictoriaMetrics.
7. On success it advances the next channel. On failure it stops and moves every
   touched channel back to its journaled prior digest in reverse order.

The rollout registry namespace and its write credential are dedicated to
promotion. Builders can publish candidates but cannot advance channels;
Watchtower has pull-only access; operators do not move channel tags manually.
Every tag mutation records actor, workflow, old digest, new digest, and source
commit.

## Rollout algorithm

### Preflight

- Acquire one mutex for the network and component release.
- Reconcile inventory, release channels, Assertoor identities, and telemetry.
- Verify all target architectures and resolve the candidate to one immutable
  digest.
- Require the network to be finalizing and all prospective canary/control nodes
  to be synced, canonical, and recently observed.
- Reject an active incident, planned fork test, maintenance blackout, unknown
  channel mutation, or unavailable rollback digest.
- Select a canary and equivalent control with the same counterpart client,
  provider, machine class, configuration, and validator role.
- Observe a completed Watchtower scan before moving coupled tags, leaving a full
  scan interval to publish them before the next local update session.

### Canary

- Move only the canary host's channel to the candidate digest.
- Wait for Watchtower to report that exact digest and a new running container.
- Wait for Docker readiness and Assertoor to return the EL/CL pair to the
  canonical ready set.
- Compare it with the unchanged control for at least two finalized epochs after
  warm-up.
- Hard-fail on a restart loop, OOM, wrong chain/digest, Engine API failure, sync
  regression, canonical divergence, missed critical duties, or stopped
  finality. Treat missing or stale telemetry as failure, never as a pass.
- Use a small relative metric set for judgment: process restarts, head distance,
  peer count, CPU throttling, memory growth, RPC errors, and comparable
  validator duty success.

### Compatibility and fleet

Advance one healthy node for every distinct counterpart client before the
general fleet. Keep bootnodes, buildoors, blobbers, and supernodes in explicit
rings or exclusions. Each node must report the exact digest and rejoin the
canonical set before another channel moves.

Then advance remaining nodes in availability-budgeted waves. Per-node channels
allow the workflow to stop between any two hosts; concurrency may later rise
from evidence, but never above `max_unavailable_nodes` or update both members of
an equivalent pair together. Respect the six-hour per-host quiet period and,
where practical, avoid validator proposer duties.

### Commit or rollback

After the observation window, record the digest/source commit as accepted and
emit deployment metrics and a notification. A rejected digest is quarantined
and is not retried automatically.

On failure, stop all promotion and point touched channels at their previous
digests. Watchtower performs rollback on its next scan and the same exact-image,
readiness, and finality checks prove recovery. Emergency rollback is the only
operation allowed to break the six-hour quiet period.

## Important failure semantics

- **Controller outage:** tags stay unchanged and Watchtower performs no client
  restart. Argo resumes the journaled workflow when available.
- **Watchtower outage:** the digest gate times out before another channel moves.
  Alert and repair that host through normal stack operations.
- **Registry outage before promotion:** do nothing. A pull failure is
  non-disruptive and promotion pauses.
- **Registry outage after a bad canary starts:** the availability budget keeps
  the failure to that canary. Its previous image remains local because cleanup
  is disabled, but Watchtower cannot switch tags while the registry is down;
  page rather than risk more nodes and roll back when the registry recovers.
- **Node dies after its tag moves:** do not advance another host. On recovery,
  Watchtower converges to the channel's journaled digest.
- **Manual or competing tag mutation:** dedicated credentials and post-write
  digest verification turn this into a fatal rollout error.
- **New or rebuilt host:** seed its deterministic channel with the accepted
  digest before Ansible starts the client. Refuse bootstrap if the channel is
  missing.
- **Canary/control drift:** abort when the pair differs outside the selected
  component. Rotate canaries over time so one host does not absorb every
  disruptive update.
- **Pre-existing unhealthy node:** defer it; never update it as an attempted
  repair or use it as a control.
- **Small cohort or no equivalent control:** run the hard gates, then require
  manual judgment instead of manufacturing a statistically meaningless score.
- **Coupled beacon and validator images:** promote both per-host tags immediately
  after an observed scan and treat them as one candidate. Watchtower replaces
  them in the next session. If a client cannot tolerate the brief sequential
  replacement, mark that release manual until the updater supports an atomic
  bundle; do not claim tag updates are transactional across repositories.
- **Rollback-unsafe migration:** require a fresh canary volume or a manual gate.
  Automation must not promise rollback across an irreversible schema change.
- **Planned non-finality:** an incident/maintenance lock suppresses intake and
  pauses a workflow at a safe boundary.

## Shared implementation work

Implement this as stack capabilities, not devnet-8 code:

1. `eth-client-docker-image-builder`: make the existing commit-qualified output
   the reliable boundary described above: commit-specific manifest inputs,
   complete platform checks, full-SHA OCI annotations, digest output, and
   release-set metadata. Do not add another builder or require a webhook.
2. `ethpandaops.general`: derive deterministic channel references, seed-before-
   start validation, configure the correct Watchtower fork and client allowlist,
   disable old-image cleanup, and expose only its authenticated read-only
   container-details endpoint on the operations network.
3. Platform: use the already-deployed Argo Workflows instance. Deploy the
   WorkflowTemplate through Argo CD and add the registry promotion/journal
   helper, builder-catalog and inventory reconciliation, VictoriaMetrics
   analysis template, mutex, dashboard, alerts, and suspend/abort/retry
   controls.
4. Devnet templates: add the small policy schema above and checks that reject a
   direct trunk reference when progressive delivery is enabled.

Devnet-8 is the first consumer after those shared changes are reviewed. This PR
keeps client containers out of Watchtower until the channels and safety gates
exist; turning direct trunk Watchtower updates back on now would bypass the
entire design.

## References

- [Nicholas Fedor Watchtower container details API](https://github.com/nicholas-fedor/watchtower/tree/main/docs/http-api/endpoints/container-details)
- [eth-client-docker-image-builder scheduled workflow](https://github.com/ethpandaops/eth-client-docker-image-builder/blob/master/.github/workflows/scheduled.yml)
- [eth-client-docker-image-builder manifest action](https://github.com/ethpandaops/eth-client-docker-image-builder/blob/master/.github/actions/manifest/action.yml)
- [Spinnaker canary overview](https://spinnaker.io/docs/guides/user/canary/canary-overview/)
- [Spinnaker canary best practices](https://spinnaker.io/docs/guides/user/canary/best-practices/)
