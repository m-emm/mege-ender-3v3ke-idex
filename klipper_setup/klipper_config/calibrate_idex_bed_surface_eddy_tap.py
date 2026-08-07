#!/usr/bin/env python3
"""Run the guarded IDEX Z Iteration 1 physical/sensor calibration.

The script deliberately keeps measured mesh data out of the repository.  Eddy
drive current and its height/frequency table are the only measured values that
become canonical configuration.  The known-good tap threshold is read from
``calib.yaml`` and is never discovered or overwritten by this workflow.  The mesh made
by ``BED_MESH_CALIBRATE`` remains session-local evidence.

The frequency/height calibration is guarded by a three-tap center reference
before and after the sweep. Each guard records Klipper's complete
``GET_POSITION`` response, including raw integer MCU step counts, so a change
in the perceived tap plane can be distinguished from a change in the
coordinate model.

Most of this module is intentionally dependency-light.  The pure calculation
helpers are useful in tests and make it possible to run ``--dry-run`` without
opening a printer connection or changing a file.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import logging
import math
import os
import re
import shutil
import shlex
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlencode

import yaml


_logger = logging.getLogger(__name__)


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
CALIB_PATH = SCRIPT_DIR / "calib.yaml"
TEMPLATE_PATH = SCRIPT_DIR / "printer.cfg.template"
CONFIG_PATH = SCRIPT_DIR / "printer.cfg"
GENERATOR_PATH = SCRIPT_DIR / "generate_printer_cfg.py"
DEPLOY_PATH = SCRIPT_DIR / "update_menderpi.sh"
RUN_ROOT = REPO_ROOT / "runs" / "idex_z_iteration_1"
DEFAULT_HOST = os.environ.get("MENDERPI_HOST", "pi@menderpi.local")
EXPECTED_KLIPPER_COMMIT = "ca8230d505b7ba7fd225bfa6ed9655bc4520e805"

STEP_CHOICES = (
    "preflight",
    "bootstrap-tap",
    "update-endstops",
    "center-verify",
    "tap-baseline",
    "drive-current",
    "eddy-frequency",
    "curve-doctor",
    "mesh",
    "run",
    "resume",
)

REFERENCE_X = 150.0
REFERENCE_Y = 150.0
CONTACT_Z = 0.0
TAP_SUCCESS_COUNT = 7
TAP_MAX_ATTEMPTS = 10
TAP_MAX_SPAN = 0.030
TAP_MAX_STDDEV = 0.010
CENTER_MEAN_TOLERANCE = 0.030
CENTER_SPAN_TOLERANCE = 0.030
EDDY_REFERENCE_TAP_COUNT = 3
EDDY_REFERENCE_TAP_MAX_ATTEMPTS = 3
EDDY_REFERENCE_PROBE_COUNT = 5
EDDY_REFERENCE_MEAN_TOLERANCE = 0.050
EDDY_REFERENCE_SPAN_TOLERANCE = 0.040
EDDY_REFERENCE_XY_TOLERANCE = 0.020
EDDY_REFERENCE_RESIDUAL_TOLERANCE = 0.020
CURVE_DOCTOR_HEIGHTS = (0.5, 1.0, 2.0, 3.0, 4.0)
CURVE_DOCTOR_BATCH_COUNT = 3
CURVE_DOCTOR_DURATION = 0.5
CURVE_DOCTOR_ASCENT_APPROACH_CLEARANCE = 0.1
CURVE_DOCTOR_ABSOLUTE_TOLERANCE = 0.020
CURVE_DOCTOR_SPAN_TOLERANCE = 0.020
MESH_CENTER_TOLERANCE = 0.005
MESH_POINT_TOLERANCE = 0.030
MESH_RMS_TOLERANCE = 0.015
MESH_STATIONARY_SCAN_HEIGHT = 2.0
MESH_STATIONARY_SCAN_COUNT = 3
MESH_STATIONARY_SCAN_DURATION = 0.5
MESH_DIAGNOSTIC_TAP_COUNT = 1
MESH_DIAGNOSTIC_XY_SPEED = 100.0
MESH_ACTIVE_TRANSFORM_TOLERANCE = 0.030
MESH_MANUAL_PROFILE = "saved_mesh"
ARMING_PHRASE = "CALIBRATE IDEX Z ITERATION 1"
WORKFLOW_VERSION = 2


class CalibrationError(RuntimeError):
    """A calibration gate failed and the run must stop."""


class Phase(str, Enum):
    PREFLIGHT = "I1.0"
    BOOTSTRAP_TAP = "I1.1"
    ENDSTOPS = "I1.2"
    CENTER_VERIFY = "I1.3"
    DRIVE_CURRENT = "I1.4"
    EDDY_CALIBRATION = "I1.5"
    CURVE_DOCTOR = "I1.5D"
    MESH_SCAN = "I1.6"
    MESH_VERIFY = "I1.7"
    FINISH = "I1.8"


@dataclass(frozen=True)
class Pose:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class AxisBounds:
    minimum: float
    maximum: float

    def contains(self, value: float, margin: float = 0.0) -> bool:
        return self.minimum + margin <= value <= self.maximum - margin


@dataclass(frozen=True)
class TapSummary:
    successful: tuple[float, ...]
    rejected_attempts: int
    mean: float
    median: float
    standard_deviation: float
    span: float


@dataclass
class RunState:
    run_id: str
    phase: str
    workflow_version: int = WORKFLOW_VERSION
    committed_phase: str | None = None
    source_hashes: dict[str, str] | None = None
    evidence: dict[str, Any] | None = None


@dataclass(frozen=True)
class MeshPoint:
    x: float
    y: float


def parse_eddy_curve(curve: str) -> tuple[tuple[float, float], ...]:
    """Parse and validate Klipper's ``height:frequency`` calibration table."""

    try:
        pairs = tuple(
            tuple(float(value) for value in item.strip().split(":", 1))
            for item in re.split(r"[,\n]+", curve)
            if item.strip()
        )
    except (AttributeError, ValueError) as exc:
        raise CalibrationError(
            "Eddy curve contains an invalid height:frequency pair"
        ) from exc
    if len(pairs) < 9 or any(len(pair) != 2 for pair in pairs):
        raise CalibrationError(
            "Eddy curve must contain at least nine height:frequency pairs"
        )
    if not all(
        math.isfinite(height) and math.isfinite(frequency)
        for height, frequency in pairs
    ):
        raise CalibrationError("Eddy curve contains a non-finite pair")
    if any(
        next_height <= height or next_frequency >= frequency
        for (height, frequency), (next_height, next_frequency) in zip(pairs, pairs[1:])
    ):
        raise CalibrationError(
            "Eddy curve heights must increase while frequencies strictly decrease"
        )
    return pairs


def eddy_curve_height_at_frequency(
    curve: Sequence[tuple[float, float]], frequency: float
) -> float:
    """Evaluate Klipper's piecewise-linear frequency-to-height conversion."""

    if not math.isfinite(frequency):
        raise CalibrationError("Eddy anchor frequency is non-finite")
    frequencies = [-item[1] for item in curve]
    index = bisect.bisect_left(frequencies, -frequency)
    if index == 0 or index >= len(curve):
        raise CalibrationError(
            "Eddy anchor frequency is outside the active calibration range"
        )
    low_height, low_frequency = curve[index - 1]
    high_height, high_frequency = curve[index]
    fraction = (frequency - low_frequency) / (high_frequency - low_frequency)
    return low_height + fraction * (high_height - low_height)


def eddy_curve_frequency_at_height(
    curve: Sequence[tuple[float, float]], height: float
) -> float:
    """Evaluate the inverse of Klipper's piecewise-linear calibration table."""

    if not math.isfinite(height):
        raise CalibrationError("Eddy anchor height is non-finite")
    heights = [item[0] for item in curve]
    index = bisect.bisect_left(heights, height)
    if index == 0 or index >= len(curve):
        raise CalibrationError(
            "Eddy anchor height is outside the active calibration range"
        )
    low_height, low_frequency = curve[index - 1]
    high_height, high_frequency = curve[index]
    fraction = (height - low_height) / (high_height - low_height)
    return low_frequency + fraction * (high_frequency - low_frequency)


def _interpolate_curve_doctor_height(
    anchors: Sequence[tuple[float, float]], inferred_height: float
) -> float:
    """Map an old inferred height to the Tap-anchored physical height."""

    inferred = [item[0] for item in anchors]
    index = bisect.bisect_right(inferred, inferred_height)
    if index == 0:
        return inferred_height + (anchors[0][1] - anchors[0][0])
    if index == len(anchors):
        return inferred_height + (anchors[-1][1] - anchors[-1][0])
    low_inferred, low_target = anchors[index - 1]
    high_inferred, high_target = anchors[index]
    fraction = (inferred_height - low_inferred) / (high_inferred - low_inferred)
    return low_target + fraction * (high_target - low_target)


def format_eddy_curve(curve: Sequence[tuple[float, float]]) -> str:
    """Render a readable multiline Klipper curve without losing precision."""

    rendered = [f"{height:.6f}:{frequency:.3f}" for height, frequency in curve]
    lines = [
        ",".join(rendered[index : index + 3]) for index in range(0, len(rendered), 3)
    ]
    return "\n".join(
        line + ("," if index < len(lines) - 1 else "")
        for index, line in enumerate(lines)
    )


def doctor_eddy_curve(
    source_curve: str, anchors: Sequence[Mapping[str, float]]
) -> tuple[str, list[dict[str, float]]]:
    """Remap a dense curve through measured Tap-anchored frequency points."""

    source = parse_eddy_curve(source_curve)
    derived: list[dict[str, float]] = []
    for anchor in anchors:
        target_height = float(anchor["target_height"])
        frequency = float(anchor["raw_frequency_hz"])
        if not math.isfinite(target_height) or target_height <= 0.0:
            raise CalibrationError("curve-doctor target height must be positive")
        derived.append(
            {
                "target_height": target_height,
                "raw_frequency_hz": frequency,
                "inferred_height": eddy_curve_height_at_frequency(source, frequency),
            }
        )
    derived.sort(key=lambda item: item["inferred_height"])
    if any(
        next_anchor["inferred_height"] <= anchor["inferred_height"]
        or next_anchor["target_height"] <= anchor["target_height"]
        for anchor, next_anchor in zip(derived, derived[1:])
    ):
        raise CalibrationError("curve-doctor anchors cross or are not monotonic")
    mapping = [
        (anchor["inferred_height"], anchor["target_height"]) for anchor in derived
    ]
    candidate = [
        (_interpolate_curve_doctor_height(mapping, height), frequency)
        for height, frequency in source
    ]
    for anchor in derived:
        frequency = anchor["raw_frequency_hz"]
        matching = next(
            (
                index
                for index, (_, source_frequency) in enumerate(candidate)
                if abs(source_frequency - frequency) <= 1e-6
            ),
            None,
        )
        if matching is None:
            candidate.append((anchor["target_height"], frequency))
        else:
            candidate[matching] = (anchor["target_height"], frequency)
    candidate.sort(key=lambda item: item[0])
    if any(
        next_height <= height or next_frequency >= frequency
        for (height, frequency), (next_height, next_frequency) in zip(
            candidate, candidate[1:]
        )
    ):
        raise CalibrationError("curve-doctor candidate is not strictly monotonic")
    rendered = format_eddy_curve(candidate)
    parsed_candidate = parse_eddy_curve(rendered)
    for anchor in derived:
        corrected = eddy_curve_height_at_frequency(
            parsed_candidate, anchor["raw_frequency_hz"]
        )
        if abs(corrected - anchor["target_height"]) > 1e-6:
            raise CalibrationError("curve-doctor candidate does not preserve an anchor")
        anchor["candidate_height"] = corrected
    return rendered, derived


def utc_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ")


def tap_contact_and_post_retract_z(status: Mapping[str, Any]) -> tuple[float, float]:
    """Return Klipper's tap contact Z and the later toolhead Z separately."""

    probe = status.get("probe")
    toolhead = status.get("toolhead")
    if not isinstance(probe, Mapping) or not isinstance(toolhead, Mapping):
        raise CalibrationError("tap status lacks probe or toolhead data")
    last_probe_position = probe.get("last_probe_position")
    toolhead_position = toolhead.get("position")
    if not isinstance(last_probe_position, Sequence) or len(last_probe_position) < 3:
        raise CalibrationError("tap status lacks probe.last_probe_position")
    if not isinstance(toolhead_position, Sequence) or len(toolhead_position) < 3:
        raise CalibrationError("tap status lacks toolhead.position")
    contact_z = float(last_probe_position[2])
    post_retract_z = float(toolhead_position[2])
    if not math.isfinite(contact_z) or not math.isfinite(post_retract_z):
        raise CalibrationError("tap status contains a non-finite Z position")
    return contact_z, post_retract_z


def probe_result_z_from_status(status: Mapping[str, Any]) -> float:
    """Return Klipper's canonical result from the last regular PROBE."""

    probe = status.get("probe")
    if not isinstance(probe, Mapping):
        raise CalibrationError("probe status is missing after Eddy PROBE")
    last_probe_position = probe.get("last_probe_position")
    if not isinstance(last_probe_position, Sequence) or len(last_probe_position) < 3:
        raise CalibrationError(
            "probe status lacks probe.last_probe_position after Eddy PROBE"
        )
    probe_z = float(last_probe_position[2])
    if not math.isfinite(probe_z):
        raise CalibrationError("Eddy PROBE result contains a non-finite Z position")
    return probe_z


def probe_result_from_status(status: Mapping[str, Any]) -> dict[str, float]:
    """Return the complete canonical regular-probe result."""

    probe = status.get("probe")
    if not isinstance(probe, Mapping):
        raise CalibrationError("probe status is missing after Eddy PROBE")
    last_probe_position = probe.get("last_probe_position")
    if not isinstance(last_probe_position, Sequence) or len(last_probe_position) < 3:
        raise CalibrationError(
            "probe status lacks probe.last_probe_position after Eddy PROBE"
        )
    values = {
        "x": float(last_probe_position[0]),
        "y": float(last_probe_position[1]),
        "z": float(last_probe_position[2]),
    }
    if not all(math.isfinite(value) for value in values.values()):
        raise CalibrationError("Eddy PROBE result contains a non-finite position")
    return values


def summarize_probe_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize regular Eddy probe results without changing their datum."""

    if not results:
        raise CalibrationError("no regular Eddy probe samples were acquired")
    z_values = tuple(float(result["z"]) for result in results)
    return {
        "count": len(z_values),
        "mean": statistics.fmean(z_values),
        "median": statistics.median(z_values),
        "min": min(z_values),
        "max": max(z_values),
        "span": max(z_values) - min(z_values),
        "stddev": statistics.pstdev(z_values),
    }


POSITION_LABELS = (
    "gcode homing",
    "gcode base",
    "kinematic",
    "toolhead",
    "stepper",
    "gcode",
    "mcu",
)


def _parse_position_values(payload: str, *, integer: bool) -> dict[str, int | float]:
    values: dict[str, int | float] = {}
    for token in payload.split():
        try:
            name, raw_value = token.rsplit(":", 1)
            values[name] = int(raw_value) if integer else float(raw_value)
        except (ValueError, IndexError) as exc:
            raise CalibrationError(f"invalid GET_POSITION value {token!r}") from exc
    return values


def parse_get_position_message(message: str) -> dict[str, Any]:
    """Parse Klipper's complete GET_POSITION response for run evidence."""

    parsed: dict[str, Any] = {"raw": message.strip()}
    for line in message.splitlines():
        line = line.strip()
        if line.startswith("//"):
            line = line[2:].strip()
        for label in POSITION_LABELS:
            prefix = f"{label}:"
            if line.startswith(prefix):
                parsed[label.replace(" ", "_")] = _parse_position_values(
                    line[len(prefix) :].strip(), integer=label == "mcu"
                )
                break
    required = {
        "mcu",
        "stepper",
        "kinematic",
        "toolhead",
        "gcode",
        "gcode_base",
        "gcode_homing",
    }
    missing = sorted(required.difference(parsed))
    if missing:
        raise CalibrationError(
            "GET_POSITION response is incomplete; missing " + ", ".join(missing)
        )
    return parsed


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize_taps(
    successful: Sequence[float],
    *,
    attempts: int | None = None,
) -> TapSummary:
    """Return robust tap statistics and account for rejected attempts."""

    values = tuple(float(value) for value in successful)
    if not values:
        raise CalibrationError("no successful tap samples were acquired")
    attempts = len(values) if attempts is None else int(attempts)
    if attempts < len(values):
        raise ValueError("attempt count cannot be smaller than successes")
    return TapSummary(
        successful=values,
        rejected_attempts=attempts - len(values),
        mean=statistics.fmean(values),
        median=statistics.median(values),
        standard_deviation=statistics.pstdev(values),
        span=max(values) - min(values),
    )


