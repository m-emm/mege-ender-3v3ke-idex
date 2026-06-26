#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_CFG="${SCRIPT_DIR}/printer.cfg"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
REMOTE_TMP="/tmp/printer.cfg.$$"

python3 "${SCRIPT_DIR}/generate_printer_cfg.py"

if [[ ! -f "${SOURCE_CFG}" ]]; then
  echo "Error: source config not found: ${SOURCE_CFG}" >&2
  exit 1
fi

cleanup_remote_tmp() {
  ssh "${REMOTE_HOST}" "rm -f '${REMOTE_TMP}'" >/dev/null 2>&1 || true
}
trap cleanup_remote_tmp EXIT

echo "Updating ${REMOTE_HOST} with THE active Klipper config..."
echo "  Source: ${SOURCE_CFG}"

scp "${SOURCE_CFG}" "${REMOTE_HOST}:${REMOTE_TMP}"

ssh "${REMOTE_HOST}" "REMOTE_TMP='${REMOTE_TMP}' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

MAIN_CFG="${HOME}/printer_data/config/printer.cfg"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="${MAIN_CFG}.bak.${TS}"

if [[ ! -f "${REMOTE_TMP}" ]]; then
  echo "Error: uploaded config not found: ${REMOTE_TMP}" >&2
  exit 1
fi

mkdir -p "$(dirname -- "${MAIN_CFG}")"

if [[ -f "${MAIN_CFG}" ]]; then
  cp -a "${MAIN_CFG}" "${BACKUP}"
  echo "Backed up: ${BACKUP}"
fi

cp -a "${REMOTE_TMP}" "${MAIN_CFG}"
rm -f "${REMOTE_TMP}"
echo "Installed: ${MAIN_CFG}"

sudo systemctl restart klipper
sleep 4

echo "Klipper service: $(systemctl is-active klipper)"

python3 - <<'PY'
import json
import urllib.request

url = "http://127.0.0.1:7125/printer/objects/query?webhooks&configfile"
status = json.loads(urllib.request.urlopen(url, timeout=10).read())["result"]["status"]
webhooks = status.get("webhooks", {})
settings = status.get("configfile", {}).get("settings", {})

print(f"Klippy state: {webhooks.get('state')}")
state_message = webhooks.get("state_message")
if state_message:
    print(f"Klippy message: {state_message}")

y_current = settings.get("tmc2209 stepper_y", {}).get("run_current")
if y_current is not None:
    print(f"Y run_current: {y_current}")

left_x_current = settings.get("tmc2209 stepper_x", {}).get("run_current")
if left_x_current is not None:
    print(f"X-left run_current: {left_x_current}")

right_x_current = settings.get("tmc2209 dual_carriage", {}).get("run_current")
if right_x_current is not None:
    print(f"X-right run_current: {right_x_current}")

left_x = settings.get("stepper_x", {})
right_x = settings.get("dual_carriage", {})
if left_x.get("position_min") is not None and left_x.get("position_max") is not None:
    print(
        "X-left range: "
        f"{left_x.get('position_min')}..{left_x.get('position_max')}, "
        f"endstop={left_x.get('position_endstop')}"
    )
if right_x.get("position_min") is not None and right_x.get("position_max") is not None:
    print(
        "X-right range: "
        f"{right_x.get('position_min')}..{right_x.get('position_max')}, "
        f"endstop={right_x.get('position_endstop')}, "
        f"safe_distance={right_x.get('safe_distance')}"
    )
PY
REMOTE_SCRIPT

echo "Update complete."
