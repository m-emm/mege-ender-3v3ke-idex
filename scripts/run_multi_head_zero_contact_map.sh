#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
REMOTE_HELPER='python3 ~/printer_data/config/multi_head_zero_probe/run_multi_head_zero_contact_map.py'
batch_id="${IDEX_CALIBRATION_BATCH_ID:-}"
if [[ -n "${batch_id}" ]]; then
  LOCAL_OUT_ROOT="${LOCAL_OUT_DIR:-${REPO_ROOT}/runs/idex_calibration/${batch_id}/tool_alignment}"
else
  LOCAL_OUT_ROOT="${LOCAL_OUT_DIR:-${REPO_ROOT}/runs/multi_head_zero_contact}"
fi
UPDATE_SCRIPT="${REPO_ROOT}/klipper_setup/klipper_config/update_menderpi.sh"
APPLY_SCRIPT="${REPO_ROOT}/scripts/apply_multi_head_zero_maximum_calibration.py"
VERIFY_SCRIPT="${REPO_ROOT}/scripts/verify_multi_head_zero_alignment.py"
DASHBOARD_ROOT="/home/pi/printer_data/calibration"

tool="both"
if [[ "$#" -eq 2 && "$1" == "--tool" && ( "$2" == "T0" || "$2" == "T1" ) ]]; then
  tool="$2"
elif [[ "$#" -ne 0 ]]; then
  echo "Usage: $0 [--tool T0|T1]" >&2
  exit 2
fi

timestamp="$(date '+%Y-%m-%d_%H-%M-%S')"
# Calibration and verification are one logical tool-alignment batch.  Keep a
# stable dashboard batch id across both remote helper invocations so the
# completed calibration evidence remains visible while verification runs.
dashboard_batch_id="${batch_id:-${timestamp}_T0_T1}"
mkdir -p "${LOCAL_OUT_ROOT}"

"${UPDATE_SCRIPT}" --check

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
  # scp preserves a restrictive local mode (for example 0600 from a secure
  # umask).  nginx serves these files directly, so publish them explicitly as
  # owner/group writable and world-readable before advertising the URL.
  ssh "${REMOTE_HOST}" "chmod 0644 -- '${remote_file}'"
  local payload
  payload="$(python3 - "${local_file}" "${artifact_name}" "${state_key}" "${event}" "${dashboard_batch_id}" <<'PY'
import json, sys
from pathlib import Path
artifact = Path(sys.argv[1])
remote_name = sys.argv[2]
key = sys.argv[3]
data = json.loads(artifact.read_text(encoding="utf-8"))
chapter = (
    {"calibration": {"result": {"artifact": "artifacts/" + remote_name, "data": data}}}
    if key == "calibration_result"
    else {"verification": {"report": {"artifact": "artifacts/" + remote_name, "data": data}}}
)
print(json.dumps({
    "batch_id": sys.argv[5],
    "status": "running",
    "stage": "tool_alignment." + ("calibration" if key == "calibration_result" else "verification"),
    "message": sys.argv[4],
    "chapters": {"tool_alignment": chapter},
}))
PY
  )"
  printf '%s' "${payload}" | "${REPO_ROOT}/scripts/publish_idex_acceptance.sh" update
}

activity_pid=""
activity_id=""
set_activity_operation() {
  local step="$1" operation="$2" progress="${3:-${operation}}"
  # Keep the same activity identity while changing the operation. This makes
  # long deployment/restart windows visible instead of leaving the dashboard
  # stuck on the preceding correction label.
  python3 - "${dashboard_batch_id}" "${activity_id}" "${step}" "${operation}" "${progress}" <<'PY' | "${REPO_ROOT}/scripts/publish_idex_acceptance.sh" activity >/dev/null 2>&1 || true
import datetime as dt, json, sys
now = dt.datetime.now(dt.timezone.utc).isoformat()
print(json.dumps({
    "attempt_id": sys.argv[1], "activity_id": sys.argv[2],
    "owner": "multi-head-zero-shell", "state": "busy", "step": int(sys.argv[3]),
    "operation": sys.argv[4], "progress": sys.argv[5],
    "started_at": now, "heartbeat_at": now,
}))
PY
}
start_activity_heartbeat() {
  local step="$1" operation="$2"
  activity_id="$(python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"
  python3 - "${dashboard_batch_id}" "${activity_id}" "${step}" "${operation}" <<'PY' | "${REPO_ROOT}/scripts/publish_idex_acceptance.sh" activity >/dev/null 2>&1 || true
import datetime as dt, json, sys
now = dt.datetime.now(dt.timezone.utc).isoformat()
print(json.dumps({"attempt_id": sys.argv[1], "activity_id": sys.argv[2], "owner": "multi-head-zero-shell", "state": "busy", "step": int(sys.argv[3]), "operation": sys.argv[4], "progress": "Starting operation", "started_at": now, "heartbeat_at": now}))
PY
  (
    while true; do
      python3 - "${dashboard_batch_id}" "${activity_id}" <<'PY' | "${REPO_ROOT}/scripts/publish_idex_acceptance.sh" heartbeat >/dev/null 2>&1 || true
import datetime as dt
import json
import sys
now = dt.datetime.now(dt.timezone.utc).isoformat()
print(json.dumps({"attempt_id": sys.argv[1], "activity_id": sys.argv[2], "heartbeat_at": now}))
PY
      sleep 5
    done
  ) &
  activity_pid="$!"
}
stop_activity_heartbeat() {
  if [[ -n "${activity_pid}" ]]; then
    kill "${activity_pid}" 2>/dev/null || true
    wait "${activity_pid}" 2>/dev/null || true
    activity_pid=""
  fi
}

