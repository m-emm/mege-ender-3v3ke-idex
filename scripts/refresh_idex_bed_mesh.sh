#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
IDEX_EDDY_PHASE=mesh \
  IDEX_CALIBRATION_RUN_SCOPE="${IDEX_CALIBRATION_RUN_SCOPE:-mesh_refresh}" \
  exec "${SCRIPT_DIR}/run_eddy_tap_bed_calibration.sh"
