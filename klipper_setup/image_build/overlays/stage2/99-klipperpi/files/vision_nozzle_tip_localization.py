#!/usr/bin/env python3
"""Shared physical nozzle-tip localization for vision calibration jobs."""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from vision_four_fiducials import detect_four_fiducials

_logger = logging.getLogger(__name__)


class NozzleTipLocalizationError(RuntimeError):
    pass


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
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    image_area = float(width * height)
    candidates: list[dict[str, Any]] = []
    for component in range(1, count):
        x, y, box_width, box_height, area = [int(item) for item in stats[component]]
        fill = area / float(max(1, box_width * box_height))
        relative_area = area / image_area
        boundary = (
            x <= 0.10 * width
            or x + box_width >= 0.90 * width
            or y <= 0.05 * height
            or y + box_height >= 0.90 * height
        )
        shape_ok = (
            0.00012 <= relative_area <= 0.008
            and 0.005 * width <= box_width <= 0.085 * width
            and 0.014 * height <= box_height <= 0.19 * height
            and fill >= 0.08
        )
        if not shape_ok or boundary:
            continue
        candidates.append(
            {
                "candidate_id": f"f{frame_index:02d}_red_{len(candidates):02d}",
                "center_px": [
                    float(centroids[component][0]),
                    float(centroids[component][1]),
                ],
                "bbox_px": [x, y, x + box_width, y + box_height],
                "area_px": area,
                "relative_area": relative_area,
                "fill_fraction": fill,
            }
        )
    return candidates


def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _clahe(image: np.ndarray) -> np.ndarray:
    return cv2.createCLAHE(2.0, (8, 8)).apply(_gray(image))


def _gradient(image: np.ndarray) -> np.ndarray:
    gray = _clahe(image)
    x_gradient = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    y_gradient = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(x_gradient, y_gradient)
    return cv2.normalize(magnitude, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


def _select_marker(
    image: np.ndarray, expected: np.ndarray, frame_index: int
) -> tuple[np.ndarray, dict[str, Any] | None]:
    candidates = _red_candidates(image, frame_index)
    if not candidates:
        _logger.info(
            "match rejected stage=red_marker_detection frame=%d "
            "reason=no red-marker candidates; using expected marker position",
            frame_index,
        )
        return expected.copy(), None
    selected = min(
        candidates,
        key=lambda item: float(
            np.linalg.norm(np.asarray(item["center_px"]) - expected)
        ),
    )
    center = np.asarray(selected["center_px"], dtype=np.float64)
    distance = float(np.linalg.norm(center - expected))
    if distance > 60.0:
        _logger.info(
            "match rejected stage=red_marker_distance_gate frame=%d "
            "reason=nearest candidate is too far from expected position "
            "distance_px=%.3f maximum_px=60.000; using expected marker position",
            frame_index,
            distance,
        )
        return expected.copy(), None
    return center, selected


def _circle_edge_score(gray: np.ndarray, center: np.ndarray, radius: float) -> float:
    angles = np.linspace(0.0, 2.0 * math.pi, 96, endpoint=False)
    scores = []
    for scale in (0.82, 0.94, 1.06, 1.18):
        xs = np.rint(center[0] + radius * scale * np.cos(angles)).astype(int)
        ys = np.rint(center[1] + radius * scale * np.sin(angles)).astype(int)
        valid = (
            (xs >= 1) & (xs < gray.shape[1] - 1) & (ys >= 1) & (ys < gray.shape[0] - 1)
        )
        if int(np.count_nonzero(valid)) < 80:
            return 0.0
        values = gray[ys[valid], xs[valid]].astype(np.float64)
        scores.append((float(np.mean(values)), float(np.std(values))))
    means = np.asarray([item[0] for item in scores])
    symmetry = float(np.median([item[1] for item in scores]))
    return float(np.sum(np.abs(np.diff(means))) - 0.35 * symmetry)


def _ring_candidates(image: np.ndarray, marker: np.ndarray) -> list[dict[str, Any]]:
    height, width = image.shape[:2]
    scale = min(width / 1920.0, height / 1080.0)
    radius = int(round(190.0 * scale))
    x0 = max(0, int(round(marker[0])) - radius)
    y0 = max(0, int(round(marker[1])) - radius)
    x1 = min(width, int(round(marker[0])) + radius)
    y1 = min(height, int(round(marker[1])) + radius)
    gray = _gray(image)
    roi = gray[y0:y1, x0:x1]
    blurred = cv2.GaussianBlur(roi, (7, 7), 2.5)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.15,
        minDist=max(22.0, 32.0 * scale),
        param1=90,
        param2=27,
        minRadius=max(18, int(round(32 * scale))),
        maxRadius=max(35, int(round(78 * scale))),
    )
    if circles is None:
        return []
    gray = _gray(image)
    result = []
    for local_x, local_y, circle_radius in circles[0]:
        center = np.asarray([local_x + x0, local_y + y0], dtype=np.float64)
        delta = center - marker
        distance = float(np.linalg.norm(delta))
        if not 35.0 * scale <= distance <= 180.0 * scale:
            continue
        edge_score = _circle_edge_score(gray, center, float(circle_radius))
        if edge_score < 10.0:
            continue
        result.append(
            {
                "center_px": center.tolist(),
                "radius_px": float(circle_radius),
                "marker_delta_px": delta.tolist(),
                "edge_score": edge_score,
            }
        )
    return sorted(result, key=lambda item: item["edge_score"], reverse=True)[:12]


