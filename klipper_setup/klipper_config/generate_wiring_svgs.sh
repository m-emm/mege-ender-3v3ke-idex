#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/wiring_diagrams"
DEFAULT_YAML_FILES=(
  "$SCRIPT_DIR/pico_w_btt_tmc2226_x.yaml"
  "$SCRIPT_DIR/pico_w_btt_tmc2226_y_z.yaml"
)

resolve_yaml_file() {
  local candidate="$1"

  if [[ -f "$candidate" ]]; then
    printf '%s\n' "$candidate"
    return 0
  fi

  if [[ -f "$SCRIPT_DIR/$candidate" ]]; then
    printf '%s\n' "$SCRIPT_DIR/$candidate"
    return 0
  fi

  return 1
}

collect_yaml_files() {
  if (( $# > 0 )); then
    local requested_file
    for requested_file in "$@"; do
      resolve_yaml_file "$requested_file" || {
        echo "Config file not found: $requested_file" >&2
        exit 1
      }
    done
    return 0
  fi

  local default_file
  for default_file in "${DEFAULT_YAML_FILES[@]}"; do
    resolve_yaml_file "$default_file" || {
      echo "Default config file not found: $default_file" >&2
      exit 1
    }
  done
}

mapfile -t YAML_FILES < <(collect_yaml_files "$@")

if (( ${#YAML_FILES[@]} == 0 )); then
  echo "No YAML config files found in: $SCRIPT_DIR" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

run_pinout() {
  local yaml_file="$1"
  local cmd="$PINOUT_CMD \"$yaml_file\" -o \"$OUTPUT_DIR\""
  echo "Running: $cmd"
  eval "$cmd"
}

if python3 -c "import mege_ender_3v3ke_idex.pinout.cli" >/dev/null 2>&1; then
  PINOUT_CMD="python3 -m mege_ender_3v3ke_idex.pinout"
else
  PROJECT_SRC_DEFAULT="$SCRIPT_DIR/../../src"
  if [[ -d "$PROJECT_SRC_DEFAULT" ]] && \
    PYTHONPATH="${PYTHONPATH:-}:$PROJECT_SRC_DEFAULT" \
      python3 -c "import mege_ender_3v3ke_idex.pinout.cli" >/dev/null 2>&1; then
    echo "Using local mege-ender-3v3ke-idex source: $PROJECT_SRC_DEFAULT"
    PINOUT_CMD="PYTHONPATH=\"${PYTHONPATH:-}:$PROJECT_SRC_DEFAULT\" python3 -m mege_ender_3v3ke_idex.pinout"
  else
    echo "Could not find pinout CLI." >&2
    echo "Install mege-ender-3v3ke-idex or set PYTHONPATH to its src/ directory." >&2
    exit 2
  fi
fi

for YAML_FILE in "${YAML_FILES[@]}"; do
  run_pinout "$YAML_FILE"

  BASE_NAME="$(python3 - <<'PY' "$YAML_FILE"
import sys
from pathlib import Path
import yaml

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
print(str(data.get("basename", "pinout")))
PY
 )"

  TOP_SVG="$OUTPUT_DIR/${BASE_NAME}_top.svg"
  BOTTOM_SVG="$OUTPUT_DIR/${BASE_NAME}_bottom.svg"

  echo "Generated:"
  echo "  $TOP_SVG"
  echo "  $BOTTOM_SVG"
done