def require_tap_acceptance(
    summary: TapSummary,
    *,
    required_successes: int = TAP_SUCCESS_COUNT,
    max_rejected: int = TAP_MAX_ATTEMPTS - TAP_SUCCESS_COUNT,
    max_span: float = TAP_MAX_SPAN,
    max_standard_deviation: float = TAP_MAX_STDDEV,
) -> None:
    if len(summary.successful) != required_successes:
        raise CalibrationError(
            f"expected {required_successes} successful taps, got "
            f"{len(summary.successful)}"
        )
    if summary.rejected_attempts > max_rejected:
        raise CalibrationError(
            f"rejected tap attempts {summary.rejected_attempts} exceed "
            f"maximum {max_rejected}"
        )
    if summary.span > max_span:
        raise CalibrationError(
            f"tap span {summary.span:.6f} mm exceeds {max_span:.6f} mm"
        )
    if summary.standard_deviation > max_standard_deviation:
        raise CalibrationError(
            "tap standard deviation "
            f"{summary.standard_deviation:.6f} mm exceeds "
            f"{max_standard_deviation:.6f} mm"
        )


def common_endstop_update(
    t0_old: float,
    t1_old: float,
    tap_contact_z: float,
) -> tuple[float, float, float]:
    """Translate both endstops so the observed T0 contact becomes Z=0."""

    delta = CONTACT_Z - float(tap_contact_z)
    return t0_old + delta, t1_old + delta, delta


def assert_relative_alignment(
    old_t0: float,
    old_t1: float,
    new_t0: float,
    new_t1: float,
    *,
    expected_delta: float | None = None,
    tolerance: float = 1e-9,
) -> None:
    old_delta = float(old_t0) - float(old_t1)
    new_delta = float(new_t0) - float(new_t1)
    if not math.isclose(old_delta, new_delta, abs_tol=tolerance):
        raise CalibrationError(
            f"common endstop update changed T0/T1 relative Z: "
            f"{old_delta:.9f} -> {new_delta:.9f}"
        )
    if expected_delta is not None and not math.isclose(
        old_delta, float(expected_delta), abs_tol=tolerance
    ):
        raise CalibrationError(
            f"stored vision T1/T0 Z delta {expected_delta!r} does not match "
            f"current source delta {old_delta:.9f}"
        )


