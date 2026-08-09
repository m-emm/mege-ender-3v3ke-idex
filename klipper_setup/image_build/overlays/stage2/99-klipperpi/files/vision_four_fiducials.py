#!/usr/bin/env python3
"""Locate the coded fiducial patch and detect its four ring fiducials."""

from __future__ import annotations

import itertools
import math
from typing import Any

import cv2
import numpy as np

PATCH_SIZE_MM = 14.0
FIDUCIAL_SPACING_MM = 8.0
LOCATOR_MARKER_ID = 42
LOCATOR_MARKER_SIDE_MM = 3.8
LOCATOR_MARKER_CENTER_MM = PATCH_SIZE_MM / 2.0

EXPECTED_EDGE_LENGTH_PX = 80.0
EDGE_LENGTH_TOLERANCE_FRACTION = 0.5
FOURTH_POINT_TOLERANCE_PX = 7.0
MAX_RADIUS_RATIO = 2.0
MAX_SIDE_BALANCE_FRACTION = 0.18
MIN_LOCATOR_MARKER_SIDE_PX = 20.0
MAX_PATCH_OUTSIDE_FRACTION = 0.02
MAX_EXHAUSTIVE_QUARTET_CANDIDATES = 32

_PATCH_CORNERS_MM = np.asarray(
    [
        [0.0, 0.0],
        [PATCH_SIZE_MM, 0.0],
        [PATCH_SIZE_MM, PATCH_SIZE_MM],
        [0.0, PATCH_SIZE_MM],
    ],
    dtype=np.float32,
)
_LOCATOR_CORNERS_MM = np.asarray(
    [
        [
            LOCATOR_MARKER_CENTER_MM - LOCATOR_MARKER_SIDE_MM / 2.0,
            LOCATOR_MARKER_CENTER_MM - LOCATOR_MARKER_SIDE_MM / 2.0,
        ],
        [
            LOCATOR_MARKER_CENTER_MM + LOCATOR_MARKER_SIDE_MM / 2.0,
            LOCATOR_MARKER_CENTER_MM - LOCATOR_MARKER_SIDE_MM / 2.0,
        ],
        [
            LOCATOR_MARKER_CENTER_MM + LOCATOR_MARKER_SIDE_MM / 2.0,
            LOCATOR_MARKER_CENTER_MM + LOCATOR_MARKER_SIDE_MM / 2.0,
        ],
        [
            LOCATOR_MARKER_CENTER_MM - LOCATOR_MARKER_SIDE_MM / 2.0,
            LOCATOR_MARKER_CENTER_MM + LOCATOR_MARKER_SIDE_MM / 2.0,
        ],
    ],
    dtype=np.float32,
)
_FIDUCIAL_CENTERS_MM = np.asarray(
    [[3.0, 3.0], [11.0, 3.0], [3.0, 11.0], [11.0, 11.0]],
    dtype=np.float32,
)


class FourFiducialError(ValueError):
    pass


def _angle_deg(vector: np.ndarray) -> float:
    return math.degrees(math.atan2(float(vector[1]), float(vector[0])))


def _cross_2d(left: np.ndarray, right: np.ndarray) -> float:
    return float(left[0] * right[1] - left[1] * right[0])


def order_quad(
    points: np.ndarray,
    reference_centers_px: np.ndarray | None = None,
) -> np.ndarray:
    """Return TL, TR, BL, BR using an optional oriented patch reference."""

    points = np.asarray(points, dtype=np.float64)
    if points.shape != (4, 2):
        raise FourFiducialError("a quadrilateral requires exactly four points")
    if reference_centers_px is not None:
        reference = np.asarray(reference_centers_px, dtype=np.float64)
        if reference.shape != (4, 2):
            raise FourFiducialError(
                "fiducial orientation reference must contain four points"
            )
        permutation = min(
            itertools.permutations(range(4)),
            key=lambda candidate: sum(
                np.linalg.norm(points[candidate[index]] - reference[index])
                for index in range(4)
            ),
        )
        return points[list(permutation)]

    order = np.argsort(points[:, 1])
    top = points[order[:2]][np.argsort(points[order[:2], 0])]
    bottom = points[order[2:]][np.argsort(points[order[2:], 0])]
    return np.asarray([top[0], top[1], bottom[0], bottom[1]], dtype=np.float64)


