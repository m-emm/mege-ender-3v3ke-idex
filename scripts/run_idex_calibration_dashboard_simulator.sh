#!/usr/bin/env bash
# Start the local-only IDEX calibration dashboard simulator.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PORT=8787
STATE_DIR="${REPO_ROOT}/.cache/idex-calibration-simulator"

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --port)
            PORT="${2:?--port requires a value}"
            shift 2
            ;;
        --state-dir)
            STATE_DIR="${2:?--state-dir requires a value}"
            shift 2
            ;;
        -h|--help)
            cat <<'EOF'
Usage: scripts/run_idex_calibration_dashboard_simulator.sh [--port PORT] [--state-dir PATH]

Serves the production calibration dashboard against localhost-only simulated
Moonraker and calibration state. It never contacts the printer.
EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

exec python3 "${SCRIPT_DIR}/idex_calibration_dashboard_simulator.py" \
    --port "${PORT}" --state-dir "${STATE_DIR}"
