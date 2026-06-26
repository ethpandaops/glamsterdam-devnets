#!/usr/bin/env python3
import base64
import gzip
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

TEAM = "ethpandaops"
API = f"https://notes.ethereum.org/api/OpenAPI/v1/teams/{TEAM}/notes"
UA = "curl/8.4.0"

ITEM_RE = re.compile(
    r"(\[(?:PR|ISSUE)-\d+[^\]]*\]"
    r"\(https://github\.com/([^/\s]+)/([^/\s)]+)/(pull|issues)/(\d+)\))"
    r"(?:[ \t]+(?:Merged|Open|Closed|Draft))?(?:[ \t]+:[\w_]+:)?"
    r"(?=[ \t]*(?:~~|$))",
    re.MULTILINE,
)

ITEM_URL_RE = {
    "pr": re.compile(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)(?:[/?#].*)?$"),
    "issue": re.compile(r"https://github\.com/([^/]+)/([^/]+)/issues/(\d+)(?:[/?#].*)?$"),
}
ITEM_LINE_RE = re.compile(
    r"^\s*-\s*\[(?:PR|ISSUE)-\d+[^\]]*\]"
    r"\(https://github\.com/([^/\s]+)/([^/\s)]+)/(?:pull|issues)/(\d+)\)"
)

STATUS_LABEL = {
    "merged": "Merged :heavy_check_mark:",
    "closed": "Closed :x:",
    "draft": "Draft :exclamation:",
    "open": "Open :exclamation:",
}

REPO_SECTIONS = {
    ("ethereum", "beacon-APIs"): "Beacon API",
    ("ethereum", "builder-specs"): "Builder Specs",
    ("ethereum", "consensus-specs"): "Consensus Specs",
    ("ethereum", "EIPs"): "EIPs",
    ("ethereum", "execution-apis"): "Execution APIs",
    ("ethereum", "execution-specs"): "Execution Specs",
}

# EELS (execution-specs) test fixtures pin each EIP to a specific ethereum/EIPs
# commit via a ReferenceSpec in `tests/amsterdam/eip<NUM>_*/spec.py`. We read
# that hash and attach it to each row of the EIP List table so the spec each
# EIP is implemented against is pinned to an exact git hash.
EELS_DEFAULT_TAG = "tests-glamsterdam-devnet"
EELS_TREE = "repos/ethereum/execution-specs/contents/tests/amsterdam"
EELS_TAG_RE = re.compile(r"tests-glamsterdam-devnet@v[\w.]+")
EIP_DIR_RE = re.compile(r"eip(\d+)_")
# Handles both keyword (`version="..."`) and positional ReferenceSpec forms.
REF_VERSION_RE = re.compile(r'version\s*=\s*"([^"]+)"')
REF_GIT_PATH_RE = re.compile(r'git_path\s*=\s*"([^"]+)"')
REF_POSITIONAL_RE = re.compile(
    r'ReferenceSpec\(\s*"([^"]+)"\s*,\s*"([^"]+)"', re.S
)
# An EIP link in the table, plus any spec pin we previously appended to it.
EIP_LINK_RE = re.compile(r"\[EIP-(\d+)\]\((https?://[^)]+)\)")
SPEC_PIN_RE = re.compile(
    r"\s*(?:\[`spec@[^`]+`\]\([^)]*\)|`spec@[^`]+`)"
)


def normalize_eels_ref(tag):
    """`v6.1.0` -> `tests-glamsterdam-devnet@v6.1.0`; full refs pass through."""
    return tag if "@" in tag else f"{EELS_DEFAULT_TAG}@{tag}"


def fetch_spec_versions(ref):
    """Map EIP number -> (git_path, hash) from each spec.py at `ref`."""
    entries = gh_api(f"{EELS_TREE}?ref={ref}", optional=True)
    if not entries:
        return {}
    versions = {}
    for entry in entries:
        if entry.get("type") != "dir":
            continue
        dm = EIP_DIR_RE.match(entry["name"])
        if not dm:
            continue
        num = dm.group(1)
        blob = gh_api(f"{EELS_TREE}/{entry['name']}/spec.py?ref={ref}", optional=True)
        if not blob:
            continue
        src = base64.b64decode(blob.get("content", "")).decode("utf-8", "replace")
        vm = REF_VERSION_RE.search(src)
        gm = REF_GIT_PATH_RE.search(src)
        if vm:
            version, git_path = vm.group(1), (gm.group(1) if gm else f"EIPS/eip-{num}.md")
        else:
            pm = REF_POSITIONAL_RE.search(src)
            if not pm:
                continue
            git_path, version = pm.group(1), pm.group(2)
        versions[num] = (git_path, version)
    return versions


def pin_spec_versions(text, versions):
    """Append/refresh a `spec@<hash>` pin on each EIP row in the EIP List
    table. Returns (new_text, [(eip, hash), ...])."""
    lines = text.split("\n")
    start = next(
        (i for i, l in enumerate(lines) if re.match(r"##\s+EIP List", l)), None
    )
    if start is None:
        raise SystemExit("no '## EIP List' section found")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s.startswith("## ") or s == "**Key:**":
            end = j
            break
    changes = []
    for j in range(start, end):
        m = EIP_LINK_RE.search(lines[j])
        if not m:
            continue
        num = m.group(1)
        after = lines[j][m.end():]
        pin = SPEC_PIN_RE.match(after)
        if pin:
            after = after[pin.end():]
        suffix = ""
        if num in versions:
            git_path, h = versions[num]
            if set(h) <= {"0"}:  # all-zero placeholder = EIP not merged yet
                suffix = " `spec@unmerged`"
            else:
                url = f"https://github.com/ethereum/EIPs/blob/{h}/{git_path}"
                suffix = f" [`spec@{h[:8]}`]({url})"
        new_line = lines[j][:m.end()] + suffix + after
        if new_line != lines[j]:
            changes.append((num, versions.get(num, (None, None))[1]))
            lines[j] = new_line
    return "\n".join(lines), changes


def hackmd(method, path="", body=None):
    token = os.environ.get("HACKMD_TOKEN")
    if not token:
        raise SystemExit(
            "HACKMD_TOKEN env var not set — generate one at "
            "https://notes.ethereum.org/settings#api and `export HACKMD_TOKEN=...`"
        )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": UA,
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        if len(data) > 8000:
            data = gzip.compress(data)
            headers["Content-Encoding"] = "gzip"
    req = urllib.request.Request(
        f"{API}/{path}" if path else API,
        data=data,
        headers=headers,
        method=method,
    )
    return urllib.request.urlopen(req)


def gh_api(path, optional=False):
    """GET a GitHub REST API path. `optional` returns None on 404 instead of
    aborting (used when probing for files/refs that may not exist)."""
    # Default to the authenticated `gh` CLI (5000 req/hr).
    try:
        out = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        return json.loads(out)
    except FileNotFoundError:
        pass  # gh not installed — fall back to GITHUB_TOKEN
    except subprocess.CalledProcessError as e:
        if optional and "HTTP 404" in e.stderr:
            return None
        raise SystemExit(f"gh api {path} failed: {e.stderr.strip()}")
    # Fall back to a GITHUB_TOKEN; without either, refuse rather than make
    # unauthenticated requests that hit the 60 req/hr rate limit.
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            "no GitHub auth available — run `gh auth login` or "
            "`export GITHUB_TOKEN=...`"
        )
    req = urllib.request.Request(
        f"https://api.github.com/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": UA,
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        return json.loads(urllib.request.urlopen(req).read())
    except urllib.error.HTTPError as e:
        if optional and e.code == 404:
            return None
        raise


def github_obj(owner, repo, num, endpoint):
    return gh_api(f"repos/{owner}/{repo}/{endpoint}/{num}")


def status_from_pr(pr):
    if pr.get("merged"):
        return STATUS_LABEL["merged"]
    if pr["state"] == "closed":
        return STATUS_LABEL["closed"]
    if pr.get("draft"):
        return STATUS_LABEL["draft"]
    return STATUS_LABEL["open"]


def status_from_issue(issue):
    if issue["state"] == "closed":
        return STATUS_LABEL["closed"]
    return STATUS_LABEL["open"]


def find_note_id(network):
    for n in json.loads(hackmd("GET").read()):
        if n.get("permalink") == network:
            return n["id"]
    raise SystemExit(f"no note with permalink '{network}' in team {TEAM}")


def local_path(network):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), f"{network}.md")


