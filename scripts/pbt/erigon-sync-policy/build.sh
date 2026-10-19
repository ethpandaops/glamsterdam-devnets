#!/usr/bin/env bash
set -euo pipefail
tool_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
output=$(realpath -m "${1:?output binary path required}")
cd "$tool_dir"
export GOWORK=off GOTOOLCHAIN=auto
go test -mod=readonly -count=1 ./...
go build -mod=readonly -trimpath -buildvcs=false -ldflags '-linkmode external -extldflags -static' -o "$output" .
python3 - "$output" "$tool_dir" <<'PY'
import datetime,hashlib,json,subprocess,sys
from pathlib import Path
binary=Path(sys.argv[1]);sources=Path(sys.argv[2])
r={'mdbx_go_version':'v0.43.0','binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
   'built_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
   'go_build_info':subprocess.check_output(['go','version','-m',str(binary)],text=True),
   'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources.iterdir()) if p.suffix in ('.go','.sh','.mod','.sum')}}
Path(str(binary)+'.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'binary':str(binary),'sha256':r['binary_sha256']}))
PY
