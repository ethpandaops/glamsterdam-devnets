"""Build standalone Panda reports and per-issue evidence archives.

Run after committing the Markdown reports: python3 build_reports.py <source-commit>.
Upload ZIPs first, then save their URLs in uploads.json and run again to add links.
"""
import base64
import hashlib
import html
import json
import re
import sys
import zipfile
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent
OLD = REPO / "md/msf-2-benchmark-2026-10-12"
OLD_SHA = "60a8cf5a3d76dc9a508c01e3a9412881d4c1440c"
SLUGS = ["01-besu-heap-exhaustion", "02-teku-persisted-envelope",
         "03-nimbus-engine-listener", "04-teku-optimistic-recovery",
         "05-nimbus-remote-bid-fallback"]
PRIOR = [
    ["besu-heap-failure.log", "besu-oom-occurrences.json", "besu-runtime-config.json",
     "besu-heap-history.json.gz", "besu-gc-history.json.gz", "besu-live-proposal-delays.json",
     "lighthouse-besu-slow-imports.json", "lighthouse-besu-slot2885.json",
     "grandine-besu-slot2977.json", "workload-sample.json", "workload-callee-code.json",
     "workload-disassembly.txt"],
    ["teku-startup-failure.log", "teku-optimistic-startup.log", "rollout-timeline.log",
     "teku-slot2559-block.json", "teku-slot2559-envelope.json"],
    ["nimbus-engine-outage-onset.json", "nimbus-el-degradation.json", "nimbus-snap-onset.json",
     "nimbus-snap-current.json", "nimbus-engine-accept-queue.txt",
     "nimbus-engine-capabilities-final.json"],
    ["rollout-timeline.log", "erigon-optimistic-recurrence.json",
     "erigon-initial-syncing-transition.json", "erigon-recurrence-chain-context.json",
     "lodestar-erigon-slot2988.json", "lodestar-erigon-runtime.json"],
    ["nimbus-reth-proposal-logs.json", "nimbus-reth-slot2821-beacon.json",
     "nimbus-reth-slot2821-execution.json", "nimbus-proposal-counters-history.json.gz",
     "reth-getpayload-history.json.gz", "slots-epochs88-90.json",
     "missed-slot-details-epochs88-90.json"] + [f"proposal-epoch-{i}.json" for i in range(91, 97)],
]
NEW = [
    ["besu-heap-current.json", "besu-gc-current.json", "overnight-oom.json",
     "workload-code-samples.json", "current-execution-block.json"],
    ["teku-slot2559-stored-envelope.ssz", "teku-slot2559-stored-block.ssz",
     "teku-slot2559-canonical-envelope.ssz", "teku-record-inspection.log",
     "teku-minimal-reproduction.log", "teku-private-startup-26.10.0.log",
     "teku-private-startup-26.9.1.log", "teku-private-reproduction.json"],
    ["nimbus-private-accept.trace", "nimbus-private-listener-test.json",
     "nimbus-engine-morning-probe.json"],
    ["overnight-erigon-optimism.json"],
    ["overnight-nimbus-proposals.json", "overnight-nimbus-events.json"],
]


