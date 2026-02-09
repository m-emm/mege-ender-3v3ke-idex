#!/bin/bash
# Flash Katapult bootloader to RP2040 (mass-storage / BOOTSEL mode)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
FIRMWARE="${SCRIPT_DIR}/katapult/out/katapult.uf2"

echo "==> Flashing Katapult to RP2040"

if [[ ! -f "${FIRMWARE}" ]]; then
  echo "ERROR: Firmware not found at ${FIRMWARE}" >&2
  echo "Run ./build_katapult_docker.sh first" >&2
  exit 1
fi

echo "==> Waiting for RP2040 in system boot mode (RPI-RP2 drive)..."
echo "    (Hold BOOTSEL and connect USB, or use your board's boot mode sequence)"

target_mount_point=""
max_wait=30
waited=0

while [[ ${waited} -lt ${max_wait} ]]; do
  for mp in "/media/$USER/RPI-RP2" /media/RPI-RP2 /Volumes/RPI-RP2; do
    if [[ -d "${mp}" ]]; then
      target_mount_point="${mp}"
      break 2
    fi
  done
  sleep 1
  waited=$((waited + 1))
  echo -n "."
done

echo ""

if [[ -z "${target_mount_point}" ]]; then
  echo "ERROR: RP2040 boot drive not detected after ${max_wait} seconds" >&2
  echo "The RP2040 should appear as a USB drive named 'RPI-RP2'" >&2
  exit 1
fi

echo "==> Found RP2040 at: ${target_mount_point}"
echo "==> Copying Katapult UF2..."

cp "${FIRMWARE}" "${target_mount_point}/"

echo "==> Katapult copied successfully!"
echo "NOTE: Flashing Katapult erases the main application area (Klipper)."
