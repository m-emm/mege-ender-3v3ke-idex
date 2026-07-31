#!/usr/bin/env bash

set -euo pipefail

HOST="pi@menderpi.local"

if [ $# -ne 1 ]; then
    echo "Usage:"
    echo "  $0 \"G28\""
    echo "  echo \"G28\" | $0 -"
    exit 1
fi

if [ "$1" = "-" ]; then
    GCODE="$(cat)"
else
    GCODE="$1"
fi

printf '{"script":"%s"}\n' "$GCODE" |
ssh -T "$HOST" \
  "curl -fsS \
    -X POST http://127.0.0.1:7125/printer/gcode/script \
    -H 'Content-Type: application/json' \
    --data-binary @-"

