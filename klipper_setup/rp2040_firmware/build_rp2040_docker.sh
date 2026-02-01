#!/bin/bash
set -euo pipefail

# Build RP2040 Klipper firmware using Docker
# Deterministic: pins Pico SDK and Klipper refs via env vars.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="klipper-rp2040-builder"

: "${KLIPPER_REF:=576d0ca13}"

echo "==> Building Docker image..."
echo "    KLIPPER_REF=${KLIPPER_REF}"

docker build  -t "${IMAGE_NAME}" "${SCRIPT_DIR}"

echo "==> Running build in Docker container..."
docker run --rm \
  -v "${SCRIPT_DIR}:/work" \
  -u "$(id -u):$(id -g)" \
  -e "KLIPPER_REF=${KLIPPER_REF}" \
  "${IMAGE_NAME}" \
  bash -lc "/work/build_rp2040_script_for_in_docker.sh"

echo ""
echo "==> Success! Firmware ready to flash."
echo "    Location: ${SCRIPT_DIR}/klipper/out/klipper.uf2"
echo ""
echo "To flash:"
echo "  1. Hold BOOTSEL button on Pico and connect USB"
echo "  2. Run: ./flash_rp2040.sh"
