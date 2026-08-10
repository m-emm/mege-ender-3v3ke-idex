#!/usr/bin/env python3
"""Report-only combined T0/T1 nozzle image X/Z sweep."""

from __future__ import annotations

import hashlib
import logging
import math
from pathlib import Path
from typing import Any

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares
from scipy.stats import theilslopes
from vision_four_fiducials import FourFiducialError, detect_four_fiducials
from vision_nozzle_tip_localization import (
    NozzleTipLocalizationError,
    localize_nozzle_tip_grid,
)

_logger = logging.getLogger(__name__)

PLOT_COLORS = (
    "#0072B2",  # blue
    "#D55E00",  # vermilion
    "#009E73",  # green
    "#CC79A7",  # purple
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#A6761D",  # ochre
    "#332288",  # indigo
)

# Temporary guard: retain the overlay implementation for later re-enablement,
# but avoid the image reloads and artifact writes while the report is plot-only.
GENERATE_OVERLAYS = False

MIN_SHARED_CURVE_CORRELATION = 0.95
SHARED_CURVE_F_SCALE_PX_PER_MM = 0.03
SHARED_CURVE_OUTLIER_SIGMA = 4.0
SHARED_CURVE_MIN_OUTLIER_LIMIT_PX_PER_MM = 0.09
MINIMUM_TIP_CORRELATION = 0.22
MINIMUM_MEDIAN_TIP_CORRELATION = 0.38
MAXIMUM_REPRESENTATION_SPREAD_PX = 2.5


class ToolXZSweepError(RuntimeError):
    pass


def _finite(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(item) for item in value]
    if isinstance(value, np.ndarray):
        return _finite(value.tolist())
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.floating, float)):
        item = float(value)
        return item if math.isfinite(item) else None
    if isinstance(value, (np.integer, int)):
        return int(value)
    return value


