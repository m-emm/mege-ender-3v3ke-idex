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
SOURCE_HEATERS="${SCRIPT_DIR}/../klipper_host/klippy/extras/heaters.py"
SOURCE_VISION="${SCRIPT_DIR}/../klipper_host/klippy/extras/vision.py"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
REMOTE_KLIPPER_DIR="${MENDERPI_KLIPPER_DIR:-/opt/klipper}"
REMOTE_TMP_CFG="/tmp/printer.cfg.$$"
REMOTE_TMP_HEATERS="/tmp/heaters.py.$$"
REMOTE_TMP_VISION="/tmp/vision.py.$$"
EXPECTED_KLIPPER_COMMIT="ca8230d505b7ba7fd225bfa6ed9655bc4520e805"
EXPECTED_UPSTREAM_HEATERS_SHA256="a95d83be80296a7ff970ea6e1b73746d1a97a7d3e47ce621c02a89d80451ac9d"
LEGACY_BOOSTED_HEATERS_SHA256="b3b362086277fc7202fb12c022aa210da7cc15a470bf536f2cc0d3d507719830"

sha256_file() {
  python3 - "$1" <<'PY'
import hashlib
import sys
from pathlib import Path

print(hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest())
PY
}

check_local_support_files() {
  "${SCRIPT_DIR}/wiring/generate_wiring_svgs.sh" --check
  python3 "${SCRIPT_DIR}/wiring/validate_wiring.py"

  if [[ ! -f "${SOURCE_HEATERS}" ]]; then
    echo "Error: managed upstream Klipper heaters.py not found: ${SOURCE_HEATERS}" >&2
    exit 1
  fi
  if [[ ! -f "${SOURCE_VISION}" ]]; then
    echo "Error: Klipper vision.py extra not found: ${SOURCE_VISION}" >&2
    exit 1
  fi

  python3 - "${SOURCE_HEATERS}" "${SOURCE_VISION}" <<'PY'
import ast
import sys
from pathlib import Path

for path_arg in sys.argv[1:]:
    ast.parse(Path(path_arg).read_text(encoding="utf-8"))
PY
}

check_live_config() {
  echo "Checking ${REMOTE_HOST} for the active Klipper config..."
  echo "  Source: ${SOURCE_CFG}"
  echo "  Klipper upstream heaters.py: ${SOURCE_HEATERS}"
  echo "  Klipper vision extra: ${SOURCE_VISION}"

  python3 "${SCRIPT_DIR}/generate_printer_cfg.py" --check
  check_local_support_files

  if [[ ! -f "${SOURCE_CFG}" ]]; then
    echo "Error: source config not found: ${SOURCE_CFG}" >&2
    exit 1
  fi

  local_sha256="$(sha256_file "${SOURCE_CFG}")"
  local_heaters_sha256="$(sha256_file "${SOURCE_HEATERS}")"
  local_vision_sha256="$(sha256_file "${SOURCE_VISION}")"
  expected_fingerprint="$(
    python3 "${SCRIPT_DIR}/generate_printer_cfg.py" --fingerprint
  )"

  if ! remote_payload="$(
    ssh "${REMOTE_HOST}" "REMOTE_KLIPPER_DIR='${REMOTE_KLIPPER_DIR}' python3 -" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

main_cfg = Path.home() / "printer_data" / "config" / "printer.cfg"
klipper_dir = Path(os.environ.get("REMOTE_KLIPPER_DIR", "/opt/klipper"))
heaters_py = klipper_dir / "klippy" / "extras" / "heaters.py"
vision_py = klipper_dir / "klippy" / "extras" / "vision.py"
payload = {
    "ok": False,
    "remote_config_path": str(main_cfg),
    "remote_heaters_path": str(heaters_py),
    "remote_vision_path": str(vision_py),
}

