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
cp "${REPO_ROOT}/klipper_setup/klipper_config/printer.cfg.template" "${batch_dir}/source/printer.cfg.template"
cp "${REPO_ROOT}/klipper_setup/klipper_config/printer.cfg" "${batch_dir}/source/printer.cfg"

publish_state() {
  local status="$1"
  local stage="$2"
  local message="$3"
  local printable="${4:-false}"
  local step
  case "${stage}" in
    *bed_calibration.reference*) step=1 ;;
    *tool_alignment*) step=4 ;;
    *bed_calibration.mesh*) step=5 ;;
    *) step=7 ;;
  esac
  local payload
payload="$(python3 - "${batch_id}" "${status}" "${stage}" "${message}" "${printable}" <<'PY'
import json, sys
import datetime as dt
step = 1 if "bed_calibration.reference" in sys.argv[3] else 4 if "tool_alignment" in sys.argv[3] else 5 if "mesh" in sys.argv[3] else 7
print(json.dumps({
    "attempt_id": sys.argv[1], "batch_id": sys.argv[1],
    "run_scope": "full", "status": sys.argv[2], "stage": sys.argv[3],
    "message": sys.argv[4], "printable": sys.argv[5] == "true",
    "status": sys.argv[2], "stage": sys.argv[3], "message": sys.argv[4],
}))
PY
)"
  printf '%s' "${payload}" | "${REPO_ROOT}/scripts/publish_idex_acceptance.sh" update
  python3 - "${batch_id}" "${step}" "${message}" <<'PY' | "${REPO_ROOT}/scripts/publish_idex_acceptance.sh" activity >/dev/null 2>&1 || true
import datetime as dt, json, sys, uuid
now = dt.datetime.now(dt.timezone.utc).isoformat()
state = "failed" if sys.argv[2] == "failed" else "completed" if sys.argv[2] == "completed" else "busy"
print(json.dumps({"attempt_id": sys.argv[1], "activity_id": str(uuid.uuid4()), "owner": "full-coordinator", "state": state, "step": int(sys.argv[2]), "operation": sys.argv[3], "progress": sys.argv[3], "started_at": now, "heartbeat_at": now}))
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
IDEX_CALIBRATION_RUN_SCOPE=full \
IDEX_BED_CALIBRATION_RUN_DIR="${batch_dir}/bed_calibration/reference" \
  "${SCRIPT_DIR}/run_idex_bed_reference.sh"

publish_state running tool_alignment.calibration "Eddy centre reference passed; starting ball alignment"
printer_console "Eddy centre reference passed; starting T0 then T1 ball alignment"
IDEX_CALIBRATION_BATCH_ID="${batch_id}" LOCAL_OUT_DIR="${batch_dir}/tool_alignment" \
IDEX_CALIBRATION_RUN_SCOPE=full \
  "${SCRIPT_DIR}/run_multi_head_zero_contact_map.sh"

publish_state running bed_calibration.mesh "Tool alignment passed; starting Eddy mesh acquisition"
printer_console "tool alignment passed; starting Eddy mesh acquisition"
IDEX_CALIBRATION_BATCH_ID="${batch_id}" \
IDEX_CALIBRATION_RUN_SCOPE=full \
IDEX_BED_CALIBRATION_RUN_DIR="${batch_dir}/bed_calibration/mesh" \
  "${SCRIPT_DIR}/refresh_idex_bed_mesh.sh"

publish_state completed completed "All calibration checks passed" true
printf '%s' "{\"batch_id\": \"${batch_id}\"}" | "${REPO_ROOT}/scripts/publish_idex_acceptance.sh" ready
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
