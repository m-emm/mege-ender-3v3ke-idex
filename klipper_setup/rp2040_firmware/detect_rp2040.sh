#!/bin/bash
# Detect RP2040 board state: BOOTSEL, Klipper, or Katapult
# Returns status and device path if applicable

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color output helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

usage() {
  cat <<EOF
Usage: $(basename "$0") [-q]

Options:
  -q   Quiet mode (machine-readable output only)
  -h   Show this help

Detects the state of connected RP2040 devices:
- BOOTSEL mode (RPI-RP2 USB drive)
- Klipper firmware (USB serial device)
- Katapult bootloader (USB serial device)

Exit codes:
  0 - Device(s) detected successfully
  1 - No RP2040 device found
  2 - Multiple devices found (ambiguous)
EOF
}

QUIET=0
while getopts ":qh" opt; do
  case "${opt}" in
    q) QUIET=1 ;;
    h) usage; exit 0 ;;
    \?) echo "Unknown option: -${OPTARG}" >&2; usage >&2; exit 2 ;;
  esac
done

# Detect BOOTSEL mode (RPI-RP2 mass storage)
detect_bootsel() {
  for mp in /Volumes/RPI-RP2 "/media/$USER/RPI-RP2" /media/RPI-RP2; do
    if [[ -d "${mp}" ]]; then
      echo "${mp}"
      return 0
    fi
  done
  return 1
}