run_remote_batch() {
  local mode="$1"
  local run_id="$2"
  local output_dir="$3"
  mkdir -p "${output_dir}"
  echo "Multi-head-zero ${mode} batch: ${run_id}"
  local remote_command
  local remote_output_root="${DASHBOARD_ROOT}/runs/${dashboard_batch_id}/tool_alignment"
  remote_command="MULTI_HEAD_ZERO_BATCH_MODE=$(printf '%q' "${mode}") MULTI_HEAD_ZERO_BATCH_RUN_ID=$(printf '%q' "${run_id}") IDEX_CALIBRATION_BATCH_ID=$(printf '%q' "${dashboard_batch_id}") MULTI_HEAD_ZERO_OUTPUT_DIR=$(printf '%q' "${remote_output_root}")"
  remote_command+=" IDEX_CALIBRATION_RUN_SCOPE=$(printf '%q' "${IDEX_CALIBRATION_RUN_SCOPE:-tool_alignment}")"
  remote_command+=" ${REMOTE_HELPER} --tool ${tool}"
  local remote_status
  set +e
  ssh "${REMOTE_HOST}" "${remote_command}" 2>&1 | tee "${output_dir}/remote.log"
  remote_status="${PIPESTATUS[0]}"
  set -e
  # Preflight failures (for example, a failed G28) happen before the helper
  # creates its immutable run directory.  Preserve the local remote.log, but do
  # not obscure the real printer error with a secondary scp "not found" error.
  if ssh "${REMOTE_HOST}" "test -d '${remote_output_root}/${run_id}'"; then
    scp -q -r "${REMOTE_HOST}:${remote_output_root}/${run_id}/." "${output_dir}/"
  else
    echo "Remote batch produced no artifact directory; preflight failed before acquisition." >&2
  fi
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
transaction_dir="$(mktemp -d "${TMPDIR:-/tmp}/mhz-calibration.XXXXXX")"
cp "${REPO_ROOT}/klipper_setup/klipper_config/calib.yaml" "${transaction_dir}/calib.yaml"
cp "${REPO_ROOT}/klipper_setup/klipper_config/printer.cfg" "${transaction_dir}/printer.cfg"
rollback_alignment() {
  echo "Tool-alignment candidate failed; restoring source calibration..." >&2
  # Prefer the last accepted checkpoint on the Pi.  The transaction snapshot
  # remains the safe fallback for a first-ever chapter run.
  local checkpoint
  checkpoint="$(ssh "${REMOTE_HOST}" "python3 - <<'PY'
import json
from pathlib import Path
try:
    state = json.loads(Path('${DASHBOARD_ROOT}/data/accepted.json').read_text())
    print((state.get('accepted', {}).get('tool_alignment') or {}).get('checkpoint') or '')
except (OSError, ValueError):
    print('')
PY
")"
  if [[ -n "${checkpoint}" ]] && ssh "${REMOTE_HOST}" "test -f '${DASHBOARD_ROOT}/${checkpoint}'"; then
    scp -q "${REMOTE_HOST}:${DASHBOARD_ROOT}/${checkpoint}" "${REPO_ROOT}/klipper_setup/klipper_config/calib.yaml"
    python3 "${REPO_ROOT}/klipper_setup/klipper_config/generate_printer_cfg.py"
  else
    cp "${transaction_dir}/calib.yaml" "${REPO_ROOT}/klipper_setup/klipper_config/calib.yaml"
    cp "${transaction_dir}/printer.cfg" "${REPO_ROOT}/klipper_setup/klipper_config/printer.cfg"
  fi
  "${UPDATE_SCRIPT}"
  "${UPDATE_SCRIPT}" --check
}
cleanup_transaction() {
  rm -rf -- "${transaction_dir}"
}
trap cleanup_transaction EXIT
printer_console "paired calibration complete; applying absolute T0/T1 XY and T1 Z correction"
echo "Applying absolute T0/T1 XY and T1 Z correction..."
start_activity_heartbeat 4 "Applying T0/T1 alignment correction"
if ! python "${APPLY_SCRIPT}" \
    --t0-run "${calibration_dir}/T0" \
    --t1-run "${calibration_dir}/T1" \
    --result "${calibration_result}"; then
  stop_activity_heartbeat
  rollback_alignment
  exit 1
fi
dashboard_publish "${calibration_result}" "${calibration_id}_calibration_result.json" "calibration_result" "Absolute XY correction calculated"

printer_console "absolute XY and T1 Z correction calculated; deploying configuration"
echo "Deploying paired calibration and checking parity..."
set_activity_operation 4 "Deploying corrected T0/T1 configuration" "Waiting for Klippy restart and parity checks"
if ! "${UPDATE_SCRIPT}" || ! "${UPDATE_SCRIPT}" --check; then
  stop_activity_heartbeat
  rollback_alignment
  exit 1
fi
set_activity_operation 4 "T0/T1 configuration deployed" "Preparing 13-contact verification"
stop_activity_heartbeat
printer_console "configuration deployment parity passed; starting 13-contact verification"

verification_id="${timestamp}_T0_T1_verification"
verification_dir="${LOCAL_OUT_ROOT}/${verification_id}"
run_remote_batch verification "${verification_id}" "${verification_dir}"

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
  checkpoint_name="${verification_id}_accepted_calib.yaml"
  scp -q "${REPO_ROOT}/klipper_setup/klipper_config/calib.yaml" "${REMOTE_HOST}:${DASHBOARD_ROOT}/artifacts/${checkpoint_name}"
  acceptance_payload="$(python3 - "${calibration_result}" "${verification_dir}/paired_report/verification_report.json" "${checkpoint_name}" "${dashboard_batch_id}" "${IDEX_CALIBRATION_RUN_SCOPE:-tool_alignment}" <<'PY'
import json, sys
calibration = json.load(open(sys.argv[1], encoding='utf-8'))
verification = json.load(open(sys.argv[2], encoding='utf-8'))
target = calibration.get('target_center') or verification.get('target_center') or {}
centres = calibration.get('measured_centers') or {}
target_endstops = calibration.get('target_endstops') or {}
t0, t1 = target_endstops.get('t0', {}), target_endstops.get('t1', {})
print(json.dumps({
  'chapter': 'tool_alignment',
  'status': 'completed', 'stage': 'tool_alignment.completed',
  'entry': {
    'status': 'accepted', 'chapter': 'tool_alignment', 'attempt_id': sys.argv[4],
    'run_scope': sys.argv[5], 'artifact': 'artifacts/' + sys.argv[3],
    'data': {'calibration': {'result': {'artifact': 'artifacts/' + sys.argv[3], 'data': calibration}},
             'verification': {'report': {'data': verification}}},
    'invariants': {
      'fixed_inputs': {'source_config_fingerprint': calibration.get('source_config_fingerprint'), 'target_center': target},
      't0_xy': [t0.get('x_endstop'), t0.get('y_endstop')],
      't1_xy': [t1.get('x_endstop'), t1.get('y_endstop')],
      'relative_z_delta': (calibration.get('measured_t1_minus_t0') or {}).get('z'),
      't0_frame': [t0.get('x_endstop'), t0.get('y_endstop'), t0.get('z_endstop')],
    },
    'checkpoint': 'artifacts/' + sys.argv[3],
  },
  'batch_id': sys.argv[4],
}))
PY
  )"
  printf '%s' "${acceptance_payload}" | "${REPO_ROOT}/scripts/publish_idex_acceptance.sh" accept
else
  printer_console "paired verification FAILED; inspect /calibration"
  rollback_alignment
  failure_payload="$(python3 - "${dashboard_batch_id}" "${verification_dir}/paired_report/verification_report.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[2], encoding='utf-8'))
print(json.dumps({'batch_id': sys.argv[1], 'status': 'failed', 'stage': 'tool_alignment.verification', 'error': '; '.join(report.get('failure_reasons') or ['paired verification failed']), 'rollback': 'restored last accepted calib.yaml checkpoint'}))
PY
  )"
  printf '%s' "${failure_payload}" | "${REPO_ROOT}/scripts/publish_idex_acceptance.sh" fail
fi

echo "Multi-head-zero full calibration complete: ${calibration_dir}"
echo "Verification report: ${verification_dir}/paired_report/verification_report.json"
exit "${verification_status}"
