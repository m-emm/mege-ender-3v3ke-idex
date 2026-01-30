#!/usr/bin/env bash
# Helps identify which /dev/diskN is the correct removable target to flash on macOS.
#
# This script NEVER writes anything; it only inspects and prints information.
# You (the user) must decide what to flash.
#
# Recommended workflow:
#   1) Unplug the SD card / USB flash target
#   2) ./scripts/identify_flash_target.sh --baseline
#   3) Plug in the SD card / USB flash target
#   4) ./scripts/identify_flash_target.sh --diff
#   5) Use the newly appeared /dev/diskN with ./scripts/flash_sd.sh
set -euo pipefail

BASELINE_FILE_DEFAULT="/tmp/klipper_flash_targets_baseline.txt"
BASELINE_FILE="${BASELINE_FILE:-${BASELINE_FILE_DEFAULT}}"

usage() {
  cat <<EOF
Usage:
  $0 --suggest
  $0 --baseline
  $0 --diff
  $0 --usb <diskN|/dev/diskN>

Commands:
  --suggest   Print summaries for all external, physical disks and mark likely flash targets.
             Tip: for scored+sorted recommendations use ./scripts/identify_flash_target.py
  --baseline  Save current external-disk list to ${BASELINE_FILE}
  --diff      Show which disks appeared/disappeared vs baseline and print detailed info.
  --usb       Show the matching USB device block from system_profiler (best-effort).

Notes:
  - Flashing uses the whole disk (e.g. /dev/disk5), not a partition (e.g. /dev/disk5s1).
  - This script does NOT flash; it only helps identify candidates.
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

list_external_physical_disks() {
  # Example lines start with "/dev/disk5".
  diskutil list external physical | awk '/^\/dev\/disk[0-9]+/ {print $1}' | sort -u
}

get_info_value() {
  local disk_dev="$1"
  local key_substring="$2"
  diskutil info "$disk_dev" 2>/dev/null | awk -F': *' -v k="$key_substring" 'index($1, k) > 0 {print $2; exit}'
}

print_disk_details() {
  local disk_dev="$1"

  echo "---- ${disk_dev} ----"
  diskutil info "${disk_dev}" | awk '
    /Device Node/ ||
    /Device Identifier/ ||
    /Device \/ Media Name/ ||
    /Media Name/ ||
    /Device Model/ ||
    /Protocol/ ||
    /Total Size/ ||
    /Disk Size/ ||
    /Removable Media/ ||
    /Virtual:/ ||
    /Solid State/ ||
    /Device Location/ ||
    /Read-Only Media/ ||
    /Volume Name/ {print}
  '

  echo "Partitions:"
  diskutil list "${disk_dev}" | sed 's/^/  /'
}

print_suggested_targets() {
  local disks
  disks="$(list_external_physical_disks || true)"

  if [ -z "${disks}" ]; then
    echo "No external, physical disks found." >&2
    return 0
  fi

  echo "External, physical disks (you must decide what to flash):"
  echo

  local d removable external total_size media_name model protocol
  for d in ${disks}; do
    removable="$(get_info_value "${d}" 'Removable Media')"
    external="$(get_info_value "${d}" 'Device Location')"
    total_size="$(get_info_value "${d}" 'Total Size')"
    media_name="$(get_info_value "${d}" 'Device / Media Name')"
    if [ -z "${media_name}" ]; then
      media_name="$(get_info_value "${d}" 'Media Name')"
    fi
    model="$(get_info_value "${d}" 'Device Model')"
    protocol="$(get_info_value "${d}" 'Protocol')"

    # Heuristic label. Still not safe to auto-pick; only for guidance.
    local tag="INFO"
    if [ "${external}" = "External" ] && { [ "${removable}" = "Yes" ] || [ "${removable}" = "Removable" ]; }; then
      tag="LIKELY_FLASH_TARGET"
    fi

    echo "[${tag}] ${d}  ${total_size:-}" 
    [ -n "${media_name}" ] && echo "  Media Name: ${media_name}"
    [ -n "${model}" ] && echo "  Model:      ${model}"
    [ -n "${protocol}" ] && echo "  Protocol:   ${protocol}"
    [ -n "${removable}" ] && echo "  Removable:  ${removable}"
    [ -n "${external}" ] && echo "  Location:   ${external}"

    # Show partitions to catch typical pi images (bootfs + Linux) etc.
    echo "  Partitions:"
    diskutil list "${d}" | sed 's/^/    /'
    echo
  done

  cat <<'EOF'
Safety tips:
  - If you’re unsure: unplug ALL other external disks, then re-run --suggest.
  - Best method: use --baseline (no card) then --diff (insert card) and flash the NEW disk.
EOF
}

save_baseline() {
  local disks
  disks="$(list_external_physical_disks || true)"

  mkdir -p "$(dirname "${BASELINE_FILE}")" 2>/dev/null || true
  printf "%s\n" "${disks}" > "${BASELINE_FILE}"

  echo "Baseline saved to: ${BASELINE_FILE}"
  if [ -z "${disks}" ]; then
    echo "(Baseline contains no external disks.)"
  else
    echo "Baseline disks:"
    printf "  %s\n" ${disks}
  fi
}

show_diff() {
  if [ ! -f "${BASELINE_FILE}" ]; then
    echo "Baseline file not found: ${BASELINE_FILE}" >&2
    echo "Run: $0 --baseline" >&2
    exit 1
  fi

  local baseline current new_disks gone_disks
  baseline="$(sort -u "${BASELINE_FILE}" | sed '/^\s*$/d')"
  current="$(list_external_physical_disks | sed '/^\s*$/d')"

  new_disks="$(comm -13 <(printf "%s\n" "${baseline}") <(printf "%s\n" "${current}") || true)"
  gone_disks="$(comm -23 <(printf "%s\n" "${baseline}") <(printf "%s\n" "${current}") || true)"

  echo "Baseline: ${BASELINE_FILE}"
  echo

  if [ -n "${new_disks}" ]; then
    echo "New disks since baseline (strongest candidates to flash):"
    printf "  %s\n" ${new_disks}
    echo

    local d
    for d in ${new_disks}; do
      print_disk_details "${d}"
      echo
    done
  else
    echo "No new disks detected since baseline."
    echo
  fi

  if [ -n "${gone_disks}" ]; then
    echo "Disks removed since baseline:"
    printf "  %s\n" ${gone_disks}
    echo
  fi

  if [ -z "${new_disks}" ]; then
    echo "Current suggestions:"
    echo
    print_suggested_targets
  fi
}

show_usb_block() {
  local disk_arg="${1:-}"
  if [ -z "${disk_arg}" ]; then
    echo "Usage: $0 --usb <diskN|/dev/diskN>" >&2
    exit 1
  fi

  local disk_id
  disk_id="${disk_arg#/dev/}"

  require_cmd system_profiler

  # Find the first matching line number, then print a chunk around it.
  local line
  line="$(system_profiler SPUSBDataType 2>/dev/null | grep -n "BSD Name: ${disk_id}" | head -n 1 | cut -d: -f1 || true)"

  if [ -z "${line}" ]; then
    echo "No USB block found containing 'BSD Name: ${disk_id}'." >&2
    echo "(This can happen for some readers / non-USB / Thunderbolt enclosures.)" >&2
    exit 1
  fi

  local start end
  start=$((line - 30))
  end=$((line + 70))
  if [ "${start}" -lt 1 ]; then start=1; fi

  system_profiler SPUSBDataType 2>/dev/null | sed -n "${start},${end}p"
}

main() {
  require_cmd diskutil

  case "${1:-}" in
    --suggest|"")
      print_suggested_targets
      ;;
    --baseline)
      save_baseline
      ;;
    --diff)
      show_diff
      ;;
    --usb)
      shift
      show_usb_block "${1:-}"
      ;;
    --help|-h)
      usage
      ;;
    *)
      echo "Unknown option: ${1}" >&2
      echo
      usage >&2
      exit 1
      ;;
  esac
}

main "$@"
