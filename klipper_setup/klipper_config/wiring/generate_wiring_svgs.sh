#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../../.." && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/diagrams"
DEFAULT_YAML_FILES=(
  "${SCRIPT_DIR}/pico_w_btt_tmc2226_x.yaml"
  "${SCRIPT_DIR}/pico_w_btt_tmc2226_y_z.yaml"
)

usage() {
  cat >&2 <<'EOF'
Usage:
  generate_wiring_svgs.sh [--check] [pinout.yaml ...]

Without --check, generate SVGs into wiring/diagrams/.
With --check, regenerate into a temporary directory and fail if committed SVGs differ.
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

run_pinout() {
  local yaml_file="$1"
  local output_dir="$2"
  PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 -m mege_ender_3v3ke_idex.pinout "${yaml_file}" -o "${output_dir}"
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

if [[ "${MODE}" == "check" ]]; then
  TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/idex-wiring-svgs.XXXXXX")"
  trap 'rm -rf "${TMP_DIR}"' EXIT
  for yaml_file in "${YAML_FILES[@]}"; do
    run_pinout "${yaml_file}" "${TMP_DIR}"
  done
  for yaml_file in "${YAML_FILES[@]}"; do
    base_name="$(pinout_basename "${yaml_file}")"
    diff -u "${OUTPUT_DIR}/${base_name}_top.svg" "${TMP_DIR}/${base_name}_top.svg"
    diff -u "${OUTPUT_DIR}/${base_name}_bottom.svg" "${TMP_DIR}/${base_name}_bottom.svg"
  done
  echo "Wiring SVG check passed."
  exit 0
fi

mkdir -p "${OUTPUT_DIR}"
for yaml_file in "${YAML_FILES[@]}"; do
  run_pinout "${yaml_file}" "${OUTPUT_DIR}"
done
