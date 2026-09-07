#!/usr/bin/env python3
"""Shared access to the flat, measured-only IDEX calibration file."""

from __future__ import annotations

import hashlib
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


MEASURED_SCALAR_KEYS = (
    "t0_x_endstop",
    "t0_y_endstop",
    "t0_z_endstop",
    "t1_x_endstop",
    "t1_y_endstop",
    "t1_z_endstop",
    "input_shaper_t0_x_type",
    "input_shaper_t0_x_frequency_hz",
    "input_shaper_t1_x_type",
    "input_shaper_t1_x_frequency_hz",
    "input_shaper_y_type",
    "input_shaper_y_frequency_hz",
    "eddy_nozzle_to_coil_x_mm",
    "eddy_nozzle_to_coil_y_mm",
    "eddy_nozzle_to_coil_z_mm",
    "eddy_temperature_calibration_c",
    "eddy_reg_drive_current",
    "eddy_tap_threshold",
)
MEASURED_COMPLEX_KEYS = ("eddy_height_calibration", "bed_mesh_points")
MEASURED_KEYS = frozenset((*MEASURED_SCALAR_KEYS, *MEASURED_COMPLEX_KEYS))


class CalibrationDataError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_measured(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CalibrationDataError(f"{path} must contain a YAML mapping")
    missing = MEASURED_KEYS.difference(data)
    extra = set(data).difference(MEASURED_KEYS)
    if missing:
        raise CalibrationDataError(
            f"{path} is missing measured calibration keys: {sorted(missing)}"
        )
    if extra:
        raise CalibrationDataError(
            f"{path} contains non-measurement keys: {sorted(extra)}"
        )
    for key in MEASURED_SCALAR_KEYS:
        if key.endswith("_type"):
            if not isinstance(data[key], str) or not data[key].strip():
                raise CalibrationDataError(f"{key} must be a non-empty string")
            continue
        if isinstance(data[key], bool):
            raise CalibrationDataError(f"{key} must be numeric")
        try:
            value = float(data[key])
        except (TypeError, ValueError):
            raise CalibrationDataError(f"{key} must be numeric") from None
        if not math.isfinite(value):
            raise CalibrationDataError(f"{key} must be finite")
    if not isinstance(data["eddy_height_calibration"], str):
        raise CalibrationDataError("eddy_height_calibration must be a block scalar")
    points = data["bed_mesh_points"]
    if not isinstance(points, list) or not points:
        raise CalibrationDataError("bed_mesh_points must be a non-empty matrix")
    width = len(points[0]) if isinstance(points[0], list) else 0
    if width == 0 or any(
        not isinstance(row, list) or len(row) != width for row in points
    ):
        raise CalibrationDataError("bed_mesh_points must be a rectangular matrix")
    for row in points:
        for point in row:
            try:
                point = float(point)
            except (TypeError, ValueError):
                raise CalibrationDataError("bed_mesh_points must be numeric") from None
            if not math.isfinite(point):
                raise CalibrationDataError("bed_mesh_points must be finite")
    return data


def endstops(data: Mapping[str, Any]) -> dict[str, dict[str, float]]:
    return {
        tool: {
            f"{axis}_endstop": float(data[f"{tool}_{axis}_endstop"])
            for axis in ("x", "y", "z")
        }
        for tool in ("t0", "t1")
    }


def _format_scalar(key: str, value: Any) -> str:
    if key.endswith("_type"):
        if not isinstance(value, str) or not value.strip():
            raise CalibrationDataError(f"{key} must be a non-empty string")
        return value.strip()
    if key in {"eddy_reg_drive_current", "eddy_tap_threshold"}:
        if isinstance(value, bool) or int(value) != value:
            raise CalibrationDataError(f"{key} must be an integer")
        return str(int(value))
    value = float(value)
    if not math.isfinite(value):
        raise CalibrationDataError(f"{key} must be finite")
    digits = 6 if key == "eddy_temperature_calibration_c" else 3
    return f"{value:.{digits}f}"


def _replace_scalar(text: str, key: str, value: Any) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)}:[^\n]*$")
    replacement = f"{key}: {_format_scalar(key, value)}"
    updated, count = pattern.subn(replacement, text)
    if count != 1:
        raise CalibrationDataError(f"expected exactly one {key} field, found {count}")
    return updated


def _replace_mesh(text: str, points: Sequence[Sequence[float]]) -> str:
    if not points or not points[0]:
        raise CalibrationDataError("bed_mesh_points cannot be empty")
    width = len(points[0])
    rows = []
    for row in points:
        if len(row) != width:
            raise CalibrationDataError("bed_mesh_points must be rectangular")
        values = [float(value) for value in row]
        if any(not math.isfinite(value) for value in values):
            raise CalibrationDataError("bed_mesh_points must be finite")
        rows.append("  - [" + ", ".join(f"{value:.6f}" for value in values) + "]")
    block = "bed_mesh_points:\n" + "\n".join(rows)
    pattern = re.compile(r"(?ms)^bed_mesh_points:\n(?:^[ \t].*\n?)*")
    updated, count = pattern.subn(block + "\n", text)
    if count != 1:
        raise CalibrationDataError(
            f"expected exactly one bed_mesh_points block, found {count}"
        )
    return updated


def _replace_block_scalar(text: str, key: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CalibrationDataError(f"{key} must be a non-empty string")
    lines = [line.strip() for line in value.strip().splitlines() if line.strip()]
    block = f"{key}: |\n" + "\n".join(f"  {line}" for line in lines)
    pattern = re.compile(rf"(?ms)^{re.escape(key)}:\s*\|[^\n]*\n(?:^[ \t].*\n?)*")
    updated, count = pattern.subn(block + "\n", text)
    if count != 1:
        raise CalibrationDataError(f"expected exactly one {key} block, found {count}")
    return updated


def atomic_update(
    path: Path,
    updates: Mapping[str, Any],
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    unknown = set(updates).difference(MEASURED_KEYS)
    if unknown:
        raise CalibrationDataError(f"unsupported calibration keys: {sorted(unknown)}")
    if expected_sha256 is not None and sha256_file(path) != expected_sha256:
        raise CalibrationDataError("calib.yaml changed since measurement acquisition")

    original = path.read_text(encoding="utf-8")
    updated = original
    for key, value in updates.items():
        if key == "bed_mesh_points":
            updated = _replace_mesh(updated, value)
        elif key == "eddy_height_calibration":
            updated = _replace_block_scalar(updated, key, value)
        else:
            updated = _replace_scalar(updated, key, value)

    parent = path.parent
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        temporary = Path(temporary_name)
        load_measured(temporary)
        os.replace(temporary, path)
    except BaseException:
        try:
            Path(temporary_name).unlink()
        except FileNotFoundError:
            pass
        raise
    return load_measured(path)
