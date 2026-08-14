#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  run_resonance_plot.sh
  run_resonance_plot.sh X [helper args...]
  run_resonance_plot.sh Y --chip right_toolhead --measure-at-z=150
  run_resonance_plot.sh --render-only /tmp/resonances_x_YYYYMMDD_HHMMSS.csv

With no arguments, or when measurement options are supplied without an axis,
this runs the default X-axis resonance test using the left toolhead
accelerometer at Z=20 mm. Each run is copied into its own timestamped
directory under runs/klipper_resonance.

Every live measurement homes all axes automatically before running
TEST_RESONANCES.

IDEX T1 (right carriage) X-axis resonance:
  For a true T1 X measurement the right carriage must be the active one when
  TEST_RESONANCES runs. Prepare the printer first via Moonraker, then invoke
  this script with --chip right_toolhead:

    ssh pi@menderpi.local 'curl -s -X POST "http://localhost:7125/printer/gcode/script" -d "script=T1"'
    run_resonance_plot.sh X --chip right_toolhead

  The wrapper homes all axes after T1 is selected, then runs the T1 X sweep.

Environment:
  MENDERPI_HOST   SSH target, default pi@menderpi.local
  LOCAL_OUT_DIR   Local copy destination, default runs/klipper_resonance
EOF
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
LOCAL_OUT_DIR="${LOCAL_OUT_DIR:-${REPO_ROOT}/runs/klipper_resonance}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage >&1
  exit 0
fi

axis="custom"
axis_upper="CUSTOM"
chip="left_toolhead"
measure_at_z="20.0"
remote_args=()
has_axis=0
has_render_only=0

case "${1:-}" in
  X|x|Y|y|Z|z)
    axis="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
    axis_upper="$(printf '%s' "$1" | tr '[:lower:]' '[:upper:]')"
    remote_args=(--axis "${axis_upper}")
    has_axis=1
    shift
    remote_args+=("$@")
    ;;
  "")
    axis="x"
    axis_upper="X"
    remote_args=(--axis X --chip left_toolhead --measure-at-z=20.0)
    ;;
  *)
    remote_args=("$@")
    ;;
esac

for ((index = 0; index < ${#remote_args[@]}; index += 1)); do
  case "${remote_args[index]}" in
    --axis)
      has_axis=1
      if ((index + 1 < ${#remote_args[@]})); then
        axis="$(printf '%s' "${remote_args[index + 1]}" | tr '[:upper:]' '[:lower:]')"
        axis_upper="$(printf '%s' "${remote_args[index + 1]}" | tr '[:lower:]' '[:upper:]')"
      fi
      ;;
    --axis=*)
      has_axis=1
      axis="$(printf '%s' "${remote_args[index]#--axis=}" | tr '[:upper:]' '[:lower:]')"
      axis_upper="$(printf '%s' "${remote_args[index]#--axis=}" | tr '[:lower:]' '[:upper:]')"
      ;;
    --chip)
      if ((index + 1 < ${#remote_args[@]})); then
        chip="${remote_args[index + 1]}"
      fi
      ;;
    --chip=*)
      chip="${remote_args[index]#--chip=}"
      ;;
    --measure-at-z)
      if ((index + 1 < ${#remote_args[@]})); then
        measure_at_z="${remote_args[index + 1]}"
      fi
      ;;
    --measure-at-z=*)
      measure_at_z="${remote_args[index]#--measure-at-z=}"
      ;;
    --render-only)
      has_render_only=1
      ;;
  esac
done

if ((has_axis == 0 && has_render_only == 0)); then
  axis="x"
  axis_upper="X"
  remote_args=(--axis X "${remote_args[@]}")
fi

timestamp="$(date '+%Y-%m-%d_%H-%M-%S')"
run_name="${timestamp}_${axis_upper}_Z${measure_at_z}_${chip}"
mkdir -p "${LOCAL_OUT_DIR}"
run_suffix=0
while :; do
  if ((run_suffix == 0)); then
    candidate_run_name="${run_name}"
  else
    candidate_run_name="${run_name}_${run_suffix}"
  fi
  LOCAL_RUN_DIR="${LOCAL_OUT_DIR}/${candidate_run_name}"
  if mkdir "${LOCAL_RUN_DIR}" 2>/dev/null; then
    run_name="${candidate_run_name}"
    break
  fi
  run_suffix=$((run_suffix + 1))
done

echo "Resolving remote printer paths on ${REMOTE_HOST}..."
REMOTE_HOME="$(ssh "${REMOTE_HOST}" 'printf %s "$HOME"')"
REMOTE_RES_ROOT="${REMOTE_HOME}/printer_data/config/resonance"
REMOTE_HELPER="${REMOTE_RES_ROOT}/run_resonance_plot.py"
REMOTE_OUTPUT_DIR="${REMOTE_RES_ROOT}/runs/${run_name}"
remote_args+=(--output-dir "${REMOTE_OUTPUT_DIR}")

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

if ! scp -q -r "${REMOTE_HOST}:${REMOTE_OUTPUT_DIR}/." "${LOCAL_RUN_DIR}/"; then
  echo "Warning: could not copy the complete remote run directory: ${REMOTE_OUTPUT_DIR}" >&2
fi

remote_plot="$(printf '%s\n' "${helper_output}" | sed -n 's/^Plot: //p' | tail -n 1)"
remote_summary="$(printf '%s\n' "${helper_output}" | sed -n 's/^Summary: //p' | tail -n 1)"
recommended_shaper="$(printf '%s\n' "${helper_output}" | sed -n 's/^Recommended shaper is /Recommended shaper: /p' | tail -n 1)"

if [[ -n "${remote_plot}" && -f "${LOCAL_RUN_DIR}/$(basename "${remote_plot}")" ]]; then
  local_plot="${LOCAL_RUN_DIR}/$(basename "${remote_plot}")"
  if [[ -n "${recommended_shaper}" ]]; then
    echo "${recommended_shaper}"
    echo
  fi

  echo
  echo "Plot written to"
  echo "${local_plot}"
  echo
  echo "Open with"
  printf 'open %q\n' "${local_plot}"
fi

if [[ -n "${remote_summary}" && -f "${LOCAL_RUN_DIR}/$(basename "${remote_summary}")" ]]; then
  echo
  echo "Summary written to"
  echo "${LOCAL_RUN_DIR}/$(basename "${remote_summary}")"
fi

echo "Run artifacts directory: ${LOCAL_RUN_DIR}"
