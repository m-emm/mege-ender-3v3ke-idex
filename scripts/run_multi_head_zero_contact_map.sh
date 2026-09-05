#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
LOCAL_OUT_ROOT="${LOCAL_OUT_DIR:-${REPO_ROOT}/runs/multi_head_zero_contact}"
REMOTE_HELPER='~/printer_data/config/multi_head_zero_probe/run_multi_head_zero_contact_map.py'
timestamp="$(date '+%Y-%m-%d_%H-%M-%S')"
selected_tool="T0"
for ((arg_index = 1; arg_index <= $#; arg_index++)); do
  argument="${!arg_index}"
  case "${argument}" in
    --tool)
      next_index=$((arg_index + 1))
      selected_tool="${!next_index}"
      ;;
    --tool=*)
      selected_tool="${argument#--tool=}"
      ;;
  esac
done
if [[ "${selected_tool}" != "T0" && "${selected_tool}" != "T1" ]]; then
  echo "--tool must be T0 or T1" >&2
  exit 2
fi
run_name="${timestamp}_${selected_tool}_coarse_maximum_search"

mkdir -p "${LOCAL_OUT_ROOT}"
LOCAL_RUN_DIR="${LOCAL_OUT_ROOT}/${run_name}"
mkdir "${LOCAL_RUN_DIR}"

remote_args=(--run-name "${run_name}")
if (($# == 0)); then
  remote_args+=(--tool T0)
else
  remote_args+=("$@")
fi

quoted_args=""
for arg in "${remote_args[@]}"; do
  printf -v quoted_arg '%q' "${arg}"
  quoted_args+=" ${quoted_arg}"
done

echo "Running multi-head-zero contact map on ${REMOTE_HOST}..."
set +e
helper_output="$(ssh "${REMOTE_HOST}" "${REMOTE_HELPER}${quoted_args}" 2>&1)"
helper_status=$?
set -e
printf '%s\n' "${helper_output}"

REMOTE_OUTPUT_DIR="~/printer_data/config/multi_head_zero_probe/runs/${run_name}"
if ! scp -q -r "${REMOTE_HOST}:${REMOTE_OUTPUT_DIR}/." "${LOCAL_RUN_DIR}/"; then
  echo "Warning: could not copy remote artifacts from ${REMOTE_OUTPUT_DIR}" >&2
fi

plot_name="${selected_tool}_maximum_search.png"
if [[ -f "${LOCAL_RUN_DIR}/${plot_name}" ]]; then
  echo "Plot: ${LOCAL_RUN_DIR}/${plot_name}"
fi
echo "Run artifacts: ${LOCAL_RUN_DIR}"

exit "${helper_status}"
