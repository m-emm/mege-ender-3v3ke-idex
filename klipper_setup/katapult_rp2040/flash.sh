#!/bin/bash
# Flash Katapult to RP2040 via BOOTSEL mode
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRMWARE="${SCRIPT_DIR}/katapult/out/katapult.withclear.uf2"

echo "==> Flashing Katapult to RP2040"

if [[ ! -f "${FIRMWARE}" ]]; then
    echo "ERROR: Katapult firmware not found at ${FIRMWARE}" >&2
    echo "Run ./build.sh first" >&2
    exit 1
fi

echo "==> Waiting for RP2040 in BOOTSEL mode..."
echo "    (Hold BOOTSEL button and connect USB)"

# Wait for BOOTSEL volume
max_wait=30
count=0
while [ $count -lt $max_wait ]; do
    if [ -d "/Volumes/RPI-RP2" ]; then
        echo ""
        echo "==> Found RP2040 at: /Volumes/RPI-RP2"
        break
    fi
    sleep 1
    count=$((count + 1))
    echo -n "."
done

if [ ! -d "/Volumes/RPI-RP2" ]; then
    echo ""
    echo "ERROR: RP2040 not found in BOOTSEL mode after ${max_wait}s"
    exit 1
fi

echo "==> Copying Katapult UF2 (withclear version)..."
cp "${FIRMWARE}" /Volumes/RPI-RP2/

echo "==> Katapult flashed successfully!"
echo "NOTE: Katapult will stay in bootloader mode (no application installed yet)"
echo "      Use Katapult's flashtool.py to upload Klipper firmware"
