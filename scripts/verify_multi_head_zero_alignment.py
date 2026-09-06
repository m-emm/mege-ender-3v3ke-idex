#!/usr/bin/env python3
"""Report paired residuals from multi-head-zero nine-contact verification."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt


XY_LIMIT_MM = 0.05
Z_LIMIT_MM = 0.02
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
        description="Compare paired nine-contact multi-head-zero verification runs."
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
        result.get("schema_version") != 4
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
        or verification.get("algorithm") != "nine_contact_octagonal_verification_v2"
        or verification.get("contact_count") != 9
        or verification.get("termination_reason") != "nine_contact_complete"
    ):
        raise VerificationError("%s has no valid nine-contact result" % path)
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
    ring_contacts = verification.get("ring_contacts")
    if not isinstance(ring_contacts, list) or len(ring_contacts) != 8:
        raise VerificationError("%s lacks eight verification ring contacts" % path)
    centre_contact = verification.get("centre_contact")
    if not isinstance(centre_contact, dict):
        raise VerificationError("%s lacks the verification centre contact" % path)
    for axis in ("x", "y"):
        if (
            abs(
                finite(centre_contact.get(axis), "%s centre %s" % (expected_tool, axis))
                - finite(expected_target.get(axis), "calibration target %s" % axis)
            )
            > 1.0e-6
        ):
            raise VerificationError("%s did not tap the exact target centre" % path)
    ring_radius = finite(verification.get("ring_radius_mm"), "verification ring radius")
    ring_by_direction = {}
    for contact in ring_contacts:
        direction = contact.get("direction")
        if direction not in VERIFICATION_DIRECTIONS or direction in ring_by_direction:
            raise VerificationError("%s has invalid ring directions" % path)
        point = {
            "x": finite(contact.get("x"), "%s %s X" % (expected_tool, direction)),
            "y": finite(contact.get("y"), "%s %s Y" % (expected_tool, direction)),
            "z": finite(
                contact.get("trigger_z"), "%s %s Z" % (expected_tool, direction)
            ),
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
    centre_z = finite(
        estimated.get("trigger_z"), "%s verification centre Z" % expected_tool
    )
    periphery_mean_z = sum(point["z"] for point in ring_by_direction.values()) / 8.0
    return {
        "manifest": manifest,
        "run_dir": run_dir.resolve(),
        "x": finite(estimated.get("x"), "%s verification X" % expected_tool),
        "y": finite(estimated.get("y"), "%s verification Y" % expected_tool),
        "z": centre_z,
        "centre_z": centre_z,
        "periphery_mean_z": periphery_mean_z,
        "ring": ring_by_direction,
    }


def write_report(output_dir, result, t0, t1):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "verification_report.json"
    csv_path = output_dir / "verification_report.csv"
    plot_path = output_dir / "T0_T1_verification.png"
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
                writer.writerow({"tool": tool, "sample": direction, **point})
    figure, (xy_axis, z_axis) = plt.subplots(
        1, 2, figsize=(12, 5.5), constrained_layout=True
    )
    xy_axis.scatter(
        [t0["x"]], [t0["y"]], marker="o", s=110, color="tab:blue", label="T0"
    )
    xy_axis.scatter(
        [t1["x"]], [t1["y"]], marker="s", s=110, color="tab:orange", label="T1"
    )
    target = result["target_center"]
    xy_axis.scatter(
        [target["x"]],
        [target["y"]],
        marker="*",
        s=180,
        color="tab:green",
        edgecolors="black",
        linewidths=0.5,
        label="Target",
    )
    xy_axis.plot([t0["x"], t1["x"]], [t0["y"], t1["y"]], color="0.4", linewidth=1)
    xy_axis.set_aspect("equal", adjustable="box")
    xy_axis.set_xlabel("Estimated ball-centre X (mm)")
    xy_axis.set_ylabel("Estimated ball-centre Y (mm)")
    xy_axis.set_title("Eight-ring harmonic XY")
    xy_axis.legend()
    xy_axis.grid(True, alpha=0.3)
    residual = result["t1_minus_t0"]
    micrometres = 1000.0
    xy_axis.text(
        0.03,
        0.03,
        "T0 error: X=%+.1f Y=%+.1f µm\nT1 error: X=%+.1f Y=%+.1f µm\nPaired: X=%+.1f Y=%+.1f µm"
        % (
            result["target_error_mm"]["t0"]["x"] * micrometres,
            result["target_error_mm"]["t0"]["y"] * micrometres,
            result["target_error_mm"]["t1"]["x"] * micrometres,
            result["target_error_mm"]["t1"]["y"] * micrometres,
            residual["x"] * micrometres,
            residual["y"] * micrometres,
        ),
        transform=xy_axis.transAxes,
        va="bottom",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
    )
    directions = list(VERIFICATION_DIRECTIONS)
    ring_deltas = [
        value * micrometres for value in result["z_diagnostics"]["periphery_deltas_mm"]
    ]
    z_axis.axhspan(
        -Z_LIMIT_MM * micrometres,
        Z_LIMIT_MM * micrometres,
        color="tab:green",
        alpha=0.12,
    )
    z_axis.axhline(0.0, color="black", linewidth=0.8)
    z_axis.plot(directions, ring_deltas, marker="o", label="Paired ring ΔZ")
    z_axis.axhline(
        result["z_diagnostics"]["centre_delta_mm"] * micrometres,
        color="tab:orange",
        linestyle="--",
        label="Centre ΔZ",
    )
    z_axis.axhline(
        result["z_diagnostics"]["periphery_mean_delta_mm"] * micrometres,
        color="tab:blue",
        linestyle=":",
        label="Periphery mean ΔZ (diagnostic)",
    )
    z_axis.tick_params(axis="x", rotation=35)
    z_axis.set_ylabel("T1 − T0 logical Z (µm)")
    z_axis.set_title("Centre Z result and raw periphery diagnostic")
    z_axis.grid(True, alpha=0.3)
    z_axis.legend(fontsize=8)
    figure.suptitle(
        "T0/T1 nine-contact verification: %s" % ("PASS" if result["pass"] else "FAIL")
    )
    figure.savefig(plot_path, dpi=200)
    plt.close(figure)
    return json_path, csv_path, plot_path


def paired_result(calibration_result_path, t0, t1, target):
    residual = {axis: t1[axis] - t0[axis] for axis in ("x", "y")}
    centre_delta = t1["centre_z"] - t0["centre_z"]
    ring_deltas = [
        t1["ring"][direction]["z"] - t0["ring"][direction]["z"]
        for direction in VERIFICATION_DIRECTIONS
    ]
    periphery_mean_delta = sum(ring_deltas) / len(ring_deltas)
    ring_standard_deviation = float(np.std(ring_deltas))
    residual["z"] = centre_delta
    residual["z_center"] = centre_delta
    residual["z_periphery_mean"] = periphery_mean_delta
    radial_xy = math.hypot(residual["x"], residual["y"])
    target_error = {
        tool: {axis: measurement[axis] - target[axis] for axis in ("x", "y")}
        for tool, measurement in (("t0", t0), ("t1", t1))
    }
    pass_components = {
        "t0_x": abs(target_error["t0"]["x"]) <= XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "t0_y": abs(target_error["t0"]["y"]) <= XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "t1_x": abs(target_error["t1"]["x"]) <= XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "t1_y": abs(target_error["t1"]["y"]) <= XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "paired_x": abs(residual["x"]) <= XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "paired_y": abs(residual["y"]) <= XY_LIMIT_MM + COMPARISON_EPSILON_MM,
        "z_center": abs(centre_delta) <= Z_LIMIT_MM + COMPARISON_EPSILON_MM,
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
                "periphery_mean_z": t0["periphery_mean_z"],
            },
            "t1": {
                "x": t1["x"],
                "y": t1["y"],
                "centre_z": t1["centre_z"],
                "periphery_mean_z": t1["periphery_mean_z"],
            },
        },
        "t1_minus_t0": residual,
        "target_error_mm": target_error,
        "z_diagnostics": {
            "centre_delta_mm": centre_delta,
            "ring_directions": list(VERIFICATION_DIRECTIONS),
            "periphery_deltas_mm": ring_deltas,
            "periphery_mean_delta_mm": periphery_mean_delta,
            "periphery_delta_standard_deviation_mm": ring_standard_deviation,
            "centre_minus_periphery_mean_mm": centre_delta - periphery_mean_delta,
            "authoritative_for_z": False,
        },
        "radial_xy_mm": radial_xy,
        "limits_mm": {"x": XY_LIMIT_MM, "y": XY_LIMIT_MM, "z": Z_LIMIT_MM},
        "pass_components": pass_components,
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
    centre_delta = result["z_diagnostics"]["centre_delta_mm"]
    periphery_mean_delta = result["z_diagnostics"]["periphery_mean_delta_mm"]
    radial_xy = result["radial_xy_mm"]
    passed = result["pass"]
    json_path, csv_path, plot_path = write_report(args.output_dir, result, t0, t1)
    print(
        "Target errors: T0 X=%+.1f Y=%+.1f; T1 X=%+.1f Y=%+.1f µm. "
        "T1-minus-T0: X=%+.1f Y=%+.1f centre Z=%+.1f periphery-mean Z=%+.1f µm; radial XY=%.1f µm"
        % (
            result["target_error_mm"]["t0"]["x"] * 1000.0,
            result["target_error_mm"]["t0"]["y"] * 1000.0,
            result["target_error_mm"]["t1"]["x"] * 1000.0,
            result["target_error_mm"]["t1"]["y"] * 1000.0,
            residual["x"] * 1000.0,
            residual["y"] * 1000.0,
            centre_delta * 1000.0,
            periphery_mean_delta * 1000.0,
            radial_xy * 1000.0,
        )
    )
    print("Verification: %s" % ("PASS" if passed else "FAIL"))
    print("Report: %s\nCSV: %s\nPlot: %s" % (json_path, csv_path, plot_path))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except VerificationError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
