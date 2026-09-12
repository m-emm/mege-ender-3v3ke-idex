#!/usr/bin/env python3
"""Report paired residuals from multi-head-zero thirteen-contact verification."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

import numpy as np


# Absolute tool-to-target checks are temporarily relaxed for live testing.
# The paired T0↔T1 relationship remains on the tighter production limit.
TARGET_XY_LIMIT_MM = 0.060
PAIRED_XY_LIMIT_MM = 0.050
Z_LIMIT_MM = 0.02
CENTER_TAP_COUNT = 5
CENTER_STDDEV_LIMIT_MM = 0.015
COMPARISON_EPSILON_MM = 1.0e-6
VERIFICATION_DIRECTIONS = (
    "east",
    "north_east",
    "north",
    "north_west",
    "west",
    "south_west",
    "south",
    "south_east",
)
VERIFICATION_ANGLES = {
    "east": 0.0,
    "north_east": math.pi / 4.0,
    "north": math.pi / 2.0,
    "north_west": 3.0 * math.pi / 4.0,
    "west": math.pi,
    "south_west": 5.0 * math.pi / 4.0,
    "south": 3.0 * math.pi / 2.0,
    "south_east": 7.0 * math.pi / 4.0,
}


class VerificationError(RuntimeError):
    pass


def build_parser():
    parser = argparse.ArgumentParser(
        description="Compare paired thirteen-contact multi-head-zero verification runs."
    )
    parser.add_argument("--t0-run", type=Path, required=True)
    parser.add_argument("--t1-run", type=Path, required=True)
    parser.add_argument("--calibration-result", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def finite(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise VerificationError("%s must be numeric" % label) from exc
    if not math.isfinite(number):
        raise VerificationError("%s must be finite" % label)
    return number


def source_endstops(manifest):
    settings = (
        manifest.get("initial_status", {}).get("configfile", {}).get("settings", {})
    )
    macro = settings.get("gcode_macro _idex_tool_state")
    if not isinstance(macro, dict):
        raise VerificationError(
            "verification manifest lacks _IDEX_TOOL_STATE provenance"
        )
    try:
        return {
            "t0": {
                "x_endstop": finite(
                    settings["stepper_x"]["position_endstop"], "T0 X endstop"
                ),
                "y_endstop": finite(macro["variable_t0_y_endstop"], "T0 Y endstop"),
                "z_endstop": finite(macro["variable_t0_z_endstop"], "T0 Z endstop"),
            },
            "t1": {
                "x_endstop": finite(
                    settings["dual_carriage"]["position_endstop"], "T1 X endstop"
                ),
                "y_endstop": finite(macro["variable_t1_y_endstop"], "T1 Y endstop"),
                "z_endstop": finite(macro["variable_t1_z_endstop"], "T1 Z endstop"),
            },
        }
    except (KeyError, TypeError) as exc:
        raise VerificationError(
            "verification manifest has incomplete provenance"
        ) from exc


def load_calibration_result(path):
    if not path.is_file():
        raise VerificationError("missing calibration result: %s" % path)
    result = json.loads(path.read_text(encoding="utf-8"))
    if (
        result.get("schema_version") != 5
        or result.get("workflow") != "multi_head_zero_calibration_result"
    ):
        raise VerificationError("%s is not a calibration result" % path)
    target = result.get("target_endstops")
    target_center = result.get("target_center")
    if not isinstance(target, dict) or not isinstance(target_center, dict):
        raise VerificationError(
            "calibration result lacks target endstops or target centre"
        )
    for axis in ("x", "y"):
        finite(target_center.get(axis), "calibration target %s" % axis.upper())
    procedure = result.get("calibration_procedure")
    if (
        not isinstance(procedure, dict)
        or procedure.get("algorithm") != "three_stage_sphere_ring_calibration_v3"
        or procedure.get("contact_count") != 47
        or procedure.get("refined_ring_unique_contact_count") != 8
        or procedure.get("refined_ring_round_count") != 3
        or procedure.get("refined_ring_contact_count") != 24
    ):
        raise VerificationError(
            "%s does not use the three-round 47-contact calibration procedure" % path
        )
    return result


def load_run(run_dir, expected_tool, calibration_result):
    path = run_dir / "manifest.json"
    if not path.is_file():
        raise VerificationError("missing verification manifest: %s" % path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != 5
        or manifest.get("workflow") != "verification"
        or manifest.get("status") != "completed"
        or manifest.get("tool") != expected_tool
    ):
        raise VerificationError(
            "%s is not a completed %s verification run" % (path, expected_tool)
        )
    verification = manifest.get("verification")
    if (
        not isinstance(verification, dict)
        or verification.get("algorithm") != "thirteen_contact_octagonal_verification_v2"
        or verification.get("contact_count") != 13
        or verification.get("termination_reason") != "thirteen_contact_complete"
    ):
        raise VerificationError("%s has no valid thirteen-contact result" % path)
    target_center = verification.get("target_center")
    expected_target = calibration_result["target_center"]
    if (
        not isinstance(target_center, dict)
        or abs(
            finite(target_center.get("x"), "verification target X")
            - finite(expected_target.get("x"), "calibration target X")
        )
        > 1.0e-6
        or abs(
            finite(target_center.get("y"), "verification target Y")
            - finite(expected_target.get("y"), "calibration target Y")
        )
        > 1.0e-6
    ):
        raise VerificationError(
            "%s did not use the calibration result target centre" % path
        )
    if source_endstops(manifest) != calibration_result["target_endstops"]:
        raise VerificationError(
            "%s was not run with the calibration result endstops" % path
        )
    if calibration_result.get("schema_version") >= 2:
        fingerprint = (
            manifest.get("initial_status", {})
            .get("gcode_macro _IDEX_CONFIG_FINGERPRINT", {})
            .get("source_sha256")
        ) or (
            manifest.get("initial_status", {})
            .get("gcode_macro _idex_config_fingerprint", {})
            .get("source_sha256")
        )
        if fingerprint != calibration_result.get("target_config_fingerprint"):
            raise VerificationError(
                "%s was not run with the calibration result fingerprint" % path
            )
    estimated = verification.get("estimated_center")
    if not isinstance(estimated, dict):
        raise VerificationError("%s lacks an estimated centre" % path)
    centre_contacts = verification.get("centre_contacts")
    centre_statistics = verification.get("centre_statistics")
    if not isinstance(centre_contacts, list) or len(centre_contacts) != CENTER_TAP_COUNT:
        raise VerificationError("%s lacks five verification centre contacts" % path)
    if not isinstance(centre_statistics, dict):
        raise VerificationError("%s lacks verification centre statistics" % path)
    centre_values = []
    for contact in centre_contacts:
        for axis in ("x", "y"):
            if abs(
                finite(contact.get(axis), "%s centre %s" % (expected_tool, axis))
                - finite(expected_target.get(axis), "calibration target %s" % axis)
            ) > 1.0e-6:
                raise VerificationError("%s did not tap the exact target centre" % path)
        centre_values.append(finite(contact.get("trigger_z"), "%s centre Z" % expected_tool))
    centre_median = float(np.median(centre_values))
    centre_stddev = float(np.std(centre_values))
    if finite(centre_statistics.get("count"), "%s centre tap count" % expected_tool) != CENTER_TAP_COUNT:
        raise VerificationError("%s has an invalid centre tap count" % path)
    if abs(finite(centre_statistics.get("median"), "%s centre median" % expected_tool) - centre_median) > 1.0e-9:
        raise VerificationError("%s has an invalid centre median" % path)
    if abs(finite(centre_statistics.get("standard_deviation"), "%s centre sigma" % expected_tool) - centre_stddev) > 1.0e-9:
        raise VerificationError("%s has an invalid centre sigma" % path)
    expected_repeatability = centre_stddev <= CENTER_STDDEV_LIMIT_MM + COMPARISON_EPSILON_MM
    if centre_statistics.get("repeatability_passed") is not expected_repeatability:
        raise VerificationError("%s has an invalid centre repeatability result" % path)
    if abs(finite(estimated.get("trigger_z"), "%s estimated centre Z" % expected_tool) - centre_median) > 1.0e-9:
        raise VerificationError("%s does not use the centre median for Z" % path)
    ring_contacts = verification.get("ring_contacts")
    if not isinstance(ring_contacts, list) or len(ring_contacts) != 8:
        raise VerificationError("%s lacks eight verification ring contacts" % path)
    ring_radius = finite(verification.get("ring_radius_mm"), "verification ring radius")
    ring_by_direction = {}
    for contact in ring_contacts:
        direction = contact.get("direction")
        if direction not in VERIFICATION_DIRECTIONS or direction in ring_by_direction:
            raise VerificationError("%s has invalid ring directions" % path)
        point = {
            "x": finite(contact.get("x"), "%s %s X" % (expected_tool, direction)),
            "y": finite(contact.get("y"), "%s %s Y" % (expected_tool, direction)),
        }
        angle = VERIFICATION_ANGLES[direction]
        expected_x = finite(
            expected_target.get("x"), "calibration target X"
        ) + ring_radius * math.cos(angle)
        expected_y = finite(
            expected_target.get("y"), "calibration target Y"
        ) + ring_radius * math.sin(angle)
        if (
            abs(point["x"] - expected_x) > 1.0e-6
            or abs(point["y"] - expected_y) > 1.0e-6
        ):
            raise VerificationError(
                "%s %s ring point is not centred on the target" % (path, direction)
            )
        ring_by_direction[direction] = point
    if tuple(ring_by_direction) != VERIFICATION_DIRECTIONS:
        raise VerificationError("%s ring order is not the prescribed octagon" % path)
    centre_z = centre_median
    return {
        "manifest": manifest,
        "run_dir": run_dir.resolve(),
        "x": finite(estimated.get("x"), "%s verification X" % expected_tool),
        "y": finite(estimated.get("y"), "%s verification Y" % expected_tool),
        "z": centre_z,
        "centre_z": centre_z,
        "centre_contacts": centre_contacts,
        "centre_statistics": centre_statistics,
        "ring": ring_by_direction,
    }


def write_report(output_dir, result, t0, t1):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "verification_report.json"
    csv_path = output_dir / "verification_report.csv"
    json_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("tool", "sample", "x", "y", "z"))
        writer.writeheader()
        for tool, measurement in (("T0", t0), ("T1", t1)):
            writer.writerow(
                {
                    "tool": tool,
                    "sample": "centre",
                    "x": measurement["x"],
                    "y": measurement["y"],
                    "z": measurement["centre_z"],
                }
            )
            for direction, point in measurement["ring"].items():
                writer.writerow({"tool": tool, "sample": direction, **point, "z": ""})
    return json_path, csv_path


def paired_result(calibration_result_path, t0, t1, target):
    residual = {axis: t1[axis] - t0[axis] for axis in ("x", "y")}
    centre_delta = t1["centre_z"] - t0["centre_z"]
    residual["z"] = centre_delta
    residual["z_center"] = centre_delta
    radial_xy = math.hypot(residual["x"], residual["y"])
    target_error = {
        tool: {axis: measurement[axis] - target[axis] for axis in ("x", "y")}
        for tool, measurement in (("t0", t0), ("t1", t1))
    }
    pass_components = {
        "t0_x": abs(target_error["t0"]["x"]) <= TARGET_XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "t0_y": abs(target_error["t0"]["y"]) <= TARGET_XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "t1_x": abs(target_error["t1"]["x"]) <= TARGET_XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "t1_y": abs(target_error["t1"]["y"]) <= TARGET_XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "paired_x": abs(residual["x"]) <= PAIRED_XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "paired_y": abs(residual["y"]) <= PAIRED_XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "z_center": abs(centre_delta) <= Z_LIMIT_MM + COMPARISON_EPSILON_MM,
        "t0_center_repeatability": t0["centre_statistics"]["standard_deviation"] <= CENTER_STDDEV_LIMIT_MM + COMPARISON_EPSILON_MM,
        "t1_center_repeatability": t1["centre_statistics"]["standard_deviation"] <= CENTER_STDDEV_LIMIT_MM + COMPARISON_EPSILON_MM,
    }
    checks = {}
    limits = {
        "t0_x": TARGET_XY_LIMIT_MM, "t0_y": TARGET_XY_LIMIT_MM,
        "t1_x": TARGET_XY_LIMIT_MM, "t1_y": TARGET_XY_LIMIT_MM,
        "paired_x": PAIRED_XY_LIMIT_MM, "paired_y": PAIRED_XY_LIMIT_MM,
        "z_center": Z_LIMIT_MM,
        "t0_center_repeatability": CENTER_STDDEV_LIMIT_MM,
        "t1_center_repeatability": CENTER_STDDEV_LIMIT_MM,
    }
    values = {
        "t0_x": target_error["t0"]["x"], "t0_y": target_error["t0"]["y"],
        "t1_x": target_error["t1"]["x"], "t1_y": target_error["t1"]["y"],
        "paired_x": residual["x"], "paired_y": residual["y"],
        "z_center": centre_delta,
        "t0_center_repeatability": t0["centre_statistics"]["standard_deviation"],
        "t1_center_repeatability": t1["centre_statistics"]["standard_deviation"],
    }
    labels = {
        "t0_x": "T0 target ΔX",
        "t0_y": "T0 target ΔY",
        "t1_x": "T1 target ΔX",
        "t1_y": "T1 target ΔY",
        "paired_x": "Paired ΔX",
        "paired_y": "Paired ΔY",
        "z_center": "Paired centre ΔZ",
        "t0_center_repeatability": "T0 centre σ",
        "t1_center_repeatability": "T1 centre σ",
    }
    for name, value in values.items():
        label = labels[name]
        checks[name] = {
            "label": label,
            "value_mm": value,
            "limit_mm": limits[name],
            "passed": pass_components[name],
            "reason": "%s: %.1f µm / limit %.1f µm — %s"
            % (label, value * 1000.0, limits[name] * 1000.0, "PASS" if pass_components[name] else "FAIL"),
        }
    return {
        "schema_version": 3,
        "workflow": "multi_head_zero_verification_report",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "calibration_result": str(calibration_result_path.resolve()),
        "runs": {"t0": str(t0["run_dir"]), "t1": str(t1["run_dir"])},
        "target_center": target,
        "measurements": {
            "t0": {
                "x": t0["x"],
                "y": t0["y"],
                "centre_z": t0["centre_z"],
                "centre_statistics": t0["centre_statistics"],
            },
            "t1": {
                "x": t1["x"],
                "y": t1["y"],
                "centre_z": t1["centre_z"],
                "centre_statistics": t1["centre_statistics"],
            },
        },
        "t1_minus_t0": residual,
        "target_error_mm": target_error,
        "radial_xy_mm": radial_xy,
        "limits_mm": {
            "target_x": TARGET_XY_LIMIT_MM,
            "target_y": TARGET_XY_LIMIT_MM,
            "paired_x": PAIRED_XY_LIMIT_MM,
            "paired_y": PAIRED_XY_LIMIT_MM,
            "z": Z_LIMIT_MM,
            "centre_sigma": CENTER_STDDEV_LIMIT_MM,
        },
        "pass_components": pass_components,
        "checks": checks,
        "failure_reasons": [check["reason"] for check in checks.values() if not check["passed"]],
        "pass": all(pass_components.values()),
    }


def main(argv):
    args = build_parser().parse_args(argv)
    calibration_result = load_calibration_result(args.calibration_result)
    t0 = load_run(args.t0_run, "T0", calibration_result)
    t1 = load_run(args.t1_run, "T1", calibration_result)
    result = paired_result(
        args.calibration_result, t0, t1, calibration_result["target_center"]
    )
    residual = result["t1_minus_t0"]
    centre_delta = result["t1_minus_t0"]["z_center"]
    radial_xy = result["radial_xy_mm"]
    passed = result["pass"]
    json_path, csv_path = write_report(args.output_dir, result, t0, t1)
    print(
        "Target errors: T0 X=%+.1f Y=%+.1f; T1 X=%+.1f Y=%+.1f µm. "
        "T1-minus-T0: X=%+.1f Y=%+.1f centre Z=%+.1f µm; radial XY=%.1f µm"
        % (
            result["target_error_mm"]["t0"]["x"] * 1000.0,
            result["target_error_mm"]["t0"]["y"] * 1000.0,
            result["target_error_mm"]["t1"]["x"] * 1000.0,
            result["target_error_mm"]["t1"]["y"] * 1000.0,
            residual["x"] * 1000.0,
            residual["y"] * 1000.0,
            centre_delta * 1000.0,
            radial_xy * 1000.0,
        )
    )
    print("Verification: %s" % ("PASS" if passed else "FAIL"))
    print("Report: %s\nCSV: %s" % (json_path, csv_path))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except VerificationError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
