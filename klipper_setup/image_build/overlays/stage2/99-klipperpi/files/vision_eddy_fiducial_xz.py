#!/usr/bin/env python3
"""Eddy fiducial X/Z grid analysis — SIFT body localisation + Hough circle detection."""

from __future__ import annotations

import hashlib
import logging
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

_logger = logging.getLogger(__name__)
# ---------------------------------------------------------------------------
# Frozen SIFT template — committed PNG of the BTT Eddy sensor body crop.
# Deployed to /usr/local/share/vision/eddy_sift_body_template.png.
# ---------------------------------------------------------------------------
_SIFT_TEMPLATE_PATH = Path("/usr/local/share/vision/eddy_sift_body_template.png")
_SIFT_LOWE_RATIO = 0.75
_SIFT_MIN_INLIERS = 8


class EddyFiducialError(RuntimeError):
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


def _gradient_image(gray: np.ndarray) -> np.ndarray:
    """Return an illumination-resistant structural image."""

    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)

    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)

    magnitude = cv2.magnitude(gx, gy)

    # Convert to uint8 for compact storage and fast template matching.

    return cv2.normalize(
        magnitude,
        None,
        0,
        255,
        cv2.NORM_MINMAX,
        dtype=cv2.CV_8U,
    )


def locate_body_template(
    frame: np.ndarray,
    template_gray: np.ndarray,
    *,
    scales: tuple[float, ...] = (
        0.80,
        0.85,
        0.90,
        0.95,
        1.00,
        1.05,
        1.10,
        1.15,
        1.20,
    ),
    min_score: float = 0.45,
) -> tuple[int, int, int, int] | None:
    """Locate the Eddy body using multi-scale gradient template matching."""

    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    frame_features = _gradient_image(frame_gray)

    template_features = _gradient_image(template_gray)

    frame_h, frame_w = frame_features.shape

    best_score = -1.0

    best_rect: tuple[int, int, int, int] | None = None

    for scale in scales:

        template_w = round(template_features.shape[1] * scale)

        template_h = round(template_features.shape[0] * scale)

        if template_w < 16 or template_h < 16:

            continue

        if template_w > frame_w or template_h > frame_h:

            continue

        scaled_template = cv2.resize(
            template_features,
            (template_w, template_h),
            interpolation=(cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR),
        )

        response = cv2.matchTemplate(
            frame_features,
            scaled_template,
            cv2.TM_CCOEFF_NORMED,
        )

        _, score, _, location = cv2.minMaxLoc(response)

        if score > best_score:

            x, y = location

            best_score = score

            best_rect = (x, y, x + template_w, y + template_h)

    if best_rect is None or best_score < min_score:

        return None

    return best_rect


def _load_gray_template() -> np.ndarray:
    template_gray = cv2.imread(
        str(_SIFT_TEMPLATE_PATH),
        cv2.IMREAD_GRAYSCALE,
    )
    if template_gray is None:
        raise EddyFiducialError(f"Cannot load body template {_SIFT_TEMPLATE_PATH}")
    return template_gray


template_gray = _load_gray_template()


def _load_sift_template() -> tuple[list, np.ndarray, int, int] | None:
    """Load the frozen sensor-body SIFT template from the sibling PNG.

    Returns (keypoints, descriptors, template_w, template_h) or None if the
    template file is absent or cannot be decoded.
    """
    if not _SIFT_TEMPLATE_PATH.is_file():
        return None
    crop = cv2.imread(str(_SIFT_TEMPLATE_PATH), cv2.IMREAD_COLOR)
    if crop is None:
        return None
    sift = cv2.SIFT_create(
        nfeatures=1500,
        nOctaveLayers=3,
        contrastThreshold=0.04,
        edgeThreshold=10,
        sigma=1.6,
    )
    kp, des = sift.detectAndCompute(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), None)
    if des is None or len(kp) < 4:
        return None
    h, w = crop.shape[:2]
    return kp, des, w, h


