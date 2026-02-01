#!/bin/bash
# Flash Klipper firmware to RP2040 (Raspberry Pi Pico)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRMWARE="${SCRIPT_DIR}/klipper/out/klipper.uf2"

echo "==> Flashing Klipper to RP2040"

# Check if firmware exists
if [ ! -f "${FIRMWARE}" ]; then
    echo "ERROR: Firmware not found at ${FIRMWARE}"
    echo "Run ./build_rp2040.sh first"
    exit 1
fi

# Wait for RP2040 in bootloader mode
echo "==> Waiting for RP2040 in bootloader mode..."
echo "    (Hold BOOTSEL button and connect USB if not already done)"

MAX_WAIT=30
WAITED=0
MOUNT_POINT=""

while [ $WAITED -lt $MAX_WAIT ]; do
    # Try common mount points
    for mp in /media/$USER/RPI-RP2 /media/RPI-RP2 /Volumes/RPI-RP2; do
        if [ -d "$mp" ]; then
            MOUNT_POINT="$mp"
            break 2
        fi
    done
    
    sleep 1
    WAITED=$((WAITED + 1))
    echo -n "."
done

echo ""

if [ -z "$MOUNT_POINT" ]; then
    echo "ERROR: RP2040 bootloader not detected after ${MAX_WAIT} seconds"
    echo ""
    echo "Make sure:"
    echo "  1. Pico is disconnected"
    echo "  2. Hold down BOOTSEL button"
    echo "  3. Connect USB cable while holding BOOTSEL"
    echo "  4. Release BOOTSEL after connection"
    echo ""
    echo "The Pico should appear as a USB drive named 'RPI-RP2'"
    exit 1
fi

echo "==> Found RP2040 at: ${MOUNT_POINT}"
echo "==> Copying firmware..."

cp "${FIRMWARE}" "${MOUNT_POINT}/"

echo "==> Firmware copied successfully!"
echo "==> The Pico will automatically reboot and start running Klipper"
echo ""
echo "To verify, check /dev/serial/by-id/ for the new Klipper MCU device"
