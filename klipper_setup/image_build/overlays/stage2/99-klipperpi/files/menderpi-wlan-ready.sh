#!/bin/bash

set -euo pipefail

interface="${MENDERPI_WLAN_INTERFACE:-wlan0}"
poll_seconds="${MENDERPI_WLAN_READY_POLL_SECONDS:-1}"
log_interval_seconds="${MENDERPI_WLAN_READY_LOG_INTERVAL_SECONDS:-15}"
next_log_at=0

echo "Waiting for a global IPv4 address on ${interface}"

while true; do
  ipv4_address="$(
    ip -4 -o address show dev "${interface}" scope global 2>/dev/null |
      awk 'NR == 1 { print $4 }' || true
  )"

  if [ -n "${ipv4_address}" ]; then
    echo "${interface} is ready with IPv4 address ${ipv4_address}"
    exit 0
  fi

  now="$(date +%s)"
  if [ "${now}" -ge "${next_log_at}" ]; then
    echo "${interface} has no global IPv4 address yet; continuing to wait"
    next_log_at="$((now + log_interval_seconds))"
  fi

  sleep "${poll_seconds}"
done