def main():
    source_sha = sys.argv[1]
    assert re.fullmatch(r"[0-9a-f]{40}", source_sha)
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    uploads = json.loads((ROOT / "uploads.json").read_text()) if (ROOT / "uploads.json").exists() else {}
    for i, slug in enumerate(SLUGS):
        md_path = ROOT / "reports" / (slug + ".md")
        text = md_path.read_text()
        files = {"report.md": md_path, "network/config.yaml": REPO / "network-configs/msf-2/metadata/config.yaml"}
        files.update({"original-evidence/" + n: OLD / "evidence" / n for n in PRIOR[i]})
        files.update({"follow-up-evidence/" + n: ROOT / "evidence" / n for n in NEW[i]})
        for n in ["current-network.json", "source-revisions.json", "source-comparison.json"]:
            files["follow-up-evidence/" + n] = ROOT / "evidence" / n
        if i == 0:
            files["besu-memory-and-gc.png"] = OLD / "besu-memory-and-gc.png"
            files["workload.md"] = OLD / "workload.md"
        if i == 1:
            for n in ["CheckStoredRecord.java", "InspectEnvelope.java", "teku_reproduce.sh"]:
                files["tests/" + n] = ROOT / "tests" / n
        if i == 2:
            files["tests/nimbus_listener.py"] = ROOT / "tests/nimbus_listener.py"
        manifest = {n: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for n, p in files.items()}
        archive = artifacts / (slug + "-evidence.zip")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for n, p in files.items():
                info = zipfile.ZipInfo(n, date_time=(2026, 10, 13, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, p.read_bytes())
            z.writestr("sha256-manifest.json", json.dumps(manifest, indent=2))
        def issue_link(match):
            target = match.group(1)
            if target.startswith(("https:", "http:", "#")):
                return match.group(0)
            if target.startswith("evidence/") or target in ["workload.md", "besu-memory-and-gc.png"]:
                path, sha = OLD / target, OLD_SHA
            else:
                path, sha = (md_path.parent / target).resolve(), source_sha
            kind = "raw" if path.suffix == ".png" else "blob"
            return "](" + f"https://github.com/ethpandaops/glamsterdam-devnets/{kind}/{sha}/" + str(path.relative_to(REPO)) + ")"

        issue_text = re.sub(r"\]\(([^)]+)\)", issue_link, text)
        rendered = markdown.markdown(text, extensions=["tables", "fenced_code", "toc"])

        def link(match):
            attr, target = match.group(1), html.unescape(match.group(2))
            if target.startswith(("https:", "http:", "#", "data:")):
                return match.group(0)
            if target.startswith("evidence/") or target in ["workload.md", "besu-memory-and-gc.png"]:
                path, sha = OLD / target, OLD_SHA
            else:
                path, sha = (md_path.parent / target).resolve(), source_sha
            if not path.exists():
                raise ValueError(f"Unresolved report link: {target}")
            if attr == "src" and path.suffix == ".png":
                target = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
            else:
                target = f"https://github.com/ethpandaops/glamsterdam-devnets/blob/{sha}/" + str(path.relative_to(REPO))
            return f'{attr}="{html.escape(target, quote=True)}"'

        rendered = re.sub(r'(href|src)="([^"]+)"', link, rendered)
        title = text.splitlines()[0].lstrip("# ")
        bundle = uploads.get(slug, {}).get("evidence_url")
        bundle_link = f'<a class="button" href="{html.escape(bundle)}">Download evidence ZIP</a>' if bundle else '<span>Evidence archive is being prepared</span>'
        page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{html.escape(title)} · msf-2</title>
<style> :root{{color-scheme:light;--ink:#172531;--muted:#556878;--accent:#17685c}} *{{box-sizing:border-box}} body{{margin:0;background:#f1f5f4;color:var(--ink);font:16px/1.65 system-ui,sans-serif}} main{{max-width:1050px;margin:32px auto;background:white;padding:clamp(20px,5vw,58px);border:1px solid #d6e1de;border-radius:16px}} header{{border-bottom:1px solid #d6e1de;margin-bottom:30px;padding-bottom:22px}} .eyebrow{{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--accent);font-weight:700}} .actions{{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}} .button,button{{background:var(--accent);border:0;border-radius:7px;color:white;padding:10px 15px;text-decoration:none;font:600 14px system-ui;cursor:pointer}} h1{{font-size:clamp(27px,4vw,40px);line-height:1.2;margin:20px 0}} h2{{font-size:23px;margin-top:42px;line-height:1.3}} h3{{font-size:19px;margin-top:30px}} a{{color:#126959;overflow-wrap:anywhere}} p,li{{overflow-wrap:anywhere}} code{{font-size:.86em;background:#edf2f2;padding:2px 5px;border-radius:4px;overflow-wrap:anywhere}} pre{{overflow:auto;background:#12272a;color:#ebf6ef;padding:20px;border-radius:8px;max-height:460px}} pre code{{background:none;padding:0;color:inherit;white-space:pre;overflow-wrap:normal}} table{{width:100%;border-collapse:collapse;font-size:14px;display:block;overflow:auto}} th,td{{padding:10px 12px;border:1px solid #dce5e2;vertical-align:top;min-width:110px}} th{{background:#edf4f1;text-align:left}} img{{max-width:100%;height:auto}} .notice{{padding:15px;background:#eaf4ef;border-left:4px solid var(--accent);border-radius:4px}} footer{{margin-top:45px;border-top:1px solid #dce5e2;padding-top:15px;color:var(--muted);font-size:13px}} details{{margin:25px 0}} textarea{{width:100%;height:350px;font:13px/1.5 monospace}} @media print{{body{{background:white}}main{{border:0;margin:0;padding:0}}.actions,details{{display:none}}pre{{max-height:none;white-space:pre-wrap}}table{{display:table}}}}</style></head><body><main>
<header><div class="eyebrow">Ethereum client investigation · glamsterdam-msf-2 · 13 October 2026</div><div class="actions">{bundle_link}<button id="copy">Copy issue Markdown</button><button id="download">Download Markdown</button></div><div class="notice">Public report prepared for later issue filing. Reproduction status and remaining causal gaps are stated below. No upstream issue or comment was submitted.</div><div id="status" role="status" aria-live="polite"></div></header>
{rendered}
<details><summary>Issue-ready Markdown</summary><textarea id="issue" aria-label="Issue-ready Markdown" readonly>{html.escape(issue_text)}</textarea></details><footer>Evidence source commit: <a href="https://github.com/ethpandaops/glamsterdam-devnets/commit/{source_sha}">{source_sha[:12]}</a>. All timestamps UTC. Public chain data and diagnostic evidence only; validator keys, authentication tokens and the full saved database are excluded.</footer></main>
<script>const issue=document.getElementById('issue');document.getElementById('copy').onclick=async()=>{{try{{await navigator.clipboard.writeText(issue.value);document.getElementById('status').textContent='Issue Markdown copied.'}}catch(e){{issue.closest('details').open=true;issue.select();document.getElementById('status').textContent='Select and copy the Markdown below.'}}}};document.getElementById('download').onclick=()=>{{const u=URL.createObjectURL(new Blob([issue.value],{{type:'text/markdown'}}));const a=document.createElement('a');a.href=u;a.download='{slug}.md';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}};</script></body></html>'''
        (artifacts / (slug + ".html")).write_text(page)
        print(slug, "html_bytes", len(page.encode()), "zip_bytes", archive.stat().st_size)


if __name__ == "__main__":
    main()