def _cluster_candidates(
    candidate_sets: dict[int, list[dict[str, Any]]],
    *,
    delta_field: str,
    score_field: str,
    radius_px: float,
) -> tuple[np.ndarray, float, dict[int, dict[str, Any]]]:
    entries = [
        candidate for candidates in candidate_sets.values() for candidate in candidates
    ]
    if not entries:
        raise NozzleTipLocalizationError(f"no candidates contain {delta_field}")
    best = None
    for seed in entries:
        seed_delta = np.asarray(seed[delta_field], dtype=np.float64)
        selected = {}
        for frame_index, candidates in candidate_sets.items():
            nearby = [
                candidate
                for candidate in candidates
                if float(
                    np.linalg.norm(
                        np.asarray(candidate[delta_field], dtype=np.float64)
                        - seed_delta
                    )
                )
                <= radius_px
            ]
            if nearby:
                selected[frame_index] = max(
                    nearby, key=lambda item: float(item[score_field])
                )
        if not selected:
            continue
        deltas = np.asarray(
            [item[delta_field] for item in selected.values()],
            dtype=np.float64,
        )
        center = np.median(deltas, axis=0)
        spread = float(np.median(np.linalg.norm(deltas - center, axis=1)))
        score = (
            len(selected) * 100.0
            - 8.0 * spread
            + sum(float(item[score_field]) for item in selected.values())
        )
        if best is None or score > best[0]:
            best = (score, center, spread, selected)
    if best is None:
        raise NozzleTipLocalizationError(f"no consistent {delta_field} trajectory")
    return best[1], best[2], best[3]


def _is_physical_tip_delta(delta: np.ndarray, ring_radius: float) -> bool:
    return bool(delta[0] >= 0.12 * ring_radius and abs(delta[1]) <= 0.15 * ring_radius)


