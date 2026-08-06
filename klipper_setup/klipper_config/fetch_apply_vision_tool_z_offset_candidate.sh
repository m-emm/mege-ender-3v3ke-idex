#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_HOST="${MENDERPI_HOST:-pi@menderpi.local}"
REMOTE_ROOT="${VISION_CALIBRATION_REMOTE_ROOT:-/home/pi/printer_data/vision/calibration}"
CALIB_PATH="${VISION_CALIB_PATH:-${SCRIPT_DIR}/calib.yaml}"
GENERATOR="${VISION_PRINTER_CFG_GENERATOR:-${SCRIPT_DIR}/generate_printer_cfg.py}"
FACT_NAME="camera.nozzle_cam.nozzle_tip.xz_sweep_report"

candidate_tmp_dir="$(mktemp -d /tmp/vision-tool-z-offset-candidate.XXXXXX)"
cleanup() {
  rm -rf -- "${candidate_tmp_dir}"
}
trap cleanup EXIT

catalog_path="${candidate_tmp_dir}/catalog.json"
fact_set_path="${candidate_tmp_dir}/fact_set.json"

echo "Fetching the latest tool X/Z sweep report from ${REMOTE_HOST}"
ssh "${REMOTE_HOST}" \
  "/usr/local/bin/vision_calibration.py rebuild-catalog" \
  >"${catalog_path}"

remote_fact_set="$(python3 - "${catalog_path}" "${FACT_NAME}" <<'PY'
import json
import sys
from pathlib import PurePosixPath

catalog_path, fact_name = sys.argv[1:]
catalog = json.load(open(catalog_path, encoding="utf-8"))
head = catalog.get("heads", {}).get(fact_name)
if not isinstance(head, dict):
    raise SystemExit(
        f"no current {fact_name} fact; run idex_tool_xz_sweep_report first"
    )
relative = PurePosixPath(str(head.get("fact_set_path", "")))
if relative.is_absolute() or not relative.parts or ".." in relative.parts:
    raise SystemExit(f"unsafe fact-set path in catalog: {relative}")
if head.get("fact_set_hash") in catalog.get("stale_fact_sets", {}):
    print(
        f"WARNING: current {fact_name} fact is marked stale; provenance checks "
        "will still require matching acquisition Z endstops",
        file=sys.stderr,
    )
print(relative.as_posix())
PY
)"

echo "Fetching ${REMOTE_ROOT}/${remote_fact_set}"
scp "${REMOTE_HOST}:${REMOTE_ROOT}/${remote_fact_set}" "${fact_set_path}"

python3 - "${catalog_path}" "${fact_set_path}" "${CALIB_PATH}" "${FACT_NAME}" <<'PY'
import json
import hashlib
import math
import os
import re
import sys
from pathlib import Path

import yaml

