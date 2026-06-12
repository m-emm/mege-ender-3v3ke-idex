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

set +e
helper_output="$(ssh "${REMOTE_HOST}" "${REMOTE_HELPER}${quoted_args}" 2>&1)"
helper_status=$?
set -e

if [[ "${helper_status}" -ne 0 ]]; then
  printf '%s\n' "${helper_output}"
  exit "${helper_status}"
fi

mkdir -p "${LOCAL_OUT_DIR}"

copy_remote_file() {
  local remote_path="$1"
  local local_path

  if [[ -z "${remote_path}" ]]; then
    return 0
  fi

  local_path="${LOCAL_OUT_DIR}/$(basename "${remote_path}")"
  scp -q "${REMOTE_HOST}:${remote_path}" "${local_path}"
  printf '%s\n' "${local_path}"
}

remote_plot="$(printf '%s\n' "${helper_output}" | sed -n 's/^Plot: //p' | tail -n 1)"
remote_summary="$(printf '%s\n' "${helper_output}" | sed -n 's/^Summary: //p' | tail -n 1)"
recommended_shaper="$(printf '%s\n' "${helper_output}" | sed -n 's/^Recommended shaper is /Recommended shaper: /p' | tail -n 1)"
local_plot="$(copy_remote_file "${remote_plot}")"
local_summary="$(copy_remote_file "${remote_summary}")"

if [[ -n "${axis}" ]]; then
  remote_pattern="printer_data/config/resonance/latest_${axis}*"
else
  remote_pattern="printer_data/config/resonance/latest_*"
fi

if ! scp -q "${REMOTE_HOST}:${remote_pattern}" "${LOCAL_OUT_DIR}/" >/dev/null 2>&1; then
  echo "Warning: could not copy ${remote_pattern}; check the helper output above." >&2
fi

if [[ -n "${local_plot}" ]]; then
  if [[ -n "${recommended_shaper}" ]]; then
    echo "${recommended_shaper}"
    echo ""
  fi

  echo ""
  echo "Plot written to"
  echo "${local_plot}"
  echo ""
  echo "Open with"
  printf 'open %q\n' "${local_plot}"
fi

if [[ -n "${local_summary}" ]]; then
  echo ""
  echo "Summary written to"
  echo "${local_summary}"
fi
