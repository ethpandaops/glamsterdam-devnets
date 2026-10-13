"""Fault-inject a queued disconnect in a disposable Nimbus container only.

Start msf2-nimbus-rst-repro from statusim/nimbus-eth1:v0.4.2 on a Docker
--internal network with RPC and Engine listening on 0.0.0.0. No validators.
This tests listener resilience, not the benchmark's execution workload.
"""
import base64
import hashlib
import hmac
import json
import socket
import struct
import subprocess
import time
import urllib.request
from datetime import datetime, timezone

NAME = "msf2-nimbus-rst-repro"


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True).strip()


info = json.loads(docker("inspect", NAME))[0]
assert info["Config"]["Image"] == "statusim/nimbus-eth1:v0.4.2"
assert info["HostConfig"]["NetworkMode"] == "msf2-investigation"
ip = info["NetworkSettings"]["Networks"]["msf2-investigation"]["IPAddress"]
secret = bytes.fromhex(docker("exec", NAME, "cat", "/tmp/case/jwt.hex").removeprefix("0x"))


def request(port):
    start = time.monotonic()
    method = "engine_exchangeCapabilities" if port == 8551 else "eth_chainId"
    headers = {"Content-Type": "application/json"}
    if port == 8551:
        b64 = lambda x: base64.urlsafe_b64encode(x).rstrip(b"=")
        unsigned = b64(b'{"alg":"HS256","typ":"JWT"}') + b"." + b64(
            json.dumps({"iat": int(time.time())}).encode()
        )
        headers["Authorization"] = "Bearer " + (
            unsigned + b"." + b64(hmac.new(secret, unsigned, hashlib.sha256).digest())
        ).decode()
    req = urllib.request.Request(
        f"http://{ip}:{port}",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                         "params": [[]] if port == 8551 else []}).encode(),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as response:
            result = {"response": json.load(response)}
    except Exception as exc:
        result = {"error": str(exc)}
    return dict(result, latency_seconds=time.monotonic() - start)


def queued_disconnect(reset):
    docker("pause", NAME)
    try:
        connection = socket.create_connection((ip, 8551), timeout=2)
        if reset:
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                  struct.pack("ii", 1, 0))
        connection.close()
        time.sleep(1)
    finally:
        docker("unpause", NAME)
    time.sleep(0.5)


result = {"started_at": datetime.now(timezone.utc).isoformat(),
          "image_id": info["Image"], "mode": "fresh-minimal-fault-injection",
          "before": {str(p): request(p) for p in (8545, 8551)}}
assert all("response" in v for v in result["before"].values()), result
queued_disconnect(False)
result["after_fin"] = {str(p): request(p) for p in (8545, 8551)}
assert all("response" in v for v in result["after_fin"].values()), result
queued_disconnect(True)
result["after_rst"] = {str(p): request(p) for p in (8545, 8551)}
result["process_running"] = docker("inspect", NAME, "--format", "{{.State.Running}}")
result["passed"] = (
    "response" in result["after_rst"]["8545"]
    and "error" in result["after_rst"]["8551"]
    and result["process_running"] == "true"
)
result["completed_at"] = datetime.now(timezone.utc).isoformat()
print(json.dumps(result, indent=2))
assert result["passed"], result
