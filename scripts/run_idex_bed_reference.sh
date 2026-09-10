#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
batch_id="${IDEX_CALIBRATION_BATCH_ID:-${timestamp}_bed_reference}"
run_dir="${IDEX_BED_CALIBRATION_RUN_DIR:-${REPO_ROOT}/runs/idex_calibration/${batch_id}/bed_calibration/reference}"

# This is the public chapter route for steps 1–3.  The full coordinator uses
# exactly the same path, preserving one artifact and acceptance contract.
IDEX_CALIBRATION_BATCH_ID="${batch_id}" \
IDEX_CALIBRATION_RUN_SCOPE="${IDEX_CALIBRATION_RUN_SCOPE:-bed_reference}" \
IDEX_EDDY_PHASE=reference \
IDEX_BED_CALIBRATION_RUN_DIR="${run_dir}" \
  exec "${SCRIPT_DIR}/run_eddy_tap_bed_calibration.sh"
