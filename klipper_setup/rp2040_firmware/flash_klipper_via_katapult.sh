#!/bin/bash
# Flash Klipper to an RP2040 using the Katapult bootloader (USB/UART)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
KATAPULT_DIR="${SCRIPT_DIR}/katapult"
VENV_DIR="${SCRIPT_DIR}/katapult_venv"
DEFAULT_FIRMWARE_BIN="${SCRIPT_DIR}/klipper/out/klipper.bin"

DEVICE=""
FIRMWARE_BIN="${DEFAULT_FIRMWARE_BIN}"

usage() {
  cat <<EOF
Usage: $(basename "$0") -d <device> [-f <klipper.bin>]

Options:
  -d  Serial device (examples: /dev/serial/by-id/... or /dev/cu.usbmodemXXXX)
  -f  Path to Klipper binary (default: ${DEFAULT_FIRMWARE_BIN})
  -h  Show this help

Notes:
- This script uses Katapult's scripts/flashtool.py.
- For best results, put the board into Katapult bootloader mode first (often double-tap RESET).
EOF
}

while getopts ":d:f:h" opt; do
  case "${opt}" in
    d) DEVICE="${OPTARG}" ;;
    f) FIRMWARE_BIN="${OPTARG}" ;;
    h) usage; exit 0 ;;
    \?) echo "Unknown option: -${OPTARG}" >&2; usage >&2; exit 2 ;;
    :)  echo "Option -${OPTARG} requires an argument" >&2; usage >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))

if [[ -z "${DEVICE}" ]]; then
  # Attempt Linux auto-detect
  if [[ -d /dev/serial/by-id ]]; then
    maybe="$(ls -1 /dev/serial/by-id 2>/dev/null | grep -i katapult | head -n1 || true)"
    if [[ -n "${maybe}" ]]; then
      DEVICE="/dev/serial/by-id/${maybe}"
      echo "==> Auto-detected Katapult device: ${DEVICE}"
    fi
  fi
fi

if [[ -z "${DEVICE}" ]]; then
  echo "ERROR: No device specified. Use -d <device>." >&2
  echo "Tip (Linux): ls /dev/serial/by-id | grep -i katapult" >&2
  echo "Tip (macOS): ls /dev/cu.* | grep -i usbmodem" >&2
  exit 1
fi

if [[ ! -f "${FIRMWARE_BIN}" ]]; then
  echo "ERROR: Klipper binary not found at ${FIRMWARE_BIN}" >&2
  echo "Build Klipper for Katapult first (bootloader offset), e.g.:" >&2
  echo "  ./build_rp2040_docker.sh -k" >&2
  exit 1
fi

if [[ ! -d "${KATAPULT_DIR}/.git" ]]; then
  echo "==> Katapult repo not found, cloning..."
  git clone https://github.com/Arksine/katapult.git "${KATAPULT_DIR}"
fi

if [[ ! -x "${VENV_DIR}/bin/python3" ]]; then
  echo "==> Creating venv and installing pyserial (one-time)..."
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/pip" install --upgrade pip
  "${VENV_DIR}/bin/pip" install pyserial
fi

echo "==> Flashing Klipper via Katapult..."
echo "    Device:   ${DEVICE}"
echo "    Firmware: ${FIRMWARE_BIN}"

"${VENV_DIR}/bin/python3" "${KATAPULT_DIR}/scripts/flashtool.py" -d "${DEVICE}" -f "${FIRMWARE_BIN}"

echo "==> Flash complete."
