#!/usr/bin/env python3
"""Coordinate-free bed-fiducial metric and tab-corner analysis."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from vision_four_fiducials import FourFiducialError, detect_four_fiducials
from vision_four_fiducials import order_quad as _order_quad
from vision_four_fiducials import quad_geometry as _quad_geometry


class BedFiducialError(RuntimeError):
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


def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _artifact(path: Path) -> dict[str, str]:
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "sha256": f"sha256:{digest}"}


def _fit_panel(image: np.ndarray, width: int = 720) -> np.ndarray:
    scale = width / image.shape[1]
    return cv2.resize(
        image,
        (width, int(round(image.shape[0] * scale))),
        interpolation=cv2.INTER_AREA,
    )


def _draw_detection(
    image: np.ndarray,
    detection: dict[str, Any] | None,
    label: str,
    *,
    selected: bool,
) -> np.ndarray:
    result = image.copy()
    color = (0, 255, 0) if selected else (0, 220, 255)
    cv2.putText(
        result,
        label,
        (24, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        color,
        2,
        cv2.LINE_AA,
    )
    if detection is None:
        cv2.putText(
            result,
            "NO FOUR-RING PATCH",
            (24, 82),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        return result
    for index, (x, y) in enumerate(detection["centers_px"]):
        radius = int(round(detection["radii_px"][index]))
        cv2.circle(result, (int(round(x)), int(round(y))), radius, color, 3)
        cv2.drawMarker(
            result,
            (int(round(x)), int(round(y))),
            color,
            cv2.MARKER_CROSS,
            18,
            2,
        )
        cv2.putText(
            result,
            str(index),
            (int(round(x + radius + 4)), int(round(y))),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
            cv2.LINE_AA,
        )
    x0, y0, x1, y1 = detection["roi_px"]
    cv2.rectangle(result, (x0, y0), (x1, y1), color, 2)
    return result


def _homography_jacobian(
    homography: np.ndarray, point: tuple[float, float]
) -> np.ndarray:
    x, y = point
    h = homography
    denominator = h[2, 0] * x + h[2, 1] * y + h[2, 2]
    u_numerator = h[0, 0] * x + h[0, 1] * y + h[0, 2]
    v_numerator = h[1, 0] * x + h[1, 1] * y + h[1, 2]
    return np.asarray(
        [
            [
                (h[0, 0] * denominator - u_numerator * h[2, 0]) / denominator**2,
                (h[0, 1] * denominator - u_numerator * h[2, 1]) / denominator**2,
            ],
            [
                (h[1, 0] * denominator - v_numerator * h[2, 0]) / denominator**2,
                (h[1, 1] * denominator - v_numerator * h[2, 1]) / denominator**2,
            ],
        ],
        dtype=np.float64,
    )


def _subpixel_peak(response: np.ndarray, x: int, y: int) -> tuple[float, float]:
    def refine(values: np.ndarray, index: int) -> float:
        if index <= 0 or index >= len(values) - 1:
            return float(index)
        left = float(values[index - 1])
        center = float(values[index])
        right = float(values[index + 1])
        denominator = left - 2.0 * center + right
        if abs(denominator) < 1e-12:
            return float(index)
        return float(index) + max(-0.5, min(0.5, 0.5 * (left - right) / denominator))

    return refine(response[y, :], x), refine(response[:, x], y)


def _track_patch_translation(
    reference_image: np.ndarray,
    target_image: np.ndarray,
    reference_roi: list[int],
) -> dict[str, Any]:
    x0, y0, x1, y1 = reference_roi
    height, width = reference_image.shape[:2]
    scale = min(width / 1920.0, height / 1080.0)
    search_x0 = max(0, x0 - int(round(120.0 * scale)))
    search_x1 = min(width, x1 + int(round(120.0 * scale)))
    search_y0 = max(0, y0 - int(round(320.0 * scale)))
    search_y1 = min(height, y1 + int(round(120.0 * scale)))

    def representations(image: np.ndarray) -> list[np.ndarray]:
        gray = _gray(image)
        return [
            gray,
            cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray),
        ]

    shifts = []
    correlations = []
    for reference, target in zip(
        representations(reference_image),
        representations(target_image),
    ):
        template = reference[y0:y1, x0:x1]
        search = target[search_y0:search_y1, search_x0:search_x1]
        response = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
        _minimum, maximum, _minimum_location, maximum_location = cv2.minMaxLoc(response)
        peak_x, peak_y = _subpixel_peak(
            response, maximum_location[0], maximum_location[1]
        )
        shifts.append(
            [
                peak_x + search_x0 - x0,
                peak_y + search_y0 - y0,
            ]
        )
        correlations.append(float(maximum))
    shifts_array = np.asarray(shifts, dtype=np.float64)
    agreement = float(np.linalg.norm(shifts_array[0] - shifts_array[1]))
    if min(correlations) < 0.75:
        raise BedFiducialError(
            f"patch registration correlation {min(correlations):.3f} is too low"
        )
    if agreement > 1.5:
        raise BedFiducialError(
            f"grayscale/CLAHE patch shifts disagree by {agreement:.3f} px"
        )
    return _finite(
        {
            "shift_px": np.mean(shifts_array, axis=0),
            "correlations": correlations,
            "representation_disagreement_px": agreement,
            "search_roi_px": [search_x0, search_y0, search_x1, search_y1],
        }
    )


def analyze_metric(
    frame_paths: list[Path],
    artifact_dir: Path,
    *,
    frames: list[dict[str, Any]],
    patch_points_mm: list[list[float]],
    require_locator: bool = True,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    images = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in frame_paths]
    detections: list[dict[str, Any] | None] = []
    tracking_records: list[dict[str, Any] | None] = []
    failures: list[str] = []
    if not images or images[0] is None:
        raise BedFiducialError("metric reference frame cannot be decoded")
    reference_detection = detect_four_fiducials(
        images[0], require_locator=require_locator
    )
    reference_centers = np.asarray(reference_detection["centers_px"], dtype=np.float64)
    reference_roi = list(reference_detection["roi_px"])
    for index, image in enumerate(images):
        try:
            if image is None:
                raise BedFiducialError("frame cannot be decoded")
            detection = (
                reference_detection
                if index == 0
                else detect_four_fiducials(image, require_locator=require_locator)
            )
            tracking = _track_patch_translation(
                images[0],
                image,
                reference_roi,
            )
            direct_center = np.mean(
                np.asarray(detection["centers_px"], dtype=np.float64),
                axis=0,
            )
            tracked_center = np.mean(reference_centers, axis=0) + np.asarray(
                tracking["shift_px"], dtype=np.float64
            )
            tracking["direct_detection_disagreement_px"] = float(
                np.linalg.norm(direct_center - tracked_center)
            )
            detection["tracking"] = tracking
            detection["commanded_position_mm"] = list(
                frames[index]["commanded_position_mm"]
            )
            detections.append(detection)
            tracking_records.append(tracking)
        except (BedFiducialError, FourFiducialError) as exc:
            detections.append(None)
            tracking_records.append(None)
            failures.append(f"frame {index}: {exc}")
    valid_indices = [
        index for index, detection in enumerate(detections) if detection is not None
    ]
    reasons: list[str] = []
    if len(valid_indices) < 5:
        reasons.append(
            f"only {len(valid_indices)} of {len(frames)} frames contain the full patch"
        )

    offsets = np.asarray(
        [float(frames[index]["y_offset_mm"]) for index in valid_indices],
        dtype=np.float64,
    )
    means = np.asarray(
        [
            np.mean(np.asarray(detections[index]["centers_px"]), axis=0)
            for index in valid_indices
        ],
        dtype=np.float64,
    )
    if len(valid_indices) >= 2 and float(np.ptp(offsets)) > 0.0:
        design = np.column_stack([np.ones_like(offsets), offsets])
        coefficients = np.linalg.lstsq(design, means, rcond=None)[0]
        intercept = coefficients[0]
        y_vector = coefficients[1]
        fitted = design @ coefficients
        residuals = means - fitted
        fit_rms_px = float(np.sqrt(np.mean(np.sum(residuals**2, axis=1))))
    else:
        intercept = np.zeros(2)
        y_vector = np.zeros(2)
        fitted = np.zeros_like(means)
        residuals = np.zeros_like(means)
        fit_rms_px = float("inf")
    scale_y = float(np.linalg.norm(y_vector))
    if not 2.0 <= scale_y <= 30.0:
        reasons.append(f"recovered printer-Y scale {scale_y:.3f} px/mm is invalid")
    if fit_rms_px > 15.0:
        reasons.append(f"fiducial displacement fit RMS {fit_rms_px:.3f} px is too high")

    zero_indices = [
        index
        for index in valid_indices
        if abs(float(frames[index]["y_offset_mm"])) < 1e-9
    ]
    if not zero_indices:
        reasons.append("no valid zero-offset fiducial frame")
        reference_centers = np.zeros((4, 2), dtype=np.float64)
        reference_capture_y = 0.0
    else:
        reference_centers = np.mean(
            np.asarray([detections[index]["centers_px"] for index in zero_indices]),
            axis=0,
        )
        reference_capture_y = float(frames[zero_indices[0]]["commanded_position_mm"][1])

    patch_points = np.asarray(patch_points_mm, dtype=np.float64)
    if patch_points.shape != (4, 2):
        raise BedFiducialError("physical reference must contain four XY centers")
    patch_center = np.mean(patch_points, axis=0)
    homography, _mask = cv2.findHomography(patch_points, reference_centers, 0)
    if homography is None:
        reasons.append("patch homography cannot be solved")
        homography = np.eye(3)
    jacobian = _homography_jacobian(homography, tuple(patch_center))
    try:
        patch_y_per_printer_y = np.linalg.solve(jacobian, y_vector)
    except np.linalg.LinAlgError:
        patch_y_per_printer_y = np.zeros(2)
        reasons.append("patch homography Jacobian is singular")
    patch_y_norm = float(np.linalg.norm(patch_y_per_printer_y))
    if not 0.65 <= patch_y_norm <= 1.35:
        reasons.append(
            "commanded Y displacement is inconsistent with the printed 8 mm metric "
            f"(patch displacement {patch_y_norm:.3f} mm/mm)"
        )
    if patch_y_norm > 0:
        patch_y_unit = patch_y_per_printer_y / patch_y_norm
    else:
        patch_y_unit = np.asarray([0.0, 1.0])
    patch_x_a = np.asarray([patch_y_unit[1], -patch_y_unit[0]])
    capture_y_values = np.asarray(
        [float(frames[index]["commanded_position_mm"][1]) for index in valid_indices],
        dtype=np.float64,
    )
    local_metric_records = []
    image_x_vectors_a = []
    for index in valid_indices:
        centers = np.asarray(detections[index]["centers_px"], dtype=np.float64)
        local_homography, _mask = cv2.findHomography(patch_points, centers, 0)
        if local_homography is None:
            reasons.append(f"frame {index} local patch homography cannot be solved")
            continue
        local_jacobian = _homography_jacobian(
            local_homography,
            tuple(patch_center),
        )
        image_x_vector_a = local_jacobian @ patch_x_a
        image_x_vectors_a.append(image_x_vector_a)
        local_metric_records.append(
            {
                "seq": index,
                "commanded_y_mm": float(frames[index]["commanded_position_mm"][1]),
                "y_offset_mm": float(frames[index]["y_offset_mm"]),
                "patch_to_image_homography": local_homography,
                "image_x_candidate_a_px_per_mm": image_x_vector_a,
            }
        )
    if len(image_x_vectors_a) != len(valid_indices):
        reasons.append("not every usable frame has a local metric")
    if len(image_x_vectors_a) >= 2 and float(np.ptp(capture_y_values)) > 0.0:
        image_x_vectors_array = np.asarray(
            image_x_vectors_a,
            dtype=np.float64,
        )
        zero_mask = np.asarray(
            [abs(float(frames[index]["y_offset_mm"])) < 1e-9 for index in valid_indices]
        )
        image_x_reference_a = np.mean(
            image_x_vectors_array[zero_mask],
            axis=0,
        )
        delta_y = capture_y_values - reference_capture_y
        denominator = float(np.dot(delta_y, delta_y))
        image_x_y_slope_a = (
            np.sum(
                delta_y[:, None] * (image_x_vectors_array - image_x_reference_a),
                axis=0,
            )
            / denominator
        )
        x_fit_residuals = image_x_vectors_array - (
            image_x_reference_a + delta_y[:, None] * image_x_y_slope_a
        )
        x_fit_rms_px_per_mm = float(
            np.sqrt(np.mean(np.sum(x_fit_residuals**2, axis=1)))
        )
    else:
        image_x_reference_a = jacobian @ patch_x_a
        image_x_y_slope_a = np.zeros(2, dtype=np.float64)
        x_fit_rms_px_per_mm = float("inf")
        reasons.append("printer-X scale/capture-Y slope cannot be fitted")
    image_x_models = [
        {
            "reference_capture_y_mm": reference_capture_y,
            "reference_vector_px_per_mm": image_x_reference_a,
            "capture_y_slope_px_per_mm_per_mm": image_x_y_slope_a,
        },
        {
            "reference_capture_y_mm": reference_capture_y,
            "reference_vector_px_per_mm": -image_x_reference_a,
            "capture_y_slope_px_per_mm_per_mm": -image_x_y_slope_a,
        },
    ]

    duplicate_disagreement_px = 0.0
    if len(zero_indices) >= 2:
        duplicate_disagreement_px = float(
            np.max(
                np.linalg.norm(
                    np.asarray(detections[zero_indices[0]]["centers_px"])
                    - np.asarray(detections[zero_indices[-1]]["centers_px"]),
                    axis=1,
                )
            )
        )
    warnings = list(failures)
    if fit_rms_px > 1.0:
        warnings.append(f"metric fit RMS is {fit_rms_px:.3f} px")
    if duplicate_disagreement_px > 1.5:
        warnings.append(
            f"zero-offset duplicate disagreement is {duplicate_disagreement_px:.3f} px"
        )

    panels = []
    for index, (image, detection) in enumerate(zip(images, detections)):
        residual = (
            float(np.linalg.norm(residuals[valid_indices.index(index)]))
            if index in valid_indices
            else None
        )
        panel = _draw_detection(
            image,
            detection,
            (f"seq={index} Yoff={frames[index]['y_offset_mm']} " f"res={residual}"),
            selected=detection is not None,
        )
        if detection is not None:
            center = np.mean(np.asarray(detection["centers_px"]), axis=0)
            predicted = intercept + y_vector * float(frames[index]["y_offset_mm"])
            cv2.drawMarker(
                panel,
                tuple(np.rint(center).astype(int)),
                (0, 255, 255),
                cv2.MARKER_CROSS,
                28,
                3,
            )
            cv2.drawMarker(
                panel,
                tuple(np.rint(predicted).astype(int)),
                (255, 255, 0),
                cv2.MARKER_TILTED_CROSS,
                28,
                3,
            )
        panels.append(_fit_panel(panel, 640))
    contact = cv2.vconcat([cv2.hconcat(panels[:3]), cv2.hconcat(panels[3:6])])
    tracking_path = artifact_dir / "fiducial_metric_tracking.jpg"
    cv2.imwrite(str(tracking_path), contact)

    plot = np.full((680, 1080, 3), 24, np.uint8)
    margin = 80
    cv2.line(plot, (margin, 600), (1000, 600), (180, 180, 180), 1)
    cv2.line(plot, (margin, 60), (margin, 600), (180, 180, 180), 1)
    if valid_indices:
        max_offset = max(1.0, float(np.max(offsets)))
        displacements = means - intercept
        axis = y_vector / max(1e-9, scale_y)
        scalar = displacements @ axis
        for offset, observed in zip(offsets, scalar):
            x = int(round(margin + 900.0 * offset / max_offset))
            y = int(round(600.0 - 480.0 * observed / max(1.0, scale_y * max_offset)))
            cv2.circle(plot, (x, y), 7, (0, 255, 0), -1)
        cv2.putText(
            plot,
            f"Y axis vector = [{y_vector[0]:.5f}, {y_vector[1]:.5f}] px/mm",
            (margin, 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
    plot_path = artifact_dir / "fiducial_displacement_plot.jpg"
    cv2.imwrite(str(plot_path), plot)

    return _finite(
        {
            "accepted": not reasons,
            "reasons": reasons,
            "warnings": warnings,
            "usable_frame_count": len(valid_indices),
            "image_y_axis_vector_px_per_mm": y_vector,
            "patch_to_image_homography": homography,
            "patch_reference_center_xy_mm": patch_center,
            "patch_y_vector_per_printer_y_mm": patch_y_per_printer_y,
            "patch_x_axis_candidates_patch_mm_per_printer_mm": [
                patch_x_a,
                -patch_x_a,
            ],
            "image_x_axis_candidate_models": image_x_models,
            "image_x_vector_capture_y_fit_rms_px_per_mm": x_fit_rms_px_per_mm,
            "local_metric_records": local_metric_records,
            "reference_marker_centers_px": reference_centers,
            "reference_capture_y_mm": reference_capture_y,
            "fit_rms_px": fit_rms_px,
            "duplicate_disagreement_px": duplicate_disagreement_px,
            "detection_records": detections,
            "tracking_records": tracking_records,
            "artifacts": {
                "fiducial_metric_tracking": _artifact(tracking_path),
                "fiducial_displacement_plot": _artifact(plot_path),
            },
        }
    )


def _line_intersection(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float] | None:
    x1, y1, x2, y2 = first
    x3, y3, x4, y4 = second
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denominator) < 1e-9:
        return None
    cross_first = x1 * y2 - y1 * x2
    cross_second = x3 * y4 - y3 * x4
    return (
        (cross_first * (x3 - x4) - (x1 - x2) * cross_second) / denominator,
        (cross_first * (y3 - y4) - (y1 - y2) * cross_second) / denominator,
    )


def detect_tab_corner_relative_to_patch(
    image: np.ndarray, detection: dict[str, Any]
) -> dict[str, Any]:
    centers = np.asarray(detection["centers_px"], dtype=np.float64)
    horizontal_span = float(
        0.5
        * (
            np.linalg.norm(centers[1] - centers[0])
            + np.linalg.norm(centers[3] - centers[2])
        )
    )
    vertical_span = float(
        0.5
        * (
            np.linalg.norm(centers[2] - centers[0])
            + np.linalg.norm(centers[3] - centers[1])
        )
    )
    top_y = float(np.mean(centers[:2, 1]))
    right_x = float(np.mean(centers[[1, 3], 0]))
    x0 = max(0, int(math.floor(float(np.min(centers[:, 0])) - horizontal_span)))
    x1 = min(
        image.shape[1],
        int(math.ceil(float(np.max(centers[:, 0])) + 1.6 * horizontal_span)),
    )
    y0 = max(0, int(math.floor(top_y - 1.2 * vertical_span)))
    y1 = min(
        image.shape[0],
        int(math.ceil(float(np.max(centers[:, 1])) + 0.9 * vertical_span)),
    )
    roi_gray = cv2.createCLAHE(2.0, (8, 8)).apply(_gray(image)[y0:y1, x0:x1])
    edges = cv2.Canny(roi_gray, 45, 120)
    lines_raw = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 1800.0,
        threshold=max(24, int(round(0.18 * horizontal_span))),
        minLineLength=max(20, int(round(0.35 * horizontal_span))),
        maxLineGap=max(8, int(round(0.18 * horizontal_span))),
    )
    if lines_raw is None:
        raise BedFiducialError("no tab-edge line candidates detected")
    lines = []
    for raw in lines_raw[:, 0]:
        xa, ya, xb, yb = [float(item) for item in raw]
        line = (xa + x0, ya + y0, xb + x0, yb + y0)
        dx = line[2] - line[0]
        dy = line[3] - line[1]
        length = math.hypot(dx, dy)
        angle = math.degrees(math.atan2(dy, dx))
        lines.append(
            {
                "line": line,
                "length": length,
                "angle_deg": angle,
                "midpoint": [(line[0] + line[2]) * 0.5, (line[1] + line[3]) * 0.5],
            }
        )
    horizontals = [
        item
        for item in lines
        if abs(item["angle_deg"]) <= 10.0
        and top_y - 1.1 * vertical_span
        <= item["midpoint"][1]
        <= top_y + 0.15 * vertical_span
    ]
    sides = [
        item
        for item in lines
        if 35.0 <= abs(item["angle_deg"]) <= 88.0
        and right_x + 0.15 * horizontal_span
        <= item["midpoint"][0]
        <= right_x + 1.5 * horizontal_span
    ]
    if not horizontals or not sides:
        raise BedFiducialError(
            f"tab edge pair missing: horizontal={len(horizontals)} side={len(sides)}"
        )
    candidates = []
    for horizontal in horizontals:
        for side in sides:
            point = _line_intersection(horizontal["line"], side["line"])
            if point is None:
                continue
            if not (
                right_x - 0.2 * horizontal_span
                <= point[0]
                <= right_x + 1.5 * horizontal_span
                and top_y - 1.1 * vertical_span
                <= point[1]
                <= top_y + 0.25 * vertical_span
            ):
                continue
            above_distance = abs((top_y - point[1]) - 0.45 * vertical_span)
            right_distance = abs((point[0] - right_x) - 0.7 * horizontal_span)
            score = (
                horizontal["length"] + side["length"] - above_distance - right_distance
            )
            candidates.append((score, point, horizontal, side))
    if not candidates:
        raise BedFiducialError("tab edge candidates do not form a valid intersection")
    _score, point, horizontal, side = max(candidates, key=lambda item: item[0])
    return _finite(
        {
            "corner_pixel_xy_px": point,
            "candidate_score": _score,
            "horizontal_line_px": horizontal["line"],
            "side_line_px": side["line"],
            "search_roi_px": [x0, y0, x1, y1],
            "candidate_line_count": len(lines),
            "horizontal_candidate_count": len(horizontals),
            "side_candidate_count": len(sides),
        }
    )


def _predicted_patch_detection(
    image: np.ndarray,
    centers_px: list[list[float]] | np.ndarray,
) -> dict[str, Any]:
    centers = _order_quad(np.asarray(centers_px, dtype=np.float64))
    geometry = _quad_geometry(centers)
    if geometry is None:
        raise BedFiducialError("predicted patch geometry is invalid")
    geometry_details = geometry[1]
    mean_side = geometry_details["mean_side_px"]
    radius = 0.1875 * mean_side
    x0, y0 = np.min(centers, axis=0)
    x1, y1 = np.max(centers, axis=0)
    pad = 0.35 * mean_side
    return _finite(
        {
            "centers_px": centers,
            "radii_px": [radius] * 4,
            "ring_scores": [None] * 4,
            "worst_ring_score": None,
            "geometry": geometry_details,
            "detection_score": None,
            "roi_px": [
                max(0, int(math.floor(x0 - pad))),
                max(0, int(math.floor(y0 - pad))),
                min(image.shape[1], int(math.ceil(x1 + pad))),
                min(image.shape[0], int(math.ceil(y1 + pad))),
            ],
            "clipped_fraction": None,
            "dark_fraction": None,
            "candidate_count": None,
            "source": "bed_metric_prediction",
        }
    )


def analyze_corner(
    frame_paths: list[Path],
    artifact_dir: Path,
    *,
    frames: list[dict[str, Any]],
    expected_marker_centers_px: list[list[float]],
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    images = [cv2.imread(str(path), cv2.IMREAD_COLOR) for path in frame_paths]
    if not images or any(image is None for image in images):
        raise BedFiducialError("one or more corner frames cannot be decoded")
    predicted_detections = [
        _predicted_patch_detection(image, expected_marker_centers_px)
        for image in images
    ]
    semantic_corners: list[dict[str, Any] | None] = []
    warnings: list[str] = []
    for index, (image, detection) in enumerate(zip(images, predicted_detections)):
        try:
            corner = detect_tab_corner_relative_to_patch(image, detection)
        except BedFiducialError as exc:
            corner = None
            warnings.append(f"frame {index}: {exc}")
        semantic_corners.append(corner)

    reasons: list[str] = []
    semantic_indices = [
        index for index, corner in enumerate(semantic_corners) if corner is not None
    ]
    if not semantic_indices:
        reasons.append("no duplicate contains a semantic tab-edge intersection")
        source_index = 0
        source_corner = np.mean(
            np.asarray(expected_marker_centers_px, dtype=np.float64), axis=0
        )
    else:
        source_index = max(
            semantic_indices,
            key=lambda index: float(semantic_corners[index]["candidate_score"]),
        )
        source_corner = np.asarray(
            semantic_corners[source_index]["corner_pixel_xy_px"],
            dtype=np.float64,
        )

    expected_centers = np.asarray(expected_marker_centers_px, dtype=np.float64)
    mean_side = _quad_geometry(expected_centers)[1]["mean_side_px"]
    roi = [
        max(0, int(math.floor(source_corner[0] - 1.5 * mean_side))),
        max(0, int(math.floor(source_corner[1] - 1.25 * mean_side))),
        min(images[0].shape[1], int(math.ceil(source_corner[0] + 1.5 * mean_side))),
        min(images[0].shape[0], int(math.ceil(source_corner[1] + 1.25 * mean_side))),
    ]
    records: list[dict[str, Any]] = []
    registered_points = []
    patch_centers = []
    for index, image in enumerate(images):
        try:
            tracking = _track_patch_translation(
                images[source_index],
                image,
                roi,
            )
            shift = np.asarray(tracking["shift_px"], dtype=np.float64)
            registered_corner = source_corner + shift
            registered_points.append(registered_corner)
            patch_centers.append(expected_centers + shift)
            records.append(
                {
                    "frame_index": index,
                    "registered_corner_pixel_xy_px": registered_corner,
                    "tracking": tracking,
                    "semantic_line_detection": semantic_corners[index],
                }
            )
        except BedFiducialError as exc:
            warnings.append(f"frame {index}: corner registration failed: {exc}")
            records.append(
                {
                    "frame_index": index,
                    "registered_corner_pixel_xy_px": None,
                    "tracking": None,
                    "semantic_line_detection": semantic_corners[index],
                }
            )

    if len(registered_points) < 4:
        reasons.append(
            f"only {len(registered_points)} duplicate corner registrations are usable"
        )
    if len(semantic_indices) < 3:
        warnings.append(
            f"only {len(semantic_indices)} duplicates independently show the tab-edge intersection"
        )
    if registered_points:
        points = np.asarray(registered_points, dtype=np.float64)
        corner_pixel = np.median(points, axis=0)
        repeatability = float(np.max(np.linalg.norm(points - corner_pixel, axis=1)))
        patch_reference = np.mean(np.asarray(patch_centers), axis=0)
        relative_corner = corner_pixel - np.mean(patch_reference, axis=0)
    else:
        corner_pixel = np.zeros(2)
        repeatability = float("inf")
        patch_reference = expected_centers
        relative_corner = np.zeros(2)
    if repeatability > 8.0:
        reasons.append(
            f"patch-relative corner repeatability {repeatability:.3f} px is too poor"
        )
    if repeatability > 2.0 and math.isfinite(repeatability):
        warnings.append(
            f"patch-relative corner repeatability is {repeatability:.3f} px"
        )

    panels = []
    for index, (image, record) in enumerate(zip(images, records)):
        shift = (
            np.asarray(record["tracking"]["shift_px"], dtype=np.float64)
            if record["tracking"] is not None
            else np.zeros(2)
        )
        detection = _predicted_patch_detection(image, expected_centers + shift)
        corner = record["semantic_line_detection"]
        panel = _draw_detection(
            image,
            detection,
            (
                f"duplicate {index} bright corner lighting "
                f"corr={min(record['tracking']['correlations']):.4f}"
                if record["tracking"] is not None
                else f"duplicate {index} registration failed"
            ),
            selected=record["tracking"] is not None,
        )
        if corner is not None:
            for key, color in (
                ("horizontal_line_px", (0, 255, 255)),
                ("side_line_px", (0, 255, 255)),
            ):
                xa, ya, xb, yb = corner[key]
                cv2.line(
                    panel,
                    (int(round(xa)), int(round(ya))),
                    (int(round(xb)), int(round(yb))),
                    color,
                    4,
                )
            x0, y0, x1, y1 = corner["search_roi_px"]
            cv2.rectangle(panel, (x0, y0), (x1, y1), (255, 128, 0), 2)
        registered = record["registered_corner_pixel_xy_px"]
        if registered is not None:
            cx, cy = registered
            cv2.circle(panel, (int(round(cx)), int(round(cy))), 18, (255, 255, 0), 4)
        panels.append(_fit_panel(panel, 640))
    while len(panels) < 6:
        panels.append(np.zeros_like(panels[0]))
    overlay = cv2.vconcat([cv2.hconcat(panels[:3]), cv2.hconcat(panels[3:6])])
    overlay_path = artifact_dir / "bed_tab_corner_relative_to_fiducials.jpg"
    cv2.imwrite(str(overlay_path), overlay)
    return _finite(
        {
            "accepted": not reasons,
            "reasons": reasons,
            "warnings": warnings,
            "usable_frame_count": len(registered_points),
            "corner_pixel_xy_px": corner_pixel,
            "patch_marker_centers_px": patch_reference,
            "corner_relative_to_patch_center_px": relative_corner,
            "repeatability_max_px": repeatability,
            "semantic_line_confirmation_count": len(semantic_indices),
            "source_frame_index": source_index,
            "corner_lighting": {
                "profile": frames[0]["profile"],
                "light_pixels": frames[0]["light_pixels"],
            },
            "records": records,
            "artifacts": {
                "bed_tab_corner_relative_to_fiducials": _artifact(overlay_path)
            },
        }
    )