def _sift_body_roi(
    frame: np.ndarray,
    template_kp: list,
    template_des: np.ndarray,
    template_w: int,
    template_h: int,
) -> tuple[int, int, int, int] | None:
    """Match the sensor-body template against *frame* via SIFT + RANSAC.

    Returns an axis-aligned bounding rect (x0, y0, x1, y1) in full-frame
    coordinates that tightly contains the projected template, or None when
    fewer than _SIFT_MIN_INLIERS inliers survive.
    """
    _logger.info("Creating SIFT detector for body localisation")
    sift = cv2.SIFT_create()

    _logger.info("SIFT detector created")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    _logger.info("Detecting SIFT keypoints in frame")
    kp2, des2 = sift.detectAndCompute(gray, None)
    if des2 is None or len(kp2) < 4:
        raise EddyFiducialError("SIFT body detection failed — insufficient keypoints")
    bf = cv2.BFMatcher(cv2.NORM_L2)

    _logger.info("Matching SIFT template against frame")

    raw = bf.knnMatch(template_des, des2, k=2)
    good = [
        m
        for m, n in raw
        if len([m, n]) == 2 and m.distance < _SIFT_LOWE_RATIO * n.distance
    ]
    if len(good) < _SIFT_MIN_INLIERS:
        raise EddyFiducialError(
            f"SIFT body detection failed — only {len(good)} inliers"
        )
    _logger.info(f"Found {len(good)} SIFT inliers for body localisation")
    src_pts = np.float32([template_kp[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    if M is None:
        raise EddyFiducialError(
            "SIFT body detection failed — homography could not be computed"
        )
    if mask is not None and int(np.sum(mask)) < _SIFT_MIN_INLIERS:
        raise EddyFiducialError(
            f"SIFT body detection failed — only {int(np.sum(mask))} inliers"
        )
    corners = np.float32(
        [[0, 0], [template_w, 0], [template_w, template_h], [0, template_h]]
    ).reshape(-1, 1, 2)
    projected = cv2.perspectiveTransform(corners, M).reshape(-1, 2)
    fh, fw = frame.shape[:2]
    x0 = max(0, int(np.floor(np.min(projected[:, 0]))))
    y0 = max(0, int(np.floor(np.min(projected[:, 1]))))
    x1 = min(fw, int(np.ceil(np.max(projected[:, 0]))))
    y1 = min(fh, int(np.ceil(np.max(projected[:, 1]))))
    if x1 <= x0 or y1 <= y0:
        raise EddyFiducialError("SIFT body ROI is degenerate")
    return x0, y0, x1, y1


def _blob_anchor(diff_gray: np.ndarray, scale: float) -> np.ndarray | None:
    """Find the centroid of the largest foreground blob in a background-diff image.

    Returns a (x, y) array in full-frame coordinates, or None if no clear blob
    is found.  The blob is the Eddy sensor body — anything that moved between
    this frame and the temporal median background.
    """
    _, mask = cv2.threshold(diff_gray, 18, 255, cv2.THRESH_BINARY)
    k_radius = max(5, int(round(11.0 * scale)))
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (k_radius * 2 + 1, k_radius * 2 + 1)
    )
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    n, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return None
    # Pick the largest foreground component (label 0 is background)
    lbl = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if float(stats[lbl, cv2.CC_STAT_AREA]) < 400.0 * scale * scale:
        return None
    return np.asarray(centroids[lbl], dtype=np.float64)


def _circle_edge_score(gray: np.ndarray, center: np.ndarray, radius: float) -> float:
    angles = np.linspace(0.0, 2.0 * math.pi, 180, endpoint=False)
    radial_means = []
    radial_spreads = []
    for radius_scale in (0.82, 0.94, 1.06, 1.18):
        xs = np.rint(center[0] + radius * radius_scale * np.cos(angles)).astype(int)
        ys = np.rint(center[1] + radius * radius_scale * np.sin(angles)).astype(int)
        valid = (xs >= 0) & (xs < gray.shape[1]) & (ys >= 0) & (ys < gray.shape[0])
        if int(np.count_nonzero(valid)) < 150:
            return 0.0
        values = gray[ys[valid], xs[valid]].astype(np.float64)
        radial_means.append(float(np.mean(values)))
        radial_spreads.append(float(np.std(values)))
    edge_contrast = float(np.sum(np.abs(np.diff(radial_means))))
    asymmetry = float(np.median(radial_spreads))
    return edge_contrast - 0.12 * asymmetry


def detect_circle(
    image: np.ndarray,
    localizer: dict[str, Any],
    *,
    expected_center_px: list[float] | np.ndarray | None = None,
    background: np.ndarray | None = None,
    sift_roi: tuple[int, int, int, int] | None = None,
) -> dict[str, Any]:
    """Find the Eddy fiducial circle.

    Two-stage strategy
    ------------------
    Stage 1 — ROI:
      When *sift_roi* (x0,y0,x1,y1) is supplied (from SIFT body localisation),
      it is used directly as the Hough crop.  The centre of the ROI becomes the
      anchor for distance filtering.

      Falls back to the blob-anchor (background subtraction) or
      ``localizer["expected_center_1080"]`` when sift_roi is None.

    Stage 2 — Hough:
      Hough circle detection runs on the original (not the diff) image crop to
      get accurate ring edges, with radius limited to the crosshair-logo range.
    """
    if image.ndim != 3 or image.shape[2] != 3:
        raise EddyFiducialError("Eddy fiducial detector requires a BGR image")
    height, width = image.shape[:2]
    scale = min(width / 1920.0, height / 1080.0)

    blob_anchor: np.ndarray | None = None

    if sift_roi is not None:
        # --- Stage 1a: SIFT body bbox drives the crop directly ---------------
        x0, y0, x1, y1 = sift_roi
        anchor = np.asarray([(x0 + x1) / 2.0, (y0 + y1) / 2.0], dtype=np.float64)
        # Accept any circle whose centre lies within the projected ROI
        max_dist = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2) / 2.0
    else:
        # --- Stage 1b: anchor via temporal background subtraction (fallback) -
        if background is not None and background.shape == image.shape:
            diff = np.clip(
                image.astype(np.float32) - background.astype(np.float32),
                0.0,
                255.0,
            ).astype(np.uint8)
            diff_gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            blob_anchor = _blob_anchor(diff_gray, scale)

        if blob_anchor is not None:
            anchor = blob_anchor
        elif expected_center_px is not None:
            anchor = np.asarray(expected_center_px, dtype=np.float64)
        else:
            anchor_1080 = localizer["expected_center_1080"]
            anchor = np.asarray(
                [anchor_1080[0] * width / 1920.0, anchor_1080[1] * height / 1080.0],
                dtype=np.float64,
            )

        half = int(round(float(localizer.get("search_radius_1080", 130.0)) * scale))
        cx, cy = int(round(anchor[0])), int(round(anchor[1]))
        x0 = max(0, cx - half)
        y0 = max(0, cy - half)
        x1 = min(width, cx + half)
        y1 = min(height, cy + half)
        max_dist = (
            float(localizer.get("max_distance_from_expected_1080", 110.0)) * scale
        )

    # --- Stage 2: Hough on image crop defined by the ROI ------------------------
    crop = image[y0:y1, x0:x1]

    gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    normalized = cv2.createCLAHE(2.0, (8, 8)).apply(gray_crop)
    blurred = cv2.GaussianBlur(normalized, (7, 7), 1.5)

    radius_range = localizer["radius_range_1080"]
    minimum_radius = max(8, int(round(float(radius_range[0]) * scale)))
    maximum_radius = max(minimum_radius + 2, int(round(float(radius_range[1]) * scale)))
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.15,
        minDist=max(20.0, 40.0 * scale),
        param1=100,
        param2=float(localizer.get("hough_threshold", 22.0)),
        minRadius=minimum_radius,
        maxRadius=maximum_radius,
    )
    if circles is None:
        return {
            "accepted": False,
            "reason": "no circle candidates",
            "candidates": [],
            "blob_anchor_px": blob_anchor.tolist() if blob_anchor is not None else None,
            "sift_roi_px": list(sift_roi) if sift_roi is not None else None,
        }

    full_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    center_weight = float(localizer.get("center_weight", 0.03)) / max(scale, 1e-9)
    candidates = []
    for local_x, local_y, radius in circles[0]:
        center = np.asarray([local_x + x0, local_y + y0], dtype=np.float64)
        distance = float(np.linalg.norm(center - anchor))
        if distance > max_dist:
            continue
        edge_score = _circle_edge_score(full_gray, center, float(radius))
        candidates.append(
            {
                "center_px": center.tolist(),
                "radius_px": float(radius),
                "edge_score": edge_score,
                "distance_from_expected_px": distance,
                "selection_score": edge_score - center_weight * distance,
            }
        )
    if not candidates:
        return {
            "accepted": False,
            "reason": "no candidates within search radius",
            "candidates": [],
            "blob_anchor_px": blob_anchor.tolist() if blob_anchor is not None else None,
            "sift_roi_px": list(sift_roi) if sift_roi is not None else None,
        }
    candidates.sort(key=lambda item: float(item["selection_score"]), reverse=True)
    selected = candidates[0]
    minimum_edge_score = float(localizer.get("minimum_edge_score", 6.0))
    return {
        "accepted": float(selected["edge_score"]) >= minimum_edge_score,
        "reason": (
            None
            if float(selected["edge_score"]) >= minimum_edge_score
            else "best circle has insufficient circular edge contrast"
        ),
        "blob_anchor_px": blob_anchor.tolist() if blob_anchor is not None else None,
        "sift_roi_px": list(sift_roi) if sift_roi is not None else None,
        **selected,
        "candidates": candidates[:8],
    }


