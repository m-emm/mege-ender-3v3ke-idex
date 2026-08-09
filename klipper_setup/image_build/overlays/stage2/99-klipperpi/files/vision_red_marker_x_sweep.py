#!/usr/bin/env python3
"""Coordinate-free red-marker trajectory discovery and tight registration."""

from __future__ import annotations

import itertools
import logging
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from vision_calibration_graph import sha256_file

_logger = logging.getLogger("vision_red_marker_x_sweep")

LOCALIZER = {"kind": "red_marker_trajectory", "version": 1}
MIN_TOOL_FRAMES = 3
MIN_TOOL_SPAN_MM = 20.0
MIN_SCALE_PX_PER_MM = 2.0
MAX_SCALE_PX_PER_MM = 30.0
MAX_TOOL_SCALE_DELTA = 0.05
MAX_TOOL_ANGLE_DELTA_DEG = 2.0
MAX_FIT_RMS_PX = 1.5
MAX_REPRESENTATION_SPREAD_PX = 2.0
# The live tool-mounted fiducial patch can change local contrast as the tool
# crosses the camera view.  Keep the geometric and bidirectional registration
# gates strict, but do not discard an otherwise coherent trajectory solely for
# a moderate single-pair correlation dip.
MIN_WITHIN_TOOL_CORRELATION = 0.55
MIN_CROSS_TOOL_CORRELATION = 0.65
BRIGHT_CORE_FRAME_PERCENTILE = 95.0
BRIGHT_CORE_FRAME_FRACTION = 0.55
MIN_BRIGHT_CORE_VALUE = 80.0
MIN_BRIGHT_CORE_FRACTION = 0.50
MIN_RED_DOMINANCE_MEDIAN = 0.40
MIN_STRONG_RED_FRACTION = 0.50


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