try:
    payload["remote_sha256"] = hashlib.sha256(main_cfg.read_bytes()).hexdigest()
    payload["remote_heaters_sha256"] = hashlib.sha256(
        heaters_py.read_bytes()
    ).hexdigest()
    payload["remote_vision_sha256"] = hashlib.sha256(
        vision_py.read_bytes()
    ).hexdigest()
    payload["remote_klipper_commit"] = subprocess.check_output(
        ["git", "-C", str(klipper_dir), "rev-parse", "HEAD"],
        text=True,
    ).strip()
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
  CHECK_LOCAL_HEATERS_SHA256="${local_heaters_sha256}" \
  CHECK_LOCAL_VISION_SHA256="${local_vision_sha256}" \
  CHECK_EXPECTED_KLIPPER_COMMIT="${EXPECTED_KLIPPER_COMMIT}" \
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
local_heaters_sha256 = os.environ["CHECK_LOCAL_HEATERS_SHA256"]
local_vision_sha256 = os.environ["CHECK_LOCAL_VISION_SHA256"]
expected_fingerprint = os.environ["CHECK_EXPECTED_FINGERPRINT"]
expected_klipper_commit = os.environ["CHECK_EXPECTED_KLIPPER_COMMIT"]
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
remote_heaters_sha256 = remote_payload.get("remote_heaters_sha256", "")
remote_vision_sha256 = remote_payload.get("remote_vision_sha256", "")
remote_klipper_commit = remote_payload.get("remote_klipper_commit", "")
status = remote_payload.get("status", {})
webhooks = status.get("webhooks", {})
configfile = status.get("configfile", {})
live_fingerprint = generator.active_config_fingerprint(status)

print(f"  Remote sha256: {remote_sha256}")
print(f"  Local heaters.py sha256: {local_heaters_sha256}")
print(f"  Remote heaters.py sha256: {remote_heaters_sha256}")
print(f"  Local vision.py sha256: {local_vision_sha256}")
print(f"  Remote vision.py sha256: {remote_vision_sha256}")
print(f"  Remote Klipper commit: {remote_klipper_commit}")
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
if remote_heaters_sha256 != local_heaters_sha256:
    errors.append(
        "remote Klipper heaters.py sha256 does not match the managed upstream file "
        f"({remote_heaters_sha256} != {local_heaters_sha256})"
    )
if remote_vision_sha256 != local_vision_sha256:
    errors.append(
        "remote Klipper vision.py sha256 does not match local extra "
        f"({remote_vision_sha256} != {local_vision_sha256})"
    )
if remote_klipper_commit != expected_klipper_commit:
    errors.append(
        "remote Klipper commit does not match expected pinned commit "
        f"({remote_klipper_commit} != {expected_klipper_commit})"
    )

