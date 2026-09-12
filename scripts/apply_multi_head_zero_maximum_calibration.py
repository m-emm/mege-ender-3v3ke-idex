#!/usr/bin/env python3
"""Rebase IDEX X/Y to the multi-head-zero target and align T1 Z."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
KLIPPER_CONFIG_DIR = REPO_ROOT / "klipper_setup/klipper_config"
sys.path.insert(0, str(KLIPPER_CONFIG_DIR))

from calibration_data import (  # noqa: E402
    CalibrationDataError,
    atomic_update,
    endstops as measured_endstops,
    load_measured,
    sha256_file,
)


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
    if manifest.get("schema_version") != 6 or manifest.get("workflow") != "calibration":
        raise CalibrationError("%s is not a schema-v6 calibration run" % manifest_path)
    if manifest.get("status") != "completed":
        raise CalibrationError("%s is not completed" % manifest_path)
    calibration = manifest.get("calibration")
    if (
        not isinstance(calibration, dict)
        or calibration.get("algorithm") != "three_stage_sphere_ring_calibration_v3"
        or calibration.get("contact_count") != 47
        or calibration.get("termination_reason") != "phase_4_centre_complete"
    ):
        raise CalibrationError(
            "%s has no valid 47-contact three-round calibration result" % manifest_path
        )
    phase_1 = calibration.get("phase_1")
    phase_2 = calibration.get("phase_2")
    phase_3 = calibration.get("phase_3")
    phase_4 = calibration.get("phase_4")
    if (
        not isinstance(phase_1, dict)
        or not isinstance(phase_2, dict)
        or not isinstance(phase_3, dict)
        or not isinstance(phase_4, dict)
    ):
        raise CalibrationError("%s lacks calibration phases" % manifest_path)
    fit = phase_1.get("fit")
    summit = phase_1.get("summit")
    phase_2_refined = phase_2.get("refined_center")
    refined = phase_3.get("refined_center")
    centre_contacts = phase_4.get("contacts")
    centre_statistics = phase_4.get("statistics")
    if not isinstance(fit, dict) or fit.get("status") != "valid":
        raise CalibrationError("%s has no valid phase-1 fit" % manifest_path)
    if (
        not isinstance(summit, dict)
        or not isinstance(phase_2_refined, dict)
        or not isinstance(refined, dict)
        or not isinstance(centre_contacts, list)
        or len(centre_contacts) != 5
        or not isinstance(centre_statistics, dict)
        or phase_4.get("contact_count") != 5
        or centre_statistics.get("count") != 5
        or phase_4.get("repeatability_passed") is not True
    ):
        raise CalibrationError("%s lacks a passing five-tap final centre" % manifest_path)
    try:
        centre_values = [finite(contact.get("trigger_z"), "%s final-centre Z" % expected_tool) for contact in centre_contacts]
    except AttributeError as exc:
        raise CalibrationError("%s has an invalid final-centre contact" % manifest_path) from exc
    if abs(finite(centre_statistics.get("median"), "%s final-centre median" % expected_tool) - statistics.median(centre_values)) > 1.0e-9:
        raise CalibrationError("%s has an invalid final-centre median" % manifest_path)
    if abs(finite(centre_statistics.get("standard_deviation"), "%s final-centre sigma" % expected_tool) - statistics.pstdev(centre_values)) > 1.0e-9:
        raise CalibrationError("%s has an invalid final-centre sigma" % manifest_path)
    if phase_2.get("ring_contact_count") != 8:
        raise CalibrationError(
            "%s does not contain the completed first eight-contact ring" % manifest_path
        )
    phase_3_contacts = phase_3.get("ring_contacts")
    phase_3_fit_inputs = phase_3.get("fit_inputs")
    phase_3_statistics = phase_3.get("per_angle_statistics")
    if (
        phase_3.get("ring_contact_count") != 24
        or phase_3.get("ring_unique_contact_count") != 8
        or phase_3.get("ring_round_count") != 3
        or not isinstance(phase_3_contacts, list)
        or len(phase_3_contacts) != 24
        or not isinstance(phase_3_fit_inputs, dict)
        or len(phase_3_fit_inputs.get("angles_degrees", [])) != 24
        or len(phase_3_fit_inputs.get("trigger_z_mm", [])) != 24
        or not isinstance(phase_3_statistics, list)
        or len(phase_3_statistics) != 8
        or any(
            not isinstance(item, dict) or item.get("count") != 3
            for item in phase_3_statistics
        )
    ):
        raise CalibrationError(
            "%s does not contain three complete eight-contact refined-ring rounds"
            % manifest_path
        )
    try:
        phase_3_round_angle_counts = {
            (int(contact["round_index"]), float(contact["angle_degrees"]))
            for contact in phase_3_contacts
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise CalibrationError("%s has invalid refined-ring contact metadata" % manifest_path) from exc
    if len(phase_3_round_angle_counts) != 24:
        raise CalibrationError("%s has duplicate or incomplete refined-ring rounds" % manifest_path)
    expected_ring_order = [
        (round_index, float(angle_index * 45))
        for round_index in (1, 2, 3)
        for angle_index in range(8)
    ]
    observed_ring_order = [
        (int(contact["round_index"]), float(contact["angle_degrees"]))
        for contact in phase_3_contacts
    ]
    if observed_ring_order != expected_ring_order:
        raise CalibrationError(
            "%s does not retain three complete clockwise refined-ring rounds"
            % manifest_path
        )
    raw_angles = [float(value) for value in phase_3_fit_inputs["angles_degrees"]]
    raw_heights = [finite(value, "%s refined-ring Z" % expected_tool) for value in phase_3_fit_inputs["trigger_z_mm"]]
    if raw_angles != [angle for _, angle in expected_ring_order]:
        raise CalibrationError("%s has invalid refined-ring fit angles" % manifest_path)
    if raw_heights != [
        finite(contact.get("trigger_z"), "%s refined-ring contact Z" % expected_tool)
        for contact in phase_3_contacts
    ]:
        raise CalibrationError("%s refined-ring fit inputs do not match contacts" % manifest_path)
    for angle_index, aggregate in enumerate(phase_3_statistics):
        values = raw_heights[angle_index::8]
        expected_angle = float(angle_index * 45)
        if (
            finite(aggregate.get("angle_degrees"), "refined-ring angle") != expected_angle
            or abs(finite(aggregate.get("mean"), "refined-ring mean") - statistics.mean(values)) > 1.0e-9
            or abs(finite(aggregate.get("minimum"), "refined-ring minimum") - min(values)) > 1.0e-9
            or abs(finite(aggregate.get("maximum"), "refined-ring maximum") - max(values)) > 1.0e-9
            or abs(finite(aggregate.get("span"), "refined-ring span") - (max(values) - min(values))) > 1.0e-9
            or abs(finite(aggregate.get("standard_deviation"), "refined-ring sigma") - statistics.pstdev(values)) > 1.0e-9
        ):
            raise CalibrationError(
                "%s has invalid refined-ring angle aggregate at %.0f degrees"
                % (manifest_path, expected_angle)
            )
    return {
        "manifest": manifest,
        "run_dir": run_dir.resolve(),
        "x": finite(refined.get("x"), "%s refined X" % expected_tool),
        "y": finite(refined.get("y"), "%s refined Y" % expected_tool),
        "phase_2_x": finite(
            phase_2_refined.get("x"), "%s phase-2 refined X" % expected_tool
        ),
        "phase_2_y": finite(
            phase_2_refined.get("y"), "%s phase-2 refined Y" % expected_tool
        ),
        "z": finite(
            phase_4["statistics"].get("median"), "%s final-centre median Z" % expected_tool
        ),
        "centre_statistics": centre_statistics,
        "calibration_procedure": {
            "algorithm": calibration.get("algorithm"),
            "contact_count": calibration.get("contact_count"),
            "refined_ring_unique_contact_count": phase_3.get("ring_unique_contact_count"),
            "refined_ring_round_count": phase_3.get("ring_round_count"),
            "refined_ring_contact_count": phase_3.get("ring_contact_count"),
        },
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
    if t0_run["calibration_procedure"] != t1_run["calibration_procedure"]:
        raise CalibrationError("T0 and T1 runs used different calibration procedures")
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
    try:
        return measured_endstops(calibration)
    except CalibrationDataError as exc:
        raise CalibrationError(str(exc)) from exc


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


def rewrite_endstops(calib_path, suggested, expected_sha256):
    updates = {
        f"{tool}_{axis}_endstop": suggested[tool][f"{axis}_endstop"]
        for tool in ("t0", "t1")
        for axis in ("x", "y", "z")
    }
    try:
        atomic_update(calib_path, updates, expected_sha256=expected_sha256)
    except CalibrationDataError as exc:
        raise CalibrationError(str(exc)) from exc


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
        "schema_version": 5,
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
        "centre_statistics": {
            "t0": t0_run["centre_statistics"],
            "t1": t1_run["centre_statistics"],
        },
        "calibration_procedure": t0_run["calibration_procedure"],
        "phase_2_centers": {
            "t0": {axis: t0_run["phase_2_%s" % axis] for axis in ("x", "y")},
            "t1": {axis: t1_run["phase_2_%s" % axis] for axis in ("x", "y")},
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
    try:
        calibration = load_measured(args.calib)
    except CalibrationDataError as exc:
        raise CalibrationError(str(exc)) from exc
    calibration_sha256 = sha256_file(args.calib)
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
        rewrite_endstops(args.calib, suggested, calibration_sha256)
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
