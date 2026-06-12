#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_CFG="${SCRIPT_DIR}/toolhead_nitehawk_and_x_axis.cfg"

TARGET_DIR="${KLIPPER_CONFIG_DIR:-${HOME}/printer_data/config}"
MAIN_CFG="${TARGET_DIR}/printer.cfg"

timestamp() {
  date +"%Y%m%d-%H%M%S"
}

backup_file() {
  local src="$1"
  if [[ -f "${src}" ]]; then
    local dst="${src}.bak.$(timestamp)"
    cp -a "${src}" "${dst}"
    echo "Backed up: ${src} -> ${dst}"
  fi
}

if [[ ! -f "${SOURCE_CFG}" ]]; then
  echo "Error: source config not found: ${SOURCE_CFG}" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

echo "Installing Klipper configuration..."
echo "  Source: ${SOURCE_CFG}"
echo "  Target: ${MAIN_CFG}"

backup_file "${MAIN_CFG}"
cp -a "${SOURCE_CFG}" "${MAIN_CFG}"
echo "Installed: ${MAIN_CFG}"

echo ""
echo "Configuration installed successfully!"
echo "Next steps:"
echo "  1. Review MCU serial IDs: ls -l /dev/serial/by-id/"
echo "  2. Restart Klipper: sudo systemctl restart klipper"
echo "  3. Check logs: tail -f ~/printer_data/logs/klippy.log"
echo ""
echo "Previous config backed up (if existed) with .bak.TIMESTAMP extension"