def pull(network):
    note = json.loads(hackmd("GET", find_note_id(network)).read())
    with open(local_path(network), "w") as f:
        f.write(note["content"])
    print(f"pulled {network}.md ({len(note['content'])} bytes)")


def push(network):
    with open(local_path(network)) as f:
        content = f.read()
    resp = hackmd("PATCH", find_note_id(network), {"content": content})
    print(f"pushed {network}.md -> HTTP {resp.status}")


def sync(network, tag=None):
    pull(network)  # remote is the source of truth — start from it
    path = local_path(network)
    with open(path) as f:
        text = f.read()
    cache = {}

    def replace(m):
        link, owner, repo, kind, num = m.groups()
        old_status = m.group(0)[len(link):].strip()
        key = (owner, repo, num)
        if key not in cache:
            if kind == "pull":
                cache[key] = status_from_pr(github_obj(owner, repo, int(num), "pulls"))
            else:
                cache[key] = status_from_issue(
                    github_obj(owner, repo, int(num), "issues")
                )
        new_status = cache[key]
        if old_status != new_status:
            print(f"{owner}/{repo}#{num}: {old_status or '(none)'} -> {new_status}")
        return f"{link} {new_status}"

    new_text = ITEM_RE.sub(replace, text)

    # Re-check which execution-spec versions the EIPs are pinned to.
    ref = normalize_eels_ref(tag) if tag else None
    if not ref:
        m = EELS_TAG_RE.search(new_text)
        ref = m.group(0) if m else None
    if ref:
        versions = fetch_spec_versions(ref)
        if versions:
            new_text, changes = pin_spec_versions(new_text, versions)
            for num, h in changes:
                print(f"EIP-{num}: spec@{(h or 'unmerged')[:8]}")
        else:
            print(f"no spec versions at {ref} (tag not cut?)")
    else:
        print("no EELS tag in note — skipping spec version check")

    if new_text == text:
        print(f"{network}.md: no changes")
        return
    with open(path, "w") as f:
        f.write(new_text)
    print(f"updated {network}.md")
    push(network)


