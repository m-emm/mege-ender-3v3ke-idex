#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
REMOTE_HELPER='python3 ~/printer_data/config/multi_head_zero_probe/run_multi_head_zero_contact_map.py'
LOCAL_OUT_ROOT="${LOCAL_OUT_DIR:-${REPO_ROOT}/runs/multi_head_zero_contact}"
UPDATE_SCRIPT="${REPO_ROOT}/klipper_setup/klipper_config/update_menderpi.sh"
APPLY_SCRIPT="${REPO_ROOT}/scripts/apply_multi_head_zero_maximum_calibration.py"
VERIFY_SCRIPT="${REPO_ROOT}/scripts/verify_multi_head_zero_alignment.py"
DASHBOARD_ROOT="/home/pi/printer_data/vision/multi_head_zero_calibration"

tool="both"
if [[ "$#" -eq 2 && "$1" == "--tool" && ( "$2" == "T0" || "$2" == "T1" ) ]]; then
  tool="$2"
elif [[ "$#" -ne 0 ]]; then
  echo "Usage: $0 [--tool T0|T1]" >&2
  exit 2
fi

timestamp="$(date '+%Y-%m-%d_%H-%M-%S')"
mkdir -p "${LOCAL_OUT_ROOT}"

printer_console() {
  local message="$1"
  local encoded
  encoded="$(printf '%s' "${message}" | base64 | tr -d '\n')"
  ssh "${REMOTE_HOST}" "MESSAGE_B64='${encoded}' python3 -" <<'PY'
import base64
import datetime as dt
import os
import urllib.parse
import urllib.request

message = base64.b64decode(os.environ["MESSAGE_B64"]).decode("utf-8")
payload = urllib.parse.urlencode(
    {"script": 'RESPOND TYPE=echo MSG="MHZ calibration: %s"' % message.replace('"', "'")}
).encode("utf-8")
urllib.request.urlopen(
    urllib.request.Request(
        "http://127.0.0.1:7125/printer/gcode/script", data=payload, method="POST"
    ),
    timeout=15,
).read()
PY
}

dashboard_publish() {
  local local_file="$1"
  local artifact_name="$2"
  local state_key="$3"
  local event="$4"
  local remote_file="${DASHBOARD_ROOT}/artifacts/${artifact_name}"
  scp -q "${local_file}" "${REMOTE_HOST}:${remote_file}"
  local event_b64
  event_b64="$(printf '%s' "${event}" | base64 | tr -d '\n')"
  ssh "${REMOTE_HOST}" "DASHBOARD_ROOT='${DASHBOARD_ROOT}' DASHBOARD_FILE='artifacts/${artifact_name}' DASHBOARD_KEY='${state_key}' DASHBOARD_EVENT_B64='${event_b64}' python3 -" <<'PY'
import base64
import datetime as dt
import json
import os
from pathlib import Path

root = Path(os.environ["DASHBOARD_ROOT"])
state_path = root / "data" / "current.json"
state = json.loads(state_path.read_text(encoding="utf-8"))
relative = os.environ["DASHBOARD_FILE"]
artifact = root / relative
entry = {
    "artifact": relative,
    "data": json.loads(artifact.read_text(encoding="utf-8")),
}
key = os.environ["DASHBOARD_KEY"]
chapters = state.setdefault("chapters", {})
if key == "calibration_result":
    chapters.setdefault("calibration", {"runs": {}})["result"] = entry
elif key == "verification":
    chapters.setdefault("verification", {"runs": {}})["report"] = entry
state[key] = entry
event = base64.b64decode(os.environ["DASHBOARD_EVENT_B64"]).decode("utf-8")
now = dt.datetime.now(dt.timezone.utc).isoformat()
state["events"] = (state.get("events", []) + [{"at": now, "message": event}])[-16:]
state["updated_at"] = now
if state.get("status") == "completed":
    state["last_completed"] = {
        "run_id": state.get("run_id"),
        "workflow": state.get("workflow"),
        "finished_at": state.get("finished_at"),
        "chapters": chapters,
    }
temporary = state_path.with_name(".%s.tmp" % state_path.name)
temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
temporary.replace(state_path)
PY
}

