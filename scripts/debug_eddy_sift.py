#!/usr/bin/env python3
"""Diagnostic: SIFT feature matching to locate the BTT Eddy crosshair logo.

By default generates a clean synthetic crosshair logo at high resolution (many
SIFT keypoints, no camera noise) then matches it against each frame.  The
synthetic template is also written to output/debug_eddy_sift/template_synthetic.png
for inspection.

Alternatively supply a real-image crop with --template.

Usage:
    python scripts/debug_eddy_sift.py                # reference frame, synthetic template
    python scripts/debug_eddy_sift.py --all-frames   # all 16 captured frames
    python scripts/debug_eddy_sift.py --template path/to/crop.png --all-frames
    python scripts/debug_eddy_sift.py --synth-size 600 --all-frames
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

# Center of the BTT crosshair logo in the reference frame (from Hough r=28).
LOGO_CENTER_XY = (901, 297)
TEMPLATE_HALF = 55          # Half-side of the square template crop (px)

LOWE_RATIO = 0.75           # Lowe's ratio-test threshold
MIN_GOOD_MATCHES = 4        # Minimum matches needed for homography
SYNTH_SIZE = 500            # Side length (px) of the synthetic template


def _extract_template(image: np.ndarray, cx: int, cy: int, half: int) -> np.ndarray:
    x0 = max(0, cx - half)
    y0 = max(0, cy - half)
    x1 = min(image.shape[1], cx + half)
    y1 = min(image.shape[0], cy + half)
    return image[y0:y1, x0:x1].copy()


def _make_synthetic_template(size: int = SYNTH_SIZE) -> np.ndarray:
    """Render a high-res synthetic BTT Eddy crosshair logo (ring + 4-segment cross).

    The geometry matches the logo visible on the sensor face:
    - Dark gray sensor-face background
    - Bright outer ring
    - 4 radial line segments from the ring toward the centre, leaving a small gap
    - Tiny centre dot
    - Optional faint inner ring

    At *size* = 500 px, SIFT finds ~200+ keypoints; at 200 px it finds ~40.
    Larger is better for matching quality.
    """
    img = np.full((size, size, 3), 38, dtype=np.uint8)   # dark gray background
    cx, cy = size // 2, size // 2

    outer_r      = int(round(size * 0.38))
    ring_thick   = max(3, int(round(size * 0.065)))
    line_thick   = max(2, int(round(size * 0.022)))
    inner_gap    = int(round(size * 0.11))               # gap around centre
    centre_dot_r = max(2, int(round(size * 0.025)))
    inner_r      = int(round(size * 0.17))
    inner_thick  = max(2, int(round(size * 0.022)))

    bright = (218, 218, 218)
    dim    = (160, 160, 160)

    # Outer ring
    cv2.circle(img, (cx, cy), outer_r, bright, ring_thick, cv2.LINE_AA)

    # Crosshair: 4 line segments (H left, H right, V top, V bottom)
    inset = ring_thick // 2
    for pt_a, pt_b in [
        ((cx - outer_r + inset, cy), (cx - inner_gap, cy)),
        ((cx + inner_gap, cy),       (cx + outer_r - inset, cy)),
        ((cx, cy - outer_r + inset), (cx, cy - inner_gap)),
        ((cx, cy + inner_gap),       (cx, cy + outer_r - inset)),
    ]:
        cv2.line(img, pt_a, pt_b, bright, line_thick, cv2.LINE_AA)

    # Small inner ring (fainter)
    cv2.circle(img, (cx, cy), inner_r, dim, inner_thick, cv2.LINE_AA)

    # Centre dot
    cv2.circle(img, (cx, cy), centre_dot_r, bright, -1, cv2.LINE_AA)

    return img


def _sift_match(
    template: np.ndarray,
    image: np.ndarray,
    *,
    lowe_ratio: float,
    min_good: int,
) -> tuple[bool, np.ndarray | None, list, list, list]:
    """Return (found, homography_M, kp1, kp2, good_matches)."""
    sift = cv2.SIFT_create()
    gray_tmpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    gray_img = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    kp1, des1 = sift.detectAndCompute(gray_tmpl, None)
    kp2, des2 = sift.detectAndCompute(gray_img, None)

    if des1 is None or des2 is None or len(kp1) < 2 or len(kp2) < 2:
        return False, None, kp1, kp2, []

    bf = cv2.BFMatcher(cv2.NORM_L2)
    raw_matches = bf.knnMatch(des1, des2, k=2)

    good = []
    for pair in raw_matches:
        if len(pair) == 2:
            m, n = pair
            if m.distance < lowe_ratio * n.distance:
                good.append(m)

    if len(good) < min_good:
        return False, None, kp1, kp2, good

    src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
    M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

    if M is None:
        return False, None, kp1, kp2, good

    return True, M, kp1, kp2, good


def _detected_center(template: np.ndarray, M: np.ndarray) -> tuple[int, int]:
    h, w = template.shape[:2]
    center_tmpl = np.float32([[w / 2.0, h / 2.0]]).reshape(-1, 1, 2)
    center_img = cv2.perspectiveTransform(center_tmpl, M)
    cx, cy = center_img.reshape(2)
    return int(round(float(cx))), int(round(float(cy)))


def _draw_result(
    image: np.ndarray,
    template: np.ndarray,
    M: np.ndarray | None,
    kp1: list,
    kp2: list,
    good: list,
    label: str,
    found: bool,
) -> np.ndarray:
    # Draw match lines between template (left) and frame (right)
    h1, w1 = template.shape[:2]
    h2, w2 = image.shape[:2]
    # Side-by-side only for the reference-frame self-check; for full frames just annotate
    out = image.copy()

    if found and M is not None:
        # Draw the template bounding box projected into the frame
        corners = np.float32(
            [[0, 0], [w1, 0], [w1, h1], [0, h1]]
        ).reshape(-1, 1, 2)
        dst = cv2.perspectiveTransform(corners, M).reshape(-1, 2).astype(int)
        cv2.polylines(out, [dst.reshape(-1, 1, 2)], True, (0, 255, 0), 3)

        cx, cy = _detected_center(template, M)
        cv2.drawMarker(out, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 40, 3)
        cv2.circle(out, (cx, cy), 5, (0, 255, 0), -1)

        cv2.putText(
            out,
            f"{label}  matches={len(good)}  FOUND ({cx},{cy})",
            (24, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
    else:
        cv2.putText(
            out,
            f"{label}  matches={len(good)}  NOT FOUND",
            (24, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.85,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    # Draw all frame keypoints faintly
    for kp in kp2:
        cv2.circle(out, (int(kp.pt[0]), int(kp.pt[1])), 3, (180, 180, 0), 1)

    # Highlight matched frame keypoints
    for m in good:
        pt = kp2[m.trainIdx].pt
        cv2.circle(out, (int(pt[0]), int(pt[1])), 6, (0, 200, 255), 2)

    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default=None, help="Path to a real-image crop PNG (default: use synthetic)")
    ap.add_argument("--synth-size", type=int, default=SYNTH_SIZE, help="Side length of synthetic template")
    ap.add_argument("--logo-cx", type=int, default=LOGO_CENTER_XY[0])
    ap.add_argument("--logo-cy", type=int, default=LOGO_CENTER_XY[1])
    ap.add_argument("--template-half", type=int, default=TEMPLATE_HALF)
    ap.add_argument("--lowe-ratio", type=float, default=LOWE_RATIO)
    ap.add_argument("--min-matches", type=int, default=MIN_GOOD_MATCHES)
    ap.add_argument("--all-frames", action="store_true")
    ap.add_argument("--out-dir", default="output/debug_eddy_sift", type=Path)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ref_image = cv2.imread(str(REFERENCE_FRAME), cv2.IMREAD_COLOR)
    assert ref_image is not None

    if args.template:
        template = cv2.imread(args.template, cv2.IMREAD_COLOR)
        assert template is not None, f"Cannot read {args.template}"
        tmpl_source = "real-image crop"
    else:
        template = _make_synthetic_template(args.synth_size)
        tmpl_source = f"synthetic {args.synth_size}×{args.synth_size} px"
        cv2.imwrite(str(out_dir / "template_synthetic.png"), template)

    tmpl_path = out_dir / "template.png"
    cv2.imwrite(str(tmpl_path), template)

    # Count SIFT keypoints in the template
    sift = cv2.SIFT_create()
    kp_tmpl, _ = sift.detectAndCompute(
        cv2.cvtColor(template, cv2.COLOR_BGR2GRAY), None
    )
    print(f"Template source: {tmpl_source}")
    print(f"Template saved:  {tmpl_path.resolve()}")
    print(f"SIFT keypoints in template: {len(kp_tmpl)}")

    # Visualise keypoints on the template
    tmpl_kp_vis = cv2.drawKeypoints(
        template,
        kp_tmpl,
        None,
        flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS,
    )
    kp_path = out_dir / "template_keypoints.png"
    cv2.imwrite(str(kp_path), tmpl_kp_vis)
    print(f"Template keypoints vis: {kp_path.resolve()}")

    frame_paths = sorted(FRAMES_DIR.glob("*.jpg")) if args.all_frames else [REFERENCE_FRAME]

    panels: list[np.ndarray] = []
    results: list[tuple[str, bool, int, int, int]] = []

    for frame_path in frame_paths:
        image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        assert image is not None

        found, M, kp1, kp2, good = _sift_match(
            template,
            image,
            lowe_ratio=args.lowe_ratio,
            min_good=args.min_matches,
        )

        cx = cy = -1
        if found and M is not None:
            cx, cy = _detected_center(template, M)

        stem = frame_path.stem
        overlay = _draw_result(image, template, M, kp1, kp2, good, stem, found)
        overlay_path = out_dir / f"{stem}_sift.png"
        cv2.imwrite(str(overlay_path), overlay)

        status = "FOUND" if found else "NOT FOUND"
        print(
            f"{stem}  {status}  good_matches={len(good)}  kp_frame={len(kp2)}"
            + (f"  center=({cx},{cy})" if found else "")
        )
        print(f"  {overlay_path.resolve()}")

        results.append((stem, found, len(good), cx, cy))
        panels.append(cv2.resize(overlay, (480, 270), interpolation=cv2.INTER_AREA))

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
    print(f"Lowe ratio={args.lowe_ratio}  min_matches={args.min_matches}")


if __name__ == "__main__":
    main()
