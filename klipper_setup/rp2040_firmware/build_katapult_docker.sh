#!/bin/bash
set -euo pipefail

# Build RP2040 Katapult bootloader using Docker
# Deterministic: pins Katapult ref via env var.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="klipper-rp2040-builder"

# Ensure helper script is executable when mounted into the container
chmod +x "${SCRIPT_DIR}/build_katapult_script_for_in_docker.sh" || true

: "${KATAPULT_REF:=b0bf421}"

echo "==> Building Docker image..."
echo "    KATAPULT_REF=${KATAPULT_REF}"

docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}"

echo "==> Running Katapult build in Docker container..."
docker run --rm \
  -v "${SCRIPT_DIR}:/work" \
  -u "$(id -u):$(id -g)" \
  -e "KATAPULT_REF=${KATAPULT_REF}" \
  "${IMAGE_NAME}" \
  bash -lc "/work/build_katapult_script_for_in_docker.sh"

echo ""
echo "==> Success! Katapult bootloader ready to flash."
echo "    Location: ${SCRIPT_DIR}/katapult/out/katapult.uf2"
