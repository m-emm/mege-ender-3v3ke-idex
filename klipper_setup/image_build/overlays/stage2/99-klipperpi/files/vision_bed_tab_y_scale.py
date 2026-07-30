#!/usr/bin/env python3
"""Discover and track the moving bed-tab top edge."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from vision_calibration_graph import sha256_file


Y_OFFSETS_MM = [0.0, 10.0, 20.0, 20.0, 10.0, 0.0]
LOCALIZER_KIND = "bed_tab_top_edge"
LOCALIZER_VERSION = 1

MAX_LINE_ANGLE_DEG = 3.0
MIN_SEGMENT_WIDTH_FRACTION = 0.03
LSD_DENSITY_THRESHOLD = 0.50
MAX_CLUSTER_Y_PX_1080 = 12.0
MAX_CLUSTER_GAP_FRACTION = 0.03
MIN_CLUSTER_SPAN_FRACTION = 0.03
MAX_DUPLICATE_LINE_Y_PX_1080 = 3.0
MIN_DUPLICATE_OVERLAP = 0.60
MIN_TAB_SIDE_ANGLE_DEG = 30.0
MAX_TAB_SIDE_ANGLE_DEG = 80.0
MIN_TAB_SIDE_DROP_HEIGHT_FRACTION = 0.03
TAB_SIDE_START_BEHIND_WIDTH_FRACTION = 0.01
TAB_SIDE_START_AHEAD_WIDTH_FRACTION = 0.08
TAB_SIDE_START_Y_HEIGHT_FRACTION = 0.0325
STRIP_X_PADDING_FRACTION = 0.02
STRIP_Y_PADDING_FRACTION = 0.0325

SEARCH_X_PX_1920 = 80.0
SEARCH_Y_PX_1080 = 180.0
MAX_REPRESENTATION_SPREAD_PX = 1.5
MAX_EDGE_Y_ERROR_PX = 2.0
MIN_MATCH_CORRELATION = 0.60
MIN_ACCEPTED_CORRELATION = 0.65
MIN_MEDIAN_CORRELATION = 0.80
MIN_USABLE_FRAMES = 5
MIN_SPAN_MM = 20.0
MIN_SCALE_PX_PER_MM = 2.0
MAX_SCALE_PX_PER_MM = 30.0

WARN_RMS_PX = 0.75
WARN_DUPLICATE_DISAGREEMENT_PX = 1.0
WARN_DIRECTION_MAGNITUDE_DELTA = 0.03
WARN_DIRECTION_ANGLE_DEG = 1.0
MAX_DISCREPANCY_MM = 1.5
AMBIGUOUS_RMS_MM = 0.05
AMBIGUOUS_SPAN_FRACTION = 0.10


@dataclass
class EdgeCandidate:
    candidate_id: str
    reference_line: tuple[float, float, float]
    duplicate_line: tuple[float, float, float]
    strip_rect: tuple[int, int, int, int]
    span_fraction: float
    duplicate_y_delta_px: float
    duplicate_overlap_fraction: float
    reference_tab_side: dict[str, float] | None = None
    duplicate_tab_side: dict[str, float] | None = None
    edge_pair_score: float | None = None
    edge_pair_ratio: float | None = None
    reference_seam_y_px: float | None = None
    positions: list[tuple[float, float] | None] = field(
        default_factory=lambda: [None] * 6
    )
    seam_y_px: list[float | None] = field(default_factory=lambda: [None] * 6)
    correlations: list[float | None] = field(default_factory=lambda: [None] * 6)
    representation_spread_px: list[float | None] = field(
        default_factory=lambda: [None] * 6
    )
    edge_y_error_px: list[float | None] = field(default_factory=lambda: [None] * 6)
    match_errors: list[str] = field(default_factory=list)
    vector_px_per_mm: tuple[float, float] | None = None
    residual_rms_px: float | None = None
    residual_rms_mm: float | None = None
    minimum_correlation: float | None = None
    median_correlation: float | None = None
    rejection_reason: str | None = None
    selected: bool = False


def _gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image.astype(np.uint8)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _representations(gray: np.ndarray) -> dict[str, np.ndarray]:
    return {
        "gray": gray,
        "clahe": cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8),
        ).apply(gray),
    }


def _subpixel_peak(response: np.ndarray, x: int, y: int) -> tuple[float, float]:
    def offset(a: float, b: float, c: float) -> float:
        denominator = a - 2.0 * b + c
        if abs(denominator) < 1.0e-9:
            return 0.0
        return float(np.clip(0.5 * (a - c) / denominator, -0.5, 0.5))

    dx = 0.0
    dy = 0.0
    if 0 < x < response.shape[1] - 1:
        dx = offset(response[y, x - 1], response[y, x], response[y, x + 1])
    if 0 < y < response.shape[0] - 1:
        dy = offset(response[y - 1, x], response[y, x], response[y + 1, x])
    return x + dx, y + dy


def _interval_gap(left: tuple[float, float], right: tuple[float, float]) -> float:
    if left[1] < right[0]:
        return right[0] - left[1]
    if right[1] < left[0]:
        return left[0] - right[1]
    return 0.0


def _horizontal_overlap(left: tuple[float, float], right: tuple[float, float]) -> float:
    intersection = max(0.0, min(left[1], right[1]) - max(left[0], right[0]))
    denominator = max(1.0e-12, min(left[1] - left[0], right[1] - right[0]))
    return intersection / denominator


def _detect_line_segments(gray: np.ndarray) -> list[dict[str, float]]:
    clahe = _representations(gray)["clahe"]
    detector = cv2.createLineSegmentDetector(
        cv2.LSD_REFINE_STD,
        0.8,
        0.6,
        2.0,
        22.5,
        0.0,
        LSD_DENSITY_THRESHOLD,
        1024,
    )
    detected = detector.detect(clahe)[0]
    segments: list[dict[str, float]] = []
    if detected is None:
        return segments
    for values in detected[:, 0, :]:
        x0, y0, x1, y1 = (float(item) for item in values)
        if x1 < x0:
            x0, x1 = x1, x0
            y0, y1 = y1, y0
        length = math.hypot(x1 - x0, y1 - y0)
        signed_angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
        angle = abs(signed_angle)
        segments.append(
            {
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "y": (y0 + y1) / 2.0,
                "length": length,
                "angle_deg": angle,
                "signed_angle_deg": signed_angle,
            }
        )
    return segments


def _detect_horizontal_segments(
    gray: np.ndarray,
    segments: list[dict[str, float]] | None = None,
) -> list[dict[str, float]]:
    _height, width = gray.shape
    minimum_length = width * MIN_SEGMENT_WIDTH_FRACTION
    return [
        segment
        for segment in (
            segments if segments is not None else _detect_line_segments(gray)
        )
        if segment["length"] >= minimum_length
        and segment["angle_deg"] <= MAX_LINE_ANGLE_DEG
    ]


def _tab_side_support(
    candidate: dict[str, Any],
    segments: list[dict[str, float]],
    image_shape: tuple[int, int],
) -> dict[str, float] | None:
    height, width = image_shape
    minimum_drop = MIN_TAB_SIDE_DROP_HEIGHT_FRACTION * height
    start_x_min = candidate["x1"] - TAB_SIDE_START_BEHIND_WIDTH_FRACTION * width
    start_x_max = candidate["x1"] + TAB_SIDE_START_AHEAD_WIDTH_FRACTION * width
    start_y_tolerance = TAB_SIDE_START_Y_HEIGHT_FRACTION * height
    matches = []
    for segment in segments:
        drop = segment["y1"] - segment["y0"]
        if not MIN_TAB_SIDE_ANGLE_DEG <= segment["angle_deg"] <= MAX_TAB_SIDE_ANGLE_DEG:
            continue
        if drop < minimum_drop:
            continue
        if not start_x_min <= segment["x0"] <= start_x_max:
            continue
        if abs(segment["y0"] - candidate["y"]) > start_y_tolerance:
            continue
        horizontal_gap = max(0.0, segment["x0"] - candidate["x1"])
        endpoint_distance = math.hypot(
            horizontal_gap,
            segment["y0"] - candidate["y"],
        )
        score = drop * segment["length"] / max(1.0, endpoint_distance)
        matches.append((score, segment, drop, endpoint_distance))
    if not matches:
        return None
    score, segment, drop, endpoint_distance = max(matches, key=lambda item: item[0])
    return {
        "x0": float(segment["x0"]),
        "y0": float(segment["y0"]),
        "x1": float(segment["x1"]),
        "y1": float(segment["y1"]),
        "angle_deg": float(segment["angle_deg"]),
        "length_px": float(segment["length"]),
        "vertical_drop_px": float(drop),
        "endpoint_distance_px": float(endpoint_distance),
        "geometry_score": float(score),
    }


def _cluster_horizontal_segments(
    segments: list[dict[str, float]],
    image_shape: tuple[int, int],
) -> list[dict[str, Any]]:
    height, width = image_shape
    y_tolerance = MAX_CLUSTER_Y_PX_1080 * height / 1080.0
    gap_tolerance = MAX_CLUSTER_GAP_FRACTION * width
    parent = list(range(len(segments)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, right_index in combinations(range(len(segments)), 2):
        left = segments[left_index]
        right = segments[right_index]
        if abs(left["y"] - right["y"]) > y_tolerance:
            continue
        gap = _interval_gap(
            (left["x0"], left["x1"]),
            (right["x0"], right["x1"]),
        )
        if gap <= gap_tolerance:
            union(left_index, right_index)

    grouped: dict[int, list[dict[str, float]]] = {}
    for index, segment in enumerate(segments):
        grouped.setdefault(find(index), []).append(segment)
    clusters = list(grouped.values())

    records = []
    for cluster in clusters:
        x0 = min(item["x0"] for item in cluster)
        x1 = max(item["x1"] for item in cluster)
        span_fraction = (x1 - x0) / width
        if span_fraction < MIN_CLUSTER_SPAN_FRACTION:
            continue
        total_length = sum(item["length"] for item in cluster)
        y = sum(item["y"] * item["length"] for item in cluster) / total_length
        records.append(
            {
                "x0": x0,
                "x1": x1,
                "y": y,
                "span_fraction": span_fraction,
                "segment_count": len(cluster),
                "segments": cluster,
            }
        )
    return sorted(records, key=lambda item: (item["y"], item["x0"]))


def _discover_candidates(
    gray_reference: np.ndarray,
    gray_duplicate: np.ndarray,
) -> list[EdgeCandidate]:
    height, width = gray_reference.shape
    if gray_duplicate.shape != gray_reference.shape:
        raise ValueError("zero-offset images have inconsistent dimensions")
    reference_segments = _detect_line_segments(gray_reference)
    duplicate_segments = _detect_line_segments(gray_duplicate)
    reference = _cluster_horizontal_segments(
        _detect_horizontal_segments(gray_reference, reference_segments),
        gray_reference.shape,
    )
    duplicate = _cluster_horizontal_segments(
        _detect_horizontal_segments(gray_duplicate, duplicate_segments),
        gray_duplicate.shape,
    )
    y_tolerance = MAX_DUPLICATE_LINE_Y_PX_1080 * height / 1080.0
    x_padding = int(round(STRIP_X_PADDING_FRACTION * width))
    y_padding = int(round(STRIP_Y_PADDING_FRACTION * height))
    candidates: list[EdgeCandidate] = []
    used_duplicates: set[int] = set()
    for reference_item in reference:
        matches = []
        for duplicate_index, duplicate_item in enumerate(duplicate):
            if duplicate_index in used_duplicates:
                continue
            y_delta = abs(reference_item["y"] - duplicate_item["y"])
            overlap = _horizontal_overlap(
                (reference_item["x0"], reference_item["x1"]),
                (duplicate_item["x0"], duplicate_item["x1"]),
            )
            if y_delta <= y_tolerance and overlap >= MIN_DUPLICATE_OVERLAP:
                matches.append((-overlap, y_delta, duplicate_index, duplicate_item))
        if not matches:
            continue
        _negative_overlap, y_delta, duplicate_index, duplicate_item = min(matches)
        used_duplicates.add(duplicate_index)
        left = max(0, int(math.floor(reference_item["x0"])) - x_padding)
        right = min(width, int(math.ceil(reference_item["x1"])) + x_padding)
        top = max(0, int(round(reference_item["y"])) - y_padding)
        bottom = min(height, int(round(reference_item["y"])) + y_padding)
        if right - left < 8 or bottom - top < 8:
            continue
        reference_tab_side = _tab_side_support(
            reference_item,
            reference_segments,
            gray_reference.shape,
        )
        duplicate_tab_side = _tab_side_support(
            duplicate_item,
            duplicate_segments,
            gray_duplicate.shape,
        )
        candidate = EdgeCandidate(
            candidate_id=f"edge_{len(candidates):02d}",
            reference_line=(
                float(reference_item["x0"]),
                float(reference_item["y"]),
                float(reference_item["x1"]),
            ),
            duplicate_line=(
                float(duplicate_item["x0"]),
                float(duplicate_item["y"]),
                float(duplicate_item["x1"]),
            ),
            strip_rect=(left, top, right, bottom),
            span_fraction=float(reference_item["span_fraction"]),
            duplicate_y_delta_px=float(y_delta),
            duplicate_overlap_fraction=float(-_negative_overlap),
            reference_tab_side=reference_tab_side,
            duplicate_tab_side=duplicate_tab_side,
        )
        if reference_tab_side is None or duplicate_tab_side is None:
            candidate.rejection_reason = (
                "missing descending bed-tab side geometry in a zero-offset frame"
            )
        candidates.append(candidate)
    return candidates


def _edge_pair_in_plane(
    plane: np.ndarray,
    rect: tuple[int, int, int, int],
    *,
    expected_y: float | None,
    expected_radius_px: int,
) -> tuple[float | None, float, float]:
    left, top, right, bottom = rect
    strip = plane[top:bottom, left:right]
    if strip.shape[0] < 12 or strip.shape[1] < 16:
        return None, 0.0, 0.0
    signed = cv2.Sobel(strip, cv2.CV_32F, 0, 1, ksize=3).mean(axis=1)
    separation_min = max(2, int(round(3 * plane.shape[0] / 1080.0)))
    separation_max = max(
        separation_min + 2,
        int(round(9 * plane.shape[0] / 1080.0)),
    )
    choices = []
    for positive_index in range(1, len(signed) - separation_max - 1):
        absolute_y = top + positive_index
        if expected_y is not None and abs(absolute_y - expected_y) > expected_radius_px:
            continue
        window = signed[
            positive_index + separation_min : positive_index + separation_max + 1
        ]
        negative_offset = int(np.argmin(window))
        negative_index = positive_index + separation_min + negative_offset
        score = max(float(signed[positive_index]), 0.0) + max(
            -float(signed[negative_index]),
            0.0,
        )
        choices.append((score, positive_index, negative_index))
    if not choices:
        return None, 0.0, 0.0
    choices.sort(reverse=True)
    best_score, positive_index, _negative_index = choices[0]
    independent = [
        item
        for item in choices[1:]
        if abs(item[1] - positive_index)
        > max(5, int(round(10 * plane.shape[0] / 1080.0)))
    ]
    second_score = independent[0][0] if independent else 0.0
    ratio = best_score / max(second_score, 1.0e-12)
    return float(top + positive_index), float(best_score), float(ratio)


def _edge_pair(
    gray: np.ndarray,
    rect: tuple[int, int, int, int],
    *,
    expected_y: float | None = None,
    expected_radius_px: int = 10,
) -> tuple[float | None, float, float, float | None]:
    representations = _representations(gray)
    measurements = [
        _edge_pair_in_plane(
            representations[name],
            rect,
            expected_y=expected_y,
            expected_radius_px=expected_radius_px,
        )
        for name in ("gray", "clahe")
    ]
    if any(measurement[0] is None for measurement in measurements):
        return None, 0.0, 0.0, None
    y_values = np.asarray([measurement[0] for measurement in measurements], dtype=float)
    spread = float(np.ptp(y_values))
    return (
        float(np.median(y_values)),
        float(min(measurement[1] for measurement in measurements)),
        float(min(measurement[2] for measurement in measurements)),
        spread,
    )


def _rect_at_position(
    base_rect: tuple[int, int, int, int],
    position: tuple[float, float],
    image_shape: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    width = base_rect[2] - base_rect[0]
    height = base_rect[3] - base_rect[1]
    left = int(round(position[0] - width / 2.0))
    top = int(round(position[1] - height / 2.0))
    right = left + width
    bottom = top + height
    image_height, image_width = image_shape
    if left < 0 or top < 0 or right > image_width or bottom > image_height:
        return None
    return left, top, right, bottom


def _match_strip(
    source_reps: dict[str, np.ndarray],
    target_reps: dict[str, np.ndarray],
    target_gray: np.ndarray,
    source_rect: tuple[int, int, int, int],
    base_rect: tuple[int, int, int, int],
    reference_edge_offset_y: float,
    reference_edge_score: float,
) -> tuple[
    tuple[float, float] | None,
    float | None,
    float | None,
    float | None,
    float | None,
    str | None,
]:
    left, top, right, bottom = source_rect
    patch_width = right - left
    patch_height = bottom - top
    image_height, image_width = target_gray.shape
    x_radius = max(8, int(round(SEARCH_X_PX_1920 * image_width / 1920.0)))
    y_radius = max(18, int(round(SEARCH_Y_PX_1080 * image_height / 1080.0)))
    search_left = max(0, left - x_radius)
    search_top = max(0, top - y_radius)
    search_right = min(image_width, right + x_radius)
    search_bottom = min(image_height, bottom + y_radius)
    matches = []
    for name in ("gray", "clahe"):
        template = source_reps[name][top:bottom, left:right]
        search = target_reps[name][
            search_top:search_bottom,
            search_left:search_right,
        ]
        if search.shape[0] < patch_height or search.shape[1] < patch_width:
            return None, None, None, None, None, "search area is smaller than strip"
        response = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _minimum, maximum, _minimum_location, maximum_location = cv2.minMaxLoc(response)
        peak_x, peak_y = maximum_location
        if (
            peak_x <= 0
            or peak_y <= 0
            or peak_x >= response.shape[1] - 1
            or peak_y >= response.shape[0] - 1
        ):
            return None, float(maximum), None, None, None, "registration hit boundary"
        sub_x, sub_y = _subpixel_peak(response, peak_x, peak_y)
        matches.append(
            {
                "position": (
                    search_left + sub_x + patch_width / 2.0,
                    search_top + sub_y + patch_height / 2.0,
                ),
                "correlation": float(maximum),
            }
        )
    if min(item["correlation"] for item in matches) < MIN_MATCH_CORRELATION:
        return (
            None,
            float(np.median([item["correlation"] for item in matches])),
            None,
            None,
            None,
            "weak strip correlation",
        )
    position_array = np.asarray([item["position"] for item in matches], dtype=float)
    center = np.median(position_array, axis=0)
    spread = float(np.max(np.linalg.norm(position_array - center, axis=1)))
    correlation = float(np.median([item["correlation"] for item in matches]))
    if spread > MAX_REPRESENTATION_SPREAD_PX:
        return (
            None,
            correlation,
            spread,
            None,
            None,
            "grayscale and CLAHE positions disagree",
        )
    position = (float(center[0]), float(center[1]))
    target_rect = _rect_at_position(base_rect, position, target_gray.shape)
    if target_rect is None:
        return None, correlation, spread, None, None, "tracked strip left image"
    expected_edge_y = target_rect[1] + reference_edge_offset_y
    seam_y, edge_score, _edge_ratio, edge_spread = _edge_pair(
        target_gray,
        target_rect,
        expected_y=expected_edge_y,
    )
    if seam_y is None or edge_score < 0.25 * reference_edge_score:
        return (
            None,
            correlation,
            spread,
            seam_y,
            None,
            "horizontal edge confirmation failed",
        )
    if edge_spread is None or edge_spread > MAX_EDGE_Y_ERROR_PX:
        return (
            None,
            correlation,
            spread,
            seam_y,
            edge_spread,
            "grayscale and CLAHE edge positions disagree",
        )
    edge_position = (position[0], seam_y)
    return edge_position, correlation, spread, seam_y, edge_spread, None


def _fit_vector(
    offsets: list[float],
    positions: list[tuple[float, float] | None],
    indices: list[int] | None = None,
) -> (
    tuple[
        tuple[float, float],
        tuple[float, float],
        float,
        list[int],
        list[list[float]],
    ]
    | None
):
    valid_indices = [
        index
        for index, position in enumerate(positions)
        if position is not None and (indices is None or index in indices)
    ]
    if len(valid_indices) < 3:
        return None
    x = np.asarray([offsets[index] for index in valid_indices], dtype=float)
    if float(np.ptp(x)) < MIN_SPAN_MM:
        return None
    design = np.column_stack([np.ones_like(x), x])
    values = np.asarray([positions[index] for index in valid_indices], dtype=float)
    coefficients, _residuals, _rank, _singular = np.linalg.lstsq(
        design,
        values,
        rcond=None,
    )
    predicted = design @ coefficients
    residual = values - predicted
    rms = float(np.sqrt(np.mean(np.sum(residual**2, axis=1))))
    return (
        (float(coefficients[1, 0]), float(coefficients[1, 1])),
        (float(coefficients[0, 0]), float(coefficients[0, 1])),
        rms,
        valid_indices,
        residual.tolist(),
    )


def _track_candidate(
    candidate: EdgeCandidate,
    gray_images: list[np.ndarray | None],
    reps: list[dict[str, np.ndarray] | None],
    missing_frames: set[int],
    offsets: list[float],
) -> None:
    if candidate.rejection_reason is not None:
        return
    if 0 in missing_frames or 5 in missing_frames:
        candidate.rejection_reason = "both zero-offset frames are required"
        return
    reference_gray = gray_images[0]
    if reference_gray is None:
        candidate.rejection_reason = "reference image is missing"
        return
    seam_y, edge_score, edge_ratio, edge_spread = _edge_pair(
        reference_gray,
        candidate.strip_rect,
    )
    candidate.reference_seam_y_px = seam_y
    candidate.edge_pair_score = edge_score
    candidate.edge_pair_ratio = edge_ratio
    if seam_y is None or edge_score <= 0.0 or edge_ratio < 1.25:
        candidate.rejection_reason = "reference horizontal seam is ambiguous"
        return
    reference_edge_offset = seam_y - candidate.strip_rect[1]
    center = (
        (candidate.strip_rect[0] + candidate.strip_rect[2]) / 2.0,
        (candidate.strip_rect[1] + candidate.strip_rect[3]) / 2.0,
    )
    candidate.positions[0] = center
    candidate.seam_y_px[0] = seam_y
    candidate.correlations[0] = 1.0
    candidate.representation_spread_px[0] = 0.0
    candidate.edge_y_error_px[0] = edge_spread

    def track_pair(
        source_index: int,
        target_index: int,
        source_rect: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int] | None:
        if (
            source_index in missing_frames
            or target_index in missing_frames
            or reps[source_index] is None
            or reps[target_index] is None
            or gray_images[target_index] is None
        ):
            candidate.match_errors.append(
                f"frame {target_index}: missing source or target"
            )
            return None
        position, correlation, spread, target_seam_y, edge_error, error = _match_strip(
            reps[source_index],
            reps[target_index],
            gray_images[target_index],
            source_rect,
            candidate.strip_rect,
            reference_edge_offset,
            edge_score,
        )
        candidate.correlations[target_index] = correlation
        candidate.representation_spread_px[target_index] = spread
        candidate.seam_y_px[target_index] = target_seam_y
        candidate.edge_y_error_px[target_index] = edge_error
        if error or position is None:
            candidate.match_errors.append(
                f"frame {target_index}: {error or 'registration failed'}"
            )
            return None
        candidate.positions[target_index] = position
        target_rect = _rect_at_position(
            candidate.strip_rect,
            position,
            gray_images[target_index].shape,
        )
        if target_rect is None:
            candidate.match_errors.append(
                f"frame {target_index}: tracked strip left image"
            )
        return target_rect

    current_rect = candidate.strip_rect
    for source_index, target_index in ((0, 1), (1, 2)):
        next_rect = track_pair(source_index, target_index, current_rect)
        if next_rect is None:
            break
        current_rect = next_rect

    duplicate_rect = track_pair(0, 5, candidate.strip_rect)
    if duplicate_rect is not None:
        current_rect = duplicate_rect
        for source_index, target_index in ((5, 4), (4, 3)):
            next_rect = track_pair(source_index, target_index, current_rect)
            if next_rect is None:
                break
            current_rect = next_rect

    fit = _fit_vector(offsets, candidate.positions)
    reasons = []
    usable = [
        index
        for index, position in enumerate(candidate.positions)
        if position is not None
    ]
    if len(usable) < MIN_USABLE_FRAMES:
        reasons.append("fewer than five usable frames")
    if usable:
        span = max(offsets[index] for index in usable) - min(
            offsets[index] for index in usable
        )
        if span < MIN_SPAN_MM:
            reasons.append("commanded span is below 20 mm")
    if fit is None:
        reasons.append("candidate motion fit is unavailable")
    else:
        vector, _intercept, rms, _indices, _residual = fit
        scale = float(np.linalg.norm(vector))
        candidate.vector_px_per_mm = vector
        candidate.residual_rms_px = rms
        candidate.residual_rms_mm = rms / scale if scale > 0.0 else float("inf")
        if not MIN_SCALE_PX_PER_MM <= scale <= MAX_SCALE_PX_PER_MM:
            reasons.append("candidate is stationary or outside scale range")
        if candidate.residual_rms_mm > MAX_DISCREPANCY_MM:
            reasons.append("candidate fit RMS is above 1.5 mm")
    correlations = [value for value in candidate.correlations if value is not None]
    if correlations:
        candidate.minimum_correlation = min(correlations)
        candidate.median_correlation = float(np.median(correlations))
    if not correlations or candidate.minimum_correlation < MIN_ACCEPTED_CORRELATION:
        reasons.append("candidate minimum correlation is below 0.65")
    if not correlations or candidate.median_correlation < MIN_MEDIAN_CORRELATION:
        reasons.append("candidate median correlation is below 0.80")
    if reasons:
        candidate.rejection_reason = "; ".join(sorted(set(reasons)))


def _select_candidate(
    candidates: list[EdgeCandidate],
) -> tuple[EdgeCandidate | None, str | None]:
    valid = [
        candidate
        for candidate in candidates
        if candidate.rejection_reason is None and candidate.residual_rms_mm is not None
    ]
    if not valid:
        return (
            None,
            "no discovered bed-tab top edge passed geometry and motion validation",
        )
    best_rms = min(candidate.residual_rms_mm for candidate in valid)
    tied = [
        candidate
        for candidate in valid
        if candidate.residual_rms_mm - best_rms <= AMBIGUOUS_RMS_MM
    ]
    tied.sort(key=lambda candidate: (-candidate.span_fraction, candidate.candidate_id))
    winner = tied[0]
    if len(tied) > 1:
        runner_up = tied[1]
        rms_close = (
            abs(winner.residual_rms_mm - runner_up.residual_rms_mm) <= AMBIGUOUS_RMS_MM
        )
        span_close = abs(
            winner.span_fraction - runner_up.span_fraction
        ) <= AMBIGUOUS_SPAN_FRACTION * max(
            winner.span_fraction, runner_up.span_fraction
        )
        distinct = (
            abs(winner.reference_line[1] - runner_up.reference_line[1])
            > MAX_CLUSTER_Y_PX_1080
        )
        if rms_close and span_close and distinct:
            return None, (
                "multiple distinct horizontal moving edges are equally supported"
            )
    winner.selected = True
    return winner, None


def _duplicate_disagreement(candidate: EdgeCandidate) -> float:
    values = []
    for left, right in ((0, 5), (1, 4), (2, 3)):
        if candidate.positions[left] is None or candidate.positions[right] is None:
            continue
        values.append(
            float(
                np.linalg.norm(
                    np.asarray(candidate.positions[left])
                    - np.asarray(candidate.positions[right])
                )
            )
        )
    return max(values) if values else float("inf")


def _vector_angle_degrees(
    left: tuple[float, float], right: tuple[float, float]
) -> float:
    left_array = np.asarray(left, dtype=float)
    right_array = np.asarray(right, dtype=float)
    denominator = float(np.linalg.norm(left_array) * np.linalg.norm(right_array))
    if denominator <= 1.0e-12:
        return float("inf")
    cosine = float(np.clip(np.dot(left_array, right_array) / denominator, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def _candidate_record(candidate: EdgeCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "reference_line_px": list(candidate.reference_line),
        "duplicate_line_px": list(candidate.duplicate_line),
        "tracking_strip_px": list(candidate.strip_rect),
        "span_fraction": candidate.span_fraction,
        "duplicate_y_delta_px": candidate.duplicate_y_delta_px,
        "duplicate_overlap_fraction": candidate.duplicate_overlap_fraction,
        "reference_tab_side": candidate.reference_tab_side,
        "duplicate_tab_side": candidate.duplicate_tab_side,
        "edge_pair_score": candidate.edge_pair_score,
        "edge_pair_ratio": candidate.edge_pair_ratio,
        "reference_seam_y_px": candidate.reference_seam_y_px,
        "positions_px": [
            list(position) if position is not None else None
            for position in candidate.positions
        ],
        "seam_y_px": candidate.seam_y_px,
        "correlations": candidate.correlations,
        "representation_spread_px": candidate.representation_spread_px,
        "edge_y_error_px": candidate.edge_y_error_px,
        "vector_px_per_mm": (
            list(candidate.vector_px_per_mm)
            if candidate.vector_px_per_mm is not None
            else None
        ),
        "residual_rms_px": candidate.residual_rms_px,
        "residual_rms_mm": candidate.residual_rms_mm,
        "minimum_correlation": candidate.minimum_correlation,
        "median_correlation": candidate.median_correlation,
        "match_errors": candidate.match_errors,
        "selected": candidate.selected,
        "rejection_reason": candidate.rejection_reason,
    }


def _resize_width(image: np.ndarray, width: int) -> np.ndarray:
    scale = width / image.shape[1]
    return cv2.resize(image, (width, int(round(image.shape[0] * scale))))


def _draw_localization_overlay(
    images: list[np.ndarray],
    candidates: list[EdgeCandidate],
    selected: EdgeCandidate | None,
    path: Path,
) -> None:
    panels = []
    for frame_index, line_attr in ((0, "reference_line"), (5, "duplicate_line")):
        canvas = images[frame_index].copy()
        for candidate in candidates:
            line = getattr(candidate, line_attr)
            color = (
                (40, 220, 40)
                if selected is candidate
                else (40, 40, 220) if candidate.rejection_reason else (40, 180, 240)
            )
            cv2.line(
                canvas,
                (int(round(line[0])), int(round(line[1]))),
                (int(round(line[2])), int(round(line[1]))),
                color,
                4,
                cv2.LINE_AA,
            )
            tab_side = (
                candidate.reference_tab_side
                if frame_index == 0
                else candidate.duplicate_tab_side
            )
            if tab_side is not None:
                cv2.line(
                    canvas,
                    (
                        int(round(tab_side["x0"])),
                        int(round(tab_side["y0"])),
                    ),
                    (
                        int(round(tab_side["x1"])),
                        int(round(tab_side["y1"])),
                    ),
                    color,
                    4,
                    cv2.LINE_AA,
                )
            left, top, right, bottom = candidate.strip_rect
            cv2.rectangle(canvas, (left, top), (right, bottom), color, 2)
            status = (
                "selected"
                if selected is candidate
                else candidate.rejection_reason or "valid"
            )
            label = f"{candidate.candidate_id}: {status}"
            cv2.putText(
                canvas,
                label[:72],
                (left, max(25, top - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )
        cv2.putText(
            canvas,
            f"zero-offset frame {frame_index}",
            (24, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (40, 240, 240),
            2,
            cv2.LINE_AA,
        )
        panels.append(_resize_width(canvas, 960))
    cv2.imwrite(str(path), np.hstack(panels))


def _draw_tracking_overlay(
    images: list[np.ndarray],
    candidate: EdgeCandidate,
    offsets: list[float],
    fit: tuple[
        tuple[float, float],
        tuple[float, float],
        float,
        list[int],
        list[list[float]],
    ],
    path: Path,
) -> None:
    vector, intercept, _rms, valid_indices, residuals = fit
    residual_by_index = {
        index: residual for index, residual in zip(valid_indices, residuals)
    }
    base_center = np.asarray(
        [
            (candidate.strip_rect[0] + candidate.strip_rect[2]) / 2.0,
            (candidate.strip_rect[1] + candidate.strip_rect[3]) / 2.0,
        ]
    )
    line = candidate.reference_line
    edge_offset = (candidate.reference_seam_y_px or line[1]) - base_center[1]
    panels = []
    half = len(images) // 2
    for index, image in enumerate(images):
        canvas = image.copy()
        pass_color = (40, 220, 40) if index < half else (210, 70, 220)
        measured = candidate.positions[index]
        predicted = np.asarray(intercept) + np.asarray(vector) * offsets[index]
        predicted_rect = _rect_at_position(
            candidate.strip_rect,
            (float(predicted[0]), float(predicted[1])),
            _gray(image).shape,
        )
        if predicted_rect is not None:
            cv2.rectangle(
                canvas,
                (predicted_rect[0], predicted_rect[1]),
                (predicted_rect[2], predicted_rect[3]),
                (255, 220, 30),
                3,
            )
            predicted_y = int(round(predicted[1] + edge_offset))
            predicted_dx = predicted[0] - base_center[0]
            cv2.line(
                canvas,
                (int(round(line[0] + predicted_dx)), predicted_y),
                (int(round(line[2] + predicted_dx)), predicted_y),
                (255, 220, 30),
                4,
                cv2.LINE_AA,
            )
        if measured is not None:
            measured_rect = _rect_at_position(
                candidate.strip_rect,
                measured,
                _gray(image).shape,
            )
            if measured_rect is not None:
                cv2.rectangle(
                    canvas,
                    (measured_rect[0], measured_rect[1]),
                    (measured_rect[2], measured_rect[3]),
                    (40, 210, 240),
                    3,
                )
            measured_dx = measured[0] - base_center[0]
            measured_y = int(
                round(
                    candidate.seam_y_px[index]
                    if candidate.seam_y_px[index] is not None
                    else measured[1] + edge_offset
                )
            )
            cv2.line(
                canvas,
                (int(round(line[0] + measured_dx)), measured_y),
                (int(round(line[2] + measured_dx)), measured_y),
                (40, 210, 240),
                4,
                cv2.LINE_AA,
            )
        residual = residual_by_index.get(index)
        residual_text = (
            f"residual [{residual[0]:.2f}, {residual[1]:.2f}] px"
            if residual is not None
            else "unusable frame"
        )
        correlation = candidate.correlations[index]
        cv2.putText(
            canvas,
            (
                f"seq={index} {'forward' if index < half else 'reverse'} "
                f"Y={offsets[index]:g} mm"
            ),
            (24, 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68,
            pass_color,
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            (
                f"corr={correlation:.3f} {residual_text}"
                if correlation is not None
                else residual_text
            ),
            (24, 72),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (40, 240, 240),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "yellow=measured  cyan=fitted",
            (24, canvas.shape[0] - 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (240, 240, 240),
            2,
            cv2.LINE_AA,
        )
        panels.append(_resize_width(canvas, 640))
    rows = [np.hstack(panels[:3]), np.hstack(panels[3:6])]
    cv2.imwrite(str(path), np.vstack(rows))


def _contact_sheet(images: list[np.ndarray], offsets: list[float], path: Path) -> None:
    panels = []
    half = len(images) // 2
    for index, image in enumerate(images):
        panel = _resize_width(image, 480)
        cv2.putText(
            panel,
            (
                f"seq={index} {'forward' if index < half else 'reverse'} "
                f"Y={offsets[index]:g} mm"
            ),
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (40, 240, 240),
            2,
            cv2.LINE_AA,
        )
        panels.append(panel)
    cv2.imwrite(
        str(path),
        np.vstack([np.hstack(panels[:3]), np.hstack(panels[3:6])]),
    )


def _plot_displacement(
    candidate: EdgeCandidate,
    offsets: list[float],
    fit: tuple[
        tuple[float, float],
        tuple[float, float],
        float,
        list[int],
        list[list[float]],
    ],
    path: Path,
) -> None:
    vector, intercept, _rms, valid_indices, _residual = fit
    width, height = 1200, 820
    canvas = np.full((height, width, 3), 248, dtype=np.uint8)
    margin_left, margin_right = 100, 50
    panel_width = width - margin_left - margin_right
    for component, top, title in ((0, 70, "image X"), (1, 430, "image Y")):
        bottom = top + 280
        cv2.rectangle(
            canvas,
            (margin_left, top),
            (width - margin_right, bottom),
            (170, 170, 170),
            1,
        )
        values = [
            candidate.positions[index][component]
            for index in valid_indices
            if candidate.positions[index] is not None
        ]
        predicted = [
            intercept[component] + vector[component] * offsets[index]
            for index in valid_indices
        ]
        all_values = values + predicted
        low, high = min(all_values), max(all_values)
        padding = max(1.0, 0.08 * (high - low or 1.0))
        low -= padding
        high += padding

        def point(offset: float, value: float) -> tuple[int, int]:
            x = margin_left + int(round(offset / 20.0 * panel_width))
            y = bottom - int(round((value - low) / (high - low) * (bottom - top)))
            return x, y

        for start_offset, end_offset in ((0.0, 20.0),):
            cv2.line(
                canvas,
                point(
                    start_offset,
                    intercept[component] + vector[component] * start_offset,
                ),
                point(
                    end_offset,
                    intercept[component] + vector[component] * end_offset,
                ),
                (40, 150, 220),
                3,
                cv2.LINE_AA,
            )
        for index in valid_indices:
            value = candidate.positions[index][component]
            color = (40, 170, 40) if index < 3 else (190, 60, 190)
            cv2.circle(canvas, point(offsets[index], value), 7, color, -1)
        cv2.putText(
            canvas,
            f"{title} displacement; slope {vector[component]:.5f} px/mm",
            (margin_left, top - 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (30, 30, 30),
            2,
            cv2.LINE_AA,
        )
    cv2.putText(
        canvas,
        "commanded Y offset (0 to 20 mm)",
        (420, height - 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (30, 30, 30),
        2,
        cv2.LINE_AA,
    )
    cv2.imwrite(str(path), canvas)


def _plot_direction(
    forward: tuple[float, float],
    reverse: tuple[float, float],
    path: Path,
) -> None:
    size = 700
    center = (size // 2, size // 2)
    canvas = np.full((size, size, 3), 250, dtype=np.uint8)
    cv2.line(canvas, (center[0], 40), (center[0], size - 40), (180, 180, 180), 1)
    cv2.line(canvas, (40, center[1]), (size - 40, center[1]), (180, 180, 180), 1)
    for vector, color, label in (
        (forward, (30, 170, 30), "forward"),
        (reverse, (210, 80, 40), "reverse"),
    ):
        endpoint = (
            int(round(center[0] + vector[0] * 18.0)),
            int(round(center[1] + vector[1] * 18.0)),
        )
        cv2.arrowedLine(canvas, center, endpoint, color, 4, tipLength=0.12)
        cv2.putText(
            canvas,
            f"{label}: [{vector[0]:.4f}, {vector[1]:.4f}] px/mm",
            (45, 55 if label == "forward" else 88),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            color,
            2,
            cv2.LINE_AA,
        )
    cv2.imwrite(str(path), canvas)


def analyze(
    frame_paths: list[Path],
    output_dir: Path,
    *,
    offsets_mm: list[float] | None = None,
    localizer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    offsets = [float(item) for item in (offsets_mm or Y_OFFSETS_MM)]
    if len(frame_paths) != len(offsets):
        raise ValueError("frame path count must match commanded offsets")
    if offsets != Y_OFFSETS_MM:
        raise ValueError(
            "bed-tab sweep must be 0,10,20 mm forward and 20,10,0 mm reverse"
        )
    localizer = localizer or {
        "kind": LOCALIZER_KIND,
        "version": LOCALIZER_VERSION,
    }
    if localizer != {"kind": LOCALIZER_KIND, "version": LOCALIZER_VERSION}:
        raise ValueError("unsupported bed-tab edge localizer")
    output_dir.mkdir(parents=True, exist_ok=False)

    images: list[np.ndarray] = []
    missing_frames: list[int] = []
    for index, path in enumerate(frame_paths):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            missing_frames.append(index)
            images.append(np.zeros((1, 1, 3), dtype=np.uint8))
        else:
            images.append(image)
    valid_images = [image for image in images if image.shape[:2] != (1, 1)]
    if not valid_images:
        return _json_finite(
            {
                "accepted": False,
                "reasons": ["no decodable frames"],
                "warnings": [],
                "missing_frames": missing_frames,
                "candidates": [],
                "artifacts": {},
            }
        )
    expected_shape = valid_images[0].shape
    if any(
        image.shape != expected_shape
        for index, image in enumerate(images)
        if index not in missing_frames
    ):
        return _json_finite(
            {
                "accepted": False,
                "reasons": ["inconsistent image dimensions"],
                "warnings": [],
                "missing_frames": missing_frames,
                "candidates": [],
                "artifacts": {},
            }
        )

    gray_images: list[np.ndarray | None] = [
        _gray(image) if index not in missing_frames else None
        for index, image in enumerate(images)
    ]
    reps = [
        _representations(gray) if gray is not None else None for gray in gray_images
    ]
    reasons: list[str] = []
    warnings: list[str] = []
    if 0 in missing_frames or 5 in missing_frames:
        candidates: list[EdgeCandidate] = []
        selected = None
        reasons.append("both zero-offset frames are required for edge discovery")
    else:
        candidates = _discover_candidates(gray_images[0], gray_images[5])
        for candidate in candidates:
            _track_candidate(
                candidate,
                gray_images,
                reps,
                set(missing_frames),
                offsets,
            )
        selected, selection_error = _select_candidate(candidates)
        if selection_error:
            reasons.append(selection_error)

    localization_path = output_dir / "edge_localization.jpg"
    if 0 not in missing_frames and 5 not in missing_frames:
        _draw_localization_overlay(images, candidates, selected, localization_path)
    contact_path = output_dir / "contact_sheet.jpg"
    if not missing_frames:
        _contact_sheet(images, offsets, contact_path)
    artifacts: dict[str, str] = {}
    if localization_path.exists():
        artifacts["edge_localization"] = str(localization_path)
    if contact_path.exists():
        artifacts["contact_sheet"] = str(contact_path)

    vector = (float("nan"), float("nan"))
    intercept = (float("nan"), float("nan"))
    joint_rms = float("inf")
    joint_rms_mm = float("inf")
    scale = float("nan")
    duplicate_disagreement = float("inf")
    duplicate_disagreement_mm = float("inf")
    forward_vector = (float("nan"), float("nan"))
    reverse_vector = (float("nan"), float("nan"))
    magnitude_delta = float("inf")
    direction_delta = float("inf")
    observations: list[dict[str, Any]] = []
    usable_frames = 0
    span = 0.0
    minimum_correlation = None
    median_correlation = None
    selected_fit = None

    if selected is not None:
        selected_fit = _fit_vector(offsets, selected.positions)
        if selected_fit is None:
            reasons.append("selected edge motion fit is unavailable")
        else:
            vector, intercept, joint_rms, valid_indices, residuals = selected_fit
            scale = float(np.linalg.norm(vector))
            joint_rms_mm = joint_rms / scale if scale > 0.0 else float("inf")
            usable_frames = len(valid_indices)
            span = max(offsets[index] for index in valid_indices) - min(
                offsets[index] for index in valid_indices
            )
            for index, residual in zip(valid_indices, residuals):
                predicted = np.asarray(intercept) + np.asarray(vector) * offsets[index]
                observations.append(
                    {
                        "frame_index": index,
                        "offset_mm": offsets[index],
                        "position_px": list(selected.positions[index]),
                        "predicted_position_px": predicted.tolist(),
                        "residual_px": residual,
                        "seam_y_px": selected.seam_y_px[index],
                        "correlation": selected.correlations[index],
                    }
                )
            correlations = [
                value for value in selected.correlations if value is not None
            ]
            if correlations:
                minimum_correlation = min(correlations)
                median_correlation = float(np.median(correlations))
            duplicate_disagreement = _duplicate_disagreement(selected)
            duplicate_disagreement_mm = duplicate_disagreement / scale
            forward_fit = _fit_vector(offsets, selected.positions, [0, 1, 2])
            reverse_fit = _fit_vector(offsets, selected.positions, [3, 4, 5])
            if forward_fit is not None:
                forward_vector = forward_fit[0]
            if reverse_fit is not None:
                reverse_vector = reverse_fit[0]
            if all(
                math.isfinite(value) for value in (*forward_vector, *reverse_vector)
            ):
                forward_magnitude = float(np.linalg.norm(forward_vector))
                reverse_magnitude = float(np.linalg.norm(reverse_vector))
                magnitude_delta = abs(forward_magnitude - reverse_magnitude) / max(
                    forward_magnitude,
                    reverse_magnitude,
                    1.0e-12,
                )
                direction_delta = _vector_angle_degrees(
                    forward_vector,
                    reverse_vector,
                )

            if usable_frames < MIN_USABLE_FRAMES:
                reasons.append("fewer than five usable frames")
            if span < MIN_SPAN_MM:
                reasons.append("commanded span is below 20 mm")
            if not MIN_SCALE_PX_PER_MM <= scale <= MAX_SCALE_PX_PER_MM:
                reasons.append("recovered scale is outside 2 to 30 px/mm")
            if joint_rms_mm > MAX_DISCREPANCY_MM:
                reasons.append("joint residual RMS is above 1.5 mm")
            elif joint_rms > WARN_RMS_PX:
                warnings.append(
                    f"joint residual RMS is above 0.75 px ({joint_rms_mm:.4f} mm)"
                )
            if duplicate_disagreement_mm > MAX_DISCREPANCY_MM:
                reasons.append("duplicate-position discrepancy is above 1.5 mm")
            elif duplicate_disagreement > WARN_DUPLICATE_DISAGREEMENT_PX:
                warnings.append(
                    "duplicate-position disagreement is above 1.0 px "
                    f"({duplicate_disagreement_mm:.4f} mm)"
                )
            if not math.isfinite(magnitude_delta):
                warnings.append("forward/reverse magnitude comparison is unavailable")
            elif magnitude_delta > WARN_DIRECTION_MAGNITUDE_DELTA:
                warnings.append("forward/reverse magnitude disagreement is above 3%")
            if not math.isfinite(direction_delta):
                warnings.append("forward/reverse direction comparison is unavailable")
            elif direction_delta > WARN_DIRECTION_ANGLE_DEG:
                warnings.append(
                    "forward/reverse direction disagreement is above 1 degree"
                )

            tracking_path = output_dir / "edge_tracking_overlay.jpg"
            displacement_path = output_dir / "displacement_vs_y.jpg"
            _draw_tracking_overlay(
                images,
                selected,
                offsets,
                selected_fit,
                tracking_path,
            )
            _plot_displacement(selected, offsets, selected_fit, displacement_path)
            artifacts["edge_tracking_overlay"] = str(tracking_path)
            artifacts["displacement_vs_y"] = str(displacement_path)
            if all(
                math.isfinite(value) for value in (*forward_vector, *reverse_vector)
            ):
                direction_path = output_dir / "forward_reverse.jpg"
                _plot_direction(forward_vector, reverse_vector, direction_path)
                artifacts["forward_reverse"] = str(direction_path)

    accepted = not reasons
    angle = (
        math.degrees(math.atan2(vector[1], vector[0]))
        if all(math.isfinite(value) for value in vector)
        else float("nan")
    )
    observed_target = (
        {
            "localizer": {
                "kind": LOCALIZER_KIND,
                "version": LOCALIZER_VERSION,
            },
            "candidate_id": selected.candidate_id,
            "reference_line_px": list(selected.reference_line),
            "duplicate_line_px": list(selected.duplicate_line),
            "tracking_strip_px": list(selected.strip_rect),
            "reference_seam_y_px": selected.reference_seam_y_px,
            "span_fraction": selected.span_fraction,
            "duplicate_y_delta_px": selected.duplicate_y_delta_px,
            "duplicate_overlap_fraction": selected.duplicate_overlap_fraction,
            "edge_pair_score": selected.edge_pair_score,
            "edge_pair_ratio": selected.edge_pair_ratio,
            "reference_tab_side": selected.reference_tab_side,
            "duplicate_tab_side": selected.duplicate_tab_side,
        }
        if selected is not None
        else None
    )
    result = {
        "accepted": accepted,
        "reasons": sorted(set(reasons)),
        "warnings": sorted(set(warnings)),
        "missing_frames": missing_frames,
        "usable_frame_count": usable_frames,
        "commanded_span_mm": span,
        "localizer": {
            "kind": LOCALIZER_KIND,
            "version": LOCALIZER_VERSION,
            "configured_position": None,
        },
        "discovered_candidate_count": len(candidates),
        "selected_candidate_id": (
            selected.candidate_id if selected is not None else None
        ),
        "observed_target": observed_target,
        "axis_vector_px_per_mm": (
            [float(vector[0]), float(vector[1])]
            if all(math.isfinite(value) for value in vector)
            else None
        ),
        "scale_px_per_mm": scale,
        "inverse_scale_mm_per_px": 1.0 / scale if scale > 0.0 else float("inf"),
        "angle_deg": angle,
        "joint_residual_rms_px": joint_rms,
        "joint_residual_rms_mm": joint_rms_mm,
        "duplicate_position_disagreement_px": duplicate_disagreement,
        "duplicate_position_disagreement_mm": duplicate_disagreement_mm,
        "forward_vector_px_per_mm": (
            list(forward_vector)
            if all(math.isfinite(value) for value in forward_vector)
            else None
        ),
        "reverse_vector_px_per_mm": (
            list(reverse_vector)
            if all(math.isfinite(value) for value in reverse_vector)
            else None
        ),
        "forward_reverse_magnitude_delta_fraction": magnitude_delta,
        "forward_reverse_angle_delta_deg": direction_delta,
        "minimum_correlation": minimum_correlation,
        "median_correlation": median_correlation,
        "candidates": [_candidate_record(candidate) for candidate in candidates],
        "observations": observations,
        "artifacts": {
            name: {
                "path": artifact,
                "sha256": sha256_file(Path(artifact)),
            }
            for name, artifact in artifacts.items()
        },
    }
    return _json_finite(result)


def _json_finite(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_finite(item) for item in value]
    if isinstance(value, tuple):
        return [_json_finite(item) for item in value]
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    return value