def _tip_candidates(
    image: np.ndarray,
    ring: dict[str, Any],
    *,
    physical_tip_only: bool = False,
) -> list[dict[str, Any]]:
    gray = _gray(image)
    ring_center = np.asarray(ring["center_px"], dtype=np.float64)
    ring_radius = float(ring["radius_px"])
    search_radius = max(8, int(round(0.36 * ring_radius)))
    center_x, center_y = np.rint(ring_center).astype(int)
    x0 = max(0, center_x - search_radius)
    y0 = max(0, center_y - search_radius)
    x1 = min(gray.shape[1], center_x + search_radius + 1)
    y1 = min(gray.shape[0], center_y + search_radius + 1)
    roi = gray[y0:y1, x0:x1]
    local_center = ring_center - np.asarray([x0, y0], dtype=np.float64)
    yy, xx = np.ogrid[: roi.shape[0], : roi.shape[1]]
    delta_x = xx - local_center[0]
    delta_y = yy - local_center[1]
    mask = delta_x**2 + delta_y**2 <= (0.34 * ring_radius) ** 2
    values = roi[mask]
    if values.size < 20:
        return []
    candidates = []
    maximum_area = max(80, int(round(0.10 * math.pi * ring_radius**2)))
    for percentile in (90, 92, 94, 96):
        threshold = float(np.percentile(values, percentile))
        binary = np.uint8((roi >= threshold) & mask) * 255
        count, labels, stats, centers = cv2.connectedComponentsWithStats(binary)
        for component in range(1, count):
            area = int(stats[component, cv2.CC_STAT_AREA])
            if not 2 <= area <= maximum_area:
                continue
            center = np.asarray(
                [
                    x0 + centers[component][0],
                    y0 + centers[component][1],
                ],
                dtype=np.float64,
            )
            delta = center - ring_center
            distance = float(np.linalg.norm(delta))
            if distance > 0.34 * ring_radius:
                continue
            # The physical nozzle tip is the bright feature just camera-right of
            # the circular locator's horizontal centerline. Other bright
            # features lower in the ring are not nozzle-tip measurements.
            if physical_tip_only and not _is_physical_tip_delta(
                delta,
                ring_radius,
            ):
                continue
            component_values = roi[labels == component].astype(np.float64)
            mean_value = float(np.mean(component_values))
            peak_value = float(np.max(component_values))
            score = (
                mean_value
                + 0.35 * peak_value
                - 30.0 * distance / ring_radius
                + 0.30 * math.sqrt(area)
            )
            candidates.append(
                {
                    "center_px": center.tolist(),
                    "tip_to_ring_delta_px": delta.tolist(),
                    "area_px": area,
                    "mean_intensity": mean_value,
                    "peak_intensity": peak_value,
                    "threshold_percentile": percentile,
                    "score": score,
                }
            )
    candidates.sort(key=lambda item: float(item["score"]), reverse=True)
    unique = []
    for candidate in candidates:
        center = np.asarray(candidate["center_px"], dtype=np.float64)
        if all(
            float(
                np.linalg.norm(
                    center - np.asarray(existing["center_px"], dtype=np.float64)
                )
            )
            > 3.0
            for existing in unique
        ):
            unique.append(candidate)
    return unique[:8]


def _crop(
    image: np.ndarray, center: np.ndarray, size: int
) -> tuple[np.ndarray, tuple[int, int]]:
    half = size // 2
    x0 = max(0, min(image.shape[1] - size, int(round(center[0])) - half))
    y0 = max(0, min(image.shape[0] - size, int(round(center[1])) - half))
    return image[y0 : y0 + size, x0 : x0 + size], (x0, y0)


def _subpixel_peak(response: np.ndarray, location: tuple[int, int]) -> np.ndarray:
    x, y = location
    result = np.asarray([float(x), float(y)], dtype=np.float64)
    for axis, coordinate, limit in (
        (0, x, response.shape[1]),
        (1, y, response.shape[0]),
    ):
        if coordinate <= 0 or coordinate >= limit - 1:
            continue
        if axis == 0:
            left, center, right = (
                float(response[y, x - 1]),
                float(response[y, x]),
                float(response[y, x + 1]),
            )
        else:
            left, center, right = (
                float(response[y - 1, x]),
                float(response[y, x]),
                float(response[y + 1, x]),
            )
        denominator = left - 2.0 * center + right
        if abs(denominator) > 1e-9:
            result[axis] += float(
                np.clip(0.5 * (left - right) / denominator, -0.75, 0.75)
            )
    return result


