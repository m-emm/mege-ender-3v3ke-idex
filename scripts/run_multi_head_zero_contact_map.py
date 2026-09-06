#!/usr/bin/env python3
"""Run guarded multi-head-zero calibration or verification contacts."""

from __future__ import annotations

import argparse
import copy
import csv
import datetime as dt
import json
import math
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt


DEFAULT_MOONRAKER_URL = "http://127.0.0.1:7125"
DEFAULT_OUTPUT_DIR = "~/printer_data/config/multi_head_zero_probe/runs"
DEFAULT_DASHBOARD_ROOT = "~/printer_data/vision/multi_head_zero_calibration"
FIT_CONDITION_LIMIT = 1.0e6
FIT_CONCAVITY_EPSILON = 1.0e-6
SEED_CONTACT_COUNT = 9
CALIBRATION_CONTACT_COUNT = 26
VERIFICATION_CONTACT_COUNT = 9
FRAME_TOLERANCE_MM = 1.0e-6


class ContactMapError(RuntimeError):
    def __init__(self, message, record=None):
        super().__init__(message)
        self.record = record


def request_json(url_base, path, *, method="GET", data=None, timeout=30.0):
    body = None
    headers = {}
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(
        url_base.rstrip("/") + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise ContactMapError(
            "%s %s failed HTTP %d: %s" % (method, path, exc.code, detail)
        ) from exc
    except urllib.error.URLError as exc:
        raise ContactMapError("%s %s failed: %s" % (method, path, exc)) from exc


def run_gcode(moonraker_url, script):
    request_json(
        moonraker_url,
        "/printer/gcode/script",
        method="POST",
        data={"script": script},
        timeout=300.0,
    )


def status(moonraker_url):
    payload = request_json(
        moonraker_url,
        "/printer/objects/query?webhooks&toolhead&print_stats&configfile&"
        "multi_head_zero_probe&dual_carriage&idex_manual_tuning&"
        "gcode_move&bed_mesh&gcode_macro%20_IDEX_TOOL_STATE&"
        "gcode_macro%20_IDEX_CONFIG_FINGERPRINT",
    )
    return payload["result"]["status"]


def gcode_origin(current_status):
    """Return the active tool's machine-minus-logical coordinate offset."""
    origin = current_status.get("gcode_move", {}).get("homing_origin", (0, 0, 0))
    if not isinstance(origin, (list, tuple)) or len(origin) < 3:
        raise ContactMapError("Klipper did not publish a valid G-code origin")
    try:
        return tuple(float(origin[index]) for index in range(3))
    except (TypeError, ValueError) as exc:
        raise ContactMapError("Klipper published a non-numeric G-code origin") from exc


def runtime_mesh_state(current_status):
    mesh = current_status.get("bed_mesh", {})
    profile_name = str(mesh.get("profile_name") or "")
    matrix = mesh.get("mesh_matrix") or []
    matrix_active = any(bool(row) for row in matrix)
    return {
        "active": bool(profile_name or matrix_active),
        "profile_name": profile_name,
        "matrix_active": matrix_active,
    }


def require_runtime_mesh_inactive(current_status):
    mesh = runtime_mesh_state(current_status)
    if mesh["active"]:
        raise ContactMapError(
            "multi-head-zero requires an inactive runtime mesh; profile=%r matrix=%s"
            % (mesh["profile_name"], mesh["matrix_active"])
        )
    return mesh


def runtime_macro(current_status, name):
    return current_status.get(name) or current_status.get(name.lower()) or {}


def runtime_frame_provenance(current_status, tool_index):
    mesh = require_runtime_mesh_inactive(current_status)
    origin = gcode_origin(current_status)
    tool_state = runtime_macro(current_status, "gcode_macro _IDEX_TOOL_STATE")
    manual = current_status.get("idex_manual_tuning", {})
    manual_adjust = float(manual.get("manual_z_adjust", 0.0))
    if abs(manual_adjust) > FRAME_TOLERANCE_MM:
        raise ContactMapError(
            "multi-head-zero requires zero manual Z adjustment; observed %.6f mm"
            % manual_adjust
        )
    expected_origin = (
        0.0,
        (
            float(tool_state.get("t0_y_offset", 0.0))
            if tool_index == 0
            else float(tool_state["t1_y_offset"])
        ),
        0.0 if tool_index == 0 else float(tool_state["t1_z_offset"]),
    )
    errors = tuple(
        observed - expected for observed, expected in zip(origin, expected_origin)
    )
    if any(abs(value) > FRAME_TOLERANCE_MM for value in errors):
        raise ContactMapError(
            "T%d G-code origin mismatch: observed=%s expected=%s error=%s"
            % (tool_index, origin, expected_origin, errors)
        )
    fingerprint = runtime_macro(
        current_status, "gcode_macro _IDEX_CONFIG_FINGERPRINT"
    ).get("source_sha256")
    if not fingerprint:
        raise ContactMapError("active configuration fingerprint is unavailable")
    return {
        "tool": tool_index,
        "gcode_origin": list(origin),
        "expected_gcode_origin": list(expected_origin),
        "origin_error_mm": list(errors),
        "manual_z_adjust_mm": manual_adjust,
        "active_tool_z_offset_mm": float(manual.get("active_tool_z_offset", 0.0)),
        "mesh": mesh,
        "config_fingerprint": str(fingerprint),
    }


def logical_to_machine_target(current_status, x, y):
    """Map the prescribed logical XY point to the active tool's machine frame."""
    origin_x, origin_y, _ = gcode_origin(current_status)
    return float(x) + origin_x, float(y) + origin_y


def apply_configured_priors(args, current_status):
    probe = (
        current_status.get("configfile", {})
        .get("settings", {})
        .get("multi_head_zero_probe", {})
    )
    required = (
        "ball_radius_mm",
        "ball_front_gap_mm",
        "y_zero_behind_front_edge_mm",
        "target_x",
        "target_y",
        "seed_x_min",
        "seed_x_max",
        "seed_y_min",
        "seed_y_max",
        "ring_radius_mm",
    )
    missing = [key for key in required if key not in probe]
    if missing:
        raise ContactMapError(
            "active [multi_head_zero_probe] is missing generated priors: %s"
            % ", ".join(missing)
        )
    priors = {key: float(probe[key]) for key in required}
    for argument_name, prior_name in (
        ("x_min", "seed_x_min"),
        ("x_max", "seed_x_max"),
        ("y_min", "seed_y_min"),
        ("y_max", "seed_y_max"),
    ):
        if getattr(args, argument_name) is None:
            setattr(args, argument_name, priors[prior_name])
    args.ball_radius_mm = priors["ball_radius_mm"]
    args.ring_radius_mm = priors["ring_radius_mm"]
    if not 0 < args.ring_radius_mm < args.ball_radius_mm:
        raise ContactMapError("configured ring radius must lie inside the ball radius")
    return priors


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run the prescribed multi-head-zero batch."
    )
    parser.add_argument(
        "--tool",
        choices=("T0", "T1", "both"),
        default="both",
        help="Default: calibrated T0 then T1. T0 or T1 collects that tool only.",
    )
    return parser