# Detect Klipper devices (macOS and Linux)
detect_klipper() {
  local devices=()
  
  # Linux: check /dev/serial/by-id
  if [[ -d /dev/serial/by-id ]]; then
    while IFS= read -r dev; do
      if [[ -n "${dev}" ]]; then
        devices+=("/dev/serial/by-id/${dev}")
      fi
    done < <(ls /dev/serial/by-id 2>/dev/null | grep -i klipper || true)
  fi
  
  # macOS: check USB devices via system_profiler (slower but accurate)
  if [[ "$(uname)" == "Darwin" ]] && command -v system_profiler >/dev/null 2>&1; then
    # Extract Klipper devices from USB tree
    local usb_data
    usb_data="$(system_profiler SPUSBDataType 2>/dev/null || true)"
    
    # Look for "klipper" or known Klipper USB IDs (0x1d50:0x614e is common)
    if echo "${usb_data}" | grep -qi "klipper"; then
      # Try to find the serial device path
      while IFS= read -r dev; do
        if [[ -c "${dev}" ]]; then
          devices+=("${dev}")
        fi
      done < <(ls /dev/cu.usbmodem* 2>/dev/null || true)
    fi
  fi
  
  # Fallback macOS: just check for usbmodem devices and filter by name
  if [[ "$(uname)" == "Darwin" ]] && [[ ${#devices[@]} -eq 0 ]]; then
    while IFS= read -r dev; do
      if [[ -c "${dev}" ]]; then
        # Try to get device info and check if it's NOT katapult
        if ! echo "${dev}" | grep -qi "katapult"; then
          # Basic heuristic: if it's a usbmodem and not katapult, might be klipper
          devices+=("${dev}")
        fi
      fi
    done < <(ls /dev/cu.usbmodem* 2>/dev/null | head -n5 || true)
  fi
  
  if [[ ${#devices[@]} -gt 0 ]]; then
    printf '%s\n' "${devices[@]}"
    return 0
  fi
  return 1
}

# Detect Katapult devices (macOS and Linux)
detect_katapult() {
  local devices=()
  
  # Linux: check /dev/serial/by-id
  if [[ -d /dev/serial/by-id ]]; then
    while IFS= read -r dev; do
      if [[ -n "${dev}" ]]; then
        devices+=("/dev/serial/by-id/${dev}")
      fi
    done < <(ls /dev/serial/by-id 2>/dev/null | grep -i katapult || true)
  fi
  
  # macOS: check USB devices via system_profiler
  if [[ "$(uname)" == "Darwin" ]] && command -v system_profiler >/dev/null 2>&1; then
    local usb_data
    usb_data="$(system_profiler SPUSBDataType 2>/dev/null || true)"
    
    if echo "${usb_data}" | grep -qi "katapult"; then
      while IFS= read -r dev; do
        if [[ -c "${dev}" ]]; then
          devices+=("${dev}")
        fi
      done < <(ls /dev/cu.usbmodem* 2>/dev/null || true)
    fi
  fi
  
  if [[ ${#devices[@]} -gt 0 ]]; then
    printf '%s\n' "${devices[@]}"
    return 0
  fi
  return 1
}

# Main detection logic
main() {
  local bootsel_path=""
  local klipper_devices=()
  local katapult_devices=()
  local found_any=0
  
  # Detect BOOTSEL
  if bootsel_path="$(detect_bootsel)"; then
    found_any=1
    if [[ ${QUIET} -eq 0 ]]; then
      echo -e "${YELLOW}[BOOTSEL]${NC} RP2040 in bootloader mode (system firmware)"
      echo "  Mount: ${bootsel_path}"
      echo ""
      echo "Actions available:"
      echo "  - Flash Katapult:     (cd ../katapult_rp2040 && ./flash.sh)"
      echo "  - Flash Klipper UF2:  ./build_rp2040_docker.sh -d && ./flash_rp2040.sh"
    else
      echo "BOOTSEL:${bootsel_path}"
    fi
  fi
  
  # Detect Katapult
  while IFS= read -r dev; do
    [[ -n "${dev}" ]] && katapult_devices+=("${dev}")
  done < <(detect_katapult)
  
  if [[ ${#katapult_devices[@]} -gt 0 ]]; then
    found_any=1
    if [[ ${QUIET} -eq 0 ]]; then
      echo -e "${BLUE}[KATAPULT]${NC} Katapult bootloader detected"
      for dev in "${katapult_devices[@]}"; do
        echo "  Device: ${dev}"
      done
      echo ""
      echo "Actions available:"
      echo "  - Flash Klipper via Katapult: ./build_rp2040_docker.sh -k && ./flash_klipper_via_katapult.sh -d ${katapult_devices[0]}"
      echo "  - Re-enter BOOTSEL: Hold BOOTSEL and tap RESET (or power cycle)"
    else
      for dev in "${katapult_devices[@]}"; do
        echo "KATAPULT:${dev}"
      done
    fi
  fi
  
  # Detect Klipper
  while IFS= read -r dev; do
    [[ -n "${dev}" ]] && klipper_devices+=("${dev}")
  done < <(detect_klipper)
  
  if [[ ${#klipper_devices[@]} -gt 0 ]]; then
    found_any=1
    if [[ ${QUIET} -eq 0 ]]; then
      echo -e "${GREEN}[KLIPPER]${NC} Klipper firmware detected"
      for dev in "${klipper_devices[@]}"; do
        echo "  Device: ${dev}"
      done
      echo ""
      echo "Actions available:"
      echo "  - Update Klipper: ./build_rp2040_docker.sh -k && ./flash_klipper_via_katapult.sh -d ${klipper_devices[0]}"
      echo "    (if Katapult is installed, double-tap RESET to enter bootloader)"
      echo "  - Reflash from scratch: Enter BOOTSEL mode and use direct flash workflow"
    else
      for dev in "${klipper_devices[@]}"; do
        echo "KLIPPER:${dev}"
      done
    fi
  fi
  
  if [[ ${found_any} -eq 0 ]]; then
    if [[ ${QUIET} -eq 0 ]]; then
      echo -e "${RED}[NOT FOUND]${NC} No RP2040 device detected"
      echo ""
      echo "Troubleshooting:"
      echo "  1. Connect the RP2040 board via USB"
      echo "  2. For BOOTSEL mode: hold BOOTSEL button while connecting power"
      echo "  3. Check 'ls /dev/cu.*' (macOS) or 'ls /dev/serial/by-id' (Linux)"
    else
      echo "NONE"
    fi
    exit 1
  fi
  
  exit 0
}

main "$@"
