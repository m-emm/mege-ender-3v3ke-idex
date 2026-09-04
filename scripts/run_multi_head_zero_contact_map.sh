#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
LOCAL_OUT_ROOT="${LOCAL_OUT_DIR:-${REPO_ROOT}/runs/multi_head_zero_contact}"
REMOTE_HELPER='~/printer_data/config/multi_head_zero_probe/run_multi_head_zero_contact_map.py'
timestamp="$(date '+%Y-%m-%d_%H-%M-%S')"
selected_tool="T0"
selected_strategy="grid"
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
    --strategy)
      next_index=$((arg_index + 1))
      selected_strategy="${!next_index}"
      ;;
    --strategy=*)
      selected_strategy="${argument#--strategy=}"
      ;;
  esac
done
if [[ "${selected_tool}" != "T0" && "${selected_tool}" != "T1" ]]; then
  echo "--tool must be T0 or T1" >&2
  exit 2
fi
if [[ "${selected_strategy}" == "grid" ]]; then
  run_suffix="10x10_grid"
elif [[ "${selected_strategy}" == "max-search" ]]; then
  run_suffix="maximum_search"
else
  echo "--strategy must be grid or max-search" >&2
  exit 2
fi
run_name="${timestamp}_${selected_tool}_${run_suffix}"

mkdir -p "${LOCAL_OUT_ROOT}"
LOCAL_RUN_DIR="${LOCAL_OUT_ROOT}/${run_name}"
mkdir "${LOCAL_RUN_DIR}"

remote_args=(--run-name "${run_name}")
if (($# == 0)); then
  remote_args+=(
    --tool T0
    --x-values 75.2,75.6,76,76.4,76.8,77.2,77.6,78,78.4,78.8
    --y-values=-14.8,-14.4,-14,-13.6,-13.2,-12.8,-12.4,-12,-11.6,-11.2
    --repeats 1
  )
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

for plot_name in "${selected_tool}_raw_contact_map.png" "${selected_tool}_maximum_search.png"; do
  if [[ -f "${LOCAL_RUN_DIR}/${plot_name}" ]]; then
    echo "Plot: ${LOCAL_RUN_DIR}/${plot_name}"
  fi
done
echo "Run artifacts: ${LOCAL_RUN_DIR}"

exit "${helper_status}"
