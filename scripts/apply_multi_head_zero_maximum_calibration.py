#!/usr/bin/env python3
"""Rebase IDEX X/Y to the multi-head-zero target and align T1 Z."""

from __future__ import annotations

import argparse
import datetime as dt
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
        description="Update T0/T1 X/Y and T1 Z from paired multi-head-zero calibrations."
    )
    parser.add_argument("--t0-run", type=Path, required=True)
    parser.add_argument("--t1-run", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--calib", type=Path, default=DEFAULT_CALIB_PATH)
    parser.add_argument("--generator", type=Path, default=DEFAULT_GENERATOR_PATH)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the candidate without editing."
    )
    return parser


def finite(value, label):
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
            "%s is not a %s calibration run" % (manifest_path, expected_tool)
        )
    if manifest.get("schema_version") != 4 or manifest.get("workflow") != "calibration":
        raise CalibrationError("%s is not a schema-v4 calibration run" % manifest_path)
    if manifest.get("status") != "completed":
        raise CalibrationError("%s is not completed" % manifest_path)
    calibration = manifest.get("calibration")
    if (
        not isinstance(calibration, dict)
        or calibration.get("algorithm") != "two_stage_sphere_ring_calibration_v1"
        or calibration.get("contact_count") != 18
        or calibration.get("termination_reason") != "phase_2_complete"
    ):
        raise CalibrationError(
            "%s has no valid 18-contact calibration result" % manifest_path
        )
    phase_1 = calibration.get("phase_1")
    phase_2 = calibration.get("phase_2")
    if not isinstance(phase_1, dict) or not isinstance(phase_2, dict):
        raise CalibrationError("%s lacks calibration phases" % manifest_path)
    fit = phase_1.get("fit")
    summit = phase_1.get("summit")
    refined = phase_2.get("refined_center")
    if not isinstance(fit, dict) or fit.get("status") != "valid":
        raise CalibrationError("%s has no valid phase-1 fit" % manifest_path)
    if not isinstance(summit, dict) or not isinstance(refined, dict):
        raise CalibrationError("%s lacks summit or refined centre" % manifest_path)
    if phase_2.get("ring_contact_count") != 8:
        raise CalibrationError(
            "%s does not contain eight completed ring contacts" % manifest_path
        )
    return {
        "manifest": manifest,
        "run_dir": run_dir.resolve(),
        "x": finite(refined.get("x"), "%s refined X" % expected_tool),
        "y": finite(refined.get("y"), "%s refined Y" % expected_tool),
        "z": finite(
            summit.get("trigger_z"), "%s direct logical summit Z" % expected_tool
        ),
        "ball_radius_mm": finite(calibration.get("ball_radius_mm"), "ball radius"),
        "ring_radius_mm": finite(calibration.get("ring_radius_mm"), "ring radius"),
    }


def source_config_fingerprint(run):
    initial_status = run["manifest"].get("initial_status", {})
    macro = initial_status.get("gcode_macro _IDEX_CONFIG_FINGERPRINT") or (
        initial_status.get("gcode_macro _idex_config_fingerprint")
    )
    if not isinstance(macro, dict) or not macro.get("source_sha256"):
        raise CalibrationError("run manifest lacks configuration fingerprint")
    return str(macro["source_sha256"])


def configured_target(run):
    priors = run["manifest"].get("configured_priors")
    if not isinstance(priors, dict):
        raise CalibrationError("run manifest lacks configured multi-head-zero priors")
    return {
        "x": finite(priors.get("target_x"), "configured ball target X"),
        "y": finite(priors.get("target_y"), "configured ball target Y"),
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
                "x_endstop": finite(
                    settings["stepper_x"]["position_endstop"], "source T0 X endstop"
                ),
                "y_endstop": finite(
                    macro["variable_t0_y_endstop"], "source T0 Y endstop"
                ),
                "z_endstop": finite(
                    macro["variable_t0_z_endstop"], "source T0 Z endstop"
                ),
            },
            "t1": {
                "x_endstop": finite(
                    settings["dual_carriage"]["position_endstop"], "source T1 X endstop"
                ),
                "y_endstop": finite(
                    macro["variable_t1_y_endstop"], "source T1 Y endstop"
                ),
                "z_endstop": finite(
                    macro["variable_t1_z_endstop"], "source T1 Z endstop"
                ),
            },
        }
    except (KeyError, TypeError) as exc:
        raise CalibrationError(
            "run manifest has incomplete endstop provenance"
        ) from exc