def default_run_name(workflow):
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ_T0_%s" % workflow)


def write_artifacts(output_dir, manifest, records):
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    csv_path = output_dir / "records.csv"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    fieldnames = sorted({key for record in records for key in record})
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    key: json.dumps(value) if isinstance(value, (dict, list)) else value
                    for key, value in record.items()
                }
            )
    return manifest_path, csv_path


def printer_log(moonraker_url, message):
    """Publish concise workflow state into the Mainsail/Klipper console."""
    clean = " ".join(str(message).split()).replace('"', "'")
    run_gcode(moonraker_url, 'RESPOND TYPE=echo MSG="MHZ calibration: %s"' % clean)


def workflow_log(moonraker_url, message):
    log(message)
    printer_log(moonraker_url, message)


def atomic_write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.%d.tmp" % (path.name, os.getpid()))
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def dashboard_record(record):
    fields = (
        "sample_index",
        "phase",
        "status",
        "commanded_x",
        "commanded_y",
        "trigger_x",
        "trigger_y",
        "trigger_z",
        "machine_commanded_x",
        "machine_commanded_y",
        "machine_trigger_x",
        "machine_trigger_y",
        "machine_trigger_z",
        "gcode_origin",
        "frame_provenance",
        "tool_selection",
        "no_contact_reason",
        "direction",
    )
    return {key: record[key] for key in fields if key in record}