def _geometry_details(ordered: np.ndarray) -> tuple[float, dict[str, Any]] | None:
    tl, tr, bl, br = ordered
    edges = np.asarray(
        [tr - tl, br - tr, bl - br, tl - bl],
        dtype=np.float64,
    )
    lengths = np.linalg.norm(edges, axis=1)
    mean_length = float(np.mean(lengths))
    if mean_length <= 0.0:
        return None
    if float(np.min(lengths)) < 0.55 * mean_length:
        return None
    if float(np.max(lengths)) > 1.45 * mean_length:
        return None

    diagonal_midpoint_error = float(np.linalg.norm((tl + br) * 0.5 - (tr + bl) * 0.5))
    if diagonal_midpoint_error > 0.30 * mean_length:
        return None

    normalized_edges = edges / lengths[:, None]
    parallel_error = max(
        abs(_cross_2d(normalized_edges[0], normalized_edges[2])),
        abs(_cross_2d(normalized_edges[1], normalized_edges[3])),
    )
    orthogonality_error = max(
        abs(float(np.dot(normalized_edges[0], normalized_edges[1]))),
        abs(float(np.dot(normalized_edges[1], normalized_edges[2]))),
        abs(float(np.dot(normalized_edges[2], normalized_edges[3]))),
        abs(float(np.dot(normalized_edges[3], normalized_edges[0]))),
    )
    if parallel_error > 0.35 or orthogonality_error > 0.45:
        return None

    opposite_error = float(
        abs(lengths[0] - lengths[2]) + abs(lengths[1] - lengths[3])
    ) / (2.0 * mean_length)
    side_balance = (
        float(abs(np.mean(lengths[[0, 2]]) - np.mean(lengths[[1, 3]]))) / mean_length
    )
    if side_balance > MAX_SIDE_BALANCE_FRACTION:
        return None
    shape_error = (
        opposite_error
        + side_balance
        + diagonal_midpoint_error / mean_length
        + parallel_error
        + orthogonality_error
    )
    score = 120.0 * max(0.0, 1.0 - min(1.0, shape_error))
    return score, {
        "side_lengths_px": lengths.tolist(),
        "mean_side_px": mean_length,
        "opposite_error_fraction": opposite_error,
        "side_balance_fraction": side_balance,
        "diagonal_midpoint_error_px": diagonal_midpoint_error,
        "parallel_error": parallel_error,
        "orthogonality_error": orthogonality_error,
        "right_edge_angle_deg": _angle_deg(edges[0]),
        "down_edge_angle_deg": _angle_deg(-edges[3]),
        "geometry_score": score,
    }


def quad_geometry(
    points: np.ndarray,
    *,
    reference_centers_px: np.ndarray | None = None,
) -> tuple[float, dict[str, Any]] | None:
    """Score square geometry without using an absolute angle prior."""

    points = np.asarray(points, dtype=np.float64)
    if points.shape != (4, 2):
        return None
    ordered = (
        order_quad(points, reference_centers_px)
        if reference_centers_px is not None
        else order_quad(points)
    )
    return _geometry_details(ordered)


