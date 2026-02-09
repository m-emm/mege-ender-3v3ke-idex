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

if command -v shellforgepy-pinout >/dev/null 2>&1; then
  run_pinout "shellforgepy-pinout \"$YAML_FILE\" -o \"$OUTPUT_DIR\""
elif python3 -c "import shellforgepy_meges_workshop.pinout.cli" >/dev/null 2>&1; then
  run_pinout "python3 -m shellforgepy_meges_workshop.pinout \"$YAML_FILE\" -o \"$OUTPUT_DIR\""
else
  SF_SRC_DEFAULT="$SCRIPT_DIR/../../../shellforgepy-meges-workshop/src"
  if [[ -d "$SF_SRC_DEFAULT" ]]; then
    echo "Using local shellforgepy-meges-workshop source: $SF_SRC_DEFAULT"
    PYTHONPATH="${PYTHONPATH:-}:$SF_SRC_DEFAULT" \
      run_pinout "python3 -m shellforgepy_meges_workshop.pinout \"$YAML_FILE\" -o \"$OUTPUT_DIR\""
  else
    echo "Could not find shellforgepy pinout CLI." >&2
    echo "Install shellforgepy-meges-workshop or set PYTHONPATH to its src/ directory." >&2
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

