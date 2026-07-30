#!/usr/bin/env python3
"""Rough two-tool X calibration calculations and two-frame verification."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from vision_calibration_graph import sha256_file
from vision_red_marker_x_sweep import (
    _pair_registration,
    _red_candidates,
    _representations,
)


LOCALIZER = {"kind": "rough_x_marker_verification", "version": 1}
MAX_ABSOLUTE_RESIDUAL_MM = 1.5
MAX_CROSS_TOOL_DISAGREEMENT_MM = 1.0
MIN_CROSS_TOOL_CORRELATION = 0.65
MAX_REPRESENTATION_SPREAD_PX = 2.5
MAX_FORWARD_REVERSE_DISAGREEMENT_PX = 2.5


def _finite_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _finite_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_json(item) for item in value]
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def calculate_candidate(
    *,
    prior_xyz_mm: list[float],
    t0_marker_fact: dict[str, Any],
    t1_marker_fact: dict[str, Any],
    old_t0_x_endstop_mm: float,
    old_t1_x_endstop_mm: float,
    decimals: int = 3,
) -> dict[str, Any]:
    if len(prior_xyz_mm) != 3:
        raise ValueError("bed-tab prior must contain XYZ")
    bed_tab_x = float(prior_xyz_mm[0])
    result: dict[str, Any] = {
        "bed_tab_corner_xyz_mm": [float(value) for value in prior_xyz_mm],
        "tools": {},
    }
    for tool, fact, old_endstop in (
        ("T0", t0_marker_fact, old_t0_x_endstop_mm),
        ("T1", t1_marker_fact, old_t1_x_endstop_mm),
    ):
        offset = float(fact["offset_mm"])
        reference_x = float(fact["reference_commanded_x_mm"])
        correction = bed_tab_x + offset - reference_x
        exact_candidate = float(old_endstop) + correction
        result["tools"][tool] = {
            "old_x_endstop_mm": float(old_endstop),
            "marker_to_bed_tab_x_mm": offset,
            "reference_commanded_x_mm": reference_x,
            "calculated_correction_mm": correction,
            "exact_candidate_x_endstop_mm": exact_candidate,
            "candidate_x_endstop_mm": round(exact_candidate, decimals),
        }
    return result


def _projection_mm(
    point: np.ndarray,
    corner: np.ndarray,
    unit_x: np.ndarray,
    scale: float,
) -> float:
    return float(np.dot(point - corner, unit_x) / scale)


def _select_candidate(
    candidates: list[dict[str, Any]],
    *,
    corner: np.ndarray,
    unit_x: np.ndarray,
    scale: float,
    expected_offset_mm: float,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    scored = []
    for candidate in candidates:
        center = np.asarray(candidate["center_px"], dtype=float)
        offset = _projection_mm(center, corner, unit_x, scale)
        scored.append(
            {
                **candidate,
                "projected_offset_mm": offset,
                "absolute_residual_mm": abs(offset - expected_offset_mm),
            }
        )
    scored.sort(key=lambda item: item["absolute_residual_mm"])
    return (scored[0] if scored else None), scored


def _line_through_projection(
    image: np.ndarray,
    point: np.ndarray,
    unit_x: np.ndarray,
    color: tuple[int, int, int],
    thickness: int,
) -> None:
    height, width = image.shape[:2]
    normal = np.asarray([-unit_x[1], unit_x[0]], dtype=float)
    extent = float(max(width, height) * 2)
    first = point - normal * extent
    second = point + normal * extent
    cv2.line(
        image,
        tuple(int(round(value)) for value in first),
        tuple(int(round(value)) for value in second),
        color,
        thickness,
        cv2.LINE_AA,
    )


def _verification_overlay(
    images: list[np.ndarray],
    records: list[dict[str, Any]],
    *,
    corner: np.ndarray,
    expected_point: np.ndarray,
    unit_x: np.ndarray,
    path: Path,
) -> None:
    panels = []
    for image, record in zip(images, records):
        panel = image.copy()
        _line_through_projection(panel, expected_point, unit_x, (0, 255, 255), 4)
        cv2.circle(
            panel,
            tuple(int(round(value)) for value in corner),
            14,
            (255, 255, 0),
            3,
            cv2.LINE_AA,
        )
        for candidate in record["candidates"]:
            x0, y0, x1, y1 = candidate["bbox_px"]
            cv2.rectangle(panel, (x0, y0), (x1, y1), (0, 0, 180), 2)
        selected = record.get("selected")
        if selected:
            x0, y0, x1, y1 = selected["bbox_px"]
            cv2.rectangle(panel, (x0, y0), (x1, y1), (0, 255, 0), 4)
            center = tuple(
                int(round(value)) for value in selected["center_px"]
            )
            cv2.drawMarker(
                panel,
                center,
                (0, 255, 0),
                cv2.MARKER_CROSS,
                30,
                3,
                cv2.LINE_AA,
            )
        cv2.putText(
            panel,
            (
                f"{record['tool']} X={record['x_mm']:.3f}: "
                f"{record.get('marker_offset_mm', float('nan')):.3f} mm "
                f"(res {record.get('residual_mm', float('nan')):+.3f})"
            ),
            (35, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 255),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            panel,
            "yellow: expected +10 mm image-X  cyan: bed-tab corner",
            (35, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        panels.append(panel)
    canvas = np.hstack(panels)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas)


def _cross_registration_overlay(
    source: np.ndarray,
    target: np.ndarray,
    source_center: np.ndarray,
    registered_target_center: np.ndarray,
    registration: dict[str, Any],
    path: Path,
) -> None:
    panel0 = source.copy()
    panel1 = target.copy()
    for panel, center, label in (
        (panel0, source_center, "T0 template center"),
        (panel1, registered_target_center, "T1 registered center"),
    ):
        point = tuple(int(round(value)) for value in center)
        cv2.drawMarker(
            panel,
            point,
            (255, 0, 255),
            cv2.MARKER_CROSS,
            35,
            4,
            cv2.LINE_AA,
        )
        cv2.putText(
            panel,
            label,
            (35, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 0, 255),
            3,
            cv2.LINE_AA,
        )
    cv2.putText(
        panel1,
        (
            f"corr {registration['minimum_correlation']:.3f}; "
            f"shift {registration['shift_px']}"
        ),
        (35, 100),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    canvas = np.hstack([panel0, panel1])
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), canvas)


def analyze(
    frame_paths: list[Path],
    output_dir: Path,
    *,
    frames: list[dict[str, Any]],
    reference: dict[str, Any],
    localizer: dict[str, Any],
) -> dict[str, Any]:
    if localizer != LOCALIZER:
        raise ValueError(f"unsupported rough-X verification localizer {localizer!r}")
    if len(frame_paths) != 2 or len(frames) != 2:
        raise ValueError("rough-X verification requires exactly two images")
    if [frame.get("tool") for frame in frames] != ["T0", "T1"]:
        raise ValueError("rough-X verification frames must be T0 then T1")
    images = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in frame_paths]
    if any(image is None for image in images):
        raise ValueError("one or more rough-X verification images cannot be decoded")
    if len({image.shape[:2] for image in images}) != 1:
        raise ValueError("rough-X verification image dimensions changed")

    x_vector = np.asarray(reference["image_x_axis_vector_px_per_mm"], dtype=float)
    scale = float(np.linalg.norm(x_vector))
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError("rough-X verification image X axis is degenerate")
    unit_x = x_vector / scale
    corner = np.asarray(reference["corner_pixel_xy_px"], dtype=float)
    corner_xyz = np.asarray(reference["corner_printer_xyz_mm"], dtype=float)
    y_vector = np.asarray(reference["image_y_axis_vector_px_per_mm"], dtype=float)
    capture_y = float(reference["capture_y_mm"])
    corner_at_capture = corner + y_vector * (
        capture_y - float(corner_xyz[1])
    )
    expected_offset = float(reference["expected_offset_mm"])
    expected_point = corner_at_capture + x_vector * expected_offset

    records = []
    reasons: list[str] = []
    for index, (image, frame) in enumerate(zip(images, frames)):
        candidates = _red_candidates(image, index)
        selected, scored = _select_candidate(
            candidates,
            corner=corner_at_capture,
            unit_x=unit_x,
            scale=scale,
            expected_offset_mm=expected_offset,
        )
        record = {
            "tool": frame["tool"],
            "x_mm": float(frame["x_mm"]),
            "candidates": scored,
            "selected": selected,
        }
        if selected is None:
            reasons.append(f"{frame['tool']} red marker was not found")
        else:
            record["marker_offset_mm"] = selected["projected_offset_mm"]
            record["residual_mm"] = (
                selected["projected_offset_mm"] - expected_offset
            )
        records.append(record)

    registration = None
    registered_t1_center = None
    if not reasons:
        t0_center = np.asarray(records[0]["selected"]["center_px"], dtype=float)
        t1_search_center = np.asarray(
            records[1]["selected"]["center_px"], dtype=float
        )
        registration = _pair_registration(
            _representations(images[0]),
            t0_center,
            _representations(images[1]),
            t1_search_center,
        )
        registered_t1_center = t0_center + np.asarray(
            registration["shift_px"], dtype=float
        )
        t1_registered_offset = _projection_mm(
            registered_t1_center, corner_at_capture, unit_x, scale
        )
        records[1]["registered_marker_center_px"] = registered_t1_center.tolist()
        records[1]["marker_offset_mm"] = t1_registered_offset
        records[1]["residual_mm"] = t1_registered_offset - expected_offset
        if registration["boundary_hit"]:
            reasons.append("cross-tool marker registration hit a search boundary")
        if registration["minimum_correlation"] < MIN_CROSS_TOOL_CORRELATION:
            reasons.append("cross-tool marker registration correlation is too low")
        if (
            registration["representation_spread_px"]
            > MAX_REPRESENTATION_SPREAD_PX
        ):
            reasons.append("grayscale and CLAHE marker registrations disagree")
        if (
            registration["maximum_forward_reverse_disagreement_px"]
            > MAX_FORWARD_REVERSE_DISAGREEMENT_PX
        ):
            reasons.append("forward and reverse marker registrations disagree")

    residuals = {
        record["tool"]: record.get("residual_mm") for record in records
    }
    if all(value is not None for value in residuals.values()):
        for tool, residual in residuals.items():
            if abs(float(residual)) > MAX_ABSOLUTE_RESIDUAL_MM:
                reasons.append(
                    f"{tool} absolute marker residual exceeds "
                    f"{MAX_ABSOLUTE_RESIDUAL_MM:.1f} mm"
                )
        marker_coincidence_residual = float(
            records[1]["marker_offset_mm"] - records[0]["marker_offset_mm"]
        )
        if abs(marker_coincidence_residual) > MAX_CROSS_TOOL_DISAGREEMENT_MM:
            reasons.append(
                "T0/T1 marker image-X disagreement exceeds "
                f"{MAX_CROSS_TOOL_DISAGREEMENT_MM:.1f} mm"
            )
    else:
        marker_coincidence_residual = None

    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = output_dir / "verification_overlay.jpg"
    _verification_overlay(
        images,
        records,
        corner=corner_at_capture,
        expected_point=expected_point,
        unit_x=unit_x,
        path=overlay_path,
    )
    artifact_paths = {"verification_overlay": overlay_path}
    if registration is not None and registered_t1_center is not None:
        registration_path = output_dir / "cross_tool_registration.jpg"
        _cross_registration_overlay(
            images[0],
            images[1],
            np.asarray(records[0]["selected"]["center_px"], dtype=float),
            registered_t1_center,
            registration,
            registration_path,
        )
        artifact_paths["cross_tool_registration"] = registration_path

    return _finite_json(
        {
            "accepted": not reasons,
            "reasons": sorted(set(reasons)),
            "warnings": [],
            "localizer": LOCALIZER,
            "verification_command_x_mm": float(reference["command_x_mm"]),
            "expected_offset_mm": expected_offset,
            "corner_pixel_at_capture_y_px": corner_at_capture.tolist(),
            "expected_image_x_point_px": expected_point.tolist(),
            "image_x_axis_vector_px_per_mm": x_vector.tolist(),
            "records": records,
            "t0_marker_offset_mm": records[0].get("marker_offset_mm"),
            "t1_marker_offset_mm": records[1].get("marker_offset_mm"),
            "t0_residual_mm": residuals["T0"],
            "t1_residual_mm": residuals["T1"],
            "marker_coincidence_residual_mm": marker_coincidence_residual,
            "cross_registration": registration,
            "artifacts": {
                name: {"path": str(path), "sha256": sha256_file(path)}
                for name, path in artifact_paths.items()
            },
        }
    )
