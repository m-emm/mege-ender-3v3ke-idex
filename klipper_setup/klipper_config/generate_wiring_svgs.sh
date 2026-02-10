#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
YAML_FILE="${1:-$SCRIPT_DIR/pico_w_btt_tmc2226.yaml}"
OUTPUT_DIR="$SCRIPT_DIR"

if [[ ! -f "$YAML_FILE" ]]; then
  echo "Config file not found: $YAML_FILE" >&2
  exit 1
fi

run_pinout() {
  local cmd="$1"
  echo "Running: $cmd"
  eval "$cmd"
}

if python3 -c "import mege_ender_3v3ke_idex.pinout.cli" >/dev/null 2>&1; then
  run_pinout "python3 -m mege_ender_3v3ke_idex.pinout \"$YAML_FILE\" -o \"$OUTPUT_DIR\""
else
  PROJECT_SRC_DEFAULT="$SCRIPT_DIR/../../src"
  if [[ -d "$PROJECT_SRC_DEFAULT" ]] && \
    PYTHONPATH="${PYTHONPATH:-}:$PROJECT_SRC_DEFAULT" \
      python3 -c "import mege_ender_3v3ke_idex.pinout.cli" >/dev/null 2>&1; then
    echo "Using local mege-ender-3v3ke-idex source: $PROJECT_SRC_DEFAULT"
    PYTHONPATH="${PYTHONPATH:-}:$PROJECT_SRC_DEFAULT" \
      run_pinout "python3 -m mege_ender_3v3ke_idex.pinout \"$YAML_FILE\" -o \"$OUTPUT_DIR\""
  else
    echo "Could not find pinout CLI." >&2
    echo "Install mege-ender-3v3ke-idex or set PYTHONPATH to its src/ directory." >&2
    exit 2
  fi
fi

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
