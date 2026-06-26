#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 [--check]" >&2
}

MODE="update"
if [[ "$#" -eq 0 ]]; then
  MODE="update"
elif [[ "$#" -eq 1 && "$1" == "--check" ]]; then
  MODE="check"
else
  usage
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_CFG="${SCRIPT_DIR}/printer.cfg"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
REMOTE_TMP="/tmp/printer.cfg.$$"

sha256_file() {
  python3 - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

check_live_config() {
  echo "Checking ${REMOTE_HOST} for the active Klipper config..."
  echo "  Source: ${SOURCE_CFG}"

  python3 "${SCRIPT_DIR}/generate_printer_cfg.py" --check

  if [[ ! -f "${SOURCE_CFG}" ]]; then
    echo "Error: source config not found: ${SOURCE_CFG}" >&2
    exit 1
  fi

  local_sha256="$(sha256_file "${SOURCE_CFG}")"
  expected_fingerprint="$(
    python3 "${SCRIPT_DIR}/generate_printer_cfg.py" --fingerprint
  )"

  if ! remote_payload="$(
    ssh "${REMOTE_HOST}" "python3 -" <<'PY'
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

main_cfg = Path.home() / "printer_data" / "config" / "printer.cfg"
payload = {
    "ok": False,
    "remote_config_path": str(main_cfg),
}

try:
    payload["remote_sha256"] = hashlib.sha256(main_cfg.read_bytes()).hexdigest()
    url = "http://127.0.0.1:7125/printer/objects/query?webhooks&configfile"
    with urllib.request.urlopen(url, timeout=10) as response:
        payload["status"] = json.loads(response.read())["result"]["status"]
    payload["ok"] = True
except Exception as exc:
    payload["error"] = f"{type(exc).__name__}: {exc}"

json.dump(payload, sys.stdout)
PY
  )"; then
    echo "Config check failed: could not SSH to ${REMOTE_HOST}." >&2
    exit 1
  fi

  CHECK_EXPECTED_FINGERPRINT="${expected_fingerprint}" \
  CHECK_LOCAL_SHA256="${local_sha256}" \
  CHECK_REMOTE_HOST="${REMOTE_HOST}" \
  CHECK_REMOTE_PAYLOAD="${remote_payload}" \
    python3 - "${SCRIPT_DIR}/generate_printer_cfg.py" <<'PY'
import importlib.util
import json
import os
import sys

generator_path = sys.argv[1]
spec = importlib.util.spec_from_file_location("generate_printer_cfg", generator_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load {generator_path}")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)

remote_host = os.environ["CHECK_REMOTE_HOST"]
local_sha256 = os.environ["CHECK_LOCAL_SHA256"]
expected_fingerprint = os.environ["CHECK_EXPECTED_FINGERPRINT"]
remote_payload = json.loads(os.environ["CHECK_REMOTE_PAYLOAD"])

print(f"  Host: {remote_host}")
print(f"  Local sha256: {local_sha256}")

remote_path = remote_payload.get("remote_config_path")
if remote_path:
    print(f"  Remote config: {remote_path}")

if not remote_payload.get("ok"):
    print(
        "Config check failed: could not inspect remote config: "
        f"{remote_payload.get('error', 'unknown error')}",
        file=sys.stderr,
    )
    sys.exit(1)

remote_sha256 = remote_payload.get("remote_sha256", "")
status = remote_payload.get("status", {})
webhooks = status.get("webhooks", {})
configfile = status.get("configfile", {})
live_fingerprint = generator.active_config_fingerprint(status)

print(f"  Remote sha256: {remote_sha256}")
print(f"  Klippy state: {webhooks.get('state')}")
print(f"  save_config_pending: {configfile.get('save_config_pending')}")
print(f"  Local fingerprint: {expected_fingerprint}")
print(f"  Live fingerprint: {live_fingerprint}")

errors = generator.live_config_check_errors(
    local_sha256=local_sha256,
    remote_sha256=remote_sha256,
    expected_fingerprint=expected_fingerprint,
    status=status,
)
if errors:
    print("Config check failed:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    sys.exit(1)

print("Config check passed: remote file matches and Klippy loaded this config.")
PY
}

if [[ "${MODE}" == "check" ]]; then
  check_live_config
  exit 0
fi

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