run_remote_batch() {
  local mode="$1"
  local run_id="$2"
  local output_dir="$3"
  local reference_x="${4:-}"
  local reference_y="${5:-}"
  mkdir -p "${output_dir}"
  echo "Multi-head-zero ${mode} batch: ${run_id}"
  local remote_command
  remote_command="MULTI_HEAD_ZERO_BATCH_MODE=$(printf '%q' "${mode}") MULTI_HEAD_ZERO_BATCH_RUN_ID=$(printf '%q' "${run_id}")"
  if [[ -n "${reference_x}" ]]; then
    remote_command+=" MULTI_HEAD_ZERO_REFERENCE_X=$(printf '%q' "${reference_x}") MULTI_HEAD_ZERO_REFERENCE_Y=$(printf '%q' "${reference_y}")"
  fi
  remote_command+=" ${REMOTE_HELPER} --tool ${tool}"
  local remote_status
  set +e
  ssh "${REMOTE_HOST}" "${remote_command}" 2>&1 | tee "${output_dir}/remote.log"
  remote_status="${PIPESTATUS[0]}"
  set -e
  scp -q -r "${REMOTE_HOST}:~/printer_data/config/multi_head_zero_probe/runs/${run_id}/." "${output_dir}/"
  return "${remote_status}"
}

calibration_id="${timestamp}_T0_T1_calibration"
calibration_dir="${LOCAL_OUT_ROOT}/${calibration_id}"
run_remote_batch calibration "${calibration_id}" "${calibration_dir}"

if [[ "${tool}" != "both" ]]; then
  echo "Single-tool calibration complete: ${calibration_dir}/${tool}"
  exit 0
fi

calibration_result="${calibration_dir}/calibration_result.json"
printer_console "paired calibration complete; applying T1 correction"
echo "Applying paired T1 correction..."
python "${APPLY_SCRIPT}" \
  --t0-run "${calibration_dir}/T0" \
  --t1-run "${calibration_dir}/T1" \
  --result "${calibration_result}"
dashboard_publish "${calibration_result}" "${calibration_id}_calibration_result.json" "calibration_result" "T1 correction calculated"

printer_console "T1 correction calculated; deploying configuration"
echo "Deploying paired calibration and checking parity..."
"${UPDATE_SCRIPT}"
"${UPDATE_SCRIPT}" --check
printer_console "configuration deployment parity passed; starting nine-contact verification"

read -r reference_x reference_y < <(
  python -c 'import json, sys; point=json.load(open(sys.argv[1], encoding="utf-8"))["reference_center"]; print("%.9f %.9f" % (point["x"], point["y"]))' "${calibration_result}"
)
verification_id="${timestamp}_T0_T1_verification"
verification_dir="${LOCAL_OUT_ROOT}/${verification_id}"
run_remote_batch verification "${verification_id}" "${verification_dir}" "${reference_x}" "${reference_y}"

echo "Reporting paired verification..."
set +e
python "${VERIFY_SCRIPT}" \
  --t0-run "${verification_dir}/T0" \
  --t1-run "${verification_dir}/T1" \
  --calibration-result "${calibration_result}" \
  --output-dir "${verification_dir}/paired_report"
verification_status="$?"
set -e
dashboard_publish "${verification_dir}/paired_report/verification_report.json" "${verification_id}_verification_report.json" "verification" "Paired verification complete"
if [[ "${verification_status}" -eq 0 ]]; then
  printer_console "paired verification PASSED"
else
  printer_console "paired verification FAILED; inspect /calibration"
fi

echo "Multi-head-zero full calibration complete: ${calibration_dir}"
echo "Verification report: ${verification_dir}/paired_report/verification_report.json"
exit "${verification_status}"