def _artifact(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _number(mapping: dict[str, Any], key: str, context: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ToolXZSweepError(f"{context}.{key} must be finite and numeric")
    return float(value)


def _vector(value: Any, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise ToolXZSweepError(f"{name} must contain two finite values")
    return result


def _tool_marker_vector(marker: dict[str, Any], tool: str) -> np.ndarray:
    quality = marker.get("quality")
    vectors = (
        quality.get("tool_axis_vectors_px_per_mm")
        if isinstance(quality, dict)
        else None
    )
    if not isinstance(vectors, dict):
        raise ToolXZSweepError(f"{tool} marker reference lacks its image motion vector")
    return _vector(vectors.get(tool), f"{tool} marker image motion vector")


def _x_vector_at_capture(mapping: dict[str, Any], capture_y_mm: float) -> np.ndarray:
    model = mapping.get("fiducial_x_vector_model_px_per_mm")
    if not isinstance(model, dict):
        raise ToolXZSweepError("fiducial mapping lacks its X-vector model")
    reference = _vector(model.get("reference_vector_px_per_mm"), "X-vector reference")
    slope = _vector(
        model.get("capture_y_slope_px_per_mm_per_mm"),
        "X-vector capture-Y slope",
    )
    reference_y = _number(model, "reference_capture_y_mm", "X-vector model")
    return reference + slope * (float(capture_y_mm) - reference_y)


def _active_tool_state(resolved: dict[str, Any]) -> dict[str, Any]:
    snapshot = resolved.get("active_tool_calibration")
    if not isinstance(snapshot, dict):
        raise ToolXZSweepError("preflight lacks loaded tool calibration")
    endstops = snapshot.get("tool_xy_endstops_mm")
    offsets = snapshot.get("tool_y_offsets_mm")
    if not isinstance(endstops, dict) or not isinstance(offsets, dict):
        raise ToolXZSweepError("loaded tool calibration is incomplete")
    return snapshot


def _tool_reference(
    tool: str,
    *,
    definition: dict[str, Any],
    input_values: dict[str, Any],
    resolved: dict[str, Any],
) -> dict[str, Any]:
    tool_key = tool.lower()
    snapshot = _active_tool_state(resolved)
    endstops = snapshot["tool_xy_endstops_mm"]
    offsets = snapshot["tool_y_offsets_mm"]
    try:
        t0_y_endstop = float(endstops["t0"]["y"])
        selected_y_endstop = float(endstops[tool_key]["y"])
        selected_y_offset = float(offsets[tool_key])
    except (KeyError, TypeError, ValueError):
        raise ToolXZSweepError(
            f"loaded {tool} calibration has invalid Y values"
        ) from None

    gap = _number(definition, "capture_endstop_gap_mm", "job definition")
    if gap <= 0.0:
        raise ToolXZSweepError("capture position must remain beyond the Y endstop")
    capture_y = selected_y_endstop + gap
    internal_y = capture_y + selected_y_offset
    if internal_y - t0_y_endstop <= 0.0:
        raise ToolXZSweepError(
            "derived internal capture Y must remain beyond the T0 endstop"
        )

    axis_minimum = resolved.get("axis_minimum")
    axis_maximum = resolved.get("axis_maximum")
    if not isinstance(axis_minimum, list) or not isinstance(axis_maximum, list):
        raise ToolXZSweepError("preflight motion limits are unavailable")
    if not float(axis_minimum[1]) <= internal_y <= float(axis_maximum[1]):
        raise ToolXZSweepError(
            f"derived internal capture Y {internal_y:.6f} is outside loaded limits "
            f"[{float(axis_minimum[1]):.6f}, {float(axis_maximum[1]):.6f}]"
        )

    metric = input_values.get("bed_metric")
    mapping = input_values.get("bed_fiducial_printer_xy_mapping")
    marker = input_values.get(f"{tool_key}_red_marker_offset")
    if not all(isinstance(item, dict) for item in (metric, mapping, marker)):
        raise ToolXZSweepError(f"{tool} X/Z sweep inputs are incomplete")

    image_y_vector = _vector(
        metric.get("image_y_axis_vector_px_per_mm"),
        "bed metric image Y vector",
    )
    reference_centers = np.asarray(
        metric.get("reference_marker_centers_px"), dtype=np.float64
    )
    if reference_centers.shape != (4, 2) or not np.all(np.isfinite(reference_centers)):
        raise ToolXZSweepError("bed metric requires four reference marker centers")
    metric_reference_y = _number(metric, "reference_capture_y_mm", "bed metric")
    patch_center_at_capture = np.mean(reference_centers, axis=0) + image_y_vector * (
        internal_y - metric_reference_y
    )
    image_x_vector = _x_vector_at_capture(mapping, internal_y)
    corner_xy = _vector(mapping.get("corner_printer_xy_mm"), "bed corner printer XY")
    fiducial_xy = _vector(
        mapping.get("fiducial_reference_printer_xy_mm"),
        "fiducial reference printer XY",
    )
    corner_pixel_at_capture = (
        patch_center_at_capture
        + image_x_vector * (corner_xy[0] - fiducial_xy[0])
        + image_y_vector * (corner_xy[1] - fiducial_xy[1])
    )
    marker_offset = _number(marker, "offset_mm", f"{tool} marker reference")
    marker_reference_x = _number(
        marker,
        "reference_commanded_x_mm",
        f"{tool} marker reference",
    )
    marker_x_vector = _tool_marker_vector(marker, tool)

    return {
        "tool": tool,
        "capture_y_mm": capture_y,
        "internal_capture_y_mm": internal_y,
        "capture_endstop_gap_mm": gap,
        "image_x_vector_px_per_mm": image_x_vector,
        "image_y_vector_px_per_mm": image_y_vector,
        "marker_x_vector_px_per_mm": marker_x_vector,
        "corner_printer_xy_mm": corner_xy,
        "fiducial_reference_printer_xy_mm": fiducial_xy,
        "corner_pixel_at_capture_px": corner_pixel_at_capture,
        "marker_offset_mm": marker_offset,
        "marker_reference_commanded_x_mm": marker_reference_x,
    }


def prepare_sweep(
    definition: dict[str, Any],
    *,
    input_values: dict[str, Any],
    resolved: dict[str, Any],
) -> dict[str, Any]:
    tools = definition.get("tools")
    if tools != ["T0", "T1"]:
        raise ToolXZSweepError("X/Z sweep must configure T0 followed by T1")

    x_offsets = [
        _number({"value": value}, "value", "X offsets")
        for value in definition.get("x_offsets_from_bed_tab_mm", [])
    ]
    z_positions = [
        _number({"value": value}, "value", "Z positions")
        for value in definition.get("z_positions_mm", [])
    ]
    if not x_offsets or not z_positions:
        raise ToolXZSweepError("X/Z sweep requires non-empty X and Z positions")

    partial = input_values.get("partial_bed_coordinate_system")
    if not isinstance(partial, dict):
        raise ToolXZSweepError("X/Z sweep lacks the bed-tab coordinate system")
    corner_xy = _vector(
        partial.get("corner_printer_xyz_mm", [])[:2], "bed corner printer XY"
    )

    axis_minimum = resolved.get("axis_minimum")
    axis_maximum = resolved.get("axis_maximum")
    if not isinstance(axis_minimum, list) or not isinstance(axis_maximum, list):
        raise ToolXZSweepError("preflight motion limits are unavailable")

    references = {}
    frames = []
    for tool in tools:
        reference = _tool_reference(
            tool,
            definition=definition,
            input_values=input_values,
            resolved=resolved,
        )
        references[tool.lower()] = reference
        for z_mm in z_positions:
            for offset_x in x_offsets:
                x_mm = float(corner_xy[0]) + offset_x
                y_mm = float(reference["capture_y_mm"])
                if not float(axis_minimum[0]) <= x_mm <= float(axis_maximum[0]):
                    raise ToolXZSweepError(
                        f"{tool} commanded X {x_mm:.6f} is out of limits"
                    )
                if not float(axis_minimum[2]) <= z_mm <= float(axis_maximum[2]):
                    raise ToolXZSweepError(f"commanded Z {z_mm:.6f} is out of limits")
                expected_marker = reference["corner_pixel_at_capture_px"] + reference[
                    "marker_x_vector_px_per_mm"
                ] * (
                    reference["marker_offset_mm"]
                    + x_mm
                    - reference["marker_reference_commanded_x_mm"]
                )
                seq = len(frames)
                frames.append(
                    {
                        "seq": seq,
                        "frame": (
                            f"{seq:02d}_{tool.lower()}_x{x_mm:.3f}_z{z_mm:.3f}"
                        ).replace(".", "p"),
                        "camera": "nozzle_cam",
                        "profile": definition["profile"],
                        "tool": tool,
                        "x_offset_from_bed_tab_mm": offset_x,
                        "x_mm": x_mm,
                        "y_mm": y_mm,
                        "z_mm": z_mm,
                        "expected_marker_pixel_px": expected_marker.tolist(),
                        "discard_fresh_frames": int(definition["discard_fresh_frames"]),
                        "commanded_position_mm": [x_mm, y_mm, z_mm],
                    }
                )

    return _finite(
        {
            "frames": frames,
            "references": references,
            "active_tool_calibration": _active_tool_state(resolved),
            "x_offsets_from_bed_tab_mm": x_offsets,
            "z_positions_mm": z_positions,
        }
    )


def _base_record(frame: dict[str, Any]) -> dict[str, Any]:
    x_mm, y_mm, z_mm = [float(item) for item in frame["commanded_position_mm"]]
    return {
        "seq": int(frame["seq"]),
        "tool": frame["tool"],
        "commanded_x_mm": x_mm,
        "commanded_y_mm": y_mm,
        "commanded_z_mm": z_mm,
        "nozzle_uv_px": None,
        "fiducial_centers_uv_px": None,
        "fiducial_fit": None,
        "fiducial_centroid_uv_px": None,
        "nozzle_detected": False,
        "accepted_for_u_x_fit": False,
        "u_x_fit_rejection_reasons": [],
        "fiducials_detected": False,
        "reasons": [],
    }


def _registration_fit_reasons(registration: dict[str, Any]) -> list[str]:
    required = (
        "minimum_correlation",
        "median_correlation",
        "representation_spread_px",
        "tip_prediction_error_px",
        "maximum_tip_prediction_error_px",
    )
    missing = [key for key in required if registration.get(key) is None]
    if missing:
        return ["localization quality metrics are incomplete: " + ", ".join(missing)]

    reasons = []
    if float(registration["minimum_correlation"]) < MINIMUM_TIP_CORRELATION:
        reasons.append(
            f"minimum tip correlation is below {MINIMUM_TIP_CORRELATION:.2f}"
        )
    if float(registration["median_correlation"]) < MINIMUM_MEDIAN_TIP_CORRELATION:
        reasons.append(
            "median tip correlation is below " f"{MINIMUM_MEDIAN_TIP_CORRELATION:.2f}"
        )
    if (
        float(registration["representation_spread_px"])
        > MAXIMUM_REPRESENTATION_SPREAD_PX
    ):
        reasons.append(
            "gray/contrast tip registrations disagree by more than "
            f"{MAXIMUM_REPRESENTATION_SPREAD_PX:.1f} px"
        )
    if float(registration["tip_prediction_error_px"]) > float(
        registration["maximum_tip_prediction_error_px"]
    ):
        reasons.append("physical-tip registration moved too far from its detector seed")
    return reasons


def _write_overlay(
    image: np.ndarray,
    frame: dict[str, Any],
    record: dict[str, Any],
    path: Path,
) -> None:
    overlay = image.copy()
    color = (0, 255, 0) if record["nozzle_detected"] else (0, 0, 255)
    centers = record.get("fiducial_centers_uv_px") or []
    radii = record.get("fiducial_radii_px") or []
    for index, center in enumerate(centers):
        radius = int(round(float(radii[index]))) if index < len(radii) else 8
        cv2.circle(
            overlay,
            tuple(np.rint(center).astype(int)),
            max(2, radius),
            (0, 255, 255),
            2,
        )
    fiducial_fit = record.get("fiducial_fit") or {}
    patch_corners = fiducial_fit.get("patch_corners_px")
    if patch_corners:
        patch = np.rint(np.asarray(patch_corners, dtype=np.float64)).astype(np.int32)
        cv2.polylines(overlay, [patch.reshape(-1, 1, 2)], True, (255, 180, 0), 2)
    locator = fiducial_fit.get("locator") or {}
    marker_corners = locator.get("marker_corners_px")
    if marker_corners:
        marker = np.rint(np.asarray(marker_corners, dtype=np.float64)).astype(np.int32)
        cv2.polylines(overlay, [marker.reshape(-1, 1, 2)], True, (255, 0, 255), 2)
    if record.get("fiducial_centroid_uv_px") is not None:
        cv2.drawMarker(
            overlay,
            tuple(np.rint(record["fiducial_centroid_uv_px"]).astype(int)),
            (255, 0, 255),
            cv2.MARKER_CROSS,
            20,
            2,
        )
    if record.get("nozzle_uv_px") is not None:
        cv2.drawMarker(
            overlay,
            tuple(np.rint(record["nozzle_uv_px"]).astype(int)),
            color,
            cv2.MARKER_CROSS,
            24,
            3,
        )
    localization = record.get("localization") or {}
    for key, marker_color, marker_type in (
        ("predicted_tip_center_px", (0, 165, 255), cv2.MARKER_TILTED_CROSS),
        ("tip_detector_center_px", (255, 0, 0), cv2.MARKER_STAR),
    ):
        point = localization.get(key)
        if point is not None:
            cv2.drawMarker(
                overlay,
                tuple(np.rint(point).astype(int)),
                marker_color,
                marker_type,
                22,
                2,
            )
    nozzle = record["nozzle_uv_px"]
    nozzle_text = (
        f"nozzle u/v={float(nozzle[0]):.2f},{float(nozzle[1]):.2f} px"
        if nozzle is not None
        else "nozzle u/v=n/a"
    )
    lines = [
        (
            f"{frame['tool']} X={record['commanded_x_mm']:.3f} "
            f"Y={record['commanded_y_mm']:.3f} Z={record['commanded_z_mm']:.3f}"
        ),
        nozzle_text,
        (
            "fiducial centroid="
            + (
                f"{record['fiducial_centroid_uv_px'][0]:.2f},"
                f"{record['fiducial_centroid_uv_px'][1]:.2f} px"
                if record["fiducial_centroid_uv_px"] is not None
                else "n/a"
            )
        ),
        (
            "fiducial fit="
            + (
                f"right={float(fiducial_fit['right_edge_angle_deg']):+.2f}deg "
                f"down={float(fiducial_fit['down_edge_angle_deg']):+.2f}deg"
                if fiducial_fit.get("right_edge_angle_deg") is not None
                else "n/a"
            )
        ),
        "detected" if record["nozzle_detected"] else "nozzle not detected",
    ]
    if localization:
        lines.append(
            "tip fit="
            f"corr={float(localization.get('minimum_correlation', 0.0)):.3f}/"
            f"{float(localization.get('median_correlation', 0.0)):.3f} "
            f"pred_err={float(localization.get('tip_prediction_error_px', 0.0)):.2f}px"
        )
    if record["reasons"]:
        lines.append("reasons: " + " | ".join(record["reasons"]))
    for index, line in enumerate(lines):
        origin = (24, 40 + 30 * index)
        cv2.putText(
            overlay,
            line,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (0, 0, 0),
            7,
            cv2.LINE_AA,
        )
        cv2.putText(
            overlay,
            line,
            origin,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            color,
            2,
            cv2.LINE_AA,
        )
    if not cv2.imwrite(str(path), overlay):
        raise ToolXZSweepError(f"could not write overlay {path}")


def _write_u_plot(records: list[dict[str, Any]], path: Path) -> None:
    figure, axis = plt.subplots(figsize=(10, 6))
    markers = {"T0": "o", "T1": "s"}
    line_styles = {"T0": "-", "T1": "--"}
    series_index = 0
    for tool in ("T0", "T1"):
        for z_mm in sorted(
            {
                float(record["commanded_z_mm"])
                for record in records
                if record["tool"] == tool
            }
        ):
            row = [
                record
                for record in records
                if record["tool"] == tool
                and abs(float(record["commanded_z_mm"]) - z_mm) < 1.0e-9
            ]
            row.sort(key=lambda record: float(record["commanded_x_mm"]))
            x_values = [float(record["commanded_x_mm"]) for record in row]
            u_values = [
                (
                    float(record["nozzle_uv_px"][0])
                    if record["nozzle_uv_px"] is not None
                    else np.nan
                )
                for record in row
            ]
            axis.plot(
                x_values,
                u_values,
                marker=markers[tool],
                linestyle=line_styles[tool],
                color=PLOT_COLORS[series_index % len(PLOT_COLORS)],
                linewidth=2.0,
                markersize=6.0,
                label=f"{tool} Z={z_mm:g} mm",
            )
            series_index += 1
    axis.set_title("Nozzle image u coordinate versus commanded X")
    axis.set_xlabel("Commanded X (mm)")
    axis.set_ylabel("Nozzle u (px)")
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _fit_robust_u_x_slope(records: list[dict[str, Any]]) -> float | None:
    usable = [
        record
        for record in records
        if record["nozzle_uv_px"] is not None
        and record.get("accepted_for_u_x_fit", True)
    ]
    if len(usable) < 3:
        return None

    x_values = np.asarray(
        [float(record["commanded_x_mm"]) for record in usable],
        dtype=np.float64,
    )
    u_values = np.asarray(
        [float(record["nozzle_uv_px"][0]) for record in usable],
        dtype=np.float64,
    )
    if len(np.unique(x_values)) < 2:
        return None

    slope, _intercept, _, _ = theilslopes(u_values, x_values)
    return float(slope)


def _u_x_correlation(x_values: np.ndarray, u_values: np.ndarray) -> float | None:
    if (
        len(x_values) < 3
        or len(np.unique(x_values)) < 2
        or len(np.unique(u_values)) < 2
    ):
        return None
    correlation = float(np.corrcoef(x_values, u_values)[0, 1])
    return correlation if math.isfinite(correlation) else None


def _fit_u_x_models(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fit robust ``u = intercept + slope * commanded_x`` tool/Z models."""
    fits = []
    z_positions = sorted(
        {
            float(record["commanded_z_mm"])
            for record in records
            if record["tool"] in {"T0", "T1"}
        }
    )
    for tool in ("T0", "T1"):
        for z_mm in z_positions:
            usable = [
                record
                for record in records
                if record["tool"] == tool
                and abs(float(record["commanded_z_mm"]) - z_mm) < 1.0e-9
                and record["nozzle_uv_px"] is not None
                and record.get("accepted_for_u_x_fit", True)
            ]
            row_records = [
                record
                for record in records
                if record["tool"] == tool
                and abs(float(record["commanded_z_mm"]) - z_mm) < 1.0e-9
            ]
            usable.sort(key=lambda record: float(record["commanded_x_mm"]))
            x_values = np.asarray(
                [float(record["commanded_x_mm"]) for record in usable],
                dtype=np.float64,
            )
            u_values = np.asarray(
                [float(record["nozzle_uv_px"][0]) for record in usable],
                dtype=np.float64,
            )
            fit = {
                "tool": tool,
                "z_mm": z_mm,
                "sample_count": int(len(usable)),
                "rejected_sample_count": sum(
                    record["nozzle_uv_px"] is not None
                    and not record.get("accepted_for_u_x_fit", True)
                    for record in row_records
                ),
                "fit_method": "theil_sen",
                "u_x_correlation_coefficient": _u_x_correlation(x_values, u_values),
                "slope_u_px_per_mm": None,
                "intercept_u_px": None,
                "fit_rms_px": None,
                "x_values_mm": x_values.tolist(),
                "u_values_px": u_values.tolist(),
            }
            slope = _fit_robust_u_x_slope(usable)
            if slope is None:
                fit["reason"] = (
                    "fewer than three usable nozzle detections"
                    if len(usable) < 3
                    else "commanded X values do not span a robust linear fit"
                )
                _logger.info(
                    "Robust nozzle u(x) fit unavailable tool=%s z_mm=%.3f "
                    "samples=%d reason=%s",
                    tool,
                    z_mm,
                    len(usable),
                    fit["reason"],
                )
                fits.append(fit)
                continue

            intercept = float(np.median(u_values - slope * x_values))
            residuals = u_values - (slope * x_values + intercept)
            fit["slope_u_px_per_mm"] = slope
            fit["intercept_u_px"] = intercept
            fit["fit_rms_px"] = float(np.sqrt(np.mean(residuals**2)))
            _logger.info(
                "Fitted robust nozzle u(x) tool=%s z_mm=%.3f samples=%d "
                "method=theil_sen slope=%.6f px/mm intercept=%.3f px "
                "fit_rms=%.3f px",
                tool,
                z_mm,
                len(usable),
                fit["slope_u_px_per_mm"],
                fit["intercept_u_px"],
                fit["fit_rms_px"],
            )
            fits.append(fit)
    return fits


def _shared_curve_arrays(
    fits: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        np.asarray([float(fit["z_mm"]) for fit in fits], dtype=np.float64),
        np.asarray(
            [float(fit["slope_u_px_per_mm"]) for fit in fits],
            dtype=np.float64,
        ),
        np.asarray(
            [fit["tool"] == "T1" for fit in fits],
            dtype=np.float64,
        ),
    )


def _shared_curve_is_identifiable(fits: list[dict[str, Any]]) -> bool:
    tools = {fit["tool"] for fit in fits}
    z_positions = {float(fit["z_mm"]) for fit in fits}
    return (
        len(fits) >= 6
        and tools == {"T0", "T1"}
        and sum(fit["tool"] == "T0" for fit in fits) >= 2
        and sum(fit["tool"] == "T1" for fit in fits) >= 2
        and len(z_positions) >= 3
    )


def _least_squares_shared_curve(fits: list[dict[str, Any]]):
    z_values, slope_values, is_t1 = _shared_curve_arrays(fits)

    def residuals(parameters: np.ndarray) -> np.ndarray:
        a, b, c, t1_z_delta = parameters
        physical_z = z_values + is_t1 * t1_z_delta
        predicted = a + b * physical_z + c * physical_z**2
        return predicted - slope_values

    result = least_squares(
        residuals,
        x0=np.asarray([9.85, -0.1, 0.0, -0.6], dtype=np.float64),
        loss="soft_l1",
        f_scale=SHARED_CURVE_F_SCALE_PX_PER_MM,
        bounds=(
            [-np.inf, -np.inf, -np.inf, -1.5],
            [np.inf, np.inf, np.inf, 1.5],
        ),
    )
    return result, residuals


def estimate_tool_z_delta(fits: list[dict[str, Any]]) -> dict[str, Any]:
    excluded_rows = []
    quality_rows = []
    for fit in fits:
        row = {
            "tool": fit["tool"],
            "z_mm": float(fit["z_mm"]),
            "slope_u_px_per_mm": fit.get("slope_u_px_per_mm"),
            "u_x_correlation_coefficient": fit.get("u_x_correlation_coefficient"),
        }
        slope = fit.get("slope_u_px_per_mm")
        correlation = fit.get("u_x_correlation_coefficient")
        if slope is None:
            row["reason"] = "missing_u_x_slope"
            excluded_rows.append(row)
            continue
        if correlation is None or float(correlation) < MIN_SHARED_CURVE_CORRELATION:
            row["reason"] = "bad_u_x_correlation"
            row["minimum_correlation"] = MIN_SHARED_CURVE_CORRELATION
            excluded_rows.append(row)
            continue
        quality_rows.append(fit)

    if not _shared_curve_is_identifiable(quality_rows):
        reason = (
            "shared Z curve requires at least six correlated slope rows, both "
            "tools, at least two rows per tool, and three distinct Z heights"
        )
        _logger.info(
            "Shared nozzle slope curve unavailable quality_rows=%d excluded_rows=%d reason=%s",
            len(quality_rows),
            len(excluded_rows),
            reason,
        )
        return {
            "available": False,
            "fit_method": "quadratic_soft_l1_with_mad_prefilter",
            "reason": reason,
            "included_rows": [],
            "excluded_rows": excluded_rows,
        }

    initial_result, initial_residuals_fn = _least_squares_shared_curve(quality_rows)
    if not initial_result.success:
        reason = f"initial shared-curve optimization failed: {initial_result.message}"
        _logger.info("Shared nozzle slope curve unavailable reason=%s", reason)
        return {
            "available": False,
            "fit_method": "quadratic_soft_l1_with_mad_prefilter",
            "reason": reason,
            "included_rows": [],
            "excluded_rows": excluded_rows,
        }

    initial_residuals = initial_residuals_fn(initial_result.x)
    residual_center = float(np.median(initial_residuals))
    residual_mad = float(np.median(np.abs(initial_residuals - residual_center)))
    robust_sigma = 1.4826 * residual_mad
    residual_limit = max(
        SHARED_CURVE_MIN_OUTLIER_LIMIT_PX_PER_MM,
        SHARED_CURVE_OUTLIER_SIGMA * robust_sigma,
    )
    retained_rows = []
    for fit, residual in zip(quality_rows, initial_residuals):
        centered_residual = abs(float(residual) - residual_center)
        if centered_residual <= residual_limit:
            retained_rows.append(fit)
            continue
        excluded_rows.append(
            {
                "tool": fit["tool"],
                "z_mm": float(fit["z_mm"]),
                "slope_u_px_per_mm": float(fit["slope_u_px_per_mm"]),
                "u_x_correlation_coefficient": fit.get("u_x_correlation_coefficient"),
                "reason": "shared_curve_residual_outlier",
                "initial_residual_px_per_mm": float(residual),
                "residual_limit_px_per_mm": residual_limit,
            }
        )

    if not _shared_curve_is_identifiable(retained_rows):
        reason = "too few shared-curve rows remain after outlier rejection"
        _logger.info(
            "Shared nozzle slope curve unavailable retained_rows=%d reason=%s",
            len(retained_rows),
            reason,
        )
        return {
            "available": False,
            "fit_method": "quadratic_soft_l1_with_mad_prefilter",
            "reason": reason,
            "outlier_residual_limit_px_per_mm": residual_limit,
            "included_rows": [],
            "excluded_rows": excluded_rows,
        }

    result, residuals_fn = _least_squares_shared_curve(retained_rows)
    if not result.success:
        reason = f"final shared-curve optimization failed: {result.message}"
        _logger.info("Shared nozzle slope curve unavailable reason=%s", reason)
        return {
            "available": False,
            "fit_method": "quadratic_soft_l1_with_mad_prefilter",
            "reason": reason,
            "outlier_residual_limit_px_per_mm": residual_limit,
            "included_rows": [],
            "excluded_rows": excluded_rows,
        }

    final_residuals = residuals_fn(result.x)
    included_rows = [
        {
            "tool": fit["tool"],
            "z_mm": float(fit["z_mm"]),
            "slope_u_px_per_mm": float(fit["slope_u_px_per_mm"]),
            "u_x_correlation_coefficient": fit.get("u_x_correlation_coefficient"),
            "residual_px_per_mm": float(residual),
        }
        for fit, residual in zip(retained_rows, final_residuals)
    ]
    a, b, c, t1_z_delta = result.x
    _logger.info(
        "Fitted shared nozzle slope curve rows=%d excluded=%d "
        "t1_z_delta_mm=%.6f rms_slope_px_per_mm=%.6f",
        len(retained_rows),
        len(excluded_rows),
        float(t1_z_delta),
        float(np.sqrt(np.mean(final_residuals**2))),
    )
    return {
        "available": True,
        "fit_method": "quadratic_soft_l1_with_mad_prefilter",
        "curve_intercept": float(a),
        "curve_linear_z": float(b),
        "curve_quadratic_z": float(c),
        "t1_z_delta_mm": float(t1_z_delta),
        "rms_slope_px_per_mm": float(np.sqrt(np.mean(final_residuals**2))),
        "outlier_residual_limit_px_per_mm": residual_limit,
        "included_rows": included_rows,
        "excluded_rows": excluded_rows,
    }


def _write_slope_plot(
    fits: list[dict[str, Any]],
    path: Path,
    *,
    shared_curve_fit: dict[str, Any],
) -> None:
    figure, axis = plt.subplots(figsize=(8, 6))
    tool_colors = {"T0": PLOT_COLORS[0], "T1": PLOT_COLORS[1]}
    tool_markers = {"T0": "o", "T1": "s"}
    for tool in ("T0", "T1"):
        tool_fits = [fit for fit in fits if fit["tool"] == tool]
        tool_fits.sort(key=lambda fit: float(fit["z_mm"]))
        z_values = [float(fit["z_mm"]) for fit in tool_fits]
        slope_values = [
            (
                float(fit["slope_u_px_per_mm"])
                if fit["slope_u_px_per_mm"] is not None
                else np.nan
            )
            for fit in tool_fits
        ]
        axis.plot(
            z_values,
            slope_values,
            marker=tool_markers[tool],
            linestyle="-",
            color=tool_colors[tool],
            linewidth=2.0,
            markersize=7.0,
            label=tool,
        )
    if shared_curve_fit.get("available"):
        z_values = np.asarray(
            sorted({float(fit["z_mm"]) for fit in fits}), dtype=np.float64
        )
        if len(z_values):
            z_grid = np.linspace(float(z_values[0]), float(z_values[-1]), 200)
            a = float(shared_curve_fit["curve_intercept"])
            b = float(shared_curve_fit["curve_linear_z"])
            c = float(shared_curve_fit["curve_quadratic_z"])
            t1_z_delta = float(shared_curve_fit["t1_z_delta_mm"])
            for tool in ("T0", "T1"):
                physical_z = z_grid + (t1_z_delta if tool == "T1" else 0.0)
                predicted = a + b * physical_z + c * physical_z**2
                axis.plot(
                    z_grid,
                    predicted,
                    linestyle="--",
                    color=tool_colors[tool],
                    linewidth=2.0,
                    label=f"{tool} shared curve",
                )
    if shared_curve_fit.get("available"):
        delta_text = (
            f"T1 ΔZ = {float(shared_curve_fit['t1_z_delta_mm']):+.4f} mm\n"
            "physical Z = commanded Z + ΔZ"
        )
        axis.text(
            0.02,
            0.98,
            delta_text,
            transform=axis.transAxes,
            va="top",
            fontsize=12,
            fontweight="bold",
            bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.9},
        )
        title = "Nozzle image-u slope versus commanded Z"
    else:
        title = "Nozzle image-u slope versus commanded Z (shared fit unavailable)"
    axis.set_title(title)
    axis.set_xlabel("Commanded Z (mm)")
    axis.set_ylabel("du/dX (px/mm)")
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def _write_shared_curve_plot(
    fits: list[dict[str, Any]],
    shared_curve_fit: dict[str, Any],
    path: Path,
) -> None:
    figure, axis = plt.subplots(figsize=(10, 6))
    tool_colors = {"T0": PLOT_COLORS[0], "T1": PLOT_COLORS[1]}
    tool_markers = {"T0": "o", "T1": "s"}

    for tool in ("T0", "T1"):
        tool_fits = [
            fit
            for fit in fits
            if fit["tool"] == tool and fit["slope_u_px_per_mm"] is not None
        ]
        if tool_fits:
            axis.scatter(
                [float(fit["z_mm"]) for fit in tool_fits],
                [float(fit["slope_u_px_per_mm"]) for fit in tool_fits],
                color=tool_colors[tool],
                marker=tool_markers[tool],
                s=70,
                label=f"{tool} measured slope",
            )

    excluded = [
        row
        for row in shared_curve_fit.get("excluded_rows", [])
        if row.get("slope_u_px_per_mm") is not None
    ]
    if excluded:
        axis.scatter(
            [float(row["z_mm"]) for row in excluded],
            [float(row["slope_u_px_per_mm"]) for row in excluded],
            color="#D62728",
            marker="x",
            s=90,
            linewidths=2.5,
            label="excluded from shared fit",
        )

    if shared_curve_fit.get("available"):
        included = shared_curve_fit.get("included_rows", [])
        z_values = np.asarray(
            [float(row["z_mm"]) for row in included], dtype=np.float64
        )
        if len(z_values):
            z_grid = np.linspace(float(z_values.min()), float(z_values.max()), 300)
            a = float(shared_curve_fit["curve_intercept"])
            b = float(shared_curve_fit["curve_linear_z"])
            c = float(shared_curve_fit["curve_quadratic_z"])
            delta = float(shared_curve_fit["t1_z_delta_mm"])
            for tool in ("T0", "T1"):
                physical_z = z_grid + (delta if tool == "T1" else 0.0)
                predicted = a + b * physical_z + c * physical_z**2
                axis.plot(
                    z_grid,
                    predicted,
                    color=tool_colors[tool],
                    linestyle="-",
                    linewidth=2.5,
                    label=f"{tool} fitted shared curve",
                )
            annotation = (
                f"T1 ΔZ = {delta:+.4f} mm\n"
                f"RMS = {float(shared_curve_fit['rms_slope_px_per_mm']):.4f} px/mm\n"
                f"included={len(included)}  excluded={len(shared_curve_fit.get('excluded_rows', []))}"
            )
            axis.text(
                0.02,
                0.98,
                annotation,
                transform=axis.transAxes,
                va="top",
                fontsize=13,
                fontweight="bold",
                bbox={
                    "boxstyle": "round",
                    "facecolor": "#FFF2CC",
                    "edgecolor": "#8C6D1F",
                    "alpha": 0.95,
                },
            )
            title = "Shared quadratic slope fit and T1 Z offset"
        else:
            title = "Shared quadratic slope fit has no included rows"
    else:
        title = "Shared quadratic slope fit unavailable"
        axis.text(
            0.02,
            0.98,
            "T1 ΔZ = unavailable\n"
            + str(shared_curve_fit.get("reason", "unknown reason")),
            transform=axis.transAxes,
            va="top",
            fontsize=12,
            fontweight="bold",
            color="#8B0000",
            bbox={"boxstyle": "round", "facecolor": "#FDECEC", "alpha": 0.95},
        )

    axis.set_title(title)
    axis.set_xlabel("Commanded Z (mm)")
    axis.set_ylabel("du/dX (px/mm)")
    axis.grid(True, alpha=0.3)
    axis.legend()
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


def analyze(
    frame_paths: list[Path],
    artifact_dir: Path,
    *,
    frames: list[dict[str, Any]],
    references: dict[str, Any],
    acquisition_calibration: dict[str, Any],
) -> dict[str, Any]:
    _logger.info(
        "X/Z sweep analysis started frames=%d artifact_dir=%s",
        len(frames),
        artifact_dir,
    )
    if len(frame_paths) != len(frames):
        raise ToolXZSweepError("X/Z sweep frame paths do not match the manifest")
    if not frames:
        raise ToolXZSweepError("X/Z sweep has no frames")
    if {frame.get("tool") for frame in frames} != {"T0", "T1"}:
        raise ToolXZSweepError("X/Z sweep requires both T0 and T1 frames")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    records = [_base_record(frame) for frame in frames]
    valid_for_localization: dict[str, list[int]] = {"T0": [], "T1": []}
    image_dimensions: list[int] | None = None

    for index, (path, frame, record) in enumerate(zip(frame_paths, frames, records)):
        _logger.info(
            "Loading X/Z sweep frame %d/%d seq=%d tool=%s x_mm=%.3f y_mm=%.3f z_mm=%.3f path=%s",
            index + 1,
            len(frames),
            int(frame["seq"]),
            frame["tool"],
            float(frame["commanded_position_mm"][0]),
            float(frame["commanded_position_mm"][1]),
            float(frame["commanded_position_mm"][2]),
            path,
        )
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ToolXZSweepError(f"X/Z sweep image {index} cannot be decoded")
        dimensions = [int(image.shape[1]), int(image.shape[0])]
        if image_dimensions is None:
            image_dimensions = dimensions
        elif dimensions != image_dimensions:
            raise ToolXZSweepError("X/Z sweep images have inconsistent dimensions")
        try:
            fiducials = detect_four_fiducials(image)
        except FourFiducialError as exc:
            record["reasons"].append(f"four-fiducial detection failed: {exc}")
            _logger.info(
                "Four-fiducial detection missed seq=%d tool=%s reason=%s",
                int(frame["seq"]),
                frame["tool"],
                exc,
            )
        else:
            centers = np.asarray(fiducials["centers_px"], dtype=np.float64)
            record["fiducials_detected"] = True
            record["fiducial_centers_uv_px"] = centers.tolist()
            record["fiducial_radii_px"] = [
                float(value) for value in fiducials["radii_px"]
            ]
            locator = fiducials.get("locator")
            record["fiducial_fit"] = _finite(
                {
                    "roi_px": fiducials.get("roi_px"),
                    "patch_corners_px": fiducials.get("patch_corners_px"),
                    "right_edge_angle_deg": fiducials.get("right_edge_angle_deg"),
                    "down_edge_angle_deg": fiducials.get("down_edge_angle_deg"),
                    "geometry": fiducials.get("geometry"),
                    "locator": (
                        {
                            "marker_id": locator.get("marker_id"),
                            "marker_corners_px": locator.get("marker_corners_px"),
                            "marker_side_px": locator.get("marker_side_px"),
                        }
                        if isinstance(locator, dict)
                        else None
                    ),
                }
            )
            record["fiducial_centroid_uv_px"] = np.mean(centers, axis=0).tolist()
            valid_for_localization[frame["tool"]].append(index)
            _logger.info(
                "Four-fiducial detection succeeded seq=%d tool=%s centroid_u=%.2f centroid_v=%.2f",
                int(frame["seq"]),
                frame["tool"],
                float(record["fiducial_centroid_uv_px"][0]),
                float(record["fiducial_centroid_uv_px"][1]),
            )
        del image

    for tool in ("T0", "T1"):
        indices = valid_for_localization[tool]
        if not indices:
            _logger.info(
                "Skipping nozzle localization tool=%s reason=no valid fiducials", tool
            )
            continue
        tool_paths = [frame_paths[index] for index in indices]
        tool_frames = [frames[index] for index in indices]
        _logger.info(
            "Starting nozzle localization tool=%s valid_fiducial_frames=%d",
            tool,
            len(indices),
        )
        try:
            localized = localize_nozzle_tip_grid(
                tool_paths,
                frames=tool_frames,
                propagate_missing_rings=True,
                physical_tip_cluster_radius_px=16.0,
            )
        except NozzleTipLocalizationError as exc:
            _logger.info(
                "Nozzle localization failed tool=%s valid_fiducial_frames=%d reason=%s",
                tool,
                len(indices),
                exc,
            )
            for index in indices:
                records[index]["reasons"].append(
                    f"nozzle-tip localization failed: {exc}"
                )
            continue
        for registration in localized["registrations"]:
            source_index = indices[int(registration["seq"])]
            center = _vector(registration.get("center_px"), "nozzle center")
            records[source_index]["nozzle_uv_px"] = center.tolist()
            records[source_index]["nozzle_detected"] = True
            fit_rejection_reasons = _registration_fit_reasons(registration)
            records[source_index]["accepted_for_u_x_fit"] = not fit_rejection_reasons
            records[source_index]["u_x_fit_rejection_reasons"] = fit_rejection_reasons
            if fit_rejection_reasons:
                records[source_index]["reasons"].extend(
                    "excluded from u(X) fitting: " + reason
                    for reason in fit_rejection_reasons
                )
                _logger.info(
                    "Rejected nozzle localization from u(X) fitting "
                    "seq=%d tool=%s reasons=%s",
                    int(frames[source_index]["seq"]),
                    tool,
                    " | ".join(fit_rejection_reasons),
                )
            records[source_index]["localization"] = _finite(
                {
                    key: value
                    for key, value in registration.items()
                    if key not in {"center_px", "marker_center_px", "ring_center_px"}
                }
            )
        _logger.info(
            "Nozzle localization complete tool=%s localized_frames=%d",
            tool,
            sum(1 for index in indices if records[index]["nozzle_detected"]),
        )

    artifacts: dict[str, dict[str, str]] = {}
    if GENERATE_OVERLAYS:
        overlay_dir = artifact_dir / "tool_xz_sweep_overlays"
        overlay_dir.mkdir(parents=True, exist_ok=True)
        for index, (frame, record) in enumerate(zip(frames, records)):
            _logger.info(
                "Writing X/Z sweep overlay %d/%d seq=%d path=%s",
                index + 1,
                len(frames),
                int(frame["seq"]),
                frame_paths[index],
            )
            image = cv2.imread(str(frame_paths[index]), cv2.IMREAD_COLOR)
            if image is None:
                raise ToolXZSweepError(f"X/Z sweep image {index} cannot be decoded")
            overlay_path = overlay_dir / f"{frame['frame']}.png"
            _write_overlay(image, frame, record, overlay_path)
            del image
            _logger.info(
                "Wrote X/Z sweep overlay seq=%d path=%s",
                int(frame["seq"]),
                overlay_path,
            )
            artifacts[f"tool_xz_sweep_overlay_{int(frame['seq']):02d}"] = _artifact(
                overlay_path
            )
    else:
        _logger.info("Skipping X/Z sweep overlays: GENERATE_OVERLAYS is disabled")

    plot_path = artifact_dir / "tool_xz_sweep_u_vs_x.png"
    _write_u_plot(records, plot_path)
    _logger.info("Wrote X/Z sweep u(x) plot path=%s", plot_path)
    artifacts["tool_xz_sweep_u_vs_x"] = _artifact(plot_path)

    u_x_linear_fits = _fit_u_x_models(records)
    shared_z_curve_fit = estimate_tool_z_delta(u_x_linear_fits)
    slope_plot_path = artifact_dir / "tool_xz_sweep_u_slope_vs_z.png"
    _write_slope_plot(
        u_x_linear_fits,
        slope_plot_path,
        shared_curve_fit=shared_z_curve_fit,
    )
    _logger.info("Wrote X/Z sweep slope-versus-Z plot path=%s", slope_plot_path)
    artifacts["tool_xz_sweep_u_slope_vs_z"] = _artifact(slope_plot_path)
    shared_plot_path = artifact_dir / "tool_xz_sweep_shared_z_fit.png"
    _write_shared_curve_plot(
        fits=u_x_linear_fits,
        shared_curve_fit=shared_z_curve_fit,
        path=shared_plot_path,
    )
    _logger.info("Wrote X/Z sweep shared-fit plot path=%s", shared_plot_path)
    artifacts["tool_xz_sweep_shared_z_fit"] = _artifact(shared_plot_path)

    missing_fiducials = sum(not record["fiducials_detected"] for record in records)
    missing_nozzles = sum(not record["nozzle_detected"] for record in records)
    rejected_nozzles = sum(
        record["nozzle_detected"] and not record["accepted_for_u_x_fit"]
        for record in records
    )
    warnings = []
    if missing_fiducials:
        warnings.append(f"{missing_fiducials} frame(s) lack four-fiducial detections")
    if missing_nozzles:
        warnings.append(f"{missing_nozzles} frame(s) lack nozzle-tip detections")
    if rejected_nozzles:
        warnings.append(
            f"{rejected_nozzles} nozzle localization(s) failed fitting quality gates"
        )
    missing_fits = sum(fit["slope_u_px_per_mm"] is None for fit in u_x_linear_fits)
    if missing_fits:
        warnings.append(f"{missing_fits} tool/Z row(s) lack a usable linear fit")
    if not shared_z_curve_fit["available"]:
        warnings.append(
            "shared tool-Z slope curve unavailable: "
            + str(shared_z_curve_fit["reason"])
        )
    elif shared_z_curve_fit["excluded_rows"]:
        warnings.append(
            f"{len(shared_z_curve_fit['excluded_rows'])} tool/Z row(s) were "
            "excluded from the shared slope curve"
        )
    _logger.info(
        "X/Z sweep analysis complete frames=%d fiducial_misses=%d "
        "nozzle_misses=%d nozzle_fit_rejections=%d",
        len(records),
        missing_fiducials,
        missing_nozzles,
        rejected_nozzles,
    )
    return _finite(
        {
            "accepted": True,
            "reasons": [],
            "warnings": warnings,
            "tools": ["T0", "T1"],
            "x_offsets_from_bed_tab_mm": sorted(
                {float(frame["x_offset_from_bed_tab_mm"]) for frame in frames}
            ),
            "z_positions_mm": sorted({float(frame["z_mm"]) for frame in frames}),
            "image_dimensions_px": image_dimensions,
            "records": records,
            "u_x_linear_fits": u_x_linear_fits,
            "shared_z_curve_fit": shared_z_curve_fit,
            "acquisition_calibration": acquisition_calibration,
            "artifacts": artifacts,
        }
    )
