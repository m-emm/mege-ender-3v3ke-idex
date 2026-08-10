#!/usr/bin/env python3
"""Report-only combined T0/T1 nozzle image X/Z sweep."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares, minimize_scalar
from scipy.stats import theilslopes
from vision_four_fiducials import FourFiducialError, detect_four_fiducials
from vision_nozzle_tip_localization import (
    BRIGHT_CIRCLE_LEGACY_MIN_SCORE,
    BRIGHT_CIRCLE_MAX_CONSENSUS_RMS_PX,
    BRIGHT_CIRCLE_MAX_ROW_RESIDUAL_PX,
    BRIGHT_CIRCLE_MIN_TRAJECTORY_INLIER_FRACTION,
    BRIGHT_CIRCLE_MIN_TRAJECTORY_INLIERS,
    BRIGHT_CIRCLE_ROI_HALF_HEIGHT_PX,
    BRIGHT_CIRCLE_ROI_HALF_WIDTH_PX,
    BRIGHT_CIRCLE_SCORE_FLOOR,
    NozzleTipLocalizationError,
    evaluate_bright_circle_quality,
    localize_bright_nozzle_tip_grid,
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
SHARED_CURVE_F_SCALE_PX_PER_MM = 0.10
SHARED_CURVE_OUTLIER_SIGMA = 3.5
SHARED_CURVE_MIN_OUTLIER_LIMIT_PX_PER_MM = 0.09
XZ_Z_DELTA_LIMIT_MM = 1.5
XY_ENDSTOP_MATCH_TOLERANCE_MM = 0.0011
ROW_HUBER_F_SCALE_PX = 0.75
ROW_ROBUST_OUTLIER_SIGMA = 3.5
MAX_DELTA_JACKKNIFE_SPAN_MM = 0.50
MANUAL_T1_Z_CORRECTION_REFERENCE_MM = 0.60
MINIMUM_TIP_CORRELATION = 0.22
MINIMUM_MEDIAN_TIP_CORRELATION = 0.38
MAXIMUM_REPRESENTATION_SPREAD_PX = 2.5


class ToolXZSweepError(RuntimeError):
    pass


def _xy_endstop_pair(value: Any, context: str) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        result = np.empty((0,), dtype=np.float64)
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise ToolXZSweepError(f"{context} must contain finite X/Y endstop values")
    return result


def _active_xy_endstop_pair(
    active_calibration: dict[str, Any], tool: str, context: str
) -> np.ndarray:
    endstops = active_calibration.get("tool_xy_endstops_mm")
    if not isinstance(endstops, dict):
        raise ToolXZSweepError(f"{context} lacks active tool XY endstops")
    item = endstops.get(tool.lower())
    if not isinstance(item, dict):
        raise ToolXZSweepError(f"{context} lacks active {tool} XY endstops")
    try:
        result = np.asarray([item["x"], item["y"]], dtype=np.float64)
    except (KeyError, TypeError, ValueError):
        result = np.empty((0,), dtype=np.float64)
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise ToolXZSweepError(f"{context} has invalid active {tool} XY endstops")
    return result


def validate_xy_datum_endstops(
    xy_datum: dict[str, Any],
    *,
    tool: str,
    active_calibration: dict[str, Any],
) -> np.ndarray:
    """Require an XY prior to have been acquired with the active XY endstops."""

    context = f"{tool} vision_xy_datum"
    if not isinstance(xy_datum, dict):
        raise ToolXZSweepError(f"{context} is required")
    source = _xy_endstop_pair(
        xy_datum.get("acquisition_endstop_xy_mm"),
        f"{context}.acquisition_endstop_xy_mm",
    )
    active = _active_xy_endstop_pair(active_calibration, tool, context)
    difference = source - active
    if np.any(np.abs(difference) > XY_ENDSTOP_MATCH_TOLERANCE_MM):
        raise ToolXZSweepError(
            f"{context} is stale: prior acquired with XY endstops "
            f"X={source[0]:.3f}, Y={source[1]:.3f}, but active endstops are "
            f"X={active[0]:.3f}, Y={active[1]:.3f}; run "
            "post-endstop-xy-check before the X/Z sweep"
        )
    return source


def _validate_reference_prior_source(
    reference: dict[str, Any],
    *,
    tool: str,
    acquisition_calibration: dict[str, Any],
) -> np.ndarray:
    source = reference.get("nozzle_image_prior_source")
    if not isinstance(source, dict):
        raise ToolXZSweepError(
            f"{tool} X/Z reference lacks nozzle_image_prior_source; "
            "rerun post-endstop-xy-check"
        )
    source_xy = _xy_endstop_pair(
        source.get("acquisition_endstop_xy_mm"),
        f"{tool} nozzle_image_prior_source.acquisition_endstop_xy_mm",
    )
    active = _active_xy_endstop_pair(
        acquisition_calibration, tool, f"{tool} X/Z acquisition calibration"
    )
    if np.any(np.abs(source_xy - active) > XY_ENDSTOP_MATCH_TOLERANCE_MM):
        raise ToolXZSweepError(
            f"{tool} X/Z reference uses a stale XY prior acquired with "
            f"endstops X={source_xy[0]:.3f}, Y={source_xy[1]:.3f}, while the "
            f"capture used X={active[0]:.3f}, Y={active[1]:.3f}; rerun "
            "post-endstop-xy-check"
        )
    return source_xy


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


def _compare_bright_circle_gates(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Report the retired brightness gate beside the active geometry gate."""

    per_frame: list[dict[str, Any]] = []
    counts = {
        "bright_circle_records": 0,
        "legacy_accepted": 0,
        "active_accepted": 0,
        "newly_admitted_geometry_consensus": 0,
        "rejected_by_active_gate": 0,
        "nozzle_not_detected": 0,
    }
    for record in records:
        localization = record.get("localization") or {}
        if localization.get("localization_method") != "bright_circle_roi_v1":
            continue
        counts["bright_circle_records"] += 1
        score_value = localization.get("bright_circle_score")
        score = None if score_value is None else float(score_value)
        residual_value = localization.get("row_residual_px")
        residual = None if residual_value is None else float(residual_value)
        legacy_reasons: list[str] = []
        if record.get("nozzle_uv_px") is None:
            legacy_reasons.append("bright circular nozzle tip was not detected")
        if score is None or not math.isfinite(score):
            legacy_reasons.append("bright-circle quality score is unavailable")
        elif score < BRIGHT_CIRCLE_LEGACY_MIN_SCORE:
            legacy_reasons.append(
                f"bright-circle contrast score is too low: {score:.1f}"
            )
        if residual is None or not math.isfinite(residual):
            legacy_reasons.append("bright-circle row residual is unavailable")
        elif residual > BRIGHT_CIRCLE_MAX_ROW_RESIDUAL_PX:
            legacy_reasons.append(
                f"bright-circle row residual {residual:.2f} px exceeds "
                f"{BRIGHT_CIRCLE_MAX_ROW_RESIDUAL_PX:.2f} px"
            )
        legacy_accepted = not legacy_reasons
        active_gate = localization.get("quality_gate") or {}
        active_accepted = bool(record.get("accepted_for_u_x_fit", False))
        if legacy_accepted:
            counts["legacy_accepted"] += 1
        if active_accepted:
            counts["active_accepted"] += 1
        if active_accepted and not legacy_accepted:
            counts["newly_admitted_geometry_consensus"] += 1
            category = "newly_admitted_geometry_consensus"
        elif active_accepted:
            category = "accepted_by_both"
        elif record.get("nozzle_uv_px") is None:
            counts["nozzle_not_detected"] += 1
            category = "nozzle_not_detected"
        else:
            counts["rejected_by_active_gate"] += 1
            category = "rejected_by_active_gate"
        per_frame.append(
            {
                "seq": int(record["seq"]),
                "tool": record["tool"],
                "commanded_x_mm": float(record["commanded_x_mm"]),
                "commanded_z_mm": float(record["commanded_z_mm"]),
                "selected_center_px": record.get("nozzle_uv_px"),
                "bright_circle_score": score,
                "row_residual_px": residual,
                "candidate_score_margin": localization.get("candidate_score_margin"),
                "trajectory_consensus": localization.get("trajectory_consensus"),
                "quality_gate": active_gate,
                "legacy_accepted": legacy_accepted,
                "legacy_rejection_reasons": legacy_reasons,
                "active_accepted": active_accepted,
                "active_rejection_reasons": record.get("u_x_fit_rejection_reasons", []),
                "category": category,
                "candidates": localization.get("candidates", []),
            }
        )
    return {
        "comparison_version": "bright_circle_gate_comparison_v1",
        "legacy_gate": {
            "minimum_score": BRIGHT_CIRCLE_LEGACY_MIN_SCORE,
            "maximum_row_residual_px": BRIGHT_CIRCLE_MAX_ROW_RESIDUAL_PX,
        },
        "active_gate": {
            "minimum_score_floor": BRIGHT_CIRCLE_SCORE_FLOOR,
            "minimum_consensus_inliers": BRIGHT_CIRCLE_MIN_TRAJECTORY_INLIERS,
            "minimum_consensus_fraction": BRIGHT_CIRCLE_MIN_TRAJECTORY_INLIER_FRACTION,
            "maximum_consensus_rms_px": BRIGHT_CIRCLE_MAX_CONSENSUS_RMS_PX,
            "maximum_row_residual_px": BRIGHT_CIRCLE_MAX_ROW_RESIDUAL_PX,
        },
        "counts": counts,
        "frames": per_frame,
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


def _nozzle_prior_center(
    reference: dict[str, Any], commanded_x_mm: float
) -> np.ndarray | None:
    prior = reference.get("nozzle_image_prior")
    if not isinstance(prior, dict):
        return None
    if prior.get("model") != "linear_commanded_x_to_image_uv_v1":
        return None
    try:
        coefficients = np.asarray(prior.get("coefficients_px"), dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if coefficients.shape != (2, 2) or not np.all(np.isfinite(coefficients)):
        return None
    center = np.asarray([1.0, float(commanded_x_mm)]) @ coefficients
    return center if np.all(np.isfinite(center)) else None


def _validated_nozzle_prior_centers(
    reference: dict[str, Any],
    *,
    tool: str,
    commanded_x_values: list[float],
) -> list[np.ndarray]:
    """Require a complete, finite XY-derived image prior for an X/Z sweep."""

    context = f"{tool} nozzle_image_prior"
    prior = reference.get("nozzle_image_prior")
    if not isinstance(prior, dict):
        raise ToolXZSweepError(
            f"{context} is required; rerun the XY calibration to publish the "
            "commanded-X image line model"
        )
    if prior.get("model") != "linear_commanded_x_to_image_uv_v1":
        raise ToolXZSweepError(
            f"{context}.model must be linear_commanded_x_to_image_uv_v1"
        )

    try:
        coefficients = np.asarray(prior.get("coefficients_px"), dtype=np.float64)
    except (TypeError, ValueError):
        coefficients = np.empty((0, 0), dtype=np.float64)
    if coefficients.shape != (2, 2) or not np.all(np.isfinite(coefficients)):
        raise ToolXZSweepError(f"{context}.coefficients_px must be a finite 2x2 matrix")

    centers: list[np.ndarray] = []
    for commanded_x_mm in commanded_x_values:
        center = np.asarray([1.0, float(commanded_x_mm)]) @ coefficients
        if center.shape != (2,) or not np.all(np.isfinite(center)):
            raise ToolXZSweepError(
                f"{context} predicts a non-finite image center at X={commanded_x_mm:.3f} mm"
            )
        centers.append(center)
    return centers


def _localize_tool_nozzle(
    tool_paths: list[Path],
    *,
    tool_frames: list[dict[str, Any]],
    reference: dict[str, Any],
) -> dict[str, Any]:
    tool = str(tool_frames[0]["tool"])
    prior_centers = _validated_nozzle_prior_centers(
        reference,
        tool=tool,
        commanded_x_values=[float(frame["x_mm"]) for frame in tool_frames],
    )
    _logger.info(
        "Using commanded-X XY image prior for bright-circle localization "
        "tool=%s frames=%d roi_half_size=(%.1f,%.1f)px",
        tool,
        len(tool_frames),
        BRIGHT_CIRCLE_ROI_HALF_WIDTH_PX,
        BRIGHT_CIRCLE_ROI_HALF_HEIGHT_PX,
    )
    bright = localize_bright_nozzle_tip_grid(
        tool_paths,
        frames=tool_frames,
        roi_centers_px=prior_centers,
    )
    if any(
        registration.get("center_px") is not None
        for registration in bright["registrations"]
    ):
        return bright
    raise NozzleTipLocalizationError(
        f"{tool} has no bright circular candidates in commanded-X prior ROIs"
    )


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
    input_binding: dict[str, Any] | None = None,
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
    xy_datum = input_values.get(f"{tool_key}_xy_datum")
    source_endstops = validate_xy_datum_endstops(
        xy_datum,
        tool=tool,
        active_calibration=snapshot,
    )
    nozzle_image_prior = (
        xy_datum.get("nozzle_image_prior") if isinstance(xy_datum, dict) else None
    )
    prior_source: dict[str, Any] = {
        "acquisition_endstop_xy_mm": source_endstops,
    }
    if isinstance(input_binding, dict):
        for key in ("fact_name", "fact_set_hash", "fact_set_path"):
            if input_binding.get(key) is not None:
                prior_source[key] = input_binding[key]

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
        "nozzle_image_prior": nozzle_image_prior,
        "nozzle_image_prior_source": prior_source,
    }


def prepare_sweep(
    definition: dict[str, Any],
    *,
    input_values: dict[str, Any],
    resolved: dict[str, Any],
    input_bindings: dict[str, dict[str, Any]] | None = None,
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
    commanded_x_values = [float(corner_xy[0]) + offset for offset in x_offsets]
    for tool in tools:
        reference = _tool_reference(
            tool,
            definition=definition,
            input_values=input_values,
            resolved=resolved,
            input_binding=(input_bindings or {}).get(f"{tool.lower()}_xy_datum"),
        )
        _validated_nozzle_prior_centers(
            reference,
            tool=tool,
            commanded_x_values=commanded_x_values,
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
    if registration.get("localization_method") == "bright_circle_roi_v1":
        quality_gate = evaluate_bright_circle_quality(registration)
        return list(quality_gate["reasons"])
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
    def _finite_float(value: Any, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if np.isfinite(number) else default

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
    localization = record.get("localization") or {}
    bright_circle = localization.get("localization_method") == "bright_circle_roi_v1"
    if record.get("nozzle_uv_px") is not None and not bright_circle:
        cv2.drawMarker(
            overlay,
            tuple(np.rint(record["nozzle_uv_px"]).astype(int)),
            color,
            cv2.MARKER_CROSS,
            24,
            3,
        )
    if bright_circle:
        roi = localization.get("roi_px")
        if isinstance(roi, (list, tuple)) and len(roi) == 4:
            x0, y0, x1, y1 = [int(round(float(value))) for value in roi]
            cv2.rectangle(overlay, (x0, y0), (x1, y1), (255, 255, 0), 1)
        prior_center = localization.get("prior_center_px")
        if isinstance(prior_center, (list, tuple)) and len(prior_center) == 2:
            cv2.drawMarker(
                overlay,
                tuple(np.rint(prior_center).astype(int)),
                (0, 165, 255),
                cv2.MARKER_CROSS,
                12,
                1,
            )
        nozzle = record.get("nozzle_uv_px")
        if nozzle is not None:
            nozzle_point = tuple(np.rint(nozzle).astype(int))
            nozzle_radius = max(
                4,
                int(
                    round(
                        _finite_float(localization.get("bright_circle_radius_px"), 8.0)
                    )
                ),
            )
            cv2.circle(overlay, nozzle_point, nozzle_radius, color, 2)
            cv2.circle(overlay, nozzle_point, 2, color, -1)
    else:
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
        if bright_circle:
            prior_center = localization.get("prior_center_px")
            lines.append(
                "ROI prior="
                + (
                    f"{float(prior_center[0]):.2f},{float(prior_center[1]):.2f}px "
                    "method=bright_circle_roi_v1"
                    if isinstance(prior_center, (list, tuple))
                    and len(prior_center) == 2
                    else "n/a method=bright_circle_roi_v1"
                )
            )
            lines.append(
                "bright circle="
                f"score={_finite_float(localization.get('bright_circle_score')):.1f} "
                f"r={_finite_float(localization.get('bright_circle_radius_px')):.1f}px "
                f"row_res={_finite_float(localization.get('row_residual_px')):.2f}px "
                f"gate={(localization.get('quality_gate') or {}).get('mode', 'n/a')}"
            )
        else:
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


def _fit_row_trajectory(
    x_values: np.ndarray,
    u_values: np.ndarray,
    *,
    method: str,
) -> dict[str, Any]:
    if len(x_values) < 3 or len(np.unique(x_values)) < 2:
        return {"slope": None, "reason": "insufficient_X_trajectory"}

    if method == "theil_sen":
        slope, intercept, _, _ = theilslopes(u_values, x_values)
        slope = float(slope)
        intercept = float(intercept)
    else:
        if method in {"huber_irls", "soft_l1"}:
            # Seed robust losses from the high-breakdown estimator.  Starting
            # from OLS lets one far-end highlight retain too much leverage in
            # the small (normally 5-point) X rows.
            initial_slope, initial_intercept, _, _ = theilslopes(u_values, x_values)
        else:
            initial_slope, initial_intercept = np.polyfit(x_values, u_values, 1)

        initial_residuals = (
            float(initial_intercept) + float(initial_slope) * x_values - u_values
        )
        initial_center = float(np.median(initial_residuals))
        initial_mad = float(np.median(np.abs(initial_residuals - initial_center)))
        initial_scale = max(1.4826 * initial_mad, 0.10)
        initial_standardized = (initial_residuals - initial_center) / initial_scale
        robust_mask = np.abs(initial_standardized) <= ROW_ROBUST_OUTLIER_SIGMA
        if int(np.count_nonzero(robust_mask)) < 3:
            robust_mask = np.ones_like(initial_standardized, dtype=bool)

        def residuals(parameters: np.ndarray) -> np.ndarray:
            return parameters[0] + parameters[1] * x_values - u_values

        if method == "ols":
            loss = "linear"
        elif method == "huber_irls":
            loss = "huber"
        elif method == "soft_l1":
            loss = "soft_l1"
        else:
            raise ToolXZSweepError(f"unknown X trajectory fit method: {method}")

        def robust_residuals(parameters: np.ndarray) -> np.ndarray:
            return np.where(robust_mask, residuals(parameters), 0.0)

        result = least_squares(
            robust_residuals,
            x0=np.asarray([initial_intercept, initial_slope], dtype=np.float64),
            loss=loss,
            f_scale=ROW_HUBER_F_SCALE_PX,
            max_nfev=1000,
        )
        if not result.success:
            return {"slope": None, "reason": result.message}
        intercept = float(result.x[0])
        slope = float(result.x[1])

    fitted = intercept + slope * x_values
    residual_values = u_values - fitted
    residual_center = float(np.median(residual_values))
    residual_mad = float(np.median(np.abs(residual_values - residual_center)))
    robust_scale = max(1.4826 * residual_mad, 0.10)
    standardized = (residual_values - residual_center) / robust_scale
    if method == "huber_irls":
        weights = np.minimum(
            1.0, ROW_HUBER_F_SCALE_PX / np.maximum(np.abs(residual_values), 1.0e-9)
        )
    elif method == "soft_l1":
        weights = 1.0 / np.sqrt(1.0 + (residual_values / ROW_HUBER_F_SCALE_PX) ** 2)
    else:
        weights = np.ones_like(residual_values)
    if method in {"huber_irls", "soft_l1"}:
        weights = np.where(robust_mask, weights, 0.0)
    centered_x = x_values - np.average(x_values, weights=weights)
    information = float(np.sum(weights * centered_x**2))
    slope_uncertainty = (
        float(robust_scale / math.sqrt(information)) if information > 0.0 else None
    )
    design = np.column_stack((np.ones_like(x_values), x_values))
    weighted_design = design * np.sqrt(weights)[:, None]
    normal_inverse = np.linalg.pinv(weighted_design.T @ weighted_design)
    leverage = np.einsum(
        "ij,jk,ik->i", weighted_design, normal_inverse, weighted_design
    )
    influence = leverage * standardized**2
    return {
        "slope": slope,
        "intercept": intercept,
        "fit_rms_px": float(np.sqrt(np.mean(residual_values**2))),
        "robust_scale_px": robust_scale,
        "slope_uncertainty_px_per_mm": slope_uncertainty,
        "residuals_px": residual_values,
        "weights": weights,
        "standardized_residuals": standardized,
        "leverage": leverage,
        "influence": influence,
        "downweighted": (weights < 0.80)
        | (np.abs(standardized) > ROW_ROBUST_OUTLIER_SIGMA),
    }


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
        [float(record["commanded_x_mm"]) for record in usable], dtype=np.float64
    )
    u_values = np.asarray(
        [float(record["nozzle_uv_px"][0]) for record in usable], dtype=np.float64
    )
    fit = _fit_row_trajectory(x_values, u_values, method="huber_irls")
    return fit.get("slope")


def _u_x_correlation(x_values: np.ndarray, u_values: np.ndarray) -> float | None:
    if (
        len(x_values) < 3
        or len(np.unique(x_values)) < 2
        or len(np.unique(u_values)) < 2
    ):
        return None
    correlation = float(np.corrcoef(x_values, u_values)[0, 1])
    return correlation if math.isfinite(correlation) else None


def _fit_u_x_models(
    records: list[dict[str, Any]],
    *,
    method: str = "huber_irls",
    mutate_records: bool = True,
) -> list[dict[str, Any]]:
    """Fit one ``u = intercept + slope * commanded_x`` model per tool/Z row."""
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
                "fit_method": method,
                "u_x_correlation_coefficient": _u_x_correlation(x_values, u_values),
                "slope_u_px_per_mm": None,
                "intercept_u_px": None,
                "fit_rms_px": None,
                "x_values_mm": x_values.tolist(),
                "u_values_px": u_values.tolist(),
            }
            row_fit = _fit_row_trajectory(x_values, u_values, method=method)
            if row_fit.get("slope") is None:
                fit["reason"] = (
                    "fewer than three usable nozzle detections"
                    if len(usable) < 3
                    else str(row_fit.get("reason", "row trajectory fit failed"))
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
            fit["slope_u_px_per_mm"] = row_fit["slope"]
            fit["intercept_u_px"] = row_fit["intercept"]
            fit["fit_rms_px"] = row_fit["fit_rms_px"]
            fit["robust_scale_px"] = row_fit["robust_scale_px"]
            fit["slope_uncertainty_px_per_mm"] = row_fit["slope_uncertainty_px_per_mm"]
            fit["downweighted_sample_count"] = int(
                np.count_nonzero(row_fit["downweighted"])
            )
            fit["point_diagnostics"] = [
                {
                    "seq": int(record["seq"]),
                    "x_mm": float(x_value),
                    "u_px": float(u_value),
                    "residual_px": float(residual),
                    "weight": float(weight),
                    "standardized_residual": float(standardized),
                    "leverage": float(leverage),
                    "influence_score": float(influence),
                    "downweighted": bool(downweighted),
                }
                for record, x_value, u_value, residual, weight, standardized, downweighted, leverage, influence in zip(
                    usable,
                    x_values,
                    u_values,
                    row_fit["residuals_px"],
                    row_fit["weights"],
                    row_fit["standardized_residuals"],
                    row_fit["downweighted"],
                    row_fit["leverage"],
                    row_fit["influence"],
                )
            ]
            if mutate_records:
                for point in fit["point_diagnostics"]:
                    record = next(
                        item for item in usable if int(item["seq"]) == point["seq"]
                    )
                    record["u_x_fit"] = {
                        "method": method,
                        "residual_px": point["residual_px"],
                        "weight": point["weight"],
                        "standardized_residual": point["standardized_residual"],
                        "leverage": point["leverage"],
                        "influence_score": point["influence_score"],
                        "downweighted": point["downweighted"],
                    }
            _logger.info(
                "Fitted robust nozzle u(x) tool=%s z_mm=%.3f samples=%d "
                "method=%s slope=%.6f px/mm intercept=%.3f px "
                "fit_rms=%.3f px downweighted=%d",
                tool,
                z_mm,
                len(usable),
                method,
                fit["slope_u_px_per_mm"],
                fit["intercept_u_px"],
                fit["fit_rms_px"],
                fit["downweighted_sample_count"],
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


def _shared_curve_weights(fits: list[dict[str, Any]]) -> np.ndarray:
    uncertainties = np.asarray(
        [max(float(fit.get("slope_uncertainty_px_per_mm", 1.0)), 0.02) for fit in fits],
        dtype=np.float64,
    )
    weights = 1.0 / uncertainties**2
    return weights / float(np.median(weights))


def _profile_shared_curve(
    fits: list[dict[str, Any]],
    *,
    loss: str,
    delta_limit_mm: float = XZ_Z_DELTA_LIMIT_MM,
    include_profile: bool = False,
) -> dict[str, Any]:
    z_values, slope_values, is_t1 = _shared_curve_arrays(fits)
    weights = _shared_curve_weights(fits)

    def fit_at_delta(delta: float) -> dict[str, Any]:
        physical_z = z_values + is_t1 * float(delta)
        design = np.column_stack((np.ones_like(physical_z), physical_z, physical_z**2))
        initial = np.linalg.lstsq(design, slope_values, rcond=None)[0]

        def residuals(parameters: np.ndarray) -> np.ndarray:
            return (design @ parameters - slope_values) * np.sqrt(weights)

        result = least_squares(
            residuals,
            x0=initial,
            loss=loss,
            f_scale=SHARED_CURVE_F_SCALE_PX_PER_MM,
            max_nfev=1000,
        )
        raw_residuals = design @ result.x - slope_values
        return {
            "delta": float(delta),
            "coefficients": result.x,
            "raw_residuals": raw_residuals,
            "weighted_objective": float(2.0 * result.cost),
            "weighted_rms": float(
                np.sqrt(np.average(raw_residuals**2, weights=weights))
            ),
            "success": bool(result.success),
        }

    grid = np.linspace(-delta_limit_mm, delta_limit_mm, 601)
    grid_results = [fit_at_delta(float(delta)) for delta in grid]
    best_grid = min(grid_results, key=lambda item: item["weighted_objective"])
    best = best_grid
    if abs(float(best_grid["delta"])) < delta_limit_mm - 0.01:
        left = max(-delta_limit_mm, float(best_grid["delta"]) - 0.02)
        right = min(delta_limit_mm, float(best_grid["delta"]) + 0.02)
        refined = minimize_scalar(
            lambda delta: fit_at_delta(float(delta))["weighted_objective"],
            bounds=(left, right),
            method="bounded",
            options={"xatol": 1.0e-5},
        )
        best = fit_at_delta(float(refined.x))
    best["boundary_saturated"] = bool(
        abs(float(best["delta"])) >= delta_limit_mm - 0.006
    )
    if include_profile:
        best["profile"] = [
            {
                "delta_mm": item["delta"],
                "weighted_objective": item["weighted_objective"],
            }
            for item in grid_results
        ]
    return best


def _physical_z_diagnostics(
    acquisition_calibration: dict[str, Any] | None,
    delta_mm: float | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "manual_reference_delta_mm": MANUAL_T1_Z_CORRECTION_REFERENCE_MM,
        "difference_from_manual_reference_mm": (
            None
            if delta_mm is None
            else float(delta_mm - MANUAL_T1_Z_CORRECTION_REFERENCE_MM)
        ),
    }
    source = (
        acquisition_calibration.get("tool_z_endstops_mm")
        if isinstance(acquisition_calibration, dict)
        else None
    )
    if not isinstance(source, dict):
        return result
    try:
        t0 = float(source["t0"])
        t1 = float(source["t1"])
    except (KeyError, TypeError, ValueError):
        return result
    result["acquisition_t0_z_endstop_mm"] = t0
    result["acquisition_t1_z_endstop_mm"] = t1
    result["acquisition_t0_minus_t1_z_mm"] = t0 - t1
    if delta_mm is not None:
        result["suggested_t1_z_endstop_mm"] = t1 + float(delta_mm)
        result["suggested_t0_minus_t1_z_mm"] = t0 - t1 - float(delta_mm)
    return result


def _fit_result_failure(
    reason: str,
    *,
    excluded_rows: list[dict[str, Any]],
    physical_diagnostics: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "available": False,
        "fit_method": "quadratic_profiled_huber_with_jackknife",
        "reason": reason,
        "included_rows": [],
        "excluded_rows": excluded_rows,
        "physical_z_diagnostics": physical_diagnostics,
        **extra,
    }


def _influential_frame_points(fits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points = []
    for fit in fits:
        for point in fit.get("point_diagnostics", []):
            if (
                not point.get("downweighted")
                and float(point.get("influence_score", 0.0)) < 0.5
            ):
                continue
            points.append(
                {
                    "tool": fit["tool"],
                    "z_mm": float(fit["z_mm"]),
                    "seq": int(point["seq"]),
                    "x_mm": float(point["x_mm"]),
                    "residual_px": float(point["residual_px"]),
                    "weight": float(point["weight"]),
                    "standardized_residual": float(point["standardized_residual"]),
                    "leverage": float(point.get("leverage", 0.0)),
                    "influence_score": float(point.get("influence_score", 0.0)),
                    "downweighted": bool(point.get("downweighted", False)),
                }
            )
    return sorted(
        points,
        key=lambda point: (-point["influence_score"], point["seq"]),
    )


def estimate_tool_z_delta(
    fits: list[dict[str, Any]],
    *,
    acquisition_calibration: dict[str, Any] | None = None,
    loss: str = "huber",
    include_profile: bool = False,
) -> dict[str, Any]:
    excluded_rows = []
    quality_rows = []
    for fit in fits:
        row = {
            "tool": fit["tool"],
            "z_mm": float(fit["z_mm"]),
            "slope_u_px_per_mm": fit.get("slope_u_px_per_mm"),
            "u_x_correlation_coefficient": fit.get("u_x_correlation_coefficient"),
            "slope_uncertainty_px_per_mm": fit.get("slope_uncertainty_px_per_mm"),
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
            "fit_method": "quadratic_profiled_huber_with_jackknife",
            "reason": reason,
            "included_rows": [],
            "excluded_rows": excluded_rows,
            "physical_z_diagnostics": _physical_z_diagnostics(
                acquisition_calibration, None
            ),
        }

    initial = _profile_shared_curve(
        quality_rows,
        loss=loss,
        include_profile=include_profile,
    )
    initial_residuals = initial["raw_residuals"]
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

    final = _profile_shared_curve(
        retained_rows,
        loss=loss,
        include_profile=include_profile,
    )
    if not final["success"]:
        return _fit_result_failure(
            "final shared-curve optimization failed",
            excluded_rows=excluded_rows,
            physical_diagnostics=_physical_z_diagnostics(acquisition_calibration, None),
            outlier_residual_limit_px_per_mm=residual_limit,
        )

    final_residuals = final["raw_residuals"]
    included_rows = [
        {
            "tool": fit["tool"],
            "z_mm": float(fit["z_mm"]),
            "slope_u_px_per_mm": float(fit["slope_u_px_per_mm"]),
            "u_x_correlation_coefficient": fit.get("u_x_correlation_coefficient"),
            "slope_uncertainty_px_per_mm": fit.get("slope_uncertainty_px_per_mm"),
            "residual_px_per_mm": float(residual),
        }
        for fit, residual in zip(retained_rows, final_residuals)
    ]
    t1_z_delta = float(final["delta"])
    jackknife_deltas = []
    for index in range(len(retained_rows)):
        leave_one_out = retained_rows[:index] + retained_rows[index + 1 :]
        if not _shared_curve_is_identifiable(leave_one_out):
            continue
        leave_one_out_fit = _profile_shared_curve(leave_one_out, loss=loss)
        if leave_one_out_fit["success"]:
            jackknife_deltas.append(float(leave_one_out_fit["delta"]))
    jackknife_min = min(jackknife_deltas) if jackknife_deltas else None
    jackknife_max = max(jackknife_deltas) if jackknife_deltas else None
    jackknife_span = (
        None
        if jackknife_min is None or jackknife_max is None
        else jackknife_max - jackknife_min
    )
    unstable = (
        final["boundary_saturated"]
        or not jackknife_deltas
        or jackknife_span > MAX_DELTA_JACKKNIFE_SPAN_MM
        or jackknife_min < -XZ_Z_DELTA_LIMIT_MM
        or jackknife_max > XZ_Z_DELTA_LIMIT_MM
    )
    physical_diagnostics = _physical_z_diagnostics(acquisition_calibration, t1_z_delta)
    common = {
        "fit_method": "quadratic_profiled_huber_with_jackknife",
        "curve_intercept": float(final["coefficients"][0]),
        "curve_linear_z": float(final["coefficients"][1]),
        "curve_quadratic_z": float(final["coefficients"][2]),
        "t1_z_delta_mm": t1_z_delta,
        "rms_slope_px_per_mm": float(np.sqrt(np.mean(final_residuals**2))),
        "weighted_rms_slope_px_per_mm": float(final["weighted_rms"]),
        "maximum_slope_residual_px_per_mm": float(np.max(np.abs(final_residuals))),
        "outlier_residual_limit_px_per_mm": residual_limit,
        "included_rows": included_rows,
        "excluded_rows": excluded_rows,
        "boundary_saturated": bool(final["boundary_saturated"]),
        "jackknife_delta_min_mm": jackknife_min,
        "jackknife_delta_max_mm": jackknife_max,
        "jackknife_delta_span_mm": jackknife_span,
        "jackknife_deltas_mm": jackknife_deltas,
        "influential_frame_points": _influential_frame_points(fits),
        "physical_z_diagnostics": physical_diagnostics,
    }
    if include_profile:
        common["delta_profile"] = final.get("profile", [])
    if unstable:
        if final["boundary_saturated"]:
            reason = "shared Z fit saturated the operational T1 delta bound"
        elif (
            jackknife_span is not None and jackknife_span > MAX_DELTA_JACKKNIFE_SPAN_MM
        ):
            reason = "shared Z fit is unstable under leave-one-row-out analysis"
        else:
            reason = "shared Z fit has insufficient stability diagnostics"
        return {"available": False, "reason": reason, **common}
    _logger.info(
        "Fitted shared nozzle slope curve rows=%d excluded=%d "
        "t1_z_delta_mm=%.6f rms_slope_px_per_mm=%.6f",
        len(retained_rows),
        len(excluded_rows),
        t1_z_delta,
        common["rms_slope_px_per_mm"],
    )
    return {"available": True, **common}


def _compare_fit_strategies(
    records: list[dict[str, Any]],
    *,
    acquisition_calibration: dict[str, Any],
) -> dict[str, Any]:
    strategies = {
        "theil_sen_plus_soft_l1": ("theil_sen", "soft_l1"),
        "ols_plus_linear": ("ols", "linear"),
        "huber_irls_plus_huber": ("huber_irls", "huber"),
        "soft_l1_plus_soft_l1": ("soft_l1", "soft_l1"),
    }
    result: dict[str, Any] = {
        "fit_strategy_version": "xz_trajectory_fit_comparison_v1",
        "delta_limit_mm": XZ_Z_DELTA_LIMIT_MM,
        "strategies": {},
    }
    for name, (row_method, curve_loss) in strategies.items():
        fits = _fit_u_x_models(
            records,
            method=row_method,
            mutate_records=False,
        )
        shared = estimate_tool_z_delta(
            fits,
            acquisition_calibration=acquisition_calibration,
            loss=curve_loss,
            include_profile=True,
        )
        shared["strategy_name"] = name
        result["strategies"][name] = {
            "row_fit_method": row_method,
            "shared_curve_loss": curve_loss,
            "shared_z_curve_fit": shared,
            "row_fits": fits,
        }
    result["physical_context"] = _physical_z_diagnostics(
        acquisition_calibration, MANUAL_T1_Z_CORRECTION_REFERENCE_MM
    )
    return _finite(result)


def _write_fit_strategy_comparison_plot(comparison: dict[str, Any], path: Path) -> None:
    strategies = comparison.get("strategies", {})
    names = list(strategies)
    labels = [name.replace("_plus_", "\n") for name in names]
    deltas = []
    rms_values = []
    colors = []
    for name in names:
        shared = strategies[name].get("shared_z_curve_fit", {})
        delta = shared.get("t1_z_delta_mm")
        deltas.append(float(delta) if delta is not None else np.nan)
        rms = shared.get("rms_slope_px_per_mm")
        rms_values.append(float(rms) if rms is not None else np.nan)
        colors.append("#D62728" if not shared.get("available") else "#2CA02C")

    figure, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].bar(labels, deltas, color=colors)
    axes[0].axhline(XZ_Z_DELTA_LIMIT_MM, color="#555555", linestyle="--")
    axes[0].axhline(-XZ_Z_DELTA_LIMIT_MM, color="#555555", linestyle="--")
    axes[0].axhline(
        MANUAL_T1_Z_CORRECTION_REFERENCE_MM,
        color="#1F77B4",
        linestyle=":",
        label="manual reference +0.6 mm",
    )
    axes[0].set_ylabel("T1 delta (mm)")
    axes[0].set_title("Fit strategy T1 delta")
    axes[0].legend(fontsize=8)
    axes[0].grid(True, axis="y", alpha=0.3)

    axes[1].bar(labels, rms_values, color=colors)
    axes[1].set_ylabel("Shared slope RMS (px/mm)")
    axes[1].set_title("Fit strategy residual")
    axes[1].grid(True, axis="y", alpha=0.3)
    figure.tight_layout()
    figure.savefig(path, dpi=160)
    plt.close(figure)


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

    for tool in ("T0", "T1"):
        tool_frames = [frame for frame in frames if str(frame["tool"]) == tool]
        reference = references.get(tool.lower(), {})
        _validated_nozzle_prior_centers(
            reference,
            tool=tool,
            commanded_x_values=[float(frame["x_mm"]) for frame in tool_frames],
        )
        _validate_reference_prior_source(
            reference,
            tool=tool,
            acquisition_calibration=acquisition_calibration,
        )

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
            localized = _localize_tool_nozzle(
                tool_paths,
                tool_frames=tool_frames,
                reference=references.get(tool.lower(), {}),
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
            if registration.get("center_px") is None:
                rejection_reasons = _registration_fit_reasons(registration)
                records[source_index]["u_x_fit_rejection_reasons"] = rejection_reasons
                records[source_index]["reasons"].extend(
                    "nozzle localization rejected: " + reason
                    for reason in rejection_reasons
                )
                records[source_index]["localization"] = _finite(
                    {
                        key: value
                        for key, value in registration.items()
                        if key
                        not in {"center_px", "marker_center_px", "ring_center_px"}
                    }
                )
                continue
            center = _vector(registration["center_px"], "nozzle center")
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
    bright_circle_gate_comparison = _compare_bright_circle_gates(records)
    gate_comparison_path = artifact_dir / "bright_circle_gate_comparison.json"
    gate_comparison_path.write_text(
        json.dumps(bright_circle_gate_comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _logger.info(
        "Wrote bright-circle gate comparison path=%s legacy_accepted=%d "
        "active_accepted=%d newly_admitted=%d active_rejected=%d",
        gate_comparison_path,
        bright_circle_gate_comparison["counts"]["legacy_accepted"],
        bright_circle_gate_comparison["counts"]["active_accepted"],
        bright_circle_gate_comparison["counts"]["newly_admitted_geometry_consensus"],
        bright_circle_gate_comparison["counts"]["rejected_by_active_gate"],
    )
    artifacts["bright_circle_gate_comparison"] = _artifact(gate_comparison_path)
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

    u_x_linear_fits = _fit_u_x_models(records, method="huber_irls")
    shared_z_curve_fit = estimate_tool_z_delta(
        u_x_linear_fits,
        acquisition_calibration=acquisition_calibration,
        loss="huber",
        include_profile=True,
    )
    fit_strategy_comparison = _compare_fit_strategies(
        records,
        acquisition_calibration=acquisition_calibration,
    )
    comparison_json_path = artifact_dir / "fit_strategy_comparison.json"
    comparison_json_path.write_text(
        json.dumps(fit_strategy_comparison, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _logger.info(
        "Wrote X/Z fit strategy comparison path=%s",
        comparison_json_path,
    )
    artifacts["fit_strategy_comparison"] = _artifact(comparison_json_path)
    comparison_plot_path = artifact_dir / "fit_strategy_comparison.png"
    _write_fit_strategy_comparison_plot(
        fit_strategy_comparison,
        comparison_plot_path,
    )
    _logger.info(
        "Wrote X/Z fit strategy comparison plot path=%s",
        comparison_plot_path,
    )
    artifacts["fit_strategy_comparison_plot"] = _artifact(comparison_plot_path)
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
            "fit_strategy_comparison": fit_strategy_comparison,
            "bright_circle_gate_comparison": bright_circle_gate_comparison,
            "acquisition_calibration": acquisition_calibration,
            "artifacts": artifacts,
        }
    )