def _match_template_scaled(
    reference: np.ndarray,
    image: np.ndarray,
    predicted_center: np.ndarray,
    *,
    search_size: int,
) -> dict[str, Any]:
    search, (search_x, search_y) = _crop(image, predicted_center, search_size)
    search_representations = {
        "gray": _gray(search),
        "clahe": _clahe(search),
        "gradient": _gradient(search),
    }
    reference_representations = {
        "gray": _gray(reference),
        "clahe": _clahe(reference),
        "gradient": _gradient(reference),
    }
    records = []
    for scale in np.linspace(0.86, 1.14, 29):
        width = max(12, int(round(reference.shape[1] * scale)))
        height = max(12, int(round(reference.shape[0] * scale)))
        if width >= search.shape[1] or height >= search.shape[0]:
            continue
        centers = []
        correlations = []
        for name in ("gray", "clahe"):
            template = cv2.resize(
                reference_representations[name],
                (width, height),
                interpolation=cv2.INTER_CUBIC,
            )
            response = cv2.matchTemplate(
                search_representations[name],
                template,
                cv2.TM_CCOEFF_NORMED,
            )
            _minimum, maximum, _minimum_location, maximum_location = cv2.minMaxLoc(
                response
            )
            subpixel = _subpixel_peak(response, maximum_location)
            centers.append(
                np.asarray(
                    [
                        search_x + subpixel[0] + width * 0.5,
                        search_y + subpixel[1] + height * 0.5,
                    ],
                    dtype=np.float64,
                )
            )
            correlations.append(float(maximum))
        center_array = np.asarray(centers)
        center_median = np.median(center_array, axis=0)
        spread = float(np.max(np.linalg.norm(center_array - center_median, axis=1)))
        records.append(
            {
                "scale": float(scale),
                "center_px": center_median,
                "minimum_correlation": min(correlations),
                "median_correlation": float(np.median(correlations)),
                "representation_spread_px": spread,
                "representation_correlations": dict(
                    zip(("gray", "clahe"), correlations)
                ),
            }
        )
    if not records:
        raise NozzleTipLocalizationError("no valid template scale")
    return max(
        records,
        key=lambda item: (
            item["minimum_correlation"] - 0.03 * item["representation_spread_px"]
        ),
    )