def _angle_degrees(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator <= 1.0e-12:
        return float("inf")
    cosine = float(np.clip(np.dot(a, b) / denominator, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def _representations(image: np.ndarray) -> dict[str, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return {
        "gray": gray,
        "clahe": cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray),
    }


def _red_candidates(image: np.ndarray, frame_index: int) -> list[dict[str, Any]]:
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = (
        ((hsv[:, :, 0] <= 16) | (hsv[:, :, 0] >= 165))
        & (hsv[:, :, 1] >= 75)
        & (hsv[:, :, 2] >= 45)
    ).astype(np.uint8) * 255
    kernel_size = max(3, int(round(min(width / 1920.0, height / 1080.0) * 3)))
    if kernel_size % 2 == 0:
        kernel_size += 1
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        np.ones((kernel_size, kernel_size), dtype=np.uint8),
    )
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    image_area = float(width * height)
    brightness_reference = float(
        np.percentile(hsv[:, :, 2], BRIGHT_CORE_FRAME_PERCENTILE)
    )
    bright_core_value = max(
        MIN_BRIGHT_CORE_VALUE,
        BRIGHT_CORE_FRAME_FRACTION * brightness_reference,
    )
    candidates: list[dict[str, Any]] = []
    rejection_counts: dict[str, int] = {}
    detailed_rejections = 0
    for component in range(1, count):
        x, y, box_width, box_height, area = [int(item) for item in stats[component]]
        fill = area / float(max(1, box_width * box_height))
        relative_area = area / image_area
        rejection_reasons = []
        if not 0.00012 <= relative_area <= 0.008:
            rejection_reasons.append("relative_area")
        if not 0.005 * width <= box_width <= 0.095 * width:
            rejection_reasons.append("width")
        if not 0.014 * height <= box_height <= 0.19 * height:
            rejection_reasons.append("height")
        if fill < 0.08:
            rejection_reasons.append("fill")
        boundary = (
            x <= 0.10 * width
            or x + box_width >= 0.90 * width
            or y <= 0.05 * height
            or y + box_height >= 0.90 * height
        )
        if boundary:
            rejection_reasons.append("boundary")
        center = [
            float(centroids[component][0]),
            float(centroids[component][1]),
        ]
        bbox = [x, y, x + box_width, y + box_height]
        if rejection_reasons:
            for reason in rejection_reasons:
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            # A full-resolution capture can contain hundreds of isolated red
            # pixels.  They fail the minimum area gate and are summarized below;
            # log only components large enough to be visually plausible.
            if relative_area >= 0.00012:
                detailed_rejections += 1
                _logger.info(
                    "Marker component reject frame=%02d component=%d center=%s bbox=%s "
                    "area=%d relative_area=%.6f fill=%.3f brightness=not_evaluated "
                    "reasons=%s",
                    frame_index,
                    component,
                    center,
                    bbox,
                    area,
                    relative_area,
                    fill,
                    ",".join(rejection_reasons),
                )
            continue
        # Do this only after the inexpensive geometry and boundary gates.  A
        # noisy full-resolution HSV mask may contain hundreds of tiny pieces;
        # indexing the whole label image for each one wastes CPU and memory.
        component_labels = labels[y : y + box_height, x : x + box_width]
        component_values = hsv[y : y + box_height, x : x + box_width, 2][
            component_labels == component
        ]
        component_bgr = image[y : y + box_height, x : x + box_width][
            component_labels == component
        ].astype(np.float32)
        blue, green, red = component_bgr.T
        red_dominance = (red - np.maximum(blue, green)) / np.maximum(red, 1.0)
        median_red_dominance = float(np.median(red_dominance))
        strong_red_fraction = float(np.mean(red_dominance >= 0.40))
        median_value = float(np.median(component_values))
        bright_core_fraction = float(np.mean(component_values >= bright_core_value))
        color_rejection_reasons = []
        if bright_core_fraction < MIN_BRIGHT_CORE_FRACTION:
            color_rejection_reasons.append("bright_core")
        if median_red_dominance < MIN_RED_DOMINANCE_MEDIAN:
            color_rejection_reasons.append("red_dominance")
        if strong_red_fraction < MIN_STRONG_RED_FRACTION:
            color_rejection_reasons.append("strong_red_fraction")
        if color_rejection_reasons:
            for reason in color_rejection_reasons:
                rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
            detailed_rejections += 1
            _logger.info(
                "Marker component reject frame=%02d component=%d center=%s bbox=%s "
                "area=%d relative_area=%.6f fill=%.3f median_value=%.1f "
                "bright_core_fraction=%.3f bright_core_value=%.1f "
                "red_dominance_median=%.3f strong_red_fraction=%.3f "
                "reasons=%s",
                frame_index,
                component,
                center,
                bbox,
                area,
                relative_area,
                fill,
                median_value,
                bright_core_fraction,
                bright_core_value,
                median_red_dominance,
                strong_red_fraction,
                ",".join(color_rejection_reasons),
            )
            continue
        candidate = {
            "candidate_id": f"f{frame_index:02d}_red_{len(candidates):02d}",
            "center_px": center,
            "bbox_px": bbox,
            "area_px": area,
            "relative_area": relative_area,
            "fill_fraction": fill,
            "median_value": median_value,
            "bright_core_fraction": bright_core_fraction,
            "bright_core_value": bright_core_value,
            "red_dominance_median": median_red_dominance,
            "strong_red_fraction": strong_red_fraction,
        }
        candidates.append(candidate)
        _logger.info(
            "Marker component keep frame=%02d candidate=%s center=%s bbox=%s "
            "area=%d relative_area=%.6f fill=%.3f median_value=%.1f "
            "bright_core_fraction=%.3f bright_core_value=%.1f "
            "red_dominance_median=%.3f strong_red_fraction=%.3f "
            "reason=passes_component_gates",
            frame_index,
            candidate["candidate_id"],
            center,
            bbox,
            area,
            relative_area,
            fill,
            median_value,
            bright_core_fraction,
            bright_core_value,
            median_red_dominance,
            strong_red_fraction,
        )
    _logger.info(
        "Marker component summary frame=%02d connected=%d kept=%d "
        "detailed_rejected=%d tiny_rejected=%d brightness_reference=%.1f "
        "bright_core_value=%.1f rejection_counts=%s",
        frame_index,
        count - 1,
        len(candidates),
        detailed_rejections,
        count - 1 - len(candidates) - detailed_rejections,
        brightness_reference,
        bright_core_value,
        rejection_counts,
    )
    return candidates


def _subpixel_peak(scores: np.ndarray, x: int, y: int) -> tuple[float, float]:
    refined = [float(x), float(y)]
    for axis, coordinate in enumerate((x, y)):
        limit = scores.shape[1] if axis == 0 else scores.shape[0]
        if coordinate <= 0 or coordinate >= limit - 1:
            continue
        if axis == 0:
            before, center, after = scores[y, x - 1 : x + 2]
        else:
            before, center, after = scores[y - 1 : y + 2, x]
        denominator = float(before - 2.0 * center + after)
        if abs(denominator) > 1.0e-9:
            refined[axis] += float(
                np.clip(0.5 * (before - after) / denominator, -0.5, 0.5)
            )
    return refined[0], refined[1]


def _one_way_registration(
    source: np.ndarray,
    source_center: np.ndarray,
    target: np.ndarray,
    target_center: np.ndarray,
) -> dict[str, Any]:
    height, width = source.shape[:2]
    roi_width = max(32, int(round(70.0 * width / 1920.0)))
    roi_height = max(44, int(round(100.0 * height / 1080.0)))
    margin_x = max(16, int(round(35.0 * width / 1920.0)))
    margin_y = max(16, int(round(35.0 * height / 1080.0)))
    x0 = int(round(float(source_center[0]) - roi_width / 2.0))
    y0 = int(round(float(source_center[1]) - roi_height / 2.0))
    x0 = min(max(0, x0), width - roi_width)
    y0 = min(max(0, y0), height - roi_height)
    template = source[y0 : y0 + roi_height, x0 : x0 + roi_width]
    tx0 = int(round(float(target_center[0]) - roi_width / 2.0 - margin_x))
    ty0 = int(round(float(target_center[1]) - roi_height / 2.0 - margin_y))
    tx0 = min(max(0, tx0), width - roi_width - 2 * margin_x)
    ty0 = min(max(0, ty0), height - roi_height - 2 * margin_y)
    search = target[
        ty0 : ty0 + roi_height + 2 * margin_y,
        tx0 : tx0 + roi_width + 2 * margin_x,
    ]
    if (
        template.size == 0
        or search.shape[0] < roi_height
        or search.shape[1] < roi_width
    ):
        raise ValueError("registration ROI lies outside the image")
    scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _minimum, maximum, _minimum_location, location = cv2.minMaxLoc(scores)
    peak_x, peak_y = _subpixel_peak(scores, location[0], location[1])
    matched_center = np.asarray(
        [
            tx0 + peak_x + roi_width / 2.0,
            ty0 + peak_y + roi_height / 2.0,
        ],
        dtype=float,
    )
    boundary = (
        location[0] <= 0
        or location[1] <= 0
        or location[0] >= scores.shape[1] - 1
        or location[1] >= scores.shape[0] - 1
    )
    return {
        "shift_px": (matched_center - source_center).tolist(),
        "correlation": float(maximum),
        "boundary_hit": boundary,
        "source_roi_px": [x0, y0, x0 + roi_width, y0 + roi_height],
        "target_search_px": [
            tx0,
            ty0,
            tx0 + roi_width + 2 * margin_x,
            ty0 + roi_height + 2 * margin_y,
        ],
    }


def _pair_registration(
    source_representations: dict[str, np.ndarray],
    source_center: np.ndarray,
    target_representations: dict[str, np.ndarray],
    target_center: np.ndarray,
) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for representation in ("gray", "clahe"):
        forward = _one_way_registration(
            source_representations[representation],
            source_center,
            target_representations[representation],
            target_center,
        )
        reverse = _one_way_registration(
            target_representations[representation],
            target_center,
            source_representations[representation],
            source_center,
        )
        forward_shift = np.asarray(forward["shift_px"], dtype=float)
        reverse_as_forward = -np.asarray(reverse["shift_px"], dtype=float)
        combined = (forward_shift + reverse_as_forward) / 2.0
        disagreement = float(np.linalg.norm(forward_shift - reverse_as_forward))
        records[representation] = {
            "forward": forward,
            "reverse": reverse,
            "combined_shift_px": combined.tolist(),
            "forward_reverse_disagreement_px": disagreement,
        }
    usable_names = [
        name
        for name, record in records.items()
        if not record["forward"]["boundary_hit"]
        and not record["reverse"]["boundary_hit"]
        and record["forward_reverse_disagreement_px"] <= MAX_REPRESENTATION_SPREAD_PX
    ]
    if not usable_names:
        return {
            "shift_px": [0.0, 0.0],
            "minimum_correlation": min(
                min(record["forward"]["correlation"], record["reverse"]["correlation"])
                for record in records.values()
            ),
            "median_correlation": float(
                np.median(
                    [
                        value
                        for record in records.values()
                        for value in (
                            record["forward"]["correlation"],
                            record["reverse"]["correlation"],
                        )
                    ]
                )
            ),
            "representation_spread_px": float("inf"),
            "maximum_forward_reverse_disagreement_px": max(
                record["forward_reverse_disagreement_px"] for record in records.values()
            ),
            "boundary_hit": True,
            "usable_representations": [],
            "representations": records,
        }

    usable_records = [records[name] for name in usable_names]
    shifts = [
        np.asarray(record["combined_shift_px"], dtype=float)
        for record in usable_records
    ]
    correlations = [
        value
        for record in usable_records
        for value in (
            record["forward"]["correlation"],
            record["reverse"]["correlation"],
        )
    ]
    spread = float(np.linalg.norm(shifts[0] - shifts[1])) if len(shifts) > 1 else 0.0
    return {
        "shift_px": np.mean(np.asarray(shifts), axis=0).tolist(),
        "minimum_correlation": min(correlations),
        "median_correlation": float(np.median(correlations)),
        "representation_spread_px": spread,
        "maximum_forward_reverse_disagreement_px": max(
            record["forward_reverse_disagreement_px"] for record in usable_records
        ),
        "boundary_hit": False,
        "usable_representations": usable_names,
        "representations": records,
    }


def _fit_positions(
    x_values: list[float], positions: list[np.ndarray]
) -> tuple[np.ndarray, np.ndarray, float]:
    x = np.asarray(x_values, dtype=float)
    matrix = np.column_stack([x, np.ones(len(x))])
    values = np.asarray(positions, dtype=float)
    coefficients, _residuals, _rank, _singular = np.linalg.lstsq(
        matrix, values, rcond=None
    )
    vector = coefficients[0]
    intercept = coefficients[1]
    predicted = matrix @ coefficients
    residuals = np.linalg.norm(values - predicted, axis=1)
    rms = float(np.sqrt(np.mean(residuals**2)))
    return vector, intercept, rms


def _trajectory_hypotheses(
    tool_frames: list[dict[str, Any]],
    y_axis_vector: np.ndarray,
) -> list[dict[str, Any]]:
    hypotheses: list[dict[str, Any]] = []
    for frame_indices in itertools.combinations(range(len(tool_frames)), 3):
        selected_frames = [tool_frames[index] for index in frame_indices]
        x_values = [frame["x_mm"] for frame in selected_frames]
        if max(x_values) - min(x_values) < MIN_TOOL_SPAN_MM:
            continue
        candidate_lists = [frame["candidates"] for frame in selected_frames]
        if any(not candidates for candidates in candidate_lists):
            continue
        for candidates in itertools.product(*candidate_lists):
            centers = [
                np.asarray(candidate["center_px"], dtype=float)
                for candidate in candidates
            ]
            rough_vector, _rough_intercept, rough_rms = _fit_positions(
                x_values, centers
            )
            magnitude = float(np.linalg.norm(rough_vector))
            if not MIN_SCALE_PX_PER_MM <= magnitude <= MAX_SCALE_PX_PER_MM:
                continue
            if rough_rms > 25.0:
                continue
            if (
                min(
                    _angle_degrees(rough_vector, y_axis_vector),
                    _angle_degrees(rough_vector, -y_axis_vector),
                )
                < 60.0
            ):
                continue
            registrations = []
            registered_positions = [centers[0]]
            usable = True
            for source, target, source_center, target_center in zip(
                selected_frames,
                selected_frames[1:],
                centers,
                centers[1:],
            ):
                registration = _pair_registration(
                    source["representations"],
                    source_center,
                    target["representations"],
                    target_center,
                )
                if (
                    registration["boundary_hit"]
                    or registration["minimum_correlation"] < MIN_WITHIN_TOOL_CORRELATION
                    or registration["representation_spread_px"]
                    > MAX_REPRESENTATION_SPREAD_PX
                    or registration["maximum_forward_reverse_disagreement_px"]
                    > MAX_REPRESENTATION_SPREAD_PX
                ):
                    usable = False
                    break
                registrations.append(registration)
                registered_positions.append(
                    registered_positions[-1]
                    + np.asarray(registration["shift_px"], dtype=float)
                )
            if not usable:
                continue
            vector, intercept, rms = _fit_positions(x_values, registered_positions)
            magnitude = float(np.linalg.norm(vector))
            if (
                not MIN_SCALE_PX_PER_MM <= magnitude <= MAX_SCALE_PX_PER_MM
                or rms > MAX_FIT_RMS_PX
            ):
                continue
            edge_vectors = [
                np.asarray(registration["shift_px"], dtype=float)
                / (x_values[index + 1] - x_values[index])
                for index, registration in enumerate(registrations)
            ]
            if (
                len(edge_vectors) > 1
                and max(float(np.linalg.norm(edge - vector)) for edge in edge_vectors)
                > 0.25
            ):
                continue
            minimum_correlation = min(
                registration["minimum_correlation"] for registration in registrations
            )
            hypotheses.append(
                {
                    "tool": selected_frames[0]["tool"],
                    "frame_indices": list(frame_indices),
                    "x_values_mm": x_values,
                    "candidate_ids": [
                        candidate["candidate_id"] for candidate in candidates
                    ],
                    "candidate_centers_px": [
                        candidate["center_px"] for candidate in candidates
                    ],
                    "registered_positions_px": [
                        position.tolist() for position in registered_positions
                    ],
                    "axis_vector_px_per_mm": vector.tolist(),
                    "intercept_px": intercept.tolist(),
                    "fit_rms_px": rms,
                    "minimum_correlation": minimum_correlation,
                    "median_correlation": float(
                        np.median(
                            [
                                registration["median_correlation"]
                                for registration in registrations
                            ]
                        )
                    ),
                    "registrations": registrations,
                    "score": (
                        10.0 * minimum_correlation
                        - rms
                        + 0.01 * (max(x_values) - min(x_values))
                    ),
                }
            )
    hypotheses.sort(key=lambda item: item["score"], reverse=True)
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for hypothesis in hypotheses:
        signature = tuple(hypothesis["candidate_ids"])
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(hypothesis)
        if len(unique) >= 24:
            break
    return unique


def _select_cross_tool_pair(
    t0_hypotheses: list[dict[str, Any]],
    t1_hypotheses: list[dict[str, Any]],
    frames_by_tool_x: dict[tuple[str, float], dict[str, Any]],
) -> dict[str, Any] | None:
    selections = []
    for t0 in t0_hypotheses:
        vector0 = np.asarray(t0["axis_vector_px_per_mm"], dtype=float)
        for t1 in t1_hypotheses:
            vector1 = np.asarray(t1["axis_vector_px_per_mm"], dtype=float)
            magnitude_delta = abs(
                float(np.linalg.norm(vector0)) - float(np.linalg.norm(vector1))
            ) / max(float(np.linalg.norm(vector0)), float(np.linalg.norm(vector1)))
            angle_delta = _angle_degrees(vector0, vector1)
            if (
                magnitude_delta > MAX_TOOL_SCALE_DELTA
                or angle_delta > MAX_TOOL_ANGLE_DELTA_DEG
            ):
                continue
            common = sorted(
                set(t0["x_values_mm"]) & set(t1["x_values_mm"]),
                key=lambda value: (abs(value - 190.0), value),
            )
            for common_x in common:
                t0_index = t0["x_values_mm"].index(common_x)
                t1_index = t1["x_values_mm"].index(common_x)
                center0 = np.asarray(t0["candidate_centers_px"][t0_index], dtype=float)
                center1 = np.asarray(t1["candidate_centers_px"][t1_index], dtype=float)
                cross = _pair_registration(
                    frames_by_tool_x[("T0", common_x)]["representations"],
                    center0,
                    frames_by_tool_x[("T1", common_x)]["representations"],
                    center1,
                )
                if (
                    cross["boundary_hit"]
                    or cross["minimum_correlation"] < MIN_CROSS_TOOL_CORRELATION
                    or cross["representation_spread_px"] > MAX_REPRESENTATION_SPREAD_PX
                    or cross["maximum_forward_reverse_disagreement_px"]
                    > MAX_REPRESENTATION_SPREAD_PX
                ):
                    continue
                score = (
                    t0["score"]
                    + t1["score"]
                    + 12.0 * cross["minimum_correlation"]
                    - 0.01 * abs(common_x - 190.0)
                )
                selections.append(
                    {
                        "t0": t0,
                        "t1": t1,
                        "common_x_mm": common_x,
                        "t0_center_px": center0.tolist(),
                        "t1_candidate_center_px": center1.tolist(),
                        "cross_registration": cross,
                        "tool_scale_delta_fraction": magnitude_delta,
                        "tool_angle_delta_deg": angle_delta,
                        "score": score,
                    }
                )
                # Prefer the planned X=190 common reference whenever it passes.
                # Later common positions are fallbacks, not competing estimates.
                break
    if not selections:
        return None
    return max(selections, key=lambda item: item["score"])


def _contact_sheet(
    frames: list[dict[str, Any]],
    selected_ids: set[str],
    path: Path,
) -> None:
    cells = []
    cell_width, cell_height = 480, 300
    for frame in frames:
        image = cv2.resize(frame["image"], (cell_width, 270))
        for candidate in frame["candidates"]:
            scale_x = cell_width / frame["image"].shape[1]
            scale_y = 270.0 / frame["image"].shape[0]
            x0, y0, x1, y1 = candidate["bbox_px"]
            color = (
                (60, 220, 60)
                if candidate["candidate_id"] in selected_ids
                else (40, 40, 220)
            )
            cv2.rectangle(
                image,
                (round(x0 * scale_x), round(y0 * scale_y)),
                (round(x1 * scale_x), round(y1 * scale_y)),
                color,
                2,
            )
        canvas = np.zeros((cell_height, cell_width, 3), dtype=np.uint8)
        canvas[:270] = image
        cv2.putText(
            canvas,
            f"{frame['tool']} X={frame['x_mm']:.0f}",
            (10, 292),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cells.append(canvas)
    rows = [np.hstack(cells[index : index + 3]) for index in range(0, len(cells), 3)]
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.vstack(rows))


def _marker_selection_overlay(
    frames: list[dict[str, Any]],
    selected_ids: set[str],
    path: Path,
) -> None:
    cells = []
    for frame in frames:
        image = cv2.resize(frame["image"], (480, 270))
        sx = 480.0 / frame["image"].shape[1]
        sy = 270.0 / frame["image"].shape[0]
        for candidate in frame["candidates"]:
            selected = candidate["candidate_id"] in selected_ids
            color = (0, 255, 0) if selected else (0, 0, 255)
            x0, y0, x1, y1 = candidate["bbox_px"]
            cv2.rectangle(
                image,
                (round(x0 * sx), round(y0 * sy)),
                (round(x1 * sx), round(y1 * sy)),
                color,
                2,
            )
            cv2.putText(
                image,
                candidate["candidate_id"],
                (round(x0 * sx), max(14, round(y0 * sy) - 3)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                color,
                1,
                cv2.LINE_AA,
            )
        cv2.putText(
            image,
            f"{frame['tool']} X={frame['x_mm']:.0f}",
            (8, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cells.append(image)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(
        str(path),
        np.vstack(
            [np.hstack(cells[index : index + 3]) for index in range(0, len(cells), 3)]
        ),
    )


def _core_registration_overlay(
    selection: dict[str, Any],
    frames_by_tool_x: dict[tuple[str, float], dict[str, Any]],
    path: Path,
) -> None:
    cells = []
    for tool_key in ("t0", "t1"):
        track = selection[tool_key]
        positions = track["registered_positions_px"]
        for x_mm, position in zip(track["x_values_mm"], positions):
            image = frames_by_tool_x[(tool_key.upper(), x_mm)]["image"].copy()
            center = np.asarray(position, dtype=float)
            color = (0, 255, 255)
            for delta in (-35, 0, 35):
                cv2.line(
                    image,
                    (round(center[0] + delta), round(center[1] - 50)),
                    (round(center[0] + delta), round(center[1] + 50)),
                    color,
                    2,
                )
            for delta in (-50, 0, 50):
                cv2.line(
                    image,
                    (round(center[0] - 35), round(center[1] + delta)),
                    (round(center[0] + 35), round(center[1] + delta)),
                    color,
                    2,
                )
            cv2.putText(
                image,
                f"{tool_key.upper()} X={x_mm:.0f}",
                (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (0, 255, 255),
                3,
                cv2.LINE_AA,
            )
            cells.append(cv2.resize(image, (480, 270)))
    columns = 3
    while len(cells) % columns:
        cells.append(np.zeros_like(cells[0]))
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(
        str(path),
        np.vstack(
            [
                np.hstack(cells[index : index + columns])
                for index in range(0, len(cells), columns)
            ]
        ),
    )


def _cross_tool_overlay(
    selection: dict[str, Any],
    frames_by_tool_x: dict[tuple[str, float], dict[str, Any]],
    path: Path,
) -> None:
    x_mm = selection["common_x_mm"]
    images = []
    centers = [
        np.asarray(selection["t0_center_px"], dtype=float),
        np.asarray(selection["t0_center_px"], dtype=float)
        + np.asarray(selection["cross_registration"]["shift_px"], dtype=float),
    ]
    for tool, center in zip(("T0", "T1"), centers):
        image = frames_by_tool_x[(tool, x_mm)]["image"].copy()
        cv2.rectangle(
            image,
            (round(center[0] - 35), round(center[1] - 50)),
            (round(center[0] + 35), round(center[1] + 50)),
            (0, 255, 255),
            3,
        )
        cv2.drawMarker(
            image,
            (round(center[0]), round(center[1])),
            (0, 255, 0),
            cv2.MARKER_CROSS,
            36,
            3,
        )
        cv2.putText(
            image,
            f"{tool} common X={x_mm:.0f}",
            (30, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 255, 255),
            3,
            cv2.LINE_AA,
        )
        images.append(cv2.resize(image, (720, 405)))
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.hstack(images))


def _trajectory_plot(selection: dict[str, Any], path: Path) -> None:
    canvas = np.full((650, 1100, 3), 245, dtype=np.uint8)
    colors = {"t0": (180, 80, 20), "t1": (30, 130, 220)}
    all_positions = []
    for key in ("t0", "t1"):
        all_positions.extend(selection[key]["registered_positions_px"])
    px_values = [position[0] for position in all_positions]
    py_values = [position[1] for position in all_positions]
    x_min, x_max = min(px_values) - 30, max(px_values) + 30
    y_min, y_max = min(py_values) - 30, max(py_values) + 30

    def map_point(position: list[float]) -> tuple[int, int]:
        px = 80 + 940 * (position[0] - x_min) / max(1.0, x_max - x_min)
        py = 570 - 480 * (position[1] - y_min) / max(1.0, y_max - y_min)
        return round(px), round(py)

    for key in ("t0", "t1"):
        track = selection[key]
        points = [map_point(position) for position in track["registered_positions_px"]]
        cv2.polylines(canvas, [np.asarray(points)], False, colors[key], 3)
        for point, x_mm in zip(points, track["x_values_mm"]):
            cv2.circle(canvas, point, 7, colors[key], -1)
            cv2.putText(
                canvas,
                f"{key.upper()} {x_mm:.0f}",
                (point[0] + 8, point[1] - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                colors[key],
                2,
                cv2.LINE_AA,
            )
    cv2.putText(
        canvas,
        "Registered red-marker trajectories in image space",
        (55, 45),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (30, 30, 30),
        2,
        cv2.LINE_AA,
    )
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
        raise ValueError(f"unsupported red-marker localizer {localizer!r}")
    if len(frame_paths) != 12 or len(frames) != 12:
        raise ValueError("red-marker sweep requires twelve images")
    images = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in frame_paths]
    if any(image is None for image in images):
        raise ValueError("one or more red-marker images cannot be decoded")
    dimensions = {image.shape[:2] for image in images}
    if len(dimensions) != 1:
        raise ValueError("red-marker image dimensions changed")

    records = []
    for index, (image, frame) in enumerate(zip(images, frames)):
        records.append(
            {
                "index": index,
                "tool": frame["tool"],
                "x_mm": float(frame["x_mm"]),
                "image": image,
                "representations": _representations(image),
                "candidates": _red_candidates(image, index),
            }
        )
    frames_by_tool_x = {(record["tool"], record["x_mm"]): record for record in records}
    y_axis_vector = np.asarray(reference["image_y_axis_vector_px_per_mm"], dtype=float)
    hypotheses = {
        tool: _trajectory_hypotheses(
            [record for record in records if record["tool"] == tool],
            y_axis_vector,
        )
        for tool in ("T0", "T1")
    }
    selection = _select_cross_tool_pair(
        hypotheses["T0"], hypotheses["T1"], frames_by_tool_x
    )
    reasons = []
    warnings = []
    if not hypotheses["T0"]:
        reasons.append("T0 has no valid three-frame marker trajectory")
    if not hypotheses["T1"]:
        reasons.append("T1 has no valid three-frame marker trajectory")
    if selection is None and not reasons:
        reasons.append("no compatible cross-tool red-marker registration was found")

    selected_ids: set[str] = set()
    if selection is not None:
        selected_ids.update(selection["t0"]["candidate_ids"])
        selected_ids.update(selection["t1"]["candidate_ids"])
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths = {
        "contact_sheet": output_dir / "contact_sheet.jpg",
        "marker_selection": output_dir / "marker_selection.jpg",
    }
    _contact_sheet(records, selected_ids, artifact_paths["contact_sheet"])
    _marker_selection_overlay(records, selected_ids, artifact_paths["marker_selection"])

    result: dict[str, Any] = {
        "accepted": False,
        "reasons": reasons,
        "warnings": warnings,
        "localizer": LOCALIZER,
        "candidate_counts": {
            f"{record['tool']}_x{record['x_mm']:.0f}": len(record["candidates"])
            for record in records
        },
        "selected_candidate_ids": sorted(selected_ids),
        "tool_hypothesis_counts": {
            tool: len(tool_hypotheses) for tool, tool_hypotheses in hypotheses.items()
        },
    }
    if selection is not None:
        vector0 = np.asarray(selection["t0"]["axis_vector_px_per_mm"], dtype=float)
        vector1 = np.asarray(selection["t1"]["axis_vector_px_per_mm"], dtype=float)
        common_vector = (vector0 + vector1) / 2.0
        scale = float(np.linalg.norm(common_vector))
        unit_x = common_vector / scale
        cross_shift = np.asarray(
            selection["cross_registration"]["shift_px"], dtype=float
        )
        corner_pixel = np.asarray(reference["corner_pixel_xy_px"], dtype=float)
        capture_y = float(reference["capture_y_mm"])
        corner_at_capture = corner_pixel + y_axis_vector * (
            capture_y - float(reference["corner_pixel_capture_y_mm"])
        )
        marker0 = np.asarray(selection["t0_center_px"], dtype=float)
        marker1 = marker0 + cross_shift
        t0_offset = float(np.dot(marker0 - corner_at_capture, unit_x) / scale)
        t1_offset = float(np.dot(marker1 - corner_at_capture, unit_x) / scale)
        result.update(
            {
                "accepted": not reasons,
                "reasons": sorted(set(reasons)),
                "common_axis_vector_px_per_mm": common_vector.tolist(),
                "common_scale_px_per_mm": scale,
                "tool_axis_vectors_px_per_mm": {
                    "T0": vector0.tolist(),
                    "T1": vector1.tolist(),
                },
                "tool_scale_delta_fraction": selection["tool_scale_delta_fraction"],
                "tool_angle_delta_deg": selection["tool_angle_delta_deg"],
                "tool_fit_rms_px": {
                    "T0": selection["t0"]["fit_rms_px"],
                    "T1": selection["t1"]["fit_rms_px"],
                },
                "tool_minimum_correlation": {
                    "T0": selection["t0"]["minimum_correlation"],
                    "T1": selection["t1"]["minimum_correlation"],
                },
                "accepted_x_mm": {
                    "T0": selection["t0"]["x_values_mm"],
                    "T1": selection["t1"]["x_values_mm"],
                },
                "common_commanded_x_mm": selection["common_x_mm"],
                "cross_tool_shift_px": cross_shift.tolist(),
                "cross_tool_minimum_correlation": selection["cross_registration"][
                    "minimum_correlation"
                ],
                "corner_pixel_at_capture_y_px": corner_at_capture.tolist(),
                "t0_marker_pixel_px": marker0.tolist(),
                "t1_marker_pixel_px": marker1.tolist(),
                "t0_red_marker_to_bed_tab_x_mm": t0_offset,
                "t1_red_marker_to_bed_tab_x_mm": t1_offset,
                "selected_tracks": {
                    "T0": selection["t0"],
                    "T1": selection["t1"],
                },
                "cross_registration": selection["cross_registration"],
            }
        )
        artifact_paths.update(
            {
                "core_registration": output_dir / "core_registration.jpg",
                "cross_tool_registration": output_dir / "cross_tool_registration.jpg",
                "trajectory": output_dir / "trajectory.jpg",
            }
        )
        _core_registration_overlay(
            selection, frames_by_tool_x, artifact_paths["core_registration"]
        )
        _cross_tool_overlay(
            selection, frames_by_tool_x, artifact_paths["cross_tool_registration"]
        )
        _trajectory_plot(selection, artifact_paths["trajectory"])
    result["artifacts"] = {
        name: {"path": str(path), "sha256": sha256_file(path)}
        for name, path in artifact_paths.items()
        if path.exists()
    }
    return _finite_json(result)
