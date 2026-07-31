#!/usr/bin/env python3
"""Fine T0/T1 nozzle-tip X/Z analysis using tight relative registration."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from vision_red_marker_x_sweep import _red_candidates


class FineNozzleError(RuntimeError):
    pass


def _finite(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    if isinstance(value, tuple):
        return [_finite(item) for item in value]
    if isinstance(value, np.ndarray):
        return _finite(value.tolist())
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


def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _clahe(image: np.ndarray) -> np.ndarray:
    return cv2.createCLAHE(2.0, (8, 8)).apply(_gray(image))


def _gradient(image: np.ndarray) -> np.ndarray:
    gray = _clahe(image)
    x_gradient = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    y_gradient = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(x_gradient, y_gradient)
    return cv2.normalize(magnitude, None, 0, 255, cv2.NORM_MINMAX).astype(
        np.uint8
    )


def _select_marker(
    image: np.ndarray, expected: np.ndarray, frame_index: int
) -> tuple[np.ndarray, dict[str, Any] | None]:
    candidates = _red_candidates(image, frame_index)
    if not candidates:
        return expected.copy(), None
    selected = min(
        candidates,
        key=lambda item: float(
            np.linalg.norm(np.asarray(item["center_px"]) - expected)
        ),
    )
    center = np.asarray(selected["center_px"], dtype=np.float64)
    if float(np.linalg.norm(center - expected)) > 130.0:
        return expected.copy(), None
    return center, selected


def _circle_edge_score(
    gray: np.ndarray, center: np.ndarray, radius: float
) -> float:
    angles = np.linspace(0.0, 2.0 * math.pi, 96, endpoint=False)
    scores = []
    for scale in (0.82, 0.94, 1.06, 1.18):
        xs = np.rint(center[0] + radius * scale * np.cos(angles)).astype(int)
        ys = np.rint(center[1] + radius * scale * np.sin(angles)).astype(int)
        valid = (
            (xs >= 1)
            & (xs < gray.shape[1] - 1)
            & (ys >= 1)
            & (ys < gray.shape[0] - 1)
        )
        if int(np.count_nonzero(valid)) < 80:
            return 0.0
        values = gray[ys[valid], xs[valid]].astype(np.float64)
        scores.append((float(np.mean(values)), float(np.std(values))))
    means = np.asarray([item[0] for item in scores])
    symmetry = float(np.median([item[1] for item in scores]))
    return float(np.sum(np.abs(np.diff(means))) - 0.35 * symmetry)


def _ring_candidates(
    image: np.ndarray, marker: np.ndarray
) -> list[dict[str, Any]]:
    height, width = image.shape[:2]
    scale = min(width / 1920.0, height / 1080.0)
    radius = int(round(190.0 * scale))
    x0 = max(0, int(round(marker[0])) - radius)
    y0 = max(0, int(round(marker[1])) - radius)
    x1 = min(width, int(round(marker[0])) + radius)
    y1 = min(height, int(round(marker[1])) + radius)
    roi = _clahe(image)[y0:y1, x0:x1]
    blurred = cv2.GaussianBlur(roi, (7, 7), 1.5)
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
        candidate
        for candidates in candidate_sets.values()
        for candidate in candidates
    ]
    if not entries:
        raise FineNozzleError(f"no candidates contain {delta_field}")
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
        raise FineNozzleError(f"no consistent {delta_field} trajectory")
    return best[1], best[2], best[3]


def _tip_candidates(
    image: np.ndarray, ring: dict[str, Any]
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
    mask = (
        (xx - local_center[0]) ** 2 + (yy - local_center[1]) ** 2
        <= (0.34 * ring_radius) ** 2
    )
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
        for name in ("gray", "clahe", "gradient"):
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
        spread = float(
            np.max(np.linalg.norm(center_array - center_median, axis=1))
        )
        records.append(
            {
                "scale": float(scale),
                "center_px": center_median,
                "minimum_correlation": min(correlations),
                "median_correlation": float(np.median(correlations)),
                "representation_spread_px": spread,
                "representation_correlations": dict(
                    zip(("gray", "clahe", "gradient"), correlations)
                ),
            }
        )
    if not records:
        raise FineNozzleError("no valid template scale")
    return max(
        records,
        key=lambda item: (
            item["minimum_correlation"] - 0.03 * item["representation_spread_px"]
        ),
    )


def _fit_tool(records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [
        record
        for record in records
        if record["minimum_correlation"] >= 0.30
        and record["median_correlation"] >= 0.42
        and record["representation_spread_px"] <= 2.5
    ]
    if len(accepted) < 8:
        raise FineNozzleError(
            f"only {len(accepted)} nozzle registrations passed for {records[0]['tool']}"
        )
    x_ref = float(np.median([record["x_mm"] for record in accepted]))
    z_ref = float(np.median([record["z_mm"] for record in accepted]))

    def design_row(record: dict[str, Any]) -> list[float]:
        dx = float(record["x_mm"]) - x_ref
        dz = float(record["z_mm"]) - z_ref
        return [1.0, dx, dz, dx * dz, dx * dx, dx * dx * dz]

    for _iteration in range(3):
        design = np.asarray(
            [design_row(record) for record in accepted],
            dtype=np.float64,
        )
        positions = np.asarray(
            [record["center_px"] for record in accepted], dtype=np.float64
        )
        position_coefficients = np.linalg.lstsq(design, positions, rcond=None)[0]
        residuals = np.linalg.norm(positions - design @ position_coefficients, axis=1)
        median = float(np.median(residuals))
        mad = float(np.median(np.abs(residuals - median)))
        limit = max(2.5, median + 4.0 * max(mad, 0.05))
        retained = [
            record
            for record, residual in zip(accepted, residuals)
            if float(residual) <= limit
        ]
        if len(retained) < 8 or len(retained) == len(accepted):
            break
        accepted = retained
    full_row_z = {
        z_mm
        for z_mm in {float(record["z_mm"]) for record in accepted}
        if len(
            {
                float(record["x_mm"])
                for record in accepted
                if abs(float(record["z_mm"]) - z_mm) < 1e-9
            }
        )
        >= 5
    }
    model_records = [
        record
        for record in accepted
        if float(record["z_mm"]) in full_row_z
    ]
    if len(full_row_z) < 3 or len(model_records) < 15:
        raise FineNozzleError(
            f"only {len(full_row_z)} full rows contain enough X observations"
        )
    design = np.asarray(
        [design_row(record) for record in model_records],
        dtype=np.float64,
    )
    positions = np.asarray(
        [record["center_px"] for record in model_records], dtype=np.float64
    )
    log_scales = np.log(
        np.asarray([record["template_scale"] for record in model_records])
    )
    position_coefficients = np.linalg.lstsq(design, positions, rcond=None)[0]
    scale_coefficients = np.linalg.lstsq(design, log_scales, rcond=None)[0]
    fitted_positions = design @ position_coefficients
    fitted_scales = design @ scale_coefficients
    position_residuals = positions - fitted_positions
    scale_residuals = log_scales - fitted_scales
    return _finite(
        {
            "x_ref_mm": x_ref,
            "z_ref_mm": z_ref,
            "model_family": "quadratic_x_linear_z_position_v1",
            "position_coefficients": position_coefficients,
            "log_scale_coefficients": scale_coefficients,
            "position_fit_rms_px": float(
                np.sqrt(np.mean(np.sum(position_residuals**2, axis=1)))
            ),
            "log_scale_fit_rms": float(np.sqrt(np.mean(scale_residuals**2))),
            "accepted_count": len(model_records),
            "minimum_correlation": min(
                record["minimum_correlation"] for record in model_records
            ),
            "median_correlation": float(
                np.median(
                    [
                        record["minimum_correlation"]
                        for record in model_records
                    ]
                )
            ),
            "accepted_sequences": [
                record["seq"] for record in model_records
            ],
            "trajectory_only_sequences": [
                record["seq"]
                for record in accepted
                if record not in model_records
            ],
            "accepted_direct_positions": [
                {
                    "seq": record["seq"],
                    "x_mm": record["x_mm"],
                    "z_mm": record["z_mm"],
                    "center_px": record["center_px"],
                }
                for record in model_records
            ],
        }
    )


def _evaluate_position(
    model: dict[str, Any], x_mm: float, z_mm: float
) -> np.ndarray:
    dx = x_mm - float(model["x_ref_mm"])
    dz = z_mm - float(model["z_ref_mm"])
    design = np.asarray(
        [1.0, dx, dz, dx * dz, dx * dx, dx * dx * dz]
    )
    return design @ np.asarray(model["position_coefficients"], dtype=np.float64)


def _x_vector(
    model: dict[str, Any], x_mm: float, z_mm: float
) -> np.ndarray:
    coefficients = np.asarray(model["position_coefficients"], dtype=np.float64)
    dx = float(x_mm) - float(model["x_ref_mm"])
    dz = float(z_mm) - float(model["z_ref_mm"])
    return (
        coefficients[1]
        + coefficients[3] * dz
        + 2.0 * coefficients[4] * dx
        + 2.0 * coefficients[5] * dx * dz
    )


def _homography_jacobian(homography: np.ndarray, point: np.ndarray) -> np.ndarray:
    x, y = [float(item) for item in point]
    h = homography
    denominator = h[2, 0] * x + h[2, 1] * y + h[2, 2]
    u_numerator = h[0, 0] * x + h[0, 1] * y + h[0, 2]
    v_numerator = h[1, 0] * x + h[1, 1] * y + h[1, 2]
    return np.asarray(
        [
            [
                (h[0, 0] * denominator - u_numerator * h[2, 0])
                / denominator**2,
                (h[0, 1] * denominator - u_numerator * h[2, 1])
                / denominator**2,
            ],
            [
                (h[1, 0] * denominator - v_numerator * h[2, 0])
                / denominator**2,
                (h[1, 1] * denominator - v_numerator * h[2, 1])
                / denominator**2,
            ],
        ]
    )


def analyze(
    frame_paths: list[Path],
    artifact_dir: Path,
    *,
    frames: list[dict[str, Any]],
    reference: dict[str, Any],
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if len(frame_paths) != len(frames):
        raise FineNozzleError("fine-grid frame paths do not match the manifest")

    marker_centers = []
    marker_records = []
    ring_candidate_sets: dict[str, dict[int, list[dict[str, Any]]]] = {
        "T0": {},
        "T1": {},
    }
    for index, (path, frame) in enumerate(zip(frame_paths, frames)):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FineNozzleError(f"fine-grid image {index} cannot be decoded")
        expected = np.asarray(frame["expected_marker_pixel_px"], dtype=np.float64)
        marker, marker_record = _select_marker(image, expected, index)
        marker_centers.append(marker)
        marker_records.append(marker_record)
        ring_candidate_sets[frame["tool"]][index] = _ring_candidates(image, marker)

    ring_tracks: dict[str, dict[int, dict[str, Any]]] = {}
    ring_deltas: dict[str, np.ndarray] = {}
    ring_spreads: dict[str, float] = {}
    tip_tracks: dict[str, dict[int, dict[str, Any]]] = {}
    tip_deltas: dict[str, np.ndarray] = {}
    tip_spreads: dict[str, float] = {}
    ring_radius_medians: dict[str, float] = {}
    for tool in ("T0", "T1"):
        delta, spread, selected = _cluster_candidates(
            ring_candidate_sets[tool],
            delta_field="marker_delta_px",
            score_field="edge_score",
            radius_px=18.0,
        )
        if len(selected) < 14:
            raise FineNozzleError(
                f"only {len(selected)} coarse ring observations for {tool}"
            )
        ring_deltas[tool] = delta
        ring_spreads[tool] = spread
        ring_tracks[tool] = selected
        tip_candidate_sets = {}
        for index, ring in selected.items():
            image = cv2.imread(str(frame_paths[index]), cv2.IMREAD_COLOR)
            if image is None:
                raise FineNozzleError(
                    f"fine-grid image {index} cannot be decoded"
                )
            tip_candidate_sets[index] = _tip_candidates(image, ring)
        tip_delta, tip_spread, selected_tips = _cluster_candidates(
            tip_candidate_sets,
            delta_field="tip_to_ring_delta_px",
            score_field="score",
            radius_px=7.0,
        )
        if len(selected_tips) < 14:
            raise FineNozzleError(
                f"only {len(selected_tips)} tip observations for {tool}"
            )
        tip_deltas[tool] = tip_delta
        tip_spreads[tool] = tip_spread
        tip_tracks[tool] = selected_tips
        ring_radius_medians[tool] = float(
            np.median(
                [float(ring["radius_px"]) for ring in selected.values()]
            )
        )

    tool_references: dict[str, dict[str, Any]] = {}
    for tool in ("T0", "T1"):
        reference_candidates = [
            (index, frame, tip_tracks[tool].get(index))
            for index, frame in enumerate(frames)
            if frame["tool"] == tool and tip_tracks[tool].get(index) is not None
        ]
        index, _frame, selected_tip = min(
            reference_candidates,
            key=lambda item: (
                abs(float(item[1]["z_mm"]) - 5.0)
                + 0.1
                * abs(
                    float(item[1]["x_mm"])
                    - float(reference["bed_tab_x_mm"] + 16.0)
                )
            ),
        )
        center = np.asarray(selected_tip["center_px"], dtype=np.float64)
        reference_image = cv2.imread(
            str(frame_paths[index]), cv2.IMREAD_COLOR
        )
        if reference_image is None:
            raise FineNozzleError(
                f"fine-grid image {index} cannot be decoded"
            )
        image_scale = min(
            reference_image.shape[1] / 1920.0,
            reference_image.shape[0] / 1080.0,
        )
        template_size = int(
            round(2.0 * ring_radius_medians[tool] * 0.24)
        )
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
            "template_size_px": template_size,
            "template_origin_px": origin,
        }

    registrations = []
    for index, (path, frame, marker) in enumerate(
        zip(frame_paths, frames, marker_centers)
    ):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FineNozzleError(
                f"fine-grid image {index} cannot be decoded"
            )
        tool = frame["tool"]
        ring = ring_tracks[tool].get(index)
        ring_center = (
            np.asarray(ring["center_px"], dtype=np.float64)
            if ring is not None
            else marker + ring_deltas[tool]
        )
        detected_tip = tip_tracks[tool].get(index)
        predicted = (
            np.asarray(detected_tip["center_px"], dtype=np.float64)
            if detected_tip is not None
            else ring_center + tip_deltas[tool]
        )
        reference_record = tool_references[tool]
        search_size = max(
            int(round(76.0 * min(image.shape[1] / 1920.0, image.shape[0] / 1080.0))),
            int(reference_record["template_size_px"]) * 2 + 8,
        )
        match = _match_template_scaled(
            reference_record["template"],
            image,
            predicted,
            search_size=search_size,
        )
        prediction_error = float(
            np.linalg.norm(np.asarray(match["center_px"]) - predicted)
        )
        ring_radius = (
            float(ring["radius_px"])
            if ring is not None
            else ring_radius_medians[tool]
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
                "representation_correlations": match[
                    "representation_correlations"
                ],
                "marker_center_px": marker,
                "marker_detected": marker_records[index] is not None,
                "ring_center_px": ring_center,
                "ring_radius_px": ring_radius,
                "ring_detected": ring is not None,
                "predicted_tip_center_px": predicted,
                "tip_detector_center_px": (
                    detected_tip["center_px"]
                    if detected_tip is not None
                    else None
                ),
                "tip_prediction_error_px": prediction_error,
                "maximum_tip_prediction_error_px": maximum_prediction_error,
                "reference_seq": reference_record["reference_seq"],
                "tip_roi_size_px": reference_record["template_size_px"],
            }
        )

    models = {
        tool: _fit_tool(
            [record for record in registrations if record["tool"] == tool]
        )
        for tool in ("T0", "T1")
    }
    fiducial_reference_xy = np.asarray(
        reference["fiducial_reference_printer_xy_mm"],
        dtype=np.float64,
    )
    fiducial_reference_pixel = np.asarray(
        reference["fiducial_reference_pixel_at_fine_capture_px"],
        dtype=np.float64,
    )
    bed_x_fiducial = np.asarray(
        reference["fiducial_x_vector_at_fine_capture_px_per_mm"],
        dtype=np.float64,
    )
    fiducial_plane_z = float(reference["fiducial_plane_printer_z_mm"])
    fiducial_x = float(fiducial_reference_xy[0])
    image_y_vector = np.asarray(
        reference["image_y_axis_vector_px_per_mm"], dtype=np.float64
    )
    vector_comparison_at_z0 = {}
    for tool in ("T0", "T1"):
        nozzle_vector = _x_vector(models[tool], fiducial_x, 0.0)
        residual = nozzle_vector - bed_x_fiducial
        coefficients = np.asarray(
            models[tool]["position_coefficients"],
            dtype=np.float64,
        )
        dx_fiducial = fiducial_x - float(models[tool]["x_ref_mm"])
        z_slope = coefficients[3] + 2.0 * coefficients[5] * dx_fiducial
        vector_comparison_at_z0[tool] = {
            "nozzle_x_vector_px_per_mm": nozzle_vector,
            "fiducial_x_vector_px_per_mm": bed_x_fiducial,
            "residual_vector_px_per_mm": residual,
            "residual_magnitude_px_per_mm": float(np.linalg.norm(residual)),
            "x_vector_z_slope_px_per_mm_per_mm": z_slope,
        }
    cross_tool_reference_x = float(reference["bed_tab_x_mm"] + 16.0)
    cross_tool_reference_z = 5.0
    cross_tool_reference_offset = (
        _evaluate_position(
            models["T1"],
            cross_tool_reference_x,
            cross_tool_reference_z,
        )
        - _evaluate_position(
            models["T0"],
            cross_tool_reference_x,
            cross_tool_reference_z,
        )
    )

    reasons = []
    warnings = []
    for tool in ("T0", "T1"):
        model = models[tool]
        tool_records = [
            record for record in registrations if record["tool"] == tool
        ]
        accepted_sequences_for_tool = {
            int(item) for item in model["accepted_sequences"]
        }
        accepted_tool_records = [
            record
            for record in tool_records
            if int(record["seq"]) in accepted_sequences_for_tool
        ]
        z_span = max(record["z_mm"] for record in tool_records) - min(
            record["z_mm"] for record in tool_records
        )
        if model["position_fit_rms_px"] > 2.0:
            reasons.append(
                f"{tool} position fit RMS {model['position_fit_rms_px']:.3f} px"
            )
        if model["accepted_count"] < 14:
            reasons.append(
                f"{tool} has only {model['accepted_count']} accepted registrations"
            )
        if z_span < 8.0:
            reasons.append(
                f"{tool} usable Z span is only {z_span:.3f} mm"
            )
        if model["minimum_correlation"] < 0.5:
            warnings.append(
                f"{tool} minimum accepted correlation is {model['minimum_correlation']:.3f}"
            )
        if tip_spreads[tool] > 5.0:
            reasons.append(
                f"{tool} tip-localizer spread {tip_spreads[tool]:.3f} px is too large"
            )
        if len(tip_tracks[tool]) < 14:
            reasons.append(
                f"{tool} has only {len(tip_tracks[tool])} direct tip detections"
            )
        full_rows = []
        for z_mm in sorted(
            {float(record["z_mm"]) for record in tool_records}
        ):
            row = [
                record
                for record in accepted_tool_records
                if abs(float(record["z_mm"]) - z_mm) < 1e-9
            ]
            unique_x = sorted({float(record["x_mm"]) for record in row})
            if len(unique_x) >= 2:
                full_rows.append(
                    {
                        "z_mm": z_mm,
                        "accepted_count": len(unique_x),
                        "x_span_mm": unique_x[-1] - unique_x[0],
                    }
                )
        if len(full_rows) < 3:
            reasons.append(f"{tool} has only {len(full_rows)} usable full X rows")
        for row in full_rows:
            if row["accepted_count"] < 5 or row["x_span_mm"] < 12.0:
                reasons.append(
                    f"{tool} Z={row['z_mm']:.3f} row has "
                    f"{row['accepted_count']} X positions over "
                    f"{row['x_span_mm']:.3f} mm"
                )
        model["full_row_coverage"] = full_rows
        if (
            vector_comparison_at_z0[tool]["residual_magnitude_px_per_mm"]
            > 0.25
        ):
            warnings.append(
                f"{tool} fiducial/nozzle X-vector residual at commanded Z=0 is "
                f"{vector_comparison_at_z0[tool]['residual_magnitude_px_per_mm']:.3f} "
                "px/mm; Stage 5.1 will solve the crossing"
            )
    slopes = [
        np.asarray(
            vector_comparison_at_z0[tool][
                "x_vector_z_slope_px_per_mm_per_mm"
            ],
            dtype=np.float64,
        )
        for tool in ("T0", "T1")
    ]
    slope_norms = [float(np.linalg.norm(item)) for item in slopes]
    if min(slope_norms) <= 1e-8 or float(np.dot(slopes[0], slopes[1])) <= 0:
        reasons.append("T0/T1 X-parallax slopes do not agree in sign")
    else:
        slope_delta = abs(slope_norms[0] - slope_norms[1]) / max(slope_norms)
        if slope_delta > 0.60:
            reasons.append(
                "T0/T1 X-parallax slope magnitudes differ by more than 60%"
            )
        elif slope_delta > 0.25:
            warnings.append(
                "T0/T1 X-parallax slope magnitudes differ by more than 25%"
            )

    panel_width = 480
    full_height = 270
    zoom_height = 180
    panels = []
    accepted_sequences = {
        tool: set(models[tool]["accepted_sequences"]) for tool in ("T0", "T1")
    }
    for path, frame, registration in zip(
        frame_paths, frames, registrations
    ):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FineNozzleError(
                f"fine-grid image {registration['seq']} cannot be decoded"
            )
        panel = image.copy()
        marker = np.asarray(registration["marker_center_px"])
        ring_center = np.asarray(registration["ring_center_px"])
        predicted = np.asarray(registration["predicted_tip_center_px"])
        center = np.asarray(registration["center_px"])
        color = (
            (0, 255, 0)
            if registration["seq"] in accepted_sequences[frame["tool"]]
            else (0, 0, 255)
        )
        cv2.drawMarker(
            panel,
            tuple(np.rint(marker).astype(int)),
            (0, 0, 255),
            cv2.MARKER_CROSS,
            24,
            3,
        )
        cv2.circle(
            panel,
            tuple(np.rint(ring_center).astype(int)),
            int(round(registration["ring_radius_px"])),
            (255, 255, 0),
            3,
        )
        cv2.drawMarker(
            panel,
            tuple(np.rint(predicted).astype(int)),
            (255, 0, 255),
            cv2.MARKER_CROSS,
            18,
            2,
        )
        roi_half = max(4, int(registration["tip_roi_size_px"]) // 2)
        cv2.rectangle(
            panel,
            tuple(np.rint(center - roi_half).astype(int)),
            tuple(np.rint(center + roi_half).astype(int)),
            color,
            3,
        )
        cv2.drawMarker(
            panel,
            tuple(np.rint(center).astype(int)),
            color,
            cv2.MARKER_TILTED_CROSS,
            26,
            3,
        )
        cv2.putText(
            panel,
            (
                f"{frame['tool']} X={frame['x_mm']} Z={frame['z_mm']} "
                f"corr={registration['minimum_correlation']:.3f}"
            ),
            (24, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
            cv2.LINE_AA,
        )
        full = cv2.resize(
            panel,
            (panel_width, full_height),
            interpolation=cv2.INTER_AREA,
        )
        zoom_size = max(
            96, int(round(2.5 * float(registration["ring_radius_px"])))
        )
        zoom, _origin = _crop(panel, ring_center, zoom_size)
        zoom = cv2.resize(
            zoom, (zoom_height, zoom_height), interpolation=cv2.INTER_CUBIC
        )
        zoom_strip = np.full((zoom_height, panel_width, 3), 18, np.uint8)
        zoom_strip[:, :zoom_height] = zoom
        lines = [
            "cyan: coarse ring only",
            "magenta: predicted tip",
            "green/red: matched tip ROI",
            (
                f"err={registration['tip_prediction_error_px']:.2f}px "
                f"scale={registration['template_scale']:.3f}"
            ),
        ]
        for line_index, line in enumerate(lines):
            cv2.putText(
                zoom_strip,
                line,
                (zoom_height + 12, 32 + line_index * 36),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (230, 230, 230),
                1,
                cv2.LINE_AA,
            )
        panels.append(cv2.vconcat([full, zoom_strip]))
    rows = []
    for start in range(0, len(panels), 5):
        row = panels[start : start + 5]
        while len(row) < 5:
            row.append(np.zeros_like(panels[0]))
        rows.append(cv2.hconcat(row))
    contact = cv2.vconcat(rows)
    contact_path = artifact_dir / "fine_nozzle_tip_registration_grid.jpg"
    cv2.imwrite(str(contact_path), contact)

    reference_panels = []
    for tool in ("T0", "T1"):
        record = tool_references[tool]
        index = int(record["reference_seq"])
        registration = registrations[index]
        image = cv2.imread(str(frame_paths[index]), cv2.IMREAD_COLOR)
        if image is None:
            raise FineNozzleError(
                f"fine-grid image {index} cannot be decoded"
            )
        ring_center = np.asarray(registration["ring_center_px"])
        center = np.asarray(registration["center_px"])
        radius = float(registration["ring_radius_px"])
        cv2.circle(
            image,
            tuple(np.rint(ring_center).astype(int)),
            int(round(radius)),
            (255, 255, 0),
            3,
        )
        half = int(registration["tip_roi_size_px"]) // 2
        cv2.rectangle(
            image,
            tuple(np.rint(center - half).astype(int)),
            tuple(np.rint(center + half).astype(int)),
            (0, 255, 0),
            3,
        )
        cv2.drawMarker(
            image,
            tuple(np.rint(center).astype(int)),
            (0, 255, 0),
            cv2.MARKER_TILTED_CROSS,
            20,
            2,
        )
        crop, _origin = _crop(image, ring_center, int(round(2.6 * radius)))
        crop = cv2.resize(crop, (520, 520), interpolation=cv2.INTER_CUBIC)
        cv2.putText(
            crop,
            f"{tool}: small nozzle-tip ROI; outer ring is locator only",
            (18, 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.60,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        reference_panels.append(crop)
    reference_contact = cv2.hconcat(reference_panels)
    reference_path = artifact_dir / "fine_nozzle_tip_references.jpg"
    cv2.imwrite(str(reference_path), reference_contact)

    model_plot = np.full((760, 1280, 3), 24, np.uint8)
    colors = {"T0": (0, 255, 255), "T1": (255, 128, 255)}
    for row, tool in enumerate(("T0", "T1")):
        y_base = 250 + row * 320
        model = models[tool]
        cv2.putText(
            model_plot,
            (
                f"{tool}: tip ROI={tool_references[tool]['template_size_px']} px, "
                f"fit RMS={models[tool]['position_fit_rms_px']:.3f} px, "
                f"Z0 bed-vector residual="
                f"{vector_comparison_at_z0[tool]['residual_magnitude_px_per_mm']:.3f} px/mm"
            ),
            (40, y_base - 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            colors[tool],
            2,
            cv2.LINE_AA,
        )
        bed_norm = float(np.linalg.norm(bed_x_fiducial))
        for z in np.linspace(1.0, 9.0, 161):
            vector = _x_vector(model, fiducial_x, float(z))
            x = int(round(100 + 120 * (z - 1.0)))
            y = int(round(y_base - 80 * (np.linalg.norm(vector) - bed_norm)))
            cv2.circle(model_plot, (x, y), 2, colors[tool], -1)
        cv2.line(model_plot, (100, y_base), (1060, y_base), (100, 100, 100), 1)
        cv2.putText(
            model_plot,
            (
                "gray line: measured fiducial X-vector magnitude at "
                f"X={fiducial_x:.3f}, Z={fiducial_plane_z:.3f}"
            ),
            (100, y_base + 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (150, 150, 150),
            1,
            cv2.LINE_AA,
        )
    plot_path = artifact_dir / "fine_nozzle_projection_model.jpg"
    cv2.imwrite(str(plot_path), model_plot)

    return _finite(
        {
            "accepted": not reasons,
            "reasons": reasons,
            "warnings": warnings,
            "registrations": registrations,
            "models": models,
            "tip_tracking": {
                tool: {
                    "marker_to_ring_delta_px": ring_deltas[tool],
                    "ring_delta_spread_px": ring_spreads[tool],
                    "ring_detection_count": len(ring_tracks[tool]),
                    "tip_to_ring_delta_px": tip_deltas[tool],
                    "tip_delta_spread_px": tip_spreads[tool],
                    "tip_detection_count": len(tip_tracks[tool]),
                    "tip_roi_size_px": tool_references[tool][
                        "template_size_px"
                    ],
                    "reference_seq": tool_references[tool]["reference_seq"],
                }
                for tool in ("T0", "T1")
            },
            "fiducial_reference_printer_xy_mm": fiducial_reference_xy,
            "fiducial_reference_pixel_at_fine_capture_px":
                fiducial_reference_pixel,
            "fiducial_x_vector_at_fine_capture_px_per_mm":
                bed_x_fiducial,
            "fiducial_plane_printer_z_mm": fiducial_plane_z,
            "fine_capture_y_mm": float(reference["fine_capture_y_mm"]),
            "image_y_axis_vector_px_per_mm": image_y_vector,
            "vector_comparison_at_commanded_z0": vector_comparison_at_z0,
            "cross_tool_tip_offset_at_reference": {
                "commanded_x_mm": cross_tool_reference_x,
                "commanded_z_mm": cross_tool_reference_z,
                "offset_px": cross_tool_reference_offset,
            },
            "artifacts": {
                "fine_nozzle_tip_registration_grid": _artifact(contact_path),
                "fine_nozzle_tip_references": _artifact(reference_path),
                "fine_nozzle_projection_model": _artifact(plot_path),
            },
        }
    )