def find_four_fiducials(
    candidates: list[dict[str, Any]],
    expected_edge_length_px: float = EXPECTED_EDGE_LENGTH_PX,
    *,
    reference_centers_px: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    """Select a square of four circles using geometry only."""

    if len(candidates) < 4:
        raise FourFiducialError("fewer than four circular fiducial candidates")
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

    best: tuple[float, np.ndarray] | None = None
    if len(candidates) <= MAX_EXHAUSTIVE_QUARTET_CANDIDATES:
        quartet_indices = itertools.combinations(range(len(candidates)), 4)
    else:
        # Keep the old bounded graph search for unusually noisy full-frame
        # legacy detection.  Locator ROIs are normally small enough for the
        # complete quartet search above, which avoids assuming that a square's
        # diagonal is also a side-length neighbor.
        neighbors = [set() for _ in candidates]
        pairs: list[tuple[int, int]] = []
        for left_index, right_index in itertools.combinations(
            range(len(candidates)), 2
        ):
            length = float(np.linalg.norm(centers[right_index] - centers[left_index]))
            if side_min <= length <= side_max:
                neighbors[left_index].add(right_index)
                neighbors[right_index].add(left_index)
                pairs.append((left_index, right_index))
        quartet_indices = (
            (left_index, right_index, other_a, other_b)
            for left_index, right_index in pairs
            for other_a, other_b in itertools.combinations(
                sorted(neighbors[left_index] & neighbors[right_index]), 2
            )
        )

    for indices_tuple in quartet_indices:
        indices = list(indices_tuple)
        points = centers[indices]
        geometry = quad_geometry(points, reference_centers_px=reference_centers_px)
        if geometry is None:
            continue
        _geometry_score, details = geometry
        if not all(
            side_min <= float(length) <= side_max
            for length in details["side_lengths_px"]
        ):
            continue
        selected_radii = radii[indices]
        if np.max(selected_radii) / np.min(selected_radii) > MAX_RADIUS_RATIO:
            continue
        score = (
            abs(float(details["mean_side_px"]) - expected_edge_length_px)
            + float(details["opposite_error_fraction"]) * expected_edge_length_px
            + float(details["diagonal_midpoint_error_px"])
            + float(details["parallel_error"]) * expected_edge_length_px
            + float(details["orthogonality_error"]) * expected_edge_length_px
        )
        if best is None or score < best[0]:
            ordered = order_quad(points, reference_centers_px)
            ordered_indices = [
                indices[int(np.where(np.all(points == point, axis=1))[0][0])]
                for point in ordered
            ]
            best = score, np.asarray(ordered_indices, dtype=int)

    if best is None:
        raise FourFiducialError("no four-fiducial square geometry found")
    return [candidates[index] for index in best[1]]


def _aruco_detector() -> Any:
    aruco = getattr(cv2, "aruco", None)
    if aruco is None:
        raise FourFiducialError("OpenCV ArUco support is unavailable")
    dictionary = aruco.getPredefinedDictionary(aruco.DICT_4X4_50)
    # OpenCV 4.6 on the Raspberry Pi exposes both APIs, but the newer
    # constructor can segfault inside detectMarkers.  Prefer the legacy
    # factory when available and keep detector threading bounded on the Pi.
    cv2.setNumThreads(1)
    if hasattr(aruco, "DetectorParameters_create"):
        parameters = aruco.DetectorParameters_create()
    else:
        parameters = aruco.DetectorParameters()
    if hasattr(parameters, "cornerRefinementMethod"):
        parameters.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
    if hasattr(aruco, "ArucoDetector"):
        return aruco.ArucoDetector(dictionary, parameters)
    return dictionary, parameters


def _detect_aruco(image: np.ndarray) -> tuple[list[np.ndarray], np.ndarray | None]:
    detector = _aruco_detector()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if isinstance(detector, tuple):
        aruco = cv2.aruco
        corners, ids, _rejected = aruco.detectMarkers(
            gray, detector[0], parameters=detector[1]
        )
    else:
        corners, ids, _rejected = detector.detectMarkers(gray)
    return corners, ids


def _project_points(homography: np.ndarray, points: np.ndarray) -> np.ndarray:
    return (
        cv2.perspectiveTransform(
            np.asarray(points, dtype=np.float32).reshape(-1, 1, 2), homography
        )
        .reshape(-1, 2)
        .astype(np.float64)
    )


def locate_fiducial_patch(image: np.ndarray) -> dict[str, Any]:
    """Locate the coded patch in a full camera frame."""

    corners, ids = _detect_aruco(image)
    if ids is None:
        raise FourFiducialError("no ArUco locator candidates detected")

    candidates = []
    for marker_corners, marker_id in zip(corners, ids.reshape(-1)):
        if int(marker_id) != LOCATOR_MARKER_ID:
            continue
        marker = np.asarray(marker_corners, dtype=np.float64).reshape(4, 2)
        side_lengths = np.linalg.norm(np.roll(marker, -1, axis=0) - marker, axis=1)
        marker_side_px = float(np.mean(side_lengths))
        if marker_side_px < MIN_LOCATOR_MARKER_SIDE_PX:
            continue
        if float(np.max(side_lengths) / np.min(side_lengths)) > 1.8:
            continue
        homography = cv2.getPerspectiveTransform(
            _LOCATOR_CORNERS_MM,
            marker.astype(np.float32),
        )
        patch_corners = _project_points(homography, _PATCH_CORNERS_MM)
        height, width = image.shape[:2]
        outside = np.logical_or(
            np.logical_or(patch_corners[:, 0] < 0.0, patch_corners[:, 0] >= width),
            np.logical_or(patch_corners[:, 1] < 0.0, patch_corners[:, 1] >= height),
        )
        if float(np.mean(outside)) > MAX_PATCH_OUTSIDE_FRACTION:
            continue
        expected_centers = _project_points(homography, _FIDUCIAL_CENTERS_MM)
        x0 = max(0, int(math.floor(np.min(patch_corners[:, 0])) - 2))
        y0 = max(0, int(math.floor(np.min(patch_corners[:, 1])) - 2))
        x1 = min(width, int(math.ceil(np.max(patch_corners[:, 0])) + 3))
        y1 = min(height, int(math.ceil(np.max(patch_corners[:, 1])) + 3))
        candidates.append(
            {
                "marker_id": int(marker_id),
                "marker_corners_px": marker.tolist(),
                "marker_side_px": marker_side_px,
                "patch_corners_px": patch_corners.tolist(),
                "expected_fiducial_centers_px": expected_centers.tolist(),
                "patch_to_image_homography": homography.tolist(),
                "roi_px": [x0, y0, x1, y1],
            }
        )

    if not candidates:
        raise FourFiducialError(
            f"no usable ArUco locator with marker ID {LOCATOR_MARKER_ID}"
        )
    return max(candidates, key=lambda candidate: candidate["marker_side_px"])


def _detect_circle_candidates(
    image: np.ndarray,
    *,
    roi_px: list[int] | None = None,
    patch_corners_px: np.ndarray | None = None,
    expected_edge_length_px: float = EXPECTED_EDGE_LENGTH_PX,
) -> tuple[list[dict[str, Any]], list[int]]:
    height, width = image.shape[:2]
    if roi_px is None:
        x0, y0, x1, y1 = 0, 0, width, height
    else:
        x0, y0, x1, y1 = roi_px
    crop = image[y0:y1, x0:x1]
    scale = expected_edge_length_px / EXPECTED_EDGE_LENGTH_PX
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 1.2)
    if patch_corners_px is not None:
        mask = np.zeros(gray.shape, dtype=np.uint8)
        polygon = np.rint(np.asarray(patch_corners_px) - [x0, y0]).astype(np.int32)
        cv2.fillConvexPoly(mask, polygon, 255)
        blurred = cv2.bitwise_and(blurred, blurred, mask=mask)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.15,
        minDist=max(8.0, 20.0 * scale),
        param1=90,
        param2=16,
        minRadius=max(1, int(round(7 * scale))),
        maxRadius=max(2, int(round(18 * scale))),
    )
    if circles is None:
        raise FourFiducialError("no circular fiducial candidates detected")

    candidates = []
    for x, y, radius in circles[0]:
        point = np.asarray([float(x + x0), float(y + y0)])
        if (
            patch_corners_px is not None
            and cv2.pointPolygonTest(
                np.asarray(patch_corners_px, dtype=np.float32), tuple(point), False
            )
            < 0
        ):
            continue
        candidates.append(
            {
                "center_px": point.tolist(),
                "radius_px": float(radius),
            }
        )

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
    return deduplicated, [x0, y0, x1, y1]


