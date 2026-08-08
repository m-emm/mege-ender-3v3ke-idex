"""Eddy-specific DAQ grid planning and G-code rendering.

This module deliberately contains no printer transport or database access.  The
generic ``daq.py`` CLI owns those concerns and imports this module for the
first DAQ job type.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import yaml


DEFAULT_GRID_X = 11
DEFAULT_GRID_Y = 11
DEFAULT_HEIGHTS = (0.5, 1.0, 1.5, 2.0)
DEFAULT_LEFT_BORDER_MM = 5.0
DEFAULT_SAFE_Z = 5.0
DEFAULT_XY_SPEED = 100.0
DEFAULT_Z_SPEED = 20.0
DEFAULT_SAMPLE_DURATION = 0.5
ASCENT_APPROACH_CLEARANCE = 0.1


@dataclass(frozen=True)
class AxisBounds:
    minimum: float
    maximum: float


@dataclass(frozen=True)
class EddyGridGeometry:
    x: AxisBounds
    y: AxisBounds
    nozzle_x: AxisBounds
    nozzle_y: AxisBounds
    offset_x: float
    offset_y: float
    columns: int
    rows: int

    @property
    def x_pitch(self):
        return (self.x.maximum - self.x.minimum) / (self.columns - 1)

    @property
    def y_pitch(self):
        return (self.y.maximum - self.y.minimum) / (self.rows - 1)


@dataclass(frozen=True)
class GridPoint:
    point_index: int
    row: int
    column: int
    bed_x: float
    bed_y: float
    coil_nozzle_x: float
    coil_nozzle_y: float


def _section(config_text: str, name: str) -> str:
    match = re.search(
        r"^\[%s\]\n(?P<body>.*?)(?=^\[|\Z)" % re.escape(name),
        config_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise ValueError("missing [%s] in printer config" % name)
    return match.group("body")


def _setting(section: str, name: str) -> str:
    match = re.search(
        r"^\s*%s\s*:\s*(?P<value>[^#\n]+)" % re.escape(name),
        section,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError("missing %s in config section" % name)
    return match.group("value").strip()


def _float_setting(config_text: str, section_name: str, setting_name: str) -> float:
    return float(_setting(_section(config_text, section_name), setting_name).split()[0])


def _pair_setting(config_text: str, section_name: str, setting_name: str) -> tuple[float, float]:
    values = _setting(_section(config_text, section_name), setting_name).split(",")
    if len(values) != 2:
        raise ValueError("%s.%s must contain two comma-separated values" % (section_name, setting_name))
    return float(values[0]), float(values[1])


def derive_geometry(
    config_text: str,
    *,
    columns: int = DEFAULT_GRID_X,
    rows: int = DEFAULT_GRID_Y,
    left_border_mm: float = DEFAULT_LEFT_BORDER_MM,
) -> EddyGridGeometry:
    """Intersect T0 nozzle travel, coil reach and configured mesh-safe bed area."""
    if columns < 2 or rows < 2:
        raise ValueError("Eddy DAQ grid needs at least 2 columns and 2 rows")
    if left_border_mm < 0.0:
        raise ValueError("left_border_mm must be non-negative")
    nozzle_x = AxisBounds(
        _float_setting(config_text, "stepper_x", "position_min"),
        _float_setting(config_text, "stepper_x", "position_max"),
    )
    nozzle_y = AxisBounds(
        _float_setting(config_text, "stepper_y", "position_min"),
        _float_setting(config_text, "stepper_y", "position_max"),
    )
    mesh_min_x, mesh_min_y = _pair_setting(config_text, "bed_mesh", "mesh_min")
    mesh_max_x, mesh_max_y = _pair_setting(config_text, "bed_mesh", "mesh_max")
    offset_x = _float_setting(config_text, "probe_eddy_current btt_eddy", "x_offset")
    offset_y = _float_setting(config_text, "probe_eddy_current btt_eddy", "y_offset")
    x_min = max(mesh_min_x + left_border_mm, nozzle_x.minimum + offset_x)
    x_max = min(mesh_max_x, nozzle_x.maximum + offset_x)
    y_min = max(mesh_min_y, nozzle_y.minimum + offset_y)
    y_max = min(mesh_max_y, nozzle_y.maximum + offset_y)
    if x_min >= x_max or y_min >= y_max:
        raise ValueError(
            "no common T0 nozzle/Eddy grid area remains after travel and border limits"
        )
    return EddyGridGeometry(
        x=AxisBounds(x_min, x_max),
        y=AxisBounds(y_min, y_max),
        nozzle_x=nozzle_x,
        nozzle_y=nozzle_y,
        offset_x=offset_x,
        offset_y=offset_y,
        columns=columns,
        rows=rows,
    )


def grid_points(geometry: EddyGridGeometry) -> tuple[GridPoint, ...]:
    """Return rows in serpentine order while preserving logical grid indices."""
    points = []
    for row in range(geometry.rows):
        y = geometry.y.minimum + row * geometry.y_pitch
        columns: Iterable[int] = range(geometry.columns)
        if row % 2:
            columns = reversed(range(geometry.columns))
        for column in columns:
            x = geometry.x.minimum + column * geometry.x_pitch
            points.append(
                GridPoint(
                    point_index=len(points),
                    row=row,
                    column=column,
                    bed_x=x,
                    bed_y=y,
                    coil_nozzle_x=x - geometry.offset_x,
                    coil_nozzle_y=y - geometry.offset_y,
                )
            )
    return tuple(points)


def load_tap_threshold(calib_path: Path) -> float:
    data = yaml.safe_load(calib_path.read_text(encoding="utf-8"))
    try:
        return float(data["eddy_relative_calibration"]["klipper"]["tap_threshold"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("calib.yaml has no numeric Eddy Tap threshold") from exc


def load_endstop_positions(calib_path: Path) -> dict[str, float]:
    data = yaml.safe_load(calib_path.read_text(encoding="utf-8"))
    try:
        tools = data["tools"]
        return {
            "%s_%s_endstop" % (tool, axis): float(tools[tool][axis + "_endstop"])
            for tool in ("t0", "t1")
            for axis in ("x", "y", "z")
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("calib.yaml has incomplete numeric T0/T1 endstops") from exc


def fingerprint(*paths: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def render_gcode(
    *,
    job_id: str,
    geometry: EddyGridGeometry,
    tap_threshold: float,
    tap_count: int = 1,
    heights: tuple[float, ...] = DEFAULT_HEIGHTS,
    sample_duration: float = DEFAULT_SAMPLE_DURATION,
    safe_z: float = DEFAULT_SAFE_Z,
    xy_speed: float = DEFAULT_XY_SPEED,
    z_speed: float = DEFAULT_Z_SPEED,
    config_fingerprint: str,
    endstop_positions: dict[str, float],
) -> str:
    if tap_count < 1:
        raise ValueError("tap_count must be at least one")
    if not heights or any(value <= 0.0 for value in heights):
        raise ValueError("heights must contain positive values")
    if any(right <= left for left, right in zip(heights, heights[1:])):
        raise ValueError("heights must be strictly ascending for a Z-spindle sweep")
    if heights[0] - ASCENT_APPROACH_CLEARANCE <= 0.0:
        raise ValueError("lowest height needs room for the upward approach")
    points = grid_points(geometry)
    expected_records = len(points) * (tap_count + len(heights))
    lines = [
        "; Generated printer DAQ Eddy grid; do not edit while running.",
        "G90",
        "G28",
        "T0",
        "BED_MESH_CLEAR",
        "DAQ_JOB_START JOB_ID=%s JOB_TYPE=eddy_grid EXPECTED_RECORDS=%d"
        % (job_id, expected_records),
        "DAQ_EDDY_CONTEXT JOB_ID=%s GRID_X=%d GRID_Y=%d X_MIN=%.6f X_MAX=%.6f "
        "Y_MIN=%.6f Y_MAX=%.6f TAP_COUNT=%d TAP_THRESHOLD=%.3f HEIGHTS=%s "
        "DURATION=%.3f XY_SPEED=%.3f SAFE_Z=%.3f CONFIG_FINGERPRINT=%s "
        "T0_X_ENDSTOP=%.6f T0_Y_ENDSTOP=%.6f T0_Z_ENDSTOP=%.6f "
        "T1_X_ENDSTOP=%.6f T1_Y_ENDSTOP=%.6f T1_Z_ENDSTOP=%.6f"
        % (
            job_id,
            geometry.columns,
            geometry.rows,
            geometry.x.minimum,
            geometry.x.maximum,
            geometry.y.minimum,
            geometry.y.maximum,
            tap_count,
            tap_threshold,
            ",".join("%.3f" % height for height in heights),
            sample_duration,
            xy_speed,
            safe_z,
            config_fingerprint,
            endstop_positions["t0_x_endstop"],
            endstop_positions["t0_y_endstop"],
            endstop_positions["t0_z_endstop"],
            endstop_positions["t1_x_endstop"],
            endstop_positions["t1_y_endstop"],
            endstop_positions["t1_z_endstop"],
        ),
    ]
    record_index = 0
    xy_feed = xy_speed * 60.0
    z_feed = z_speed * 60.0
    for point in points:
        lines.extend(
            [
                "M117 DAQ %d/%d Tap" % (point.point_index + 1, len(points)),
                "G1 Z%.3f F%.0f" % (safe_z, z_feed),
                "G1 X%.6f Y%.6f F%.0f" % (point.bed_x, point.bed_y, xy_feed),
            ]
        )
        for tap_index in range(tap_count):
            lines.append(
                "DAQ_EDDY_TAP JOB_ID=%s RECORD_INDEX=%d POINT_INDEX=%d TAP_INDEX=%d "
                "X=%.6f Y=%.6f THRESHOLD=%.3f"
                % (
                    job_id,
                    record_index,
                    point.point_index,
                    tap_index,
                    point.bed_x,
                    point.bed_y,
                    tap_threshold,
                )
            )
            record_index += 1
        lines.extend(
            [
                "G1 Z%.3f F%.0f" % (safe_z, z_feed),
                "G1 X%.6f Y%.6f F%.0f"
                % (point.coil_nozzle_x, point.coil_nozzle_y, xy_feed),
                "G1 Z%.6f F%.0f"
                % (heights[0] - ASCENT_APPROACH_CLEARANCE, z_feed),
            ]
        )
        for height_index, height in enumerate(heights):
            lines.extend(
                [
                    "G1 Z%.6f F%.0f" % (height, z_feed),
                    "DAQ_EDDY_SAMPLE JOB_ID=%s RECORD_INDEX=%d POINT_INDEX=%d "
                    "HEIGHT_INDEX=%d X=%.6f Y=%.6f Z=%.6f DURATION=%.3f"
                    % (
                        job_id,
                        record_index,
                        point.point_index,
                        height_index,
                        point.bed_x,
                        point.bed_y,
                        height,
                        sample_duration,
                    ),
                ]
            )
            record_index += 1
    lines.extend(
        [
            "G1 Z%.3f F%.0f" % (safe_z, z_feed),
            "DAQ_JOB_FINISH JOB_ID=%s" % job_id,
            "M117 DAQ complete",
        ]
    )
    assert record_index == expected_records
    return "\n".join(lines) + "\n"


def manifest(
    *,
    job_id: str,
    geometry: EddyGridGeometry,
    tap_threshold: float,
    tap_count: int,
    heights: tuple[float, ...],
    sample_duration: float,
    safe_z: float,
    xy_speed: float,
    z_speed: float,
    config_fingerprint: str,
    endstop_positions: dict[str, float],
) -> dict:
    points = grid_points(geometry)
    return {
        "schema_version": 1,
        "job_id": job_id,
        "job_type": "eddy_grid",
        "geometry": asdict(geometry),
        "grid_point_count": len(points),
        "expected_records": len(points) * (tap_count + len(heights)),
        "tap_threshold": tap_threshold,
        "tap_count": tap_count,
        "heights": list(heights),
        "sample_duration": sample_duration,
        "safe_z": safe_z,
        "xy_speed": xy_speed,
        "z_speed": z_speed,
        "config_fingerprint": config_fingerprint,
        "calibration_endstops": dict(endstop_positions),
        "points": [asdict(point) for point in points],
    }
