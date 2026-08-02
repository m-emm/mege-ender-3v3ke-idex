#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
REMOTE_ROOT="/home/pi/printer_data/vision/calibration"
CALIB_PATH="${SCRIPT_DIR}/calib.yaml"
GENERATOR="${SCRIPT_DIR}/generate_printer_cfg.py"
RUN_NAME="idex_tool_xy_candidate_$(date -u +%Y%m%dT%H%M%SZ)"

candidate_tmp_dir="$(mktemp -d /tmp/vision-tool-xy-candidate.XXXXXX)"
cleanup() {
  rm -rf -- "${candidate_tmp_dir}"
}
trap cleanup EXIT

result_path="${candidate_tmp_dir}/result.json"
candidate_path="${candidate_tmp_dir}/calib_candidate.yaml"

echo "Calculating the latest tool-XY candidate on ${REMOTE_HOST}"
ssh "${REMOTE_HOST}" \
  "/usr/local/bin/vision_calibration.py compute idex_tool_xy_candidate --name '${RUN_NAME}'" \
  >"${result_path}"

job_id="$(python3 - "${result_path}" <<'PY'
import json
import sys

result = json.load(open(sys.argv[1], encoding="utf-8"))
analysis = result["analysis"]
if analysis["state"] != "accepted":
    raise SystemExit(
        "remote tool-XY candidate was rejected: "
        + "; ".join(analysis["details"].get("reasons", []))
    )
print(result["job_id"])
PY
)"
analysis_id="$(python3 - "${result_path}" <<'PY'
import json
import sys

print(json.load(open(sys.argv[1], encoding="utf-8"))["analysis"]["analysis_run_id"])
PY
)"

remote_candidate="${REMOTE_ROOT}/jobs/${job_id}/analysis/${analysis_id}/calib_candidate.yaml"
echo "Fetching ${remote_candidate}"
scp "${REMOTE_HOST}:${remote_candidate}" "${candidate_path}"

python3 - "${result_path}" "${candidate_path}" "${CALIB_PATH}" <<'PY'
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import yaml

result_path, candidate_path, calib_path = map(Path, sys.argv[1:])
result = json.loads(result_path.read_text(encoding="utf-8"))
details = result["analysis"]["details"]
candidate_bytes = candidate_path.read_bytes()
candidate_hash = "sha256:" + hashlib.sha256(candidate_bytes).hexdigest()
if candidate_hash != details["candidate_calib_sha256"]:
    raise SystemExit(
        f"candidate hash mismatch: fetched {candidate_hash}, "
        f"expected {details['candidate_calib_sha256']}"
    )

local = yaml.safe_load(calib_path.read_text(encoding="utf-8"))
candidate = yaml.safe_load(candidate_bytes)
source = details["source_endstop_xy_mm"]
for tool in ("t0", "t1"):
    local_xy = [
        float(local["tools"][tool]["x_endstop"]),
        float(local["tools"][tool]["y_endstop"]),
    ]
    expected_xy = [float(item) for item in source[tool]]
    if any(abs(a - b) > 0.0011 for a, b in zip(local_xy, expected_xy)):
        raise SystemExit(
            f"local calib.yaml {tool.upper()} X/Y {local_xy} does not match "
            f"the acquisition source {expected_xy}; refusing to apply"
        )

suggested = [float(item) for item in details["suggested_t1_endstop_xy_mm"]]
candidate_xy = [
    float(candidate["tools"]["t1"]["x_endstop"]),
    float(candidate["tools"]["t1"]["y_endstop"]),
]
if any(abs(a - b) > 1.0e-9 for a, b in zip(candidate_xy, suggested)):
    raise SystemExit("candidate YAML does not contain the published T1 suggestion")

lines = calib_path.read_text(encoding="utf-8").splitlines(keepends=True)
in_tools = False
in_t1 = False
replaced = {"x_endstop": 0, "y_endstop": 0}
for index, line in enumerate(lines):
    if re.match(r"^tools:\s*$", line.rstrip("\r\n")):
        in_tools = True
        in_t1 = False
        continue
    if in_tools and re.match(r"^[^ ]", line) and line.strip():
        in_tools = False
        in_t1 = False
    if in_tools and re.match(r"^  t1:\s*$", line.rstrip("\r\n")):
        in_t1 = True
        continue
    if in_t1 and re.match(r"^  [^ ]", line) and line.strip():
        in_t1 = False
    if not in_t1:
        continue
    for key, value in zip(("x_endstop", "y_endstop"), suggested):
        if re.match(rf"^    {key}:\s*", line):
            newline = "\r\n" if line.endswith("\r\n") else "\n"
            lines[index] = f"    {key}: {value:.3f}{newline}"
            replaced[key] += 1

if replaced != {"x_endstop": 1, "y_endstop": 1}:
    raise SystemExit(f"could not uniquely update tools.t1 X/Y: {replaced}")

temporary = calib_path.with_name(f".{calib_path.name}.tool-xy-{os.getpid()}.tmp")
temporary.write_text("".join(lines), encoding="utf-8")
os.replace(temporary, calib_path)

error = details["alignment_error_xy_mm"]
print(
    "Applied tool-XY candidate:\n"
    f"  measured T1-T0 error: X={float(error[0]):+.6f} "
    f"Y={float(error[1]):+.6f} mm\n"
    f"  T1 endstop: X={source['t1'][0]:.6f} -> {suggested[0]:.6f}, "
    f"Y={source['t1'][1]:.6f} -> {suggested[1]:.6f}"
)
PY

echo "Regenerating the versioned printer.cfg"
python3 "${GENERATOR}"

echo "Local calibration is ready for review and deployment:"
echo "  git diff -- '${CALIB_PATH}' '${SCRIPT_DIR}/printer.cfg'"
echo "  ${SCRIPT_DIR}/update_menderpi.sh"
echo "  ${SCRIPT_DIR}/deploy_webcam_vision.sh"
echo "Candidate review: http://menderpi.local/vision/calibration/jobs/${job_id}/analysis/${analysis_id}/"
