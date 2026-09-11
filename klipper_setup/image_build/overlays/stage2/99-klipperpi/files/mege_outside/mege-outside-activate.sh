#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "Usage: $0 <hub-wireguard-public-key> os.meges-world.net <hub-ssh-ed25519-public-key>" >&2
  exit 2
fi

HUB_WG_PUBLIC_KEY=$1
OUTSIDE_HOST=$2
HUB_SSH_HOST_KEY=$3
[[ "$OUTSIDE_HOST" == os.meges-world.net ]] || {
  echo "Unexpected outside host: $OUTSIDE_HOST" >&2
  exit 1
}
[[ "$HUB_WG_PUBLIC_KEY" =~ ^[A-Za-z0-9+/]{43}=$ ]] || {
  echo "Invalid hub WireGuard public key" >&2
  exit 1
}
[[ "$HUB_SSH_HOST_KEY" == ssh-ed25519\ * ]] || {
  echo "Only an ssh-ed25519 hub host key is accepted" >&2
  exit 1
}

WG_KEY=/etc/wireguard/mege.key
SSH_KEY=/home/pi/.ssh/mege-outside-printer-tunnel
TEMPLATE=/usr/local/share/mege-outside/mege.conf.template
CONFIG=/etc/wireguard/mege.conf
KNOWN_HOSTS=/home/pi/.ssh/mege-outside-known_hosts
[[ -s "$WG_KEY" && -s "$SSH_KEY" && -s "$TEMPLATE" ]] || {
  echo "Enroll the printer before activation" >&2
  exit 1
}

HOST_KEY_TMP=$(mktemp)
CONFIG_TMP=$(mktemp)
KNOWN_HOSTS_TMP=$(mktemp)
cleanup() {
  rm -f "$HOST_KEY_TMP" "$CONFIG_TMP" "$KNOWN_HOSTS_TMP"
}
trap cleanup EXIT

printf '%s\n' "$HUB_SSH_HOST_KEY" >"$HOST_KEY_TMP"
ssh-keygen -lf "$HOST_KEY_TMP" >/dev/null
[[ "$(awk '{print $1}' "$HOST_KEY_TMP")" == ssh-ed25519 ]] || {
  echo "Hub host key is not ED25519" >&2
  exit 1
}

PRIVATE_KEY=$(tr -d '\n' <"$WG_KEY")
MEGE_PRIVATE_KEY=$PRIVATE_KEY \
HUB_WG_PUBLIC_KEY=$HUB_WG_PUBLIC_KEY \
python3 - "$TEMPLATE" "$CONFIG_TMP" <<'PY'
import os
import sys
from pathlib import Path

template = Path(sys.argv[1]).read_text(encoding="utf-8")
replacements = {
    "__MEGE_PRIVATE_KEY__": os.environ["MEGE_PRIVATE_KEY"],
    "__HUB_WIREGUARD_PUBLIC_KEY__": os.environ["HUB_WG_PUBLIC_KEY"],
}
for marker, value in replacements.items():
    if template.count(marker) != 1:
        raise SystemExit(f"template must contain exactly one {marker}")
    template = template.replace(marker, value)
if "__" in template:
    raise SystemExit("activation template contains an unresolved marker")
Path(sys.argv[2]).write_text(
    template + ("" if template.endswith("\n") else "\n"), encoding="utf-8"
)
PY
install -o root -g root -m 0600 "$CONFIG_TMP" "$CONFIG"

printf '%s %s\n' "$OUTSIDE_HOST" "$HUB_SSH_HOST_KEY" >"$KNOWN_HOSTS_TMP"
install -o pi -g pi -m 0600 "$KNOWN_HOSTS_TMP" "$KNOWN_HOSTS"

systemctl daemon-reload
systemctl disable --now mege-printer-tunnel.service >/dev/null 2>&1 || true
systemctl enable --now wg-quick@mege.service

latest=0
deadline=$(( $(date +%s) + 120 ))
while (( $(date +%s) < deadline )); do
  latest=$(wg show mege latest-handshakes | awk 'NF >= 2 {print $2; exit}')
  now=$(date +%s)
  if [[ "$latest" =~ ^[0-9]+$ ]] && (( latest > 0 && now - latest <= 120 )); then
    break
  fi
  sleep 2
done
if [[ ! "$latest" =~ ^[0-9]+$ ]] || (( latest == 0 || $(date +%s) - latest > 120 )); then
  echo "WireGuard hub handshake was not observed" >&2
  systemctl --no-pager --full status wg-quick@mege.service >&2 || true
  exit 1
fi

systemctl enable --now mege-printer-tunnel.service
for _ in {1..30}; do
  [[ "$(systemctl is-active mege-printer-tunnel.service)" == active ]] && break
  sleep 2
done
[[ "$(systemctl is-active mege-printer-tunnel.service)" == active ]] || {
  systemctl --no-pager --full status mege-printer-tunnel.service >&2 || true
  exit 1
}

printf 'MEGE_OUTSIDE_ACTIVATED=1\n'
printf 'WIREGUARD_INTERFACE=mege\n'
printf 'WIREGUARD_HANDSHAKE_EPOCH=%s\n' "$latest"
printf 'TUNNEL_SERVICE=active\n'
