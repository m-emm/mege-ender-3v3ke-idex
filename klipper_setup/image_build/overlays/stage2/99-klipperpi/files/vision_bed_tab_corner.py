#!/usr/bin/env python3
"""Locate the bed-tab corner and refine it through duplicate registration."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from vision_bed_tab_y_scale import (
    _cluster_horizontal_segments,
    _detect_horizontal_segments,
    _detect_line_segments,
    _gray,
    _representations,
    _subpixel_peak,
    _tab_side_support,
)
from vision_calibration_graph import sha256_file


LOCALIZER = {"kind": "bed_tab_corner", "version": 1}
EXPECTED_RADIUS_DIAGONAL_FRACTION = 0.08
CORNER_ROI_X_RADIUS_FRACTION = 0.07
CORNER_ROI_Y_RADIUS_FRACTION = 0.10
SEARCH_X_FRACTION = 0.025
SEARCH_Y_FRACTION = 0.025
LINE_CONFIRMATION_DIAGONAL_FRACTION = 0.012
MIN_USABLE_FRAMES = 4
MIN_LINE_CONFIRMATIONS = 3
MIN_CORRELATION = 0.75
MIN_MEDIAN_CORRELATION = 0.90
WARN_REPEATABILITY_PX = 1.0
MAX_REPEATABILITY_PX = 5.0
WARN_REGISTRATION_DISAGREEMENT_PX = 0.75
MAX_REGISTRATION_DISAGREEMENT_PX = 4.0
MAX_REPRESENTATION_SPREAD_PX = 1.5


def _line_intersection(
    horizontal: dict[str, Any], side: dict[str, float]
) -> tuple[float, float] | None:
    denominator = side["y1"] - side["y0"]
    if abs(denominator) < 1.0e-9:
        return None
    y = float(horizontal["y"])
    x = side["x0"] + (y - side["y0"]) * (side["x1"] - side["x0"]) / denominator
    return float(x), y


def _detect_candidates(gray: np.ndarray) -> list[dict[str, Any]]:
    segments = _detect_line_segments(gray)
    horizontal = _cluster_horizontal_segments(
        _detect_horizontal_segments(gray, segments),
        gray.shape,
    )
    candidates = []
    for cluster in horizontal:
        side = _tab_side_support(cluster, segments, gray.shape)
        if side is None:
            continue
        corner = _line_intersection(cluster, side)
        if corner is None:
            continue
        score = (
            float(cluster["span_fraction"]) * gray.shape[1]
            + math.log1p(max(0.0, side["geometry_score"])) * 20.0
        )
        candidates.append(
            {
                "candidate_id": f"corner_{len(candidates):02d}",
                "corner_px": [corner[0], corner[1]],
                "horizontal_line_px": [
                    float(cluster["x0"]),
                    float(cluster["y"]),
                    float(cluster["x1"]),
                ],
                "tab_side": side,
                "span_fraction": float(cluster["span_fraction"]),
                "geometry_score": float(score),
            }
        )
    return candidates


def _clip_rect(
    corner: tuple[float, float], shape: tuple[int, int]
) -> tuple[int, int, int, int]:
    height, width = shape
    x_radius = max(24, int(round(width * CORNER_ROI_X_RADIUS_FRACTION)))
    y_radius = max(24, int(round(height * CORNER_ROI_Y_RADIUS_FRACTION)))
    left = max(0, int(round(corner[0])) - x_radius)
    right = min(width, int(round(corner[0])) + x_radius)
    top = max(0, int(round(corner[1])) - y_radius)
    bottom = min(height, int(round(corner[1])) + y_radius)
    if right - left < 32 or bottom - top < 32:
        raise ValueError("corner registration ROI is clipped")
    return left, top, right, bottom


def _register(
    source: np.ndarray,
    target: np.ndarray,
    source_rect: tuple[int, int, int, int],
    expected_target_top_left: tuple[float, float],
    search_x: int,
    search_y: int,
) -> tuple[tuple[float, float], float, bool]:
    source_left, source_top, source_right, source_bottom = source_rect
    template = source[source_top:source_bottom, source_left:source_right]
    template_height, template_width = template.shape
    expected_left, expected_top = expected_target_top_left
    search_left = max(0, int(math.floor(expected_left)) - search_x)
    search_top = max(0, int(math.floor(expected_top)) - search_y)
    search_right = min(
        target.shape[1],
        int(math.ceil(expected_left)) + template_width + search_x,
    )
    search_bottom = min(
        target.shape[0],
        int(math.ceil(expected_top)) + template_height + search_y,
    )
    search = target[search_top:search_bottom, search_left:search_right]
    if (
        template.shape[0] < 16
        or template.shape[1] < 16
        or search.shape[0] < template.shape[0]
        or search.shape[1] < template.shape[1]
    ):
        raise ValueError("corner registration search is clipped")
    response = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _minimum, correlation, _minimum_location, location = cv2.minMaxLoc(response)
    peak_x, peak_y = _subpixel_peak(response, location[0], location[1])
    matched_left = search_left + peak_x
    matched_top = search_top + peak_y
    boundary = location[0] in (0, response.shape[1] - 1) or location[1] in (
        0,
        response.shape[0] - 1,
    )
    return (
        (
            matched_left - source_left,
            matched_top - source_top,
        ),
        float(correlation),
        boundary,
    )


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _nearest_candidate(
    candidates: list[dict[str, Any]],
    expected: tuple[float, float],
    maximum_distance: float,
) -> tuple[dict[str, Any] | None, float]:
    if not candidates:
        return None, float("inf")
    ranked = sorted(
        (
            _distance(tuple(candidate["corner_px"]), expected),
            -candidate["geometry_score"],
            candidate,
        )
        for candidate in candidates
    )
    distance, _negative_score, candidate = ranked[0]
    if distance > maximum_distance:
        return None, float(distance)
    return candidate, float(distance)


def _draw_cross(
    image: np.ndarray,
    point: tuple[float, float],
    color: tuple[int, int, int],
    *,
    radius: int = 18,
    thickness: int = 3,
) -> None:
    x, y = (int(round(item)) for item in point)
    cv2.line(image, (x - radius, y), (x + radius, y), color, thickness, cv2.LINE_AA)
    cv2.line(image, (x, y - radius), (x, y + radius), color, thickness, cv2.LINE_AA)
    cv2.circle(image, (x, y), radius // 2, color, thickness, cv2.LINE_AA)


def _resize(image: np.ndarray, width: int) -> np.ndarray:
    scale = width / image.shape[1]
    return cv2.resize(image, (width, int(round(image.shape[0] * scale))))


def _draw_localization(
    image: np.ndarray,
    candidates: list[dict[str, Any]],
    selected: dict[str, Any] | None,
    expected: tuple[float, float],
    roi: tuple[int, int, int, int] | None,
    path: Path,
) -> None:
    canvas = image.copy()
    _draw_cross(canvas, expected, (255, 255, 0), radius=24)
    cv2.putText(
        canvas,
        "cyan: upstream Y-model prediction",
        (28, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 0),
        2,
        cv2.LINE_AA,
    )
    for candidate in candidates:
        chosen = candidate is selected
        color = (0, 230, 255) if chosen else (40, 40, 220)
        line = candidate["horizontal_line_px"]
        side = candidate["tab_side"]
        cv2.line(
            canvas,
            (int(round(line[0])), int(round(line[1]))),
            (int(round(line[2])), int(round(line[1]))),
            color,
            4 if chosen else 2,
            cv2.LINE_AA,
        )
        cv2.line(
            canvas,
            (int(round(side["x0"])), int(round(side["y0"]))),
            (int(round(side["x1"])), int(round(side["y1"]))),
            color,
            4 if chosen else 2,
            cv2.LINE_AA,
        )
        _draw_cross(canvas, tuple(candidate["corner_px"]), color)
        cv2.putText(
            canvas,
            candidate["candidate_id"] + (" selected" if chosen else ""),
            (
                int(round(candidate["corner_px"][0])) + 15,
                int(round(candidate["corner_px"][1])) - 15,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )
    if roi is not None:
        cv2.rectangle(
            canvas,
            (roi[0], roi[1]),
            (roi[2], roi[3]),
            (0, 230, 255),
            3,
        )
    cv2.imwrite(str(path), canvas)


def _draw_duplicates(
    images: list[np.ndarray],
    observations: list[dict[str, Any]],
    path: Path,
) -> None:
    panels = []
    for index, (image, observation) in enumerate(zip(images, observations)):
        canvas = image.copy()
        registered = observation.get("registered_corner_px")
        measured = observation.get("line_corner_px")
        if registered is not None:
            _draw_cross(canvas, tuple(registered), (255, 255, 0), radius=20)
        if measured is not None:
            _draw_cross(canvas, tuple(measured), (0, 230, 255), radius=13)
        cv2.putText(
            canvas,
            (
                f"duplicate {index}: corr={observation.get('correlation', 0):.4f} "
                f"residual={observation.get('line_registration_error_px')}"
            ),
            (24, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (40, 240, 240),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "cyan=registered, yellow=line intersection",
            (24, 76),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (40, 240, 240),
            2,
            cv2.LINE_AA,
        )
        panels.append(_resize(canvas, 640))
    blank = np.zeros_like(panels[0])
    while len(panels) < 6:
        panels.append(blank.copy())
    contact = np.vstack((np.hstack(panels[:3]), np.hstack(panels[3:6])))
    cv2.imwrite(str(path), contact)


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


def analyze(
    frame_paths: list[Path],
    output_dir: Path,
    *,
    expected_corner_px: list[float],
    localizer: dict[str, Any],
) -> dict[str, Any]:
    if localizer != LOCALIZER:
        raise ValueError("unsupported bed-tab corner localizer")
    if len(frame_paths) != 5:
        raise ValueError("bed-tab corner analysis requires five duplicates")
    if (
        not isinstance(expected_corner_px, list)
        or len(expected_corner_px) != 2
        or not all(isinstance(item, (int, float)) for item in expected_corner_px)
    ):
        raise ValueError("expected corner must contain two numeric pixel coordinates")
    output_dir.mkdir(parents=True, exist_ok=False)

    images = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in frame_paths]
    missing_frames = [index for index, image in enumerate(images) if image is None]
    if missing_frames:
        return {
            "accepted": False,
            "reasons": [f"undecodable duplicate frames: {missing_frames}"],
            "warnings": [],
            "missing_frames": missing_frames,
            "artifacts": {},
        }
    if any(image.shape != images[0].shape for image in images[1:]):
        return {
            "accepted": False,
            "reasons": ["duplicate image dimensions are inconsistent"],
            "warnings": [],
            "missing_frames": [],
            "artifacts": {},
        }

    gray = [_gray(image) for image in images]
    representations = [_representations(item) for item in gray]
    height, width = gray[0].shape
    diagonal = math.hypot(width, height)
    expected = (float(expected_corner_px[0]), float(expected_corner_px[1]))
    expected_radius = diagonal * EXPECTED_RADIUS_DIAGONAL_FRACTION
    candidates_by_frame = [_detect_candidates(item) for item in gray]
    selected, expected_distance = _nearest_candidate(
        candidates_by_frame[0],
        expected,
        expected_radius,
    )
    reasons: list[str] = []
    warnings: list[str] = []
    roi = None
    observations: list[dict[str, Any]] = []
    if selected is None:
        reasons.append(
            "no semantic bed-tab corner was found near the upstream Y-model prediction"
        )
    else:
        selected_corner = tuple(selected["corner_px"])
        roi = _clip_rect(selected_corner, gray[0].shape)
        search_x = max(8, int(round(width * SEARCH_X_FRACTION)))
        search_y = max(8, int(round(height * SEARCH_Y_FRACTION)))
        confirmation_radius = diagonal * LINE_CONFIRMATION_DIAGONAL_FRACTION
        for index in range(5):
            if index == 0:
                shift = (0.0, 0.0)
                correlation = 1.0
                representation_spread = 0.0
                direction_disagreement = 0.0
                boundary = False
            else:
                forward = {}
                correlations = {}
                boundaries = []
                for representation_name in ("gray", "clahe"):
                    (
                        forward[representation_name],
                        correlations[representation_name],
                        representation_boundary,
                    ) = _register(
                        representations[0][representation_name],
                        representations[index][representation_name],
                        roi,
                        (float(roi[0]), float(roi[1])),
                        search_x,
                        search_y,
                    )
                    boundaries.append(representation_boundary)
                representation_spread = _distance(forward["gray"], forward["clahe"])
                shift = (
                    (forward["gray"][0] + forward["clahe"][0]) / 2.0,
                    (forward["gray"][1] + forward["clahe"][1]) / 2.0,
                )
                target_rect = (
                    int(round(roi[0] + shift[0])),
                    int(round(roi[1] + shift[1])),
                    int(round(roi[2] + shift[0])),
                    int(round(roi[3] + shift[1])),
                )
                reverse_shift, reverse_correlation, reverse_boundary = _register(
                    representations[index]["gray"],
                    representations[0]["gray"],
                    target_rect,
                    (float(roi[0]), float(roi[1])),
                    search_x,
                    search_y,
                )
                reverse_as_forward = (-reverse_shift[0], -reverse_shift[1])
                direction_disagreement = _distance(shift, reverse_as_forward)
                shift = (
                    (shift[0] + reverse_as_forward[0]) / 2.0,
                    (shift[1] + reverse_as_forward[1]) / 2.0,
                )
                correlation = min(
                    correlations["gray"],
                    correlations["clahe"],
                    reverse_correlation,
                )
                boundary = any(boundaries) or reverse_boundary

            registered_corner = (
                selected_corner[0] + shift[0],
                selected_corner[1] + shift[1],
            )
            line_candidate, line_error = _nearest_candidate(
                candidates_by_frame[index],
                registered_corner,
                confirmation_radius,
            )
            line_corner = (
                tuple(line_candidate["corner_px"])
                if line_candidate is not None
                else None
            )
            observations.append(
                {
                    "frame_index": index,
                    "registered_corner_px": list(registered_corner),
                    "line_corner_px": list(line_corner) if line_corner else None,
                    "line_candidate_id": (
                        line_candidate["candidate_id"] if line_candidate else None
                    ),
                    "line_registration_error_px": (
                        line_error if line_candidate is not None else None
                    ),
                    "shift_px": list(shift),
                    "correlation": correlation,
                    "representation_spread_px": representation_spread,
                    "forward_reverse_disagreement_px": direction_disagreement,
                    "boundary_hit": boundary,
                }
            )

    usable = [
        observation
        for observation in observations
        if observation["correlation"] >= MIN_CORRELATION
        and not observation["boundary_hit"]
        and observation["representation_spread_px"] <= MAX_REPRESENTATION_SPREAD_PX
        and observation["forward_reverse_disagreement_px"]
        <= MAX_REGISTRATION_DISAGREEMENT_PX
    ]
    confirmed = [
        observation
        for observation in usable
        if observation["line_corner_px"] is not None
    ]
    # The semantic line intersection establishes the absolute corner once.
    # Tight duplicate registration is the authoritative refinement; independent
    # line intersections only confirm that the same geometry remains attached.
    corner_positions = [observation["registered_corner_px"] for observation in usable]
    if corner_positions:
        corner_array = np.asarray(corner_positions, dtype=float)
        corner_pixel = np.median(corner_array, axis=0)
        distances = np.linalg.norm(corner_array - corner_pixel, axis=1)
        repeatability_rms = float(np.sqrt(np.mean(distances**2)))
        repeatability_max = float(np.max(distances))
    else:
        corner_pixel = np.asarray([float("nan"), float("nan")])
        repeatability_rms = float("inf")
        repeatability_max = float("inf")
    correlations = [observation["correlation"] for observation in usable]
    minimum_correlation = min(correlations) if correlations else None
    median_correlation = float(np.median(correlations)) if correlations else None
    max_representation_spread = max(
        (observation["representation_spread_px"] for observation in observations),
        default=float("inf"),
    )
    max_direction_disagreement = max(
        (
            observation["forward_reverse_disagreement_px"]
            for observation in observations
        ),
        default=float("inf"),
    )

    if len(usable) < MIN_USABLE_FRAMES:
        reasons.append("fewer than four duplicate registrations are usable")
    if len(confirmed) < MIN_LINE_CONFIRMATIONS:
        reasons.append("fewer than three duplicates confirm the tab-edge intersection")
    if median_correlation is None or median_correlation < MIN_MEDIAN_CORRELATION:
        reasons.append("median duplicate registration correlation is below 0.90")
    if repeatability_max > MAX_REPEATABILITY_PX:
        reasons.append("corner repeatability exceeds 5 px")
    elif repeatability_max > WARN_REPEATABILITY_PX:
        warnings.append(
            f"corner repeatability maximum is above 1 px ({repeatability_max:.3f} px)"
        )
    if max_direction_disagreement > MAX_REGISTRATION_DISAGREEMENT_PX:
        reasons.append("forward/reverse duplicate registration disagrees by over 4 px")
    elif max_direction_disagreement > WARN_REGISTRATION_DISAGREEMENT_PX:
        warnings.append(
            "forward/reverse duplicate registration disagreement is above "
            f"0.75 px ({max_direction_disagreement:.3f} px)"
        )

    localization_path = output_dir / "corner_localization.jpg"
    duplicates_path = output_dir / "corner_duplicate_registration.jpg"
    _draw_localization(
        images[0],
        candidates_by_frame[0],
        selected,
        expected,
        roi,
        localization_path,
    )
    if observations:
        _draw_duplicates(images, observations, duplicates_path)
    artifact_paths = {
        "corner_localization": localization_path,
        "corner_duplicate_registration": duplicates_path,
    }
    artifacts = {
        name: {"path": str(path), "sha256": sha256_file(path)}
        for name, path in artifact_paths.items()
        if path.exists()
    }
    return _json_finite(
        {
            "accepted": not reasons,
            "reasons": sorted(set(reasons)),
            "warnings": sorted(set(warnings)),
            "missing_frames": [],
            "localizer": LOCALIZER,
            "expected_corner_px": list(expected),
            "selected_candidate": selected,
            "expected_distance_px": expected_distance,
            "corner_pixel_xy_px": corner_pixel.tolist(),
            "usable_frame_count": len(usable),
            "line_confirmation_count": len(confirmed),
            "minimum_correlation": minimum_correlation,
            "median_correlation": median_correlation,
            "repeatability_rms_px": repeatability_rms,
            "repeatability_max_px": repeatability_max,
            "maximum_representation_spread_px": max_representation_spread,
            "maximum_forward_reverse_disagreement_px": max_direction_disagreement,
            "candidates_by_frame": candidates_by_frame,
            "observations": observations,
            "artifacts": artifacts,
        }
    )
