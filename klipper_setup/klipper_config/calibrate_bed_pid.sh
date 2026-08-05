#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: calibrate_bed_pid.sh [--target TEMP_C] [--timeout SECONDS] [--yes]

Runs a supervised heatbed PID calibration on menderpi, writes the
measured PID constants into printer.cfg.template, regenerates printer.cfg, and
redeploys.

This energizes the single 220V 750W SSR-controlled heatbed.
EOF
}

TARGET="80"
TIMEOUT="3600"
ASSUME_YES="0"

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET="$2"
      shift 2
      ;;
    --timeout)
      TIMEOUT="$2"
      shift 2
      ;;
    --yes)
      ASSUME_YES="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
TEMPLATE="${SCRIPT_DIR}/printer.cfg.template"

if [[ "${ASSUME_YES}" != "1" ]]; then
  cat >&2 <<EOF
This will heat the single 220V 750W bed to ${TARGET}C using the SSR on gpio20.

Stay at the printer, verify mains wiring/earthing/fusing/SSR cooling, and be
ready to cut power immediately.

Type CALIBRATE to start:
EOF
  read -r confirmation
  if [[ "${confirmation}" != "CALIBRATE" ]]; then
    echo "Calibration aborted." >&2
    exit 1
  fi
fi

echo "Deploying calibration-ready single-bed config..."
"${SCRIPT_DIR}/update_menderpi.sh"

echo "Starting PID_CALIBRATE HEATER=heater_bed TARGET=${TARGET} on ${REMOTE_HOST}..."
pid_json="$(
  ssh "${REMOTE_HOST}" "TARGET='${TARGET}' TIMEOUT='${TIMEOUT}' python3 -" <<'PY'
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request

target = float(os.environ["TARGET"])
timeout = float(os.environ["TIMEOUT"])
log_path = Path.home() / "printer_data" / "logs" / "klippy.log"
start_pos = log_path.stat().st_size if log_path.exists() else 0

script = f"PID_CALIBRATE HEATER=heater_bed TARGET={target:g}"
request = urllib.request.Request(
    "http://127.0.0.1:7125/printer/gcode/script",
    data=json.dumps({"script": script}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=timeout + 60.0) as response:
    response.read()

pattern = re.compile(
    r"Autotune: final: Kp=(?P<Kp>[0-9.]+) Ki=(?P<Ki>[0-9.]+) Kd=(?P<Kd>[0-9.]+)"
)
deadline = time.monotonic() + timeout
position = start_pos
while time.monotonic() < deadline:
    if log_path.exists():
        with log_path.open("r", encoding="utf-8", errors="replace") as log_file:
            log_file.seek(position)
            chunk = log_file.read()
            position = log_file.tell()
        for line in chunk.splitlines():
            if "Autotune:" in line or "Heater" in line:
                print(line, file=sys.stderr, flush=True)
            match = pattern.search(line)
            if match:
                print(json.dumps({
                    "pid_Kp": float(match.group("Kp")),
                    "pid_Ki": float(match.group("Ki")),
                    "pid_Kd": float(match.group("Kd")),
                }))
                raise SystemExit(0)
    time.sleep(2.0)

raise SystemExit(
    f"Timed out after {timeout:g}s waiting for PID calibration results in {log_path}"
)
PY
)"

echo "Measured PID constants: ${pid_json}"

echo "Turning heater_bed target off before rewriting config..."
ssh "${REMOTE_HOST}" "python3 -" <<'PY'
import json
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1:7125/printer/gcode/script",
    data=json.dumps({
        "script": "SET_HEATER_TEMPERATURE HEATER=heater_bed TARGET=0"
    }).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=10) as response:
    response.read()
PY

PID_JSON="${pid_json}" python3 - "${TEMPLATE}" <<'PY'
import json
import os
from pathlib import Path
import re
import sys

template_path = Path(sys.argv[1])
pid = json.loads(os.environ["PID_JSON"])
text = template_path.read_text(encoding="utf-8")

section_match = re.search(
    r"(?ms)^\[heater_bed\]\n.*?(?=^\[|\Z)",
    text,
)
if section_match is None:
    raise SystemExit("Could not find [heater_bed] in printer.cfg.template")

new_lines = []
inserted_pid = False
for line in section_match.group(0).splitlines():
    stripped = line.strip()
    if stripped.startswith("# Calibration-ready only"):
        continue
    if stripped.startswith("# PID constants measured"):
        continue
    if stripped.startswith("pid_K"):
        continue
    if stripped.startswith("max_delta:"):
        continue
    if stripped.startswith("control:"):
        new_lines.append("# PID constants measured by calibrate_bed_pid.sh.")
        new_lines.append("control: pid")
        new_lines.append(f"pid_Kp: {pid['pid_Kp']:.3f}")
        new_lines.append(f"pid_Ki: {pid['pid_Ki']:.3f}")
        new_lines.append(f"pid_Kd: {pid['pid_Kd']:.3f}")
        inserted_pid = True
        continue
    new_lines.append(line)

if not inserted_pid:
    raise SystemExit("Could not replace heater_bed control setting")

updated = (
    text[: section_match.start()]
    + "\n".join(new_lines)
    + "\n"
    + text[section_match.end() :]
)
template_path.write_text(updated, encoding="utf-8")
PY

echo "Regenerating printer.cfg and redeploying measured PID config..."
python3 "${SCRIPT_DIR}/generate_printer_cfg.py"
"${SCRIPT_DIR}/update_menderpi.sh"

echo "Bed PID calibration complete."
