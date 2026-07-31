#!/usr/bin/env python3
"""Diagnostic: use the whole BTT Eddy sensor body as a SIFT template for ROI finding.

Step 1: crop the sensor body from a chosen reference frame.
Step 2: compute SIFT keypoints + descriptors on that crop.
Step 3: match against all 16 frames with BFMatcher + Lowe ratio test + RANSAC.
Step 4: draw the projected bounding box and the derived centre on each frame.
Step 5: write per-frame overlays + contact sheet.

Usage:
    python scripts/debug_eddy_sift_body.py                # reference frame only
    python scripts/debug_eddy_sift_body.py --all-frames   # all 16 frames
    python scripts/debug_eddy_sift_body.py --x0 640 --y0 130 --x1 1000 --y1 460
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


FRAMES_DIR = Path(
    "resources/vision_datasets/20260731_eddy_fiducial_xz_once/frames"
)
REFERENCE_FRAME = FRAMES_DIR / "00_eddy_x230p000_z0p500.jpg"

# Sensor body bounding box in the reference frame (image pixels, 1920×1080).
# Covers the full gray rectangular housing including the crosshair logo.
DEFAULT_X0, DEFAULT_Y0 = 640, 130
DEFAULT_X1, DEFAULT_Y1 = 1000, 460

LOWE_RATIO = 0.75
MIN_INLIERS = 8   # minimum RANSAC inliers to declare a match


def _crop(image: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    h, w = image.shape[:2]
    return image[max(0, y0) : min(h, y1), max(0, x0) : min(w, x1)].copy()


def _sift_match(
    template_gray: np.ndarray,
    kp1: list,
    des1: np.ndarray,
    image: np.ndarray,
    *,
    lowe_ratio: float,
    min_inliers: int,
) -> tuple[bool, np.ndarray | None, list, int]:
    """Return (found, homography_M, good_matches, n_inliers)."""
    sift = cv2.SIFT_create()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    kp2, des2 = sift.detectAndCompute(gray, None)

    if des2 is None or len(kp2) < 4:
        return False, None, [], 0

    bf = cv2.BFMatcher(cv2.NORM_L2)
    raw = bf.knnMatch(des1, des2, k=2)
    good = [m for m, n in raw if len([m, n]) == 2 and m.distance < lowe_ratio * n.distance]

    if len(good) < min_inliers:
        return False, None, good, 0

    src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

    if M is None:
        return False, None, good, 0

    n_inliers = int(np.sum(mask)) if mask is not None else 0
    return n_inliers >= min_inliers, M, good, n_inliers


def _project_box(
    M: np.ndarray,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    body_x0: int,
    body_y0: int,
) -> tuple[np.ndarray, tuple[int, int]]:
    """Project template corners and centre back into full-frame coordinates.

    The SIFT keypoints were detected in the *crop* coordinate system (origin at
    top-left of the crop).  The homography M maps those crop coordinates to
    full-frame coordinates of the *target* frame directly — no further offset
    needed.
    """
    w = x1 - x0
    h = y1 - y0
    corners_crop = np.float32(
        [[0, 0], [w, 0], [w, h], [0, h]]
    ).reshape(-1, 1, 2)
    # M maps crop-space → full-frame-space already
    corners_full = cv2.perspectiveTransform(corners_crop, M)
    cx = float(np.mean(corners_full[:, 0, 0]))
    cy = float(np.mean(corners_full[:, 0, 1]))
    return corners_full.reshape(-1, 2).astype(int), (int(round(cx)), int(round(cy)))


def _draw_result(
    image: np.ndarray,
    found: bool,
    corners: np.ndarray | None,
    center: tuple[int, int] | None,
    good_matches: list,
    n_inliers: int,
    n_kp_frame: int,
    label: str,
) -> np.ndarray:
    out = image.copy()
    color_ok = (0, 230, 0)
    color_fail = (0, 60, 255)
    color = color_ok if found else color_fail

    if found and corners is not None and center is not None:
        cv2.polylines(out, [corners.reshape(-1, 1, 2)], True, color_ok, 3)
        cv2.drawMarker(out, center, color_ok, cv2.MARKER_CROSS, 50, 3)
        cv2.circle(out, center, 8, color_ok, -1)
        cv2.putText(
            out,
            f"FOUND  inliers={n_inliers}  matches={len(good_matches)}  center=({center[0]},{center[1]})",
            (24, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.80,
            color_ok,
            2,
            cv2.LINE_AA,
        )
    else:
        cv2.putText(
            out,
            f"NOT FOUND  matches={len(good_matches)}  inliers={n_inliers}  kp={n_kp_frame}",
            (24, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.80,
            color_fail,
            2,
            cv2.LINE_AA,
        )

    cv2.putText(
        out, label,
        (24, 86),
        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 0), 2, cv2.LINE_AA,
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--x0", type=int, default=DEFAULT_X0)
    ap.add_argument("--y0", type=int, default=DEFAULT_Y0)
    ap.add_argument("--x1", type=int, default=DEFAULT_X1)
    ap.add_argument("--y1", type=int, default=DEFAULT_Y1)
    ap.add_argument("--lowe-ratio", type=float, default=LOWE_RATIO)
    ap.add_argument("--min-inliers", type=int, default=MIN_INLIERS)
    ap.add_argument("--all-frames", action="store_true")
    ap.add_argument("--out-dir", default="output/debug_eddy_sift_body", type=Path)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Build template from reference frame -----------------------------------
    ref_img = cv2.imread(str(REFERENCE_FRAME), cv2.IMREAD_COLOR)
    assert ref_img is not None, f"Cannot read {REFERENCE_FRAME}"

    body_crop = _crop(ref_img, args.x0, args.y0, args.x1, args.y1)
    tmpl_path = out_dir / "template_body.png"
    cv2.imwrite(str(tmpl_path), body_crop)

    sift = cv2.SIFT_create()
    tmpl_gray = cv2.cvtColor(body_crop, cv2.COLOR_BGR2GRAY)
    kp1, des1 = sift.detectAndCompute(tmpl_gray, None)
    assert des1 is not None and len(kp1) >= 4, "Too few SIFT keypoints in template"

    # Visualise keypoints on the template crop
    kp_vis = cv2.drawKeypoints(
        body_crop, kp1, None, flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS
    )
    cv2.imwrite(str(out_dir / "template_body_keypoints.png"), kp_vis)

    print(f"Template body crop ({body_crop.shape[1]}×{body_crop.shape[0]} px): {tmpl_path.resolve()}")
    print(f"SIFT keypoints in template: {len(kp1)}")
    print(f"Keypoint visualisation: {(out_dir / 'template_body_keypoints.png').resolve()}")

    # --- Match against frames --------------------------------------------------
    frame_paths = sorted(FRAMES_DIR.glob("*.jpg")) if args.all_frames else [REFERENCE_FRAME]
    panels: list[np.ndarray] = []
    results = []

    for frame_path in frame_paths:
        img = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        assert img is not None

        # SIFT keypoints in full frame (needed for match count display)
        sift_frame = cv2.SIFT_create()
        kp_frame, _ = sift_frame.detectAndCompute(
            cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), None
        )

        found, M, good, n_inliers = _sift_match(
            tmpl_gray, kp1, des1, img,
            lowe_ratio=args.lowe_ratio,
            min_inliers=args.min_inliers,
        )

        corners = center = None
        if found and M is not None:
            corners, center = _project_box(
                M, args.x0, args.y0, args.x1, args.y1, args.x0, args.y0
            )

        stem = frame_path.stem
        overlay = _draw_result(
            img, found, corners, center,
            good, n_inliers, len(kp_frame), stem,
        )
        overlay_path = out_dir / f"{stem}_sift_body.png"
        cv2.imwrite(str(overlay_path), overlay)

        status = "FOUND" if found else "NOT FOUND"
        cx_str = f"  center=({center[0]},{center[1]})" if center else ""
        print(
            f"{stem}  {status}  inliers={n_inliers}  good={len(good)}"
            f"  kp_frame={len(kp_frame)}{cx_str}"
        )
        print(f"  {overlay_path.resolve()}")

        results.append((stem, found, n_inliers, center))
        panels.append(cv2.resize(overlay, (480, 270), interpolation=cv2.INTER_AREA))

    # --- Contact sheet ---------------------------------------------------------
    if len(panels) > 1:
        rows = []
        for start in range(0, len(panels), 4):
            row = panels[start : start + 4]
            while len(row) < 4:
                row.append(np.zeros_like(panels[0]))
            rows.append(cv2.hconcat(row))
        sheet_path = out_dir / "contact_sheet.jpg"
        cv2.imwrite(str(sheet_path), cv2.vconcat(rows))
        print(f"\nContact sheet: {sheet_path.resolve()}")

    found_count = sum(1 for _, f, *_ in results if f)
    print(f"\nSummary: {found_count}/{len(results)} frames detected")
    print(f"Lowe ratio={args.lowe_ratio}  min_inliers={args.min_inliers}")
    print(f"Template body region: x=[{args.x0},{args.x1}]  y=[{args.y0},{args.y1}]")


if __name__ == "__main__":
    main()