def analyze(
    frame_paths: list[Path],
    artifact_dir: Path,
    *,
    frames: list[dict[str, Any]],
    localizer: dict[str, Any],
) -> dict[str, Any]:
    """Measure the Eddy fiducial image center for every commanded X/Z pose.

    Images are read one at a time.  SIFT body localisation drives the crop
    for each Hough circle search; no background image is needed.
    """

    _logger.info(f"analyzing {len(frames)} Eddy fiducial X/Z frames in {artifact_dir}")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if len(frame_paths) != len(frames):
        raise EddyFiducialError("Eddy frame paths do not match the manifest")

    # --- Per-frame detection and circle overlays (one image at a time) ----------
    records = []
    expected_center: np.ndarray | None = None
    panels_overlay: list[np.ndarray] = []
    image_dimensions: list[int] | None = None
    artifacts: dict[str, Any] = {}

    for path, frame in zip(frame_paths, frames):
        _logger.info(f"Loading frame {frame['seq']} from {path}")

        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        _logger.info(f"Loaded frame {frame['seq']} from {path}")
        if image is None:
            raise EddyFiducialError(f"Eddy image {frame['seq']} cannot be decoded")
        dimensions = [int(image.shape[1]), int(image.shape[0])]
        if image_dimensions is None:
            image_dimensions = dimensions
        elif dimensions != image_dimensions:
            raise EddyFiducialError("Eddy grid images have inconsistent dimensions")

        body_rect = locate_body_template(image, template_gray)

        if body_rect is None:
            continue
            # raise EddyFiducialError("Could not locate Eddy body")

        x0, y0, x1, y1 = body_rect

        detection = detect_circle(
            image,
            localizer,
            expected_center_px=expected_center,
            sift_roi=(x0, y0, x1, y1),
        )
        if detection["accepted"]:
            expected_center = np.asarray(detection["center_px"], dtype=np.float64)

        center = detection.get("center_px")
        sift_roi_record = detection["sift_roi_px"]
        record = {
            "seq": int(frame["seq"]),
            "commanded_x_mm": float(frame["x_mm"]),
            "commanded_z_mm": float(frame["z_mm"]),
            "image_x_px": float(center[0]) if center is not None else None,
            "image_y_px": float(center[1]) if center is not None else None,
            "detected": bool(detection["accepted"]),
            "radius_px": detection.get("radius_px"),
            "edge_score": detection.get("edge_score"),
            "sift_roi_px": sift_roi_record,
            "rejection_reason": detection.get("reason"),
        }
        records.append(record)

        status_text = (
            f"X={record['commanded_x_mm']:.3f} "
            f"Z={record['commanded_z_mm']:.3f} "
            f"{'detected' if record['detected'] else 'MISSED'}"
        )
        draw_color = (0, 255, 0) if record["detected"] else (0, 0, 255)

        overlay = image.copy()
        rx0, ry0, rx1, ry1 = sift_roi_record

        _logger.info(
            f"Drawing rectangle overlay for frame {frame['seq']}: ({rx0}, {ry0}) to ({rx1}, {ry1})"
        )
        cv2.rectangle(overlay, (rx0, ry0), (rx1, ry1), (0, 230, 230), 2)
        if center is not None:
            center_point = tuple(np.rint(center).astype(int))
            cv2.circle(
                overlay,
                center_point,
                int(round(float(detection["radius_px"]))),
                draw_color,
                3,
            )
            cv2.drawMarker(overlay, center_point, draw_color, cv2.MARKER_CROSS, 24, 3)
        cv2.putText(
            overlay,
            status_text,
            (24, 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            draw_color,
            2,
            cv2.LINE_AA,
        )

        overlay_path = artifact_dir / f"{frame['frame']}_eddy_circle.png"
        if not cv2.imwrite(str(overlay_path), overlay):
            raise EddyFiducialError(f"could not write overlay {overlay_path}")

        _logger.info(f"Saved overlay for frame {frame['seq']} to {overlay_path}")
        artifacts[f"eddy_circle_overlay_{int(frame['seq']):02d}"] = _artifact(
            overlay_path
        )
        panels_overlay.append(
            cv2.resize(overlay, (480, 270), interpolation=cv2.INTER_AREA)
        )
        # image and overlay go out of scope here — GC reclaims the memory

    # --- Contact sheet (4 columns) ----------------------------------------------
    def _contact_sheet(panels: list[np.ndarray], path: Path) -> None:
        rows = []
        for start in range(0, len(panels), 4):
            row = panels[start : start + 4]
            while len(row) < 4:
                row.append(np.zeros_like(panels[0]))
            rows.append(cv2.hconcat(row))
        if not cv2.imwrite(str(path), cv2.vconcat(rows)):
            raise EddyFiducialError(f"could not write contact sheet {path}")

    contact_overlay_path = artifact_dir / "eddy_fiducial_xz_grid.jpg"
    _contact_sheet(panels_overlay, contact_overlay_path)
    artifacts["eddy_fiducial_xz_grid"] = _artifact(contact_overlay_path)

    # --- Result -----------------------------------------------------------------
    missing = [record["seq"] for record in records if not record["detected"]]
    reasons = (
        []
        if not missing
        else ["Eddy fiducial not detected in frames " + ", ".join(map(str, missing))]
    )
    raw_positions = [
        {
            "commanded_x_mm": record["commanded_x_mm"],
            "commanded_z_mm": record["commanded_z_mm"],
            "image_x_px": record["image_x_px"],
            "image_y_px": record["image_y_px"],
        }
        for record in records
    ]
    return _finite(
        {
            "accepted": not reasons,
            "reasons": reasons,
            "warnings": [],
            "raw_positions": raw_positions,
            "records": records,
            "image_dimensions_px": image_dimensions,
            "artifacts": artifacts,
        }
    )
