#!/usr/bin/env python3
"""Collect raw multi-head-zero contacts and render non-fitted plots on the Pi."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
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
MAX_SEARCH_X_MIN = 72.0
MAX_SEARCH_X_MAX = 79.0
MAX_SEARCH_Y_MIN = -14.8
MAX_SEARCH_Y_MAX = -9.0
MAX_SEARCH_INITIAL_STEP = 1.0
MAX_SEARCH_MIN_STEP = 0.2
MAX_SEARCH_CONTACT_LIMIT = 30
MAX_SEARCH_IMPROVEMENT_EPSILON = 0.005


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


def parse_values(value, option):
    try:
        values = [float(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "%s must be a comma-separated list of numbers" % option
        ) from exc
    if not values:
        raise argparse.ArgumentTypeError("%s must not be empty" % option)
    return values


def build_parser():
    parser = argparse.ArgumentParser(
        description="Collect raw multi-head-zero contact heights and render raw plots."
    )
    parser.add_argument("--tool", choices=("T0", "T1"), default="T0")
    parser.add_argument(
        "--x-values", default="75.2,75.6,76,76.4,76.8,77.2,77.6,78,78.4,78.8"
    )
    parser.add_argument(
        "--y-values", default="-14.8,-14.4,-14,-13.6,-13.2,-12.8,-12.4,-12,-11.6,-11.2"
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--strategy", choices=("grid", "max-search"), default="grid")
    parser.add_argument("--x-min", type=float, default=MAX_SEARCH_X_MIN)
    parser.add_argument("--x-max", type=float, default=MAX_SEARCH_X_MAX)
    parser.add_argument("--y-min", type=float, default=MAX_SEARCH_Y_MIN)
    parser.add_argument("--y-max", type=float, default=MAX_SEARCH_Y_MAX)
    parser.add_argument("--max-contacts", type=int, default=MAX_SEARCH_CONTACT_LIMIT)
    parser.add_argument("--min-step", type=float, default=MAX_SEARCH_MIN_STEP)
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
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ_T0_contact_map")


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
    allow_no_contact,
    **record_fields,
):
    command = "MULTI_HEAD_ZERO_CONTACT X=%.3f Y=%.3f TOOL=%d" % (
        x,
        y,
        tool_index,
    )
    if allow_no_contact:
        command += " ALLOW_NO_CONTACT=1"
    record = {
        "sample_index": sample_index,
        "commanded_x": x,
        "commanded_y": y,
        "tool": tool,
        "command": command,
        **record_fields,
    }
    try:
        # Moonraker accepts scripts before their motion has completed. M400
        # makes this request synchronous from the runner's perspective, so the
        # following status read belongs to this contact rather than the prior
        # one.
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


def render_grid_plots(output_dir, tool, records):
    complete = completed_records(records)
    if not complete:
        return None
    x_values = [record["commanded_x"] for record in complete]
    y_values = [record["commanded_y"] for record in complete]
    z_values = [record["trigger_z"] for record in complete]
    figure, axes = plt.subplots(1, 3, figsize=(18, 5), constrained_layout=True)
    scatter = axes[0].scatter(x_values, y_values, c=z_values, cmap="viridis", s=100)
    axes[0].set_title("Raw multi-head-zero trigger Z by commanded XY (%s)" % tool)
    axes[0].set_xlabel("Commanded X (mm)")
    axes[0].set_ylabel("Commanded Y (mm)")
    axes[0].grid(True, alpha=0.3)
    figure.colorbar(scatter, ax=axes[0], label="Raw trigger Z (mm)")
    unique_x = sorted(set(x_values))
    unique_y = sorted(set(y_values))
    grid_records = {
        (record["commanded_x"], record["commanded_y"]): record["trigger_z"]
        for record in complete
    }
    if len(grid_records) == len(unique_x) * len(unique_y) == len(complete):
        x_grid, y_grid = np.meshgrid(unique_x, unique_y)
        z_grid = np.array(
            [
                [grid_records[(x_value, y_value)] for x_value in unique_x]
                for y_value in unique_y
            ]
        )
        contour = axes[1].contourf(x_grid, y_grid, z_grid, levels=12, cmap="viridis")
        lines = axes[1].contour(
            x_grid, y_grid, z_grid, levels=8, colors="white", linewidths=0.8
        )
        axes[1].clabel(lines, inline=True, fontsize=8, fmt="%.3f")
        figure.colorbar(contour, ax=axes[1], label="Raw trigger Z (mm)")
        axes[1].set_title("Raw trigger-Z contour (%s)" % tool)
        axes[1].set_xlabel("Commanded X (mm)")
        axes[1].set_ylabel("Commanded Y (mm)")
        axes[1].grid(True, alpha=0.3)
    else:
        axes[1].text(
            0.5,
            0.5,
            "Contour requires one raw\nmeasurement per XY grid point.",
            ha="center",
            va="center",
            transform=axes[1].transAxes,
        )
        axes[1].set_axis_off()
    for y_value in unique_y:
        row = sorted(
            (record for record in complete if record["commanded_y"] == y_value),
            key=lambda record: record["commanded_x"],
        )
        axes[2].plot(
            [record["commanded_x"] for record in row],
            [record["trigger_z"] for record in row],
            "o-",
            label="Y=%.1f" % y_value,
        )
    axes[2].set_title("Raw X/Z cross-sections (%s)" % tool)
    axes[2].set_xlabel("Commanded X (mm)")
    axes[2].set_ylabel("Raw trigger Z (mm)")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend(title="Commanded Y", fontsize=8, ncol=2)
    plot_path = output_dir / ("%s_raw_contact_map.png" % tool)
    figure.savefig(plot_path, dpi=200)
    plt.close(figure)
    return plot_path


def is_within_bounds(x, y, bounds):
    return (
        bounds["x_min"] <= x <= bounds["x_max"]
        and bounds["y_min"] <= y <= bounds["y_max"]
    )


def point_key(x, y):
    return (round(x, 3), round(y, 3))


def is_boundary_point(record, bounds):
    x = record["commanded_x"]
    y = record["commanded_y"]
    return any(
        abs(value - boundary) < 0.001
        for value, boundary in (
            (x, bounds["x_min"]),
            (x, bounds["x_max"]),
            (y, bounds["y_min"]),
            (y, bounds["y_max"]),
        )
    )


def run_maximum_search(args, tool_index, records):
    bounds = {
        "x_min": args.x_min,
        "x_max": args.x_max,
        "y_min": args.y_min,
        "y_max": args.y_max,
    }
    seed_x_values = np.linspace(args.x_min, args.x_max, 3).tolist()
    seed_y_values = np.linspace(args.y_min, args.y_max, 3).tolist()
    visited = set()

    def sample(x, y, phase, step_mm=None, candidate_direction=None):
        if len(records) >= args.max_contacts:
            return None
        key = point_key(x, y)
        if key in visited:
            return None
        visited.add(key)
        record = perform_contact(
            args.moonraker_url,
            tool=args.tool,
            tool_index=tool_index,
            x=x,
            y=y,
            sample_index=len(records) + 1,
            allow_no_contact=True,
            phase=phase,
            step_mm=step_mm,
            candidate_direction=candidate_direction,
        )
        records.append(record)
        return record

    for y in seed_y_values:
        for x in seed_x_values:
            sample(x, y, "coarse_seed")
    eligible = completed_records(records)
    if not eligible:
        raise ContactMapError("maximum search found no contact in its 3x3 seed")
    current = max(eligible, key=lambda record: record["trigger_z"])
    step_mm = MAX_SEARCH_INITIAL_STEP
    termination_reason = None
    while True:
        if len(records) >= args.max_contacts:
            termination_reason = "contact_budget"
            break
        candidates = []
        for direction, delta_x, delta_y in (
            ("x_minus", -step_mm, 0.0),
            ("x_plus", step_mm, 0.0),
            ("y_minus", 0.0, -step_mm),
            ("y_plus", 0.0, step_mm),
        ):
            x = current["commanded_x"] + delta_x
            y = current["commanded_y"] + delta_y
            if is_within_bounds(x, y, bounds) and point_key(x, y) not in visited:
                candidates.append((direction, x, y))
        improved = False
        for direction, x, y in candidates:
            record = sample(x, y, "ascent", step_mm, direction)
            if (
                record is not None
                and record.get("status") == "completed"
                and record["trigger_z"]
                > current["trigger_z"] + MAX_SEARCH_IMPROVEMENT_EPSILON
            ):
                current = record
                improved = True
                break
            if len(records) >= args.max_contacts:
                break
        if improved:
            continue
        if len(records) >= args.max_contacts:
            termination_reason = "contact_budget"
            break
        if step_mm <= args.min_step:
            termination_reason = (
                "boundary_limited"
                if is_boundary_point(current, bounds)
                else "converged"
            )
            break
        step_mm = max(args.min_step, step_mm / 2.0)
    maximum = max(completed_records(records), key=lambda record: record["trigger_z"])
    return {
        "bounds": bounds,
        "seed_grid_size": 3,
        "initial_step_mm": MAX_SEARCH_INITIAL_STEP,
        "minimum_step_mm": args.min_step,
        "maximum_contacts": args.max_contacts,
        "improvement_epsilon_mm": MAX_SEARCH_IMPROVEMENT_EPSILON,
        "termination_reason": termination_reason,
        "found_maximum": {
            "sample_index": maximum["sample_index"],
            "x": maximum["commanded_x"],
            "y": maximum["commanded_y"],
            "trigger_z": maximum["trigger_z"],
        },
    }


def render_maximum_search(output_dir, tool, records, search_summary):
    complete = completed_records(records)
    figure, axis = plt.subplots(figsize=(8, 6), constrained_layout=True)
    if complete:
        scatter = axis.scatter(
            [record["commanded_x"] for record in complete],
            [record["commanded_y"] for record in complete],
            c=[record["trigger_z"] for record in complete],
            cmap="viridis",
            s=90,
            zorder=3,
        )
        figure.colorbar(scatter, ax=axis, label="Raw trigger Z (mm)")
        ordered = sorted(complete, key=lambda record: record["sample_index"])
        axis.plot(
            [record["commanded_x"] for record in ordered],
            [record["commanded_y"] for record in ordered],
            "--",
            color="0.35",
            alpha=0.7,
            zorder=1,
            label="Measured-contact path",
        )
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
    maximum = search_summary["found_maximum"]
    axis.scatter(
        [maximum["x"]],
        [maximum["y"]],
        marker="*",
        color="gold",
        edgecolors="black",
        s=260,
        zorder=5,
        label="Observed maximum",
    )
    axis.annotate(
        "max: X=%.3f, Y=%.3f, Z=%.4f"
        % (maximum["x"], maximum["y"], maximum["trigger_z"]),
        (maximum["x"], maximum["y"]),
        xytext=(8, 8),
        textcoords="offset points",
    )
    bounds = search_summary["bounds"]
    axis.set_xlim(bounds["x_min"], bounds["x_max"])
    axis.set_ylim(bounds["y_min"], bounds["y_max"])
    axis.set_aspect("equal", adjustable="box")
    axis.set_title(
        "Adaptive multi-head-zero maximum search (%s, %s)"
        % (tool, search_summary["termination_reason"])
    )
    axis.set_xlabel("Commanded X (mm)")
    axis.set_ylabel("Commanded Y (mm)")
    axis.grid(True, alpha=0.3)
    axis.legend(loc="best")
    plot_path = output_dir / ("%s_maximum_search.png" % tool)
    figure.savefig(plot_path, dpi=200)
    plt.close(figure)
    return plot_path


def main(argv):
    args = build_parser().parse_args(argv)
    if args.repeats < 1 or args.repeats > 8:
        raise ContactMapError("--repeats must be in 1..8")
    x_values = parse_values(args.x_values, "--x-values")
    y_values = parse_values(args.y_values, "--y-values")
    if args.strategy == "grid" and len(x_values) * len(y_values) * args.repeats > 128:
        raise ContactMapError(
            "refusing more than 128 raw contacts in one first-iteration run"
        )
    if args.strategy == "max-search":
        if not args.x_min < args.x_max or not args.y_min < args.y_max:
            raise ContactMapError("maximum-search bounds must have a positive span")
        if args.max_contacts < 9 or args.max_contacts > 128:
            raise ContactMapError("--max-contacts must be in 9..128")
        if args.min_step <= 0.0 or args.min_step > MAX_SEARCH_INITIAL_STEP:
            raise ContactMapError("--min-step must be in (0, 1.0]")
    tool_index = int(args.tool[-1])
    run_id = run_name(args.run_name).replace("T0", args.tool)
    output_dir = Path(args.output_dir).expanduser() / run_id
    records = []
    start_status = status(args.moonraker_url)
    if start_status.get("webhooks", {}).get("state") != "ready":
        raise ContactMapError("Klipper is not ready")
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "tool": args.tool,
        "strategy": args.strategy,
        "x_values": x_values,
        "y_values": y_values,
        "repeats": args.repeats,
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
    sample_index = 0
    search_summary = None
    try:
        if args.strategy == "max-search":
            search_summary = run_maximum_search(args, tool_index, records)
            manifest["maximum_search"] = search_summary
        else:
            for row_index, y in enumerate(y_values):
                row_x_values = (
                    x_values if row_index % 2 == 0 else list(reversed(x_values))
                )
                for x in row_x_values:
                    for repeat_index in range(args.repeats):
                        sample_index += 1
                        record = perform_contact(
                            args.moonraker_url,
                            tool=args.tool,
                            tool_index=tool_index,
                            x=x,
                            y=y,
                            sample_index=sample_index,
                            allow_no_contact=False,
                            row_index=row_index,
                            repeat_index=repeat_index,
                        )
                        records.append(record)
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
        else render_grid_plots(output_dir, args.tool, records)
    )
    print("Manifest: %s" % manifest_path)
    print("Records: %s" % csv_path)
    if plot_path is not None:
        print("Plot: %s" % plot_path)
    if search_summary is not None:
        maximum = search_summary["found_maximum"]
        print(
            "Observed maximum: %s X=%.3f Y=%.3f raw Z=%.6f (%s)"
            % (
                args.tool,
                maximum["x"],
                maximum["y"],
                maximum["trigger_z"],
                search_summary["termination_reason"],
            )
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
