#!/usr/bin/env python3
"""Save bounded JFR windows; preserve directories containing OOM heap dumps."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request


def command(*args):
    return subprocess.check_output(args, text=True, timeout=45).strip()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def checkpoint(root, container, keep, minimum_free):
    if shutil.disk_usage(root).free < minimum_free:
        raise RuntimeError("Profiling filesystem has less than the configured free-space reserve")
    run_id = (root / "active-run").read_text().strip()
    if not re.fullmatch(r"\d{8}T\d{6}Z-[0-9a-f-]{36}", run_id):
        raise RuntimeError("Invalid profiling run identifier")
    run_dir = root / "runs" / run_id
    state = json.loads(command("docker", "inspect", "--format", "{{json .State}}", container))
    if not state["Running"]:
        raise RuntimeError("Execution container is not running")
    image = command("docker", "inspect", "--format", "{{.Image}}", container)
    processes = command("docker", "exec", container, "sh", "-c",
                        'for p in /proc/[0-9]*; do '
                        'if [ "$(cat "$p/comm" 2>/dev/null)" = java ]; then '
                        'basename "$p"; fi; done').splitlines()
    pids = [s for s in processes if s.isdigit()]
    if len(pids) != 1:
        raise RuntimeError("Expected exactly one Besu JVM")
    recordings = command("docker", "exec", container, "jcmd", pids[0], "JFR.check")
    if not re.search(r"name=besu\b.*\(running\)", recordings):
        raise RuntimeError("The dedicated Besu recording is not running")
    stopped_default = bool(re.search(r"Recording 1: name=1\s", recordings))
    if stopped_default:
        command("docker", "exec", container, "jcmd", pids[0], "JFR.stop", "name=1")
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    filename = "checkpoint-" + timestamp + ".jfr"
    target = run_dir / "checkpoints" / filename
    result = command("docker", "exec", container, "jcmd", pids[0], "JFR.dump",
                     "name=besu", "maxage=5m", "maxsize=64m",
                     "filename=/profiling/runs/" + run_id + "/checkpoints/" + filename)
    # Reject a checkpoint raced by a container restart.
    if (root / "active-run").read_text().strip() != run_id:
        raise RuntimeError("Container restarted during checkpoint; retry on the next timer tick")
    with target.open("rb") as stream:
        if stream.read(4) != b"FLR\0":
            raise RuntimeError("Checkpoint is not a JFR recording")
    metadata = {
        "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "run_id": run_id, "container_started_at": state["StartedAt"],
        "image_id": image, "recording": str(target), "bytes": target.stat().st_size,
        "jcmd_result": result,
        "stopped_redundant_startup_recording": stopped_default,
    }
    try:
        with urllib.request.urlopen("http://127.0.0.1:5052/eth/v1/node/syncing", timeout=5) as response:
            metadata["consensus_sync"] = json.load(response)["data"]
    except Exception as error:
        metadata["consensus_probe_error"] = type(error).__name__
    save(target.with_suffix(".json"), metadata)
    save(root / "status.json", metadata)
    ordinary = sorted((p for p in (root / "runs").glob("*/checkpoints/checkpoint-*.jfr")
                       if not (p.parent.parent / "heap.hprof").exists()),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in ordinary[keep:]:
        stale.unlink()
        stale.with_suffix(".json").unlink(missing_ok=True)
    print(json.dumps({"run_id": run_id, "checkpoint_bytes": metadata["bytes"],
                      "consensus_sync": metadata.get("consensus_sync")}, sort_keys=True))


if __name__ == "__main__":
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--container", default="execution")
    parser.add_argument("--keep", type=int, default=24)
    parser.add_argument("--minimum-free", type=int, default=40 * 1024 ** 3)
    options = parser.parse_args()
    if options.keep < 1:
        parser.error("--keep must be positive")
    checkpoint(options.root, options.container, options.keep, options.minimum_free)
