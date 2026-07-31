#!/usr/bin/env python3
"""Diagnostic: multi-scale template matching for the BTT Eddy crosshair logo.

The crosshair logo is extracted from a reference frame (or supplied via --template),
then searched across every frame using normalised cross-correlation at multiple scales.

Usage:
    # Show match heatmap for the reference frame only:
    python scripts/debug_eddy_template_match.py

    # Process all 16 captured frames and write overlays + a contact sheet:
    python scripts/debug_eddy_template_match.py --all-frames

    # Supply your own template crop:
    python scripts/debug_eddy_template_match.py --template path/to/template.png

    # Tune scale sweep:
    python scripts/debug_eddy_template_match.py --scale-min 0.85 --scale-max 1.15 --scale-steps 13
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

# Centre of the BTT crosshair logo in the reference frame (from r=28 Hough detection).
# Adjust if needed — this is where the template crop is taken from.
LOGO_CENTER_XY = (901, 297)
TEMPLATE_HALF = 46          # Half-size of the square template crop in pixels

SCALE_MIN = 0.88
SCALE_MAX = 1.12
SCALE_STEPS = 9             # Number of scale levels to try


def _extract_template(image: np.ndarray, cx: int, cy: int, half: int) -> np.ndarray:
    x0 = max(0, cx - half)
    y0 = max(0, cy - half)
    x1 = min(image.shape[1], cx + half)
    y1 = min(image.shape[0], cy + half)
    return image[y0:y1, x0:x1].copy()


def _match_template_multiscale(
    image: np.ndarray,
    template: np.ndarray,
    *,
    scale_min: float,
    scale_max: float,
    scale_steps: int,
) -> tuple[float, int, int, float]:
    """Return (best_score, best_cx, best_cy, best_scale)."""
    gray_img = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray_tmpl_base = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

    best_score = -1.0
    best_cx = best_cy = 0
    best_scale = 1.0

    scales = np.linspace(scale_min, scale_max, scale_steps)
    for s in scales:
        tw = max(8, int(round(template.shape[1] * s)))
        th = max(8, int(round(template.shape[0] * s)))
        tmpl = cv2.resize(gray_tmpl_base, (tw, th), interpolation=cv2.INTER_LINEAR)
        if tmpl.shape[0] > gray_img.shape[0] or tmpl.shape[1] > gray_img.shape[1]:
            continue
        result = cv2.matchTemplate(gray_img, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if float(max_val) > best_score:
            best_score = float(max_val)
            best_cx = max_loc[0] + tw // 2
            best_cy = max_loc[1] + th // 2
            best_scale = float(s)

    return best_score, best_cx, best_cy, best_scale


def _heatmap_overlay(image: np.ndarray, template: np.ndarray, scale: float) -> np.ndarray:
    """Return a heatmap overlay (full-res, BGR) of TM_CCOEFF_NORMED scores."""
    gray_img = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray_tmpl = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    tw = max(8, int(round(template.shape[1] * scale)))
    th = max(8, int(round(template.shape[0] * scale)))
    tmpl = cv2.resize(gray_tmpl, (tw, th), interpolation=cv2.INTER_LINEAR)
    result = cv2.matchTemplate(gray_img, tmpl, cv2.TM_CCOEFF_NORMED)
    # result is (H-th+1) × (W-tw+1); pad back to full size
    padded = np.zeros(gray_img.shape[:2], dtype=np.float32)
    ph, pw = result.shape[:2]
    padded[th // 2 : th // 2 + ph, tw // 2 : tw // 2 + pw] = result
    # Normalise 0..1 → colourmap
    norm = cv2.normalize(padded, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    heatmap = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    return cv2.addWeighted(image, 0.55, heatmap, 0.45, 0)


def _draw_result(
    image: np.ndarray,
    cx: int,
    cy: int,
    template: np.ndarray,
    scale: float,
    score: float,
    label: str,
) -> np.ndarray:
    out = image.copy()
    half_w = int(round(template.shape[1] * scale / 2))
    half_h = int(round(template.shape[0] * scale / 2))
    cv2.rectangle(
        out,
        (cx - half_w, cy - half_h),
        (cx + half_w, cy + half_h),
        (0, 255, 0),
        2,
    )
    cv2.drawMarker(out, (cx, cy), (0, 255, 0), cv2.MARKER_CROSS, 28, 2)
    cv2.putText(
        out,
        f"{label}  score={score:.3f}  scale={scale:.2f}",
        (24, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        out,
        f"match center=({cx},{cy})",
        (24, 84),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.70,
        (0, 230, 230),
        2,
        cv2.LINE_AA,
    )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default=None, help="Path to an existing template crop PNG")
    ap.add_argument("--logo-cx", type=int, default=LOGO_CENTER_XY[0])
    ap.add_argument("--logo-cy", type=int, default=LOGO_CENTER_XY[1])
    ap.add_argument("--template-half", type=int, default=TEMPLATE_HALF)
    ap.add_argument("--scale-min", type=float, default=SCALE_MIN)
    ap.add_argument("--scale-max", type=float, default=SCALE_MAX)
    ap.add_argument("--scale-steps", type=int, default=SCALE_STEPS)
    ap.add_argument("--all-frames", action="store_true", help="Process all 16 frames")
    ap.add_argument("--out-dir", default="output/debug_eddy_template", type=Path)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Load / build template --------------------------------------------------
    ref_image = cv2.imread(str(REFERENCE_FRAME), cv2.IMREAD_COLOR)
    assert ref_image is not None, f"Cannot read {REFERENCE_FRAME}"

    if args.template:
        template = cv2.imread(args.template, cv2.IMREAD_COLOR)
        assert template is not None, f"Cannot read template {args.template}"
    else:
        template = _extract_template(ref_image, args.logo_cx, args.logo_cy, args.template_half)

    tmpl_path = out_dir / "template.png"
    cv2.imwrite(str(tmpl_path), template)
    print(f"Template ({template.shape[1]}×{template.shape[0]} px): {tmpl_path.resolve()}")

    # --- Determine frames to process --------------------------------------------
    if args.all_frames:
        frame_paths = sorted(FRAMES_DIR.glob("*.jpg"))
    else:
        frame_paths = [REFERENCE_FRAME]

    panels: list[np.ndarray] = []

    for frame_path in frame_paths:
        image = cv2.imread(str(frame_path), cv2.IMREAD_COLOR)
        assert image is not None, f"Cannot read {frame_path}"

        score, cx, cy, scale = _match_template_multiscale(
            image,
            template,
            scale_min=args.scale_min,
            scale_max=args.scale_max,
            scale_steps=args.scale_steps,
        )

        stem = frame_path.stem

        # Heatmap at best scale
        heatmap = _heatmap_overlay(image, template, scale)
        heatmap_path = out_dir / f"{stem}_heatmap.png"
        cv2.imwrite(str(heatmap_path), heatmap)

        # Match overlay
        overlay = _draw_result(image, cx, cy, template, scale, score, stem)
        overlay_path = out_dir / f"{stem}_match.png"
        cv2.imwrite(str(overlay_path), overlay)

        print(f"{stem}  score={score:.4f}  center=({cx},{cy})  scale={scale:.3f}")
        print(f"  heatmap : {heatmap_path.resolve()}")
        print(f"  overlay : {overlay_path.resolve()}")

        panels.append(cv2.resize(overlay, (480, 270), interpolation=cv2.INTER_AREA))

    # Contact sheet (4 columns) if multiple frames
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


if __name__ == "__main__":
    main()
