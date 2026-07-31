#!/usr/bin/env python3
"""Diagnostic: find all Hough circles in an Eddy frame and show them.

Tune PARAM2 to control sensitivity (lower = more circles).
Concentric pairs (center distance < CONCENTRIC_TOL_PX) are highlighted in white.

Usage:
    python scripts/debug_eddy_circles.py [frame_path] [--param2 N] [--out path]
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
from pathlib import Path

import cv2
import numpy as np


# --------------------------------------------------------------------------- #
# Defaults — adjust via CLI flags
# --------------------------------------------------------------------------- #
DEFAULT_FRAME = (
    "resources/vision_datasets/20260731_eddy_fiducial_xz_once/frames/"
    "00_eddy_x230p000_z0p500.jpg"
)
DEFAULT_PARAM2 = 40          # Lower → more circles found; tune until ~5-15 remain
DEFAULT_MIN_DIST = 40        # Minimum pixel distance between detected circle centres
MIN_R = 20
MAX_R = 80                   # Hard cap — suppresses sensor housing / window frame
CONCENTRIC_TOL_PX = 18       # Max centre-to-centre distance to call two circles concentric
RATIO_RANGE = (0.35, 0.80)   # inner/outer radius range for a valid concentric pair
CLAHE_CLIP = 2.0
BLUR_SIGMA = 1.5


def _color_for_radius(r: float, min_r: float, max_r: float) -> tuple[int, int, int]:
    """HSV rainbow from blue (small r) to red (large r), returned as BGR."""
    t = (r - min_r) / max(max_r - min_r, 1.0)
    h = (1.0 - t) * 0.67   # blue → cyan → green → yellow → red
    r_f, g_f, b_f = colorsys.hsv_to_rgb(h, 1.0, 1.0)
    return (int(b_f * 255), int(g_f * 255), int(r_f * 255))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frame", nargs="?", default=DEFAULT_FRAME)
    ap.add_argument("--param2", type=float, default=DEFAULT_PARAM2)
    ap.add_argument("--min-dist", type=int, default=DEFAULT_MIN_DIST)
    ap.add_argument("--out", default="output/debug_eddy_circles.png")
    ap.add_argument("--min-r", type=int, default=MIN_R)
    ap.add_argument("--max-r", type=int, default=MAX_R)
    args = ap.parse_args()

    img = cv2.imread(args.frame, cv2.IMREAD_COLOR)
    if img is None:
        raise SystemExit(f"Cannot open {args.frame}")
    h, w = img.shape[:2]
    scale = min(w / 1920.0, h / 1080.0)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    norm = cv2.createCLAHE(CLAHE_CLIP, (8, 8)).apply(gray)
    blurred = cv2.GaussianBlur(norm, (7, 7), BLUR_SIGMA)

    circles_raw = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.15,
        minDist=float(args.min_dist),
        param1=100,
        param2=args.param2,
        minRadius=args.min_r,
        maxRadius=args.max_r,
    )

    overlay = img.copy()
    all_circles: list[tuple[float, float, float]] = []

    if circles_raw is not None:
        all_circles = [(float(x), float(y), float(r)) for x, y, r in circles_raw[0]]
        all_circles.sort(key=lambda c: c[2])   # draw small first

        for x, y, r in all_circles:
            color = _color_for_radius(r, args.min_r, args.max_r)
            cv2.circle(overlay, (int(round(x)), int(round(y))), int(round(r)), color, 2)
            cv2.drawMarker(
                overlay, (int(round(x)), int(round(y))), color, cv2.MARKER_CROSS, 10, 1
            )
            cv2.putText(
                overlay,
                f"r{int(round(r))}",
                (int(round(x)) + 5, int(round(y)) - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                color,
                1,
                cv2.LINE_AA,
            )

    # --- Find and highlight concentric pairs ------------------------------------
    concentric_pairs: list[tuple[int, int]] = []
    for i, (x1, y1, r1) in enumerate(all_circles):
        for j, (x2, y2, r2) in enumerate(all_circles):
            if j <= i:
                continue
            dist = math.hypot(x1 - x2, y1 - y2)
            if dist > CONCENTRIC_TOL_PX:
                continue
            inner_r, outer_r = min(r1, r2), max(r1, r2)
            ratio = inner_r / max(outer_r, 1.0)
            if ratio < RATIO_RANGE[0] or ratio > RATIO_RANGE[1]:
                continue
            concentric_pairs.append((i, j))
            cx = int(round((x1 + x2) / 2))
            cy = int(round((y1 + y2) / 2))
            # Draw both circles thick white, then thin gold
            cv2.circle(overlay, (cx, cy), int(round(inner_r)), (255, 255, 255), 4)
            cv2.circle(overlay, (cx, cy), int(round(outer_r)), (255, 255, 255), 4)
            cv2.circle(overlay, (cx, cy), int(round(inner_r)), (0, 215, 255), 2)
            cv2.circle(overlay, (cx, cy), int(round(outer_r)), (0, 215, 255), 2)
            cv2.drawMarker(overlay, (cx, cy), (0, 215, 255), cv2.MARKER_DIAMOND, 24, 3)
            cv2.putText(
                overlay,
                f"PAIR r{int(round(inner_r))}/{int(round(outer_r))} ratio={ratio:.2f}",
                (cx + int(round(outer_r)) + 6, cy),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 215, 255),
                2,
                cv2.LINE_AA,
            )

    # Legend
    cv2.putText(
        overlay,
        f"{len(all_circles)} circles  param2={args.param2}  minDist={args.min_dist}  r=[{args.min_r},{args.max_r}]",
        (24, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (220, 220, 0),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        overlay,
        f"{len(concentric_pairs)} concentric pairs (gold/white)",
        (24, 86),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (0, 215, 255),
        2,
        cv2.LINE_AA,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), overlay)
    print(f"\nSaved: {out_path.resolve()}")
    print(f"Found {len(all_circles)} circles, {len(concentric_pairs)} concentric pairs")
    print("\nAll circles (x, y, r):")
    for i, (x, y, r) in enumerate(all_circles):
        print(f"  [{i:2d}] ({x:6.1f}, {y:6.1f})  r={r:5.1f}")
    if concentric_pairs:
        print("\nConcentric pairs:")
        for i, j in concentric_pairs:
            x1, y1, r1 = all_circles[i]
            x2, y2, r2 = all_circles[j]
            dist = math.hypot(x1 - x2, y1 - y2)
            print(
                f"  [{i}]+[{j}]  ({x1:.0f},{y1:.0f}) r={r1:.0f}  +  ({x2:.0f},{y2:.0f}) r={r2:.0f}"
                f"  dist={dist:.1f}  ratio={min(r1,r2)/max(r1,r2):.3f}"
            )


if __name__ == "__main__":
    main()
