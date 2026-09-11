#!/usr/bin/env bash
set -euo pipefail

WG_KEY=/etc/wireguard/mege.key
SSH_DIR=/home/pi/.ssh
SSH_KEY=${SSH_DIR}/mege-outside-printer-tunnel

install -d -m 0700 /etc/wireguard
if [[ ! -e "$WG_KEY" ]]; then
  umask 077
  wg genkey >"$WG_KEY"
fi
[[ -s "$WG_KEY" ]] || { echo "WireGuard private key is empty" >&2; exit 1; }
chmod 0600 "$WG_KEY"

install -d -m 0700 -o pi -g pi "$SSH_DIR"
if [[ ! -e "$SSH_KEY" ]]; then
  sudo -u pi ssh-keygen -q -t ed25519 -N '' \
    -C "mege-printer-tunnel@$(hostname)" -f "$SSH_KEY"
elif [[ ! -s "${SSH_KEY}.pub" ]]; then
  umask 077
  ssh-keygen -y -f "$SSH_KEY" >"${SSH_KEY}.pub"
fi
[[ -s "$SSH_KEY" && -s "${SSH_KEY}.pub" ]] || {
  echo "SSH tunnel key pair is incomplete" >&2
  exit 1
}
chown pi:pi "$SSH_KEY" "${SSH_KEY}.pub"
chmod 0600 "$SSH_KEY"
chmod 0644 "${SSH_KEY}.pub"

WIREGUARD_PUBLIC_KEY=$(wg pubkey <"$WG_KEY")
SSH_PUBLIC_KEY=$(tr -d '\n' <"${SSH_KEY}.pub")
printf 'WIREGUARD_PUBLIC_KEY=%s\n' "$WIREGUARD_PUBLIC_KEY"
printf 'SSH_PUBLIC_KEY=%s\n' "$SSH_PUBLIC_KEY"
