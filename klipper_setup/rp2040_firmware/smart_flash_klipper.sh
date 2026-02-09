#!/bin/bash
# Smart Klipper flash script
# - Detects current board state
# - Only flashes Katapult if needed
# - Flashes Klipper appropriately based on current state

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]

Options:
  -f   Force reflash (even if Katapult detected)
  -h   Show this help

This script intelligently flashes Klipper firmware:
1. Detects current board state (BOOTSEL/Klipper/Katapult)
2. If in BOOTSEL and Katapult not installed: offers to install Katapult first
3. If Katapult detected: flashes Klipper via Katapult (fast)
4. If in BOOTSEL with force flag: flashes Klipper directly (UF2)
EOF
}

FORCE=0
while getopts ":fh" opt; do
  case "${opt}" in
    f) FORCE=1 ;;
    h) usage; exit 0 ;;
    \?) echo "Unknown option: -${OPTARG}" >&2; usage >&2; exit 2 ;;
  esac
done

echo "==> Detecting board state..."
detection_output="$("${SCRIPT_DIR}/detect_rp2040.sh" -q)"

if echo "${detection_output}" | grep -q "^KATAPULT:"; then
  device="$(echo "${detection_output}" | grep "^KATAPULT:" | head -n1 | cut -d: -f2)"
  echo "==> Katapult detected at: ${device}"
  echo "==> Building Klipper for Katapult..."
  "${SCRIPT_DIR}/build_rp2040_docker.sh" -k
  
  echo ""
  echo "==> Ready to flash. Put board into Katapult bootloader mode:"
  echo "    (Usually: double-tap RESET button)"
  read -p "Press Enter when ready, or Ctrl+C to cancel... " -r
  
  "${SCRIPT_DIR}/flash_klipper_via_katapult.sh" -d "${device}"
  echo ""
  echo "==> Done! Klipper updated via Katapult."
  
elif echo "${detection_output}" | grep -q "^KLIPPER:"; then
  device="$(echo "${detection_output}" | grep "^KLIPPER:" | head -n1 | cut -d: -f2)"
  echo "==> Klipper already running at: ${device}"
  echo ""
  echo "To update Klipper:"
  echo "  1. If you have Katapult: double-tap RESET and re-run this script"
  echo "  2. If no Katapult: enter BOOTSEL mode and run with -f flag"
  exit 0
  
elif echo "${detection_output}" | grep -q "^BOOTSEL:"; then
  mountpoint="$(echo "${detection_output}" | grep "^BOOTSEL:" | head -n1 | cut -d: -f2)"
  echo "==> Board in BOOTSEL mode at: ${mountpoint}"
  
  if [[ ${FORCE} -eq 0 ]]; then
    echo ""
    echo "Recommended: Install Katapult bootloader first for future easy updates"
    echo ""
    read -p "Install Katapult? [Y/n] " -r
    if [[ ! "${REPLY}" =~ ^[Nn]$ ]]; then
      echo "==> Building Katapult..."
      "${SCRIPT_DIR}/build_katapult_docker.sh"
      
      echo "==> Flashing Katapult..."
      "${SCRIPT_DIR}/flash_katapult.sh"
      
      echo ""
      echo "==> Katapult installed! Now building Klipper..."
      "${SCRIPT_DIR}/build_rp2040_docker.sh" -k
      
      echo ""
      echo "==> Put board back into Katapult bootloader mode:"
      echo "    (Power cycle, then double-tap RESET)"
      read -p "Press Enter when ready, or Ctrl+C to cancel... " -r
      
      # Re-detect to get Katapult device path
      detection_output="$("${SCRIPT_DIR}/detect_rp2040.sh" -q)"
      if echo "${detection_output}" | grep -q "^KATAPULT:"; then
        device="$(echo "${detection_output}" | grep "^KATAPULT:" | head -n1 | cut -d: -f2)"
        "${SCRIPT_DIR}/flash_klipper_via_katapult.sh" -d "${device}"
        echo ""
        echo "==> Done! Katapult + Klipper installed."
      else
        echo "ERROR: Could not detect Katapult device. Try again." >&2
        exit 1
      fi
    else
      echo "==> Building Klipper for direct flash..."
      "${SCRIPT_DIR}/build_rp2040_docker.sh" -d
      
      echo "==> Flashing Klipper (direct UF2)..."
      "${SCRIPT_DIR}/flash_rp2040.sh"
      
      echo ""
      echo "==> Done! Klipper installed (no Katapult)."
    fi
  else
    echo "==> Force flag set, flashing Klipper directly..."
    "${SCRIPT_DIR}/build_rp2040_docker.sh" -d
    "${SCRIPT_DIR}/flash_rp2040.sh"
    echo ""
    echo "==> Done! Klipper installed (direct flash)."
  fi
  
else
  echo "ERROR: No RP2040 device detected!" >&2
  echo "" >&2
  echo "Please connect your RP2040 board:" >&2
  echo "  - For fresh flash: hold BOOTSEL and connect power" >&2
  echo "  - For Katapult update: double-tap RESET button" >&2
  exit 1
fi