class DashboardPublisher:
    """Maintain a small atomically-written live snapshot for /calibration/."""

    def __init__(self, run_id, workflow, tool_selection):
        self.root = Path(DEFAULT_DASHBOARD_ROOT).expanduser()
        self.path = self.root / "data" / "current.json"
        previous = {}
        if self.path.is_file():
            try:
                previous = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                previous = {}
        chapters = copy.deepcopy(previous.get("chapters") or {})
        if not chapters:
            previous_completed = previous.get("last_completed") or {}
            previous_workflow = previous_completed.get("workflow")
            if previous_workflow in {"calibration", "verification"}:
                chapters[previous_workflow] = {
                    "run_id": previous_completed.get("run_id"),
                    "status": "completed",
                    "finished_at": previous_completed.get("finished_at"),
                    "runs": previous_completed.get("runs", {}),
                }
            if previous.get("calibration_result"):
                chapters.setdefault("calibration", {"runs": {}})["result"] = previous[
                    "calibration_result"
                ]
            if previous.get("verification"):
                chapters.setdefault("verification", {"runs": {}})["report"] = previous[
                    "verification"
                ]
        if workflow == "calibration":
            chapters = {}
        chapters[workflow] = {
            "run_id": run_id,
            "status": "preparing",
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "runs": {},
        }
        self.payload = {
            "schema_version": 2,
            "kind": "multi_head_zero_calibration_dashboard",
            "run_id": run_id,
            "workflow": workflow,
            "tool_selection": tool_selection,
            "status": "preparing",
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "updated_at": None,
            "events": [],
            "chapters": chapters,
        }
        self.publish()

    def publish(self):
        self.payload["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        atomic_write_json(self.path, self.payload)

    def event(self, message):
        self.payload["events"] = (
            self.payload.get("events", [])
            + [{"at": dt.datetime.now(dt.timezone.utc).isoformat(), "message": message}]
        )[-16:]
        self.publish()

    def update_run(
        self, tool, workflow, records, total, state, summary=None, plot=None
    ):
        payload = {
            "workflow": workflow,
            "state": state,
            "progress": {"completed": len(records), "total": total},
            "records": [dashboard_record(record) for record in records],
        }
        if summary is not None:
            payload["summary"] = summary
        if plot is not None:
            payload["plot"] = plot
        self.payload["chapters"][workflow]["runs"][tool.lower()] = payload
        self.publish()

    def publish_plot(self, source, tool, workflow):
        artifacts = self.root / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=True)
        filename = "%s_%s_%s.png" % (self.payload["run_id"], tool, workflow)
        target = artifacts / filename
        temporary = target.with_name(".%s.%d.tmp" % (target.name, os.getpid()))
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
        return "artifacts/%s" % filename

    def finish(self, status, error=None):
        self.payload["status"] = status
        self.payload["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        chapter = self.payload["chapters"][self.payload["workflow"]]
        chapter["status"] = status
        chapter["finished_at"] = self.payload["finished_at"]
        if error:
            self.payload["error"] = error
            chapter["error"] = error
        self.payload["last_completed"] = {
            "run_id": self.payload["run_id"],
            "workflow": self.payload["workflow"],
            "finished_at": self.payload["finished_at"],
            "chapters": self.payload["chapters"],
        }
        self.publish()


def perform_contact(
    moonraker_url,
    *,
    tool,
    tool_index,
    x,
    y,
    sample_index,
    phase,
):
    tool_selection = verify_selected_tool(moonraker_url, tool, tool_index)
    frame_status = status(moonraker_url)
    frame_provenance = runtime_frame_provenance(frame_status, tool_index)
    machine_x, machine_y = logical_to_machine_target(frame_status, x, y)
    command = "MULTI_HEAD_ZERO_CONTACT X=%.3f Y=%.3f TOOL=%d" % (
        x,
        y,
        tool_index,
    )
    if phase == "phase_1_seed":
        command += " ALLOW_NO_CONTACT=1"
    record = {
        "sample_index": sample_index,
        "commanded_x": x,
        "commanded_y": y,
        "machine_commanded_x": machine_x,
        "machine_commanded_y": machine_y,
        "tool": tool,
        "command": command,
        "phase": phase,
        "tool_selection": tool_selection,
        "frame_provenance": frame_provenance,
    }
    try:
        run_gcode(moonraker_url, command + "\nM400")
    except ContactMapError as exc:
        record["status"] = "failed"
        record["runner_error"] = str(exc)
        measurement = (
            status(moonraker_url)
            .get("multi_head_zero_probe", {})
            .get("last_measurement")
        )
        if measurement:
            record.update(measurement)
        raise ContactMapError(record["runner_error"], record=record)
    measurement_status = status(moonraker_url)
    post_provenance = runtime_frame_provenance(measurement_status, tool_index)
    if post_provenance != frame_provenance:
        raise ContactMapError(
            "coordinate-frame provenance changed during contact",
            record=record,
        )
    measurement = measurement_status.get("multi_head_zero_probe", {}).get(
        "last_measurement"
    )
    if not measurement or measurement.get("status") not in {"completed", "no_contact"}:
        record["status"] = "failed"
        record["runner_error"] = (
            "Klipper did not publish a completed or no-contact measurement"
        )
        if measurement:
            record.update(measurement)
        raise ContactMapError(record["runner_error"], record=record)
    record.update(measurement)
    measurement_origin = gcode_origin(
        {"gcode_move": {"homing_origin": record.get("gcode_origin", (0, 0, 0))}}
    )
    if any(
        abs(left - right) > FRAME_TOLERANCE_MM
        for left, right in zip(measurement_origin, frame_provenance["gcode_origin"])
    ):
        raise ContactMapError(
            "contact measurement origin differs from its preflight origin",
            record=record,
        )
    record["machine_commanded_x"] = float(record.get("machine_commanded_x", machine_x))
    record["machine_commanded_y"] = float(record.get("machine_commanded_y", machine_y))
    record["commanded_x"] = float(x)
    record["commanded_y"] = float(y)
    if record.get("status") == "completed":
        for axis, origin in zip(("x", "y", "z"), measurement_origin):
            machine_value = float(record["trigger_%s" % axis])
            record["machine_trigger_%s" % axis] = machine_value
            record["trigger_%s" % axis] = machine_value - origin
    return record


def verify_selected_tool(moonraker_url, tool, tool_index):
    current = status(moonraker_url)
    manual = current.get("idex_manual_tuning", {})
    macro = current.get("gcode_macro _IDEX_TOOL_STATE", {})
    toolhead = current.get("toolhead", {})
    carriage = current.get("dual_carriage", {})
    expected_extruder = "extruder" if tool_index == 0 else "extruder1"
    expected_carriages = (
        ("PRIMARY", "INACTIVE") if tool_index == 0 else ("INACTIVE", "PRIMARY")
    )
    observed = {
        "manual_active_tool": manual.get("active_tool"),
        "macro_active_tool": macro.get("active_tool"),
        "toolhead_extruder": toolhead.get("extruder"),
        "carriage_0": carriage.get("carriage_0"),
        "carriage_1": carriage.get("carriage_1"),
    }
    if (
        observed["manual_active_tool"] != tool_index
        or observed["macro_active_tool"] != tool_index
        or observed["toolhead_extruder"] != expected_extruder
        or (observed["carriage_0"], observed["carriage_1"]) != expected_carriages
    ):
        raise ContactMapError(
            "%s physical tool selection mismatch: %s" % (tool, observed)
        )
    return observed


def completed_records(records):
    return [record for record in records if record.get("status") == "completed"]


def is_within_bounds(x, y, bounds):
    return (
        bounds["x_min"] <= x <= bounds["x_max"]
        and bounds["y_min"] <= y <= bounds["y_max"]
    )


def is_strictly_within_bounds(x, y, bounds, margin=0.001):
    return (
        bounds["x_min"] + margin < x < bounds["x_max"] - margin
        and bounds["y_min"] + margin < y < bounds["y_max"] - margin
    )


def contact_payload(record):
    payload = {
        "sample_index": record["sample_index"],
        "x": float(record["commanded_x"]),
        "y": float(record["commanded_y"]),
        "trigger_z": float(record["trigger_z"]),
    }
    for key in (
        "machine_commanded_x",
        "machine_commanded_y",
        "machine_trigger_x",
        "machine_trigger_y",
        "machine_trigger_z",
        "gcode_origin",
        "frame_provenance",
        "tool_selection",
    ):
        if key in record:
            payload[key] = record[key]
    return payload


def fit_paraboloid(records, bounds):
    complete = completed_records(records)
    result = {
        "model": "normalized_quadratic_paraboloid",
        "status": "invalid",
        "sample_count": len(complete),
        "validation_errors": [],
    }
    if len(complete) < 6:
        result["validation_errors"].append("insufficient_contacts")
        return result
    x_values = np.asarray([float(record["commanded_x"]) for record in complete])
    y_values = np.asarray([float(record["commanded_y"]) for record in complete])
    z_values = np.asarray([float(record["trigger_z"]) for record in complete])
    origin = np.asarray([x_values.mean(), y_values.mean()])
    scale = np.asarray([np.ptp(x_values) / 2.0, np.ptp(y_values) / 2.0])
    if np.any(scale <= 1.0e-9):
        result["validation_errors"].append("degenerate_xy_span")
        return result
    u_values = (x_values - origin[0]) / scale[0]
    v_values = (y_values - origin[1]) / scale[1]
    design = np.column_stack(
        (
            np.ones(len(complete)),
            u_values,
            v_values,
            u_values**2,
            u_values * v_values,
            v_values**2,
        )
    )
    coefficients, _, rank, singular_values = np.linalg.lstsq(
        design, z_values, rcond=None
    )
    fitted_values = design @ coefficients
    condition_number = (
        float(singular_values[0] / singular_values[-1])
        if singular_values[-1] > 0.0
        else None
    )
    hessian = np.asarray(
        [
            [2.0 * coefficients[3], coefficients[4]],
            [coefficients[4], 2.0 * coefficients[5]],
        ]
    )
    eigenvalues = np.linalg.eigvalsh(hessian)
    machine_hessian = hessian / np.outer(scale, scale)
    result.update(
        {
            "origin": {"x": float(origin[0]), "y": float(origin[1])},
            "scale": {"x": float(scale[0]), "y": float(scale[1])},
            "coefficients": {
                "constant": float(coefficients[0]),
                "x": float(coefficients[1]),
                "y": float(coefficients[2]),
                "xx": float(coefficients[3]),
                "xy": float(coefficients[4]),
                "yy": float(coefficients[5]),
            },
            "rank": int(rank),
            "condition_number": condition_number,
            "rmse_mm": float(np.sqrt(np.mean((fitted_values - z_values) ** 2))),
            "machine_hessian_eigenvalues_per_mm": [
                float(value) for value in np.linalg.eigvalsh(machine_hessian)
            ],
        }
    )
    if rank != 6:
        result["validation_errors"].append("rank_deficient")
    if condition_number is None or condition_number > FIT_CONDITION_LIMIT:
        result["validation_errors"].append("ill_conditioned")
    if not np.all(eigenvalues < -FIT_CONCAVITY_EPSILON):
        result["validation_errors"].append("not_strictly_concave")
    try:
        normalized_vertex = -np.linalg.solve(hessian, coefficients[1:3])
    except np.linalg.LinAlgError:
        result["validation_errors"].append("singular_hessian")
        return result
    vertex = origin + scale * normalized_vertex
    vertex_design = np.asarray(
        [
            1.0,
            normalized_vertex[0],
            normalized_vertex[1],
            normalized_vertex[0] ** 2,
            normalized_vertex[0] * normalized_vertex[1],
            normalized_vertex[1] ** 2,
        ]
    )
    result["predicted_maximum"] = {
        "x": float(vertex[0]),
        "y": float(vertex[1]),
        "z": float(vertex_design @ coefficients),
    }
    if not is_within_bounds(vertex[0], vertex[1], bounds):
        result["validation_errors"].append("vertex_outside_search_bounds")
    elif not is_strictly_within_bounds(vertex[0], vertex[1], bounds):
        result["validation_errors"].append("vertex_on_search_boundary")
    if not result["validation_errors"]:
        result["status"] = "valid"
    return result


def evaluate_paraboloid(fit, x_values, y_values):
    coefficients = fit["coefficients"]
    origin = fit["origin"]
    scale = fit["scale"]
    u_values = (np.asarray(x_values) - origin["x"]) / scale["x"]
    v_values = (np.asarray(y_values) - origin["y"]) / scale["y"]
    return (
        coefficients["constant"]
        + coefficients["x"] * u_values
        + coefficients["y"] * v_values
        + coefficients["xx"] * u_values**2
        + coefficients["xy"] * u_values * v_values
        + coefficients["yy"] * v_values**2
    )


def ring_targets(x_center, y_center, ring_radius_mm):
    theta = np.arange(8, dtype=float) * (math.pi / 4.0)
    return theta, np.column_stack(
        (
            x_center + ring_radius_mm * np.cos(theta),
            y_center + ring_radius_mm * np.sin(theta),
        )
    )


def sphere_z(x_values, y_values, x_center, y_center, z_max, ball_radius_mm):
    radial_squared = (np.asarray(x_values) - x_center) ** 2 + (
        np.asarray(y_values) - y_center
    ) ** 2
    inside = ball_radius_mm**2 - radial_squared
    if np.any(inside < -1.0e-9):
        raise ContactMapError("sphere diagnostic point lies outside the ball radius")
    return z_max - ball_radius_mm + np.sqrt(np.maximum(inside, 0.0))


def fit_xy_from_ring(x_rough, y_rough, theta, z_values, ball_radius_mm, ring_radius_mm):
    theta = np.asarray(theta, dtype=float)
    z_values = np.asarray(z_values, dtype=float)
    if len(theta) != 8 or len(z_values) != 8:
        raise ContactMapError("ring refinement requires exactly eight contacts")
    a_cos = float(2.0 / len(theta) * np.sum(z_values * np.cos(theta)))
    b_sin = float(2.0 / len(theta) * np.sum(z_values * np.sin(theta)))
    scale = math.sqrt(ball_radius_mm**2 - ring_radius_mm**2) / ring_radius_mm
    return {
        "a_cos_mm": a_cos,
        "b_sin_mm": b_sin,
        "scale": scale,
        "dx_mm": a_cos * scale,
        "dy_mm": b_sin * scale,
        "x": x_rough + a_cos * scale,
        "y": y_rough + b_sin * scale,
    }


def require_contact(record, label):
    if record.get("status") != "completed":
        raise ContactMapError(
            "%s must trigger; got %s" % (label, record.get("status")), record=record
        )


def run_ring_refinement(
    args,
    tool_index,
    records,
    *,
    center,
    summit_z,
    phase,
    contact_function,
    progress_callback,
):
    theta, targets = ring_targets(center["x"], center["y"], args.ring_radius_mm)
    ring_records = []
    for angle, target in zip(theta, targets):
        record = contact_function(
            args.moonraker_url,
            tool=args.tool,
            tool_index=tool_index,
            x=float(target[0]),
            y=float(target[1]),
            sample_index=len(records) + 1,
            phase=phase,
        )
        record["angle_degrees"] = float(math.degrees(angle))
        records.append(record)
        if progress_callback is not None:
            progress_callback(record)
        require_contact(
            record, "%s contact %.0f degrees" % (phase, math.degrees(angle))
        )
        ring_records.append(record)
    refined = fit_xy_from_ring(
        center["x"],
        center["y"],
        theta,
        [record["trigger_z"] for record in ring_records],
        args.ball_radius_mm,
        args.ring_radius_mm,
    )
    expected_ring_z = sphere_z(
        [record["commanded_x"] for record in ring_records],
        [record["commanded_y"] for record in ring_records],
        refined["x"],
        refined["y"],
        summit_z,
        args.ball_radius_mm,
    )
    residuals = [
        float(record["trigger_z"] - expected)
        for record, expected in zip(ring_records, expected_ring_z)
    ]
    return {
        "ring_center": {"x": center["x"], "y": center["y"]},
        "ring_contact_count": len(ring_records),
        "ring_angles_degrees": [float(math.degrees(angle)) for angle in theta],
        "ring_contacts": [contact_payload(record) for record in ring_records],
        "harmonic": {
            "a_cos_mm": refined["a_cos_mm"],
            "b_sin_mm": refined["b_sin_mm"],
            "scale": refined["scale"],
            "dx_mm": refined["dx_mm"],
            "dy_mm": refined["dy_mm"],
        },
        "refined_center": {"x": refined["x"], "y": refined["y"]},
        "sphere_residuals_mm": residuals,
        "sphere_residual_rmse_mm": float(np.sqrt(np.mean(np.square(residuals)))),
        "sphere_residual_max_abs_mm": float(max(abs(value) for value in residuals)),
    }


def run_calibration(
    args, tool_index, records, contact_function=perform_contact, progress_callback=None
):
    bounds = {
        "x_min": args.x_min,
        "x_max": args.x_max,
        "y_min": args.y_min,
        "y_max": args.y_max,
    }
    for row_index, y in enumerate(np.linspace(args.y_min, args.y_max, 3)):
        x_values = np.linspace(args.x_min, args.x_max, 3)
        if row_index % 2:
            x_values = x_values[::-1]
        for x in x_values:
            record = contact_function(
                args.moonraker_url,
                tool=args.tool,
                tool_index=tool_index,
                x=float(x),
                y=float(y),
                sample_index=len(records) + 1,
                phase="phase_1_seed",
            )
            records.append(record)
            if progress_callback is not None:
                progress_callback(record)
    coarse_fit = fit_paraboloid(records, bounds)
    if coarse_fit["status"] != "valid":
        raise ContactMapError(
            "phase-1 seed fit invalid: %s" % ", ".join(coarse_fit["validation_errors"])
        )
    predicted = coarse_fit["predicted_maximum"]
    summit = contact_function(
        args.moonraker_url,
        tool=args.tool,
        tool_index=tool_index,
        x=predicted["x"],
        y=predicted["y"],
        sample_index=len(records) + 1,
        phase="phase_1_summit",
    )
    records.append(summit)
    if progress_callback is not None:
        progress_callback(summit)
    require_contact(summit, "phase-1 summit contact")
    phase_2 = run_ring_refinement(
        args,
        tool_index,
        records,
        center=predicted,
        summit_z=summit["trigger_z"],
        phase="phase_2_ring",
        contact_function=contact_function,
        progress_callback=progress_callback,
    )
    phase_3 = run_ring_refinement(
        args,
        tool_index,
        records,
        center=phase_2["refined_center"],
        summit_z=summit["trigger_z"],
        phase="phase_3_ring",
        contact_function=contact_function,
        progress_callback=progress_callback,
    )
    return {
        "algorithm": "three_stage_sphere_ring_calibration_v2",
        "contact_count": CALIBRATION_CONTACT_COUNT,
        "ball_radius_mm": args.ball_radius_mm,
        "ring_radius_mm": args.ring_radius_mm,
        "phase_1": {
            "seed_grid_size": 3,
            "bounds": bounds,
            "fit": coarse_fit,
            "summit": contact_payload(summit),
        },
        "phase_2": phase_2,
        "phase_3": phase_3,
        "termination_reason": "phase_3_complete",
    }


def run_verification(
    args, tool_index, records, contact_function=perform_contact, progress_callback=None
):
    if args.reference_x is None or args.reference_y is None:
        raise ContactMapError("verification requires --reference-x and --reference-y")
    centre = contact_function(
        args.moonraker_url,
        tool=args.tool,
        tool_index=tool_index,
        x=args.reference_x,
        y=args.reference_y,
        sample_index=1,
        phase="verification_centre",
    )
    records.append(centre)
    if progress_callback is not None:
        progress_callback(centre)
    require_contact(centre, "verification centre contact")
    octagonal = (
        ("east", 0.0),
        ("north_east", math.pi / 4.0),
        ("north", math.pi / 2.0),
        ("north_west", 3.0 * math.pi / 4.0),
        ("west", math.pi),
        ("south_west", 5.0 * math.pi / 4.0),
        ("south", 3.0 * math.pi / 2.0),
        ("south_east", 7.0 * math.pi / 4.0),
    )
    ring_records = []
    for direction, angle in octagonal:
        record = contact_function(
            args.moonraker_url,
            tool=args.tool,
            tool_index=tool_index,
            x=args.reference_x + args.ring_radius_mm * math.cos(angle),
            y=args.reference_y + args.ring_radius_mm * math.sin(angle),
            sample_index=len(records) + 1,
            phase="verification_%s" % direction,
        )
        record["direction"] = direction
        record["angle_degrees"] = float(math.degrees(angle))
        records.append(record)
        if progress_callback is not None:
            progress_callback(record)
        require_contact(record, "verification %s contact" % direction)
        ring_records.append(record)
    theta = np.asarray([angle for _direction, angle in octagonal], dtype=float)
    z_values = np.asarray([record["trigger_z"] for record in ring_records], dtype=float)
    refined = fit_xy_from_ring(
        args.reference_x,
        args.reference_y,
        theta,
        z_values,
        args.ball_radius_mm,
        args.ring_radius_mm,
    )
    return {
        "algorithm": "nine_contact_octagonal_verification_v2",
        "contact_count": VERIFICATION_CONTACT_COUNT,
        "ball_radius_mm": args.ball_radius_mm,
        "ring_radius_mm": args.ring_radius_mm,
        "target_center": {"x": args.reference_x, "y": args.reference_y},
        "centre_contact": contact_payload(centre),
        "ring_contacts": [
            contact_payload(record)
            | {
                "direction": record["direction"],
                "angle_degrees": record["angle_degrees"],
            }
            for record in ring_records
        ],
        "harmonic": {
            "a_cos_mm": refined["a_cos_mm"],
            "b_sin_mm": refined["b_sin_mm"],
            "scale": refined["scale"],
            "dx_mm": refined["dx_mm"],
            "dy_mm": refined["dy_mm"],
        },
        "periphery_mean_z": float(np.mean(z_values)),
        "periphery_z_standard_deviation": float(np.std(z_values)),
        "estimated_center": {
            "x": refined["x"],
            "y": refined["y"],
            "trigger_z": float(centre["trigger_z"]),
        },
        "termination_reason": "nine_contact_complete",
    }


def render_calibration(output_dir, tool, records, summary):
    figure, (xy_axis, residual_axis) = plt.subplots(
        1, 2, figsize=(13, 5), constrained_layout=True
    )
    phase_1 = summary["phase_1"]
    phase_2 = summary["phase_2"]
    phase_3 = summary["phase_3"]
    bounds = phase_1["bounds"]
    seed = [record for record in records if record["phase"] == "phase_1_seed"]
    complete_seed = completed_records(seed)
    no_contact = [record for record in seed if record.get("status") == "no_contact"]
    fit_x = np.linspace(bounds["x_min"], bounds["x_max"], 100)
    fit_y = np.linspace(bounds["y_min"], bounds["y_max"], 100)
    grid_x, grid_y = np.meshgrid(fit_x, fit_y)
    contours = xy_axis.contour(
        grid_x,
        grid_y,
        evaluate_paraboloid(phase_1["fit"], grid_x, grid_y),
        levels=10,
        colors="0.4",
        linewidths=0.7,
        alpha=0.7,
    )
    xy_axis.clabel(contours, inline=True, fontsize=7, fmt="%.3f")
    scatter = xy_axis.scatter(
        [record["commanded_x"] for record in complete_seed],
        [record["commanded_y"] for record in complete_seed],
        c=[record["trigger_z"] for record in complete_seed],
        cmap="viridis",
        s=85,
        label="Phase-1 seed contacts",
        zorder=3,
    )
    figure.colorbar(scatter, ax=xy_axis, label="Logical trigger Z (mm)")
    if no_contact:
        xy_axis.scatter(
            [record["commanded_x"] for record in no_contact],
            [record["commanded_y"] for record in no_contact],
            marker="x",
            color="crimson",
            s=85,
            linewidths=2,
            label="Seed no contact",
            zorder=4,
        )
    summit = phase_1["summit"]
    phase_2_refined = phase_2["refined_center"]
    refined = phase_3["refined_center"]
    ring = phase_2["ring_contacts"]
    final_ring = phase_3["ring_contacts"]
    xy_axis.scatter(
        [summit["x"]],
        [summit["y"]],
        marker="*",
        color="gold",
        edgecolors="black",
        s=220,
        label="Direct summit",
        zorder=5,
    )
    xy_axis.scatter(
        [item["x"] for item in ring],
        [item["y"] for item in ring],
        marker="o",
        facecolors="none",
        edgecolors="tab:red",
        s=90,
        label="Phase-2 ring",
        zorder=5,
    )
    xy_axis.scatter(
        [item["x"] for item in final_ring],
        [item["y"] for item in final_ring],
        marker="s",
        facecolors="none",
        edgecolors="tab:purple",
        s=82,
        label="Phase-3 ring",
        zorder=5,
    )
    xy_axis.scatter(
        [phase_2_refined["x"]],
        [phase_2_refined["y"]],
        marker="D",
        color="lightskyblue",
        edgecolors="black",
        s=70,
        label="Phase-2 centre",
        zorder=6,
    )
    xy_axis.scatter(
        [refined["x"]],
        [refined["y"]],
        marker="D",
        color="deepskyblue",
        edgecolors="black",
        s=85,
        label="Refined centre",
        zorder=6,
    )
    xy_axis.set(
        xlim=(bounds["x_min"], bounds["x_max"]),
        ylim=(bounds["y_min"], bounds["y_max"]),
        aspect="equal",
        xlabel="Commanded X (mm)",
        ylabel="Commanded Y (mm)",
        title="26-contact calibration (%s)" % tool,
    )
    xy_axis.grid(True, alpha=0.3)
    xy_axis.legend(fontsize=8, loc="upper right")
    angles = phase_2["ring_angles_degrees"]
    residuals = phase_2["sphere_residuals_mm"]
    final_residuals = phase_3["sphere_residuals_mm"]
    residual_axis.axhline(0.0, color="black", linewidth=0.8)
    residual_axis.plot(
        angles, residuals, marker="o", color="tab:red", label="Phase-2 ring"
    )
    residual_axis.plot(
        angles,
        final_residuals,
        marker="s",
        color="tab:purple",
        label="Phase-3 ring",
    )
    residual_axis.set(
        xticks=angles,
        xlabel="Ring angle (degrees)",
        ylabel="Measured − sphere Z (mm)",
        title="Fixed-sphere diagnostics (%s)" % tool,
    )
    residual_axis.grid(True, alpha=0.3)
    residual_axis.legend(fontsize=8)
    residual_axis.text(
        0.03,
        0.03,
        "Phase-2 XY: %.4f, %.4f\nFinal XY: %.4f, %.4f\nDirect summit Z: %.4f\nFinal RMSE: %.4f mm"
        % (
            phase_2_refined["x"],
            phase_2_refined["y"],
            refined["x"],
            refined["y"],
            summit["trigger_z"],
            phase_3["sphere_residual_rmse_mm"],
        ),
        transform=residual_axis.transAxes,
        va="bottom",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
    )
    path = output_dir / ("%s_calibration.png" % tool)
    figure.savefig(path, dpi=200)
    plt.close(figure)
    return path


def render_verification(output_dir, tool, records, summary):
    figure, axis = plt.subplots(figsize=(7, 6), constrained_layout=True)
    centre = summary["centre_contact"]
    ring = summary["ring_contacts"]
    estimated = summary["estimated_center"]
    axis.scatter(
        [centre["x"]],
        [centre["y"]],
        marker="*",
        color="gold",
        edgecolors="black",
        s=220,
        label="Centre contact",
        zorder=3,
    )
    axis.scatter(
        [item["x"] for item in ring],
        [item["y"] for item in ring],
        marker="o",
        color="tab:red",
        s=90,
        label="Eight-point ring contacts",
        zorder=3,
    )
    for item in ring:
        axis.annotate(
            item["direction"],
            (item["x"], item["y"]),
            xytext=(5, 5),
            textcoords="offset points",
        )
    axis.scatter(
        [estimated["x"]],
        [estimated["y"]],
        marker="D",
        color="deepskyblue",
        edgecolors="black",
        s=90,
        label="Estimated centre",
        zorder=4,
    )
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("Commanded X (mm)")
    axis.set_ylabel("Commanded Y (mm)")
    axis.set_title("Nine-contact verification (%s)" % tool)
    axis.grid(True, alpha=0.3)
    axis.legend()
    axis.text(
        0.03,
        0.03,
        "Estimated XY: %.4f, %.4f\nCentre direct Z: %.4f\nPeriphery mean Z: %.4f"
        % (
            estimated["x"],
            estimated["y"],
            estimated["trigger_z"],
            summary["periphery_mean_z"],
        ),
        transform=axis.transAxes,
        va="bottom",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
    )
    path = output_dir / ("%s_verification.png" % tool)
    figure.savefig(path, dpi=200)
    plt.close(figure)
    return path


def log(message):
    print("Multi-head-zero: %s" % message, flush=True)


def configured_runtime_args(priors, tool, moonraker_url):
    return SimpleNamespace(
        tool=tool,
        moonraker_url=moonraker_url,
        x_min=priors["seed_x_min"],
        x_max=priors["seed_x_max"],
        y_min=priors["seed_y_min"],
        y_max=priors["seed_y_max"],
        ball_radius_mm=priors["ball_radius_mm"],
        ring_radius_mm=priors["ring_radius_mm"],
        reference_x=priors["target_x"],
        reference_y=priors["target_y"],
    )


def require_ready_and_prepare(moonraker_url):
    initial_status = status(moonraker_url)
    if initial_status.get("webhooks", {}).get("state") != "ready":
        raise ContactMapError("Klipper is not ready")
    homed_axes = initial_status.get("toolhead", {}).get("homed_axes", "")
    homing_required = not all(axis in homed_axes for axis in "xyz")
    workflow_log(
        moonraker_url,
        "batch start; XYZ homed=%s; homing_required=%s"
        % (homed_axes or "none", homing_required),
    )
    if homing_required:
        run_gcode(moonraker_url, "G28\nM400")
    run_gcode(moonraker_url, "BED_MESH_CLEAR\nM400")
    prepared_status = status(moonraker_url)
    if prepared_status.get("toolhead", {}).get("homed_axes") != "xyz":
        raise ContactMapError("preparation did not establish XYZ homing")
    if prepared_status.get("multi_head_zero_probe", {}).get("state") == "TRIGGERED":
        raise ContactMapError("multi-head-zero is already triggered before the run")
    require_runtime_mesh_inactive(prepared_status)
    workflow_log(moonraker_url, "preparation complete; runtime mesh verified inactive")
    return initial_status, prepared_status, homing_required


def select_tool_once(moonraker_url, tool):
    tool_index = int(tool[-1])
    try:
        selection = verify_selected_tool(moonraker_url, tool, tool_index)
    except ContactMapError:
        workflow_log(moonraker_url, "lift Z=10.000 and switch to %s" % tool)
        run_gcode(moonraker_url, "G90\nG1 Z10.000 F1200\n%s\nM400" % tool)
        selection = verify_selected_tool(moonraker_url, tool, tool_index)
    return selection


def run_tool_workflow(
    *,
    batch_dir,
    workflow,
    tool,
    initial_status,
    prepared_status,
    priors,
    dashboard,
):
    tool_index = int(tool[-1])
    args = configured_runtime_args(priors, tool, DEFAULT_MOONRAKER_URL)
    records = []
    manifest = {
        "schema_version": 5,
        "run_id": batch_dir.name,
        "tool": tool,
        "workflow": workflow,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "initial_status": initial_status,
        "prepared_status": prepared_status,
        "configured_priors": priors,
        "prepared_tool_selection": None,
        "status": "running",
    }
    summary = None
    contact_total = (
        CALIBRATION_CONTACT_COUNT
        if workflow == "calibration"
        else VERIFICATION_CONTACT_COUNT
    )

    def progress(record):
        dashboard.update_run(
            tool, workflow, records, contact_total, "running", summary=None
        )
        measured_z = record.get("trigger_z")
        suffix = (
            " Z=%.4f" % float(measured_z)
            if record.get("status") == "completed" and measured_z is not None
            else " %s" % record.get("status")
        )
        workflow_log(
            DEFAULT_MOONRAKER_URL,
            "%s %d/%d %s%s"
            % (tool, record["sample_index"], contact_total, record["phase"], suffix),
        )

    try:
        manifest["prepared_tool_selection"] = select_tool_once(
            DEFAULT_MOONRAKER_URL, tool
        )
        workflow_log(
            DEFAULT_MOONRAKER_URL,
            "%s %s: %s contacts" % (tool, workflow, contact_total),
        )
        dashboard.update_run(tool, workflow, records, contact_total, "running")
        if workflow == "calibration":
            summary = run_calibration(
                args, tool_index, records, progress_callback=progress
            )
            manifest["calibration"] = summary
        else:
            summary = run_verification(
                args, tool_index, records, progress_callback=progress
            )
            manifest["verification"] = summary
    except Exception as exc:
        failed_record = getattr(exc, "record", None)
        if failed_record is not None and failed_record not in records:
            records.append(failed_record)
        manifest["status"] = "aborted"
        manifest["error"] = str(exc)
    else:
        manifest["status"] = "completed"
    manifest["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest["final_status"] = status(DEFAULT_MOONRAKER_URL)
    manifest["record_count"] = len(records)
    tool_dir = batch_dir / tool
    manifest_path, csv_path = write_artifacts(tool_dir, manifest, records)
    if summary is not None:
        plot_path = (
            render_calibration(tool_dir, tool, records, summary)
            if workflow == "calibration"
            else render_verification(tool_dir, tool, records, summary)
        )
        manifest["plot"] = str(plot_path)
        dashboard_plot = dashboard.publish_plot(plot_path, tool, workflow)
        dashboard.update_run(
            tool,
            workflow,
            records,
            contact_total,
            "completed" if manifest["status"] == "completed" else "aborted",
            summary=summary,
            plot=dashboard_plot,
        )
        manifest_path, csv_path = write_artifacts(tool_dir, manifest, records)
    elif manifest["status"] != "completed":
        dashboard.update_run(tool, workflow, records, contact_total, "aborted")
    if manifest["status"] != "completed":
        raise ContactMapError(manifest["error"])
    if workflow == "calibration":
        refined = summary["phase_3"]["refined_center"]
        summit = summary["phase_1"]["summit"]
        workflow_log(
            DEFAULT_MOONRAKER_URL,
            "%s centre X=%.6f Y=%.6f direct summit Z=%.6f"
            % (tool, refined["x"], refined["y"], summit["trigger_z"]),
        )
    else:
        estimated = summary["estimated_center"]
        workflow_log(
            DEFAULT_MOONRAKER_URL,
            "%s verification X=%.6f Y=%.6f direct Z=%.6f periphery mean Z=%.6f"
            % (
                tool,
                estimated["x"],
                estimated["y"],
                estimated["trigger_z"],
                summary["periphery_mean_z"],
            ),
        )
    return {
        "tool": tool,
        "manifest": str(manifest_path),
        "records": str(csv_path),
        "summary": summary,
    }


def main(argv):
    command_args = build_parser().parse_args(argv)
    workflow = os.environ.get("MULTI_HEAD_ZERO_BATCH_MODE", "calibration")
    if workflow not in {"calibration", "verification"}:
        raise ContactMapError("invalid internal batch mode: %s" % workflow)
    if command_args.tool != "both" and workflow != "calibration":
        raise ContactMapError("single-tool mode supports calibration only")
    selected_tools = (
        ("T0", "T1") if command_args.tool == "both" else (command_args.tool,)
    )
    run_id = os.environ.get("MULTI_HEAD_ZERO_BATCH_RUN_ID") or dt.datetime.now(
        dt.timezone.utc
    ).strftime("%Y%m%dT%H%M%SZ_batch_%s" % workflow)
    dashboard = DashboardPublisher(run_id, workflow, command_args.tool)
    dashboard.event("Batch requested")
    start_status, prepared_status, homing_required = require_ready_and_prepare(
        DEFAULT_MOONRAKER_URL
    )
    priors_args = SimpleNamespace(x_min=None, x_max=None, y_min=None, y_max=None)
    priors = apply_configured_priors(priors_args, start_status)
    batch_dir = Path(DEFAULT_OUTPUT_DIR).expanduser() / run_id
    batch_dir.mkdir(parents=True, exist_ok=False)
    batch = {
        "schema_version": 1,
        "workflow": workflow,
        "run_id": run_id,
        "tool_selection": command_args.tool,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "homing_required": homing_required,
        "configured_priors": priors,
        "status": "running",
        "runs": {},
    }
    dashboard.payload["status"] = "running"
    dashboard.payload["homing_required"] = homing_required
    dashboard.payload["configured_priors"] = priors
    dashboard.payload["chapters"][workflow]["status"] = "running"
    dashboard.payload["chapters"][workflow]["configured_priors"] = priors
    dashboard.event("Preparation complete")
    try:
        for index, tool in enumerate(selected_tools):
            if index:
                workflow_log(DEFAULT_MOONRAKER_URL, "switching from T0 to T1")
                dashboard.event("Switching from T0 to T1")
            result = run_tool_workflow(
                batch_dir=batch_dir,
                workflow=workflow,
                tool=tool,
                initial_status=start_status,
                prepared_status=prepared_status,
                priors=priors,
                dashboard=dashboard,
            )
            batch["runs"][tool.lower()] = result
    except Exception as exc:
        batch["status"] = "aborted"
        batch["error"] = str(exc)
    else:
        batch["status"] = "completed"
    batch["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    batch["final_status"] = status(DEFAULT_MOONRAKER_URL)
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(batch, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("Batch manifest: %s" % (batch_dir / "batch_manifest.json"), flush=True)
    if batch["status"] != "completed":
        dashboard.finish("aborted", batch["error"])
        workflow_log(DEFAULT_MOONRAKER_URL, "batch aborted: %s" % batch["error"])
        raise ContactMapError(batch["error"])
    dashboard.finish("completed")
    workflow_log(DEFAULT_MOONRAKER_URL, "%s batch complete" % workflow)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ContactMapError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
