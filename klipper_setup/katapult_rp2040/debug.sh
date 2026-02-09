#!/bin/bash
# Launch interactive Docker container for Katapult debugging
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="katapult-rp2040-builder"

: "${KATAPULT_REF:=b0bf421}"

echo "==> Building Docker image..."
docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}"

echo ""
echo "==> Launching interactive Docker container..."
echo "    Working directory: /work"
echo "    Katapult source:   /work/katapult"
echo ""
echo "Available commands:"
echo "  - cd katapult && make menuconfig KCONFIG_CONFIG=/work/katapult_config"
echo "  - cd katapult && cp /work/katapult_config .config && make"
echo "  - cat katapult/.config             # View current config"
echo "  - cat katapult/out/autoconf.h      # View generated config"
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
