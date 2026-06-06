#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  run_resonance_plot.sh X [helper args...]
  run_resonance_plot.sh Y --chip right_toolhead
  run_resonance_plot.sh --render-only /tmp/resonances_x_YYYYMMDD_HHMMSS.csv

Environment:
  MENDERPI_HOST   SSH target, default pi@menderpi.local
  LOCAL_OUT_DIR   Local copy destination, default runs/klipper_resonance
EOF
}

if [[ "$#" -lt 1 ]]; then
  usage
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
REMOTE_HELPER="~/printer_data/config/resonance/run_resonance_plot.py"
LOCAL_OUT_DIR="${LOCAL_OUT_DIR:-${REPO_ROOT}/runs/klipper_resonance}"

axis=""
remote_args=()

case "${1:-}" in
  X|x|Y|y|Z|z)
    axis="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
    remote_args=(--axis "$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')")
    shift
    remote_args+=("$@")
    ;;
  *)
    remote_args=("$@")
    ;;
esac

quoted_args=""
for arg in "${remote_args[@]}"; do
  printf -v quoted_arg '%q' "${arg}"
  quoted_args+=" ${quoted_arg}"
done

echo "Running resonance helper on ${REMOTE_HOST}..."
ssh "${REMOTE_HOST}" "${REMOTE_HELPER}${quoted_args}"

mkdir -p "${LOCAL_OUT_DIR}"

if [[ -n "${axis}" ]]; then
  remote_pattern="printer_data/config/resonance/latest_${axis}*"
else
  remote_pattern="printer_data/config/resonance/latest_*"
fi

echo "Copying latest resonance outputs to ${LOCAL_OUT_DIR}..."
if ! scp -q "${REMOTE_HOST}:${remote_pattern}" "${LOCAL_OUT_DIR}/"; then
  echo "Warning: could not copy ${remote_pattern}; check the helper output above." >&2
fi

echo "Local resonance outputs:"
find "${LOCAL_OUT_DIR}" -maxdepth 1 -type f -name 'latest_*' -print | sort
