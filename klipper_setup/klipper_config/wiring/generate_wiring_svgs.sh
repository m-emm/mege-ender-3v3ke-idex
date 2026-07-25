#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/diagrams"
DEFAULT_YAML_FILES=(
  "${SCRIPT_DIR}/pico_w_btt_tmc2226_x.yaml"
  "${SCRIPT_DIR}/pico_w_btt_tmc2226_y_z.yaml"
  "${SCRIPT_DIR}/rp2040plus_btt_tmc5160t_plus_y.yaml"
)

MEGE_CIRCUITS_SRC="${REPO_ROOT}/../mege-circuits/src"
if [[ -d "${MEGE_CIRCUITS_SRC}" ]]; then
  export PYTHONPATH="${MEGE_CIRCUITS_SRC}${PYTHONPATH:+:${PYTHONPATH}}"
fi

usage() {
  cat >&2 <<'EOF'
Usage:
  generate_wiring_svgs.sh [--check] [pinout.yaml ...]

Without --check, generate SVGs into wiring/diagrams/.
With --check, regenerate into a temporary directory and fail if committed SVGs differ.
Run with no YAML arguments to generate all active and review wiring diagrams.
EOF
}

MODE="write"
REQUESTED_FILES=()
while (($#)); do
  case "$1" in
    --check)
      MODE="check"
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      REQUESTED_FILES+=("$1")
      ;;
  esac
  shift
done

resolve_yaml_file() {
  local candidate="$1"

  if [[ -f "${candidate}" ]]; then
    printf '%s\n' "${candidate}"
    return 0
  fi

  if [[ -f "${SCRIPT_DIR}/${candidate}" ]]; then
    printf '%s\n' "${SCRIPT_DIR}/${candidate}"
    return 0
  fi

  return 1
}

collect_yaml_files() {
  if ((${#REQUESTED_FILES[@]} > 0)); then
    local requested_file
    for requested_file in "${REQUESTED_FILES[@]}"; do
      resolve_yaml_file "${requested_file}" || {
        echo "Config file not found: ${requested_file}" >&2
        exit 1
      }
    done
    return 0
  fi

  local default_file
  for default_file in "${DEFAULT_YAML_FILES[@]}"; do
    resolve_yaml_file "${default_file}" || {
      echo "Default config file not found: ${default_file}" >&2
      exit 1
    }
  done
}

mapfile -t YAML_FILES < <(collect_yaml_files)
if ((${#YAML_FILES[@]} == 0)); then
  echo "No YAML config files selected." >&2
  exit 1
fi

RUN_CUSTOM_GENERATORS=0
if ((${#REQUESTED_FILES[@]} == 0)); then
  RUN_CUSTOM_GENERATORS=1
fi

run_pinout() {
  local yaml_file="$1"
  local output_dir="$2"
  python3 -m mege_circuits.pinout "${yaml_file}" -o "${output_dir}"
}

run_custom_generators() {
  local output_dir="$1"
  PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}" python3 - "${output_dir}" <<'PY'
from pathlib import Path
import sys

from pico_tb6600_stripboard_interface import render_tb6600_schematic
from pico_tb6600_stripboard_layout import render_tb6600_stripboard_build
from tmc5160t_plus_84dd4cb_delta import render_tmc5160t_plus_84dd4cb_delta
from tmc5160t_plus_dual_rail_delta import render_tmc5160t_plus_dual_rail_delta
from tmc5160t_plus_power_sequencing import render_tmc5160t_plus_power_sequencing

output_dir = Path(sys.argv[1])
render_tb6600_schematic(output_dir)
render_tb6600_stripboard_build(output_dir)
render_tmc5160t_plus_power_sequencing(output_dir)
render_tmc5160t_plus_84dd4cb_delta(output_dir)
render_tmc5160t_plus_dual_rail_delta(output_dir)
PY
}

pinout_basename() {
  local yaml_file="$1"
  python3 - "${yaml_file}" <<'PY'
from pathlib import Path
import sys
import yaml

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
print(str(data.get("basename", "pinout")))
PY
}

pinout_has_discrete_view() {
  local yaml_file="$1"
  python3 - "${yaml_file}" <<'PY'
from pathlib import Path
import sys
import yaml

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
print("1" if data.get("component_placements") else "0")
PY
}

require_nonempty() {
  local path="$1"
  if [[ ! -s "${path}" ]]; then
    echo "Expected generated artifact is missing or empty: ${path}" >&2
    exit 1
  fi
}

if [[ "${MODE}" == "check" ]]; then
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/idex-wiring-svgs.XXXXXX")"
  trap 'rm -rf "${TMP_DIR}"' EXIT
  for yaml_file in "${YAML_FILES[@]}"; do
    run_pinout "${yaml_file}" "${TMP_DIR}"
  done
  if [[ "${RUN_CUSTOM_GENERATORS}" == "1" ]]; then
    run_custom_generators "${TMP_DIR}"
  fi
  for yaml_file in "${YAML_FILES[@]}"; do
    base_name="$(pinout_basename "${yaml_file}")"
    diff -u "${OUTPUT_DIR}/${base_name}_top.svg" "${TMP_DIR}/${base_name}_top.svg"
    diff -u "${OUTPUT_DIR}/${base_name}_bottom.svg" "${TMP_DIR}/${base_name}_bottom.svg"
    if [[ "$(pinout_has_discrete_view "${yaml_file}")" == "1" ]]; then
      diff -u \
        "${OUTPUT_DIR}/${base_name}_top_discrete.svg" \
        "${TMP_DIR}/${base_name}_top_discrete.svg"
    fi
  done
  if [[ "${RUN_CUSTOM_GENERATORS}" == "1" ]]; then
    for stem in \
      pico_tb6600_stripboard_interface \
      pico_tb6600_stripboard_interface_stripboard \
      tmc5160t_plus_power_sequencing
    do
      diff -u "${OUTPUT_DIR}/${stem}.svg" "${TMP_DIR}/${stem}.svg"
      require_nonempty "${OUTPUT_DIR}/${stem}.png"
      require_nonempty "${TMP_DIR}/${stem}.png"
    done
    for stem in \
      rp2040plus_btt_tmc5160t_plus_y_top_discrete_84dd4cb_delta \
      rp2040plus_btt_tmc5160t_plus_y_bottom_84dd4cb_delta \
      rp2040plus_btt_tmc5160t_plus_y_top_discrete_dual_rail_delta \
      rp2040plus_btt_tmc5160t_plus_y_bottom_dual_rail_delta
    do
      diff -u "${OUTPUT_DIR}/${stem}.svg" "${TMP_DIR}/${stem}.svg"
    done
  fi
  echo "Wiring SVG check passed."
  exit 0
fi

mkdir -p "${OUTPUT_DIR}"
for yaml_file in "${YAML_FILES[@]}"; do
  run_pinout "${yaml_file}" "${OUTPUT_DIR}"
done
if [[ "${RUN_CUSTOM_GENERATORS}" == "1" ]]; then
  run_custom_generators "${OUTPUT_DIR}"
fi