def add_item(network, *args):
    if len(args) == 1:
        sync_remote, url = False, args[0]
    elif len(args) == 2:
        sync_remote, url = args[0].lower() in ("true", "1", "yes"), args[1]
    else:
        raise SystemExit(
            "usage: sync.py add <network> [<sync-to-remote>] <github-pr-or-issue-url>"
        )
    kind = next((k for k, rx in ITEM_URL_RE.items() if rx.match(url)), None)
    if not kind:
        raise SystemExit(f"not a github PR or issue URL: {url}")
    m = ITEM_URL_RE[kind].match(url)
    owner, repo, num = m.group(1), m.group(2), int(m.group(3))
    section = REPO_SECTIONS.get((owner, repo))
    if not section:
        raise SystemExit(
            f"no section mapped for {owner}/{repo}; add it to REPO_SECTIONS"
        )

    if kind == "pr":
        label = "PR"
        obj = github_obj(owner, repo, num, "pulls")
        canonical_url = f"https://github.com/{owner}/{repo}/pull/{num}"
        status = status_from_pr(obj)
    else:
        label = "ISSUE"
        obj = github_obj(owner, repo, num, "issues")
        canonical_url = f"https://github.com/{owner}/{repo}/issues/{num}"
        status = status_from_issue(obj)
    new_line = f"- [{label}-{num} - {obj['title']}]({canonical_url}) {status}\n"

    path = local_path(network)
    with open(path) as f:
        lines = f.readlines()

    heading = f"**{section}**"
    section_start = next(
        (i for i, l in enumerate(lines) if l.strip() == heading), None
    )
    if section_start is None:
        raise SystemExit(f"section '{section}' not found in {network}.md")

    section_end = len(lines)
    for j in range(section_start + 1, len(lines)):
        s = lines[j].strip()
        if (s.startswith("**") and s.endswith("**")) or s.startswith("#"):
            section_end = j
            break

    insert_at = None
    last_item_line = None
    for j in range(section_start + 1, section_end):
        pm = ITEM_LINE_RE.match(lines[j])
        if not pm:
            continue
        if (pm.group(1), pm.group(2)) == (owner, repo) and int(pm.group(3)) == num:
            print(f"{label}-{num} already in {network}.md under '{section}'")
            return
        if int(pm.group(3)) > num:
            insert_at = j
            break
        last_item_line = j

    if insert_at is None:
        insert_at = last_item_line + 1 if last_item_line is not None else section_start + 1

    lines.insert(insert_at, new_line)
    with open(path, "w") as f:
        f.writelines(lines)
    print(f"added {label}-{num} to '{section}' in {network}.md")
    if sync_remote:
        push(network)


COMMANDS = {
    "from-remote": (pull, "<network>"),
    "to-remote": (push, "<network>"),
    "sync": (sync, "<network> [<tag>]"),
    "add": (add_item, "<network> [<sync-to-remote>] <github-pr-or-issue-url>"),
}


def usage():
    print("usage:", file=sys.stderr)
    for name, (_, args) in COMMANDS.items():
        print(f"  sync.py {name} {args}", file=sys.stderr)
    sys.exit(1)


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] not in COMMANDS:
        usage()
    fn, _ = COMMANDS[argv[0]]
    try:
        fn(*argv[1:])
    except TypeError:
        usage()


if __name__ == "__main__":
    main()
