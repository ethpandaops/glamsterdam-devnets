#!/usr/bin/env bash
set -euo pipefail
source_dir=$(realpath "${1:?pinned Erigon checkout required}")
output=$(realpath -m "${2:?output binary path required}")
tool_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
revision=8c1e3893d77d230720d172f1492d95b5777a862c
test "$(git -C "$source_dir" rev-parse HEAD)" = "$revision"
test -z "$(git -C "$source_dir" status --porcelain)"
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/pbt-bal-build.XXXXXX")
trap 'rm -rf -- "$build_dir"' EXIT
cp "$tool_dir"/*.go "$build_dir/"
cp "$source_dir/go.sum" "$build_dir/go.sum"
cd "$build_dir"
cat > go.mod <<'EOF'
module ethpandaops/pbt-erigon-bal-backfill

go 1.26.0

require github.com/erigontech/erigon v0.0.0

replace github.com/holiman/bloomfilter/v2 => github.com/AskAlexSharov/bloomfilter/v2 v2.0.9
EOF
export GOWORK=off GOTOOLCHAIN=auto
go mod edit -replace="github.com/erigontech/erigon=$source_dir"
go test -race -mod=mod -count=1 ./...
go build -mod=mod -trimpath -buildvcs=false -o "$output" .
python3 - "$output" "$tool_dir" "$revision" <<'PY'
import datetime,hashlib,json,subprocess,sys
from pathlib import Path
binary=Path(sys.argv[1]);sources=Path(sys.argv[2])
report={'client_revision':sys.argv[3],'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
        'built_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'go_build_info':subprocess.check_output(['go','version','-m',str(binary)],text=True),
        'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources.iterdir()) if p.suffix in ('.go','.sh')}}
Path(str(binary)+'.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'binary':str(binary),'sha256':report['binary_sha256']}))
PY
