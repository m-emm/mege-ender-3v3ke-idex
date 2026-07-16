#!/usr/bin/env python3
"""Shared bed-Y camera registration and printer-coordinate projection helpers."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any


FEATURE_MODES = ("gray_norm", "clahe", "grad_y", "grad_mag")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def preprocess_image(image: Any, mode: str) -> Any:
    import cv2
    import numpy as np

    if mode not in FEATURE_MODES:
        raise ValueError(f"unknown bed-Y feature mode: {mode}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if mode == "gray_norm":
        feature = gray.astype("float32")
    else:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        if mode == "clahe":
            feature = clahe.astype("float32")
        elif mode == "grad_y":
            feature = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
        else:
            grad_x = cv2.Sobel(clahe, cv2.CV_32F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(clahe, cv2.CV_32F, 0, 1, ksize=3)
            feature = cv2.magnitude(grad_x, grad_y)
    feature = feature.astype("float32")
    std = float(feature.std())
    if std <= 1.0e-6:
        return np.zeros(feature.shape, dtype="float32")
    return (feature - float(feature.mean())) / std


def subpixel_peak_offset(
    response: Any, max_loc: tuple[int, int]
) -> tuple[float, float]:
    x, y = max_loc
    height, width = response.shape[:2]

    def axis_offset(v0: float, v_minus: float, v_plus: float) -> float:
        denominator = v_minus - 2.0 * v0 + v_plus
        if abs(denominator) < 1.0e-9:
            return 0.0
        offset = 0.5 * (v_minus - v_plus) / denominator
        return max(-1.0, min(1.0, float(offset)))

    center = float(response[y, x])
    dx = 0.0
    dy = 0.0
    if 0 < x < width - 1:
        dx = axis_offset(center, float(response[y, x - 1]), float(response[y, x + 1]))
    if 0 < y < height - 1:
        dy = axis_offset(center, float(response[y - 1, x]), float(response[y + 1, x]))
    return dx, dy


def project_pixel_to_y(
    *,
    pixel: tuple[float, float],
    reference_pixel: tuple[float, float],
    reference_y_mm: float,
    axis_vector_px_per_mm: tuple[float, float],
) -> dict[str, float]:
    vx, vy = axis_vector_px_per_mm
    denominator = vx * vx + vy * vy
    if denominator <= 1.0e-12:
        raise ValueError("bed-Y axis vector must be non-zero")
    dx = float(pixel[0]) - float(reference_pixel[0])
    dy = float(pixel[1]) - float(reference_pixel[1])
    delta_y_mm = (dx * vx + dy * vy) / denominator
    scale = math.sqrt(denominator)
    cross_axis_px = (dx * -vy + dy * vx) / scale
    return {
        "measured_y_mm": float(reference_y_mm) + delta_y_mm,
        "delta_y_mm": delta_y_mm,
        "cross_axis_px": cross_axis_px,
    }


def expected_pixel_for_y(
    *,
    expected_y_mm: float,
    reference_y_mm: float,
    reference_pixel: tuple[float, float],
    axis_vector_px_per_mm: tuple[float, float],
) -> tuple[float, float]:
    delta_y = float(expected_y_mm) - float(reference_y_mm)
    return (
        float(reference_pixel[0]) + float(axis_vector_px_per_mm[0]) * delta_y,
        float(reference_pixel[1]) + float(axis_vector_px_per_mm[1]) * delta_y,
    )


def match_template(
    *,
    image: Any,
    template_image: Any,
    expected_anchor_px: tuple[float, float],
    axis_vector_px_per_mm: tuple[float, float],
    feature_mode: str,
    search_radius_mm: float,
    cross_axis_margin_px: float,
) -> dict[str, Any]:
    import cv2

    image_feature = preprocess_image(image, feature_mode)
    template_feature = preprocess_image(template_image, feature_mode)
    image_height, image_width = image_feature.shape[:2]
    template_height, template_width = template_feature.shape[:2]
    texture_std = float(template_feature.std())
    if texture_std <= 0.015:
        raise ValueError(
            "bed-Y reference template has too little texture "
            f"(std={texture_std:.5f})"
        )

    vx, vy = (float(value) for value in axis_vector_px_per_mm)
    axis_scale = math.hypot(vx, vy)
    if axis_scale <= 1.0e-9:
        raise ValueError("bed-Y axis vector must be non-zero")
    axis_x, axis_y = vx / axis_scale, vy / axis_scale
    perp_x, perp_y = -axis_y, axis_x
    along_px = abs(float(search_radius_mm)) * axis_scale
    cross_px = abs(float(cross_axis_margin_px))
    pad_x = abs(axis_x) * along_px + abs(perp_x) * cross_px
    pad_y = abs(axis_y) * along_px + abs(perp_y) * cross_px

    expected_x = float(expected_anchor_px[0]) - template_width / 2.0
    expected_y = float(expected_anchor_px[1]) - template_height / 2.0
    x0 = max(0, int(math.floor(expected_x - pad_x)))
    y0 = max(0, int(math.floor(expected_y - pad_y)))
    x1 = min(
        image_width,
        int(math.ceil(expected_x + template_width + pad_x)),
    )
    y1 = min(
        image_height,
        int(math.ceil(expected_y + template_height + pad_y)),
    )
    search = image_feature[y0:y1, x0:x1]
    if search.shape[0] < template_height or search.shape[1] < template_width:
        raise ValueError("bed-Y template search window is smaller than the template")

    response = cv2.matchTemplate(
        search.astype("float32"),
        template_feature.astype("float32"),
        cv2.TM_CCOEFF_NORMED,
    )
    _min_value, max_value, _min_loc, max_loc = cv2.minMaxLoc(response)
    sub_x, sub_y = subpixel_peak_offset(response, max_loc)
    matched_x = float(x0 + max_loc[0]) + sub_x
    matched_y = float(y0 + max_loc[1]) + sub_y
    anchor = (
        matched_x + template_width / 2.0,
        matched_y + template_height / 2.0,
    )
    return {
        "correlation": float(max_value),
        "anchor_px": [float(anchor[0]), float(anchor[1])],
        "match_roi": [matched_x, matched_y, template_width, template_height],
        "search_roi": [x0, y0, x1 - x0, y1 - y0],
        "texture_std": texture_std,
    }