def _detect_legacy(image: np.ndarray) -> dict[str, Any]:
    height, width = image.shape[:2]
    scale = min(width / 1920.0, height / 1080.0)
    candidates, _full_roi = _detect_circle_candidates(
        image,
        expected_edge_length_px=EXPECTED_EDGE_LENGTH_PX * scale,
    )
    selected = find_four_fiducials(
        candidates,
        expected_edge_length_px=EXPECTED_EDGE_LENGTH_PX * scale,
    )
    centers = np.asarray([candidate["center_px"] for candidate in selected])
    geometry = quad_geometry(centers, reference_centers_px=centers)
    if geometry is None:
        raise FourFiducialError("selected four-fiducial geometry is invalid")
    _geometry_score, details = geometry
    pad = max(12.0 * scale, 0.35 * float(details["mean_side_px"]))
    x0, y0 = np.min(centers, axis=0)
    x1, y1 = np.max(centers, axis=0)
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
        "candidate_count": len(candidates),
        "candidates": candidates,
        "right_edge_angle_deg": details["right_edge_angle_deg"],
        "down_edge_angle_deg": details["down_edge_angle_deg"],
        "geometry": details,
        "locator": None,
    }


def detect_four_fiducials(
    image: np.ndarray,
    *,
    require_locator: bool = True,
) -> dict[str, Any]:
    """Locate and order the four-ring patch in a camera frame."""

    try:
        locator = locate_fiducial_patch(image)
    except FourFiducialError:
        if not require_locator:
            return _detect_legacy(image)
        raise

    patch_corners = np.asarray(locator["patch_corners_px"], dtype=np.float64)
    expected_centers = np.asarray(
        locator["expected_fiducial_centers_px"], dtype=np.float64
    )
    expected_edge = float(
        np.mean(
            [
                np.linalg.norm(expected_centers[1] - expected_centers[0]),
                np.linalg.norm(expected_centers[3] - expected_centers[2]),
                np.linalg.norm(expected_centers[2] - expected_centers[0]),
                np.linalg.norm(expected_centers[3] - expected_centers[1]),
            ]
        )
    )
    candidates, roi = _detect_circle_candidates(
        image,
        roi_px=locator["roi_px"],
        patch_corners_px=patch_corners,
        expected_edge_length_px=expected_edge,
    )
    selected = find_four_fiducials(
        candidates,
        expected_edge_length_px=expected_edge,
        reference_centers_px=expected_centers,
    )
    centers = np.asarray([candidate["center_px"] for candidate in selected])
    geometry = quad_geometry(centers, reference_centers_px=expected_centers)
    if geometry is None:
        raise FourFiducialError("selected four-fiducial geometry is invalid")
    _geometry_score, details = geometry
    return {
        "centers_px": centers.tolist(),
        "radii_px": [candidate["radius_px"] for candidate in selected],
        "roi_px": roi,
        "patch_corners_px": patch_corners.tolist(),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "right_edge_angle_deg": details["right_edge_angle_deg"],
        "down_edge_angle_deg": details["down_edge_angle_deg"],
        "geometry": details,
        "locator": locator,
    }