def localize_nozzle_tip_grid(
    frame_paths: list[Path],
    *,
    frames: list[dict[str, Any]],
    propagate_missing_rings: bool = False,
    commanded_x_vector_px_per_mm: np.ndarray | None = None,
    minimum_direct_detections: int = 2,
    physical_tip_cluster_radius_px: float = 7.0,
    require_locator: bool = True,
) -> dict[str, Any]:
    """Locate one tool's physical nozzle tip in a registration grid."""
    if len(frame_paths) != len(frames):
        raise NozzleTipLocalizationError(
            "fine-grid frame paths do not match the manifest"
        )
    tools = {str(frame["tool"]) for frame in frames}
    if len(tools) != 1 or tools - {"T0", "T1"}:
        raise NozzleTipLocalizationError("fine-grid analysis requires exactly one tool")
    if minimum_direct_detections < 1:
        raise NozzleTipLocalizationError("minimum direct detections must be positive")
    if physical_tip_cluster_radius_px <= 0.0:
        raise NozzleTipLocalizationError("physical-tip cluster radius must be positive")
    target_tool = tools.pop()

    marker_centers = []
    marker_records = []
    ring_candidate_sets: dict[str, dict[int, list[dict[str, Any]]]] = {target_tool: {}}
    for index, (path, frame) in enumerate(zip(frame_paths, frames)):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise NozzleTipLocalizationError(
                f"fine-grid image {index} cannot be decoded"
            )
        expected = np.asarray(frame["expected_marker_pixel_px"], dtype=np.float64)
        marker, marker_record = _select_marker(image, expected, index)
        marker_centers.append(marker)
        marker_records.append(marker_record)
        ring_candidate_sets[frame["tool"]][index] = _ring_candidates(image, marker)

    ring_tracks: dict[str, dict[int, dict[str, Any]]] = {}
    ring_deltas: dict[str, np.ndarray] = {}
    ring_spreads: dict[str, float] = {}
    physical_tip_tracks: dict[str, dict[int, dict[str, Any]]] = {}
    physical_tip_deltas: dict[str, np.ndarray] = {}
    physical_tip_spreads: dict[str, float] = {}
    ring_radius_medians: dict[str, float] = {}
    for tool in (target_tool,):
        delta, spread, selected = _cluster_candidates(
            ring_candidate_sets[tool],
            delta_field="marker_delta_px",
            score_field="edge_score",
            radius_px=18.0,
        )
        if len(selected) < minimum_direct_detections:
            _logger.info(
                "analysis rejected stage=coarse_ring_localization tool=%s "
                "reason=only %d of %d frames have consistent ring observations; "
                "minimum=%d",
                tool,
                len(selected),
                len(frames),
                minimum_direct_detections,
            )
            raise NozzleTipLocalizationError(
                f"only {len(selected)} coarse ring observations for {tool}"
            )
        ring_deltas[tool] = delta
        ring_spreads[tool] = spread
        ring_tracks[tool] = selected
        ring_radius_medians[tool] = float(
            np.median([float(ring["radius_px"]) for ring in selected.values()])
        )
        physical_tip_candidate_sets = {}
        ring_candidates_for_tip = dict(selected)
        if propagate_missing_rings:
            for index, marker_center in enumerate(marker_centers):
                ring_candidates_for_tip.setdefault(
                    index,
                    {
                        "center_px": (marker_center + delta).tolist(),
                        "radius_px": ring_radius_medians[tool],
                    },
                )
        for index, ring in ring_candidates_for_tip.items():
            image = cv2.imread(str(frame_paths[index]), cv2.IMREAD_COLOR)
            if image is None:
                raise NozzleTipLocalizationError(
                    f"fine-grid image {index} cannot be decoded"
                )
            physical_tip_candidate_sets[index] = _tip_candidates(
                image,
                ring,
                physical_tip_only=True,
            )
        (
            physical_tip_delta,
            physical_tip_spread,
            selected_physical_tips,
        ) = _cluster_candidates(
            physical_tip_candidate_sets,
            delta_field="tip_to_ring_delta_px",
            score_field="score",
            radius_px=physical_tip_cluster_radius_px,
        )
        if len(selected_physical_tips) < minimum_direct_detections:
            _logger.info(
                "analysis rejected stage=physical_tip_detection tool=%s "
                "reason=only %d of %d frames have consistent physical-tip "
                "observations; minimum=%d",
                tool,
                len(selected_physical_tips),
                len(frames),
                minimum_direct_detections,
            )
            raise NozzleTipLocalizationError(
                f"only {len(selected_physical_tips)} physical tip observations "
                f"for {tool}"
            )
        physical_tip_deltas[tool] = physical_tip_delta
        physical_tip_spreads[tool] = physical_tip_spread
        physical_tip_tracks[tool] = selected_physical_tips

    tool_references: dict[str, dict[str, Any]] = {}
    reference_x = float(np.median([frame["x_mm"] for frame in frames]))
    reference_z = float(np.median([frame["z_mm"] for frame in frames]))
    for tool in (target_tool,):
        reference_candidates = [
            (index, frame, physical_tip_tracks[tool].get(index))
            for index, frame in enumerate(frames)
            if frame["tool"] == tool
            and physical_tip_tracks[tool].get(index) is not None
        ]
        index, _frame, selected_tip = min(
            reference_candidates,
            key=lambda item: (
                abs(float(item[1]["z_mm"]) - reference_z)
                + 0.1 * abs(float(item[1]["x_mm"]) - reference_x)
            ),
        )
        center = np.asarray(selected_tip["center_px"], dtype=np.float64)
        reference_image = cv2.imread(str(frame_paths[index]), cv2.IMREAD_COLOR)
        if reference_image is None:
            raise NozzleTipLocalizationError(
                f"fine-grid image {index} cannot be decoded"
            )
        image_scale = min(
            reference_image.shape[1] / 1920.0,
            reference_image.shape[0] / 1080.0,
        )
        template_size = int(round(2.0 * ring_radius_medians[tool] * 0.24))
        template_size = max(
            int(round(24.0 * image_scale)),
            min(int(round(40.0 * image_scale)), template_size),
        )
        template_size += template_size % 2
        template, origin = _crop(reference_image, center, template_size)
        tool_references[tool] = {
            "template": template.copy(),
            "tip_center_px": center,
            "reference_seq": index,
            "reference_x_mm": float(frames[index]["x_mm"]),
            "template_size_px": template_size,
            "template_origin_px": origin,
        }

    registrations = []
    four_fiducials_registrations = []
    for index, (path, frame, marker) in enumerate(
        zip(frame_paths, frames, marker_centers)
    ):
        _logger.info(f"Loading image {index} for fine-grid analysis from {path}")
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise NozzleTipLocalizationError(
                f"fine-grid image {index} cannot be decoded"
            )
        tool = frame["tool"]

        four_fiducials = detect_four_fiducials(
            image, require_locator=require_locator
        )
        four_fiducials_registrations.append(
            {
                "seq": index,
                "tool": tool,
                "x_mm": float(frame["x_mm"]),
                "z_mm": float(frame["z_mm"]),
                "four_fiducials": four_fiducials,
            }
        )

        ring = ring_tracks[tool].get(index)
        ring_center = (
            np.asarray(ring["center_px"], dtype=np.float64)
            if ring is not None
            else marker + ring_deltas[tool]
        )
        detected_tip = physical_tip_tracks[tool].get(index)
        reference_record = tool_references[tool]
        if commanded_x_vector_px_per_mm is None:
            predicted_tip = ring_center + physical_tip_deltas[tool]
        else:
            predicted_tip = np.asarray(
                reference_record["tip_center_px"], dtype=np.float64
            ) + np.asarray(commanded_x_vector_px_per_mm, dtype=np.float64) * (
                float(frame["x_mm"]) - float(reference_record["reference_x_mm"])
            )
        search_size = max(
            int(reference_record["template_size_px"])
            + int(
                round(
                    8.0
                    * min(
                        image.shape[1] / 1920.0,
                        image.shape[0] / 1080.0,
                    )
                )
            ),
            int(round(40.0 * min(image.shape[1] / 1920.0, image.shape[0] / 1080.0))),
        )
        match = _match_template_scaled(
            reference_record["template"],
            image,
            predicted_tip,
            search_size=search_size,
        )
        prediction_error = float(
            np.linalg.norm(np.asarray(match["center_px"]) - predicted_tip)
        )
        ring_radius = (
            float(ring["radius_px"]) if ring is not None else ring_radius_medians[tool]
        )
        maximum_prediction_error = max(
            8.0 * min(image.shape[1] / 1920.0, image.shape[0] / 1080.0),
            0.18 * ring_radius,
        )
        registrations.append(
            {
                "seq": index,
                "tool": tool,
                "x_mm": float(frame["x_mm"]),
                "z_mm": float(frame["z_mm"]),
                "center_px": match["center_px"],
                "template_scale": match["scale"],
                "minimum_correlation": match["minimum_correlation"],
                "median_correlation": match["median_correlation"],
                "representation_spread_px": match["representation_spread_px"],
                "representation_correlations": match["representation_correlations"],
                "marker_center_px": marker,
                "marker_detected": marker_records[index] is not None,
                "ring_center_px": ring_center,
                "ring_radius_px": ring_radius,
                "ring_detected": ring is not None,
                "predicted_tip_center_px": predicted_tip,
                "tip_detector_center_px": (
                    detected_tip["center_px"] if detected_tip is not None else None
                ),
                "tip_prediction_error_px": prediction_error,
                "maximum_tip_prediction_error_px": maximum_prediction_error,
                "reference_seq": reference_record["reference_seq"],
                "tip_roi_size_px": reference_record["template_size_px"],
                "tip_detector_agrees_with_registration": (
                    prediction_error <= maximum_prediction_error
                ),
            }
        )

    return {
        "target_tool": target_tool,
        "registrations": registrations,
        "four_fiducial_registrations": four_fiducials_registrations,
        "ring_tracks": ring_tracks,
        "ring_deltas": ring_deltas,
        "ring_spreads": ring_spreads,
        "physical_tip_tracks": physical_tip_tracks,
        "physical_tip_deltas": physical_tip_deltas,
        "physical_tip_spreads": physical_tip_spreads,
        "tool_references": tool_references,
        "minimum_direct_detections": minimum_direct_detections,
    }