settings = status.get("configfile", {}).get("settings", {})
bed = settings.get("heater_bed", {})
expected_bed_settings = {
    "heater_pin": "gpio20",
    "pwm_cycle_time": 2.0,
}
for key, expected in expected_bed_settings.items():
    actual = bed.get(key)
    if isinstance(expected, float):
        try:
            matches = abs(float(actual) - expected) < 1e-6
        except (TypeError, ValueError):
            matches = False
    else:
        matches = actual == expected
    if not matches:
        errors.append(
            f"live heater_bed.{key} is {actual!r}, expected {expected!r}"
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
check_local_support_files

if [[ ! -f "${SOURCE_CFG}" ]]; then
  echo "Error: source config not found: ${SOURCE_CFG}" >&2
  exit 1
fi

cleanup_remote_tmp() {
  ssh "${REMOTE_HOST}" "rm -f '${REMOTE_TMP_CFG}' '${REMOTE_TMP_HEATERS}' '${REMOTE_TMP_VISION}'" >/dev/null 2>&1 || true
}
trap cleanup_remote_tmp EXIT

local_heaters_sha256="$(sha256_file "${SOURCE_HEATERS}")"
local_vision_sha256="$(sha256_file "${SOURCE_VISION}")"

echo "Updating ${REMOTE_HOST} with THE active Klipper config and host extras..."
echo "  Source: ${SOURCE_CFG}"
echo "  Klipper upstream heaters.py: ${SOURCE_HEATERS}"
echo "  Klipper vision extra: ${SOURCE_VISION}"

scp "${SOURCE_CFG}" "${REMOTE_HOST}:${REMOTE_TMP_CFG}"
scp "${SOURCE_HEATERS}" "${REMOTE_HOST}:${REMOTE_TMP_HEATERS}"
scp "${SOURCE_VISION}" "${REMOTE_HOST}:${REMOTE_TMP_VISION}"

ssh "${REMOTE_HOST}" \
  "REMOTE_TMP_CFG='${REMOTE_TMP_CFG}' REMOTE_TMP_HEATERS='${REMOTE_TMP_HEATERS}' REMOTE_TMP_VISION='${REMOTE_TMP_VISION}' REMOTE_KLIPPER_DIR='${REMOTE_KLIPPER_DIR}' EXPECTED_KLIPPER_COMMIT='${EXPECTED_KLIPPER_COMMIT}' EXPECTED_UPSTREAM_HEATERS_SHA256='${EXPECTED_UPSTREAM_HEATERS_SHA256}' LEGACY_BOOSTED_HEATERS_SHA256='${LEGACY_BOOSTED_HEATERS_SHA256}' EXPECTED_MANAGED_HEATERS_SHA256='${local_heaters_sha256}' EXPECTED_VISION_SHA256='${local_vision_sha256}' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail

MAIN_CFG="${HOME}/printer_data/config/printer.cfg"
HEATERS_PY="${REMOTE_KLIPPER_DIR}/klippy/extras/heaters.py"
VISION_PY="${REMOTE_KLIPPER_DIR}/klippy/extras/vision.py"
TS="$(date +%Y%m%d-%H%M%S)"
CFG_BACKUP="${MAIN_CFG}.bak.${TS}"
HEATERS_BACKUP="${HEATERS_PY}.bak.${TS}"
VISION_BACKUP="${VISION_PY}.bak.${TS}"

if [[ ! -f "${REMOTE_TMP_CFG}" ]]; then
  echo "Error: uploaded config not found: ${REMOTE_TMP_CFG}" >&2
  exit 1
fi
if [[ ! -f "${REMOTE_TMP_HEATERS}" ]]; then
  echo "Error: uploaded heaters.py not found: ${REMOTE_TMP_HEATERS}" >&2
  exit 1
fi
if [[ ! -f "${REMOTE_TMP_VISION}" ]]; then
  echo "Error: uploaded vision.py not found: ${REMOTE_TMP_VISION}" >&2
  exit 1
fi
if [[ ! -f "${HEATERS_PY}" ]]; then
  echo "Error: remote Klipper heaters.py not found: ${HEATERS_PY}" >&2
  exit 1
fi

remote_commit="$(git -C "${REMOTE_KLIPPER_DIR}" rev-parse HEAD)"
if [[ "${remote_commit}" != "${EXPECTED_KLIPPER_COMMIT}" ]]; then
  echo "Error: remote Klipper commit ${remote_commit} does not match ${EXPECTED_KLIPPER_COMMIT}" >&2
  exit 1
fi

current_heaters_sha="$(sha256sum "${HEATERS_PY}" | awk '{print $1}')"
if [[ "${current_heaters_sha}" != "${EXPECTED_UPSTREAM_HEATERS_SHA256}" \
      && "${current_heaters_sha}" != "${LEGACY_BOOSTED_HEATERS_SHA256}" ]]; then
  echo "Error: remote heaters.py has unexpected sha256 ${current_heaters_sha}" >&2
  echo "Expected upstream ${EXPECTED_UPSTREAM_HEATERS_SHA256} or legacy boosted ${LEGACY_BOOSTED_HEATERS_SHA256}" >&2
  exit 1
fi

uploaded_heaters_sha="$(sha256sum "${REMOTE_TMP_HEATERS}" | awk '{print $1}')"
if [[ "${uploaded_heaters_sha}" != "${EXPECTED_MANAGED_HEATERS_SHA256}" \
      || "${uploaded_heaters_sha}" != "${EXPECTED_UPSTREAM_HEATERS_SHA256}" ]]; then
  echo "Error: uploaded heaters.py sha256 ${uploaded_heaters_sha} is not the expected upstream file" >&2
  exit 1
fi

uploaded_vision_sha="$(sha256sum "${REMOTE_TMP_VISION}" | awk '{print $1}')"
if [[ "${uploaded_vision_sha}" != "${EXPECTED_VISION_SHA256}" ]]; then
  echo "Error: uploaded vision.py sha256 ${uploaded_vision_sha} does not match local ${EXPECTED_VISION_SHA256}" >&2
  exit 1
fi

python3 - <<'PY'
import json
import sys
import urllib.request

url = (
    "http://127.0.0.1:7125/printer/objects/query?"
    "webhooks&print_stats&heater_bed&virtual_sdcard"
)
status = json.loads(urllib.request.urlopen(url, timeout=10).read())["result"]["status"]
webhooks = status.get("webhooks", {})
klippy_state = webhooks.get("state")
print_state = status.get("print_stats", {}).get("state")
bed = status.get("heater_bed", {})
virtual_sd_active = status.get("virtual_sdcard", {}).get("is_active", False)

if klippy_state == "ready":
    if print_state not in {"standby", "complete", "cancelled", "error"}:
        raise SystemExit(
            "Refusing to restart ready Klipper while "
            f"print_stats.state={print_state!r}"
        )
    if virtual_sd_active:
        raise SystemExit("Refusing to restart ready Klipper while virtual SD is active")
    if bed.get("target", 0.0) not in {0, 0.0}:
        raise SystemExit(
            "Refusing to restart ready Klipper while "
            f"heater_bed target={bed.get('target')!r}"
        )
    print(
        "Printer idle check passed: "
        f"Klippy state={klippy_state}, print_stats.state={print_state}, "
        f"heater_bed target={bed.get('target')}"
    )
elif klippy_state == "error":
    print(
        "Klippy is in config/error recovery state; allowing config install "
        f"and service restart: {webhooks.get('state_message')}"
    )
else:
    raise SystemExit(
        "Refusing to restart Klipper with unverified state: "
        f"webhooks.state={klippy_state!r}, print_stats.state={print_state!r}"
    )
PY

if [[ "${current_heaters_sha}" == "${EXPECTED_UPSTREAM_HEATERS_SHA256}" ]]; then
  echo "Upstream Klipper heaters.py already installed: ${HEATERS_PY}"
else
  cp -a "${HEATERS_PY}" "${HEATERS_BACKUP}"
  echo "Backed up: ${HEATERS_BACKUP}"
  cp -a "${REMOTE_TMP_HEATERS}" "${HEATERS_PY}"
  echo "Restored upstream Klipper heaters.py: ${HEATERS_PY}"
fi
rm -f "${REMOTE_TMP_HEATERS}"

if [[ -f "${VISION_PY}" ]]; then
  current_vision_sha="$(sha256sum "${VISION_PY}" | awk '{print $1}')"
else
  current_vision_sha=""
fi
if [[ "${current_vision_sha}" == "${EXPECTED_VISION_SHA256}" ]]; then
  echo "Klipper vision extra already installed: ${VISION_PY}"
else
  mkdir -p "$(dirname -- "${VISION_PY}")"
  if [[ -f "${VISION_PY}" ]]; then
    cp -a "${VISION_PY}" "${VISION_BACKUP}"
    echo "Backed up: ${VISION_BACKUP}"
  fi
  cp -a "${REMOTE_TMP_VISION}" "${VISION_PY}"
  echo "Installed: ${VISION_PY}"
fi
rm -f "${REMOTE_TMP_VISION}"

mkdir -p "$(dirname -- "${MAIN_CFG}")"

if [[ -f "${MAIN_CFG}" ]]; then
  cp -a "${MAIN_CFG}" "${CFG_BACKUP}"
  echo "Backed up: ${CFG_BACKUP}"
fi

cp -a "${REMOTE_TMP_CFG}" "${MAIN_CFG}"
rm -f "${REMOTE_TMP_CFG}"
echo "Installed: ${MAIN_CFG}"

sudo systemctl restart klipper

python3 - <<'PY'
import json
import time
import urllib.request

deadline = time.monotonic() + 60.0
last_state = None
last_message = None
while time.monotonic() < deadline:
    try:
        url = "http://127.0.0.1:7125/printer/objects/query?webhooks"
        status = json.loads(urllib.request.urlopen(url, timeout=5).read())[
            "result"
        ]["status"]
        webhooks = status.get("webhooks", {})
        last_state = webhooks.get("state")
        last_message = webhooks.get("state_message")
        if last_state == "ready":
            print("Klippy reached ready state.")
            break
    except Exception as exc:
        last_state = type(exc).__name__
        last_message = str(exc)
    time.sleep(2.0)
else:
    raise SystemExit(
        f"Klippy did not reach ready state after restart: {last_state}: {last_message}"
    )
PY

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
bed = settings.get("heater_bed", {})
for key in [
    "heater_pin",
    "pwm_cycle_time",
    "control",
]:
    if key in bed:
        print(f"heater_bed {key}: {bed[key]}")
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

echo "Verifying deployed config and host extras..."
check_live_config

echo "Deploying the complete tracked vision code set..."
MENDERPI_HOST="${REMOTE_HOST}" "${SCRIPT_DIR}/deploy_vision_code.sh"

echo "Update complete."
