#!/bin/sh
# Import the prestate blocks into this host's EL (CL stopped). Stage import_blocks.py and
# block1.json/block2.json in <dir> first, then run via ansible:
#   ansible '<hosts>' -b -m script -a 'scripts/shadowfork-prestate/run_import.sh /tmp/pre'
d="${1:-/tmp/pre}"
ip=$(docker inspect execution --format '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' | cut -d' ' -f1)
python3 "$d/import_blocks.py" "http://$ip:8551" "http://$ip:8545" /data/execution-auth.secret "$d/block1.json" "$d/block2.json"