def validate_vision_relative_provenance(
    calibration: Mapping[str, Any],
    *,
    tolerance: float | None = None,
) -> float:
    provenance = calibration.get("vision_relative_alignment")
    if not isinstance(provenance, Mapping):
        raise CalibrationError(
            "calib.yaml is missing vision_relative_alignment provenance"
        )
    try:
        expected = float(provenance["t0_minus_t1_z"])
        declared_tolerance = float(provenance["tolerance_mm"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CalibrationError(
            "vision_relative_alignment must declare t0_minus_t1_z and " "tolerance_mm"
        ) from exc
    if declared_tolerance <= 0:
        raise CalibrationError("vision relative-alignment tolerance must be positive")
    if tolerance is not None and declared_tolerance > tolerance:
        raise CalibrationError(
            "vision relative-alignment provenance tolerance is broader than "
            "the workflow acceptance tolerance"
        )
    return expected


def coil_over_target_pose(
    target: Pose,
    nozzle_to_coil: Pose,
) -> Pose:
    """Return the nozzle pose that places the Eddy coil at ``target``."""

    return Pose(
        x=target.x - nozzle_to_coil.x,
        y=target.y - nozzle_to_coil.y,
        z=target.z - nozzle_to_coil.z,
    )


def validate_pose(
    pose: Pose,
    *,
    x: AxisBounds,
    y: AxisBounds,
    z: AxisBounds,
    label: str = "pose",
) -> None:
    if not x.contains(pose.x) or not y.contains(pose.y) or not z.contains(pose.z):
        raise CalibrationError(
            f"{label} is outside motion limits: "
            f"({pose.x:.3f}, {pose.y:.3f}, {pose.z:.3f})"
        )


def mesh_corrected_contact_z(raw_tap_z: float, mesh_correction_z: float) -> float:
    """Apply the bed-mesh inverse to a raw kinematic tap result."""

    return float(raw_tap_z) - float(mesh_correction_z)


def mesh_correction_at(
    matrix: Sequence[Sequence[float]],
    *,
    mesh_min: MeshPoint,
    mesh_max: MeshPoint,
    point: MeshPoint,
) -> float:
    """Bilinearly interpolate a Klipper mesh matrix at a validation point."""

    if not matrix or not matrix[0] or len({len(row) for row in matrix}) != 1:
        raise CalibrationError("active mesh matrix is empty or ragged")
    rows = len(matrix)
    columns = len(matrix[0])
    if (
        not mesh_min.x <= point.x <= mesh_max.x
        or not mesh_min.y <= point.y <= mesh_max.y
    ):
        raise CalibrationError(f"mesh lookup point is outside the active mesh: {point}")
    x_fraction = (point.x - mesh_min.x) / (mesh_max.x - mesh_min.x)
    y_fraction = (point.y - mesh_min.y) / (mesh_max.y - mesh_min.y)
    x_position = x_fraction * (columns - 1)
    y_position = y_fraction * (rows - 1)
    x0 = min(int(math.floor(x_position)), columns - 1)
    x1 = min(x0 + 1, columns - 1)
    y0 = min(int(math.floor(y_position)), rows - 1)
    y1 = min(y0 + 1, rows - 1)
    dx = x_position - x0
    dy = y_position - y0
    lower = float(matrix[y0][x0]) * (1.0 - dx) + float(matrix[y0][x1]) * dx
    upper = float(matrix[y1][x0]) * (1.0 - dx) + float(matrix[y1][x1]) * dx
    return lower * (1.0 - dy) + upper * dy


def mesh_tap_acceptance(
    tap_samples: Mapping[MeshPoint, Sequence[float]],
    mesh_corrections: Mapping[MeshPoint, float],
    *,
    point_tolerance: float = MESH_POINT_TOLERANCE,
    rms_tolerance: float = MESH_RMS_TOLERANCE,
) -> dict[str, Any]:
    """Calculate and gate raw-tap minus mesh-correction results."""

    corrected: dict[str, dict[str, float]] = {}
    residuals: list[float] = []
    for point, samples in tap_samples.items():
        if point not in mesh_corrections:
            raise CalibrationError(f"missing mesh correction for tap point {point}")
        summary = summarize_taps(samples, attempts=len(samples))
        if summary.rejected_attempts or summary.span > 0.020:
            raise CalibrationError(f"tap repeatability failed at {point}")
        corrected_z = mesh_corrected_contact_z(summary.mean, mesh_corrections[point])
        residuals.append(corrected_z)
        corrected[f"{point.x:.3f},{point.y:.3f}"] = {
            "raw_mean": summary.mean,
            "mesh_correction": float(mesh_corrections[point]),
            "mesh_corrected_mean": corrected_z,
            "span": summary.span,
        }
    if not residuals:
        raise CalibrationError("no tap-safe mesh validation points were measured")
    rms = math.sqrt(statistics.fmean(value * value for value in residuals))
    if any(abs(value) > point_tolerance for value in residuals):
        raise CalibrationError(
            f"mesh-corrected tap exceeds point tolerance: {residuals}"
        )
    if rms > rms_tolerance:
        raise CalibrationError(
            f"mesh-corrected tap RMS {rms:.6f} exceeds {rms_tolerance:.6f}"
        )
    return {"points": corrected, "rms": rms, "max_abs": max(map(abs, residuals))}


def derive_safe_tap_grid(
    *,
    nozzle_x: AxisBounds,
    nozzle_y: AxisBounds,
    mesh_x: AxisBounds,
    mesh_y: AxisBounds,
    coil_offset_x: float,
    coil_offset_y: float,
    margin: float = 5.0,
    count: int = 3,
) -> tuple[MeshPoint, ...]:
    """Derive a grid in the intersection safe for both nozzle and coil taps."""

    if count < 2:
        raise ValueError("tap validation grid needs at least two points per axis")
    x_min = max(nozzle_x.minimum, mesh_x.minimum, mesh_x.minimum - coil_offset_x)
    x_max = min(nozzle_x.maximum, mesh_x.maximum, mesh_x.maximum - coil_offset_x)
    y_min = max(nozzle_y.minimum, mesh_y.minimum, mesh_y.minimum - coil_offset_y)
    y_max = min(nozzle_y.maximum, mesh_y.maximum, mesh_y.maximum - coil_offset_y)
    x_min += margin
    x_max -= margin
    y_min += margin
    y_max -= margin
    if x_min >= x_max or y_min >= y_max:
        raise CalibrationError("no safe nozzle/coil overlap exists for tap validation")
    xs = [x_min + (x_max - x_min) * i / (count - 1) for i in range(count)]
    ys = [y_min + (y_max - y_min) * i / (count - 1) for i in range(count)]
    return tuple(MeshPoint(x, y) for y in ys for x in xs)


def extract_pending_value(
    pending: Mapping[str, Any] | Sequence[Any],
    section: str,
    option: str,
) -> Any:
    """Extract a Klipper ``save_config_pending_items`` value.

    Klipper has represented this status as both a section mapping and a list
    of records across versions; accepting both keeps the runner pinned to the
    printer's declared Klipper revision without hard-coding one JSON shape.
    """

    section_names = {section, f"[{section}]"}

    def unwrap(value: Any) -> Any:
        if isinstance(value, Mapping) and "value" in value:
            return value["value"]
        return value

    if isinstance(pending, Mapping):
        for name in section_names:
            candidate = pending.get(name)
            if isinstance(candidate, Mapping) and option in candidate:
                return unwrap(candidate[option])
        for candidate in pending.values():
            try:
                return extract_pending_value(candidate, section, option)
            except KeyError:
                pass
    elif isinstance(pending, Sequence) and not isinstance(pending, (str, bytes)):
        for item in pending:
            if not isinstance(item, Mapping):
                continue
            item_section = item.get("section", item.get("name"))
            item_option = item.get("option", item.get("key"))
            if item_section in section_names and item_option == option:
                return unwrap(item.get("value"))
            try:
                return extract_pending_value(item, section, option)
            except KeyError:
                pass
    raise KeyError(f"pending config value not found: [{section}] {option}")


def pending_sections(pending: Any, *, _root: bool = True) -> set[str]:
    """Collect section names from a pending-config object for gate checks."""

    found: set[str] = set()
    if isinstance(pending, Mapping):
        for key, value in pending.items():
            if isinstance(key, str) and (
                key.startswith("[")
                or key in {"bed_mesh", "probe_eddy_current btt_eddy"}
                or (_root and isinstance(value, Mapping))
            ):
                found.add(key.strip("[]"))
            found.update(pending_sections(value, _root=False))
    elif isinstance(pending, Sequence) and not isinstance(pending, (str, bytes)):
        for item in pending:
            if isinstance(item, Mapping):
                section = item.get("section", item.get("name"))
                if isinstance(section, str):
                    found.add(section.strip("[]"))
                found.update(pending_sections(item, _root=False))
    return found


def require_only_transient_mesh_pending(pending: Any) -> None:
    sections = pending_sections(pending)
    unexpected = sections - {
        "bed_mesh default",
        f"bed_mesh {MESH_MANUAL_PROFILE}",
        "bed_mesh",
    }
    if unexpected:
        raise CalibrationError(
            "unexpected pending config after mesh scan: "
            + ", ".join(sorted(unexpected))
        )


def reject_mesh_data_in_canonical(data: Mapping[str, Any]) -> None:
    forbidden = {"mesh_matrix", "probed_matrix", "mesh_points", "bed_mesh"}
    present = forbidden.intersection(data)
    if present:
        raise CalibrationError(
            "measured mesh data must remain runtime-only; found "
            + ", ".join(sorted(present))
        )


def _set_scalar_at_path(text: str, path: Sequence[str], value: str) -> str:
    lines = text.splitlines(keepends=True)
    stack: list[tuple[int, str]] = []
    target = tuple(path)
    found = False
    for index, line in enumerate(lines):
        match = re.match(r"^(?P<indent>\s*)(?P<key>[^#:\n]+):(?P<rest>.*)$", line)
        if not match or not match.group("key").strip():
            continue
        indent = len(match.group("indent"))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key = match.group("key").strip()
        current = tuple(item[1] for item in stack) + (key,)
        if current == target:
            newline = "\n" if line.endswith("\n") else ""
            lines[index] = f"{match.group('indent')}{key}: {value}{newline}"
            found = True
            break
        stack.append((indent, key))
    if not found:
        raise CalibrationError(
            "cannot update missing calibration field " + ".".join(path)
        )
    return "".join(lines)


def _set_block_scalar_at_path(text: str, path: Sequence[str], value: str) -> str:
    lines = text.splitlines(keepends=True)
    stack: list[tuple[int, str]] = []
    target = tuple(path)
    for index, line in enumerate(lines):
        match = re.match(r"^(?P<indent>\s*)(?P<key>[^#:\n]+):(?P<rest>.*)$", line)
        if not match:
            continue
        indent = len(match.group("indent"))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key = match.group("key").strip()
        current = tuple(item[1] for item in stack) + (key,)
        if current != target:
            stack.append((indent, key))
            continue
        if "|" not in match.group("rest"):
            raise CalibrationError("calibration table must use a YAML block scalar")
        end = index + 1
        while end < len(lines):
            continuation = lines[end]
            if (
                continuation.strip()
                and len(continuation) - len(continuation.lstrip()) <= indent
            ):
                break
            end += 1
        rendered = value.strip()
        replacement = [f"{match.group('indent')}{key}: |\n"]
        replacement.extend(
            f"{' ' * (indent + 4)}{part.strip()}\n" for part in rendered.splitlines()
        )
        lines[index:end] = replacement
        return "".join(lines)
    raise CalibrationError("cannot update missing calibration table " + ".".join(path))


def atomic_update_calibration(path: Path, updates: Mapping[Sequence[str], Any]) -> None:
    """Update only known scalar/table fields while preserving comments."""

    original = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(original)
    if not isinstance(parsed, Mapping):
        raise CalibrationError("calib.yaml must contain a mapping")
    reject_mesh_data_in_canonical(parsed)
    updated = original
    for path_parts, value in updates.items():
        path_parts = tuple(path_parts)
        if path_parts[-1] == "calibrate":
            updated = _set_block_scalar_at_path(updated, path_parts, str(value))
        else:
            if value is None:
                rendered = "null"
            elif isinstance(value, bool):
                rendered = "true" if value else "false"
            elif isinstance(value, int):
                rendered = str(value)
            else:
                rendered = f"{float(value):.3f}"
            updated = _set_scalar_at_path(updated, path_parts, rendered)
    updated_data = yaml.safe_load(updated)
    if not isinstance(updated_data, Mapping):
        raise CalibrationError("updated calib.yaml is not a mapping")
    reject_mesh_data_in_canonical(updated_data)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        shutil.copystat(path, temp_name)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


class MoonrakerClient:
    """Small Moonraker-over-SSH client with injectable transport for tests."""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        *,
        request_fn: (
            Callable[[str, Mapping[str, Any] | None, float], dict[str, Any]] | None
        ) = None,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.host = host
        self.request_fn = request_fn
        self.runner = runner

    def request(
        self,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        if self.request_fn is not None:
            return self.request_fn(path, payload, timeout)
        query = ""
        if payload is not None and path.startswith("/printer/objects/query"):
            query = "?" + urlencode(payload)
        request_script = f"""
import json
import urllib.request
url = {('http://127.0.0.1:7125' + path + query)!r}
payload = {dict(payload or {})!r}
if payload and not url.endswith("query") and "?" not in url:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={{"Content-Type": "application/json"}})
else:
    request = urllib.request.Request(url)
with urllib.request.urlopen(request, timeout={float(timeout)!r}) as response:
    print(response.read().decode())
"""
        result = self.runner(
            ["ssh", self.host, "python3", "-"],
            input=request_script,
            text=True,
            capture_output=True,
            check=True,
            timeout=timeout + 10.0,
        )
        body = json.loads(result.stdout)
        return body.get("result", body)

    def status(self, objects: Iterable[str] | None = None) -> dict[str, Any]:
        object_names = list(objects or ["webhooks", "configfile"])
        query = urlencode([(name, "") for name in object_names])
        result = self.request(f"/printer/objects/query?{query}")
        if "result" in result and isinstance(result["result"], Mapping):
            result = result["result"]
        return result.get("status", result)

    def gcode(self, script: str, *, timeout: float = 60.0) -> dict[str, Any]:
        return self.request(
            "/printer/gcode/script", {"script": script}, timeout=timeout
        )

    def gcode_store(self, *, count: int = 50) -> list[dict[str, Any]]:
        result = self.request(f"/server/gcode_store?count={int(count)}")
        if not isinstance(result, Mapping):
            raise CalibrationError("Moonraker gcode store returned a non-mapping")
        entries = result.get("gcode_store", [])
        if not isinstance(entries, list):
            raise CalibrationError("Moonraker gcode store returned invalid entries")
        return [entry for entry in entries if isinstance(entry, dict)]

    def restart(self, *, timeout: float = 30.0) -> dict[str, Any]:
        return self.request(
            "/machine/services/restart", {"service": "klipper"}, timeout=timeout
        )

    def emergency_stop(self) -> dict[str, Any]:
        return self.gcode("M112", timeout=10.0)


class ArtifactStore:
    def __init__(self, root: Path, run_id: str, *, enabled: bool = True) -> None:
        self.path = root / run_id
        self.enabled = enabled
        if enabled:
            self.path.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, value: Any) -> None:
        if not self.enabled:
            return
        destination = self.path / name
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        temporary.write_text(
            json.dumps(value, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)

    def copy(self, source: Path, name: str) -> None:
        if self.enabled:
            shutil.copy2(source, self.path / name)


def _config_hashes() -> dict[str, str]:
    return {
        "calib.yaml": sha256_file(CALIB_PATH),
        "printer.cfg.template": sha256_file(TEMPLATE_PATH),
        "printer.cfg": sha256_file(CONFIG_PATH),
    }


def _load_raw_calibration() -> dict[str, Any]:
    value = yaml.safe_load(CALIB_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CalibrationError("calib.yaml must contain a mapping")
    reject_mesh_data_in_canonical(value)
    return value


def configured_tap_threshold(calibration: Mapping[str, Any]) -> int:
    """Return the required known-good tap threshold from calib.yaml."""

    try:
        value = calibration["eddy_relative_calibration"]["klipper"]["tap_threshold"]
    except (KeyError, TypeError) as exc:
        raise CalibrationError(
            "calib.yaml must define eddy_relative_calibration.klipper.tap_threshold"
        ) from exc
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CalibrationError("calib.yaml tap_threshold must be a positive integer")
    return value


def _run_local(
    command: Sequence[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    rendered = shlex.join(str(part) for part in command)
    _logger.info("local command started: %s", rendered)
    started = time.monotonic()
    try:
        result = subprocess.run(
            command, cwd=REPO_ROOT, text=True, capture_output=True, check=check
        )
    except subprocess.CalledProcessError as exc:
        _logger.error(
            "local command failed after %.1fs: %s (exit=%s)",
            time.monotonic() - started,
            rendered,
            exc.returncode,
        )
        if exc.stdout:
            _logger.error("local stdout: %s", exc.stdout[-1000:].strip())
        if exc.stderr:
            _logger.error("local stderr: %s", exc.stderr[-1000:].strip())
        raise
    _logger.info(
        "local command finished in %.1fs: %s",
        time.monotonic() - started,
        rendered,
    )
    return result


class Iteration1Runner:
    def __init__(
        self,
        *,
        client: MoonrakerClient,
        store: ArtifactStore,
        dry_run: bool = False,
        assume_yes: bool = False,
        sleep: Callable[[float], None] = time.sleep,
        snapshot: bool = True,
    ) -> None:
        self.client = client
        self.store = store
        self.dry_run = dry_run
        self.assume_yes = assume_yes
        self.sleep = sleep
        self.state = RunState(run_id=store.path.name, phase=Phase.PREFLIGHT.value)
        self.raw_calibration = _load_raw_calibration()
        self.tap_threshold = configured_tap_threshold(self.raw_calibration)
        _logger.info(
            "calibration runner ready: run_dir=%s dry_run=%s host=%s "
            "reference=(%.3f, %.3f) tap_threshold=%d",
            self.store.path,
            self.dry_run,
            getattr(self.client, "host", "<injected>"),
            REFERENCE_X,
            REFERENCE_Y,
            self.tap_threshold,
        )
        if snapshot:
            self.store.copy(CALIB_PATH, "calib.yaml.before")
            self.store.copy(CONFIG_PATH, "printer.cfg.before")

    def checkpoint(
        self, phase: Phase, *, committed: bool = False, **evidence: Any
    ) -> None:
        self.state.workflow_version = WORKFLOW_VERSION
        self.state.phase = phase.value
        if committed:
            self.state.committed_phase = phase.value
        self.state.source_hashes = _config_hashes()
        self.state.evidence = {**(self.state.evidence or {}), **evidence}
        self.store.write_json("state.json", asdict(self.state))
        _logger.info(
            "checkpoint: phase=%s committed=%s",
            phase.value,
            committed,
        )

    def confirm(self) -> None:
        if self.dry_run or self.assume_yes:
            return
        print(
            f"This moves and probes the printer through IDEX Z Iteration 1. "
            f"Type {ARMING_PHRASE!r} to continue: ",
            end="",
            flush=True,
        )
        if input().strip() != ARMING_PHRASE:
            raise CalibrationError("arming confirmation did not match")

    def preflight(
        self, *, checkpoint_state: bool = True, sync_printer: bool = False
    ) -> dict[str, Any]:
        _logger.info("preflight: validating local configuration and live printer")
        if not CONFIG_PATH.exists():
            raise CalibrationError("generated printer.cfg is missing")
        _run_local([sys.executable, str(GENERATOR_PATH), "--check"])
        status_objects = [
            "webhooks",
            "print_stats",
            "virtual_sdcard",
            "configfile",
            "toolhead",
            "gcode_move",
            "heater_bed",
            "extruder",
            "extruder1",
            "temperature_probe btt_eddy",
        ]
        if sync_printer:
            current_status = self.client.status(status_objects)
            self._validate_status_preflight(current_status)
            _logger.info("preflight: deploying managed diagnostic support files")
            _run_local([str(DEPLOY_PATH)])
        _run_local([str(DEPLOY_PATH), "--check"])
        expected_delta = validate_vision_relative_provenance(self.raw_calibration)
        tools = self.raw_calibration.get("tools", {})
        t0 = tools.get("t0", {})
        t1 = tools.get("t1", {})
        assert_relative_alignment(
            float(t0["z_endstop"]),
            float(t1["z_endstop"]),
            float(t0["z_endstop"]),
            float(t1["z_endstop"]),
            expected_delta=expected_delta,
            tolerance=float(
                self.raw_calibration["vision_relative_alignment"]["tolerance_mm"]
            ),
        )
        status = self.client.status(status_objects)
        self._validate_status_preflight(status)
        _logger.info(
            "preflight passed: klippy=%s print_state=%s homed_axes=%s",
            status.get("webhooks", {}).get("state"),
            status.get("print_stats", {}).get("state"),
            status.get("toolhead", {}).get("homed_axes"),
        )
        if checkpoint_state:
            self.checkpoint(Phase.PREFLIGHT, committed=True, status=status)
        return status

    def _validate_status_preflight(self, status: Mapping[str, Any]) -> None:
        webhooks = status.get("webhooks", {})
        if webhooks.get("state") != "ready":
            raise CalibrationError(f"Klippy is not ready: {webhooks!r}")
        print_state = status.get("print_stats", {}).get("state")
        if print_state not in {None, "standby", "complete", "cancelled", "error"}:
            raise CalibrationError(
                f"printer is not idle: print_stats.state={print_state!r}"
            )
        if status.get("virtual_sdcard", {}).get("is_active", False):
            raise CalibrationError("virtual SD print is active")
        configfile = status.get("configfile", {})
        if configfile.get("save_config_pending") not in {None, False}:
            raise CalibrationError("a SAVE_CONFIG change is already pending")
        pending = configfile.get("save_config_pending_items", {})
        if pending:
            raise CalibrationError(
                "pending configuration items must be empty before calibration"
            )
        for name in ("heater_bed", "extruder", "extruder1"):
            temperature = status.get(name, {}).get("temperature")
            if temperature is not None and float(temperature) > (
                40.0 if name == "heater_bed" else 50.0
            ):
                raise CalibrationError(
                    f"{name} is too hot for the cold baseline: {temperature}"
                )
        eddy_temperature = status.get("temperature_probe btt_eddy", {}).get(
            "temperature"
        )
        if eddy_temperature is not None and not math.isfinite(float(eddy_temperature)):
            raise CalibrationError("Eddy temperature is not finite")
        homing_origin = status.get("gcode_move", {}).get("homing_origin", [0, 0, 0])
        if any(abs(float(value)) > 1e-6 for value in homing_origin[:3]):
            raise CalibrationError(
                f"visible G-code offset is not zero: {homing_origin}"
            )

    def _gcode(
        self,
        script: str,
        *,
        timeout: float = 60.0,
        emergency_stop_on_error: bool = False,
    ) -> dict[str, Any]:
        summary = " | ".join(
            line.strip() for line in script.splitlines() if line.strip()
        )
        _logger.info("G-code started: %s (timeout=%.0fs)", summary, timeout)
        if self.dry_run:
            self.store.write_json(
                "dry_run_command.json",
                {"script": script, "timeout": timeout},
            )
            _logger.info("G-code skipped in dry-run: %s", summary)
            return {}
        try:
            previous_responses = {
                self._gcode_store_marker(entry)
                for entry in self.client.gcode_store(count=100)
            }
        except Exception as exc:
            previous_responses = set()
            _logger.warning(
                "could not snapshot G-code responses before command %s: %s",
                summary,
                exc,
            )
        try:
            result = self.client.gcode(script, timeout=timeout)
        except Exception as exc:
            if emergency_stop_on_error:
                try:
                    self.client.emergency_stop()
                except Exception:
                    pass
            raise CalibrationError(
                f"G-code failed{'; emergency stop sent' if emergency_stop_on_error else ''}: {exc}"
            ) from exc
        responses = self._new_gcode_responses(previous_responses, summary)
        self.store.write_json(
            f"command-{int(time.time() * 1000)}.json",
            {"script": script, "result": result, "gcode_responses": responses},
        )
        _logger.info("G-code finished: %s", summary)
        for response in responses:
            _logger.info("G-code response: %s", response)
        return result

    @staticmethod
    def _gcode_store_marker(entry: Mapping[str, Any]) -> tuple[float, str, str]:
        return (
            float(entry.get("time", 0.0)),
            str(entry.get("type", "")),
            str(entry.get("message", "")),
        )

    def _new_gcode_responses(
        self, previous: set[tuple[float, str, str]], summary: str
    ) -> list[str]:
        """Return Klipper response lines emitted during one submitted command.

        Moonraker's script endpoint only returns ``ok``.  ``respond_info`` and
        normal Klipper diagnostics are delivered separately through the bounded
        gcode store used by Mainsail's console.
        """

        try:
            entries = self.client.gcode_store(count=100)
        except Exception as exc:
            _logger.warning(
                "could not read G-code responses after command %s: %s", summary, exc
            )
            return []
        return [
            marker[2]
            for entry in entries
            if (marker := self._gcode_store_marker(entry)) not in previous
            and marker[1] == "response"
        ]

    def _home_clean_frame(self) -> None:
        _logger.info("homing clean frame: heaters off, mesh/offsets clear, G28, T0")
        self._gcode(
            "M140 S0\nM104 T0 S0\nM104 T1 S0\n"
            "BED_MESH_CLEAR\nSET_GCODE_OFFSET X=0 Y=0 Z=0 MOVE=0\n"
            "G28\nT0"
        )

    def collect_taps(
        self,
        *,
        x: float,
        y: float,
        count: int,
        max_attempts: int,
        tap_threshold: int,
        allow_empty: bool = False,
    ) -> tuple[TapSummary | None, list[dict[str, Any]]]:
        _logger.info(
            "tap series started: point=(%.3f, %.3f) target=%d max_attempts=%d "
            "threshold=%d",
            x,
            y,
            count,
            max_attempts,
            tap_threshold,
        )
        samples: list[float] = []
        attempts: list[dict[str, Any]] = []
        for attempt in range(max_attempts):
            if len(samples) >= count:
                break
            try:
                _logger.info(
                    "tap attempt %d/%d started (successful=%d/%d)",
                    attempt + 1,
                    max_attempts,
                    len(samples),
                    count,
                )
                self._gcode(
                    f"G90\nG1 X{x:.3f} Y{y:.3f} Z5 F1200\n"
                    f"PROBE METHOD=tap TAP_THRESHOLD={tap_threshold}"
                )
                if self.dry_run:
                    value = 0.0
                    post_retract_z = 0.0
                else:
                    status = self.client.status(["probe", "toolhead"])
                    value, post_retract_z = tap_contact_and_post_retract_z(status)
                    _logger.info(
                        "tap %d: contact_z=%.6f post_retract_toolhead_z=%.6f "
                        "retract_delta=%.6f",
                        attempt + 1,
                        value,
                        post_retract_z,
                        post_retract_z - value,
                    )
                samples.append(value)
                _logger.info(
                    "tap attempt %d accepted: contact_z=%.6f post_retract_z=%.6f",
                    attempt + 1,
                    value,
                    post_retract_z,
                )
                attempts.append(
                    {
                        "attempt": attempt + 1,
                        "ok": True,
                        "z": value,
                        "contact_z": value,
                        "post_retract_toolhead_z": post_retract_z,
                        "retract_delta": post_retract_z - value,
                    }
                )
            except Exception as exc:
                _logger.warning("tap attempt %d rejected: %s", attempt + 1, exc)
                attempts.append(
                    {"attempt": attempt + 1, "ok": False, "error": str(exc)}
                )
                if not self.dry_run and attempt + 1 >= max_attempts:
                    break
        if not samples and allow_empty:
            _logger.warning(
                "tap series finished without a successful sample: point=(%.3f, %.3f) "
                "rejected=%d",
                x,
                y,
                len(attempts),
            )
            return None, attempts
        summary = summarize_taps(samples, attempts=len(attempts))
        _logger.info(
            "tap series finished: successful=%d rejected=%d mean=%.6f "
            "median=%.6f span=%.6f stddev=%.6f",
            len(summary.successful),
            summary.rejected_attempts,
            summary.mean,
            summary.median,
            summary.span,
            summary.standard_deviation,
        )
        return summary, attempts

    @staticmethod
    def require_center_tap(summary: TapSummary, *, count: int) -> None:
        if len(summary.successful) != count:
            raise CalibrationError(
                f"expected {count} successful center taps, got "
                f"{len(summary.successful)}"
            )
        if summary.rejected_attempts:
            raise CalibrationError("center reference tap rejected a sample")
        if abs(summary.mean) > EDDY_REFERENCE_MEAN_TOLERANCE:
            raise CalibrationError(
                "center reference tap is not native Z=0: "
                f"mean={summary.mean:.6f} allowed={EDDY_REFERENCE_MEAN_TOLERANCE:.6f}"
            )
        if summary.span > EDDY_REFERENCE_SPAN_TOLERANCE:
            raise CalibrationError(
                "center reference tap is not repeatable: "
                f"span={summary.span:.6f} allowed={EDDY_REFERENCE_SPAN_TOLERANCE:.6f}"
            )

    def capture_full_position(self, label: str) -> dict[str, Any]:
        """Capture GET_POSITION, including raw integer MCU step counts."""

        if self.dry_run:
            _logger.info("GET_POSITION skipped in dry-run: label=%s", label)
            return {"label": label, "dry_run": True}
        _logger.info("capturing GET_POSITION: label=%s", label)
        self._gcode("GET_POSITION")
        for entry in reversed(self.client.gcode_store()):
            message = str(entry.get("message", ""))
            if "mcu:" not in message or "stepper:" not in message:
                continue
            position = parse_get_position_message(message)
            position["label"] = label
            _logger.info(
                "GET_POSITION captured: label=%s mcu_stepper_z=%s mcu_stepper_z1=%s "
                "toolhead_z=%.6f",
                label,
                position["mcu"].get("stepper_z"),
                position["mcu"].get("stepper_z1"),
                position["toolhead"].get("Z", float("nan")),
            )
            return position
        raise CalibrationError("GET_POSITION response was not found in gcode store")

    def eddy_reference_sequence(self, label: str) -> dict[str, Any]:
        """Home, prove center tap Z=0, and record the median-Z position."""

        _logger.info("Eddy reference sequence started: %s", label)
        self._home_clean_frame()
        after_home = self.capture_full_position(f"{label}.after_home")
        summary, attempts = self.collect_taps(
            x=REFERENCE_X,
            y=REFERENCE_Y,
            count=EDDY_REFERENCE_TAP_COUNT,
            max_attempts=EDDY_REFERENCE_TAP_MAX_ATTEMPTS,
            tap_threshold=self.tap_threshold,
        )
        summary_data = asdict(summary)
        try:
            self.require_center_tap(summary, count=EDDY_REFERENCE_TAP_COUNT)
        except CalibrationError as exc:
            self.store.write_json(
                f"{label}-reference.json",
                {
                    "after_home": after_home,
                    "taps": attempts,
                    "summary": summary_data,
                    "error": str(exc),
                },
            )
            raise
        _logger.info(
            "Eddy reference gate passed: label=%s mean=%.6f span=%.6f median=%.6f",
            label,
            summary.mean,
            summary.span,
            summary.median,
        )
        self._gcode(
            f"G90\nG1 X{REFERENCE_X:.3f} Y{REFERENCE_Y:.3f} "
            f"Z{summary.median:.6f} F1200"
        )
        after_median_move = self.capture_full_position(f"{label}.after_median_tap_move")
        evidence = {
            "after_home": after_home,
            "taps": attempts,
            "summary": summary_data,
            "median_tap_z": summary.median,
            "after_median_move": after_median_move,
        }
        self.store.write_json(f"{label}-reference.json", evidence)
        _logger.info("Eddy reference sequence finished: %s", label)
        return evidence

    def bootstrap_tap(self) -> TapSummary:
        _logger.info("I1.1 bootstrap tap started")
        self._home_clean_frame()
        summary, attempts = self.collect_taps(
            x=REFERENCE_X,
            y=REFERENCE_Y,
            count=TAP_SUCCESS_COUNT,
            max_attempts=TAP_MAX_ATTEMPTS,
            tap_threshold=self.tap_threshold,
        )
        require_tap_acceptance(summary)
        self.checkpoint(
            Phase.BOOTSTRAP_TAP,
            committed=True,
            bootstrap_taps=attempts,
            bootstrap_summary=asdict(summary),
        )
        _logger.info(
            "I1.1 bootstrap tap passed: median=%.6f mean=%.6f span=%.6f",
            summary.median,
            summary.mean,
            summary.span,
        )
        return summary

    def update_endstops(self, tap_center_z: float) -> tuple[float, float]:
        _logger.info("I1.2 updating both endstops from tap_center_z=%.6f", tap_center_z)
        tools = self.raw_calibration["tools"]
        t0_old = float(tools["t0"]["z_endstop"])
        t1_old = float(tools["t1"]["z_endstop"])
        expected = validate_vision_relative_provenance(self.raw_calibration)
        t0_new, t1_new, delta = common_endstop_update(t0_old, t1_old, tap_center_z)
        assert_relative_alignment(
            t0_old, t1_old, t0_new, t1_new, expected_delta=expected, tolerance=1e-9
        )
        if self.dry_run:
            self.checkpoint(
                Phase.ENDSTOPS,
                committed=False,
                proposed_endstops={"t0": t0_new, "t1": t1_new, "delta": delta},
            )
            return t0_new, t1_new
        _logger.info(
            "I1.2 deploying endstops: t0 %.6f -> %.6f, t1 %.6f -> %.6f, delta=%.6f",
            t0_old,
            t0_new,
            t1_old,
            t1_new,
            delta,
        )
        atomic_update_calibration(
            CALIB_PATH,
            {
                ("tools", "t0", "z_endstop"): t0_new,
                ("tools", "t1", "z_endstop"): t1_new,
            },
        )
        _run_local([sys.executable, str(GENERATOR_PATH)])
        _run_local([str(DEPLOY_PATH)])
        _run_local([str(DEPLOY_PATH), "--check"])
        self.checkpoint(
            Phase.ENDSTOPS,
            committed=True,
            endstops={"t0": t0_new, "t1": t1_new, "delta": delta},
        )
        _logger.info("I1.2 endstop update deployed and committed")
        return t0_new, t1_new

    def verify_center(self, phase: Phase = Phase.CENTER_VERIFY) -> TapSummary:
        _logger.info("%s center verification started", phase.value)
        self._home_clean_frame()
        summary, attempts = self.collect_taps(
            x=REFERENCE_X,
            y=REFERENCE_Y,
            count=5,
            max_attempts=5,
            tap_threshold=self.tap_threshold,
        )
        if (
            abs(summary.mean) > CENTER_MEAN_TOLERANCE
            or summary.span > CENTER_SPAN_TOLERANCE
        ):
            raise CalibrationError(
                f"center tap is not native Z=0: mean={summary.mean:.6f}, span={summary.span:.6f} allowed mean={CENTER_MEAN_TOLERANCE:.6f}, span={CENTER_SPAN_TOLERANCE:.6f}"
            )
        if summary.rejected_attempts:
            raise CalibrationError("center verification rejected a tap")
        self.checkpoint(
            phase,
            committed=True,
            center_verification=attempts,
            center_summary=asdict(summary),
        )
        _logger.info(
            "%s center verification passed: mean=%.6f span=%.6f",
            phase.value,
            summary.mean,
            summary.span,
        )
        return summary

    def capture_pending(self, section: str, option: str) -> Any:
        status = self.client.status(["configfile"])
        pending = status.get("configfile", {}).get("save_config_pending_items", {})
        try:
            return extract_pending_value(pending, section, option)
        except KeyError as exc:
            raise CalibrationError(str(exc)) from exc

    def deploy_value(
        self,
        updates: Mapping[Sequence[str], Any],
        phase: Phase,
        *,
        checkpoint: bool = True,
        **evidence: Any,
    ) -> None:
        _logger.info(
            "deploying canonical update for phase=%s: %s",
            phase.value,
            ", ".join(".".join(path) for path in updates),
        )
        if self.dry_run:
            if checkpoint:
                self.checkpoint(phase, committed=False, **evidence)
            return
        atomic_update_calibration(CALIB_PATH, updates)
        _run_local([sys.executable, str(GENERATOR_PATH)])
        _run_local([str(DEPLOY_PATH)])
        _run_local([str(DEPLOY_PATH), "--check"])
        if checkpoint:
            self.checkpoint(phase, committed=True, **evidence)
        _logger.info("canonical update deployed: phase=%s", phase.value)

    def calibrate_drive_current(self, *, clean_frame: bool = True) -> None:
        _logger.info("I1.4 Eddy drive-current calibration started")
        eddy = self.raw_calibration["eddy_relative_calibration"]["nozzle_to_coil"]
        coil_pose = coil_over_target_pose(
            Pose(REFERENCE_X, REFERENCE_Y, 20.0), Pose(**eddy)
        )
        if clean_frame:
            self._home_clean_frame()
            self._gcode(
                f"G1 X{coil_pose.x:.3f} Y{coil_pose.y:.3f} Z{coil_pose.z:.3f} F1200"
            )
        else:
            _logger.info(
                "I1.4 reusing the verified center frame; lifting before coil motion"
            )
            self._gcode(
                f"G90\nG1 Z20.000 F1200\n"
                f"G1 X{coil_pose.x:.3f} Y{coil_pose.y:.3f} F1200\n"
                f"G1 Z{coil_pose.z:.3f} F1200"
            )
        self._gcode("LDC_CALIBRATE_DRIVE_CURRENT CHIP=btt_eddy", timeout=120.0)
        if self.dry_run:
            self.checkpoint(
                Phase.DRIVE_CURRENT, committed=False, coil_pose=asdict(coil_pose)
            )
            return
        current = int(
            self.capture_pending("probe_eddy_current btt_eddy", "reg_drive_current")
        )
        if not 0 <= current <= 31:
            raise CalibrationError(
                f"proposed Eddy drive current is outside 0..31: {current}"
            )
        _logger.info("I1.4 proposed Eddy drive current: %d", current)
        self.deploy_value(
            {("eddy_relative_calibration", "klipper", "reg_drive_current"): current},
            Phase.DRIVE_CURRENT,
            drive_current=current,
            coil_pose=asdict(coil_pose),
        )
        _logger.info("I1.4 Eddy drive-current calibration finished")

    @staticmethod
    def _coordinate_component(value: Any, index: int, name: str) -> float:
        if isinstance(value, Mapping):
            return float(value[name])
        axis_value = getattr(value, name, None)
        if axis_value is not None:
            return float(axis_value)
        return float(value[index])

    def _eddy_reference_nozzle_pose(self, nozzle_z: float = 5.0) -> Pose:
        eddy = self.raw_calibration["eddy_relative_calibration"]["nozzle_to_coil"]
        offset = Pose(**eddy)
        return coil_over_target_pose(
            Pose(REFERENCE_X, REFERENCE_Y, nozzle_z + offset.z), offset
        )

    def _validate_eddy_reference_pose(self, pose: Pose) -> dict[str, Any]:
        if self.dry_run:
            return {"dry_run": True}
        status = self.client.status(["toolhead"])
        toolhead = status.get("toolhead", {})
        axis_minimum = toolhead.get("axis_minimum")
        axis_maximum = toolhead.get("axis_maximum")
        if axis_minimum is None or axis_maximum is None:
            raise CalibrationError("toolhead motion limits are unavailable")
        bounds = {
            "x_min": self._coordinate_component(axis_minimum, 0, "x"),
            "x_max": self._coordinate_component(axis_maximum, 0, "x"),
            "y_min": self._coordinate_component(axis_minimum, 1, "y"),
            "y_max": self._coordinate_component(axis_maximum, 1, "y"),
        }
        if not (
            bounds["x_min"] <= pose.x <= bounds["x_max"]
            and bounds["y_min"] <= pose.y <= bounds["y_max"]
        ):
            raise CalibrationError(
                "Eddy reference nozzle pose is outside motion limits: "
                f"pose=({pose.x:.3f}, {pose.y:.3f}), bounds={bounds}"
            )
        return bounds

    def _capture_regular_eddy_probe(
        self,
        *,
        pose: Pose,
        probe_speed: float | None = None,
        label: str,
    ) -> dict[str, Any]:
        command = (
            f"G90\nG1 X{pose.x:.3f} Y{pose.y:.3f} Z{pose.z:.3f} F1200\n"
            "PROBE METHOD=probe SAMPLES=1"
        )
        if probe_speed is not None:
            command += f" PROBE_SPEED={probe_speed:.3f}"
        self._gcode(command)
        status = self.client.status(["probe", "toolhead", "temperature_probe btt_eddy"])
        result = probe_result_from_status(status)
        if (
            abs(result["x"] - REFERENCE_X) > EDDY_REFERENCE_XY_TOLERANCE
            or abs(result["y"] - REFERENCE_Y) > EDDY_REFERENCE_XY_TOLERANCE
        ):
            raise CalibrationError(
                "regular Eddy PROBE physical point mismatch: "
                f"expected=({REFERENCE_X:.3f}, {REFERENCE_Y:.3f}), "
                f"got=({result['x']:.6f}, {result['y']:.6f})"
            )
        position = self.capture_full_position(label)
        toolhead = status.get("toolhead", {})
        temperature = status.get("temperature_probe btt_eddy", {}).get("temperature")
        evidence = {
            "label": label,
            "probe_speed": probe_speed,
            "probe_result": result,
            "toolhead_z": float(toolhead.get("position", [0.0, 0.0, math.nan])[2]),
            "temperature": None if temperature is None else float(temperature),
            "position": position,
        }
        _logger.info(
            "Eddy PROBE %s: bed=(%.6f, %.6f) z=%.6f toolhead_z=%.6f "
            "speed=%s temperature=%s mcu_stepper_z=%s mcu_stepper_z1=%s",
            label,
            result["x"],
            result["y"],
            result["z"],
            evidence["toolhead_z"],
            probe_speed if probe_speed is not None else "default",
            evidence["temperature"],
            position["mcu"].get("stepper_z"),
            position["mcu"].get("stepper_z1"),
        )
        return evidence

    def _capture_stationary_scan(
        self, *, pose: Pose, nozzle_z: float, label: str
    ) -> dict[str, Any]:
        """Capture a stationary scan at a commanded nozzle Z height."""

        command = (
            f"G90\nG1 X{pose.x:.3f} Y{pose.y:.3f} Z{nozzle_z:.3f} F1200\n"
            "PROBE METHOD=scan SAMPLES=1"
        )
        self._gcode(command)
        status = self.client.status(["probe", "toolhead", "temperature_probe btt_eddy"])
        result = probe_result_from_status(status)
        position = self.capture_full_position(label)
        return {
            "label": label,
            "commanded_nozzle_z": nozzle_z,
            "probe_result": result,
            "toolhead_z": float(status["toolhead"]["position"][2]),
            "temperature": status.get("temperature_probe btt_eddy", {}).get(
                "temperature"
            ),
            "position": position,
        }

    def run_eddy_probe_diagnostics(self) -> dict[str, Any]:
        """Collect speed and stationary-height evidence after a failed gate."""

        pose = self._eddy_reference_nozzle_pose()
        self._validate_eddy_reference_pose(pose)
        regular: list[dict[str, Any]] = []
        for speed in (1.0, 2.0, 5.0):
            try:
                regular.append(
                    self._capture_regular_eddy_probe(
                        pose=pose,
                        probe_speed=speed,
                        label=f"diagnostic.regular.speed_{speed:g}",
                    )
                )
            except Exception as exc:
                regular.append({"probe_speed": speed, "error": str(exc)})
                _logger.warning(
                    "regular Eddy diagnostic failed at %.1f mm/s: %s", speed, exc
                )
        stationary: list[dict[str, Any]] = []
        for nozzle_z in (3.0, 2.0, 1.0, 0.5):
            try:
                stationary.append(
                    self._capture_stationary_scan(
                        pose=pose,
                        nozzle_z=nozzle_z,
                        label=f"diagnostic.stationary.nozzle_z_{nozzle_z:g}",
                    )
                )
            except Exception as exc:
                stationary.append({"commanded_nozzle_z": nozzle_z, "error": str(exc)})
                _logger.warning(
                    "stationary Eddy diagnostic failed at nozzle Z=%.3f: %s",
                    nozzle_z,
                    exc,
                )
        evidence = {
            "reference": {"x": REFERENCE_X, "y": REFERENCE_Y},
            "nozzle_pose": asdict(pose),
            "regular": regular,
            "stationary": stationary,
        }
        self.store.write_json("eddy-probe-diagnostics.json", evidence)
        return evidence

    def verify_eddy_probe_reference(
        self, tap_summary: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        """Require repeated regular Eddy PROBEs to agree with tap Z=0."""

        _logger.info(
            "I1.5 regular Eddy PROBE reference check started for physical point "
            "(%.3f, %.3f)",
            REFERENCE_X,
            REFERENCE_Y,
        )
        pose = self._eddy_reference_nozzle_pose()
        bounds = self._validate_eddy_reference_pose(pose)
        if self.dry_run:
            results = [
                {
                    "x": REFERENCE_X,
                    "y": REFERENCE_Y,
                    "z": 0.0,
                    "probe_speed": None,
                    "toolhead_z": pose.z,
                    "temperature": None,
                    "position": {"dry_run": True},
                }
                for _ in range(EDDY_REFERENCE_PROBE_COUNT)
            ]
        else:
            results = [
                self._capture_regular_eddy_probe(
                    pose=pose,
                    label=f"post_eddy.reference_probe_{index + 1}",
                )
                for index in range(EDDY_REFERENCE_PROBE_COUNT)
            ]
        probe_positions = [
            result["probe_result"] if "probe_result" in result else result
            for result in results
        ]
        summary = summarize_probe_results(probe_positions)
        tap_median = None if tap_summary is None else float(tap_summary["median"])
        residual = None if tap_median is None else summary["median"] - tap_median
        evidence = {
            "x": REFERENCE_X,
            "y": REFERENCE_Y,
            "nozzle_pose": asdict(pose),
            "motion_bounds": bounds,
            "probe_results": results,
            "probe_summary": summary,
            "tap_median": tap_median,
            "median_residual": residual,
            "mean_tolerance": EDDY_REFERENCE_MEAN_TOLERANCE,
            "span_tolerance": EDDY_REFERENCE_SPAN_TOLERANCE,
            "residual_tolerance": EDDY_REFERENCE_RESIDUAL_TOLERANCE,
        }
        self.store.write_json("post-eddy-probe-reference.json", evidence)
        _logger.info(
            "I1.5 regular Eddy PROBE reference: mean=%.6f median=%.6f "
            "span=%.6f tap_median=%s residual=%s",
            summary["mean"],
            summary["median"],
            summary["span"],
            tap_median,
            residual,
        )
        if abs(summary["mean"]) > EDDY_REFERENCE_MEAN_TOLERANCE:
            raise CalibrationError(
                "regular Eddy PROBE is not native Z=0 after frequency calibration: "
                f"mean={summary['mean']:.6f}, "
                f"tolerance={EDDY_REFERENCE_MEAN_TOLERANCE:.6f}"
            )
        if summary["span"] > EDDY_REFERENCE_SPAN_TOLERANCE:
            raise CalibrationError(
                "regular Eddy PROBE is not repeatable after frequency calibration: "
                f"span={summary['span']:.6f}, "
                f"tolerance={EDDY_REFERENCE_SPAN_TOLERANCE:.6f}"
            )
        if tap_median is not None and abs(tap_median) > EDDY_REFERENCE_MEAN_TOLERANCE:
            raise CalibrationError(
                "tap median is not native Z=0: "
                f"median={tap_median:.6f}, "
                f"tolerance={EDDY_REFERENCE_MEAN_TOLERANCE:.6f}"
            )
        if residual is not None and abs(residual) > EDDY_REFERENCE_RESIDUAL_TOLERANCE:
            raise CalibrationError(
                "regular Eddy PROBE does not agree with tap median: "
                f"tap_median={tap_median:.6f}, probe_median={summary['median']:.6f}, "
                f"residual={residual:.6f}, "
                f"tolerance={EDDY_REFERENCE_RESIDUAL_TOLERANCE:.6f}"
            )
        _logger.info("I1.5 regular Eddy PROBE reference passed")
        return evidence

    def _snapshot_eddy_candidate_base(self) -> None:
        if self.dry_run:
            return
        self.store.copy(CALIB_PATH, "eddy-frequency-candidate-before-calib.yaml")
        self.store.copy(CONFIG_PATH, "eddy-frequency-candidate-before-config.cfg")

    def _restore_eddy_candidate_base(self) -> None:
        if self.dry_run:
            return
        calib_backup = self.store.path / "eddy-frequency-candidate-before-calib.yaml"
        config_backup = self.store.path / "eddy-frequency-candidate-before-config.cfg"
        if not calib_backup.exists() or not config_backup.exists():
            raise CalibrationError("Eddy candidate rollback snapshots are missing")
        shutil.copy2(calib_backup, CALIB_PATH)
        shutil.copy2(config_backup, CONFIG_PATH)
        _run_local([sys.executable, str(GENERATOR_PATH), "--check"])
        _run_local([str(DEPLOY_PATH)])
        _run_local([str(DEPLOY_PATH), "--check"])
        _logger.info("restored pre-candidate Eddy configuration")

    def calibrate_eddy_curve(self) -> None:
        _logger.info("I1.5 Eddy frequency/height calibration started")
        pre_eddy_reference = self.eddy_reference_sequence("pre_eddy")
        _logger.info("I1.5 pre-calibration reference passed; starting frequency sweep")
        self._gcode(f"G1 X{REFERENCE_X:.3f} Y{REFERENCE_Y:.3f} Z5 F1200")
        self._gcode("PROBE_EDDY_CURRENT_CALIBRATE CHIP=btt_eddy", timeout=300.0)
        if self.dry_run:
            post_eddy_reference = self.eddy_reference_sequence("post_eddy")
            post_eddy_probe = self.verify_eddy_probe_reference(
                post_eddy_reference["summary"]
            )
            self.checkpoint(
                Phase.EDDY_CALIBRATION,
                committed=False,
                pre_eddy_reference=pre_eddy_reference,
                post_eddy_reference=post_eddy_reference,
                post_eddy_probe=post_eddy_probe,
            )
            _logger.info("I1.5 dry-run frequency sweep complete")
            return
        status = self.client.status(["manual_probe"])
        manual_probe = status.get("manual_probe", {})
        if not manual_probe.get("is_active"):
            raise CalibrationError("Eddy calibration did not enter manual-probe mode")
        current_z = float(manual_probe["z_position"])
        _logger.info(
            "I1.5 manual-probe mode active at z=%.6f; targeting z=0", current_z
        )
        delta = -current_z
        if current_z + delta < -0.01:
            raise CalibrationError(
                "manual-probe targeting would descend below native contact"
            )
        self._gcode(f"TESTZ Z={delta:.6f}")
        status = self.client.status(["manual_probe"])
        final_z = float(status.get("manual_probe", {}).get("z_position", math.nan))
        if not math.isfinite(final_z) or abs(final_z) > 0.004:
            raise CalibrationError(
                f"manual-probe target did not reach Z=0: {final_z!r}"
            )
        _logger.info(
            "I1.5 manual-probe target reached at z=%.6f; accepting sweep", final_z
        )
        # Klipper continues the frequency sweep after ACCEPT; the response can
        # therefore take longer than the normal short G-code request timeout.
        self._gcode("ACCEPT", timeout=300.0)
        curve = str(self.capture_pending("probe_eddy_current btt_eddy", "calibrate"))
        pairs = [part.strip() for part in curve.split(",") if part.strip()]
        if len(pairs) < 9:
            raise CalibrationError("Eddy calibration returned fewer than nine pairs")
        for pair in pairs:
            height, frequency = pair.split(":", 1)
            if not math.isfinite(float(height)) or not math.isfinite(float(frequency)):
                raise CalibrationError("Eddy calibration contains a non-finite pair")
        _logger.info(
            "I1.5 received Eddy curve with %d height/frequency pairs", len(pairs)
        )
        self._snapshot_eddy_candidate_base()
        try:
            self.deploy_value(
                {("eddy_relative_calibration", "klipper", "calibrate"): curve},
                Phase.EDDY_CALIBRATION,
                checkpoint=False,
            )
            post_eddy_reference = self.eddy_reference_sequence("post_eddy")
        except CalibrationError as exc:
            self.checkpoint(
                Phase.EDDY_CALIBRATION,
                committed=False,
                eddy_calibration=curve,
                pre_eddy_reference=pre_eddy_reference,
                post_eddy_error=str(exc),
            )
            self._restore_eddy_candidate_base()
            raise
        _logger.info(
            "I1.5 post-calibration reference passed: mean=%.6f span=%.6f",
            post_eddy_reference["summary"]["mean"],
            post_eddy_reference["summary"]["span"],
        )
        try:
            post_eddy_probe = self.verify_eddy_probe_reference(
                post_eddy_reference["summary"]
            )
        except CalibrationError as exc:
            diagnostics = self.run_eddy_probe_diagnostics()
            self.checkpoint(
                Phase.EDDY_CALIBRATION,
                committed=False,
                eddy_calibration=curve,
                pre_eddy_reference=pre_eddy_reference,
                post_eddy_reference=post_eddy_reference,
                post_eddy_probe_error=str(exc),
                eddy_probe_diagnostics=diagnostics,
            )
            self._restore_eddy_candidate_base()
            raise
        self._gcode(f"G1 X{REFERENCE_X:.3f} Y{REFERENCE_Y:.3f} Z5 F1200")
        self.checkpoint(
            Phase.EDDY_CALIBRATION,
            committed=True,
            eddy_calibration=curve,
            pre_eddy_reference=pre_eddy_reference,
            post_eddy_reference=post_eddy_reference,
            post_eddy_probe=post_eddy_probe,
        )
        _logger.info("I1.5 Eddy frequency/height calibration finished and committed")

    @staticmethod
    def _curve_doctor_status(status: Mapping[str, Any], field: str) -> dict[str, Any]:
        extra = status.get("eddy_tap_measure")
        if not isinstance(extra, Mapping):
            raise CalibrationError("Eddy diagnostic extra status is unavailable")
        value = extra.get(field)
        if not isinstance(value, Mapping):
            raise CalibrationError(f"Eddy diagnostic extra did not publish {field}")
        return dict(value)

    def _collect_curve_doctor_raw_batch(
        self,
        *,
        target_height: float,
        tap_median: float,
        safe_travel: bool = True,
        lift_after: bool = True,
        approach_z: float | None = None,
    ) -> dict[str, Any]:
        commanded_z = tap_median + target_height
        if commanded_z <= 0.0:
            raise CalibrationError(
                f"curve-doctor commanded Z is unsafe: {commanded_z:.6f}"
            )
        command = (
            f"EDDY_RAW_MEASURE X={REFERENCE_X:.3f} Y={REFERENCE_Y:.3f} "
            f"Z={commanded_z:.6f} DURATION={CURVE_DOCTOR_DURATION:.3f}"
        )
        if not safe_travel:
            command += " SAFE_TRAVEL=0"
        if not lift_after:
            command += " LIFT_AFTER=0"
        if approach_z is not None:
            command += f" APPROACH_Z={approach_z:.6f}"
        self._gcode(command)
        raw = self._curve_doctor_status(
            self.client.status(["eddy_tap_measure"]), "last_raw_measurement"
        )
        required = (
            "bed_x",
            "bed_y",
            "nozzle_x",
            "nozzle_y",
            "requested_nozzle_z",
            "toolhead_z",
            "toolhead_position",
            "raw_frequency_hz",
            "raw_frequency_span_hz",
            "sample_count",
            "temperature",
        )
        if any(key not in raw for key in required):
            raise CalibrationError("Eddy raw status is missing curve-doctor fields")
        numeric = {
            key: float(raw[key])
            for key in required
            if key not in {"temperature", "toolhead_position"}
        }
        if not all(math.isfinite(value) for value in numeric.values()):
            raise CalibrationError("Eddy raw status contains a non-finite value")
        if (
            abs(numeric["bed_x"] - REFERENCE_X) > EDDY_REFERENCE_XY_TOLERANCE
            or abs(numeric["bed_y"] - REFERENCE_Y) > EDDY_REFERENCE_XY_TOLERANCE
        ):
            raise CalibrationError(
                "Eddy raw measurement did not use the reference bed point"
            )
        if abs(numeric["requested_nozzle_z"] - commanded_z) > 1e-6:
            raise CalibrationError("Eddy raw measurement used an unexpected nozzle Z")
        if abs(numeric["toolhead_z"] - commanded_z) > 0.005:
            raise CalibrationError(
                "Eddy raw measurement did not settle at its commanded Z"
            )
        toolhead_position = raw["toolhead_position"]
        if (
            not isinstance(toolhead_position, Sequence)
            or len(toolhead_position) < 3
            or any(not math.isfinite(float(value)) for value in toolhead_position[:3])
        ):
            raise CalibrationError("Eddy raw status is missing its toolhead position")
        raw.update(numeric)
        raw["target_height"] = target_height
        raw["commanded_z"] = commanded_z
        return raw

    def _collect_curve_doctor_anchors(
        self, tap_median: float, source_curve: str
    ) -> list[dict[str, Any]]:
        source = parse_eddy_curve(source_curve)
        anchors: list[dict[str, Any]] = []
        approach_z = tap_median + CURVE_DOCTOR_ASCENT_APPROACH_CLEARANCE
        if approach_z <= 0.0:
            raise CalibrationError(
                "curve-doctor upward approach Z is unsafe: " f"{approach_z:.6f}"
            )
        for target_height in CURVE_DOCTOR_HEIGHTS:
            batches: list[dict[str, Any]] = []
            for batch_index in range(CURVE_DOCTOR_BATCH_COUNT):
                _logger.info(
                    "curve-doctor raw batch %d/%d: target_height=%.3f",
                    batch_index + 1,
                    CURVE_DOCTOR_BATCH_COUNT,
                    target_height,
                )
                if self.dry_run:
                    frequency = eddy_curve_frequency_at_height(source, target_height)
                    batches.append(
                        {
                            "target_height": target_height,
                            "commanded_z": tap_median + target_height,
                            "raw_frequency_hz": frequency,
                            "raw_frequency_span_hz": 0.0,
                            "sample_count": 0,
                            "temperature": None,
                            "dry_run": True,
                        }
                    )
                else:
                    batches.append(
                        self._collect_curve_doctor_raw_batch(
                            target_height=target_height,
                            tap_median=tap_median,
                            safe_travel=not anchors and batch_index == 0,
                            lift_after=False,
                            approach_z=(
                                approach_z if not anchors and batch_index == 0 else None
                            ),
                        )
                    )
            frequencies = [float(batch["raw_frequency_hz"]) for batch in batches]
            anchors.append(
                {
                    "target_height": target_height,
                    "commanded_z": tap_median + target_height,
                    "raw_frequency_hz": statistics.median(frequencies),
                    "batch_frequency_span_hz": max(frequencies) - min(frequencies),
                    "batches": batches,
                }
            )
        if not self.dry_run:
            _logger.info(
                "curve-doctor anchor sweep finished; lifting once to the safe travel height"
            )
            self._gcode("G90\nG1 Z5 F1200")
        return anchors

    def _validate_curve_doctor_candidate(self, tap_median: float) -> dict[str, Any]:
        commanded_heights = tuple(
            tap_median + target_height for target_height in CURVE_DOCTOR_HEIGHTS
        )
        if self.dry_run:
            results = [
                {
                    "target_height": target_height,
                    "commanded_z": commanded_z,
                    "scan_bed_z": tap_median,
                    "residual": 0.0,
                }
                for target_height, commanded_z in zip(
                    CURVE_DOCTOR_HEIGHTS, commanded_heights
                )
            ]
            return {"results": results, "span": 0.0, "dry_run": True}
        nozzle_zs = ",".join(f"{height:.6f}" for height in commanded_heights)
        self._gcode(
            f"EDDY_SCAN_HEIGHT_TEST X={REFERENCE_X:.3f} Y={REFERENCE_Y:.3f} "
            f"NOZZLE_ZS={nozzle_zs} DURATION={CURVE_DOCTOR_DURATION:.3f}"
        )
        measured = self._curve_doctor_status(
            self.client.status(["eddy_tap_measure"]), "last_scan_height_test"
        )
        values = measured.get("results")
        if not isinstance(values, Sequence) or len(values) != len(CURVE_DOCTOR_HEIGHTS):
            raise CalibrationError(
                "Eddy scan-height validation returned an invalid result count"
            )
        results: list[dict[str, Any]] = []
        for target_height, commanded_z, value in zip(
            CURVE_DOCTOR_HEIGHTS, commanded_heights, values
        ):
            if not isinstance(value, Mapping):
                raise CalibrationError(
                    "Eddy scan-height validation returned an invalid point"
                )
            scan_bed_z = float(value.get("scan_bed_z", math.nan))
            toolhead_z = float(value.get("toolhead_z", math.nan))
            if not math.isfinite(scan_bed_z) or not math.isfinite(toolhead_z):
                raise CalibrationError(
                    "Eddy scan-height validation returned a non-finite Z"
                )
            if abs(toolhead_z - commanded_z) > 0.005:
                raise CalibrationError(
                    "Eddy scan-height validation used an unexpected nozzle Z"
                )
            residual = scan_bed_z - tap_median
            results.append(
                {
                    "target_height": target_height,
                    "commanded_z": commanded_z,
                    "scan_bed_z": scan_bed_z,
                    "residual": residual,
                    "raw": dict(value),
                }
            )
        residuals = [float(result["residual"]) for result in results]
        span = max(residuals) - min(residuals)
        validation = {"results": results, "span": span, "raw_status": measured}
        if any(
            abs(residual) > CURVE_DOCTOR_ABSOLUTE_TOLERANCE for residual in residuals
        ):
            raise CalibrationError(
                "curve-doctor validation exceeds absolute tolerance: " + repr(residuals)
            )
        if span > CURVE_DOCTOR_SPAN_TOLERANCE:
            raise CalibrationError(
                f"curve-doctor validation span {span:.6f} exceeds "
                f"{CURVE_DOCTOR_SPAN_TOLERANCE:.6f}"
            )
        return validation

    def doctor_eddy_curve(self) -> None:
        """Build, deploy, validate, and atomically retain a Tap-anchored curve."""

        _logger.info("I1.5D Tap-anchored Eddy curve doctoring started")
        source_curve = str(
            self.raw_calibration["eddy_relative_calibration"]["klipper"]["calibrate"]
        )
        pre_reference = self.eddy_reference_sequence("curve_doctor_pre")
        tap_median = float(pre_reference["median_tap_z"])
        anchors = self._collect_curve_doctor_anchors(tap_median, source_curve)
        candidate_curve, derived_anchors = doctor_eddy_curve(source_curve, anchors)
        evidence: dict[str, Any] = {
            "source_curve": source_curve,
            "pre_reference": pre_reference,
            "anchors": anchors,
            "derived_anchors": derived_anchors,
            "candidate_curve": candidate_curve,
        }
        self.store.write_json("curve-doctor-candidate.json", evidence)
        if self.dry_run:
            validation = self._validate_curve_doctor_candidate(tap_median)
            self.checkpoint(
                Phase.CURVE_DOCTOR,
                committed=False,
                curve_doctor={**evidence, "validation": validation},
            )
            return
        self._snapshot_eddy_candidate_base()
        try:
            self.deploy_value(
                {
                    (
                        "eddy_relative_calibration",
                        "klipper",
                        "calibrate",
                    ): candidate_curve
                },
                Phase.CURVE_DOCTOR,
                checkpoint=False,
            )
            post_reference = self.eddy_reference_sequence("curve_doctor_post")
            validation = self._validate_curve_doctor_candidate(
                float(post_reference["median_tap_z"])
            )
        except Exception as exc:
            failure = {**evidence, "error": str(exc)}
            self.store.write_json("curve-doctor-failed.json", failure)
            self.checkpoint(Phase.CURVE_DOCTOR, committed=False, curve_doctor=failure)
            self._restore_eddy_candidate_base()
            raise
        self.raw_calibration = _load_raw_calibration()
        accepted = {
            **evidence,
            "post_reference": post_reference,
            "validation": validation,
            "rollback": False,
        }
        self.store.write_json("curve-doctor-accepted.json", accepted)
        self.checkpoint(Phase.CURVE_DOCTOR, committed=True, curve_doctor=accepted)
        _logger.info("I1.5D Tap-anchored Eddy curve doctoring committed")

    def _mesh_snapshot(self, mesh_status: Mapping[str, Any]) -> dict[str, Any]:
        matrix = mesh_status.get("mesh_matrix") or mesh_status.get("probed_matrix")
        if not matrix:
            raise CalibrationError("active mesh did not expose a matrix for diagnosis")
        mesh_min_values = mesh_status.get("mesh_min", [0.0, 20.0])
        mesh_max_values = mesh_status.get("mesh_max", [190.0, 275.0])
        if isinstance(mesh_min_values, Mapping):
            mesh_min_values = [mesh_min_values["x"], mesh_min_values["y"]]
        if isinstance(mesh_max_values, Mapping):
            mesh_max_values = [mesh_max_values["x"], mesh_max_values["y"]]
        eddy = self.raw_calibration["eddy_relative_calibration"]["nozzle_to_coil"]
        live = self.client.status(
            ["probe", "toolhead", "temperature_probe btt_eddy", "gcode_move"]
        )
        snapshot = {
            "profile_name": mesh_status.get("profile_name"),
            "mesh_min": [float(mesh_min_values[0]), float(mesh_min_values[1])],
            "mesh_max": [float(mesh_max_values[0]), float(mesh_max_values[1])],
            "mesh_matrix": [[float(value) for value in row] for row in matrix],
            "probed_matrix": [
                [float(value) for value in row]
                for row in (mesh_status.get("probed_matrix") or matrix)
            ],
            "zero_reference_position": [REFERENCE_X, REFERENCE_Y],
            "probe_offsets": {"x": float(eddy["x"]), "y": float(eddy["y"])},
            "temperature": live.get("temperature_probe btt_eddy", {}).get(
                "temperature"
            ),
            "toolhead_position": live.get("toolhead", {}).get("position"),
            "gcode_position": live.get("gcode_move", {}).get("gcode_position"),
        }
        self.store.write_json("mesh-scan.json", snapshot)
        return snapshot

    @staticmethod
    def _mesh_snapshot_bounds(
        snapshot: Mapping[str, Any],
    ) -> tuple[MeshPoint, MeshPoint]:
        mesh_min = snapshot["mesh_min"]
        mesh_max = snapshot["mesh_max"]
        return (
            MeshPoint(float(mesh_min[0]), float(mesh_min[1])),
            MeshPoint(float(mesh_max[0]), float(mesh_max[1])),
        )

    def _capture_same_point_mesh_measurement(
        self, *, point: MeshPoint
    ) -> dict[str, Any]:
        self._gcode(
            f"EDDY_TAP_MEASURE X={point.x:.3f} Y={point.y:.3f} "
            f"THRESHOLD={self.tap_threshold} COUNT={MESH_DIAGNOSTIC_TAP_COUNT} "
            "EDDY_MODE=scan "
            f"SCAN_COUNT={MESH_STATIONARY_SCAN_COUNT} "
            f"SCAN_HEIGHT={MESH_STATIONARY_SCAN_HEIGHT:.6f} "
            f"DURATION={MESH_STATIONARY_SCAN_DURATION:.3f} "
            f"XY_SPEED={MESH_DIAGNOSTIC_XY_SPEED:.3f}"
        )
        status = self.client.status(["eddy_tap_measure"])
        extra = status.get("eddy_tap_measure", {})
        result = extra.get("last_tap_measurement")
        if not isinstance(result, Mapping):
            raise CalibrationError("same-point Tap/scan did not publish its result")
        captured = dict(result)
        tap = captured.get("tap")
        stationary = captured.get("stationary_scan")
        if not isinstance(tap, Mapping) or not isinstance(stationary, Mapping):
            raise CalibrationError("same-point Tap/scan returned incomplete evidence")
        if (
            abs(float(captured.get("bed_x", math.nan)) - point.x)
            > EDDY_REFERENCE_XY_TOLERANCE
            or abs(float(captured.get("bed_y", math.nan)) - point.y)
            > EDDY_REFERENCE_XY_TOLERANCE
        ):
            raise CalibrationError(
                "same-point Tap/scan did not measure the requested physical point"
            )
        if int(tap.get("count", 0)) != MESH_DIAGNOSTIC_TAP_COUNT:
            raise CalibrationError(
                "same-point measurement returned an unexpected Tap count"
            )
        if int(stationary.get("count", 0)) != MESH_STATIONARY_SCAN_COUNT:
            raise CalibrationError(
                "same-point measurement returned an unexpected scan count"
            )
        return captured

    @staticmethod
    def _residual_summary(values: Sequence[float]) -> dict[str, float] | None:
        if not values:
            return None
        return {
            "median": statistics.median(values),
            "rms": math.sqrt(statistics.fmean(value * value for value in values)),
            "max_abs": max(map(abs, values)),
        }

    def diagnose_mesh_against_tap(
        self, rapid_snapshot: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Measure a clean same-point Tap/stationary-scan map against the mesh."""

        mesh_min, mesh_max = self._mesh_snapshot_bounds(rapid_snapshot)
        matrix = rapid_snapshot["mesh_matrix"]
        eddy = self.raw_calibration["eddy_relative_calibration"]["nozzle_to_coil"]
        grid = derive_safe_tap_grid(
            nozzle_x=AxisBounds(0.0, 255.0),
            nozzle_y=AxisBounds(-15.0, 296.0),
            mesh_x=AxisBounds(mesh_min.x, mesh_max.x),
            mesh_y=AxisBounds(mesh_min.y, mesh_max.y),
            coil_offset_x=float(eddy["x"]),
            coil_offset_y=float(eddy["y"]),
        )
        reference = MeshPoint(REFERENCE_X, REFERENCE_Y)
        _logger.info(
            "mesh METHOD=scan diagnostic: clearing mesh for clean measurements"
        )
        self._gcode("BED_MESH_CLEAR")
        reference_result: dict[str, Any] = {
            "point": asdict(reference),
            "ok": False,
        }
        failures: list[str] = []
        try:
            center_measurement = self._capture_same_point_mesh_measurement(
                point=reference
            )
        except Exception as exc:
            reference_result["error"] = str(exc)
            failures.append("reference same-point Tap/scan acquisition failed")
        else:
            center_tap = center_measurement["tap"]
            center_scan = center_measurement["stationary_scan"]
            reference_result["same_point"] = center_measurement
            reference_result["summary"] = dict(center_tap)
            reference_result["samples"] = [
                float(sample["z"]) for sample in center_tap["samples"]
            ]
            reference_result["mesh_correction"] = mesh_correction_at(
                matrix, mesh_min=mesh_min, mesh_max=mesh_max, point=reference
            )
            reference_result["ok"] = (
                abs(float(center_tap["mean"])) <= MESH_POINT_TOLERANCE
                and abs(reference_result["mesh_correction"]) <= MESH_CENTER_TOLERANCE
            )
            if not reference_result["ok"]:
                reference_result["error"] = (
                    "reference Tap/mesh gate failed: "
                    f"mean={float(center_tap['mean']):.6f} "
                    f"correction={reference_result['mesh_correction']:.6f}"
                )
                failures.append(reference_result["error"])
            reference_result["stationary_scan"] = center_scan
            reference_result["stationary_eddy_minus_tap"] = float(
                center_scan["scan_bed_z_median"]
            ) - float(center_tap["mean"])
        point_results: list[dict[str, Any]] = []
        failed_points: list[dict[str, Any]] = []
        tap_samples: dict[MeshPoint, tuple[float, ...]] = {}
        corrections: dict[MeshPoint, float] = {}
        rapid_minus_stationary: list[float] = []
        stationary_minus_tap: list[float] = []
        rapid_minus_tap: list[float] = []
        for point in grid:
            result: dict[str, Any] = {"point": asdict(point), "ok": False}
            correction = mesh_correction_at(
                matrix, mesh_min=mesh_min, mesh_max=mesh_max, point=point
            )
            result["mesh_correction"] = correction
            try:
                measurement = self._capture_same_point_mesh_measurement(point=point)
            except Exception as exc:
                result["acquisition_error"] = str(exc)
            else:
                tap = measurement["tap"]
                stationary = measurement["stationary_scan"]
                tap_mean = float(tap["mean"])
                stationary_median = float(stationary["scan_bed_z_median"])
                result["same_point"] = measurement
                result["tap_summary"] = dict(tap)
                result["tap_samples"] = [
                    float(sample["z"]) for sample in tap["samples"]
                ]
                result["stationary_scan"] = stationary
                result["mesh_minus_stationary"] = correction - stationary_median
                result["stationary_eddy_minus_tap"] = stationary_median - tap_mean
                result["mesh_minus_tap"] = correction - tap_mean
                rapid_minus_stationary.append(result["mesh_minus_stationary"])
                stationary_minus_tap.append(result["stationary_eddy_minus_tap"])
                rapid_minus_tap.append(result["mesh_minus_tap"])
                tap_samples[point] = tuple(result["tap_samples"])
                corrections[point] = correction
                result["ok"] = True
            point_results.append(result)
            if not result["ok"]:
                failed_points.append(result)
            _logger.info(
                "mesh METHOD=scan diagnostic point: x=%.3f y=%.3f mesh=%+.6f "
                "tap=%s stationary=%s mesh_minus_stationary=%s "
                "stationary_minus_tap=%s",
                point.x,
                point.y,
                correction,
                _format_optional_float(
                    result.get("tap_summary", {}).get("mean")
                    if isinstance(result.get("tap_summary"), Mapping)
                    else None
                ),
                _format_optional_float(
                    result.get("stationary_scan", {}).get("scan_bed_z_median")
                    if isinstance(result.get("stationary_scan"), Mapping)
                    else None
                ),
                _format_optional_float(result.get("mesh_minus_stationary")),
                _format_optional_float(result.get("stationary_eddy_minus_tap")),
            )
        try:
            rapid_tap_gate = mesh_tap_acceptance(tap_samples, corrections)
        except CalibrationError as exc:
            rapid_tap_gate = {"points": {}, "rms": None, "max_abs": None}
            failures.append(f"mesh-vs-single-Tap gate: {exc}")
        if failed_points:
            failures.append(
                f"diagnostic acquisition failed at {len(failed_points)} points"
            )
        verification: dict[str, Any] = {
            "rapid_scan": dict(rapid_snapshot),
            "reference": reference_result,
            "same_point_eddy_mode": "scan",
            "tap_count": MESH_DIAGNOSTIC_TAP_COUNT,
            "stationary_scan_count": MESH_STATIONARY_SCAN_COUNT,
            "stationary_scan_height": MESH_STATIONARY_SCAN_HEIGHT,
            "xy_speed": MESH_DIAGNOSTIC_XY_SPEED,
            "point_results": point_results,
            "failed_points": failed_points,
            "attempted_points": len(grid),
            "successful_tap_points": len(tap_samples),
            "rapid_mesh_vs_tap": rapid_tap_gate,
            "rapid_mesh_minus_stationary": self._residual_summary(
                rapid_minus_stationary
            ),
            "stationary_eddy_minus_tap": self._residual_summary(stationary_minus_tap),
            "rapid_mesh_minus_tap": self._residual_summary(rapid_minus_tap),
            "error": "; ".join(failures) if failures else None,
        }
        return verification

    def verify_active_mesh_transform(
        self, verification: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Verify that an active mesh preserves raw Tap contact reporting."""

        candidates = [
            point
            for point in verification.get("point_results", [])
            if isinstance(point, Mapping)
            and isinstance(point.get("tap_summary"), Mapping)
            and "mesh_correction" in point
        ]
        if not candidates:
            return {
                "ok": False,
                "error": "no Tap-safe point for active transform check",
            }
        candidate = max(
            candidates, key=lambda item: abs(float(item["mesh_correction"]))
        )
        point_data = candidate["point"]
        point = MeshPoint(float(point_data["x"]), float(point_data["y"]))
        raw_tap_mean = float(candidate["tap_summary"]["mean"])
        correction = float(candidate["mesh_correction"])
        active_summary, attempts = self.collect_taps(
            x=point.x,
            y=point.y,
            count=1,
            max_attempts=1,
            tap_threshold=self.tap_threshold,
            allow_empty=True,
        )
        result: dict[str, Any] = {
            "point": asdict(point),
            "raw_tap_mean": raw_tap_mean,
            "mesh_correction": correction,
            "expected_raw_tap": raw_tap_mean,
            "attempts": attempts,
            "ok": False,
        }
        if active_summary is None:
            result["error"] = "no active-mesh Tap samples"
            return result
        result["summary"] = asdict(active_summary)
        result["active_tap_mean"] = active_summary.mean
        result["delta_active_minus_clean_raw"] = active_summary.mean - raw_tap_mean
        if active_summary.rejected_attempts:
            result["error"] = (
                "active-mesh raw Tap acquisition failed: "
                f"rejected={active_summary.rejected_attempts}"
            )
            return result
        if (
            abs(result["delta_active_minus_clean_raw"])
            > MESH_ACTIVE_TRANSFORM_TOLERANCE
        ):
            result["error"] = (
                "active-mesh raw Tap differs from clean raw Tap: "
                f"delta={result['delta_active_minus_clean_raw']:.6f} "
                f"tolerance={MESH_ACTIVE_TRANSFORM_TOLERANCE:.6f}"
            )
            return result
        result["ok"] = True
        return result

    def verify_mesh_against_tap(self, mesh_status: Mapping[str, Any]) -> dict[str, Any]:
        matrix = mesh_status.get("mesh_matrix") or mesh_status.get("probed_matrix")
        if not matrix:
            raise CalibrationError(
                "active mesh did not expose a matrix for verification"
            )
        mesh_min_values = mesh_status.get("mesh_min", [0.0, 20.0])
        mesh_max_values = mesh_status.get("mesh_max", [190.0, 275.0])
        if isinstance(mesh_min_values, Mapping):
            mesh_min_values = [mesh_min_values["x"], mesh_min_values["y"]]
        if isinstance(mesh_max_values, Mapping):
            mesh_max_values = [mesh_max_values["x"], mesh_max_values["y"]]
        mesh_min = MeshPoint(float(mesh_min_values[0]), float(mesh_min_values[1]))
        mesh_max = MeshPoint(float(mesh_max_values[0]), float(mesh_max_values[1]))
        eddy = self.raw_calibration["eddy_relative_calibration"]["nozzle_to_coil"]
        grid = derive_safe_tap_grid(
            nozzle_x=AxisBounds(0.0, 255.0),
            nozzle_y=AxisBounds(-15.0, 296.0),
            mesh_x=AxisBounds(mesh_min.x, mesh_max.x),
            mesh_y=AxisBounds(mesh_min.y, mesh_max.y),
            coil_offset_x=float(eddy["x"]),
            coil_offset_y=float(eddy["y"]),
        )
        reference = MeshPoint(REFERENCE_X, REFERENCE_Y)
        _logger.info(
            "mesh reference verification started: x=%.3f y=%.3f",
            reference.x,
            reference.y,
        )
        reference_summary, reference_attempts = self.collect_taps(
            x=reference.x,
            y=reference.y,
            count=3,
            max_attempts=3,
            tap_threshold=self.tap_threshold,
            allow_empty=True,
        )
        reference_result: dict[str, Any] = {
            "point": {"x": reference.x, "y": reference.y},
            "attempts": reference_attempts,
            "ok": False,
        }
        reference_errors: list[str] = []
        if reference_summary is None:
            reference_errors.append("no successful tap samples")
        else:
            reference_result["summary"] = asdict(reference_summary)
            reference_result["samples"] = list(reference_summary.successful)
            try:
                reference_correction = mesh_correction_at(
                    matrix,
                    mesh_min=mesh_min,
                    mesh_max=mesh_max,
                    point=reference,
                )
            except Exception as exc:
                reference_errors.append(str(exc))
            else:
                reference_corrected_mean = mesh_corrected_contact_z(
                    reference_summary.mean, reference_correction
                )
                reference_result["mesh_correction"] = reference_correction
                reference_result["mesh_corrected_mean"] = reference_corrected_mean
                if (
                    len(reference_summary.successful) != 3
                    or reference_summary.rejected_attempts
                ):
                    reference_errors.append(
                        "reference tap rejected a sample: "
                        f"successful={len(reference_summary.successful)}, "
                        f"rejected={reference_summary.rejected_attempts}"
                    )
                if reference_summary.span > 0.020:
                    reference_errors.append(
                        "reference tap span exceeds 0.020 mm: "
                        f"span={reference_summary.span:.6f}"
                    )
                if abs(reference_correction) > MESH_CENTER_TOLERANCE:
                    reference_errors.append(
                        "reference mesh correction exceeds tolerance: "
                        f"correction={reference_correction:.6f}, "
                        f"tolerance={MESH_CENTER_TOLERANCE:.6f}"
                    )
                if abs(reference_corrected_mean) > MESH_POINT_TOLERANCE:
                    reference_errors.append(
                        "mesh-corrected reference tap exceeds point tolerance: "
                        f"mean={reference_corrected_mean:.6f}, "
                        f"tolerance={MESH_POINT_TOLERANCE:.6f}"
                    )
        if reference_errors:
            reference_result["error"] = "; ".join(reference_errors)
            _logger.warning(
                "mesh reference verification failed: %s; continuing through grid",
                reference_result["error"],
            )
        else:
            reference_result["ok"] = True
            _logger.info(
                "mesh reference verification passed: mean=%.6f correction=%.6f "
                "corrected_mean=%.6f span=%.6f",
                reference_summary.mean,
                reference_result["mesh_correction"],
                reference_result["mesh_corrected_mean"],
                reference_summary.span,
            )
        tap_samples: dict[MeshPoint, tuple[float, ...]] = {}
        corrections: dict[MeshPoint, float] = {}
        point_results: list[dict[str, Any]] = []
        failed_points: list[dict[str, Any]] = []
        for point in grid:
            _logger.info(
                "mesh verification point started: x=%.3f y=%.3f",
                point.x,
                point.y,
            )
            summary, attempts = self.collect_taps(
                x=point.x,
                y=point.y,
                count=3,
                max_attempts=3,
                tap_threshold=self.tap_threshold,
                allow_empty=True,
            )
            result: dict[str, Any] = {
                "point": {"x": point.x, "y": point.y},
                "attempts": attempts,
                "ok": False,
            }
            if summary is None:
                result["error"] = "no successful tap samples"
                failed_points.append(result)
                point_results.append(result)
                _logger.warning(
                    "mesh verification point failed: x=%.3f y=%.3f "
                    "no successful tap samples; continuing",
                    point.x,
                    point.y,
                )
                continue
            result["summary"] = asdict(summary)
            result["samples"] = list(summary.successful)
            if summary.rejected_attempts or summary.span > 0.020:
                result["error"] = (
                    "tap repeatability failed: "
                    f"rejected={summary.rejected_attempts}, span={summary.span:.6f}"
                )
                failed_points.append(result)
                point_results.append(result)
                _logger.warning(
                    "mesh verification point failed: x=%.3f y=%.3f %s; continuing",
                    point.x,
                    point.y,
                    result["error"],
                )
                continue
            try:
                correction = mesh_correction_at(
                    matrix,
                    mesh_min=mesh_min,
                    mesh_max=mesh_max,
                    point=point,
                )
            except Exception as exc:
                result["error"] = str(exc)
                failed_points.append(result)
                point_results.append(result)
                _logger.warning(
                    "mesh verification point failed: x=%.3f y=%.3f %s; continuing",
                    point.x,
                    point.y,
                    exc,
                )
                continue
            result["mesh_correction"] = correction
            result["ok"] = True
            tap_samples[point] = summary.successful
            corrections[point] = correction
            point_results.append(result)
            _logger.info(
                "mesh verification point passed acquisition: x=%.3f y=%.3f "
                "mean=%.6f span=%.6f correction=%.6f",
                point.x,
                point.y,
                summary.mean,
                summary.span,
                correction,
            )
        verification: dict[str, Any]
        global_error: str | None = None
        try:
            verification = mesh_tap_acceptance(tap_samples, corrections)
        except CalibrationError as exc:
            global_error = str(exc)
            verification = {
                "points": {},
                "rms": None,
                "max_abs": None,
            }
        verification.update(
            {
                "reference": reference_result,
                "point_results": point_results,
                "failed_points": failed_points,
                "attempted_points": len(grid),
                "successful_points": len(tap_samples),
            }
        )
        failures: list[str] = []
        if reference_errors:
            failures.append(
                "reference "
                f"({reference.x:.3f},{reference.y:.3f}): "
                f"{reference_result['error']}"
            )
        if failed_points:
            failed_labels = ", ".join(
                f"({item['point']['x']:.3f},{item['point']['y']:.3f})"
                for item in failed_points
            )
            failures.append(
                f"grid acquisition failed at {len(failed_points)}: {failed_labels}"
            )
        if global_error is not None:
            failures.append(f"grid global gate: {global_error}")
        if failures:
            verification["error"] = "; ".join(failures)
        self.store.write_json("mesh-verification.json", verification)
        if failures:
            raise CalibrationError(
                "mesh verification surveyed all "
                f"{len(grid)} points but failed: {verification['error']}"
            )
        return verification

    def final_mesh(self, *, clean_frame: bool = True) -> None:
        _logger.info("I1.6/I1.7 final transient mesh scan started")
        if clean_frame:
            self._home_clean_frame()
        else:
            _logger.info("I1.6 reusing the committed post-Eddy clean frame")
        if not self.dry_run:
            before = self.client.status(["configfile"])
            pending = before.get("configfile", {}).get("save_config_pending_items", {})
            if pending:
                raise CalibrationError("pending configuration exists before mesh scan")
        _logger.info("running mesh scan at HORIZONTAL_MOVE_Z=1")
        self._gcode(
            "BED_MESH_CALIBRATE METHOD=scan PROFILE=default HORIZONTAL_MOVE_Z=1",
            timeout=900.0,
        )
        if not self.dry_run:
            _logger.info(
                "saving METHOD=scan mesh profile %s for supervised manual inspection",
                MESH_MANUAL_PROFILE,
            )
            self._gcode(f"BED_MESH_PROFILE SAVE={MESH_MANUAL_PROFILE}")
        status = (
            self.client.status(["bed_mesh", "configfile"]) if not self.dry_run else {}
        )
        if not self.dry_run:
            require_only_transient_mesh_pending(
                status.get("configfile", {}).get("save_config_pending_items", {})
            )
            mesh = status.get("bed_mesh", {})
            if not mesh.get("profile_name") and not mesh.get("mesh_matrix"):
                raise CalibrationError(
                    "mesh scan did not leave an active in-memory mesh"
                )
            rapid_snapshot = self._mesh_snapshot(mesh)
            verification: dict[str, Any]
            diagnostic_error: Exception | None = None
            try:
                verification = self.diagnose_mesh_against_tap(rapid_snapshot)
            except Exception as exc:
                diagnostic_error = exc
                verification = {
                    "rapid_scan": rapid_snapshot,
                    "error": f"clean mesh diagnostic did not complete: {exc}",
                }
            finally:
                _logger.info(
                    "reloading saved METHOD=scan mesh profile %s after clean diagnostics",
                    MESH_MANUAL_PROFILE,
                )
                self._gcode(f"BED_MESH_PROFILE LOAD={MESH_MANUAL_PROFILE}")
            active_status = self.client.status(["bed_mesh"])
            active_mesh = active_status.get("bed_mesh", {})
            if active_mesh.get(
                "profile_name"
            ) != MESH_MANUAL_PROFILE or not active_mesh.get("mesh_matrix"):
                reload_error = (
                    f"METHOD=scan mesh profile {MESH_MANUAL_PROFILE} did not become active "
                    "after reload"
                )
                verification["error"] = "; ".join(
                    value
                    for value in [verification.get("error"), reload_error]
                    if value
                )
            else:
                transform = self.verify_active_mesh_transform(verification)
                verification["active_mesh_transform"] = transform
                if not transform.get("ok"):
                    verification["error"] = "; ".join(
                        value
                        for value in [
                            verification.get("error"),
                            "active mesh raw-Tap check: "
                            + str(transform.get("error", "failed")),
                        ]
                        if value
                    )
            verification["rapid_mesh_profile"] = MESH_MANUAL_PROFILE
            verification["rapid_mesh_reloaded"] = not bool(
                verification.get("error")
                and "did not become active" in str(verification["error"])
            )
            self.store.write_json("mesh-verification.json", verification)
            if diagnostic_error is not None:
                raise CalibrationError(str(diagnostic_error))
            if verification.get("error"):
                raise CalibrationError(
                    "mesh diagnostic surveyed all 9 points but failed: "
                    + str(verification["error"])
                )
        if self.dry_run:
            self.checkpoint(Phase.MESH_SCAN, committed=False)
        else:
            self.checkpoint(Phase.MESH_SCAN, committed=True, mesh_status=status)
            self.checkpoint(
                Phase.MESH_VERIFY, committed=True, mesh_verification=verification
            )
            rapid_tap = verification["rapid_mesh_vs_tap"]
            rapid_stationary = verification["rapid_mesh_minus_stationary"]
            stationary_tap = verification["stationary_eddy_minus_tap"]
            _logger.info(
                "I1.7 METHOD=scan diagnostic passed: mesh-vs-Tap max_abs=%.6f "
                "rms=%.6f; mesh-vs-stationary max_abs=%s; "
                "stationary-vs-Tap max_abs=%s",
                rapid_tap["max_abs"],
                rapid_tap["rms"],
                _format_optional_float(
                    None if rapid_stationary is None else rapid_stationary["max_abs"]
                ),
                _format_optional_float(
                    None if stationary_tap is None else stationary_tap["max_abs"]
                ),
            )
        _logger.info("I1.6/I1.7 final transient mesh scan finished")

    def resume(self) -> RunState:
        """Continue only from the last committed phase boundary."""

        committed = self.state.committed_phase
        if committed is None:
            raise CalibrationError("run has no committed phase boundary")
        self.confirm()
        self.preflight(checkpoint_state=False)
        phase = Phase(committed)
        if phase is Phase.CURVE_DOCTOR:
            raise CalibrationError(
                "curve-doctor is a standalone step and cannot be resumed as Iteration 1"
            )
        phases = list(Phase)
        index = phases.index(phase)
        if index <= phases.index(Phase.PREFLIGHT):
            self.bootstrap_tap()
            index = phases.index(Phase.BOOTSTRAP_TAP)
        elif index == phases.index(Phase.BOOTSTRAP_TAP):
            summary_data = (self.state.evidence or {}).get("bootstrap_summary")
            if not summary_data:
                raise CalibrationError("resume state lacks bootstrap tap summary")
            self.update_endstops(float(summary_data["median"]))
        if index <= phases.index(Phase.ENDSTOPS):
            self.verify_center()
        if index <= phases.index(Phase.CENTER_VERIFY):
            self.calibrate_drive_current()
        if index <= phases.index(Phase.DRIVE_CURRENT):
            self.calibrate_eddy_curve()
        if index <= phases.index(Phase.EDDY_CALIBRATION):
            self.final_mesh()
        elif phase is Phase.MESH_SCAN:
            status = self.client.status(["bed_mesh", "configfile"])
            verification = self.verify_mesh_against_tap(status.get("bed_mesh", {}))
            self.checkpoint(
                Phase.MESH_VERIFY, committed=True, mesh_verification=verification
            )
        self.checkpoint(Phase.FINISH, committed=True, note="Iteration 1 complete")
        self.write_final_report()
        return self.state

    def write_final_report(self) -> None:
        self.store.write_json("final-report.json", asdict(self.state))
        if self.store.enabled:
            report = self.store.path / "final-report.md"
            report.write_text(
                "# IDEX Z Iteration 1 report\n\n"
                f"- Run: `{self.state.run_id}`\n"
                f"- Final committed phase: `{self.state.committed_phase}`\n"
                "- Mesh validation scope: tap-safe region\n"
                "- Measured mesh data: runtime-only; not written to canonical configuration\n",
                encoding="utf-8",
            )

    def run(self) -> RunState:
        self.confirm()
        self.preflight()
        if self.dry_run:
            eddy = self.raw_calibration["eddy_relative_calibration"]["nozzle_to_coil"]
            coil_pose = coil_over_target_pose(
                Pose(REFERENCE_X, REFERENCE_Y, 20.0), Pose(**eddy)
            )
            self.checkpoint(
                Phase.FINISH, committed=True, dry_run=True, coil_pose=asdict(coil_pose)
            )
            return self.state
        summary = self.bootstrap_tap()
        self.update_endstops(summary.median)
        self.verify_center()
        self.calibrate_drive_current(clean_frame=False)
        self.calibrate_eddy_curve()
        self.final_mesh(clean_frame=False)
        self.checkpoint(Phase.FINISH, committed=True, note="Iteration 1 complete")
        self.write_final_report()
        return self.state


def rollback(run_directory: Path, *, host: str, assume_yes: bool) -> None:
    if not assume_yes:
        raise CalibrationError(
            "rollback requires --yes because it deploys a prior configuration"
        )
    calib_backup = run_directory / "calib.yaml.before"
    config_backup = run_directory / "printer.cfg.before"
    if not calib_backup.exists() or not config_backup.exists():
        raise CalibrationError(
            f"run directory lacks rollback snapshots: {run_directory}"
        )
    shutil.copy2(calib_backup, CALIB_PATH)
    shutil.copy2(config_backup, CONFIG_PATH)
    _run_local([sys.executable, str(GENERATOR_PATH), "--check"])
    _run_local([str(DEPLOY_PATH)])
    _run_local([str(DEPLOY_PATH), "--check"])
    MoonrakerClient(host).restart()


def _load_run_state(run_directory: Path, *, strict_hashes: bool = True) -> RunState:
    state_path = run_directory / "state.json"
    if not state_path.exists():
        raise CalibrationError(f"run state is missing: {state_path}")
    try:
        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        state = RunState(
            run_id=state_data["run_id"],
            phase=state_data["phase"],
            workflow_version=int(state_data.get("workflow_version", 0)),
            committed_phase=state_data.get("committed_phase"),
            source_hashes=state_data.get("source_hashes"),
            evidence=state_data.get("evidence"),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"invalid run state: {state_path}") from exc
    if state.workflow_version != WORKFLOW_VERSION:
        raise CalibrationError(
            "run state uses an unsupported workflow version; start a new run"
        )
    saved_hashes = state.source_hashes or {}
    if saved_hashes and saved_hashes != _config_hashes():
        if strict_hashes:
            raise CalibrationError(
                "source hashes changed since the last committed phase"
            )
        _logger.warning(
            "run state source hashes are stale; accepting them for the explicitly "
            "requested direct step and refreshing state after it completes"
        )
    return state


def _make_runner(
    *,
    run_directory: Path | None,
    host: str,
    dry_run: bool,
    assume_yes: bool,
    strict_state_hashes: bool = True,
) -> tuple[Iteration1Runner, bool]:
    if run_directory is None:
        run_directory = RUN_ROOT / utc_run_id()
    else:
        run_directory = run_directory.expanduser().resolve()
    store = ArtifactStore(
        run_directory.parent,
        run_directory.name,
        enabled=not dry_run,
    )
    state_path = run_directory / "state.json"
    existing = state_path.exists()
    runner = Iteration1Runner(
        client=MoonrakerClient(host),
        store=store,
        dry_run=dry_run,
        assume_yes=assume_yes,
        snapshot=not existing,
    )
    if existing:
        runner.state = _load_run_state(run_directory, strict_hashes=strict_state_hashes)
    return runner, existing


def _run_step(runner: Iteration1Runner, step: str) -> RunState:
    """Execute exactly one named workflow step against a persistent run dir."""

    _logger.info("workflow step started: %s", step)
    if step == "run":
        state = runner.run()
    elif step == "resume":
        state = runner.resume()
    elif step == "preflight":
        runner.preflight()
        state = runner.state
    else:
        runner.confirm()
        runner.preflight(
            checkpoint_state=False,
            sync_printer=step == "curve-doctor" and not runner.dry_run,
        )
        if step == "bootstrap-tap":
            runner.bootstrap_tap()
        elif step == "update-endstops":
            summary = (runner.state.evidence or {}).get("bootstrap_summary")
            if not summary:
                raise CalibrationError(
                    "update-endstops requires a committed bootstrap-tap step"
                )
            runner.update_endstops(float(summary["median"]))
        elif step == "center-verify":
            runner.verify_center()
        elif step == "tap-baseline":
            summary = runner.bootstrap_tap()
            runner.update_endstops(summary.median)
            runner.verify_center()
        elif step == "drive-current":
            runner.calibrate_drive_current()
        elif step == "eddy-frequency":
            runner.calibrate_eddy_curve()
        elif step == "curve-doctor":
            runner.doctor_eddy_curve()
        elif step == "mesh":
            runner.final_mesh()
        else:
            raise CalibrationError(f"unsupported calibration step: {step}")
        state = runner.state
    _logger.info(
        "workflow step finished: %s committed_phase=%s",
        step,
        state.committed_phase,
    )
    return state


def _compact_run_summary(state: RunState) -> dict[str, Any]:
    """Extract terminal-sized operator results from the persisted run state."""

    evidence = state.evidence or {}
    summary: dict[str, Any] = {
        "run_id": state.run_id,
        "phase": state.phase,
        "committed_phase": state.committed_phase,
    }
    curve_doctor = evidence.get("curve_doctor")
    if isinstance(curve_doctor, Mapping):
        validation = curve_doctor.get("validation", {})
        pre_reference = curve_doctor.get("pre_reference", {})
        post_reference = curve_doctor.get("post_reference", {})
        anchors = curve_doctor.get("anchors", [])
        results = (
            validation.get("results", []) if isinstance(validation, Mapping) else []
        )
        summary["curve_doctor"] = {
            "retained": not bool(curve_doctor.get("rollback", False)),
            "pre_tap_median": pre_reference.get("median_tap_z"),
            "post_tap_median": post_reference.get("median_tap_z"),
            "anchor_frequencies_hz": [
                {
                    "height": anchor.get("target_height"),
                    "frequency": anchor.get("raw_frequency_hz"),
                    "batch_span_hz": anchor.get("batch_frequency_span_hz"),
                }
                for anchor in anchors
                if isinstance(anchor, Mapping)
            ],
            "validation_residuals": [
                result.get("residual")
                for result in results
                if isinstance(result, Mapping)
            ],
            "validation_span": (
                validation.get("span") if isinstance(validation, Mapping) else None
            ),
        }
    mesh = evidence.get("mesh_verification")
    if isinstance(mesh, Mapping):
        rapid_tap = mesh.get("rapid_mesh_vs_tap")
        rapid_stationary = mesh.get("rapid_mesh_minus_stationary")
        stationary_tap = mesh.get("stationary_eddy_minus_tap")
        active_transform = mesh.get("active_mesh_transform")
        summary["mesh"] = {
            "profile": mesh.get("rapid_mesh_profile"),
            "reloaded": mesh.get("rapid_mesh_reloaded"),
            "point_count": mesh.get("attempted_points"),
            "rapid_mesh_vs_tap": rapid_tap,
            "rapid_mesh_minus_stationary": rapid_stationary,
            "stationary_eddy_minus_tap": stationary_tap,
            "active_transform_delta": (
                active_transform.get("delta_active_minus_clean_raw")
                if isinstance(active_transform, Mapping)
                else None
            ),
            "failure": mesh.get("error", mesh.get("failure")),
        }
    return summary


def _log_run_summary(state: RunState, run_directory: Path) -> None:
    """Log a concise handoff; the full evidence remains in ``state.json``."""

    summary = _compact_run_summary(state)
    _logger.info(
        "run summary: run_id=%s phase=%s committed_phase=%s artifacts=%s",
        summary["run_id"],
        summary["phase"],
        summary["committed_phase"],
        run_directory,
    )
    curve_doctor = summary.get("curve_doctor")
    if isinstance(curve_doctor, Mapping):
        _logger.info(
            "curve-doctor summary: retained=%s pre_tap_median=%s post_tap_median=%s "
            "validation_span=%s residuals=%s",
            curve_doctor["retained"],
            _format_optional_float(curve_doctor["pre_tap_median"]),
            _format_optional_float(curve_doctor["post_tap_median"]),
            _format_optional_float(curve_doctor["validation_span"]),
            ",".join(
                _format_optional_float(value)
                for value in curve_doctor["validation_residuals"]
            ),
        )
        _logger.info(
            "curve-doctor anchors: %s",
            "; ".join(
                "z=%s f=%sHz batch_span=%sHz"
                % (
                    _format_optional_float(anchor["height"]),
                    _format_optional_float(anchor["frequency"], digits=3),
                    _format_optional_float(anchor["batch_span_hz"], digits=3),
                )
                for anchor in curve_doctor["anchor_frequencies_hz"]
            ),
        )
    mesh = summary.get("mesh")
    if isinstance(mesh, Mapping):
        rapid_tap = mesh.get("rapid_mesh_vs_tap")
        rapid_stationary = mesh.get("rapid_mesh_minus_stationary")
        stationary_tap = mesh.get("stationary_eddy_minus_tap")
        _logger.info(
            "mesh summary: profile=%s reloaded=%s points=%s "
            "mesh-vs-Tap(rms=%s,max=%s) mesh-vs-stationary(rms=%s,max=%s) "
            "stationary-vs-Tap(rms=%s,max=%s) active-transform-delta=%s failure=%s",
            mesh.get("profile"),
            mesh.get("reloaded"),
            mesh.get("point_count"),
            _format_optional_float(
                rapid_tap.get("rms") if isinstance(rapid_tap, Mapping) else None
            ),
            _format_optional_float(
                rapid_tap.get("max_abs") if isinstance(rapid_tap, Mapping) else None
            ),
            _format_optional_float(
                rapid_stationary.get("rms")
                if isinstance(rapid_stationary, Mapping)
                else None
            ),
            _format_optional_float(
                rapid_stationary.get("max_abs")
                if isinstance(rapid_stationary, Mapping)
                else None
            ),
            _format_optional_float(
                stationary_tap.get("rms")
                if isinstance(stationary_tap, Mapping)
                else None
            ),
            _format_optional_float(
                stationary_tap.get("max_abs")
                if isinstance(stationary_tap, Mapping)
                else None
            ),
            _format_optional_float(mesh.get("active_transform_delta")),
            mesh.get("failure"),
        )


def _format_optional_float(value: Any, *, digits: int = 6) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--step",
        choices=STEP_CHOICES,
        help="run one named workflow step; use --run-dir to continue it later",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="persistent artifact/state directory for an individual step",
    )
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--rollback", type=Path)
    parser.add_argument("--yes", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    try:
        _logger.info(
            "calibration command: step=%s host=%s run_dir=%s dry_run=%s",
            args.step or "run/resume",
            args.host,
            args.run_dir or args.resume or args.rollback or "(new timestamped run)",
            args.dry_run,
        )
        if args.step and (args.resume or args.rollback):
            raise CalibrationError(
                "--step cannot be combined with --resume or --rollback"
            )
        if args.run_dir and (args.resume or args.rollback):
            raise CalibrationError(
                "--run-dir cannot be combined with --resume or --rollback"
            )
        if args.rollback:
            _logger.info("rollback started: run_dir=%s", args.rollback)
            rollback(args.rollback, host=args.host, assume_yes=args.yes)
            _logger.info("rollback finished")
            return 0
        if args.resume:
            runner, _ = _make_runner(
                run_directory=args.resume,
                host=args.host,
                dry_run=False,
                assume_yes=args.yes,
            )
            state = runner.resume()
            _logger.info("resume finished: committed_phase=%s", state.committed_phase)
            _log_run_summary(state, args.resume)
            return 0
        step = args.step or "run"
        if step == "resume" and args.run_dir is None:
            raise CalibrationError("--step resume requires --run-dir")
        runner, existing = _make_runner(
            run_directory=args.run_dir,
            host=args.host,
            dry_run=args.dry_run,
            assume_yes=args.yes,
            strict_state_hashes=step == "resume",
        )
        if existing and step == "run":
            raise CalibrationError(
                "run directory already has state; use --step resume or choose a new directory"
            )
        if step == "resume" and not existing:
            raise CalibrationError("--step resume requires an existing --run-dir")
        state = _run_step(runner, step)
        _log_run_summary(state, runner.store.path)
        return 0
    except (CalibrationError, subprocess.CalledProcessError, OSError) as exc:
        _logger.error("calibration aborted: %s", exc)
        print(f"Iteration 1 aborted: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
