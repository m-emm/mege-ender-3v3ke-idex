#!/usr/bin/env python3
"""Relative multi-patch analysis for the nozzle-camera bed-tab Y sweep."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from vision_calibration_graph import sha256_file


Y_OFFSETS_MM = [0.0, 5.0, 10.0, 15.0, 20.0, 15.0, 10.0, 5.0, 0.0]
MIN_USABLE_FRAMES = 7
MIN_PATCHES = 3
MIN_SPAN_MM = 15.0
MIN_CORRELATION = 0.75
MIN_MEDIAN_CORRELATION = 0.90
MAX_RMS_PX = 0.75
MAX_DUPLICATE_DISAGREEMENT_PX = 1.0
MAX_DIRECTION_MAGNITUDE_DELTA = 0.03
MAX_DIRECTION_ANGLE_DEG = 1.0
MIN_SCALE_PX_PER_MM = 2.0
MAX_SCALE_PX_PER_MM = 30.0


@dataclass
class PatchTrack:
    patch_id: str
    rect: tuple[int, int, int, int]
    positions: list[tuple[float, float] | None]
    correlations: list[float | None]
    representation_spread_px: list[float | None]
    slope: tuple[float, float] | None
    residual_rms_px: float | None
    rejection_reason: str | None = None
    match_errors: list[str] | None = None


def _gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image.astype(np.uint8)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _representations(gray: np.ndarray) -> dict[str, np.ndarray]:
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    sx = cv2.Sobel(clahe, cv2.CV_32F, 1, 0, ksize=3)
    sy = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
    gradient = cv2.magnitude(sx, sy)
    gradient = cv2.normalize(gradient, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return {"gray": gray, "clahe": clahe, "gradient": gradient}


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


def _candidate_rectangles(
    gray: np.ndarray, maximum: int = 24
) -> list[tuple[int, int, int, int]]:
    height, width = gray.shape
    x0, x1 = int(width * 0.22), int(width * 0.82)
    y0, y1 = int(height * 0.20), int(height * 0.80)
    roi = gray[y0:y1, x0:x1]
    scale = min(width / 1920.0, height / 1080.0)
    patch_width = max(40, int(round(64 * scale)))
    patch_height = max(32, int(round(48 * scale)))
    min_distance = max(24, int(round(40 * scale)))
    corners = cv2.goodFeaturesToTrack(
        roi,
        maxCorners=maximum * 5,
        qualityLevel=0.015,
        minDistance=min_distance,
        blockSize=9,
        useHarrisDetector=False,
    )
    if corners is None:
        return []
    rectangles: list[tuple[int, int, int, int]] = []
    for corner in corners[:, 0, :]:
        cx = int(round(float(corner[0]))) + x0
        cy = int(round(float(corner[1]))) + y0
        left = cx - patch_width // 2
        top = cy - patch_height // 2
        right = left + patch_width
        bottom = top + patch_height
        if left < x0 or top < y0 or right >= x1 or bottom >= y1:
            continue
        patch = gray[top:bottom, left:right]
        clipped_fraction = float(np.mean((patch <= 2) | (patch >= 253)))
        if clipped_fraction > 0.05 or float(np.std(patch)) < 12.0:
            continue
        if any(
            not (right <= old[0] or left >= old[2] or bottom <= old[1] or top >= old[3])
            for old in rectangles
        ):
            continue
        rectangles.append((left, top, right, bottom))
        if len(rectangles) >= maximum:
            break
    return rectangles


def _match_patch(
    reference_reps: dict[str, np.ndarray],
    target_reps: dict[str, np.ndarray],
    rect: tuple[int, int, int, int],
    search_radius: int,
) -> tuple[tuple[float, float] | None, float | None, float | None, str | None]:
    left, top, right, bottom = rect
    patch_width = right - left
    patch_height = bottom - top
    image_height, image_width = next(iter(target_reps.values())).shape
    search_left = max(0, left - search_radius)
    search_top = max(0, top - search_radius)
    search_right = min(image_width, right + search_radius)
    search_bottom = min(image_height, bottom + search_radius)
    matches: list[dict[str, Any]] = []
    for name in ("gray", "clahe", "gradient"):
        template = reference_reps[name][top:bottom, left:right]
        search = target_reps[name][search_top:search_bottom, search_left:search_right]
        if search.shape[0] < patch_height or search.shape[1] < patch_width:
            continue
        response = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _minimum, maximum, _minimum_location, maximum_location = cv2.minMaxLoc(response)
        peak_x, peak_y = maximum_location
        if (
            peak_x <= 0
            or peak_y <= 0
            or peak_x >= response.shape[1] - 1
            or peak_y >= response.shape[0] - 1
        ):
            boundary_hit = True
        else:
            boundary_hit = False
        sub_x, sub_y = _subpixel_peak(response, peak_x, peak_y)
        matches.append(
            {
                "name": name,
                "position": (
                    search_left + sub_x + patch_width / 2.0,
                    search_top + sub_y + patch_height / 2.0,
                ),
                "correlation": float(maximum),
                "boundary_hit": boundary_hit,
            }
        )
    if len(matches) < 2:
        return None, None, None, "fewer than two image representations matched"

    best_pair = min(
        combinations(matches, 2),
        key=lambda pair: float(
            np.linalg.norm(
                np.asarray(pair[0]["position"]) - np.asarray(pair[1]["position"])
            )
        ),
    )
    pair_distance = float(
        np.linalg.norm(
            np.asarray(best_pair[0]["position"]) - np.asarray(best_pair[1]["position"])
        )
    )
    if pair_distance > 2.0:
        correlations = [match["correlation"] for match in matches]
        return (
            None,
            float(np.median(correlations)),
            pair_distance,
            "fewer than two image representations agree",
        )
    pair_center = np.median(
        np.asarray([match["position"] for match in best_pair], dtype=float),
        axis=0,
    )
    selected = [
        match
        for match in matches
        if float(
            np.linalg.norm(np.asarray(match["position"], dtype=float) - pair_center)
        )
        <= 2.0
    ]
    location_array = np.asarray([match["position"] for match in selected], dtype=float)
    center = np.median(location_array, axis=0)
    spread = float(np.max(np.linalg.norm(location_array - center, axis=1)))
    correlation = float(np.median([match["correlation"] for match in selected]))
    if sum(bool(match["boundary_hit"]) for match in selected) >= 2:
        return None, correlation, spread, "registration hit search boundary"
    if correlation < MIN_CORRELATION:
        return None, correlation, spread, "weak correlation"
    return (float(center[0]), float(center[1])), correlation, spread, None


def _rect_at_position(
    rect: tuple[int, int, int, int],
    position: tuple[float, float],
    image_shape: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    width = rect[2] - rect[0]
    height = rect[3] - rect[1]
    left = int(round(position[0] - width / 2.0))
    top = int(round(position[1] - height / 2.0))
    right = left + width
    bottom = top + height
    image_height, image_width = image_shape
    if left < 0 or top < 0 or right > image_width or bottom > image_height:
        return None
    return left, top, right, bottom


def _track_patch(
    reps: list[dict[str, np.ndarray] | None],
    rect: tuple[int, int, int, int],
    missing_frames: set[int],
    search_radius: int,
) -> tuple[
    list[tuple[float, float] | None],
    list[float | None],
    list[float | None],
    list[str],
]:
    frame_count = len(reps)
    positions: list[tuple[float, float] | None] = [None] * frame_count
    correlations: list[float | None] = [None] * frame_count
    spreads: list[float | None] = [None] * frame_count
    errors: list[str] = []
    if 0 in missing_frames or reps[0] is None:
        return positions, correlations, spreads, ["frame 0: missing"]

    positions[0] = (
        (rect[0] + rect[2]) / 2.0,
        (rect[1] + rect[3]) / 2.0,
    )
    correlations[0] = 1.0
    spreads[0] = 0.0
    image_shape = next(iter(reps[0].values())).shape

    def track_sequence(
        indices: list[int], start_rect: tuple[int, int, int, int]
    ) -> None:
        current_rect = start_rect
        for source_index, target_index in zip(indices, indices[1:]):
            if (
                source_index in missing_frames
                or target_index in missing_frames
                or reps[source_index] is None
                or reps[target_index] is None
            ):
                errors.append(
                    f"frame {target_index}: cannot bridge missing predecessor"
                )
                break
            position, correlation, spread, error = _match_patch(
                reps[source_index],
                reps[target_index],
                current_rect,
                search_radius,
            )
            if error or position is None:
                errors.append(f"frame {target_index}: {error or 'match failed'}")
                break
            target_rect = _rect_at_position(rect, position, image_shape)
            if target_rect is None:
                errors.append(f"frame {target_index}: tracked patch left image")
                break
            if positions[target_index] is not None:
                disagreement = float(
                    np.linalg.norm(
                        np.asarray(positions[target_index]) - np.asarray(position)
                    )
                )
                if disagreement > 2.0:
                    positions[target_index] = None
                    correlations[target_index] = None
                    spreads[target_index] = disagreement
                    errors.append(
                        f"frame {target_index}: forward/reverse track disagreement"
                    )
                    break
                position = tuple(
                    float(value)
                    for value in np.mean(
                        np.asarray([positions[target_index], position]), axis=0
                    )
                )
                correlation = min(
                    correlations[target_index] or correlation, correlation
                )
                spread = max(spreads[target_index] or 0.0, spread, disagreement)
            positions[target_index] = position
            correlations[target_index] = correlation
            spreads[target_index] = spread
            current_rect = target_rect

    track_sequence([0, 1, 2, 3, 4], rect)

    if 8 not in missing_frames and reps[8] is not None:
        position, correlation, spread, error = _match_patch(
            reps[0], reps[8], rect, search_radius
        )
        if error or position is None:
            errors.append(f"frame 8: {error or 'match failed'}")
        else:
            reverse_rect = _rect_at_position(rect, position, image_shape)
            if reverse_rect is None:
                errors.append("frame 8: tracked patch left image")
            else:
                positions[8] = position
                correlations[8] = correlation
                spreads[8] = spread
                track_sequence([8, 7, 6, 5, 4], reverse_rect)
    return positions, correlations, spreads, errors


def _fit_vector(
    offsets: list[float],
    positions: list[tuple[float, float] | None],
    indices: list[int] | None = None,
) -> tuple[tuple[float, float], float, list[int]] | None:
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
        design, values, rcond=None
    )
    predicted = design @ coefficients
    rms = float(np.sqrt(np.mean(np.sum((values - predicted) ** 2, axis=1))))
    vector = (float(coefficients[1, 0]), float(coefficients[1, 1]))
    return vector, rms, valid_indices


def _vector_angle_degrees(
    left: tuple[float, float], right: tuple[float, float]
) -> float:
    left_array = np.asarray(left, dtype=float)
    right_array = np.asarray(right, dtype=float)
    denominator = float(np.linalg.norm(left_array) * np.linalg.norm(right_array))
    if denominator <= 1.0e-12:
        return 180.0
    cosine = float(np.clip(np.dot(left_array, right_array) / denominator, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def _cluster_tracks(tracks: list[PatchTrack]) -> tuple[list[PatchTrack], str | None]:
    candidates = [track for track in tracks if track.slope is not None]
    if not candidates:
        return [], "no moving patch trajectories"
    clusters: list[list[PatchTrack]] = []
    for track in candidates:
        vector = np.asarray(track.slope, dtype=float)
        assigned = False
        for cluster in clusters:
            center = np.median(
                np.asarray([item.slope for item in cluster], dtype=float), axis=0
            )
            tolerance = max(0.3, 0.03 * float(np.linalg.norm(center)))
            if float(np.linalg.norm(vector - center)) <= tolerance:
                cluster.append(track)
                assigned = True
                break
        if not assigned:
            clusters.append([track])
    clusters.sort(
        key=lambda cluster: (-len(cluster), min(item.patch_id for item in cluster))
    )
    moving = [
        cluster
        for cluster in clusters
        if MIN_SCALE_PX_PER_MM
        <= float(
            np.linalg.norm(
                np.median(
                    np.asarray([item.slope for item in cluster], dtype=float), axis=0
                )
            )
        )
        <= MAX_SCALE_PX_PER_MM
    ]
    if not moving:
        return [], "all patch clusters were stationary or out of scale range"
    winner = moving[0]
    if len(moving) > 1 and len(moving[1]) >= len(winner):
        return [], "ambiguous equally supported moving patch clusters"
    return winner, None


def _joint_fit(
    tracks: list[PatchTrack], offsets: list[float]
) -> tuple[tuple[float, float], float, list[dict[str, Any]]]:
    rows: list[list[float]] = []
    values_x: list[float] = []
    values_y: list[float] = []
    patch_count = len(tracks)
    observations: list[dict[str, Any]] = []
    for patch_index, track in enumerate(tracks):
        for frame_index, position in enumerate(track.positions):
            if position is None:
                continue
            row = [0.0] * (patch_count + 1)
            row[patch_index] = 1.0
            row[-1] = offsets[frame_index]
            rows.append(row)
            values_x.append(position[0])
            values_y.append(position[1])
            observations.append(
                {
                    "patch_id": track.patch_id,
                    "frame_index": frame_index,
                    "offset_mm": offsets[frame_index],
                    "position_px": [position[0], position[1]],
                }
            )
    design = np.asarray(rows, dtype=float)
    coefficient_x, _rx, _rank_x, _sx = np.linalg.lstsq(
        design, np.asarray(values_x), rcond=None
    )
    coefficient_y, _ry, _rank_y, _sy = np.linalg.lstsq(
        design, np.asarray(values_y), rcond=None
    )
    predicted_x = design @ coefficient_x
    predicted_y = design @ coefficient_y
    residual = np.column_stack(
        [np.asarray(values_x) - predicted_x, np.asarray(values_y) - predicted_y]
    )
    rms = float(np.sqrt(np.mean(np.sum(residual**2, axis=1))))
    for item, residual_value in zip(observations, residual):
        item["residual_px"] = [
            float(residual_value[0]),
            float(residual_value[1]),
        ]
    return (
        (float(coefficient_x[-1]), float(coefficient_y[-1])),
        rms,
        observations,
    )


def _duplicate_disagreement(tracks: list[PatchTrack]) -> float:
    values: list[float] = []
    for track in tracks:
        for left, right in ((0, 8), (1, 7), (2, 6), (3, 5)):
            if track.positions[left] is None or track.positions[right] is None:
                continue
            values.append(
                float(
                    np.linalg.norm(
                        np.asarray(track.positions[left])
                        - np.asarray(track.positions[right])
                    )
                )
            )
    return max(values) if values else float("inf")


def _draw_patch_overlay(
    image: np.ndarray,
    tracks: list[PatchTrack],
    selected_ids: set[str],
    path: Path,
) -> None:
    canvas = image.copy()
    for track in tracks:
        left, top, right, bottom = track.rect
        selected = track.patch_id in selected_ids
        color = (40, 210, 40) if selected else (40, 40, 220)
        cv2.rectangle(canvas, (left, top), (right, bottom), color, 2)
        label = track.patch_id if selected else f"{track.patch_id}: reject"
        cv2.putText(
            canvas,
            label,
            (left, max(15, top - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )
    cv2.imwrite(str(path), canvas)


def _contact_sheet(images: list[np.ndarray], labels: list[str], path: Path) -> None:
    thumb_width = 480
    thumbs: list[np.ndarray] = []
    for image, label in zip(images, labels):
        scale = thumb_width / image.shape[1]
        thumb = cv2.resize(image, (thumb_width, int(round(image.shape[0] * scale))))
        cv2.putText(
            thumb,
            label,
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (40, 240, 240),
            2,
            cv2.LINE_AA,
        )
        thumbs.append(thumb)
    rows = []
    for start in range(0, len(thumbs), 3):
        row = thumbs[start : start + 3]
        while len(row) < 3:
            row.append(np.zeros_like(thumbs[0]))
        rows.append(np.hstack(row))
    cv2.imwrite(str(path), np.vstack(rows))


def _plot_displacement(
    observations: list[dict[str, Any]],
    vector: tuple[float, float],
    path: Path,
) -> None:
    width, height = 1200, 850
    canvas = np.full((height, width, 3), 250, dtype=np.uint8)
    by_patch: dict[str, dict[int, dict[str, Any]]] = {}
    for item in observations:
        by_patch.setdefault(item["patch_id"], {})[int(item["frame_index"])] = item

    for component, panel_top, component_name in (
        (0, 70, "image x"),
        (1, 445, "image y"),
    ):
        panel_left = 100
        panel_right = width - 50
        panel_bottom = panel_top + 300
        traces: dict[str, dict[float, list[float]]] = {
            "forward": {},
            "reverse": {},
        }
        for frames in by_patch.values():
            if 0 not in frames:
                continue
            baseline = float(frames[0]["position_px"][component])
            for frame_index, item in frames.items():
                displacement = float(item["position_px"][component]) - baseline
                offset = float(item["offset_mm"])
                if frame_index <= 4:
                    traces["forward"].setdefault(offset, []).append(displacement)
                if frame_index >= 4:
                    traces["reverse"].setdefault(offset, []).append(displacement)

        points = [
            (offset, float(np.median(values)))
            for trace in traces.values()
            for offset, values in trace.items()
        ]
        points.extend([(0.0, 0.0), (20.0, vector[component] * 20.0)])
        y_values = [value for _offset, value in points]
        y_min = min(y_values)
        y_max = max(y_values)
        padding = max(0.5, (y_max - y_min) * 0.12)
        y_min -= padding
        y_max += padding

        def pixel(offset: float, displacement: float) -> tuple[int, int]:
            x = int(round(panel_left + offset / 20.0 * (panel_right - panel_left)))
            y = int(
                round(
                    panel_bottom
                    - (displacement - y_min)
                    / (y_max - y_min)
                    * (panel_bottom - panel_top)
                )
            )
            return x, y

        cv2.rectangle(
            canvas,
            (panel_left, panel_top),
            (panel_right, panel_bottom),
            (100, 100, 100),
            1,
        )
        if y_min <= 0.0 <= y_max:
            zero_left = pixel(0.0, 0.0)
            zero_right = pixel(20.0, 0.0)
            cv2.line(canvas, zero_left, zero_right, (185, 185, 185), 1)

        for direction, color in (
            ("forward", (40, 150, 40)),
            ("reverse", (190, 70, 180)),
        ):
            trace_points = [
                (offset, float(np.median(values)))
                for offset, values in sorted(traces[direction].items())
            ]
            pixels = [pixel(offset, value) for offset, value in trace_points]
            if len(pixels) >= 2:
                cv2.polylines(
                    canvas,
                    [np.asarray(pixels, dtype=np.int32)],
                    False,
                    color,
                    2,
                    cv2.LINE_AA,
                )
            for point in pixels:
                if direction == "forward":
                    cv2.circle(canvas, point, 6, color, -1, cv2.LINE_AA)
                else:
                    cv2.rectangle(
                        canvas,
                        (point[0] - 5, point[1] - 5),
                        (point[0] + 5, point[1] + 5),
                        color,
                        -1,
                    )

        cv2.putText(
            canvas,
            f"{component_name} displacement; fitted slope {vector[component]:.4f} px/mm",
            (panel_left, panel_top - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (30, 30, 30),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            f"{y_max:.1f}",
            (12, panel_top + 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (30, 30, 30),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            f"{y_min:.1f} px",
            (12, panel_bottom),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (30, 30, 30),
            1,
            cv2.LINE_AA,
        )
    cv2.putText(
        canvas,
        "forward",
        (900, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (40, 150, 40),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "reverse",
        (1030, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (190, 70, 180),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        "commanded Y offset: 0 to 20 mm",
        (430, height - 25),
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
    scale = 18.0
    for vector, color, label in (
        (forward, (30, 170, 30), "forward"),
        (reverse, (210, 80, 40), "reverse"),
    ):
        endpoint = (
            int(round(center[0] + vector[0] * scale)),
            int(round(center[1] + vector[1] * scale)),
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
) -> dict[str, Any]:
    offsets = list(offsets_mm or Y_OFFSETS_MM)
    if len(frame_paths) != len(offsets):
        raise ValueError("frame path count must match commanded offsets")
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
        return {
            "accepted": False,
            "reasons": ["no decodable frames"],
            "missing_frames": missing_frames,
            "tracks": [],
            "artifacts": {},
        }
    expected_shape = valid_images[0].shape
    shape_errors = [
        index
        for index, image in enumerate(images)
        if image.shape != expected_shape and index not in missing_frames
    ]
    if shape_errors:
        return {
            "accepted": False,
            "reasons": [f"inconsistent image dimensions at frames {shape_errors}"],
            "missing_frames": missing_frames,
            "tracks": [],
            "artifacts": {},
        }
    reference_index = next(
        index for index in range(len(images)) if index not in missing_frames
    )
    gray_images = [
        _gray(image) if index not in missing_frames else None
        for index, image in enumerate(images)
    ]
    reps = [
        _representations(gray) if gray is not None else None for gray in gray_images
    ]
    rectangles = _candidate_rectangles(gray_images[reference_index])
    search_radius = max(
        90,
        int(round(min(expected_shape[1] / 1920.0, expected_shape[0] / 1080.0) * 130)),
    )
    tracks: list[PatchTrack] = []
    for patch_index, rect in enumerate(rectangles):
        positions, correlations, spreads, errors = _track_patch(
            reps, rect, set(missing_frames), search_radius
        )
        fit = _fit_vector(offsets, positions)
        track = PatchTrack(
            patch_id=f"patch_{patch_index:02d}",
            rect=rect,
            positions=positions,
            correlations=correlations,
            representation_spread_px=spreads,
            slope=fit[0] if fit else None,
            residual_rms_px=fit[1] if fit else None,
            match_errors=errors,
        )
        valid_correlations = [
            correlation
            for position, correlation in zip(positions, correlations)
            if position is not None and correlation is not None
        ]
        if fit is None:
            track.rejection_reason = "insufficient usable span"
        elif len(valid_correlations) < MIN_USABLE_FRAMES:
            track.rejection_reason = "fewer than seven usable frames"
        elif min(valid_correlations) < MIN_CORRELATION:
            track.rejection_reason = "minimum correlation below 0.75"
        elif float(np.median(valid_correlations)) < MIN_MEDIAN_CORRELATION:
            track.rejection_reason = "median correlation below 0.90"
        elif fit[1] > 1.5:
            track.rejection_reason = "trajectory residual above patch limit"
        tracks.append(track)

    eligible = [track for track in tracks if track.rejection_reason is None]
    selected, cluster_error = _cluster_tracks(eligible)
    selected_ids = {track.patch_id for track in selected}
    for track in eligible:
        if track.patch_id not in selected_ids:
            track.rejection_reason = "outside selected motion-vector cluster"

    reasons: list[str] = []
    usable_frames = len(offsets) - len(missing_frames)
    if usable_frames < MIN_USABLE_FRAMES:
        reasons.append("fewer than seven usable frames")
    available_offsets = [
        offset for index, offset in enumerate(offsets) if index not in missing_frames
    ]
    span = float(max(available_offsets) - min(available_offsets))
    if span < MIN_SPAN_MM:
        reasons.append("commanded span is below 15 mm")
    if cluster_error:
        reasons.append(cluster_error)
    if len(selected) < MIN_PATCHES:
        reasons.append("fewer than three independent moving patches")

    vector = (float("nan"), float("nan"))
    joint_rms = float("inf")
    observations: list[dict[str, Any]] = []
    forward_vector = (float("nan"), float("nan"))
    reverse_vector = (float("nan"), float("nan"))
    magnitude_delta = float("inf")
    direction_delta = float("inf")
    duplicate_disagreement = float("inf")
    correlations: list[float] = []
    if selected:
        vector, joint_rms, observations = _joint_fit(selected, offsets)
        forward_fits = [
            _fit_vector(offsets, track.positions, list(range(0, 5)))
            for track in selected
        ]
        reverse_fits = [
            _fit_vector(offsets, track.positions, list(range(4, 9)))
            for track in selected
        ]
        forward_vectors = [fit[0] for fit in forward_fits if fit is not None]
        reverse_vectors = [fit[0] for fit in reverse_fits if fit is not None]
        if forward_vectors and reverse_vectors:
            forward_vector = tuple(
                float(value) for value in np.median(np.asarray(forward_vectors), axis=0)
            )
            reverse_vector = tuple(
                float(value) for value in np.median(np.asarray(reverse_vectors), axis=0)
            )
            forward_magnitude = float(np.linalg.norm(forward_vector))
            reverse_magnitude = float(np.linalg.norm(reverse_vector))
            magnitude_delta = abs(forward_magnitude - reverse_magnitude) / max(
                forward_magnitude, reverse_magnitude, 1.0e-12
            )
            direction_delta = _vector_angle_degrees(forward_vector, reverse_vector)
        duplicate_disagreement = _duplicate_disagreement(selected)
        correlations = [
            value
            for track in selected
            for value in track.correlations
            if value is not None
        ]
    scale = float(np.linalg.norm(vector))
    if (
        not math.isfinite(scale)
        or not MIN_SCALE_PX_PER_MM <= scale <= MAX_SCALE_PX_PER_MM
    ):
        reasons.append("recovered scale is outside 2 to 30 px/mm")
    if joint_rms > MAX_RMS_PX:
        reasons.append("joint residual RMS is above 0.75 px")
    if duplicate_disagreement > MAX_DUPLICATE_DISAGREEMENT_PX:
        reasons.append("duplicate-position disagreement is above 1.0 px")
    if magnitude_delta > MAX_DIRECTION_MAGNITUDE_DELTA:
        reasons.append("forward/reverse magnitude disagreement is above 3%")
    if direction_delta > MAX_DIRECTION_ANGLE_DEG:
        reasons.append("forward/reverse direction disagreement is above 1 degree")
    if not correlations or min(correlations) < MIN_CORRELATION:
        reasons.append("accepted minimum correlation is below 0.75")
    if not correlations or float(np.median(correlations)) < MIN_MEDIAN_CORRELATION:
        reasons.append("accepted median correlation is below 0.90")

    overlay_path = output_dir / "patch_selection.jpg"
    _draw_patch_overlay(images[reference_index], tracks, selected_ids, overlay_path)
    contact_path = output_dir / "contact_sheet.jpg"
    _contact_sheet(
        [image for index, image in enumerate(images) if index not in missing_frames],
        [
            f"seq={index} Y offset={offsets[index]:g} mm"
            for index in range(len(images))
            if index not in missing_frames
        ],
        contact_path,
    )
    artifacts = {
        "patch_selection": str(overlay_path),
        "contact_sheet": str(contact_path),
    }
    if selected:
        displacement_path = output_dir / "displacement_vs_y.jpg"
        direction_path = output_dir / "forward_reverse.jpg"
        _plot_displacement(observations, vector, displacement_path)
        _plot_direction(forward_vector, reverse_vector, direction_path)
        artifacts.update(
            {
                "displacement_vs_y": str(displacement_path),
                "forward_reverse": str(direction_path),
            }
        )

    accepted = not reasons
    track_records = []
    for track in tracks:
        track_records.append(
            {
                "patch_id": track.patch_id,
                "rect_px": list(track.rect),
                "positions_px": [
                    list(position) if position is not None else None
                    for position in track.positions
                ],
                "correlations": track.correlations,
                "representation_spread_px": track.representation_spread_px,
                "slope_px_per_mm": list(track.slope) if track.slope else None,
                "residual_rms_px": track.residual_rms_px,
                "selected": track.patch_id in selected_ids,
                "rejection_reason": track.rejection_reason,
                "match_errors": track.match_errors,
            }
        )
    axis_vector = (
        [float(vector[0]), float(vector[1])]
        if all(math.isfinite(value) for value in vector)
        else None
    )
    forward_vector_result = (
        [float(forward_vector[0]), float(forward_vector[1])]
        if all(math.isfinite(value) for value in forward_vector)
        else None
    )
    reverse_vector_result = (
        [float(reverse_vector[0]), float(reverse_vector[1])]
        if all(math.isfinite(value) for value in reverse_vector)
        else None
    )
    result = {
        "accepted": accepted,
        "reasons": sorted(set(reasons)),
        "missing_frames": missing_frames,
        "usable_frame_count": usable_frames,
        "commanded_span_mm": span,
        "candidate_patch_count": len(tracks),
        "accepted_patch_count": len(selected),
        "axis_vector_px_per_mm": axis_vector,
        "scale_px_per_mm": scale,
        "inverse_scale_mm_per_px": (
            1.0 / scale if math.isfinite(scale) and scale else None
        ),
        "angle_deg": (
            math.degrees(math.atan2(vector[1], vector[0]))
            if math.isfinite(scale)
            else None
        ),
        "joint_residual_rms_px": joint_rms,
        "duplicate_position_disagreement_px": duplicate_disagreement,
        "forward_vector_px_per_mm": forward_vector_result,
        "reverse_vector_px_per_mm": reverse_vector_result,
        "forward_reverse_magnitude_delta_fraction": magnitude_delta,
        "forward_reverse_angle_delta_deg": direction_delta,
        "minimum_correlation": min(correlations) if correlations else None,
        "median_correlation": float(np.median(correlations)) if correlations else None,
        "tracks": track_records,
        "observations": observations,
        "artifacts": {
            name: {
                "path": path,
                "sha256": sha256_file(Path(path)),
            }
            for name, path in artifacts.items()
        },
    }
    return _json_finite(result)


def _json_finite(value: Any) -> Any:
    """Replace unavailable non-finite diagnostics with strict-JSON nulls."""
    if isinstance(value, dict):
        return {key: _json_finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_finite(item) for item in value]
    if isinstance(value, tuple):
        return [_json_finite(item) for item in value]
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    return value
