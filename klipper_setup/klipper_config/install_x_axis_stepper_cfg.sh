#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_CFG="${SCRIPT_DIR}/x_axis_stepper_endstop_pico_w.cfg"

TARGET_DIR="${KLIPPER_CONFIG_DIR:-${HOME}/printer_data/config}"
TARGET_CFG="${TARGET_DIR}/x_axis_stepper_endstop_pico_w.cfg"
MAIN_CFG="${TARGET_DIR}/printer.cfg"
INCLUDE_LINE="[include x_axis_stepper_endstop_pico_w.cfg]"
SAVE_CONFIG_MARKER="#*# <---------------------- SAVE_CONFIG ---------------------->"

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

insert_include_line() {
  local file="$1"
  local tmp
  tmp="$(mktemp)"

  awk -v include_line="${INCLUDE_LINE}" -v marker="${SAVE_CONFIG_MARKER}" '
    $0 == marker && !inserted {
      print include_line
      inserted=1
    }
    { print }
    END {
      if (!inserted) {
        print ""
        print include_line
      }
    }
  ' "${file}" >"${tmp}"

  mv "${tmp}" "${file}"
}

if [[ ! -f "${SOURCE_CFG}" ]]; then
  echo "Error: source config not found: ${SOURCE_CFG}" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

backup_file "${TARGET_CFG}"
cp -a "${SOURCE_CFG}" "${TARGET_CFG}"
echo "Installed: ${TARGET_CFG}"

if [[ ! -f "${MAIN_CFG}" ]]; then
  cat >"${MAIN_CFG}" <<EOF
# Autocreated by install_x_axis_stepper_cfg.sh
${INCLUDE_LINE}
EOF
  echo "Created: ${MAIN_CFG}"
  echo "Warning: ${MAIN_CFG} has only an include. Add your full printer config before printing."
  exit 0
fi

if grep -Fqx "${INCLUDE_LINE}" "${MAIN_CFG}"; then
  echo "Include already present in: ${MAIN_CFG}"
  exit 0
fi

backup_file "${MAIN_CFG}"
insert_include_line "${MAIN_CFG}"
echo "Added include to: ${MAIN_CFG}"
echo "Done. Restart Klipper: sudo systemctl restart klipper"
