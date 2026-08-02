#!/usr/bin/env python3
"""Shared four-ring fiducial detection for nozzle-camera vision analyzers."""

from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

EXPECTED_EDGE_LENGTH_PX = 80.0
EDGE_LENGTH_TOLERANCE_FRACTION = 0.5
EXPECTED_RIGHT_EDGE_ANGLE_DEG = -5.0
EXPECTED_UP_EDGE_ANGLE_DEG = EXPECTED_RIGHT_EDGE_ANGLE_DEG - 90.0
EDGE_ANGLE_TOLERANCE_DEG = 4.0
FOURTH_POINT_TOLERANCE_PX = 7.0
MAX_RADIUS_RATIO = 2.0


class FourFiducialError(ValueError):
    pass


def order_quad(points: np.ndarray) -> np.ndarray:
    order = np.argsort(points[:, 1])
    top = points[order[:2]][np.argsort(points[order[:2], 0])]
    bottom = points[order[2:]][np.argsort(points[order[2:], 0])]
    return np.asarray([top[0], top[1], bottom[0], bottom[1]], dtype=np.float64)


def quad_geometry(points: np.ndarray) -> tuple[float, dict[str, float]] | None:
    ordered = order_quad(points)
    tl, tr, bl, br = ordered
    lengths = np.asarray(
        [
            np.linalg.norm(tr - tl),
            np.linalg.norm(br - bl),
            np.linalg.norm(bl - tl),
            np.linalg.norm(br - tr),
        ],
        dtype=np.float64,
    )
    mean_length = float(np.mean(lengths))
    if mean_length <= 0.0:
        return None
    if float(np.min(lengths)) < 0.45 * mean_length:
        return None
    if float(np.max(lengths)) > 1.75 * mean_length:
        return None
    diagonal_midpoint_error = float(np.linalg.norm((tl + br) * 0.5 - (tr + bl) * 0.5))
    if diagonal_midpoint_error > 0.28 * mean_length:
        return None
    right = tr - tl
    down = bl - tl
    area = abs(float(right[0] * down[1] - right[1] * down[0]))
    if area < 0.25 * mean_length * mean_length:
        return None
    opposite_error = float(
        abs(lengths[0] - lengths[1]) + abs(lengths[2] - lengths[3])
    ) / (2.0 * mean_length)
    side_balance = float(abs(np.mean(lengths[:2]) - np.mean(lengths[2:]))) / mean_length
    if side_balance > 0.22:
        return None
    geometry_score = 120.0 * (
        1.0
        - min(
            1.0,
            opposite_error + side_balance + diagonal_midpoint_error / mean_length,
        )
    )
    return geometry_score, {
        "mean_side_px": mean_length,
        "opposite_error_fraction": opposite_error,
        "side_balance_fraction": side_balance,
        "diagonal_midpoint_error_px": diagonal_midpoint_error,
        "area_px2": area,
    }


def _angle_deg(vector: np.ndarray) -> float:
    return math.degrees(math.atan2(vector[1], vector[0]))


def _angle_error_deg(angle: float, expected: float) -> float:
    return abs((angle - expected + 180.0) % 360.0 - 180.0)


