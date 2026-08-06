#!/usr/bin/env python3
"""Report-only combined T0/T1 nozzle image X/Z sweep."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from vision_four_fiducials import FourFiducialError, detect_four_fiducials
from vision_nozzle_tip_localization import (
    NozzleTipLocalizationError,
    localize_nozzle_tip_grid,
)


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
        "fiducial_centroid_uv_px": None,
        "nozzle_detected": False,
        "fiducials_detected": False,
        "reasons": [],
    }


def _write_overlay(
    image: np.ndarray,
    frame: dict[str, Any],
    record: dict[str, Any],
    path: Path,
) -> None:
    overlay = image.copy()
    color = (0, 255, 0) if record["nozzle_detected"] else (0, 0, 255)
    centers = record.get("fiducial_centers_uv_px") or []
    for center in centers:
        cv2.circle(overlay, tuple(np.rint(center).astype(int)), 8, (0, 255, 255), 2)
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
        "detected" if record["nozzle_detected"] else "nozzle not detected",
    ]
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
    colors = {"T0": "tab:blue", "T1": "tab:orange"}
    markers = {"T0": "o", "T1": "s"}
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
                color=colors[tool],
                label=f"{tool} Z={z_mm:g} mm",
            )
    axis.set_title("Nozzle image u coordinate versus commanded X")
    axis.set_xlabel("Commanded X (mm)")
    axis.set_ylabel("Nozzle u (px)")
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
    if len(frame_paths) != len(frames):
        raise ToolXZSweepError("X/Z sweep frame paths do not match the manifest")
    if not frames:
        raise ToolXZSweepError("X/Z sweep has no frames")
    if {frame.get("tool") for frame in frames} != {"T0", "T1"}:
        raise ToolXZSweepError("X/Z sweep requires both T0 and T1 frames")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    overlay_dir = artifact_dir / "tool_xz_sweep_overlays"
    overlay_dir.mkdir(parents=True, exist_ok=True)
    records = [_base_record(frame) for frame in frames]
    images: dict[int, np.ndarray] = {}
    valid_for_localization: dict[str, list[int]] = {"T0": [], "T1": []}

    for index, (path, frame, record) in enumerate(zip(frame_paths, frames, records)):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise ToolXZSweepError(f"X/Z sweep image {index} cannot be decoded")
        images[index] = image
        try:
            fiducials = detect_four_fiducials(image)
        except FourFiducialError as exc:
            record["reasons"].append(f"four-fiducial detection failed: {exc}")
            continue
        centers = np.asarray(fiducials["centers_px"], dtype=np.float64)
        record["fiducials_detected"] = True
        record["fiducial_centers_uv_px"] = centers.tolist()
        record["fiducial_radii_px"] = [float(value) for value in fiducials["radii_px"]]
        record["fiducial_centroid_uv_px"] = np.mean(centers, axis=0).tolist()
        valid_for_localization[frame["tool"]].append(index)

    for tool in ("T0", "T1"):
        indices = valid_for_localization[tool]
        if not indices:
            continue
        tool_paths = [frame_paths[index] for index in indices]
        tool_frames = [frames[index] for index in indices]
        try:
            localized = localize_nozzle_tip_grid(
                tool_paths,
                frames=tool_frames,
                propagate_missing_rings=True,
                physical_tip_cluster_radius_px=16.0,
            )
        except NozzleTipLocalizationError as exc:
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
            records[source_index]["localization"] = _finite(
                {
                    key: value
                    for key, value in registration.items()
                    if key not in {"center_px", "marker_center_px", "ring_center_px"}
                }
            )

    artifacts: dict[str, dict[str, str]] = {}
    for index, (frame, record) in enumerate(zip(frames, records)):
        overlay_path = overlay_dir / f"{frame['frame']}.png"
        _write_overlay(images[index], frame, record, overlay_path)
        artifacts[f"tool_xz_sweep_overlay_{int(frame['seq']):02d}"] = _artifact(
            overlay_path
        )

    plot_path = artifact_dir / "tool_xz_sweep_u_vs_x.png"
    _write_u_plot(records, plot_path)
    artifacts["tool_xz_sweep_u_vs_x"] = _artifact(plot_path)

    missing_fiducials = sum(not record["fiducials_detected"] for record in records)
    missing_nozzles = sum(not record["nozzle_detected"] for record in records)
    warnings = []
    if missing_fiducials:
        warnings.append(f"{missing_fiducials} frame(s) lack four-fiducial detections")
    if missing_nozzles:
        warnings.append(f"{missing_nozzles} frame(s) lack nozzle-tip detections")
    dimensions = images[0].shape
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
            "image_dimensions_px": [int(dimensions[1]), int(dimensions[0])],
            "records": records,
            "acquisition_calibration": acquisition_calibration,
            "artifacts": artifacts,
        }
    )
