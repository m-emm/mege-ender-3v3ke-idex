#!/usr/bin/env python3
"""Analysis helpers for report-only rough IDEX and Eddy-light calibration."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any


ROUGH_OBSERVATION_SCALE = 100.0
ROUGH_TEMPLATE_SIZE_1080 = 132
ROUGH_TEMPLATE_MIN_CORRELATION = 0.70
ROUGH_TEMPLATE_STRICT_MIN_CORRELATION = 0.80
ROUGH_MAX_FIT_RMS = 1.5
ROUGH_MAX_DUPLICATE_MAD = 0.75
ROUGH_MAX_JACOBIAN_CONDITION = 15.0
ROUGH_MAX_AXIS_RELATIVE_SPREAD = 0.15
ROUGH_MAX_RING_SCALE_SPREAD = 0.05
ROUGH_PASS_X_AGREEMENT_MM = 0.15
ROUGH_PASS_YZ_AGREEMENT_MM = 0.20
ROUGH_CORRECTION_LIMITS_MM = (25.0, 5.0, 2.0)
ROUGH_NOZZLE_ROI_SIZE = (260, 220)
ROUGH_NOZZLE_OFFSET_FROM_RED = (35.0, 105.0)
ROUGH_TOOL_CENTER_HINTS_1080 = {
    "t0": (1032.0, 500.0),
    "t1": (1030.0, 511.0),
}
ROUGH_RING_RADIUS_HINT_1080 = 62.0
ROUGH_X_AXIS_HINT_PX_PER_MM_1080 = 8.0
EDDY_LIGHT_ROI_1080 = (850, 225, 170, 160)
EDDY_LIGHT_EXPECTED_CENTER_1080 = (928, 297)
EDDY_LIGHT_CENTER_SEARCH_RADIUS_1080 = (18, 14)
EDDY_LIGHT_RING_RADII_1080 = (11, 17, 23, 29)


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def center_out_offsets(max_offset: float = 18.0, step: float = 3.0) -> list[float]:
    if max_offset <= 0 or step <= 0:
        raise ValueError("max_offset and step must be positive")
    values = [0.0]
    level = step
    while level <= max_offset + 1.0e-9:
        values.extend((-level, level))
        level += step
    return values


def median_absolute_deviation(values: list[float]) -> float:
    if not values:
        return math.inf
    center = statistics.median(values)
    return statistics.median(abs(value - center) for value in values)


def detect_red_locator(image: Any) -> dict[str, Any]:
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    scale_x = width / 1920.0
    scale_y = height / 1080.0
    x = int(round(920 * scale_x))
    y = int(round(330 * scale_y))
    w = int(round(260 * scale_x))
    h = int(round(190 * scale_y))
    crop = image[y : y + h, x : x + w]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    low = cv2.inRange(hsv, np.array([0, 70, 35]), np.array([14, 255, 255]))
    high = cv2.inRange(hsv, np.array([168, 70, 35]), np.array([180, 255, 255]))
    mask = cv2.bitwise_or(low, high)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 80.0:
            continue
        moments = cv2.moments(contour)
        if not moments["m00"]:
            continue
        candidates.append(
            {
                "center_px": [
                    float(moments["m10"] / moments["m00"] + x),
                    float(moments["m01"] / moments["m00"] + y),
                ],
                "area": area,
            }
        )
    candidates.sort(key=lambda item: item["area"], reverse=True)
    if not candidates:
        return {
            "accepted": False,
            "roi": [x, y, w, h],
            "rejection_reason": "red locator not found",
        }
    return {
        "accepted": True,
        "roi": [x, y, w, h],
        **candidates[0],
        "candidates": candidates[:5],
    }


def _radial_edge_score(gray: Any, cx: float, cy: float, radius: float) -> tuple[float, float]:
    import cv2
    import numpy as np

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(gx, gy)
    angles = np.linspace(0.0, 2.0 * math.pi, 180, endpoint=False)
    samples = []
    for delta in (-2.0, 0.0, 2.0):
        rr = radius + delta
        xs = np.clip(
            np.rint(cx + rr * np.cos(angles)).astype(int), 0, gray.shape[1] - 1
        )
        ys = np.clip(
            np.rint(cy + rr * np.sin(angles)).astype(int), 0, gray.shape[0] - 1
        )
        samples.append(magnitude[ys, xs])
    edge = np.max(np.asarray(samples), axis=0)
    threshold = float(np.percentile(magnitude, 80))
    return float(np.median(edge)), float(np.mean(edge >= threshold))


def detect_nozzle_observation(
    image: Any,
    *,
    require_orifice: bool = True,
    expected_center_px: tuple[float, float] | list[float] | None = None,
    expected_radius_px: float | None = None,
) -> dict[str, Any]:
    import cv2
    import numpy as np

    red = detect_red_locator(image)
    if expected_center_px is None and not red.get("accepted"):
        return {
            "accepted": False,
            "red_locator": red,
            "rejection_reason": red.get("rejection_reason"),
            "exclusion_reason": "nozzle_not_visible",
        }
    image_height, image_width = image.shape[:2]
    if expected_center_px is None:
        red_x, red_y = [float(value) for value in red["center_px"]]
        expected_x = red_x + ROUGH_NOZZLE_OFFSET_FROM_RED[0] * image_width / 1920.0
        expected_y = red_y + ROUGH_NOZZLE_OFFSET_FROM_RED[1] * image_height / 1080.0
    else:
        expected_x, expected_y = [float(value) for value in expected_center_px]
    roi_w = int(round(ROUGH_NOZZLE_ROI_SIZE[0] * image_width / 1920.0))
    roi_h = int(round(ROUGH_NOZZLE_ROI_SIZE[1] * image_height / 1080.0))
    roi_x = max(0, min(image_width - roi_w, int(round(expected_x - roi_w / 2))))
    roi_y = max(0, min(image_height - roi_h, int(round(expected_y - roi_h / 2))))
    crop = image[roi_y : roi_y + roi_h, roi_x : roi_x + roi_w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blurred = cv2.GaussianBlur(clahe, (7, 7), 1.5)
    scale = (image_width / 1920.0 + image_height / 1080.0) / 2.0
    radius_hint = (
        float(expected_radius_px)
        if expected_radius_px is not None
        else 72.0 * scale
    )
    min_ring_radius = (
        max(15, int(round(radius_hint * 0.78)))
        if expected_radius_px is not None
        else max(15, int(round(28 * scale)))
    )
    max_ring_radius = (
        max(min_ring_radius + 8, int(round(radius_hint * 1.22)))
        if expected_radius_px is not None
        else max(45, int(round(110 * scale)))
    )
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(18, int(round(30 * scale))),
        param1=80,
        # The nozzle-face ring is low contrast in several otherwise fully
        # visible frames.  Identity is guarded by the expected center, radius,
        # and central-orifice checks below, so use a moderately sensitive Hough
        # stage and let those explicit visibility checks reject impostors.
        param2=20,
        minRadius=min_ring_radius,
        maxRadius=max_ring_radius,
    )
    ring_candidates: list[dict[str, Any]] = []
    if circles is not None:
        for cx, cy, radius in circles[0]:
            radial, coverage = _radial_edge_score(gray, float(cx), float(cy), float(radius))
            global_x = float(cx + roi_x)
            global_y = float(cy + roi_y)
            expected_distance = math.hypot(global_x - expected_x, global_y - expected_y)
            if expected_center_px is not None and (
                expected_distance > 14.0 * scale
                or abs(float(radius) - radius_hint) > 0.18 * radius_hint
            ):
                continue
            score = (
                radial
                + 45.0 * coverage
                - (1.8 if expected_center_px is not None else 0.7)
                * expected_distance
                - (1.2 if expected_radius_px is not None else 0.12)
                * abs(float(radius) - radius_hint)
            )
            ring_candidates.append(
                {
                    "center_px": [global_x, global_y],
                    "radius_px": float(radius),
                    "radial_edge": radial,
                    "arc_coverage": coverage,
                    "expected_distance_px": expected_distance,
                    "score": score,
                }
            )
    ring_candidates.sort(key=lambda item: item["score"], reverse=True)
    if not ring_candidates:
        return {
            "accepted": False,
            "red_locator": red,
            "roi": [roi_x, roi_y, roi_w, roi_h],
            "rejection_reason": "no nozzle-face ring found",
            "exclusion_reason": "nozzle_not_visible",
            "ring_candidates": [],
        }
    ring = ring_candidates[0]
    ambiguous_ring = False
    if len(ring_candidates) > 1:
        second = ring_candidates[1]
        score_gap = float(ring["score"]) - float(second["score"])
        center_gap = math.hypot(
            float(ring["center_px"][0]) - float(second["center_px"][0]),
            float(ring["center_px"][1]) - float(second["center_px"][1]),
        )
        ambiguous_ring = score_gap < 8.0 and center_gap > 18.0 * scale
    ring_x = float(ring["center_px"][0] - roi_x)
    ring_y = float(ring["center_px"][1] - roi_y)
    small = cv2.HoughCircles(
        cv2.GaussianBlur(gray, (5, 5), 1.0),
        cv2.HOUGH_GRADIENT,
        dp=1.1,
        minDist=max(8, int(round(12 * scale))),
        param1=80,
        param2=12,
        minRadius=max(3, int(round(4 * scale))),
        maxRadius=max(12, int(round(26 * scale))),
    )
    orifice_candidates: list[dict[str, Any]] = []
    if small is not None:
        for cx, cy, radius in small[0]:
            distance = math.hypot(float(cx) - ring_x, float(cy) - ring_y)
            if distance > max(26.0 * scale, float(ring["radius_px"]) * 0.42):
                continue
            orifice_candidates.append(
                {
                    "center_px": [float(cx + roi_x), float(cy + roi_y)],
                    "radius_px": float(radius),
                    "ring_center_distance_px": distance,
                    "score": -distance - abs(float(radius) - 10.0 * scale),
                }
            )
    orifice_candidates.sort(key=lambda item: item["score"], reverse=True)
    accepted = (
        float(ring["arc_coverage"])
        >= (0.55 if expected_center_px is not None else 0.45)
        and float(ring["radial_edge"])
        >= (50.0 if expected_center_px is not None else 0.0)
        and float(ring["expected_distance_px"])
        <= (14.0 * scale if expected_center_px is not None else 70.0 * scale)
        and (
            expected_radius_px is None
            or abs(float(ring["radius_px"]) - radius_hint)
            <= 0.18 * radius_hint
        )
        and not ambiguous_ring
        and (bool(orifice_candidates) or not require_orifice)
        and (
            not require_orifice
            or not orifice_candidates
            or float(orifice_candidates[0]["ring_center_distance_px"])
            <= 0.34 * float(ring["radius_px"])
        )
    )
    if accepted and orifice_candidates and expected_center_px is None:
        orifice = orifice_candidates[0]
        center = [
            0.8 * float(ring["center_px"][0]) + 0.2 * float(orifice["center_px"][0]),
            0.8 * float(ring["center_px"][1]) + 0.2 * float(orifice["center_px"][1]),
        ]
    else:
        orifice = orifice_candidates[0] if orifice_candidates else None
        center = list(ring["center_px"])
    return {
        "accepted": accepted,
        "red_locator": red,
        "roi": [roi_x, roi_y, roi_w, roi_h],
        "center_px": [round(float(center[0]), 4), round(float(center[1]), 4)],
        "radius_px": round(float(ring["radius_px"]), 4),
        "observation": [
            round(float(center[0]), 6),
            round(float(center[1]), 6),
            round(ROUGH_OBSERVATION_SCALE * math.log(float(ring["radius_px"])), 6),
        ],
        "ring": ring,
        "ambiguous_ring": ambiguous_ring,
        "orifice": orifice,
        "ring_candidates": ring_candidates[:8],
        "orifice_candidates": orifice_candidates[:8],
        "rejection_reason": (
            ""
            if accepted
            else (
                "central nozzle orifice not found"
                if require_orifice and not orifice_candidates
                else (
                    "ambiguous nozzle-face rings"
                    if ambiguous_ring
                    else "nozzle ring quality below threshold"
                )
            )
        ),
        "exclusion_reason": "" if accepted else "nozzle_not_visible",
        "expected_center_px": [expected_x, expected_y],
        "expected_radius_px": radius_hint,
    }


def _prepare_nozzle_template_image(image: Any, *, edge: bool) -> Any:
    import cv2
    import numpy as np

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    prepared = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    if edge:
        gradient_x = cv2.Sobel(prepared, cv2.CV_32F, 1, 0, ksize=3)
        gradient_y = cv2.Sobel(prepared, cv2.CV_32F, 0, 1, ksize=3)
        prepared = cv2.magnitude(gradient_x, gradient_y)
        upper = max(1.0, float(np.percentile(prepared, 98)))
        prepared = np.clip(prepared, 0.0, upper)
        prepared = cv2.normalize(
            prepared, None, 0, 255, cv2.NORM_MINMAX
        ).astype(np.uint8)
    return cv2.GaussianBlur(prepared, (3, 3), 0.7)


def make_nozzle_tracking_template(
    image: Any,
    center_px: tuple[float, float] | list[float],
    *,
    edge: bool = False,
) -> Any:
    image_height, image_width = image.shape[:2]
    scale = (image_width / 1920.0 + image_height / 1080.0) / 2.0
    size = max(64, int(round(ROUGH_TEMPLATE_SIZE_1080 * scale)))
    if size % 2:
        size += 1
    center_x, center_y = [float(value) for value in center_px]
    x0 = int(round(center_x - size / 2))
    y0 = int(round(center_y - size / 2))
    x1 = x0 + size
    y1 = y0 + size
    if x0 < 0 or y0 < 0 or x1 > image_width or y1 > image_height:
        raise ValueError("nozzle tracking template extends outside the image")
    prepared = _prepare_nozzle_template_image(image, edge=edge)
    return prepared[y0:y1, x0:x1].copy()


def track_nozzle_template(
    image: Any,
    template: Any,
    expected_center_px: tuple[float, float] | list[float],
    *,
    minimum_correlation: float = ROUGH_TEMPLATE_MIN_CORRELATION,
    maximum_center_error_px: float = 18.0,
    edge: bool = False,
) -> dict[str, Any]:
    import cv2
    import numpy as np

    prepared = _prepare_nozzle_template_image(image, edge=edge)
    expected_x, expected_y = [float(value) for value in expected_center_px]
    image_height, image_width = prepared.shape[:2]
    image_scale = (image_width / 1920.0 + image_height / 1080.0) / 2.0
    margin = max(12, int(round(18.0 * image_scale)))
    best: dict[str, Any] | None = None
    for template_scale in np.linspace(0.88, 1.12, 49):
        scaled = cv2.resize(
            template,
            None,
            fx=float(template_scale),
            fy=float(template_scale),
            interpolation=cv2.INTER_LINEAR,
        )
        height, width = scaled.shape[:2]
        x0 = max(0, int(math.floor(expected_x - width / 2 - margin)))
        y0 = max(0, int(math.floor(expected_y - height / 2 - margin)))
        x1 = min(image_width, int(math.ceil(expected_x + width / 2 + margin)))
        y1 = min(image_height, int(math.ceil(expected_y + height / 2 + margin)))
        search = prepared[y0:y1, x0:x1]
        if search.shape[0] < height or search.shape[1] < width:
            continue
        correlation = cv2.matchTemplate(
            search, scaled, cv2.TM_CCOEFF_NORMED
        )
        _, peak, _, peak_location = cv2.minMaxLoc(correlation)
        peak_x, peak_y = peak_location

        def subpixel_offset(axis: int) -> float:
            if axis == 0:
                if peak_x <= 0 or peak_x >= correlation.shape[1] - 1:
                    return 0.0
                before = float(correlation[peak_y, peak_x - 1])
                center = float(correlation[peak_y, peak_x])
                after = float(correlation[peak_y, peak_x + 1])
            else:
                if peak_y <= 0 or peak_y >= correlation.shape[0] - 1:
                    return 0.0
                before = float(correlation[peak_y - 1, peak_x])
                center = float(correlation[peak_y, peak_x])
                after = float(correlation[peak_y + 1, peak_x])
            denominator = before - 2.0 * center + after
            if abs(denominator) <= 1.0e-9:
                return 0.0
            return max(-1.0, min(1.0, 0.5 * (before - after) / denominator))

        center_x = x0 + peak_x + subpixel_offset(0) + width / 2.0
        center_y = y0 + peak_y + subpixel_offset(1) + height / 2.0
        center_error = math.hypot(center_x - expected_x, center_y - expected_y)
        candidate = {
            "accepted": (
                float(peak) >= float(minimum_correlation)
                and center_error <= float(maximum_center_error_px) * image_scale
            ),
            "center_px": [round(center_x, 6), round(center_y, 6)],
            "scale": round(float(template_scale), 6),
            "correlation": round(float(peak), 6),
            "expected_center_distance_px": round(center_error, 6),
            "scale_at_search_limit": bool(
                template_scale <= 0.885 or template_scale >= 1.115
            ),
        }
        if best is None or float(candidate["correlation"]) > float(
            best["correlation"]
        ):
            best = candidate
    if best is None:
        return {
            "accepted": False,
            "rejection_reason": "no valid nozzle template search window",
        }
    if not best["accepted"]:
        if float(best["correlation"]) < float(minimum_correlation):
            best["rejection_reason"] = (
                f"nozzle template correlation {float(best['correlation']):.4f} "
                f"is below {float(minimum_correlation):.4f}"
            )
        else:
            best["rejection_reason"] = (
                "nozzle template peak is outside the tool-local search gate"
            )
    else:
        best["rejection_reason"] = ""
    return best


def fit_observation_model(samples: list[dict[str, Any]]) -> dict[str, Any]:
    import numpy as np

    if len(samples) < 8:
        return {
            "ok": False,
            "rejection_reason": "need at least eight accepted XYZ observations",
        }
    design = np.asarray(
        [
            [
                float(sample["pose"]["x"]),
                float(sample["pose"]["y"]),
                float(sample["pose"]["z"]),
                1.0,
            ]
            for sample in samples
        ],
        dtype=float,
    )
    observations = np.asarray([sample["observation"] for sample in samples], dtype=float)
    coefficients, _residuals, rank, _singular = np.linalg.lstsq(
        design, observations, rcond=None
    )
    predicted = design @ coefficients
    errors = observations - predicted
    rms = float(math.sqrt(float(np.mean(np.sum(errors * errors, axis=1)))))
    jacobian = coefficients[:3, :].T
    intercept = coefficients[3, :]
    condition = float(np.linalg.cond(jacobian))
    return {
        "ok": bool(rank == 4 and math.isfinite(condition)),
        "sample_count": len(samples),
        "rank": int(rank),
        "jacobian": jacobian.tolist(),
        "intercept": intercept.tolist(),
        "fit_rms": rms,
        "condition_number": condition,
        "residuals": errors.tolist(),
    }


def _column_relative_spread(first: Any, second: Any) -> float:
    import numpy as np

    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    denominator = max(1.0e-9, (float(np.linalg.norm(a)) + float(np.linalg.norm(b))) / 2)
    return float(np.linalg.norm(a - b) / denominator)


def solve_pass_correction(
    t0_fit: dict[str, Any], t1_fit: dict[str, Any]
) -> dict[str, Any]:
    import numpy as np

    hard_failures: list[str] = []
    if not t0_fit.get("ok") or not t1_fit.get("ok"):
        return {
            "ok": False,
            "hard_failures": ["T0 and T1 observation models are both required"],
        }
    j0 = np.asarray(t0_fit["jacobian"], dtype=float)
    j1 = np.asarray(t1_fit["jacobian"], dtype=float)
    axis_spreads = [
        _column_relative_spread(j0[:, index], j1[:, index]) for index in range(3)
    ]
    for axis, spread in zip("XYZ", axis_spreads):
        if spread > ROUGH_MAX_AXIS_RELATIVE_SPREAD:
            hard_failures.append(
                f"{axis} image-axis relative spread {spread:.4f} exceeds "
                f"{ROUGH_MAX_AXIS_RELATIVE_SPREAD:.4f}"
            )
    jacobian = (j0 + j1) / 2.0
    condition = float(np.linalg.cond(jacobian))
    if condition > ROUGH_MAX_JACOBIAN_CONDITION:
        hard_failures.append(
            f"Jacobian condition {condition:.3f} exceeds "
            f"{ROUGH_MAX_JACOBIAN_CONDITION:.3f}"
        )
    delta = np.asarray(t1_fit["intercept"], dtype=float) - np.asarray(
        t0_fit["intercept"], dtype=float
    )
    try:
        correction = np.linalg.solve(jacobian, delta)
    except np.linalg.LinAlgError:
        hard_failures.append("XYZ image Jacobian is singular")
        correction = np.asarray([math.nan, math.nan, math.nan])
    for axis, value, limit in zip("XYZ", correction, ROUGH_CORRECTION_LIMITS_MM):
        if not math.isfinite(float(value)) or abs(float(value)) > limit:
            hard_failures.append(
                f"{axis} correction {float(value):.4f}mm exceeds ±{limit:.4f}mm"
            )
    predicted_residual = delta - jacobian @ correction
    return {
        "ok": not hard_failures,
        "hard_failures": hard_failures,
        "jacobian": jacobian.tolist(),
        "condition_number": condition,
        "axis_relative_spread": dict(zip(("x", "y", "z"), axis_spreads)),
        "observation_delta_t1_minus_t0": delta.tolist(),
        "correction_mm": {
            "x": float(correction[0]),
            "y": float(correction[1]),
            "z": float(correction[2]),
        },
        "predicted_residual": predicted_residual.tolist(),
    }


def combine_pass_corrections(passes: list[dict[str, Any]]) -> dict[str, Any]:
    hard_failures: list[str] = []
    accepted = [item for item in passes if item.get("ok")]
    if len(accepted) != 2:
        hard_failures.append("two accepted independent passes are required")
        return {"ok": False, "hard_failures": hard_failures, "passes": passes}
    values = {
        axis: [float(item["correction_mm"][axis]) for item in accepted]
        for axis in ("x", "y", "z")
    }
    agreements = {
        axis: abs(axis_values[1] - axis_values[0])
        for axis, axis_values in values.items()
    }
    if agreements["x"] > ROUGH_PASS_X_AGREEMENT_MM:
        hard_failures.append(
            f"X pass disagreement {agreements['x']:.4f}mm exceeds "
            f"{ROUGH_PASS_X_AGREEMENT_MM:.4f}mm"
        )
    for axis in ("y", "z"):
        if agreements[axis] > ROUGH_PASS_YZ_AGREEMENT_MM:
            hard_failures.append(
                f"{axis.upper()} pass disagreement {agreements[axis]:.4f}mm exceeds "
                f"{ROUGH_PASS_YZ_AGREEMENT_MM:.4f}mm"
            )
    correction = {
        axis: statistics.mean(axis_values) for axis, axis_values in values.items()
    }
    return {
        "ok": not hard_failures,
        "hard_failures": hard_failures,
        "passes": passes,
        "pass_agreement_mm": agreements,
        "correction_mm": correction,
    }


def solve_fast_x_pass(
    *,
    t0_motion_gate: dict[str, Any],
    t1_motion_gate: dict[str, Any],
    t0_anchor_x: float,
    t1_anchor_x: float,
    t0_anchor_center_x_px: float,
    t1_anchor_center_x_px: float,
) -> dict[str, Any]:
    hard_failures: list[str] = []
    if not t0_motion_gate.get("ok") or not t1_motion_gate.get("ok"):
        hard_failures.append("both tool-local X trajectories are required")
    slopes = [
        float((gate.get("axis_vector_px_per_mm") or [math.nan])[0])
        for gate in (t0_motion_gate, t1_motion_gate)
    ]
    if not all(math.isfinite(value) and abs(value) >= 2.0 for value in slopes):
        hard_failures.append("tool-local X image scales are unusable")
    elif slopes[0] * slopes[1] <= 0:
        hard_failures.append("tool-local X image scales disagree in sign")
    average_scale = statistics.mean(slopes)
    relative_spread = (
        abs(slopes[1] - slopes[0])
        / max(1.0e-9, statistics.mean(abs(value) for value in slopes))
        if all(math.isfinite(value) for value in slopes)
        else math.inf
    )
    if relative_spread > ROUGH_MAX_AXIS_RELATIVE_SPREAD:
        hard_failures.append(
            f"X image-scale relative spread {relative_spread:.4f} exceeds "
            f"{ROUGH_MAX_AXIS_RELATIVE_SPREAD:.4f}"
        )
    commanded_delta = float(t1_anchor_x) - float(t0_anchor_x)
    image_delta = float(t1_anchor_center_x_px) - float(t0_anchor_center_x_px)
    correction = (
        -commanded_delta + image_delta / average_scale
        if math.isfinite(average_scale) and abs(average_scale) > 1.0e-9
        else math.nan
    )
    if not math.isfinite(correction) or abs(correction) > ROUGH_CORRECTION_LIMITS_MM[0]:
        hard_failures.append(
            f"X correction {correction:.4f}mm exceeds "
            f"±{ROUGH_CORRECTION_LIMITS_MM[0]:.4f}mm"
        )
    return {
        "ok": not hard_failures,
        "hard_failures": hard_failures,
        "correction_mm": correction,
        "commanded_anchor_delta_mm": commanded_delta,
        "image_anchor_delta_px": image_delta,
        "x_scale_px_per_mm": average_scale,
        "tool_x_scales_px_per_mm": {"t0": slopes[0], "t1": slopes[1]},
        "x_scale_relative_spread": relative_spread,
    }


def combine_fast_x_passes(passes: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [item for item in passes if item.get("ok")]
    if len(accepted) != 2:
        return {
            "ok": False,
            "hard_failures": ["two accepted fast X passes are required"],
            "passes": passes,
        }
    values = [float(item["correction_mm"]) for item in accepted]
    disagreement = abs(values[1] - values[0])
    hard_failures = []
    if disagreement > ROUGH_PASS_X_AGREEMENT_MM:
        hard_failures.append(
            f"X pass disagreement {disagreement:.4f}mm exceeds "
            f"{ROUGH_PASS_X_AGREEMENT_MM:.4f}mm"
        )
    return {
        "ok": not hard_failures,
        "hard_failures": hard_failures,
        "passes": passes,
        "pass_agreement_mm": disagreement,
        "correction_mm": statistics.mean(values),
    }


def load_calib_yaml(path: Path) -> dict[str, Any]:
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return payload


def write_calib_candidate(
    *,
    source_path: Path,
    destination: Path,
    correction_mm: dict[str, float] | None = None,
    target_update: tuple[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    import yaml

    source = load_calib_yaml(source_path)
    candidate = copy.deepcopy(source)
    changes: dict[str, Any] = {}
    if correction_mm is not None:
        t1 = candidate["tools"]["t1"]
        old_values = {
            axis: float(t1[f"{axis}_endstop"]) for axis in ("x", "y", "z")
        }
        new_values = {
            axis: round(
                old_values[axis] + float(correction_mm.get(axis, 0.0)),
                3,
            )
            for axis in ("x", "y", "z")
        }
        for axis in ("x", "y", "z"):
            t1[f"{axis}_endstop"] = new_values[axis]
        changes["tools.t1"] = {
            "old": old_values,
            "new": new_values,
            "changed_axes": [
                axis for axis in ("x", "y", "z") if axis in correction_mm
            ],
        }
    if target_update is not None:
        target_name, target_value = target_update
        nozzle_cam = candidate.setdefault("cameras", {}).setdefault("nozzle_cam", {})
        targets = nozzle_cam.setdefault("targets", {})
        old_target = copy.deepcopy(targets.get(target_name))
        targets[target_name] = copy.deepcopy(target_value)
        changes[f"cameras.nozzle_cam.targets.{target_name}"] = {
            "old": old_target,
            "new": copy.deepcopy(target_value),
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(candidate, sort_keys=False)
    destination.write_text(rendered, encoding="utf-8")
    reparsed = yaml.safe_load(destination.read_text(encoding="utf-8"))
    if reparsed != candidate:
        raise RuntimeError("calibration candidate failed YAML round-trip verification")
    return {
        "source_path": str(source_path),
        "source_sha256": sha256_file(source_path),
        "candidate_path": str(destination),
        "candidate_sha256": sha256_file(destination),
        "changes": changes,
    }


def score_eddy_lighting(image: Any) -> dict[str, Any]:
    import cv2
    import numpy as np

    height, width = image.shape[:2]
    sx = width / 1920.0
    sy = height / 1080.0
    x, y, w, h = [
        int(round(value * scale))
        for value, scale in zip(EDDY_LIGHT_ROI_1080, (sx, sy, sx, sy))
    ]
    crop = image[y : y + h, x : x + w]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    clipped_fraction = float(np.mean(gray >= 250))
    shadow_fraction = float(np.mean(gray <= 8))
    contrast = float(np.percentile(gray, 95) - np.percentile(gray, 5))
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    normalized = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(
        cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    )
    scale = (sx + sy) / 2.0
    expected_center = (
        float(EDDY_LIGHT_EXPECTED_CENTER_1080[0] * sx),
        float(EDDY_LIGHT_EXPECTED_CENTER_1080[1] * sy),
    )
    search_x = max(
        2, int(round(EDDY_LIGHT_CENTER_SEARCH_RADIUS_1080[0] * sx))
    )
    search_y = max(
        2, int(round(EDDY_LIGHT_CENTER_SEARCH_RADIUS_1080[1] * sy))
    )
    nominal_radii = [
        max(3, int(round(radius * scale))) for radius in EDDY_LIGHT_RING_RADII_1080
    ]
    max_radius = max(nominal_radii) + max(4, int(round(4 * scale)))
    angles = np.linspace(0.0, 2.0 * math.pi, 180, endpoint=False, dtype=np.float32)
    radii = np.arange(0, max_radius + 3, dtype=np.float32)
    cos_angles = np.cos(angles)[:, None]
    sin_angles = np.sin(angles)[:, None]

    def radial_measurement(center_x: float, center_y: float) -> dict[str, Any]:
        map_x = (center_x + cos_angles * radii[None, :]).astype(np.float32)
        map_y = (center_y + sin_angles * radii[None, :]).astype(np.float32)
        samples = cv2.remap(
            normalized,
            map_x,
            map_y,
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        ).astype(np.float32)
        radial_derivative = 0.5 * np.abs(samples[:, 2:] - samples[:, :-2])
        derivative_mean = radial_derivative.mean(axis=0)
        derivative_std = radial_derivative.std(axis=0)
        coherent_response = derivative_mean * (
            derivative_mean / (derivative_std + 4.0)
        )
        ring_records = []
        tolerance = max(2, int(round(2 * scale)))
        for nominal_radius in nominal_radii:
            first = max(1, nominal_radius - tolerance)
            last = min(len(coherent_response), nominal_radius + tolerance + 1)
            index = first + int(np.argmax(coherent_response[first:last]))
            ring_records.append(
                {
                    "radius_px": float(index + 1),
                    "response": float(coherent_response[index]),
                    "edge_contrast": float(derivative_mean[index]),
                    "radial_coherence": float(
                        derivative_mean[index] / (derivative_std[index] + 4.0)
                    ),
                }
            )
        return {
            "center_px": [float(center_x), float(center_y)],
            "rings": ring_records,
            "radial_strength": float(
                sum(record["response"] for record in ring_records)
            ),
        }

    coarse_step = max(1, int(round(2 * scale)))
    center_x_min = int(round(expected_center[0] - search_x))
    center_x_max = int(round(expected_center[0] + search_x))
    center_y_min = int(round(expected_center[1] - search_y))
    center_y_max = int(round(expected_center[1] + search_y))
    candidates = []
    for center_y in range(center_y_min, center_y_max + 1, coarse_step):
        for center_x in range(center_x_min, center_x_max + 1, coarse_step):
            measurement = radial_measurement(center_x, center_y)
            candidates.append(
                (
                    measurement["radial_strength"],
                    -math.hypot(
                        center_x - expected_center[0],
                        center_y - expected_center[1],
                    ),
                    measurement,
                )
            )
    coarse_best = max(candidates, key=lambda item: (item[0], item[1]))[2]
    coarse_x, coarse_y = coarse_best["center_px"]
    refined = []
    for center_y in range(int(coarse_y) - coarse_step, int(coarse_y) + coarse_step + 1):
        for center_x in range(
            int(coarse_x) - coarse_step, int(coarse_x) + coarse_step + 1
        ):
            measurement = radial_measurement(center_x, center_y)
            refined.append(
                (
                    measurement["radial_strength"],
                    -math.hypot(
                        center_x - expected_center[0],
                        center_y - expected_center[1],
                    ),
                    measurement,
                )
            )
    best = max(refined, key=lambda item: (item[0], item[1]))[2]
    strongest_response = max(
        (float(record["response"]) for record in best["rings"]), default=0.0
    )
    minimum_response = max(3.0, 0.20 * strongest_response)
    accepted_rings = [
        record
        for record in best["rings"]
        if float(record["response"]) >= minimum_response
    ]
    ring_count = len(accepted_rings)
    center = best["center_px"] if ring_count else None
    center_spread = 0.0 if center is not None else None
    radial_strength = float(
        sum(float(record["response"]) for record in accepted_rings)
    )
    radial_symmetry = (
        statistics.mean(float(record["radial_coherence"]) for record in accepted_rings)
        if accepted_rings
        else 0.0
    )
    center_radius = max(3, int(round(7 * scale)))
    center_x = int(round(best["center_px"][0]))
    center_y = int(round(best["center_px"][1]))
    center_patch = normalized[
        max(0, center_y - center_radius) : center_y + center_radius + 1,
        max(0, center_x - center_radius) : center_x + center_radius + 1,
    ]
    cross_sharpness = (
        float(cv2.Laplacian(center_patch, cv2.CV_64F).var())
        if center_patch.size
        else 0.0
    )
    raw_circles = [
        {
            "center_px": list(best["center_px"]),
            "radius_px": float(record["radius_px"]),
            "response": float(record["response"]),
        }
        for record in accepted_rings
    ]
    clipping_penalty = 900.0 * clipped_fraction
    shadow_penalty = 300.0 * shadow_fraction
    score = (
        radial_strength
        + 12.0 * ring_count
        + 0.25 * contrast
        + 8.0 * radial_symmetry
        + 0.002 * min(cross_sharpness, 10000.0)
        - clipping_penalty
        - shadow_penalty
    )
    accepted = (
        ring_count >= 3
        and center is not None
        and clipped_fraction < 0.005
        and shadow_fraction < 0.05
        and math.hypot(
            center[0] - expected_center[0], center[1] - expected_center[1]
        )
        <= max(search_x, search_y)
    )
    return {
        "accepted": accepted,
        "score": score,
        "roi": [x, y, w, h],
        "center_px": center,
        "center_spread_px": center_spread,
        "ring_count": ring_count,
        "circles": raw_circles,
        "clipped_fraction": clipped_fraction,
        "shadow_fraction": shadow_fraction,
        "contrast": contrast,
        "sharpness": sharpness,
        "cross_sharpness": cross_sharpness,
        "radial_strength": radial_strength,
        "radial_symmetry": radial_symmetry,
        "expected_center_px": list(expected_center),
    }


def validate_lighting_duplicates(
    scores: list[dict[str, Any]],
    correlations: list[float] | None = None,
) -> dict[str, Any]:
    hard_failures: list[str] = []
    if len(scores) != 5:
        hard_failures.append("exactly five duplicate frames are required")
    if any(not score.get("accepted") for score in scores):
        hard_failures.append("all duplicate frames must detect the Eddy fiducial")
    centers = [score.get("center_px") for score in scores if score.get("center_px")]
    center_spread = math.inf
    if centers:
        mean_x = statistics.mean(float(center[0]) for center in centers)
        mean_y = statistics.mean(float(center[1]) for center in centers)
        center_spread = max(
            math.hypot(float(center[0]) - mean_x, float(center[1]) - mean_y)
            for center in centers
        )
    if center_spread > 1.0:
        hard_failures.append(
            f"duplicate center spread {center_spread:.3f}px exceeds 1.000px"
        )
    values = [float(score.get("score") or 0.0) for score in scores]
    score_cv = (
        statistics.pstdev(values) / abs(statistics.mean(values))
        if values and abs(statistics.mean(values)) > 1.0e-9
        else math.inf
    )
    if score_cv > 0.10:
        hard_failures.append(
            f"duplicate score variation {score_cv:.3f} exceeds 0.100"
        )
    if any(float(score.get("clipped_fraction") or 0.0) >= 0.005 for score in scores):
        hard_failures.append("duplicate fiducial ROI clipping exceeds 0.5%")
    correlation_min = min(correlations) if correlations else None
    correlation_median = statistics.median(correlations) if correlations else None
    if correlations is not None:
        if len(correlations) != len(scores):
            hard_failures.append(
                "duplicate correlation count does not match duplicate frame count"
            )
        elif correlation_min is None or correlation_min < 0.90:
            hard_failures.append(
                "duplicate fiducial correlation falls below 0.900"
            )
    return {
        "ok": not hard_failures,
        "hard_failures": hard_failures,
        "center_spread_px": center_spread,
        "score_cv": score_cv,
        "correlations": correlations,
        "correlation_min": correlation_min,
        "correlation_median": correlation_median,
    }
