#!/usr/bin/env python3
"""Guarded cold Eddy Z-axis characterization and bed-planeness job.

The job is deliberately report-only. Physical Z endstops remain authoritative,
the generated motion never calls SAVE_CONFIG, and the temporary bed mesh is
cleared in a finally block.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from eddy_relative_calibration import (
    DURATION_MS,
    HASH_PLACEHOLDER,
    SAMPLE_RATE_HZ,
    SETTLE_MS,
    canonical_json_bytes,
    compute_gcode_hash,
    gcode_float,
    median_mad,
    sha256_prefixed,
)

SCHEMA_VERSION = 1
JOB_KIND = "eddy_z_diagnostic"
MEASUREMENT = "eddy_z_diagnostic"
TRAVEL_Z_MM = 5.0
SENSOR_X_POSITIONS_MM = (37.5, 117.5, 197.5)
SENSOR_Y_MM = 117.5
HYSTERESIS_TARGETS_MM = (1.0, 2.0, 3.0)
HYSTERESIS_APPROACH_MM = 0.5
HYSTERESIS_CYCLES = 6
SMALL_STEP_BASE_MM = 2.0
SMALL_STEP_VALUES_MM = (0.01, 0.02, 0.04, 0.08, 0.16)
SMALL_STEP_REPEATS = 3
HOMING_CYCLES = 10
REFERENCE_DRIFT_LIMIT_MM = 0.05
MAX_COLD_TEMPERATURE_C = 35.0
DEFAULT_JOB_ROOT = Path(
    os.environ.get(
        "VISION_NOZZLE_JOB_ROOT",
        "/home/pi/printer_data/vision/nozzle_cam/jobs",
    )
)
DEFAULT_VIRTUAL_SD_ROOT = Path(
    os.environ.get("VISION_VIRTUAL_SD_ROOT", "/home/pi/printer_data/gcodes")
)
DEFAULT_VIRTUAL_SD_SUBDIR = os.environ.get("VISION_VIRTUAL_SD_SUBDIR", "vision_jobs")
DEFAULT_MOONRAKER_URL = "http://127.0.0.1:7125"
NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_name(value: Any) -> str:
    return NAME_RE.sub("_", str(value or "")).strip("._-") or "baseline"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def append_event(job_dir: Path, event: str, details: dict[str, Any]) -> None:
    record = {"at_utc": utc_now(), "event": event, **details}
    path = job_dir / "events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def sensor_to_nozzle(
    sensor_x: float,
    sensor_y: float,
    *,
    x_offset: float,
    y_offset: float,
) -> tuple[float, float]:
    return sensor_x - x_offset, sensor_y - y_offset


def _sample(
    samples: list[dict[str, Any]],
    *,
    phase: str,
    commanded_z: float,
    approach: str,
    pre_moves: list[dict[str, float]],
    nozzle_to_coil_z: float,
    **metadata: Any,
) -> None:
    seq = len(samples)
    suffix = sanitize_name(
        "_".join(
            str(value)
            for value in (
                phase,
                metadata.get("target_z", ""),
                metadata.get("cycle", ""),
                approach,
                metadata.get("role", ""),
            )
        )
    )
    sample_id = f"{seq:03d}_{suffix}"
    samples.append(
        {
            "seq": seq,
            "sample": sample_id,
            "phase": phase,
            "commanded_z": round(commanded_z, 4),
            "nozzle_gap": round(commanded_z, 4),
            "coil_gap": round(commanded_z + nozzle_to_coil_z, 4),
            "approach": approach,
            "settle_ms": SETTLE_MS,
            "duration_ms": DURATION_MS,
            "pre_moves": pre_moves,
            **metadata,
        }
    )


def build_sample_schedule(
    *,
    bed_center_x: float = 117.5,
    bed_center_y: float = 117.5,
    x_offset: float = -8.18,
    y_offset: float = 9.0,
    nozzle_to_coil_z: float = 2.5,
) -> dict[str, Any]:
    """Build deterministic motion and sample metadata for the cold baseline."""

    center_x, center_y = sensor_to_nozzle(
        bed_center_x,
        bed_center_y,
        x_offset=x_offset,
        y_offset=y_offset,
    )
    samples: list[dict[str, Any]] = []

    def reference(label: str) -> None:
        _sample(
            samples,
            phase="reference",
            commanded_z=3.0,
            approach="descending",
            pre_moves=[
                {"z": TRAVEL_Z_MM, "feed": 1200.0},
                {"x": center_x, "y": center_y, "z": TRAVEL_Z_MM, "feed": 6000.0},
                {"z": 3.5, "feed": 1200.0},
                {"z": 3.0, "feed": 300.0},
            ],
            nozzle_to_coil_z=nozzle_to_coil_z,
            label=label,
            reference=True,
            sensor_x=bed_center_x,
            sensor_y=bed_center_y,
        )

    reference("before")

    for index in range(5):
        _sample(
            samples,
            phase="stationary",
            commanded_z=2.0,
            approach="stationary",
            pre_moves=(
                [{"z": 2.5, "feed": 1200.0}, {"z": 2.0, "feed": 300.0}]
                if index == 0
                else []
            ),
            nozzle_to_coil_z=nozzle_to_coil_z,
            cycle=index,
            sensor_x=bed_center_x,
            sensor_y=bed_center_y,
        )

    for target in HYSTERESIS_TARGETS_MM:
        for cycle in range(HYSTERESIS_CYCLES):
            directions = (
                ("descending", "ascending")
                if cycle % 2 == 0
                else ("ascending", "descending")
            )
            for direction in directions:
                anchor = (
                    target + HYSTERESIS_APPROACH_MM
                    if direction == "descending"
                    else target - HYSTERESIS_APPROACH_MM
                )
                _sample(
                    samples,
                    phase="hysteresis",
                    commanded_z=target,
                    approach=direction,
                    pre_moves=[
                        {"z": anchor, "feed": 1200.0},
                        {"z": target, "feed": 300.0},
                    ],
                    nozzle_to_coil_z=nozzle_to_coil_z,
                    target_z=target,
                    cycle=cycle,
                    pair_id=f"h_{gcode_float(target)}_{cycle}",
                    sensor_x=bed_center_x,
                    sensor_y=bed_center_y,
                )

    for delta in SMALL_STEP_VALUES_MM:
        for repeat in range(SMALL_STEP_REPEATS):
            for direction in (-1, 1):
                requested_delta = round(direction * delta, 4)
                pair_id = (
                    f"s_{gcode_float(delta)}_{repeat}_"
                    f"{'pos' if direction > 0 else 'neg'}"
                )
                opposite_anchor = SMALL_STEP_BASE_MM + direction * 0.25
                _sample(
                    samples,
                    phase="small_step",
                    commanded_z=SMALL_STEP_BASE_MM,
                    approach="positive" if direction > 0 else "negative",
                    pre_moves=[
                        {"z": opposite_anchor, "feed": 1200.0},
                        {"z": SMALL_STEP_BASE_MM, "feed": 120.0},
                    ],
                    nozzle_to_coil_z=nozzle_to_coil_z,
                    requested_delta=requested_delta,
                    repeat=repeat,
                    pair_id=pair_id,
                    role="baseline",
                    sensor_x=bed_center_x,
                    sensor_y=bed_center_y,
                )
                _sample(
                    samples,
                    phase="small_step",
                    commanded_z=SMALL_STEP_BASE_MM + requested_delta,
                    approach="positive" if direction > 0 else "negative",
                    pre_moves=[
                        {
                            "z": SMALL_STEP_BASE_MM + requested_delta,
                            "feed": 60.0,
                        }
                    ],
                    nozzle_to_coil_z=nozzle_to_coil_z,
                    requested_delta=requested_delta,
                    repeat=repeat,
                    pair_id=pair_id,
                    role="response",
                    sensor_x=bed_center_x,
                    sensor_y=bed_center_y,
                )

    reference("mid")

    for cycle in range(HOMING_CYCLES):
        for position_index, sensor_x in enumerate(SENSOR_X_POSITIONS_MM):
            nozzle_x, nozzle_y = sensor_to_nozzle(
                sensor_x,
                SENSOR_Y_MM,
                x_offset=x_offset,
                y_offset=y_offset,
            )
            pre_moves: list[dict[str, float]] = []
            if position_index == 0:
                pre_moves.append({"home_z": 1.0})
            pre_moves.extend(
                [
                    {"z": TRAVEL_Z_MM, "feed": 1200.0},
                    {
                        "x": nozzle_x,
                        "y": nozzle_y,
                        "z": TRAVEL_Z_MM,
                        "feed": 6000.0,
                    },
                    {"z": 1.5, "feed": 1200.0},
                    {"z": 1.0, "feed": 300.0},
                ]
            )
            _sample(
                samples,
                phase="homing",
                commanded_z=1.0,
                approach="descending",
                pre_moves=pre_moves,
                nozzle_to_coil_z=nozzle_to_coil_z,
                cycle=cycle,
                position_index=position_index,
                sensor_x=sensor_x,
                sensor_y=SENSOR_Y_MM,
            )

    reference("after")
    return {
        "samples": samples,
        "center_nozzle": {"x": center_x, "y": center_y},
        "bed_center": {"x": bed_center_x, "y": bed_center_y},
        "sensor_x_positions": list(SENSOR_X_POSITIONS_MM),
        "sensor_y": SENSOR_Y_MM,
        "travel_z": TRAVEL_Z_MM,
        "hysteresis_targets": list(HYSTERESIS_TARGETS_MM),
        "hysteresis_cycles": HYSTERESIS_CYCLES,
        "small_step_values": list(SMALL_STEP_VALUES_MM),
        "small_step_repeats": SMALL_STEP_REPEATS,
        "homing_cycles": HOMING_CYCLES,
    }


def build_sweep_manifest(
    *,
    job_id: str,
    schedule: dict[str, Any],
    active_config_fingerprint: str,
    x_offset: float,
    y_offset: float,
    nozzle_to_coil_z: float,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": JOB_KIND,
        "job_id": job_id,
        "created_at_utc": utc_now(),
        "manifest_hash": HASH_PLACEHOLDER,
        "gcode_hash": HASH_PLACEHOLDER,
        "report_only": True,
        "cold_only": True,
        "save_config_allowed": False,
        "physical_z_endstops_authoritative": True,
        "active_config_fingerprint": active_config_fingerprint,
        "probe_offsets": {
            "x": round(x_offset, 4),
            "y": round(y_offset, 4),
            "z": round(nozzle_to_coil_z, 4),
        },
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "settle_ms": SETTLE_MS,
        "duration_ms": DURATION_MS,
        "schedule": {key: value for key, value in schedule.items() if key != "samples"},
        "samples": schedule["samples"],
        "bed_mesh": {
            "mesh_min": [37.5, 37.5],
            "mesh_max": [197.5, 197.5],
            "probe_count": [5, 5],
            "horizontal_move_z": TRAVEL_Z_MM,
            "method": "default",
            "persist": False,
        },
    }


def _render_move(move: dict[str, float]) -> list[str]:
    if "home_z" in move:
        return ["G28 Z", "M400"]
    words = [
        f"{axis.upper()}{gcode_float(move[axis])}"
        for axis in ("x", "y", "z")
        if axis in move
    ]
    if "feed" in move:
        words.append(f"F{gcode_float(move['feed'])}")
    return ["G1 " + " ".join(words), "M400"]


def render_sweep_gcode(manifest: dict[str, Any]) -> str:
    lines = [
        f"; guarded cold Eddy Z diagnostic {manifest['job_id']}",
        "; report-only; no SAVE_CONFIG; runtime bed mesh cleared by runner",
        "G90",
        "T0",
    ]
    for sample in manifest["samples"]:
        for move in sample["pre_moves"]:
            lines.extend(_render_move(move))
        lines.append(
            "VISION_EDDY_SAMPLE_SYNC "
            f"JOB={manifest['job_id']} SEQ={sample['seq']} "
            f"SAMPLE={sample['sample']} "
            f"MANIFEST_HASH={manifest['manifest_hash']} "
            f"APPROACH={sample['approach']} "
            f"COMMANDED_Z={gcode_float(sample['commanded_z'])} "
            f"NOZZLE_GAP={gcode_float(sample['nozzle_gap'])} "
            f"COIL_GAP={gcode_float(sample['coil_gap'])} "
            f"SETTLE_MS={SETTLE_MS} DURATION_MS={DURATION_MS}"
        )
    lines.extend(
        [
            f"G1 Z{gcode_float(TRAVEL_Z_MM)} F1200",
            "M400",
            "BED_MESH_CLEAR",
            "BED_MESH_CALIBRATE",
            "M400",
        ]
    )
    return "\n".join(lines) + "\n"


def finalize_sweep_hashes(
    manifest: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    finalized = json.loads(json.dumps(manifest))
    finalized["manifest_hash"] = HASH_PLACEHOLDER
    finalized["gcode_hash"] = HASH_PLACEHOLDER
    finalized["gcode_hash"] = compute_gcode_hash(render_sweep_gcode(finalized))
    finalized["manifest_hash"] = HASH_PLACEHOLDER
    finalized["manifest_hash"] = sha256_prefixed(canonical_json_bytes(finalized))
    gcode = render_sweep_gcode(finalized)
    if compute_gcode_hash(gcode) != finalized["gcode_hash"]:
        raise RuntimeError("Eddy Z diagnostic G-code hash did not stabilize")
    return finalized, gcode


def validate_schedule_safety(
    schedule: dict[str, Any],
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    z_min: float,
    z_max: float,
) -> None:
    current_z: float | None = None
    for sample in schedule["samples"]:
        for move in sample["pre_moves"]:
            if "home_z" in move:
                current_z = z_max
                continue
            x = move.get("x")
            y = move.get("y")
            z = move.get("z")
            for axis, value, lower, upper in (
                ("X", x, x_min, x_max),
                ("Y", y, y_min, y_max),
                ("Z", z, z_min, z_max),
            ):
                if value is not None and not lower <= value <= upper:
                    raise RuntimeError(
                        f"{axis} move {value:.4f} outside [{lower:.4f}, {upper:.4f}]"
                    )
            lateral = x is not None or y is not None
            move_z = current_z if z is None else z
            if lateral and (move_z is None or move_z < TRAVEL_Z_MM - 1.0e-9):
                raise RuntimeError("lateral diagnostic travel below Z5 is forbidden")
            if z is not None:
                current_z = z
        commanded_z = float(sample["commanded_z"])
        if not z_min <= commanded_z <= z_max:
            raise RuntimeError(
                f"sample {sample['sample']} Z={commanded_z:.4f} is outside limits"
            )
        current_z = commanded_z


def moonraker_get(base_url: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=20) as response:
        return json.loads(response.read())


def run_gcode(base_url: str, script: str, *, timeout: float = 60.0) -> None:
    data = urllib.parse.urlencode({"script": script}).encode()
    request = urllib.request.Request(
        base_url.rstrip("/") + "/printer/gcode/script",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()


def query_status(base_url: str) -> dict[str, Any]:
    objects = (
        "webhooks&print_stats&toolhead&extruder&extruder1&heater_bed&configfile&"
        "bed_mesh&temperature_probe%20btt_eddy&"
        "temperature_sensor%20btt_eddy_mcu&"
        "gcode_macro%20_IDEX_CONFIG_FINGERPRINT"
    )
    return moonraker_get(base_url, f"/printer/objects/query?{objects}")["result"][
        "status"
    ]


def preflight(
    status: dict[str, Any],
    *,
    expected_fingerprint: str,
    schedule: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []
    if (status.get("webhooks") or {}).get("state") != "ready":
        failures.append("Klippy is not ready")
    print_state = (status.get("print_stats") or {}).get("state")
    if print_state not in ("standby", "complete"):
        failures.append(f"printer is not idle: print_stats.state={print_state!r}")
    homed_axes = str((status.get("toolhead") or {}).get("homed_axes") or "")
    if any(axis not in homed_axes for axis in "xyz"):
        failures.append(f"XYZ are not homed: homed_axes={homed_axes!r}")
    temperatures: dict[str, dict[str, Any]] = {}
    for name in ("heater_bed", "extruder", "extruder1"):
        heater = status.get(name) or {}
        temperatures[name] = {
            "temperature": heater.get("temperature"),
            "target": heater.get("target"),
        }
        if float(heater.get("target") or 0.0) != 0.0:
            failures.append(f"{name} target is not zero")
        if float(heater.get("temperature") or 0.0) > MAX_COLD_TEMPERATURE_C:
            failures.append(f"{name} is above {MAX_COLD_TEMPERATURE_C:.0f}C")
    configfile = status.get("configfile") or {}
    if configfile.get("save_config_pending") is not False:
        failures.append("configfile.save_config_pending is not exactly false")
    settings = configfile.get("settings") or {}
    eddy = settings.get("probe_eddy_current btt_eddy") or {}
    if eddy.get("reg_drive_current") is None:
        failures.append("active Eddy reg_drive_current is missing")
    if not str(eddy.get("calibrate") or "").strip():
        failures.append("active Eddy calibrate curve is missing")
    active_fingerprint = str(
        (status.get("gcode_macro _IDEX_CONFIG_FINGERPRINT") or {}).get("source_sha256")
        or ""
    ).removeprefix("sha256:")
    expected = str(expected_fingerprint).removeprefix("sha256:")
    if not expected or active_fingerprint.lower() != expected.lower():
        failures.append(
            "active config fingerprint does not match the queued diagnostic"
        )
    stepper_x = settings.get("stepper_x") or {}
    stepper_y = settings.get("stepper_y") or {}
    stepper_z = settings.get("stepper_z") or {}
    limits = {
        "x_min": float(stepper_x.get("position_min", 0.0)),
        "x_max": float(stepper_x.get("position_max", 0.0)),
        "y_min": float(stepper_y.get("position_min", 0.0)),
        "y_max": float(stepper_y.get("position_max", 0.0)),
        "z_min": float(stepper_z.get("position_min", 0.0)),
        "z_max": float(stepper_z.get("position_max", 0.0)),
    }
    try:
        validate_schedule_safety(schedule, **limits)
    except RuntimeError as exc:
        failures.append(str(exc))
    if failures:
        raise RuntimeError("; ".join(failures))
    return {
        "ok": True,
        "active_config_fingerprint": active_fingerprint,
        "save_config_pending": False,
        "print_state": print_state,
        "homed_axes": homed_axes,
        "temperatures": temperatures,
        "eddy": {
            "reg_drive_current": eddy.get("reg_drive_current"),
            "calibrate_pair_count": len(
                [
                    value
                    for value in str(eddy.get("calibrate") or "").split(",")
                    if value.strip()
                ]
            ),
        },
        "limits": limits,
    }


def load_sample_records(
    sweep_dir: Path, manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for sample in manifest["samples"]:
        path = sweep_dir / "raw" / f"{sample['seq']:03d}_{sample['sample']}.json"
        if not path.is_file():
            raise RuntimeError(f"missing Eddy sample sidecar: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw_samples = raw.get("samples") or []
        frequencies = [float(value[1]) for value in raw_samples]
        heights = [float(value[2]) for value in raw_samples]
        median_frequency, mad_frequency = median_mad(frequencies)
        median_height, mad_height = median_mad(heights)
        records.append(
            {
                **sample,
                "sample_path": str(path),
                "captured_at_utc": raw.get("captured_at_utc"),
                "sample_count": len(raw_samples),
                "raw_samples": raw_samples,
                "median_frequency_hz": median_frequency,
                "mad_frequency_hz": mad_frequency,
                "median_height_mm": median_height,
                "mad_height_mm": mad_height,
                "stddev_height_mm": (
                    float(statistics.pstdev(heights)) if len(heights) > 1 else 0.0
                ),
                "errors": int(raw.get("errors") or 0),
                "overflows": int(raw.get("overflows") or 0),
                "complete": bool(raw.get("complete")),
                "temperatures": raw.get("temperatures") or {},
            }
        )
    return records


def _summary(values: list[float]) -> dict[str, float | None]:
    median, mad = median_mad(values)
    return {
        "count": len(values),
        "median": median,
        "mad": mad,
        "stddev": float(statistics.pstdev(values)) if len(values) > 1 else 0.0,
        "range": max(values) - min(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
    }


def analyze_records(
    records: list[dict[str, Any]],
    manifest: dict[str, Any],
    mesh: dict[str, Any],
) -> dict[str, Any]:
    hard_failures: list[str] = []
    expected_samples = int(SAMPLE_RATE_HZ * DURATION_MS / 1000)
    incomplete = [
        record
        for record in records
        if not record["complete"]
        or record["sample_count"] < int(expected_samples * 0.8)
        or record["errors"]
        or record["overflows"]
        or record["median_height_mm"] is None
    ]
    if len(records) != len(manifest["samples"]):
        hard_failures.append(
            f"received {len(records)} of {len(manifest['samples'])} sample windows"
        )
    if incomplete:
        hard_failures.append(
            f"{len(incomplete)} sample windows are incomplete or contain sensor errors"
        )

    stationary = [
        float(record["median_height_mm"])
        for record in records
        if record["phase"] == "stationary"
    ]
    stationary_points = [
        float(point[2])
        for record in records
        if record["phase"] == "stationary"
        for point in record["raw_samples"]
    ]

    hysteresis: list[dict[str, Any]] = []
    for target in HYSTERESIS_TARGETS_MM:
        descending = [
            float(record["median_height_mm"])
            for record in records
            if record["phase"] == "hysteresis"
            and float(record["target_z"]) == target
            and record["approach"] == "descending"
        ]
        ascending = [
            float(record["median_height_mm"])
            for record in records
            if record["phase"] == "hysteresis"
            and float(record["target_z"]) == target
            and record["approach"] == "ascending"
        ]
        descending_summary = _summary(descending)
        ascending_summary = _summary(ascending)
        signed = (
            float(ascending_summary["median"]) - float(descending_summary["median"])
            if ascending_summary["median"] is not None
            and descending_summary["median"] is not None
            else None
        )
        hysteresis.append(
            {
                "commanded_z_mm": target,
                "descending": descending_summary,
                "ascending": ascending_summary,
                "signed_ascending_minus_descending_mm": signed,
                "absolute_directional_hysteresis_mm": (
                    abs(signed) if signed is not None else None
                ),
            }
        )

    small_pairs: list[dict[str, Any]] = []
    pair_ids = sorted(
        {
            str(record["pair_id"])
            for record in records
            if record["phase"] == "small_step"
        }
    )
    for pair_id in pair_ids:
        pair = [
            record
            for record in records
            if record["phase"] == "small_step" and str(record["pair_id"]) == pair_id
        ]
        baseline = next(
            (record for record in pair if record["role"] == "baseline"), None
        )
        response = next(
            (record for record in pair if record["role"] == "response"), None
        )
        if baseline is None or response is None:
            hard_failures.append(f"small-step pair {pair_id} is incomplete")
            continue
        requested = float(response["requested_delta"])
        measured = float(response["median_height_mm"]) - float(
            baseline["median_height_mm"]
        )
        noise = math.hypot(
            float(baseline["mad_height_mm"] or 0.0),
            float(response["mad_height_mm"] or 0.0),
        )
        resolved = measured * requested > 0.0 and abs(measured) > max(
            3.0 * noise, 0.001
        )
        small_pairs.append(
            {
                "pair_id": pair_id,
                "requested_delta_mm": requested,
                "measured_delta_mm": measured,
                "lost_motion_mm": abs(requested) - abs(measured),
                "combined_mad_mm": noise,
                "resolved": resolved,
            }
        )
    reliable_by_direction: dict[str, float | None] = {}
    for direction_name, sign in (("negative", -1), ("positive", 1)):
        reliable_by_direction[direction_name] = None
        for delta in SMALL_STEP_VALUES_MM:
            matching = [
                pair
                for pair in small_pairs
                if math.isclose(abs(pair["requested_delta_mm"]), delta)
                and pair["requested_delta_mm"] * sign > 0
            ]
            if sum(bool(pair["resolved"]) for pair in matching) >= 2:
                reliable_by_direction[direction_name] = delta
                break
    resolved_values = [
        value for value in reliable_by_direction.values() if value is not None
    ]

    homing_positions: list[dict[str, Any]] = []
    for sensor_x in SENSOR_X_POSITIONS_MM:
        values = [
            float(record["median_height_mm"])
            for record in records
            if record["phase"] == "homing"
            and math.isclose(float(record["sensor_x"]), sensor_x)
        ]
        homing_positions.append({"sensor_x_mm": sensor_x, **_summary(values)})
    gantry_cycles: list[dict[str, Any]] = []
    for cycle in range(HOMING_CYCLES):
        cycle_records = sorted(
            [
                record
                for record in records
                if record["phase"] == "homing" and int(record["cycle"]) == cycle
            ],
            key=lambda record: float(record["sensor_x"]),
        )
        if len(cycle_records) != len(SENSOR_X_POSITIONS_MM):
            hard_failures.append(f"homing cycle {cycle} is incomplete")
            continue
        xs = np.array([float(record["sensor_x"]) for record in cycle_records])
        zs = np.array([float(record["median_height_mm"]) for record in cycle_records])
        slope, intercept = np.polyfit(xs, zs, 1)
        fitted = slope * xs + intercept
        gantry_cycles.append(
            {
                "cycle": cycle,
                "slope_mm_per_mm": float(slope),
                "left_to_right_span_mm": float(
                    slope * (SENSOR_X_POSITIONS_MM[-1] - SENSOR_X_POSITIONS_MM[0])
                ),
                "center_residual_mm": float(zs[1] - fitted[1]),
                "values_mm": zs.tolist(),
            }
        )

    references = [record for record in records if bool(record.get("reference"))]
    reference_values = [float(record["median_height_mm"]) for record in references]
    reference_drift = (
        max(reference_values) - min(reference_values) if reference_values else None
    )
    if reference_drift is None or reference_drift > REFERENCE_DRIFT_LIMIT_MM:
        hard_failures.append(
            "reference drift is unavailable or exceeds "
            f"{REFERENCE_DRIFT_LIMIT_MM:.3f}mm"
        )

    mesh_analysis = analyze_mesh(mesh)
    hard_failures.extend(mesh_analysis.pop("hard_failures"))
    temperatures = []
    for record in records:
        coil = (record.get("temperatures") or {}).get("coil") or {}
        mcu = (record.get("temperatures") or {}).get("mcu") or {}
        temperatures.append(
            {
                "seq": record["seq"],
                "coil_c": coil.get("temperature"),
                "mcu_c": mcu.get("temperature"),
            }
        )
    hysteresis_values = [
        item["absolute_directional_hysteresis_mm"]
        for item in hysteresis
        if item["absolute_directional_hysteresis_mm"] is not None
    ]
    slope_spans = [float(item["left_to_right_span_mm"]) for item in gantry_cycles]
    return {
        "schema_version": SCHEMA_VERSION,
        "measurement": MEASUREMENT,
        "kind": JOB_KIND,
        "job_id": manifest["job_id"],
        "created_at_utc": utc_now(),
        "ok": not hard_failures,
        "accepted": not hard_failures,
        "cold_only": True,
        "report_only": True,
        "mechanical_verdict": "baseline_only",
        "hard_failures": hard_failures,
        "quality": {
            "expected_window_count": len(manifest["samples"]),
            "received_window_count": len(records),
            "incomplete_window_count": len(incomplete),
            "reference_drift_mm": reference_drift,
            "reference_drift_limit_mm": REFERENCE_DRIFT_LIMIT_MM,
        },
        "stationary_noise": {
            "window_medians_mm": _summary(stationary),
            "raw_calibrated_height_mm": _summary(stationary_points),
        },
        "hysteresis": hysteresis,
        "maximum_absolute_hysteresis_mm": (
            max(hysteresis_values) if hysteresis_values else None
        ),
        "small_step_response": {
            "pairs": small_pairs,
            "smallest_reliably_resolved_by_direction_mm": reliable_by_direction,
            "smallest_reliably_resolved_reversal_mm": (
                max(resolved_values) if len(resolved_values) == 2 else None
            ),
        },
        "homing_repeatability": {
            "cycles": HOMING_CYCLES,
            "positions": homing_positions,
        },
        "gantry_plane": {
            "cycles": gantry_cycles,
            "left_to_right_span_mm": _summary(slope_spans),
        },
        "bed_planeness": mesh_analysis,
        "temperatures": temperatures,
    }


def analyze_mesh(mesh: dict[str, Any]) -> dict[str, Any]:
    matrix = mesh.get("probed_matrix") or mesh.get("mesh_matrix") or []
    failures: list[str] = []
    if (
        not isinstance(matrix, list)
        or len(matrix) != 5
        or any(not isinstance(row, list) or len(row) != 5 for row in matrix)
    ):
        return {
            "hard_failures": ["bed mesh did not produce a complete 5x5 matrix"],
            "matrix": matrix,
        }
    z = np.array(matrix, dtype=float)
    if not np.all(np.isfinite(z)):
        failures.append("bed mesh contains non-finite values")
    mesh_min = mesh.get("mesh_min") or [37.5, 37.5]
    mesh_max = mesh.get("mesh_max") or [197.5, 197.5]
    xs = np.linspace(float(mesh_min[0]), float(mesh_max[0]), z.shape[1])
    ys = np.linspace(float(mesh_min[1]), float(mesh_max[1]), z.shape[0])
    xx, yy = np.meshgrid(xs, ys)
    design = np.column_stack((xx.ravel(), yy.ravel(), np.ones(z.size)))
    coefficients, *_unused = np.linalg.lstsq(design, z.ravel(), rcond=None)
    fitted = (design @ coefficients).reshape(z.shape)
    residual = z - fitted
    x_slope, y_slope, intercept = coefficients
    return {
        "hard_failures": failures,
        "matrix": z.tolist(),
        "mesh_min": [float(mesh_min[0]), float(mesh_min[1])],
        "mesh_max": [float(mesh_max[0]), float(mesh_max[1])],
        "peak_to_valley_mm": float(np.ptp(z)),
        "best_fit_plane": {
            "x_slope_mm_per_mm": float(x_slope),
            "y_slope_mm_per_mm": float(y_slope),
            "intercept_mm": float(intercept),
            "x_span_mm": float(x_slope * (xs[-1] - xs[0])),
            "y_span_mm": float(y_slope * (ys[-1] - ys[0])),
        },
        "residual_matrix": residual.tolist(),
        "residual_peak_to_valley_mm": float(np.ptp(residual)),
        "residual_rms_mm": float(np.sqrt(np.mean(np.square(residual)))),
    }


def write_samples(
    job_dir: Path,
    records: list[dict[str, Any]],
) -> None:
    json_records = [
        {key: value for key, value in record.items() if key != "raw_samples"}
        for record in records
    ]
    atomic_write_json(job_dir / "samples.json", json_records)
    with (job_dir / "samples.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "seq",
                "sample",
                "phase",
                "approach",
                "commanded_z_mm",
                "sensor_x_mm",
                "sensor_y_mm",
                "sample_index",
                "time_s",
                "frequency_hz",
                "calibrated_height_mm",
            ),
        )
        writer.writeheader()
        for record in records:
            for index, point in enumerate(record["raw_samples"]):
                writer.writerow(
                    {
                        "seq": record["seq"],
                        "sample": record["sample"],
                        "phase": record["phase"],
                        "approach": record["approach"],
                        "commanded_z_mm": record["commanded_z"],
                        "sensor_x_mm": record.get("sensor_x"),
                        "sensor_y_mm": record.get("sensor_y"),
                        "sample_index": index,
                        "time_s": point[0],
                        "frequency_hz": point[1],
                        "calibrated_height_mm": point[2],
                    }
                )


def _plot_series(
    path: Path,
    *,
    title: str,
    xlabel: str,
    ylabel: str,
    series: list[tuple[str, list[float], list[float], tuple[int, int, int]]],
) -> None:
    width, height = 1100, 700
    canvas = np.full((height, width, 3), 250, dtype=np.uint8)
    left, right, top, bottom = 100, 40, 70, 85
    all_x = [value for _name, xs, _ys, _color in series for value in xs]
    all_y = [value for _name, _xs, ys, _color in series for value in ys]
    if not all_x or not all_y:
        cv2.putText(
            canvas,
            "No data",
            (420, 350),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (40, 40, 40),
            2,
        )
        cv2.imwrite(str(path), canvas)
        return
    x_min, x_max = min(all_x), max(all_x)
    y_min, y_max = min(all_y), max(all_y)
    if math.isclose(x_min, x_max):
        x_min, x_max = x_min - 0.5, x_max + 0.5
    if math.isclose(y_min, y_max):
        y_min, y_max = y_min - 0.001, y_max + 0.001
    y_pad = 0.08 * (y_max - y_min)
    y_min -= y_pad
    y_max += y_pad

    def point(x: float, y: float) -> tuple[int, int]:
        px = left + int((x - x_min) / (x_max - x_min) * (width - left - right))
        py = (
            height
            - bottom
            - int((y - y_min) / (y_max - y_min) * (height - top - bottom))
        )
        return px, py

    cv2.rectangle(
        canvas,
        (left, top),
        (width - right, height - bottom),
        (90, 90, 90),
        1,
    )
    legend_y = top + 25
    for name, xs, ys, color in series:
        points = [point(x, y) for x, y in zip(xs, ys)]
        for start, end in zip(points, points[1:]):
            cv2.line(canvas, start, end, color, 2, cv2.LINE_AA)
        for px, py in points:
            cv2.circle(canvas, (px, py), 4, color, -1, cv2.LINE_AA)
        cv2.line(canvas, (width - 330, legend_y), (width - 285, legend_y), color, 3)
        cv2.putText(
            canvas,
            name,
            (width - 275, legend_y + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (30, 30, 30),
            1,
            cv2.LINE_AA,
        )
        legend_y += 24
    cv2.putText(
        canvas,
        title,
        (left, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (20, 20, 20),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        xlabel,
        (width // 2 - 80, height - 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (30, 30, 30),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        ylabel,
        (12, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (30, 30, 30),
        1,
        cv2.LINE_AA,
    )
    cv2.imwrite(str(path), canvas)


def _write_mesh_plots(plots_dir: Path, analysis: dict[str, Any]) -> list[str]:
    bed = analysis["bed_planeness"]
    matrix_value = bed.get("matrix") or []
    if len(matrix_value) != 5:
        return []
    matrix = np.array(matrix_value, dtype=float)
    normalized = cv2.normalize(matrix, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    heatmap = cv2.applyColorMap(
        cv2.resize(normalized, (800, 800), interpolation=cv2.INTER_NEAREST),
        cv2.COLORMAP_TURBO,
    )
    heatmap_path = plots_dir / "bed_planeness.png"
    cv2.imwrite(str(heatmap_path), heatmap)

    canvas = np.full((760, 1100, 3), 250, dtype=np.uint8)
    z_scale = 900.0 / max(float(np.ptp(matrix)), 0.02)

    def project(row: int, column: int) -> tuple[int, int]:
        return (
            230 + column * 150 + row * 55,
            540 - row * 75 - int((matrix[row, column] - matrix.min()) * z_scale),
        )

    for row in range(5):
        for column in range(4):
            cv2.line(
                canvas,
                project(row, column),
                project(row, column + 1),
                (30, 80, 220),
                3,
                cv2.LINE_AA,
            )
    for column in range(5):
        for row in range(4):
            cv2.line(
                canvas,
                project(row, column),
                project(row + 1, column),
                (20, 160, 90),
                3,
                cv2.LINE_AA,
            )
    cv2.putText(
        canvas,
        "5x5 Eddy bed planeness (height exaggerated)",
        (90, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (20, 20, 20),
        2,
        cv2.LINE_AA,
    )
    wire_path = plots_dir / "bed_planeness_3d.png"
    cv2.imwrite(str(wire_path), canvas)
    return [str(heatmap_path), str(wire_path)]


def write_plots(job_dir: Path, analysis: dict[str, Any]) -> list[str]:
    plots_dir = job_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    output: list[str] = []
    hysteresis = analysis["hysteresis"]
    path = plots_dir / "hysteresis.png"
    _plot_series(
        path,
        title="Directional Eddy height at equal commanded Z",
        xlabel="commanded Z (mm)",
        ylabel="Eddy height (mm)",
        series=[
            (
                "descending",
                [item["commanded_z_mm"] for item in hysteresis],
                [item["descending"]["median"] for item in hysteresis],
                (30, 90, 220),
            ),
            (
                "ascending",
                [item["commanded_z_mm"] for item in hysteresis],
                [item["ascending"]["median"] for item in hysteresis],
                (30, 170, 80),
            ),
        ],
    )
    output.append(str(path))

    pairs = analysis["small_step_response"]["pairs"]
    path = plots_dir / "small_step_response.png"
    _plot_series(
        path,
        title="Small reversal response",
        xlabel="requested delta (mm)",
        ylabel="observed delta (mm)",
        series=[
            (
                "observed",
                [pair["requested_delta_mm"] for pair in pairs],
                [pair["measured_delta_mm"] for pair in pairs],
                (170, 60, 210),
            )
        ],
    )
    output.append(str(path))

    cycles = analysis["gantry_plane"]["cycles"]
    path = plots_dir / "gantry_plane.png"
    _plot_series(
        path,
        title="Cycle-to-cycle left-to-right gantry plane",
        xlabel="home cycle",
        ylabel="left-to-right span (mm)",
        series=[
            (
                "plane span",
                [item["cycle"] for item in cycles],
                [item["left_to_right_span_mm"] for item in cycles],
                (220, 110, 25),
            )
        ],
    )
    output.append(str(path))

    path = plots_dir / "homing_repeatability.png"
    _plot_series(
        path,
        title="Ten-home repeatability by sensor X",
        xlabel="home cycle",
        ylabel="Eddy height (mm)",
        series=[
            (
                f"sensor X={gcode_float(sensor_x)}",
                [item["cycle"] for item in cycles],
                [item["values_mm"][position_index] for item in cycles],
                color,
            )
            for position_index, (sensor_x, color) in enumerate(
                zip(
                    SENSOR_X_POSITIONS_MM,
                    ((30, 90, 220), (20, 160, 90), (220, 110, 25)),
                )
            )
        ],
    )
    output.append(str(path))

    temperatures = analysis["temperatures"]
    path = plots_dir / "temperature.png"
    temperature_series = []
    for key, name, color in (
        ("coil_c", "coil", (30, 80, 220)),
        ("mcu_c", "Eddy MCU", (20, 160, 90)),
    ):
        points = [
            (float(item["seq"]), float(item[key]))
            for item in temperatures
            if item.get(key) is not None
        ]
        if points:
            temperature_series.append(
                (
                    name,
                    [point[0] for point in points],
                    [point[1] for point in points],
                    color,
                )
            )
    _plot_series(
        path,
        title="Eddy temperatures during diagnostic",
        xlabel="sample sequence",
        ylabel="temperature (C)",
        series=temperature_series,
    )
    output.append(str(path))
    output.extend(_write_mesh_plots(plots_dir, analysis))
    return output


def write_report(job_dir: Path, analysis: dict[str, Any]) -> Path:
    center = next(
        (
            item
            for item in analysis["homing_repeatability"]["positions"]
            if math.isclose(item["sensor_x_mm"], 117.5)
        ),
        {},
    )
    bed = analysis["bed_planeness"]
    lines = [
        "# Cold Eddy Z Diagnostic",
        "",
        f"- Job: `{analysis['job_id']}`",
        f"- Data quality: `{'complete' if analysis['ok'] else 'failed'}`",
        "- Mechanical verdict: `baseline_only` (no pass/fail threshold applied)",
        "- Physical dual-Z endstops remained authoritative.",
        "- Temporary bed mesh was not saved and was cleared after capture.",
        "",
        "## Summary",
        "",
        f"- Stationary raw-height standard deviation: "
        f"{analysis['stationary_noise']['raw_calibrated_height_mm']['stddev']:.6f} mm",
        f"- Maximum absolute directional hysteresis: "
        f"{analysis['maximum_absolute_hysteresis_mm']:.6f} mm",
        f"- Smallest reliably resolved reversal: "
        f"{analysis['small_step_response']['smallest_reliably_resolved_reversal_mm']} mm",
        f"- Center homing range: {center.get('range')} mm",
        f"- Bed peak-to-valley: {bed.get('peak_to_valley_mm')} mm",
        f"- Residual warp after plane removal: "
        f"{bed.get('residual_peak_to_valley_mm')} mm",
        "",
        "## Data-quality failures",
        "",
    ]
    lines.extend(
        [f"- {failure}" for failure in analysis["hard_failures"]] or ["- None"]
    )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `manifest.json` and `eddy_sweep/manifest.json`",
            "- `eddy_sweep/sweep.gcode` and raw sample sidecars",
            "- `samples.csv`, `samples.json`, and `analysis.json`",
            "- `plots/`",
            "",
        ]
    )
    path = job_dir / "report.md"
    atomic_write_text(path, "\n".join(lines))
    return path


def mesh_status(base_url: str) -> dict[str, Any]:
    return (
        moonraker_get(base_url, "/printer/objects/query?bed_mesh")["result"][
            "status"
        ].get("bed_mesh")
        or {}
    )


def run_job(args: argparse.Namespace) -> dict[str, Any]:
    from vision_nozzle_align import (
        refresh_vision_ui_best_effort,
        stage_and_run_eddy_sweep,
    )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_id = f"eddy_z_diagnostic_{timestamp}_{sanitize_name(args.name)}"
    job_dir = Path(args.job_root) / job_id
    if job_dir.exists():
        raise RuntimeError(f"diagnostic job directory already exists: {job_dir}")
    job_dir.mkdir(parents=True)
    state = {
        "schema_version": SCHEMA_VERSION,
        "job_id": job_id,
        "kind": JOB_KIND,
        "state": "prepared",
        "created_at_utc": utc_now(),
        "updated_at_utc": utc_now(),
        "frame_count": 0,
    }
    atomic_write_json(job_dir / "state.json", state)
    append_event(job_dir, "prepared", {"state": "prepared"})
    mesh_cleared = False
    try:
        schedule = build_sample_schedule(
            bed_center_x=args.bed_center_x,
            bed_center_y=args.bed_center_y,
            x_offset=args.nozzle_to_coil_x,
            y_offset=args.nozzle_to_coil_y,
            nozzle_to_coil_z=args.nozzle_to_coil_z,
        )
        status = query_status(args.moonraker_url)
        preflight_result = preflight(
            status,
            expected_fingerprint=args.active_config_fingerprint,
            schedule=schedule,
        )
        sweep_manifest = build_sweep_manifest(
            job_id=job_id,
            schedule=schedule,
            active_config_fingerprint=preflight_result["active_config_fingerprint"],
            x_offset=args.nozzle_to_coil_x,
            y_offset=args.nozzle_to_coil_y,
            nozzle_to_coil_z=args.nozzle_to_coil_z,
        )
        sweep_manifest, gcode = finalize_sweep_hashes(sweep_manifest)
        outer_manifest = {
            "schema_version": SCHEMA_VERSION,
            "job_id": job_id,
            "kind": JOB_KIND,
            "camera": "nozzle_cam",
            "profile": "none",
            "created_at_utc": utc_now(),
            "manifest_hash": HASH_PLACEHOLDER,
            "gcode_file": "eddy_sweep/sweep.gcode",
            "gcode_hash": sweep_manifest["gcode_hash"],
            "frame_count": 0,
            "frames": [],
            "measurement_parameters": {
                "measurement": MEASUREMENT,
                "cold_only": True,
                "report_only": True,
            },
            "sweep_manifest_hash": sweep_manifest["manifest_hash"],
            "preflight": preflight_result,
        }
        outer_manifest["manifest_hash"] = sha256_prefixed(
            canonical_json_bytes(outer_manifest)
        )
        atomic_write_json(job_dir / "manifest.json", outer_manifest)
        state.update(
            {
                "state": "acquiring",
                "updated_at_utc": utc_now(),
                "manifest_hash": outer_manifest["manifest_hash"],
            }
        )
        atomic_write_json(job_dir / "state.json", state)
        acquisition = stage_and_run_eddy_sweep(
            args=args,
            job_dir=job_dir,
            manifest=sweep_manifest,
            gcode=gcode,
        )
        captured_mesh = mesh_status(args.moonraker_url)
        run_gcode(args.moonraker_url, "BED_MESH_CLEAR", timeout=30)
        mesh_cleared = True
        append_event(
            job_dir,
            "bed_mesh_cleanup",
            {"cleared": True, "save_config_called": False},
        )
        state.update({"state": "analysing", "updated_at_utc": utc_now()})
        atomic_write_json(job_dir / "state.json", state)
        records = load_sample_records(Path(acquisition["sweep_dir"]), sweep_manifest)
        analysis = analyze_records(records, sweep_manifest, captured_mesh)
        write_samples(job_dir, records)
        plot_paths = write_plots(job_dir, analysis)
        report_path = write_report(job_dir, analysis)
        analysis["artifacts"] = {
            "report": str(report_path),
            "analysis_json": str(job_dir / "analysis.json"),
            "samples_csv": str(job_dir / "samples.csv"),
            "samples_json": str(job_dir / "samples.json"),
            "plots": plot_paths,
            "raw_directory": str(job_dir / "eddy_sweep" / "raw"),
        }
        atomic_write_json(job_dir / "analysis.json", analysis)
        atomic_write_json(job_dir / "facts.json", analysis)
        atomic_write_json(
            job_dir / "result.json",
            {
                "ok": analysis["ok"],
                "job_id": job_id,
                "job_dir": str(job_dir),
                "analysis_path": str(job_dir / "analysis.json"),
                "report_path": str(report_path),
            },
        )
        state.update(
            {
                "state": "completed" if analysis["ok"] else "failed",
                "reason": (
                    "complete cold baseline"
                    if analysis["ok"]
                    else "; ".join(analysis["hard_failures"])
                ),
                "updated_at_utc": utc_now(),
                "completed_at_utc": utc_now(),
                "committed_frame_count": 0,
            }
        )
        atomic_write_json(job_dir / "state.json", state)
        append_event(job_dir, state["state"], {"state": state["state"]})
        return {
            "ok": analysis["ok"],
            "job_id": job_id,
            "job_dir": str(job_dir),
            "analysis_path": str(job_dir / "analysis.json"),
            "report_path": str(report_path),
        }
    except Exception as exc:
        state.update(
            {
                "state": "failed",
                "reason": str(exc),
                "updated_at_utc": utc_now(),
                "failed_at_utc": utc_now(),
            }
        )
        atomic_write_json(job_dir / "state.json", state)
        append_event(job_dir, "failed", {"state": "failed", "error": str(exc)})
        raise
    finally:
        try:
            if not mesh_cleared:
                try:
                    run_gcode(args.moonraker_url, "BED_MESH_CLEAR", timeout=30)
                    mesh_cleared = True
                finally:
                    append_event(
                        job_dir,
                        "bed_mesh_cleanup",
                        {"cleared": mesh_cleared, "save_config_called": False},
                    )
        finally:
            refresh_vision_ui_best_effort(Path(args.job_root))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-job", action="store_true")
    parser.add_argument("--name", default="post_rebuild_baseline")
    parser.add_argument("--bed-center-x", type=float, default=117.5)
    parser.add_argument("--bed-center-y", type=float, default=117.5)
    parser.add_argument("--nozzle-to-coil-x", type=float, default=-8.18)
    parser.add_argument("--nozzle-to-coil-y", type=float, default=9.0)
    parser.add_argument("--nozzle-to-coil-z", type=float, default=2.5)
    parser.add_argument("--active-config-fingerprint", required=True)
    parser.add_argument("--moonraker-url", default=DEFAULT_MOONRAKER_URL)
    parser.add_argument("--job-root", type=Path, default=DEFAULT_JOB_ROOT)
    parser.add_argument("--virtual-sd-root", type=Path, default=DEFAULT_VIRTUAL_SD_ROOT)
    parser.add_argument("--virtual-sd-subdir", default=DEFAULT_VIRTUAL_SD_SUBDIR)
    parser.add_argument("--eddy-monitor-timeout", type=float, default=1800.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.run_job:
        raise SystemExit("--run-job is required")
    try:
        result = run_job(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
