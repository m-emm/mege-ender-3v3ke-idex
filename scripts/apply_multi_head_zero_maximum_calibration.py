#!/usr/bin/env python3
"""Apply a T1 IDEX calibration candidate from two maximum-search manifests."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALIB_PATH = REPO_ROOT / "klipper_setup/klipper_config/calib.yaml"
DEFAULT_GENERATOR_PATH = (
    REPO_ROOT / "klipper_setup/klipper_config/generate_printer_cfg.py"
)
MAX_CORRECTION_MM = 2.0


class CalibrationError(RuntimeError):
    pass


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Update tools.t1 endstops from converged T0/T1 multi-head-zero "
            "maximum searches."
        )
    )
    parser.add_argument("--t0-run", type=Path, required=True)
    parser.add_argument("--t1-run", type=Path, required=True)
    parser.add_argument("--calib", type=Path, default=DEFAULT_CALIB_PATH)
    parser.add_argument("--generator", type=Path, default=DEFAULT_GENERATOR_PATH)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the candidate without editing."
    )
    return parser


def _finite(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CalibrationError("%s must be numeric" % label) from exc
    if not math.isfinite(number):
        raise CalibrationError("%s must be finite" % label)
    return number


def load_run(run_dir, expected_tool):
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise CalibrationError("missing manifest: %s" % manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("tool") != expected_tool:
        raise CalibrationError(
            "%s is not a %s maximum-search run" % (manifest_path, expected_tool)
        )
    if (
        manifest.get("strategy") != "max-search"
        or manifest.get("status") != "completed"
    ):
        raise CalibrationError("%s is not a completed maximum search" % manifest_path)
    search = manifest.get("maximum_search")
    if not isinstance(search, dict) or search.get("termination_reason") != "converged":
        raise CalibrationError("%s did not converge" % manifest_path)
    maximum = search.get("found_maximum")
    if not isinstance(maximum, dict):
        raise CalibrationError("%s has no observed maximum" % manifest_path)
    return {
        "manifest": manifest,
        "x": _finite(maximum.get("x"), "%s maximum X" % expected_tool),
        "y": _finite(maximum.get("y"), "%s maximum Y" % expected_tool),
        "z": _finite(maximum.get("trigger_z"), "%s maximum Z" % expected_tool),
    }


def source_endstops(run):
    settings = (
        run["manifest"]
        .get("initial_status", {})
        .get("configfile", {})
        .get("settings", {})
    )
    macro = settings.get("gcode_macro _idex_tool_state")
    if not isinstance(macro, dict):
        raise CalibrationError("run manifest lacks _IDEX_TOOL_STATE config provenance")
    try:
        return {
            "t0": {
                "x_endstop": _finite(
                    settings["stepper_x"]["position_endstop"], "source T0 X endstop"
                ),
                "y_endstop": _finite(
                    macro["variable_t0_y_endstop"], "source T0 Y endstop"
                ),
                "z_endstop": _finite(
                    macro["variable_t0_z_endstop"], "source T0 Z endstop"
                ),
            },
            "t1": {
                "x_endstop": _finite(
                    settings["dual_carriage"]["position_endstop"],
                    "source T1 X endstop",
                ),
                "y_endstop": _finite(
                    macro["variable_t1_y_endstop"], "source T1 Y endstop"
                ),
                "z_endstop": _finite(
                    macro["variable_t1_z_endstop"], "source T1 Z endstop"
                ),
            },
        }
    except (KeyError, TypeError) as exc:
        raise CalibrationError(
            "run manifest has incomplete endstop provenance"
        ) from exc


def verify_sources(t0_run, t1_run, calibration):
    source_t0 = source_endstops(t0_run)
    source_t1 = source_endstops(t1_run)
    if source_t0 != source_t1:
        raise CalibrationError("T0 and T1 runs used different endstop calibrations")
    for tool in ("t0", "t1"):
        for key, source_value in source_t0[tool].items():
            current = _finite(calibration["tools"][tool][key], "%s.%s" % (tool, key))
            if abs(current - source_value) > 0.0011:
                raise CalibrationError(
                    "calib.yaml %s.%s %.6f no longer matches the search source %.6f"
                    % (tool, key, current, source_value)
                )
    return source_t0


def suggested_t1_endstops(source, t0_run, t1_run):
    error = {axis: t1_run[axis] - t0_run[axis] for axis in ("x", "y", "z")}
    if any(abs(value) > MAX_CORRECTION_MM for value in error.values()):
        raise CalibrationError(
            "refusing correction larger than %.1f mm: %s" % (MAX_CORRECTION_MM, error)
        )
    # Match the existing vision-candidate conventions. X/Y candidates subtract
    # the observed T1-minus-T0 alignment error. Z top-endstop corrections are
    # additive: a negative T1 physical delta means T1 is low and must rise.
    return error, {
        "x_endstop": source["t1"]["x_endstop"] - error["x"],
        "y_endstop": source["t1"]["y_endstop"] - error["y"],
        "z_endstop": source["t1"]["z_endstop"] + error["z"],
    }


def rewrite_t1_endstops(calib_path, suggested):
    lines = calib_path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_tools = False
    in_t1 = False
    replaced = {key: 0 for key in suggested}
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
        if not in_t1:
            continue
        for key, value in suggested.items():
            if re.match(r"^    %s:\s*" % re.escape(key), line):
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                lines[index] = "    %s: %.3f%s" % (key, value, newline)
                replaced[key] += 1
    if any(count != 1 for count in replaced.values()):
        raise CalibrationError("could not uniquely update tools.t1: %s" % replaced)
    temporary = calib_path.with_name(".%s.%d.tmp" % (calib_path.name, os.getpid()))
    temporary.write_text("".join(lines), encoding="utf-8")
    os.replace(temporary, calib_path)


def main(argv):
    args = build_parser().parse_args(argv)
    t0_run = load_run(args.t0_run, "T0")
    t1_run = load_run(args.t1_run, "T1")
    calibration = yaml.safe_load(args.calib.read_text(encoding="utf-8"))
    source = verify_sources(t0_run, t1_run, calibration)
    error, suggested = suggested_t1_endstops(source, t0_run, t1_run)
    print(
        "Observed T1-minus-T0 maximum error: "
        "X=%+.6f Y=%+.6f Z=%+.6f mm" % (error["x"], error["y"], error["z"])
    )
    print(
        "Suggested tools.t1 endstops: "
        "X=%.6f Y=%.6f Z=%.6f"
        % (suggested["x_endstop"], suggested["y_endstop"], suggested["z_endstop"])
    )
    if args.dry_run:
        return 0
    rewrite_t1_endstops(args.calib, suggested)
    subprocess.run([sys.executable, str(args.generator)], check=True)
    print("Updated %s and regenerated printer.cfg" % args.calib)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except CalibrationError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
