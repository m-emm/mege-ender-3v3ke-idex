#!/bin/bash
# Build Katapult RP2040 bootloader using Docker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="katapult-rp2040-builder"

: "${KATAPULT_REF:=b0bf421}"

echo "==> Building Docker image..."
echo "    KATAPULT_REF=${KATAPULT_REF}"

docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}"

echo "==> Running Katapult build in Docker container..."
chmod +x "${SCRIPT_DIR}/build_in_docker.sh"

docker run --rm \
  -v "${SCRIPT_DIR}:/work" \
  -u "$(id -u):$(id -g)" \
  -e "KATAPULT_REF=${KATAPULT_REF}" \
  "${IMAGE_NAME}" \
  bash -lc "/work/build_in_docker.sh"

echo ""
echo "==> Success! Katapult bootloader ready to flash."
echo "    Location: ${SCRIPT_DIR}/katapult/out/katapult.uf2"
echo "    WithClear: ${SCRIPT_DIR}/katapult/out/katapult.withclear.uf2"
