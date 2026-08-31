#!/usr/bin/env python3
"""Resolve the exact EIP commit an EELS test release pins.

The execution-specs test suite is the source of truth for what a devnet actually
runs. Each tests/<fork>/<eip>/spec.py declares a ReferenceSpec(git_path, version)
where `version` is a commit hash in ethereum/EIPs — the EIP text *as implemented*.
This walks a release tag and emits the pinned ethereum/EIPs blob URLs so spec
sheets (and automated debugging) link to frozen commits instead of master, which
drifts.

Usage:
  eip_pins.py <release-tag> [--fork amsterdam] [--json]

Examples:
  eip_pins.py tests-glamsterdam-devnet@v6.1.0
  eip_pins.py tests-glamsterdam-devnet@v6.1.0 --json

Optional: set GITHUB_TOKEN (or GH_TOKEN) to lift the unauthenticated rate limit.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

REPO = "ethereum/execution-specs"
API = "https://api.github.com/repos"
UA = "glamsterdam-devnet-spec/eip_pins"

GIT_PATH_RE = re.compile(r"EIPS/eip-?\d+\.md")
VERSION_RE = re.compile(r"\b[0-9a-f]{40}\b")
EIP_NUM_RE = re.compile(r"eip-?(\d+)")


def gh(url):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": UA}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=headers)).read())


def contents(path, ref):
    q = urllib.parse.urlencode({"ref": ref})
    return gh(f"{API}/{REPO}/contents/{path}?{q}")


def resolve(fork, ref):
    dirs = sorted(e["name"] for e in contents(f"tests/{fork}", ref) if e["type"] == "dir")
    pins = []
    for d in dirs:
        try:
            src = base64.b64decode(contents(f"tests/{fork}/{d}/spec.py", ref)["content"]).decode()
        except urllib.error.HTTPError:  # directory without a spec.py
            continue
        gp = GIT_PATH_RE.search(src)
        if not gp:
            continue
        git_path = gp.group(0)
        # version always follows git_path (keyword form on the next line, or the
        # second positional arg of ReferenceSpec("EIPS/...", "<hash>")).
        vm = VERSION_RE.search(src, gp.end())
        version = vm.group(0) if vm else None
        if version and set(version) == {"0"}:  # placeholder hash (EIP not yet merged to master)
            version = None
        num = EIP_NUM_RE.search(git_path)
        pins.append({
            "eip": int(num.group(1)) if num else None,
            "dir": d,
            "git_path": git_path,
            "version": version,
            "eip_url": f"https://github.com/ethereum/EIPs/blob/{version}/{git_path}" if version else None,
        })
    pins.sort(key=lambda p: (p["eip"] is None, p["eip"]))
    return pins


def main():
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    fork = "amsterdam"
    if "--fork" in args:
        i = args.index("--fork")
        fork = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        sys.exit(__doc__)
    tag = args[0]

    pins = resolve(fork, tag)
    if as_json:
        print(json.dumps({"release": tag, "fork": fork, "pins": pins}, indent=2))
        return

    print(f"# EIP pins for `{tag}` (fork: {fork})\n")
    print("| EIP | Pinned EIP commit |")
    print("|-----|-------------------|")
    for p in pins:
        eip = f"EIP-{p['eip']}" if p["eip"] else p["dir"]
        if p["eip_url"]:
            print(f"| {eip} | [{p['version'][:10]}]({p['eip_url']}) |")
        else:
            print(f"| {eip} | _no version pinned in spec.py_ |")


if __name__ == "__main__":
    main()
