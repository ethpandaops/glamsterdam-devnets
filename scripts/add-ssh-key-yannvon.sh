#!/usr/bin/env bash
# Append yannvon's GitHub SSH key to the devops user's authorized_keys.
#
# Stop-gap for when a full bootstrap run is too slow. NOT durable: the bootstrap role
# writes authorized_keys with ansible.builtin.copy (content:), so it rewrites the whole
# file and drops anything added here. For a lasting change add "yannvon" to
# github_all_extra_users in inventories/devnet-10/group_vars/all/all.yaml.
#
# The key is embedded rather than fetched per host: 1000+ hosts hitting github.com at
# once would be rate limited. Refresh with: curl -sS https://github.com/yannvon.keys
#
#   ansible 'all:!localhost' -b -f 400 -m script -a ../scripts/add-ssh-key-yannvon.sh

set -euo pipefail

USER_NAME=devops
SSH_DIR="/home/$USER_NAME/.ssh"
KEYFILE="$SSH_DIR/authorized_keys"
KEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJKegljdxG+yZkGnZCqFWvtlpAd+xcX54eWkQjcMGl1J'
COMMENT=yannvon

id -u "$USER_NAME" >/dev/null 2>&1 || { echo "FATAL: no $USER_NAME user" >&2; exit 1; }
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0700 "$SSH_DIR"
[ -f "$KEYFILE" ] || install -o "$USER_NAME" -g "$USER_NAME" -m 0600 /dev/null "$KEYFILE"

# Match on the key material only, so a differing trailing comment is not a duplicate.
BLOB=$(awk '{print $2}' <<<"$KEY")
if grep -qF -- "$BLOB" "$KEYFILE"; then
  echo "$(hostname): already present ($(grep -c '[^[:space:]]' "$KEYFILE") keys)"
else
  printf '%s %s\n' "$KEY" "$COMMENT" >> "$KEYFILE"
  echo "$(hostname): added ($(grep -c '[^[:space:]]' "$KEYFILE") keys)"
fi
chown "$USER_NAME:$USER_NAME" "$KEYFILE"
chmod 0600 "$KEYFILE"
