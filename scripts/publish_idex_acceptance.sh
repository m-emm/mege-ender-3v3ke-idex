#!/usr/bin/env bash
# Internal transport for the shared acceptance-ledger publisher on the Pi.
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "Usage: $0 begin|update|accept|fail|ready" >&2
  exit 2
fi
command_name="$1"
case "${command_name}" in
  begin|update|accept|fail|ready) ;;
  *) echo "unknown acceptance command: ${command_name}" >&2; exit 2 ;;
esac
remote_host="${MENDERPI_HOST:-pi@menderpi.local}"
remote_root="${IDEX_DASHBOARD_ROOT:-/home/pi/printer_data/calibration}"
# Stream the JSON over SSH instead of embedding it in the remote command line.
# Run artifacts include contact records and plots, so a base64-in-argv
# transport eventually exceeds the shell's argument-size limit.
ssh "${remote_host}" \
  "python3 ~/printer_data/config/idex_calibration_acceptance.py ${command_name} --root '${remote_root}'"
