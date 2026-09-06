#!/usr/bin/env python3
"""Print the prescribed multi-head-zero calibration move budget."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CALIB_PATH = ROOT / "klipper_setup/klipper_config/calib.yaml"
CONFIG_PATH = ROOT / "klipper_setup/klipper_config/printer.cfg"


def probe_settings():
    values = {}
    inside_section = False
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("["):
            inside_section = line == "[multi_head_zero_probe]"
            continue
        if inside_section:
            match = re.match(r"([a-z_]+):\s*([-0-9.]+)$", line)
            if match:
                values[match.group(1)] = float(match.group(2))
    return values


def path_length(points):
    return sum(math.dist(left, right) for left, right in zip(points, points[1:]))


def main():
    calib = yaml.safe_load(CALIB_PATH.read_text(encoding="utf-8"))
    priors = calib["multi_head_zero_probe"]
    bounds = priors["seed_bounds"]
    target = priors["target"]
    ring_radius = float(priors["refinement_ring_radius_mm"])
    seed = []
    for row, y in enumerate(
        (float(bounds["y_min"]), float(target["y"]), float(bounds["y_max"]))
    ):
        x_values = (float(bounds["x_min"]), float(target["x"]), float(bounds["x_max"]))
        if row % 2:
            x_values = tuple(reversed(x_values))
        seed.extend((x, y) for x in x_values)
    summit = (float(target["x"]), float(target["y"]))
    ring = [
        (
            summit[0] + ring_radius * math.cos(index * math.pi / 4.0),
            summit[1] + ring_radius * math.sin(index * math.pi / 4.0),
        )
        for index in range(8)
    ]
    settings = probe_settings()
    max_tap_seconds = (
        abs(settings["start_z"] - settings["target_z"]) / settings["probe_speed"]
        + abs(settings["start_z"] - settings["target_z"]) / settings["travel_speed"]
    )
    report = {
        "workflow": "prescribed_t0_then_t1_calibration",
        "tools": 2,
        "tool_switches": 1,
        "contacts_per_tool": {"seed": 9, "summit": 1, "ring": 8, "total": 18},
        "contacts_total": 36,
        "verification": {
            "contacts_per_tool": {"centre": 1, "ring": 8, "total": 9},
            "contacts_total": 18,
            "full_calibration_and_verification_contacts": 54,
            "max_seconds_total": 18 * max_tap_seconds,
            "full_calibration_and_verification_max_seconds": 54 * max_tap_seconds,
        },
        "seed_order": seed,
        "xy_path_mm_per_tool": {
            "seed_serpentine": path_length(seed),
            "seed_row_reset": path_length(
                [
                    (x, y)
                    for y in (bounds["y_min"], target["y"], bounds["y_max"])
                    for x in (bounds["x_min"], target["x"], bounds["x_max"])
                ]
            ),
            "seed_to_nominal_summit": math.dist(seed[-1], summit),
            "ring": math.dist(summit, ring[0]) + path_length(ring),
            "total_nominal": path_length(seed + [summit] + ring),
        },
        "z_motion": {
            "per_contact": ["guarded descent", "fast retract to START_Z"],
            "guarded_descent_max_mm": abs(settings["start_z"] - settings["target_z"]),
            "guarded_descent_max_seconds_total": 36
            * abs(settings["start_z"] - settings["target_z"])
            / settings["probe_speed"],
            "max_seconds_per_contact": max_tap_seconds,
            "max_seconds_total": 36 * max_tap_seconds,
        },
        "switch_safety": "One machine-Z=10.000 recovery before preparation; no per-tap tool switches.",
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