def verify_sources(t0_run, t1_run):
    source_t0 = source_endstops(t0_run)
    source_t1 = source_endstops(t1_run)
    if source_t0 != source_t1:
        raise CalibrationError("T0 and T1 runs used different endstop calibrations")
    if (
        abs(t0_run["ball_radius_mm"] - t1_run["ball_radius_mm"]) > 1.0e-9
        or abs(t0_run["ring_radius_mm"] - t1_run["ring_radius_mm"]) > 1.0e-9
    ):
        raise CalibrationError("T0 and T1 runs used different sphere geometry")
    if source_config_fingerprint(t0_run) != source_config_fingerprint(t1_run):
        raise CalibrationError("T0 and T1 runs used different config fingerprints")
    target_t0 = configured_target(t0_run)
    target_t1 = configured_target(t1_run)
    if target_t0 != target_t1:
        raise CalibrationError("T0 and T1 runs used different ball targets")
    return source_t0, target_t0


def generated_config_fingerprint(path):
    match = re.search(
        r'^variable_source_sha256:\s*"([0-9a-f]+)"\s*$',
        path.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    if not match:
        raise CalibrationError("generated printer.cfg lacks a config fingerprint")
    return match.group(1)


def calibration_endstops(calibration):
    return {
        tool: {
            key: finite(calibration["tools"][tool][key], "%s.%s" % (tool, key))
            for key in ("x_endstop", "y_endstop", "z_endstop")
        }
        for tool in ("t0", "t1")
    }


def endstops_match(left, right):
    return all(
        abs(left[tool][key] - right[tool][key]) <= 1.0e-9
        for tool in ("t0", "t1")
        for key in ("x_endstop", "y_endstop", "z_endstop")
    )


def suggested_endstops(source, t0_run, t1_run, target):
    measured_t1_minus_t0 = {
        axis: t1_run[axis] - t0_run[axis] for axis in ("x", "y", "z")
    }
    target_error = {
        "t0": {axis: t0_run[axis] - target[axis] for axis in ("x", "y")},
        "t1": {axis: t1_run[axis] - target[axis] for axis in ("x", "y")},
    }
    applied_delta = {
        "t0": {
            "x_endstop": -target_error["t0"]["x"],
            "y_endstop": -target_error["t0"]["y"],
            "z_endstop": 0.0,
        },
        "t1": {
            "x_endstop": -target_error["t1"]["x"],
            "y_endstop": -target_error["t1"]["y"],
            # T1 logical Z is machine Z minus its active G-code origin. That
            # origin is T0_z_endstop - T1_z_endstop, so increasing the T1
            # endstop increases its reported logical trigger Z.
            "z_endstop": -measured_t1_minus_t0["z"],
        },
    }
    correction_values = [
        value for tool in applied_delta.values() for value in tool.values()
    ]
    if any(abs(value) > MAX_CORRECTION_MM for value in correction_values):
        raise CalibrationError(
            "refusing correction larger than %.1f mm: %s"
            % (MAX_CORRECTION_MM, applied_delta)
        )
    suggested = {
        tool: {
            key: round(source[tool][key] + applied_delta[tool][key], 3)
            for key in ("x_endstop", "y_endstop", "z_endstop")
        }
        for tool in ("t0", "t1")
    }
    return measured_t1_minus_t0, target_error, applied_delta, suggested


def rewrite_endstops(calib_path, suggested):
    lines = calib_path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_tools = False
    active_tool = None
    replaced = {tool: {key: 0 for key in values} for tool, values in suggested.items()}
    for index, line in enumerate(lines):
        stripped = line.rstrip("\r\n")
        if re.match(r"^tools:\s*$", stripped):
            in_tools, active_tool = True, None
            continue
        if in_tools and re.match(r"^[^ ]", line) and line.strip():
            in_tools, active_tool = False, None
        tool_match = re.match(r"^  (t[01]):\s*$", stripped)
        if in_tools and tool_match:
            active_tool = tool_match.group(1)
            continue
        if active_tool and re.match(r"^  [^ ]", line) and line.strip():
            active_tool = None
        if not active_tool or active_tool not in suggested:
            continue
        for key, value in suggested[active_tool].items():
            if re.match(r"^    %s:\s*" % re.escape(key), line):
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                lines[index] = "    %s: %.3f%s" % (key, value, newline)
                replaced[active_tool][key] += 1
    if any(
        count != 1
        for tool_counts in replaced.values()
        for count in tool_counts.values()
    ):
        raise CalibrationError(
            "could not uniquely update tools endstops: %s" % replaced
        )
    temporary = calib_path.with_name(".%s.%d.tmp" % (calib_path.name, os.getpid()))
    temporary.write_text("".join(lines), encoding="utf-8")
    os.replace(temporary, calib_path)


def write_result(
    path,
    *,
    t0_run,
    t1_run,
    source,
    suggested,
    measured_t1_minus_t0,
    target,
    target_error,
    applied_delta,
    target_config_fingerprint,
):
    payload = {
        "schema_version": 3,
        "workflow": "multi_head_zero_calibration_result",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_runs": {"t0": str(t0_run["run_dir"]), "t1": str(t1_run["run_dir"])},
        "source_endstops": source,
        "target_endstops": suggested,
        "measured_t1_minus_t0": measured_t1_minus_t0,
        "target_center": target,
        "measured_centers": {
            "t0": {axis: t0_run[axis] for axis in ("x", "y", "z")},
            "t1": {axis: t1_run[axis] for axis in ("x", "y", "z")},
        },
        "target_error_before_mm": target_error,
        "applied_endstop_delta_mm": applied_delta,
        "source_config_fingerprint": source_config_fingerprint(t0_run),
        "target_config_fingerprint": target_config_fingerprint,
        "ball_radius_mm": t0_run["ball_radius_mm"],
        "ring_radius_mm": t0_run["ring_radius_mm"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main(argv):
    args = build_parser().parse_args(argv)
    t0_run = load_run(args.t0_run, "T0")
    t1_run = load_run(args.t1_run, "T1")
    calibration = yaml.safe_load(args.calib.read_text(encoding="utf-8"))
    source, target_center = verify_sources(t0_run, t1_run)
    (
        measured_t1_minus_t0,
        target_error,
        applied_delta,
        suggested,
    ) = suggested_endstops(source, t0_run, t1_run, target_center)
    current = calibration_endstops(calibration)
    current_matches_source = endstops_match(current, source)
    current_matches_target = endstops_match(current, suggested)
    if not current_matches_source and not current_matches_target:
        raise CalibrationError(
            "calib.yaml no longer matches either the calibration source or its target"
        )
    print(
        "Ball target: X=%.6f Y=%.6f; measured T1-minus-T0: X=%+.6f Y=%+.6f Z=%+.6f mm"
        % (
            target_center["x"],
            target_center["y"],
            measured_t1_minus_t0["x"],
            measured_t1_minus_t0["y"],
            measured_t1_minus_t0["z"],
        )
    )
    print(
        "Applied endstop deltas: T0 X=%+.6f Y=%+.6f; T1 X=%+.6f Y=%+.6f Z=%+.6f mm"
        % (
            applied_delta["t0"]["x_endstop"],
            applied_delta["t0"]["y_endstop"],
            applied_delta["t1"]["x_endstop"],
            applied_delta["t1"]["y_endstop"],
            applied_delta["t1"]["z_endstop"],
        )
    )
    if args.dry_run:
        return 0
    if not current_matches_target:
        rewrite_endstops(args.calib, suggested)
        subprocess.run([sys.executable, str(args.generator)], check=True)
    target_config_fingerprint = generated_config_fingerprint(
        args.generator.parent / "printer.cfg"
    )
    write_result(
        args.result,
        t0_run=t0_run,
        t1_run=t1_run,
        source=source,
        suggested=suggested,
        measured_t1_minus_t0=measured_t1_minus_t0,
        target=target_center,
        target_error=target_error,
        applied_delta=applied_delta,
        target_config_fingerprint=target_config_fingerprint,
    )
    print(
        "Updated %s, regenerated printer.cfg, and wrote %s" % (args.calib, args.result)
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except CalibrationError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
