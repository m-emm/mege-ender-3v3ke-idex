#!/bin/bash
set -euo pipefail

# Debug script: Launch interactive Docker container for Katapult development
# Use this to run menuconfig, inspect config, or debug build issues

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="klipper-rp2040-builder"

: "${KATAPULT_REF:=b0bf421}"

echo "==> Building Docker image..."
echo "    KATAPULT_REF=${KATAPULT_REF}"

docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}"

echo ""
echo "==> Launching interactive Docker container..."
echo "    Working directory: /work"
echo "    Katapult source:   /work/katapult"
echo ""
echo "Available commands:"
echo "  - cd katapult && make menuconfig   # Configure Katapult"
echo "  - cd katapult && make              # Build Katapult"
echo "  - cat katapult/.config             # View current config"
echo "  - exit                             # Leave container"
echo ""

docker run --rm -it \
  -v "${SCRIPT_DIR}:/work" \
  -u "$(id -u):$(id -g)" \
  -e "KATAPULT_REF=${KATAPULT_REF}" \
  -e "TERM=${TERM:-xterm-256color}" \
  -w /work \
  "${IMAGE_NAME}" \
  bash