def find_four_fiducials(
    candidates: list[dict[str, Any]],
    expected_edge_length_px: float = EXPECTED_EDGE_LENGTH_PX,
) -> list[dict[str, Any]]:
    centers = np.asarray(
        [candidate["center_px"] for candidate in candidates],
        dtype=np.float64,
    )
    radii = np.asarray(
        [candidate["radius_px"] for candidate in candidates],
        dtype=np.float64,
    )
    side_min = expected_edge_length_px * (1.0 - EDGE_LENGTH_TOLERANCE_FRACTION)
    side_max = expected_edge_length_px * (1.0 + EDGE_LENGTH_TOLERANCE_FRACTION)
    order_x = np.argsort(centers[:, 0])
    right_edges = []
    for position, left_index in enumerate(order_x[:-1]):
        left = centers[left_index]
        for right_index in order_x[position + 1 :]:
            right = centers[right_index]
            edge = right - left
            if edge[0] > side_max:
                break
            length = float(np.linalg.norm(edge))
            if not side_min <= length <= side_max:
                continue
            angle_error = _angle_error_deg(
                _angle_deg(edge),
                EXPECTED_RIGHT_EDGE_ANGLE_DEG,
            )
            if angle_error <= EDGE_ANGLE_TOLERANCE_DEG:
                right_edges.append(
                    (int(left_index), int(right_index), length, angle_error)
                )
    if not right_edges:
        raise FourFiducialError("no right-edge fiducial pairs found")

    best = None
    for (
        bottom_left_index,
        bottom_right_index,
        right_length,
        right_angle_error,
    ) in right_edges:
        bottom_left = centers[bottom_left_index]
        bottom_right = centers[bottom_right_index]
        for top_left_index, top_left in enumerate(centers):
            if top_left_index in {bottom_left_index, bottom_right_index}:
                continue
            up_edge = top_left - bottom_left
            up_length = float(np.linalg.norm(up_edge))
            if not side_min <= up_length <= side_max:
                continue
            up_angle_error = _angle_error_deg(
                _angle_deg(up_edge),
                EXPECTED_UP_EDGE_ANGLE_DEG,
            )
            if up_angle_error > EDGE_ANGLE_TOLERANCE_DEG:
                continue
            predicted_top_right = bottom_right + up_edge
            errors = np.linalg.norm(centers - predicted_top_right, axis=1)
            errors[[bottom_left_index, bottom_right_index, top_left_index]] = np.inf
            top_right_index = int(np.argmin(errors))
            fourth_error = float(errors[top_right_index])
            if fourth_error > FOURTH_POINT_TOLERANCE_PX:
                continue
            selected_indices = np.asarray(
                [
                    top_left_index,
                    top_right_index,
                    bottom_left_index,
                    bottom_right_index,
                ]
            )
            selected_radii = radii[selected_indices]
            if np.max(selected_radii) / np.min(selected_radii) > MAX_RADIUS_RATIO:
                continue
            score = (
                abs(right_length - expected_edge_length_px)
                + abs(up_length - expected_edge_length_px)
                + abs(right_length - up_length)
                + right_angle_error
                + up_angle_error
                + fourth_error
            )
            if best is None or score < best[0]:
                best = score, selected_indices
    if best is None:
        raise FourFiducialError("no four-fiducial pattern found")
    return [candidates[index] for index in best[1]]


def detect_four_fiducials(
    image: np.ndarray,
) -> dict[str, Any]:
    """Find and order the 8 x 8 mm four-ring patch in a camera frame."""

    height, width = image.shape[:2]
    scale = min(width / 1920.0, height / 1080.0)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 1.2)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.15,
        minDist=20 * scale,
        param1=90,
        param2=16,
        minRadius=max(1, int(round(7 * scale))),
        maxRadius=max(2, int(round(18 * scale))),
    )
    if circles is None:
        raise FourFiducialError("no circular fiducial candidates detected")

    candidates = [
        {
            "center_px": [float(x), float(y)],
            "radius_px": float(radius),
        }
        for x, y, radius in circles[0]
    ]
    deduplicated: list[dict[str, Any]] = []
    for candidate in candidates:
        center = np.asarray(candidate["center_px"], dtype=np.float64)
        if any(
            np.linalg.norm(center - np.asarray(item["center_px"])) < 10.0 * scale
            for item in deduplicated
        ):
            continue
        deduplicated.append(candidate)
        if len(deduplicated) >= 110:
            break
    if len(deduplicated) < 4:
        raise FourFiducialError(
            f"only {len(deduplicated)} independent ring candidates detected"
        )

    selected = find_four_fiducials(
        deduplicated,
        expected_edge_length_px=EXPECTED_EDGE_LENGTH_PX * scale,
    )
    centers = np.asarray(
        [candidate["center_px"] for candidate in selected],
        dtype=np.float64,
    )
    geometry = quad_geometry(centers)
    if geometry is None:
        raise FourFiducialError("selected four-fiducial geometry is invalid")
    _geometry_score, geometry_details = geometry
    x0, y0 = np.min(centers, axis=0)
    x1, y1 = np.max(centers, axis=0)
    pad = max(12.0 * scale, 0.35 * geometry_details["mean_side_px"])
    roi = [
        max(0, int(math.floor(x0 - pad))),
        max(0, int(math.floor(y0 - pad))),
        min(width, int(math.ceil(x1 + pad))),
        min(height, int(math.ceil(y1 + pad))),
    ]
    return {
        "centers_px": centers.tolist(),
        "radii_px": [candidate["radius_px"] for candidate in selected],
        "roi_px": roi,
        "candidate_count": len(deduplicated),
        "candidates": deduplicated,
    }
