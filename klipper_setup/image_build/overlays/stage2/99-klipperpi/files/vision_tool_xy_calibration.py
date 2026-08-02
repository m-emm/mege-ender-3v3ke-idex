#!/usr/bin/env python3
"""Single-tool nozzle-camera X/Y datum acquisition and analysis."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from vision_four_fiducials import FourFiducialError, detect_four_fiducials
from vision_nozzle_tip_localization import (
    NozzleTipLocalizationError,
    localize_nozzle_tip_grid,
)

MINIMUM_TIP_CORRELATION = 0.22
MINIMUM_MEDIAN_TIP_CORRELATION = 0.38
MAXIMUM_REPRESENTATION_SPREAD_PX = 2.5
MAXIMUM_DATUM_RESIDUAL_MM = 0.5
MINIMUM_ACCEPTED_FRAMES = 3
MINIMUM_ACCEPTED_X_SPAN_MM = 8.0


class ToolXYError(RuntimeError):
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


def _vector(value: Any, name: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.shape != (2,) or not np.all(np.isfinite(result)):
        raise ToolXYError(f"{name} must contain two finite values")
    return result


def _number(mapping: dict[str, Any], key: str, context: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ToolXYError(f"{context}.{key} must be finite and numeric")
    return float(value)


def _x_vector_at_capture(mapping: dict[str, Any], capture_y_mm: float) -> np.ndarray:
    model = mapping.get("fiducial_x_vector_model_px_per_mm")
    if not isinstance(model, dict):
        raise ToolXYError("fiducial mapping lacks its X-vector model")
    reference = _vector(model.get("reference_vector_px_per_mm"), "X-vector reference")
    slope = _vector(
        model.get("capture_y_slope_px_per_mm_per_mm"),
        "X-vector capture-Y slope",
    )
    reference_y = _number(model, "reference_capture_y_mm", "X-vector model")
    return reference + slope * (float(capture_y_mm) - reference_y)


def _tool_marker_vector(marker: dict[str, Any], tool: str) -> np.ndarray:
    quality = marker.get("quality")
    vectors = (
        quality.get("tool_axis_vectors_px_per_mm")
        if isinstance(quality, dict)
        else None
    )
    if not isinstance(vectors, dict):
        raise ToolXYError(f"{tool} marker reference lacks its image motion vector")
    return _vector(vectors.get(tool), f"{tool} marker image motion vector")


def _pixel_delta_to_printer_xy_mm(
    pixel_delta: Any,
    *,
    x_vector_px_per_mm: Any,
    y_vector_px_per_mm: Any,
) -> np.ndarray:
    basis = np.column_stack(
        (
            _vector(x_vector_px_per_mm, "image X vector"),
            _vector(y_vector_px_per_mm, "image Y vector"),
        )
    )
    condition_number = float(np.linalg.cond(basis))
    if not math.isfinite(condition_number) or condition_number > 100.0:
        raise ToolXYError(
            f"pixel/printer XY basis is ill-conditioned: {condition_number:.3f}"
        )
    return np.linalg.solve(basis, _vector(pixel_delta, "pixel delta"))


def _active_tool_state(resolved: dict[str, Any]) -> dict[str, Any]:
    snapshot = resolved.get("active_tool_calibration")
    if not isinstance(snapshot, dict):
        raise ToolXYError("preflight lacks loaded tool calibration")
    endstops = snapshot.get("tool_xy_endstops_mm")
    offsets = snapshot.get("tool_y_offsets_mm")
    if not isinstance(endstops, dict) or not isinstance(offsets, dict):
        raise ToolXYError("loaded tool calibration is incomplete")
    return snapshot


def prepare_measurement(
    definition: dict[str, Any],
    *,
    input_values: dict[str, Any],
    resolved: dict[str, Any],
) -> dict[str, Any]:
    """Resolve capture motion and the image reference for one tool."""
    tool = str(definition.get("tool", ""))
    if tool not in {"T0", "T1"}:
        raise ToolXYError("tool-XY measurement requires T0 or T1")
    tool_key = tool.lower()
    gap = _number(definition, "capture_endstop_gap_mm", "job definition")
    if gap <= 0.0:
        raise ToolXYError("capture_endstop_gap_mm must be positive")
    commanded_z = _number(definition, "commanded_z_mm", "job definition")
    if abs(commanded_z - 0.5) > 1e-9:
        raise ToolXYError("tool-XY measurement requires commanded Z=0.5 mm")

    snapshot = _active_tool_state(resolved)
    endstops = snapshot["tool_xy_endstops_mm"]
    offsets = snapshot["tool_y_offsets_mm"]
    try:
        t0_y_endstop = float(endstops["t0"]["y"])
        selected_y_endstop = float(endstops[tool_key]["y"])
        selected_y_offset = float(offsets[tool_key])
    except (KeyError, TypeError, ValueError):
        raise ToolXYError("loaded tool calibration has invalid Y values") from None
    expected_offset = t0_y_endstop - selected_y_endstop
    if abs(selected_y_offset - expected_offset) > 1e-6:
        raise ToolXYError(
            f"loaded {tool} Y offset {selected_y_offset:.6f} does not equal "
            f"T0-minus-{tool} endstop offset {expected_offset:.6f}"
        )

    capture_y = selected_y_endstop + gap
    internal_y = capture_y + selected_y_offset
    expected_internal_y = t0_y_endstop + gap
    if abs(internal_y - expected_internal_y) > 1e-6:
        raise ToolXYError("derived capture Y does not preserve the endstop gap")
    axis_minimum = resolved.get("axis_minimum")
    axis_maximum = resolved.get("axis_maximum")
    if not isinstance(axis_minimum, list) or not isinstance(axis_maximum, list):
        raise ToolXYError("preflight motion limits are unavailable")
    if not float(axis_minimum[1]) <= internal_y <= float(axis_maximum[1]):
        raise ToolXYError(
            f"derived internal capture Y {internal_y:.6f} is outside loaded "
            f"limits [{float(axis_minimum[1]):.6f}, {float(axis_maximum[1]):.6f}]"
        )

    metric = input_values.get("bed_metric")
    mapping = input_values.get("bed_fiducial_printer_xy_mapping")
    marker = input_values.get(f"{tool_key}_red_marker_offset")
    if not all(isinstance(item, dict) for item in (metric, mapping, marker)):
        raise ToolXYError("tool-XY measurement inputs are incomplete")
    image_y_vector = _vector(
        metric.get("image_y_axis_vector_px_per_mm"),
        "bed metric image Y vector",
    )
    reference_centers = np.asarray(
        metric.get("reference_marker_centers_px"), dtype=np.float64
    )
    if reference_centers.shape != (4, 2) or not np.all(np.isfinite(reference_centers)):
        raise ToolXYError("bed metric requires four reference marker centers")
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

    offsets_x = [
        float(item) for item in definition.get("x_offsets_from_bed_tab_mm", [])
    ]
    if len(offsets_x) < 3 or offsets_x != sorted(set(offsets_x)):
        raise ToolXYError("tool-XY X offsets must contain at least three unique values")
    frames = []
    for seq, offset_x in enumerate(offsets_x):
        x_mm = float(corner_xy[0]) + offset_x
        if not float(axis_minimum[0]) <= x_mm <= float(axis_maximum[0]):
            raise ToolXYError(f"tool-XY commanded X {x_mm:.6f} is out of limits")
        expected_marker = corner_pixel_at_capture + marker_x_vector * (
            marker_offset + x_mm - marker_reference_x
        )
        frames.append(
            {
                "seq": seq,
                "frame": (
                    f"{seq:02d}_{tool_key}_x{x_mm:.3f}_z{commanded_z:.3f}"
                ).replace(".", "p"),
                "camera": "nozzle_cam",
                "profile": definition["profile"],
                "tool": tool,
                "x_offset_from_bed_tab_mm": offset_x,
                "x_mm": x_mm,
                "y_mm": capture_y,
                "z_mm": commanded_z,
                "expected_marker_pixel_px": expected_marker.tolist(),
                "discard_fresh_frames": int(definition["discard_fresh_frames"]),
                "commanded_position_mm": [x_mm, capture_y, commanded_z],
            }
        )

    return _finite(
        {
            "frames": frames,
            "reference": {
                "tool": tool,
                "capture_y_mm": capture_y,
                "internal_capture_y_mm": internal_y,
                "capture_endstop_gap_mm": gap,
                "commanded_z_mm": commanded_z,
                "fiducial_reference_printer_xy_mm": fiducial_xy,
                "corner_printer_xy_mm": corner_xy,
                "image_x_vector_px_per_mm": image_x_vector,
                "image_y_vector_px_per_mm": image_y_vector,
                "marker_x_vector_px_per_mm": marker_x_vector,
                "marker_offset_mm": marker_offset,
                "marker_reference_commanded_x_mm": marker_reference_x,
            },
            "active_tool_calibration": snapshot,
        }
    )


def _capture_line(job_id: str, frame: dict[str, Any]) -> str:
    return (
        f"VISION_CAPTURE_SYNC JOB={job_id} SEQ={frame['seq']} "
        f"FRAME={frame['frame']} CAMERA=nozzle_cam "
        f"PROFILE={frame['profile']} TOOL={frame['tool']}"
    )


def build_acquisition_gcode(
    job_id: str,
    manifest_hash: str,
    gcode_hash: str,
    manifest: dict[str, Any],
    definition: dict[str, Any],
) -> str:
    frames = manifest["frames"]
    if not frames:
        raise ToolXYError("tool-XY acquisition has no frames")
    pose = manifest["motion"]["resolved_pose"]
    feedrate = float(definition.get("velocity_mm_s", 60.0)) * 60.0
    tool = str(frames[0]["tool"])
    capture_y = float(frames[0]["commanded_position_mm"][1])
    safe_z = float(pose["safe_tool_change_z_mm"])
    lines = [
        f"; vision calibration job {job_id}",
        "G28",
        "G90",
        (
            f"VISION_JOB_BEGIN JOB={job_id} "
            f"MANIFEST_HASH={manifest_hash} GCODE_HASH={gcode_hash}"
        ),
        f"VISION_PROFILE CAMERA=nozzle_cam PROFILE={definition['profile']}",
        definition["light_macro"],
        f"G1 Z{safe_z:.6f} F{feedrate:.3f}",
        tool,
        f"G1 Z{safe_z:.6f} F{feedrate:.3f}",
        f"G1 Y{capture_y:.6f} F{feedrate:.3f}",
        "M400",
        f"G4 P{int(definition['tool_change_settle_ms'])}",
    ]
    for frame in frames:
        x_mm, _y_mm, z_mm = [float(item) for item in frame["commanded_position_mm"]]
        lines.extend(
            [
                f"G1 Z{z_mm:.6f} F{feedrate:.3f}",
                f"G1 X{x_mm:.6f} F{feedrate:.3f}",
                "M400",
                f"G4 P{int(definition['settle_ms'])}",
                _capture_line(job_id, frame),
            ]
        )
    lines.extend(
        [
            f"G1 Z{safe_z:.6f} F{feedrate:.3f}",
            "T0",
            f"G1 Z{safe_z:.6f} F{feedrate:.3f}",
            f"VISION_JOB_END JOB={job_id} EXPECTED_FRAMES={len(frames)}",
            "VISION_LIGHT_OFF",
            "",
        ]
    )
    return "\n".join(lines)


def _registration_reasons(registration: dict[str, Any]) -> list[str]:
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


def _endstop_line(acquisition_calibration: dict[str, Any]) -> str:
    endstops = acquisition_calibration["tool_xy_endstops_mm"]
    return "acquire endstops: " + " | ".join(
        f"{tool.upper()} X={float(endstops[tool]['x']):.3f} "
        f"Y={float(endstops[tool]['y']):.3f}"
        for tool in ("t0", "t1")
    )


def _write_overlays(
    frame_paths: list[Path],
    frames: list[dict[str, Any]],
    records: list[dict[str, Any]],
    artifact_dir: Path,
    acquisition_calibration: dict[str, Any],
) -> dict[str, dict[str, str]]:
    overlay_dir = artifact_dir / "tool_xy_overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    cells = []
    record_by_seq = {int(record["seq"]): record for record in records}
    endstop_line = _endstop_line(acquisition_calibration)
    for path, frame in zip(frame_paths, frames):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ToolXYError(f"cannot decode {path}")
        record = record_by_seq[int(frame["seq"])]
        accepted = bool(record.get("accepted"))
        color = (0, 255, 0) if accepted else (0, 0, 255)
        if record.get("tip_center_px") is not None:
            tip = tuple(np.rint(record["tip_center_px"]).astype(int))
            cv2.drawMarker(image, tip, color, cv2.MARKER_CROSS, 20, 3)
        for center in record.get("fiducial_centers_px") or []:
            cv2.circle(image, tuple(np.rint(center).astype(int)), 8, (0, 255, 255), 2)
        command = frame["commanded_position_mm"]
        lines = [
            (
                f"{frame['tool']} X={float(command[0]):.3f} "
                f"Y={float(command[1]):.3f} Z={float(command[2]):.3f} "
                f"{('accepted' if accepted else 'rejected')}"
            ),
            (
                f"fiducials_to_tip_mm={record.get('fiducials_to_tip_xy_mm')} "
                f"x_datum={record.get('x_datum_mm')} "
                f"y_datum={record.get('y_datum_mm')}"
            ),
            endstop_line,
        ]
        if not accepted:
            lines.append("reasons: " + " | ".join(record.get("rejection_reasons", [])))
        for line_index, line in enumerate(lines):
            cv2.putText(
                image,
                line,
                (24, 40 + 30 * line_index),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.72,
                color,
                2,
                cv2.LINE_AA,
            )
        suffix = "accepted" if accepted else "rejected"
        overlay_path = overlay_dir / f"{frame['frame']}_{suffix}.png"
        if not cv2.imwrite(str(overlay_path), image):
            raise ToolXYError(f"could not write overlay {overlay_path}")
        artifacts[f"tool_xy_overlay_{int(frame['seq']):02d}"] = _artifact(overlay_path)
        cells.append(cv2.resize(image, (480, 270), interpolation=cv2.INTER_AREA))
    contact = cv2.hconcat(cells)
    contact_path = artifact_dir / "tool_xy_measurement.jpg"
    if not cv2.imwrite(str(contact_path), contact):
        raise ToolXYError(f"could not write contact sheet {contact_path}")
    artifacts["tool_xy_measurement"] = _artifact(contact_path)
    return artifacts


def analyze_measurement(
    frame_paths: list[Path],
    artifact_dir: Path,
    *,
    frames: list[dict[str, Any]],
    reference: dict[str, Any],
    acquisition_calibration: dict[str, Any],
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if len(frame_paths) != len(frames):
        raise ToolXYError("tool-XY frame paths do not match the manifest")
    if not frames:
        raise ToolXYError("tool-XY analysis has no frames")
    tools = {str(frame.get("tool")) for frame in frames}
    if len(tools) != 1 or tools - {"T0", "T1"}:
        raise ToolXYError("tool-XY analysis requires exactly one tool")
    tool = tools.pop()
    if tool != reference.get("tool"):
        raise ToolXYError("tool-XY frames do not match their reference")
    image_x_vector = _vector(
        reference.get("image_x_vector_px_per_mm"), "image X vector"
    )
    image_y_vector = _vector(
        reference.get("image_y_vector_px_per_mm"), "image Y vector"
    )
    corner_xy = _vector(reference.get("corner_printer_xy_mm"), "bed corner printer XY")
    fiducial_xy = _vector(
        reference.get("fiducial_reference_printer_xy_mm"),
        "fiducial reference printer XY",
    )
    marker_offset = _number(reference, "marker_offset_mm", "tool-XY reference")
    marker_reference_x = _number(
        reference,
        "marker_reference_commanded_x_mm",
        "tool-XY reference",
    )
    marker_x_vector = _vector(
        reference.get("marker_x_vector_px_per_mm"),
        "marker image motion vector",
    )
    for frame in frames:
        if abs(float(frame["commanded_position_mm"][2]) - 0.5) > 1e-9:
            raise ToolXYError("tool-XY analysis requires commanded Z=0.5 mm")

    valid_paths = []
    valid_frames = []
    fiducials_by_source_seq: dict[int, dict[str, Any]] = {}
    records_by_seq: dict[int, dict[str, Any]] = {}
    for path, frame in zip(frame_paths, frames):
        source_seq = int(frame["seq"])
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ToolXYError(f"cannot decode {path}")
        try:
            fiducials = detect_four_fiducials(image)
        except FourFiducialError as exc:
            records_by_seq[source_seq] = {
                "seq": source_seq,
                "tool": tool,
                "x_mm": float(frame["x_mm"]),
                "accepted": False,
                "rejection_reasons": [f"four-fiducial detection failed: {exc}"],
            }
            continue
        fiducials_by_source_seq[source_seq] = fiducials
        valid_paths.append(path)
        fiducial_center = np.mean(
            np.asarray(fiducials["centers_px"], dtype=np.float64), axis=0
        )
        commanded_x = float(frame["commanded_position_mm"][0])
        expected_marker = (
            fiducial_center
            + image_x_vector * float(corner_xy[0] - fiducial_xy[0])
            + image_y_vector * float(corner_xy[1] - fiducial_xy[1])
            + marker_x_vector * (marker_offset + commanded_x - marker_reference_x)
        )
        analysis_frame = dict(frame)
        analysis_frame["expected_marker_pixel_px"] = expected_marker.tolist()
        valid_frames.append(analysis_frame)

    if len(valid_frames) >= 2:
        try:
            localized = localize_nozzle_tip_grid(
                valid_paths,
                frames=valid_frames,
                propagate_missing_rings=True,
                commanded_x_vector_px_per_mm=image_x_vector,
                physical_tip_cluster_radius_px=16.0,
            )
        except NozzleTipLocalizationError as exc:
            localized = None
            for frame in valid_frames:
                source_seq = int(frame["seq"])
                records_by_seq[source_seq] = {
                    "seq": source_seq,
                    "tool": tool,
                    "x_mm": float(frame["x_mm"]),
                    "accepted": False,
                    "rejection_reasons": [f"nozzle-tip localization failed: {exc}"],
                }
    else:
        localized = None
        for frame in valid_frames:
            source_seq = int(frame["seq"])
            records_by_seq[source_seq] = {
                "seq": source_seq,
                "tool": tool,
                "x_mm": float(frame["x_mm"]),
                "accepted": False,
                "rejection_reasons": ["fewer than two fiducial-valid frames"],
            }

    if localized is not None:
        for local_index, registration in enumerate(localized["registrations"]):
            frame = valid_frames[local_index]
            source_seq = int(frame["seq"])
            fiducials = fiducials_by_source_seq[source_seq]
            fiducial_centers = np.asarray(fiducials["centers_px"], dtype=np.float64)
            fiducial_center = np.mean(fiducial_centers, axis=0)
            tip_center = _vector(registration["center_px"], "tip center")
            delta_mm = _pixel_delta_to_printer_xy_mm(
                tip_center - fiducial_center,
                x_vector_px_per_mm=image_x_vector,
                y_vector_px_per_mm=image_y_vector,
            )
            commanded_x, commanded_y, _commanded_z = [
                float(item) for item in frame["commanded_position_mm"]
            ]
            reasons = _registration_reasons(registration)
            records_by_seq[source_seq] = _finite(
                {
                    **registration,
                    "seq": source_seq,
                    "fiducial_centers_px": fiducial_centers,
                    "fiducial_patch_center_px": fiducial_center,
                    "tip_center_px": tip_center,
                    "fiducials_to_tip_xy_mm": delta_mm,
                    "x_datum_mm": commanded_x - float(delta_mm[0]),
                    "y_datum_mm": commanded_y + float(delta_mm[1]),
                    "accepted": not reasons,
                    "rejection_reasons": reasons,
                }
            )

    preliminary = [record for record in records_by_seq.values() if record["accepted"]]
    if preliminary:
        preliminary_median = np.median(
            np.asarray(
                [
                    [record["x_datum_mm"], record["y_datum_mm"]]
                    for record in preliminary
                ],
                dtype=np.float64,
            ),
            axis=0,
        )
        for record in preliminary:
            residual = float(
                np.linalg.norm(
                    np.asarray([record["x_datum_mm"], record["y_datum_mm"]])
                    - preliminary_median
                )
            )
            record["datum_residual_mm"] = residual
            if residual > MAXIMUM_DATUM_RESIDUAL_MM:
                record["accepted"] = False
                record["rejection_reasons"].append(
                    f"datum residual {residual:.3f} mm exceeds "
                    f"{MAXIMUM_DATUM_RESIDUAL_MM:.3f} mm"
                )

    records = [records_by_seq[int(frame["seq"])] for frame in frames]
    accepted_records = [record for record in records if record["accepted"]]
    accepted_x = sorted({float(record["x_mm"]) for record in accepted_records})
    accepted_x_span = accepted_x[-1] - accepted_x[0] if len(accepted_x) >= 2 else 0.0
    reasons = []
    if len(accepted_records) < MINIMUM_ACCEPTED_FRAMES:
        reasons.append(
            f"only {len(accepted_records)} accepted frames; "
            f"at least {MINIMUM_ACCEPTED_FRAMES} are required"
        )
    if accepted_x_span < MINIMUM_ACCEPTED_X_SPAN_MM:
        reasons.append(
            f"accepted X span {accepted_x_span:.3f} mm is below "
            f"{MINIMUM_ACCEPTED_X_SPAN_MM:.3f} mm"
        )
    datum = None
    if accepted_records:
        datum = np.median(
            np.asarray(
                [
                    [record["x_datum_mm"], record["y_datum_mm"]]
                    for record in accepted_records
                ],
                dtype=np.float64,
            ),
            axis=0,
        )
    artifacts = _write_overlays(
        frame_paths,
        frames,
        records,
        artifact_dir,
        acquisition_calibration,
    )
    return _finite(
        {
            "accepted": not reasons,
            "reasons": reasons,
            "warnings": [],
            "tool": tool,
            "commanded_z_mm": 0.5,
            "x_datum_mm": datum[0] if datum is not None else None,
            "y_datum_mm": datum[1] if datum is not None else None,
            "accepted_count": len(accepted_records),
            "captured_count": len(frames),
            "accepted_x_span_mm": accepted_x_span,
            "records": records,
            "artifacts": artifacts,
        }
    )


def build_measurement_fact(
    details: dict[str, Any],
    *,
    acquisition_calibration: dict[str, Any],
) -> dict[str, Any]:
    if not details.get("accepted"):
        raise ToolXYError("cannot build a fact from a rejected tool-XY analysis")
    tool = str(details.get("tool", ""))
    if tool not in {"T0", "T1"}:
        raise ToolXYError("tool-XY analysis has an invalid tool")
    tool_key = tool.lower()
    try:
        endstop = acquisition_calibration["tool_xy_endstops_mm"][tool_key]
        acquisition_xy = [float(endstop["x"]), float(endstop["y"])]
    except (KeyError, TypeError, ValueError):
        raise ToolXYError(
            "acquisition calibration lacks the selected endstop"
        ) from None
    return {
        "x_datum_mm": float(details["x_datum_mm"]),
        "y_datum_mm": float(details["y_datum_mm"]),
        "acquisition_endstop_xy_mm": acquisition_xy,
        "commanded_z_mm": float(details["commanded_z_mm"]),
    }