catalog_path, fact_set_path, calib_path = map(Path, sys.argv[1:4])
fact_name = sys.argv[4]
catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
fact_set = json.loads(fact_set_path.read_text(encoding="utf-8"))
head = catalog["heads"][fact_name]
fact_payload = dict(fact_set)
fact_payload.pop("fact_set_hash", None)
calculated_hash = "sha256:" + hashlib.sha256(
    json.dumps(
        fact_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
).hexdigest()
if fact_set.get("fact_set_hash") != calculated_hash:
    raise SystemExit("fetched X/Z report fact-set content hash is invalid")
if fact_set.get("fact_set_hash") != head.get("fact_set_hash"):
    raise SystemExit(
        "fetched X/Z report hash does not match the current catalog head"
    )

fact = next(
    (item for item in fact_set.get("facts", []) if item.get("name") == fact_name),
    None,
)
if not isinstance(fact, dict):
    raise SystemExit(f"fetched fact set does not contain {fact_name}")
if fact.get("role") != "diagnostic" or int(fact.get("definition_version", 0)) != 1:
    raise SystemExit("tool X/Z sweep report has an unsupported fact contract")

value = fact.get("value")
if not isinstance(value, dict):
    raise SystemExit("tool X/Z sweep report value is missing")
curve = value.get("shared_z_curve_fit")
if not isinstance(curve, dict) or not curve.get("available"):
    reason = curve.get("reason", "shared curve unavailable") if isinstance(curve, dict) else "shared curve missing"
    raise SystemExit(f"tool X/Z sweep has no applicable Z-offset candidate: {reason}")

delta = curve.get("t1_z_delta_mm")
if not isinstance(delta, (int, float)) or not math.isfinite(float(delta)):
    raise SystemExit("tool X/Z sweep T1 Z delta is not finite")
delta = float(delta)
if abs(delta) > 1.500001:
    raise SystemExit(f"tool X/Z sweep T1 Z delta {delta:+.6f} mm is out of bounds")

acquisition = value.get("acquisition_calibration")
source_z = acquisition.get("tool_z_endstops_mm") if isinstance(acquisition, dict) else None
if not isinstance(source_z, dict) or not all(tool in source_z for tool in ("t0", "t1")):
    raise SystemExit(
        "tool X/Z sweep lacks acquisition Z-endstop provenance; deploy the "
        "updated vision code and rerun the sweep"
    )
source_t0 = float(source_z["t0"])
source_t1 = float(source_z["t1"])

local = yaml.safe_load(calib_path.read_text(encoding="utf-8"))
local_t0 = float(local["tools"]["t0"]["z_endstop"])
local_t1 = float(local["tools"]["t1"]["z_endstop"])
for tool, current, source in (
    ("T0", local_t0, source_t0),
    ("T1", local_t1, source_t1),
):
    if abs(current - source) > 0.0011:
        raise SystemExit(
            f"local calib.yaml {tool} Z endstop {current:.6f} does not match "
            f"the sweep acquisition source {source:.6f}; refusing to apply"
        )

# The Z endstops are at the top of travel. A negative fitted physical T1 Z
# delta means T1 is too low at the same command, so raising it requires reducing
# its configured top-endstop coordinate. Therefore the correction is additive.
suggested_t1 = source_t1 + delta
if not math.isfinite(suggested_t1):
    raise SystemExit("calculated T1 Z endstop is not finite")

lines = calib_path.read_text(encoding="utf-8").splitlines(keepends=True)
in_tools = False
in_t1 = False
replaced = 0
for index, line in enumerate(lines):
    stripped = line.rstrip("\r\n")
    if re.match(r"^tools:\s*$", stripped):
        in_tools = True
        in_t1 = False
        continue
    if in_tools and re.match(r"^[^ ]", line) and line.strip():
        in_tools = False
        in_t1 = False
    if in_tools and re.match(r"^  t1:\s*$", stripped):
        in_t1 = True
        continue
    if in_t1 and re.match(r"^  [^ ]", line) and line.strip():
        in_t1 = False
    if in_t1 and re.match(r"^    z_endstop:\s*", line):
        newline = "\r\n" if line.endswith("\r\n") else "\n"
        lines[index] = f"    z_endstop: {suggested_t1:.3f}{newline}"
        replaced += 1

if replaced != 1:
    raise SystemExit(f"could not uniquely update tools.t1.z_endstop: {replaced}")

temporary = calib_path.with_name(f".{calib_path.name}.tool-z-{os.getpid()}.tmp")
temporary.write_text("".join(lines), encoding="utf-8")
os.replace(temporary, calib_path)

direction = "higher" if delta < 0 else "lower" if delta > 0 else "unchanged"
print(
    "Applied tool-Z offset candidate:\n"
    f"  fitted T1 physical Z delta: {delta:+.6f} mm\n"
    f"  top-endstop correction: {source_t1:.6f} + ({delta:+.6f}) "
    f"= {suggested_t1:.6f} mm\n"
    f"  expected T1 nozzle direction: {direction}\n"
    f"  shared-curve RMS: {float(curve['rms_slope_px_per_mm']):.6f} px/mm\n"
    f"  included rows: {len(curve.get('included_rows', []))}; "
    f"excluded rows: {len(curve.get('excluded_rows', []))}"
)
PY

echo "Regenerating the versioned printer.cfg"
python3 "${GENERATOR}"

echo "Local calibration is ready for review and deployment:"
echo "  git diff -- '${CALIB_PATH}' '${SCRIPT_DIR}/printer.cfg'"
echo "  ${SCRIPT_DIR}/update_menderpi.sh"
echo "  ${SCRIPT_DIR}/deploy_webcam_vision.sh"
echo "No printer configuration was changed by this helper; deployment remains explicit."
