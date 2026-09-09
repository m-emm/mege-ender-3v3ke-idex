#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
timestamp="$(date -u '+%Y%m%dT%H%M%SZ')"
batch_id="${IDEX_CALIBRATION_BATCH_ID:-${timestamp}_full}"
batch_dir="${REPO_ROOT}/runs/idex_calibration/${batch_id}"
dashboard_root="/home/pi/printer_data/calibration"
mkdir -p "${batch_dir}/source"
cp "${REPO_ROOT}/klipper_setup/klipper_config/calib.yaml" "${batch_dir}/source/calib.yaml"
cp "${REPO_ROOT}/klipper_setup/klipper_config/calib_config.yaml" "${batch_dir}/source/calib_config.yaml"
cp "${REPO_ROOT}/klipper_setup/klipper_config/printer.cfg" "${batch_dir}/source/printer.cfg"

publish_state() {
  local status="$1"
  local stage="$2"
  local message="$3"
  local printable="${4:-false}"
  local payload
  payload="$(python3 - "${batch_id}" "${status}" "${stage}" "${message}" "${printable}" <<'PY'
import datetime as dt
import json
import sys

print(json.dumps({
    "batch_id": sys.argv[1],
    "status": sys.argv[2],
    "stage": sys.argv[3],
    "message": sys.argv[4],
    "printable": sys.argv[5] == "true",
    "at": dt.datetime.now(dt.timezone.utc).isoformat(),
}))
PY
)"
  local encoded
  encoded="$(printf '%s' "${payload}" | base64 | tr -d '\n')"
  ssh "${REMOTE_HOST}" "DASHBOARD_ROOT='${dashboard_root}' PAYLOAD_B64='${encoded}' python3 -" <<'PY'
import base64
import json
import os
from pathlib import Path

root = Path(os.environ["DASHBOARD_ROOT"])
path = root / "data/current.json"
path.parent.mkdir(parents=True, exist_ok=True)
try:
    state = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    state = {}
payload = json.loads(base64.b64decode(os.environ["PAYLOAD_B64"]))
if state.get("batch_id") != payload["batch_id"]:
    state = {"chapters": {}, "events": []}
state.update({
    "schema_version": 3,
    "kind": "idex_calibration_dashboard",
    "batch_id": payload["batch_id"],
    "status": payload["status"],
    "stage": payload["stage"],
    "updated_at": payload["at"],
})
state["events"] = (state.get("events", []) + [{"at": payload["at"], "message": payload["message"]}])[-24:]
state["readiness"] = {
    "printable": payload["printable"],
    "checks": state.get("readiness", {}).get("checks", []),
    "reasons": [] if payload["printable"] else ([payload["message"]] if payload["status"] == "failed" else []),
}
temporary = path.with_name("." + path.name + ".tmp")
temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
temporary.replace(path)
if payload["printable"]:
    successful = root / "data/last_successful.json"
    successful_tmp = successful.with_name("." + successful.name + ".tmp")
    successful_tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    successful_tmp.replace(successful)
PY
}

printer_console() {
  local encoded
  encoded="$(printf '%s' "$1" | base64 | tr -d '\n')"
  ssh "${REMOTE_HOST}" "MESSAGE_B64='${encoded}' python3 -" <<'PY'
import base64
import os
import urllib.parse
import urllib.request

message = base64.b64decode(os.environ["MESSAGE_B64"]).decode()
body = urllib.parse.urlencode({"script": 'RESPOND TYPE=echo MSG="IDEX calibration: %s"' % message.replace('"', "'")}).encode()
urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:7125/printer/gcode/script", data=body, method="POST"), timeout=15).read()
PY
}

publish_batch_summary() {
  local remote_batch_dir="${dashboard_root}/runs/${batch_id}"
  COPYFILE_DISABLE=1 tar -C "${batch_dir}" -cf - source batch_manifest.json "$@" | \
    ssh "${REMOTE_HOST}" "mkdir -p '${remote_batch_dir}' && tar -C '${remote_batch_dir}' -xf -"
}

failure() {
  local status="$?"
  publish_state failed failed "Full calibration stopped; inspect the dashboard and batch artifacts"
  printer_console "FAILED; inspect /calibration/"
  python3 - "${batch_dir}" "${batch_id}" "${status}" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]) / "batch_manifest.json"
path.write_text(json.dumps({
    "schema_version": 1,
    "workflow": "idex_full_calibration_v2",
    "batch_id": sys.argv[2],
    "status": "failed",
    "exit_status": int(sys.argv[3]),
    "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  publish_batch_summary
  exit "${status}"
}
trap failure ERR

publish_state running tool_alignment.calibration "Full IDEX calibration started"
printer_console "full calibration started"
# Establish the absolute bed-Z datum before touching the ball.  The ball
# workflow then runs in the newly rebased logical Z frame; mesh acquisition is
# deliberately deferred until both toolheads have passed alignment.
publish_state running bed_calibration.reference "Starting Eddy centre reference before tool alignment"
printer_console "starting Eddy centre reference at X=150 Y=150 before ball calibration"
IDEX_CALIBRATION_BATCH_ID="${batch_id}" \
IDEX_EDDY_PHASE=reference \
IDEX_BED_CALIBRATION_RUN_DIR="${batch_dir}/bed_calibration/reference" \
  "${SCRIPT_DIR}/run_eddy_tap_bed_calibration.sh"

publish_state running tool_alignment.calibration "Eddy centre reference passed; starting ball alignment"
printer_console "Eddy centre reference passed; starting T0 then T1 ball alignment"
IDEX_CALIBRATION_BATCH_ID="${batch_id}" LOCAL_OUT_DIR="${batch_dir}/tool_alignment" \
  "${SCRIPT_DIR}/run_multi_head_zero_contact_map.sh"

publish_state running bed_calibration.mesh "Tool alignment passed; starting Eddy mesh acquisition"
printer_console "tool alignment passed; starting Eddy mesh acquisition"
IDEX_CALIBRATION_BATCH_ID="${batch_id}" \
IDEX_EDDY_PHASE=mesh \
IDEX_BED_CALIBRATION_RUN_DIR="${batch_dir}/bed_calibration/mesh" \
  "${SCRIPT_DIR}/run_eddy_tap_bed_calibration.sh"

publish_state completed completed "All calibration checks passed" true
printer_console "READY TO PRINT"
python3 - "${batch_dir}" "${batch_id}" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
reference = json.loads(
    (root / "bed_calibration/reference/bed_calibration_result.json").read_text()
)
mesh = json.loads(
    (root / "bed_calibration/mesh/bed_calibration_result.json").read_text()
)
bed = {
    "schema_version": 2,
    "workflow": "idex_eddy_tap_bed_calibration_v2_reference_then_mesh",
    "reference": reference,
    "mesh": mesh,
    "target_config_fingerprint": mesh["target_config_fingerprint"],
}
(root / "bed_calibration/bed_calibration_result.json").write_text(
    json.dumps(bed, indent=2, sort_keys=True) + "\n"
)
verification = sorted((root / "tool_alignment").glob("*_verification/paired_report/verification_report.json"))[-1]
report = {
    "schema_version": 1,
    "workflow": "idex_full_calibration_v2",
    "batch_id": sys.argv[2],
    "status": "completed",
    "printable": True,
    "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "target_config_fingerprint": bed["target_config_fingerprint"],
    "tool_verification": str(verification.relative_to(root)),
    "bed_calibration": "bed_calibration/bed_calibration_result.json",
}
(root / "final_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
(root / "batch_manifest.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY
publish_batch_summary final_report.json
trap - ERR
echo "IDEX calibration complete and printable: ${batch_dir}"
