"""Build a standalone public review and curated archive from saved evidence."""
import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import re
import zipfile
import markdown

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True)
parser.add_argument('--evidence-url')
args = parser.parse_args()
artifacts = ROOT / 'artifacts'
artifacts.mkdir(exist_ok=True)
text = (ROOT / 'README.md').read_text()
rendered = markdown.markdown(text, extensions=['tables', 'fenced_code'])

def link(match):
    attr, target = match.group(1), html.unescape(match.group(2))
    if target.startswith(('https:', 'http:', '#', 'data:')):
        return match.group(0)
    path = (ROOT / target).resolve()
    assert path.exists(), target
    if attr == 'src':
        path = path.with_suffix('.svg')
        target = 'data:image/svg+xml;base64,' + base64.b64encode(path.read_bytes()).decode()
    else:
        target = f'https://github.com/ethpandaops/glamsterdam-devnets/blob/{args.source}/' + str(path.relative_to(REPO))
    return f'{attr}="{html.escape(target, quote=True)}"'

rendered = re.sub(r'(href|src)="([^"]+)"', link, rendered)

def md_link(match):
    target = match.group(1)
    if target.startswith(('https:', 'http:', '#')):
        return match.group(0)
    path = (ROOT / target).resolve()
    kind = 'raw' if path.suffix in ('.png', '.svg') else 'blob'
    return f'](https://github.com/ethpandaops/glamsterdam-devnets/{kind}/{args.source}/' + str(path.relative_to(REPO)) + ')'

portable_text = re.sub(r'\]\(([^)]+)\)', md_link, text)
style = 'body{margin:0;background:#f1f5f4;color:#172531;font:16px/1.65 system-ui,sans-serif}*{box-sizing:border-box}main{max-width:1060px;margin:28px auto;background:white;padding:clamp(18px,5vw,54px);border:1px solid #d6e1de;border-radius:14px}h1{font-size:clamp(27px,4vw,39px);line-height:1.2}h2{margin-top:38px;font-size:25px;line-height:1.3}a{color:#126959;overflow-wrap:anywhere}p,li{overflow-wrap:anywhere}img{width:100%;height:auto}table{display:block;width:100%;overflow:auto;border-collapse:collapse;font-size:14px}th,td{padding:10px;border:1px solid #dce5e2;min-width:100px;vertical-align:top}th{background:#edf4f1;text-align:left}code{font-size:.86em;overflow-wrap:anywhere;background:#edf2f2;padding:2px 4px}button,.button{display:inline-block;background:#17685c;border:0;border-radius:7px;color:white;padding:10px 15px;text-decoration:none;font:600 14px system-ui;cursor:pointer}.actions{display:flex;flex-wrap:wrap;gap:10px}header{border-bottom:1px solid #d6e1de;padding-bottom:22px;margin-bottom:26px}.eyebrow{font-size:13px;text-transform:uppercase;color:#17685c;letter-spacing:.08em}footer{border-top:1px solid #d6e1de;margin-top:35px;padding-top:18px;color:#556878;font-size:13px}textarea{width:100%;height:320px}details{margin-top:30px}@media print{body{background:white}main{border:0;margin:0;padding:0}.actions,details{display:none}table{display:table}}'
archive_link = f'<a class="button" href="{html.escape(args.evidence_url)}">Download curated evidence</a>' if args.evidence_url else ''
page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Glamsterdam msf 2 review October 14 2026</title><style>' + style + '</style></head><body><main><header><p class="eyebrow">Client benchmarking review · October 14 2026 · All times UTC</p><div class="actions">' + archive_link + '<button id="copy">Copy review Markdown</button></div><p>Public chain evidence and sanitized diagnostics. Heap dumps, raw profiles and validator secrets remain private. No upstream issue has been filed.</p><div id="status" role="status"></div></header>' + rendered + '<details><summary>Portable review Markdown</summary><textarea id="review" readonly>' + html.escape(portable_text) + '</textarea></details><footer>Evidence source: <a href="https://github.com/ethpandaops/glamsterdam-devnets/commit/' + args.source + '">' + args.source[:12] + '</a>. Scope and collection limits are stated in the review.</footer></main><script>document.getElementById("copy").onclick=async()=>{const t=document.getElementById("review");try{await navigator.clipboard.writeText(t.value);document.getElementById("status").textContent="Review copied."}catch(e){t.closest("details").open=true;t.select();document.getElementById("status").textContent="Select and copy the Markdown below."}};</script></body></html>'
(artifacts / 'msf-2-review-2026-10-14.html').write_text(page)
# Keep the archive below the public upload gateway's request size. The complete
# canonical census and metrics remain permanently in the repository.
files = [ROOT / 'README.md', ROOT / 'window.json', ROOT / 'summarize.py', ROOT / 'plot_review.py']
files += list(ROOT.glob('*.svg'))
files += [p for p in (ROOT / 'evidence').glob('*.json') if not p.name.endswith('-history.json') and not p.name.startswith('log-counts-') and p.name != 'nimbus-missed-proposal-logs.json']
manifest = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
with zipfile.ZipFile(artifacts / 'msf-2-review-2026-10-14-evidence.zip', 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for p in sorted(files):
        z.write(p, str(p.relative_to(ROOT)))
    z.writestr('sha256-manifest.json', json.dumps(manifest, indent=2) + '\n')
    z.writestr('archive-scope.json', json.dumps({'source': args.source, 'scope': 'Curated findings and source captures; full census and historical metrics in linked public repository. summarize.py needs the full repository evidence tree; plot_review.py also needs the omitted historical metric JSONs.'}, indent=2) + '\n')
for p in artifacts.iterdir():
    assert p.stat().st_size < 760000, (p.name, p.stat().st_size)
print(json.dumps({p.name: p.stat().st_size for p in artifacts.iterdir()}))
