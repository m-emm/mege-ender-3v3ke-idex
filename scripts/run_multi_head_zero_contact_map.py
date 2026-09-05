#!/usr/bin/env python3
"""Locate the multi-head-zero crown with ten guarded contact attempts."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
from matplotlib import pyplot as plt


DEFAULT_MOONRAKER_URL = "http://127.0.0.1:7125"
DEFAULT_OUTPUT_DIR = "~/printer_data/config/multi_head_zero_probe/runs"
SEARCH_X_MIN = 72.0
SEARCH_X_MAX = 79.0
SEARCH_Y_MIN = -14.8
SEARCH_Y_MAX = -9.0
FIT_CONDITION_LIMIT = 1.0e6
FIT_CONCAVITY_EPSILON = 1.0e-6
CONTACT_COUNT = 10


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
        "idex_manual_tuning&multi_head_zero_probe",
    )
    return payload["result"]["status"]


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Locate the multi-head-zero crown from a wide 3x3 seed and one "
            "physical verification contact."
        )
    )
    parser.add_argument("--tool", choices=("T0", "T1"), default="T0")
    parser.add_argument("--x-min", type=float, default=SEARCH_X_MIN)
    parser.add_argument("--x-max", type=float, default=SEARCH_X_MAX)
    parser.add_argument("--y-min", type=float, default=SEARCH_Y_MIN)
    parser.add_argument("--y-max", type=float, default=SEARCH_Y_MAX)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--run-name")
    parser.add_argument("--moonraker-url", default=DEFAULT_MOONRAKER_URL)
    parser.add_argument(
        "--skip-home",
        action="store_true",
        help="Do not run the guarded Tn/G28/BED_MESH_CLEAR preparation sequence.",
    )
    return parser


def run_name(value):
    if value:
        return value
    return dt.datetime.now(dt.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ_T0_coarse_maximum_search"
    )


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
    command = "MULTI_HEAD_ZERO_CONTACT X=%.3f Y=%.3f TOOL=%d ALLOW_NO_CONTACT=1" % (
        x,
        y,
        tool_index,
    )
    record = {
        "sample_index": sample_index,
        "commanded_x": x,
        "commanded_y": y,
        "tool": tool,
        "command": command,
        "phase": phase,
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
    measurement = (
        status(moonraker_url).get("multi_head_zero_probe", {}).get("last_measurement")
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
    return record


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


def maximum_payload(record):
    return {
        "sample_index": record["sample_index"],
        "x": record["commanded_x"],
        "y": record["commanded_y"],
        "trigger_z": record["trigger_z"],
    }


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

    x_values = np.asarray(
        [float(record["commanded_x"]) for record in complete], dtype=float
    )
    y_values = np.asarray(
        [float(record["commanded_y"]) for record in complete], dtype=float
    )
    z_values = np.asarray(
        [float(record["trigger_z"]) for record in complete], dtype=float
    )
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


def run_maximum_search(args, tool_index, records, contact_function=perform_contact):
    bounds = {
        "x_min": args.x_min,
        "x_max": args.x_max,
        "y_min": args.y_min,
        "y_max": args.y_max,
    }
    for y in np.linspace(args.y_min, args.y_max, 3):
        for x in np.linspace(args.x_min, args.x_max, 3):
            record = contact_function(
                args.moonraker_url,
                tool=args.tool,
                tool_index=tool_index,
                x=float(x),
                y=float(y),
                sample_index=len(records) + 1,
                phase="coarse_seed",
            )
            records.append(record)

    fit = fit_paraboloid(records, bounds)
    if fit["status"] != "valid":
        raise ContactMapError(
            "coarse paraboloid fit invalid: %s" % ", ".join(fit["validation_errors"])
        )
    predicted = fit["predicted_maximum"]
    verification = contact_function(
        args.moonraker_url,
        tool=args.tool,
        tool_index=tool_index,
        x=predicted["x"],
        y=predicted["y"],
        sample_index=CONTACT_COUNT,
        phase="coarse_fit_verification",
    )
    records.append(verification)
    if verification.get("status") != "completed":
        raise ContactMapError(
            "coarse fitted vertex produced no contact", record=verification
        )
    maximum = max(completed_records(records), key=lambda record: record["trigger_z"])
    return {
        "algorithm": "coarse_paraboloid_10_contact_v1",
        "bounds": bounds,
        "contact_count": CONTACT_COUNT,
        "seed_grid_size": 3,
        "termination_reason": "coarse_verified",
        "fit_status": "valid",
        "fit": fit,
        "found_maximum": maximum_payload(maximum),
        "predicted_maximum": predicted,
        "verified_maximum": maximum_payload(verification),
    }


def render_maximum_search(output_dir, tool, records, search_summary):
    complete = completed_records(records)
    fit = search_summary["fit"]
    bounds = search_summary["bounds"]
    figure, axis = plt.subplots(figsize=(8, 6), constrained_layout=True)
    fit_x = np.linspace(bounds["x_min"], bounds["x_max"], 100)
    fit_y = np.linspace(bounds["y_min"], bounds["y_max"], 100)
    fit_x_grid, fit_y_grid = np.meshgrid(fit_x, fit_y)
    fit_contours = axis.contour(
        fit_x_grid,
        fit_y_grid,
        evaluate_paraboloid(fit, fit_x_grid, fit_y_grid),
        levels=10,
        colors="black",
        linewidths=0.7,
        alpha=0.45,
        zorder=2,
    )
    axis.clabel(fit_contours, inline=True, fontsize=7, fmt="%.3f")
    axis.plot(
        [],
        [],
        color="black",
        alpha=0.45,
        linewidth=0.7,
        label="Coarse fitted paraboloid",
    )
    scatter = axis.scatter(
        [record["commanded_x"] for record in complete],
        [record["commanded_y"] for record in complete],
        c=[record["trigger_z"] for record in complete],
        cmap="viridis",
        s=90,
        zorder=3,
    )
    figure.colorbar(scatter, ax=axis, label="Raw trigger Z (mm)")
    no_contacts = [record for record in records if record.get("status") == "no_contact"]
    if no_contacts:
        axis.scatter(
            [record["commanded_x"] for record in no_contacts],
            [record["commanded_y"] for record in no_contacts],
            marker="x",
            color="crimson",
            s=85,
            linewidths=2,
            zorder=4,
            label="No contact at target Z",
        )
    observed = search_summary["found_maximum"]
    predicted = search_summary["predicted_maximum"]
    verified = search_summary["verified_maximum"]
    axis.scatter(
        [observed["x"]],
        [observed["y"]],
        marker="*",
        color="gold",
        edgecolors="black",
        s=260,
        zorder=5,
        label="Highest raw contact",
    )
    axis.scatter(
        [predicted["x"]],
        [predicted["y"]],
        marker="D",
        facecolors="none",
        edgecolors="deepskyblue",
        linewidths=2,
        s=130,
        zorder=6,
        label="Fitted and verified XY",
    )
    axis.scatter(
        [verified["x"]],
        [verified["y"]],
        marker="o",
        facecolors="none",
        edgecolors="white",
        linewidths=2,
        s=210,
        zorder=7,
    )
    axis.set_xlim(bounds["x_min"], bounds["x_max"])
    axis.set_ylim(bounds["y_min"], bounds["y_max"])
    axis.set_aspect("equal", adjustable="box")
    axis.set_title("10-contact multi-head-zero coarse search (%s)" % tool)
    axis.set_xlabel("Commanded X (mm)")
    axis.set_ylabel("Commanded Y (mm)")
    axis.grid(True, alpha=0.3)
    axis.text(
        0.02,
        0.02,
        "Fitted/verified XY: %.3f, %.3f\nVerified raw Z: %.4f"
        % (verified["x"], verified["y"], verified["trigger_z"]),
        transform=axis.transAxes,
        va="bottom",
        fontsize=9,
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
        zorder=8,
    )
    axis.legend(loc="upper right", fontsize=8)
    plot_path = output_dir / ("%s_maximum_search.png" % tool)
    figure.savefig(plot_path, dpi=200)
    plt.close(figure)
    return plot_path


def main(argv):
    args = build_parser().parse_args(argv)
    if not args.x_min < args.x_max or not args.y_min < args.y_max:
        raise ContactMapError("search bounds must have a positive span")
    tool_index = int(args.tool[-1])
    run_id = run_name(args.run_name).replace("T0", args.tool)
    output_dir = Path(args.output_dir).expanduser() / run_id
    records = []
    start_status = status(args.moonraker_url)
    if start_status.get("webhooks", {}).get("state") != "ready":
        raise ContactMapError("Klipper is not ready")
    manifest = {
        "schema_version": 3,
        "run_id": run_id,
        "tool": args.tool,
        "strategy": "coarse-max-search",
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "initial_status": start_status,
        "status": "running",
    }
    if not args.skip_home:
        run_gcode(
            args.moonraker_url,
            "%s\nG28\nBED_MESH_CLEAR\nQUERY_MULTI_HEAD_ZERO\nM400" % args.tool,
        )
    prepared_status = status(args.moonraker_url)
    if prepared_status.get("toolhead", {}).get("homed_axes") != "xyz":
        raise ContactMapError("preparation did not establish XYZ homing")
    if prepared_status.get("multi_head_zero_probe", {}).get("state") == "TRIGGERED":
        raise ContactMapError("multi-head-zero is already triggered before the run")
    search_summary = None
    try:
        search_summary = run_maximum_search(args, tool_index, records)
        manifest["maximum_search"] = search_summary
    except Exception as exc:
        failed_record = getattr(exc, "record", None)
        if failed_record is not None and failed_record not in records:
            records.append(failed_record)
        manifest["status"] = "aborted"
        manifest["error"] = str(exc)
    else:
        manifest["status"] = "completed"
    manifest["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest["final_status"] = status(args.moonraker_url)
    manifest["record_count"] = len(records)
    manifest_path, csv_path = write_artifacts(output_dir, manifest, records)
    plot_path = (
        render_maximum_search(output_dir, args.tool, records, search_summary)
        if search_summary is not None
        else None
    )
    print("Manifest: %s" % manifest_path)
    print("Records: %s" % csv_path)
    if plot_path is not None:
        print("Plot: %s" % plot_path)
        predicted = search_summary["predicted_maximum"]
        verified = search_summary["verified_maximum"]
        print(
            "Coarse fitted maximum: %s X=%.6f Y=%.6f fitted Z=%.6f"
            % (args.tool, predicted["x"], predicted["y"], predicted["z"])
        )
        print(
            "Verified coarse point: %s X=%.6f Y=%.6f raw Z=%.6f"
            % (args.tool, verified["x"], verified["y"], verified["trigger_z"])
        )
    if manifest["status"] != "completed":
        raise ContactMapError(manifest["error"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ContactMapError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        raise SystemExit(1)
