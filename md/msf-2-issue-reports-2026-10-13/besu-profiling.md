# Besu profiling on msf-2

All six Besu execution nodes capture OOM heap dumps, GC/safepoint logs and bounded default JFR recordings. The heap remains 16 GiB and the image remains Besu 26.9.0. Beacon and validator container identities were preserved.

## Deployment

The dedicated Ansible playbook reads each existing execution container's bootstrap argument before applying the standard execution role. It runs serially, waits for an execution-valid head, writes a real JFR checkpoint, observes health and checks again. Initial deployment additionally compared head roots and finality with a reference node and held during Lighthouse's delayed recovery.

```bash
cd ansible
ANSIBLE_STRATEGY=linear ansible-playbook \
  -i inventories/msf-2/inventory.ini besu-profiling.yaml
```

Use `--limit nimbus-besu-1` for a canary. The regular node playbook installs the profiling prerequisites before Besu starts and enables the timer afterwards.

## Artifacts and retention

The host directory `/data/besu-profiling` is mode 0700. Each start creates `runs/<UTC timestamp>-<UUID>/` with `heap.hprof`, rotating `gc-*.log`, JFR repository chunks and `checkpoints/`. A unique directory prevents filename collisions when the container JVM PID repeats.

- The continuous recording is named `besu`, uses `default` settings, and retains a 30-minute / 256 MiB window, subject to JFR chunk boundaries.
- The timer triggers every five minutes. Each checkpoint contains up to five minutes / 64 MiB, with metadata recording UTC time, image ID, container start time and consensus sync state.
- The collector retains 24 ordinary checkpoints across runs. Runs containing `heap.hprof` are exempt so incident evidence survives; archive them privately and monitor disk consumption. The free-space reserve is 40 GiB. GC logs rotate at ten 50 MiB files **per run**, rather than a global disk cap.
- Besu's launcher starts an unnamed default JFR recording. Once the dedicated recording is verified, the collector stops only that redundant startup recording. Other operator-named recordings are preserved.

Raw heap dumps and recordings can contain authentication material. Keep them private. Public reports contain sanitized allocation aggregates and recording counts; no raw live HPROF or JFR file was uploaded.

## Check and capture

On a Besu host:

```bash
sudo systemctl status besu-profiling.timer
sudo journalctl -u besu-profiling.service --since '30 minutes ago'
sudo cat /data/besu-profiling/status.json
sudo systemctl start besu-profiling.service
```

The shipped image contains `jcmd` and `jfr`. The collector discovers the Java PID from `/proc`; it does not depend on `jcmd -l` finding the JVM. Read `active-run` for the current directory. `jfr summary` verifies event counts; `jfr assemble` can recover surviving repository chunks after abrupt exit. The private OOM test did not produce a complete `dumponexit` recording.

For richer short recording, start a separately named `profile` session with `jcmd <pid> JFR.start settings=profile duration=5m filename=<private mounted path>`. Use it on one node first and correlate its time range with Engine payload hashes, workload inputs, heap/GC metrics and proposal/import logs. A full live heap dump can pause the node; no healthy-node heap dump was forced during deployment.

## Analysis and limits

Use Eclipse MAT privately to inspect retained sizes and GC roots in an OOM dump. Compare with JFR allocation stacks to distinguish a retained object graph from high transient allocation traffic. Replay the relevant workload privately to compare parallel import, proposal construction and prefetch, with one variable changed at a time.

The first sanitized live checkpoint contains 27,249 allocation samples. Transaction-announcement work accounts for about 29.1% of sampled allocation weight and RocksDB reads about 9.9%, grouped by the first Besu frame. These are allocation estimates under the current workload and txpool configuration, **not retained heap or proof of the earlier OOM cause**.

[Rollout verification](evidence/besu-profiling-rollout.json) records each node's health, one running recording, heap flags, timer state and event counts. [The private pipeline test](evidence/besu-profiling-pipeline-test.json) verifies OOM capture, private file permissions and distinct restart directories on a synthetic JVM fixture in the exact image; it is not an Ethereum workload reproducer.

References: [JVM recording options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html), [JFR diagnostic commands](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html), [Eclipse MAT](https://eclipse.dev/mat/).
