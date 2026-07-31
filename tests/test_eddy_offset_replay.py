#!/usr/bin/env python3
"""Solve for the nozzle-tip → Eddy-fiducial XZ offset from captured analysis results.

Uses two pre-computed result JSON files (no image re-analysis required):

  resources/vision_datasets/20260731_eddy_offset/nozzle_t0_result.json
  resources/vision_datasets/20260731_eddy_offset/eddy_result.json

To populate these from the printer (one-time):

    mkdir -p resources/vision_datasets/20260731_eddy_offset
    scp pi@menderpi.local:/home/pi/printer_data/vision/calibration/jobs/\\
        20260731T140539.158539Z-stage5_t0_rerun/analysis/\\
        20260731T140754.042073Z-ac8c121b77/result.json \\
        resources/vision_datasets/20260731_eddy_offset/nozzle_t0_result.json
    scp pi@menderpi.local:/home/pi/printer_data/vision/calibration/jobs/\\
        20260731T140941.066574Z-eddy_fiducial/analysis/\\
        20260731T142143.085238Z-4bda42a0f6/result.json \\
        resources/vision_datasets/20260731_eddy_offset/eddy_result.json

Model
-----
The nozzle fine-XZ job yields a 6-term polynomial mapping
    (printer_x, printer_z) → (image_x_px, image_y_px)

for the nozzle tip position (which is, by definition, the T0 reference position
when the carriage is commanded to (X, Z)).

The eddy fiducial job yields image-space positions of the Eddy sensor's crosshair
circle when the carriage is commanded to a different grid of (X, Z) points.

Because both the nozzle tip and the Eddy sensor are rigidly attached to T0, the
camera model is the same for both; the Eddy sensor is just at a fixed 3D offset
(δx, δz) from the nozzle tip in printer coordinates.  (δy cannot be recovered
from these captures because both jobs use the same capture_y_mm = −14 mm.)

For each eddy observation at commanded (Xₑ, Zₑ):
    predicted_eddy_image = nozzle_cam(Xₑ + δx, Zₑ + δz)

We minimise the sum of squared pixel residuals over (δx, δz).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import pytest
from scipy.optimize import least_squares


REPO_ROOT = Path(__file__).resolve().parents[1]
DATASET_ROOT = REPO_ROOT / "resources" / "vision_datasets" / "20260731_eddy_offset"
OUTPUT_ROOT = REPO_ROOT / "output" / "vision_eddy_offset"

# ── data files ────────────────────────────────────────────────────────────────

NOZZLE_RESULT_JSON = DATASET_ROOT / "nozzle_t0_result.json"
EDDY_RESULT_JSON = DATASET_ROOT / "eddy_result.json"


# ── nozzle polynomial model ────────────────────────────────────────────────────


def _eval_nozzle_model(model: dict, x_mm: float, z_mm: float) -> tuple[float, float]:
    """Evaluate the 6-term polynomial projection model at (x_mm, z_mm).

    Returns (image_x_px, image_y_px).

    terms = [1, dx, dz, dx*dz, dx², dx²*dz]
    coefficients shape: (6, 2)  — column 0 → image_x, column 1 → image_y
    """
    dx = float(x_mm) - float(model["x_ref_mm"])
    dz = float(z_mm) - float(model["z_ref_mm"])
    terms = np.array(
        [1.0, dx, dz, dx * dz, dx * dx, dx * dx * dz],
        dtype=np.float64,
    )
    coeffs = np.asarray(model["position_coefficients"], dtype=np.float64)  # (6,2)
    pred = terms @ coeffs
    return float(pred[0]), float(pred[1])


# ── residual function for scipy.optimize ──────────────────────────────────────


def _eddy_residuals(
    params: np.ndarray,
    model: dict,
    eddy_records: list[dict],
    y_axis_vector: tuple[float, float],
) -> np.ndarray:
    """Return flat residual vector [Δpx_0, Δpy_0, Δpx_1, Δpy_1, …] in pixels.

    params = [δx, δy, δz] — printer-coordinate offset of eddy relative to nozzle.
    The Y contribution uses image_y_axis_vector_px_per_mm because the polynomial
    model was fitted at a fixed capture Y; δy adds a constant image offset.
    """
    dx, dy, dz = float(params[0]), float(params[1]), float(params[2])
    yvec_x, yvec_y = y_axis_vector
    residuals: list[float] = []
    for rec in eddy_records:
        pred_x, pred_y = _eval_nozzle_model(
            model,
            rec["commanded_x_mm"] + dx,
            rec["commanded_z_mm"] + dz,
        )
        pred_x += yvec_x * dy
        pred_y += yvec_y * dy
        residuals.append(pred_x - rec["image_x_px"])
        residuals.append(pred_y - rec["image_y_px"])
    return np.array(residuals, dtype=np.float64)


# ── colour helpers ─────────────────────────────────────────────────────────────


def _distinct_bgr_colors(count: int) -> list[tuple[int, int, int]]:
    hues = np.linspace(0, 179, count, endpoint=False, dtype=np.uint8)
    hsv = np.zeros((1, count, 3), dtype=np.uint8)
    hsv[0, :, 0] = hues
    hsv[0, :, 1] = 190
    hsv[0, :, 2] = 200
    return [
        tuple(int(c) for c in col)
        for col in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0]
    ]


def _plot_point(
    x_val: float,
    x_min: float,
    x_max: float,
    y_val: float,
    y_min: float,
    y_max: float,
    rect: tuple[int, int, int, int],
) -> tuple[int, int]:
    left, top, right, bottom = rect
    span_x = max(x_max - x_min, 1e-9)
    span_y = max(y_max - y_min, 1e-9)
    px = left + int(round((x_val - x_min) / span_x * (right - left)))
    py = bottom - int(round((y_val - y_min) / span_y * (bottom - top)))
    return px, py


def _axis_labels(
    canvas: np.ndarray,
    rect: tuple[int, int, int, int],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    x_label: str,
    y_label: str,
    n_ticks: int = 5,
) -> None:
    left, top, right, bottom = rect
    font = cv2.FONT_HERSHEY_SIMPLEX
    # x-axis ticks
    for i in range(n_ticks):
        v = x_min + i * (x_max - x_min) / (n_ticks - 1)
        px, py = _plot_point(v, x_min, x_max, y_min, y_min, y_max, rect)
        cv2.line(canvas, (px, bottom - 4), (px, bottom + 4), (80, 80, 80), 1)
        cv2.putText(
            canvas,
            f"{v:.1f}",
            (px - 20, bottom + 18),
            font,
            0.38,
            (60, 60, 60),
            1,
            cv2.LINE_AA,
        )
    # y-axis ticks
    for i in range(n_ticks):
        v = y_min + i * (y_max - y_min) / (n_ticks - 1)
        px, py = _plot_point(x_min, x_min, x_max, v, y_min, y_max, rect)
        cv2.line(canvas, (left - 4, py), (left + 4, py), (80, 80, 80), 1)
        cv2.putText(
            canvas,
            f"{v:.0f}",
            (left - 52, py + 5),
            font,
            0.38,
            (60, 60, 60),
            1,
            cv2.LINE_AA,
        )
    # axis border
    cv2.rectangle(canvas, (left, top), (right, bottom), (120, 120, 120), 1)
    # axis labels
    cv2.putText(
        canvas, x_label, ((left + right) // 2 - 40, bottom + 36),
        font, 0.48, (30, 30, 30), 1, cv2.LINE_AA,
    )
    cv2.putText(
        canvas, y_label, (left - 68, (top + bottom) // 2),
        font, 0.42, (30, 30, 30), 1, cv2.LINE_AA,
    )


# ── plot 1: commanded X vs image X ────────────────────────────────────────────


def _write_commanded_x_vs_image_x(
    nozzle_accepted: list[dict],
    eddy_detected: list[dict],
    model: dict,
    dx_solved: float,
    dz_solved: float,
    path: Path,
) -> None:
    """Two panels: raw data (top) and after offset correction (bottom)."""
    W, H = 1100, 900
    canvas = np.full((H, W, 3), 248, dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX

    cv2.putText(
        canvas,
        "Nozzle tip vs Eddy fiducial  |  commanded X vs image X",
        (30, 38), font, 0.78, (20, 20, 20), 2, cv2.LINE_AA,
    )

    # top panel: raw  —  bottom panel: after offset
    panels = [
        (50, 60, W - 50, 390, "raw (eddy at commanded X)"),
        (50, 455, W - 50, 850, f"corrected (eddy shifted by δx={dx_solved:+.2f} mm)"),
    ]

    # x-axis: printer X mm;  y-axis: image X px
    all_nozzle_x = [r["x_mm"] for r in nozzle_accepted]
    all_eddy_x = [r["commanded_x_mm"] for r in eddy_detected]
    all_img_x = (
        [r["center_px"][0] for r in nozzle_accepted]
        + [r["image_x_px"] for r in eddy_detected]
    )
    x_min = min(all_nozzle_x + all_eddy_x) - 3
    x_max = max(all_nozzle_x + all_eddy_x) + 3
    px_min = min(all_img_x) - 20
    px_max = max(all_img_x) + 20

    # z values for colouring
    z_values_nozzle = sorted({r["z_mm"] for r in nozzle_accepted})
    z_values_eddy = sorted({r["commanded_z_mm"] for r in eddy_detected})
    colors_n = _distinct_bgr_colors(len(z_values_nozzle))
    colors_e = _distinct_bgr_colors(len(z_values_eddy))

    for panel_idx, (left, top, right, bottom, title) in enumerate(panels):
        cv2.putText(
            canvas, title, (left, top - 8), font, 0.56, (50, 50, 50), 1, cv2.LINE_AA,
        )
        _axis_labels(
            canvas, (left, top, right, bottom),
            x_min, x_max, px_min, px_max,
            "commanded X (mm)", "image X (px)",
        )

        # nozzle points (circles)
        for rec in nozzle_accepted:
            ci = z_values_nozzle.index(rec["z_mm"])
            col = colors_n[ci]
            px, py = _plot_point(
                rec["x_mm"], x_min, x_max,
                rec["center_px"][0], px_min, px_max,
                (left, top, right, bottom),
            )
            cv2.circle(canvas, (px, py), 5, col, -1, cv2.LINE_AA)

        # eddy points: raw or corrected
        for rec in eddy_detected:
            ci = z_values_eddy.index(rec["commanded_z_mm"])
            col = colors_e[ci]
            x_plot = (
                rec["commanded_x_mm"] if panel_idx == 0
                else rec["commanded_x_mm"] + dx_solved
            )
            px, py = _plot_point(
                x_plot, x_min, x_max,
                rec["image_x_px"], px_min, px_max,
                (left, top, right, bottom),
            )
            cv2.drawMarker(
                canvas, (px, py), col, cv2.MARKER_DIAMOND, 10, 2, cv2.LINE_AA,
            )

        # model prediction curve for nozzle (one curve per Z level)
        x_dense = np.linspace(x_min, x_max, 120)
        for zi, z_val in enumerate(z_values_nozzle):
            col = colors_n[zi]
            pts = []
            for xv in x_dense:
                pred_x, _ = _eval_nozzle_model(model, xv, z_val)
                pp = _plot_point(
                    xv, x_min, x_max,
                    pred_x, px_min, px_max,
                    (left, top, right, bottom),
                )
                pts.append(pp)
            for i in range(len(pts) - 1):
                cv2.line(canvas, pts[i], pts[i + 1], col, 1, cv2.LINE_AA)

    # legend
    lx, ly = 820, 70
    cv2.putText(canvas, "legend", (lx, ly), font, 0.44, (50, 50, 50), 1, cv2.LINE_AA)
    cv2.circle(canvas, (lx + 8, ly + 20), 5, (120, 120, 120), -1)
    cv2.putText(canvas, "nozzle (circle)", (lx + 18, ly + 25), font, 0.38, (60, 60, 60), 1)
    cv2.drawMarker(canvas, (lx + 8, ly + 40), (120, 120, 120), cv2.MARKER_DIAMOND, 10, 2)
    cv2.putText(canvas, "eddy (diamond)", (lx + 18, ly + 45), font, 0.38, (60, 60, 60), 1)
    cv2.putText(canvas, "-- nozzle model", (lx + 18, ly + 62), font, 0.38, (60, 60, 60), 1)

    cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 6])


# ── plot 2: commanded Z vs image Y ────────────────────────────────────────────


def _write_commanded_z_vs_image_y(
    nozzle_accepted: list[dict],
    eddy_detected: list[dict],
    model: dict,
    dx_solved: float,
    dz_solved: float,
    path: Path,
) -> None:
    """Two panels: raw (top) and Z-corrected (bottom)."""
    W, H = 1100, 900
    canvas = np.full((H, W, 3), 248, dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX

    cv2.putText(
        canvas,
        "Nozzle tip vs Eddy fiducial  |  commanded Z vs image Y",
        (30, 38), font, 0.78, (20, 20, 20), 2, cv2.LINE_AA,
    )

    all_z = (
        [r["z_mm"] for r in nozzle_accepted]
        + [r["commanded_z_mm"] for r in eddy_detected]
    )
    all_img_y = (
        [r["center_px"][1] for r in nozzle_accepted]
        + [r["image_y_px"] for r in eddy_detected]
    )
    z_min = min(all_z) - 1
    z_max = max(all_z) + 1
    py_min = min(all_img_y) - 20
    py_max = max(all_img_y) + 20

    x_values_nozzle = sorted({r["x_mm"] for r in nozzle_accepted})
    x_values_eddy = sorted({r["commanded_x_mm"] for r in eddy_detected})
    colors_n = _distinct_bgr_colors(len(x_values_nozzle))
    colors_e = _distinct_bgr_colors(len(x_values_eddy))

    panels = [
        (50, 60, W - 50, 390, "raw (eddy at commanded Z)"),
        (50, 455, W - 50, 850, f"corrected (eddy shifted by δz={dz_solved:+.2f} mm)"),
    ]

    for panel_idx, (left, top, right, bottom, title) in enumerate(panels):
        cv2.putText(
            canvas, title, (left, top - 8), font, 0.56, (50, 50, 50), 1, cv2.LINE_AA,
        )
        _axis_labels(
            canvas, (left, top, right, bottom),
            z_min, z_max, py_min, py_max,
            "commanded Z (mm)", "image Y (px)",
        )

        for rec in nozzle_accepted:
            ci = x_values_nozzle.index(rec["x_mm"])
            col = colors_n[ci]
            px, py = _plot_point(
                rec["z_mm"], z_min, z_max,
                rec["center_px"][1], py_min, py_max,
                (left, top, right, bottom),
            )
            cv2.circle(canvas, (px, py), 5, col, -1, cv2.LINE_AA)

        for rec in eddy_detected:
            ci = x_values_eddy.index(rec["commanded_x_mm"])
            col = colors_e[ci]
            z_plot = (
                rec["commanded_z_mm"] if panel_idx == 0
                else rec["commanded_z_mm"] + dz_solved
            )
            px, py = _plot_point(
                z_plot, z_min, z_max,
                rec["image_y_px"], py_min, py_max,
                (left, top, right, bottom),
            )
            cv2.drawMarker(
                canvas, (px, py), col, cv2.MARKER_DIAMOND, 10, 2, cv2.LINE_AA,
            )

        # model prediction curves (one per X)
        z_dense = np.linspace(z_min, z_max, 100)
        for xi, x_val in enumerate(x_values_nozzle):
            col = colors_n[xi]
            pts = []
            for zv in z_dense:
                _, pred_y = _eval_nozzle_model(model, x_val, zv)
                pp = _plot_point(
                    zv, z_min, z_max,
                    pred_y, py_min, py_max,
                    (left, top, right, bottom),
                )
                pts.append(pp)
            for i in range(len(pts) - 1):
                cv2.line(canvas, pts[i], pts[i + 1], col, 1, cv2.LINE_AA)

    cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 6])


# ── plot 3: residual vectors in image space ────────────────────────────────────


def _write_residuals_plot(
    nozzle_accepted: list[dict],
    eddy_detected: list[dict],
    model: dict,
    y_axis_vector: tuple[float, float],
    dx_solved: float,
    dy_solved: float,
    dz_solved: float,
    path: Path,
) -> tuple[float, float]:
    """Show per-point prediction error (model vs measured) in image pixel space.

    Both nozzle and eddy residuals after offset correction, quiver-style.
    """
    W, H = 1100, 700
    canvas = np.full((H, W, 3), 248, dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX

    cv2.putText(
        canvas,
        "Residuals: measured − model prediction  (px)",
        (30, 38), font, 0.78, (20, 20, 20), 2, cv2.LINE_AA,
    )

    left, top, right, bottom = 80, 60, W - 60, H - 60
    _axis_labels(
        canvas, (left, top, right, bottom),
        800, 1200, 200, 700,
        "image X (px)", "image Y (px)",
    )

    scale = 20.0  # px in plot per px residual

    def _draw_arrow(cx: int, cy: int, ex: int, ey: int, color: tuple) -> None:
        cv2.arrowedLine(canvas, (cx, cy), (ex, ey), color, 2, cv2.LINE_AA, tipLength=0.4)

    nozzle_rms_x = []
    nozzle_rms_y = []
    for rec in nozzle_accepted:
        pred_px, pred_py = _eval_nozzle_model(model, rec["x_mm"], rec["z_mm"])
        meas_x, meas_y = rec["center_px"][0], rec["center_px"][1]
        err_x = meas_x - pred_px
        err_y = meas_y - pred_py
        nozzle_rms_x.append(err_x)
        nozzle_rms_y.append(err_y)
        ix, iy = _plot_point(
            meas_x, 800, 1200, meas_y, 200, 700, (left, top, right, bottom),
        )
        ex = ix + int(round(err_x * scale))
        ey = iy - int(round(err_y * scale))
        cv2.circle(canvas, (ix, iy), 4, (200, 140, 60), -1, cv2.LINE_AA)
        if abs(err_x) > 0.05 or abs(err_y) > 0.05:
            _draw_arrow(ix, iy, ex, ey, (200, 140, 60))

    eddy_rms_x = []
    eddy_rms_y = []
    for rec in eddy_detected:
        pred_px, pred_py = _eval_nozzle_model(
            model,
            rec["commanded_x_mm"] + dx_solved,
            rec["commanded_z_mm"] + dz_solved,
        )
        pred_px += y_axis_vector[0] * dy_solved
        pred_py += y_axis_vector[1] * dy_solved
        meas_x, meas_y = rec["image_x_px"], rec["image_y_px"]
        err_x = meas_x - pred_px
        err_y = meas_y - pred_py
        eddy_rms_x.append(err_x)
        eddy_rms_y.append(err_y)
        ix, iy = _plot_point(
            meas_x, 800, 1200, meas_y, 200, 700, (left, top, right, bottom),
        )
        ex = ix + int(round(err_x * scale))
        ey = iy - int(round(err_y * scale))
        cv2.drawMarker(
            canvas, (ix, iy), (60, 140, 200), cv2.MARKER_DIAMOND, 10, 2, cv2.LINE_AA,
        )
        if abs(err_x) > 0.05 or abs(err_y) > 0.05:
            _draw_arrow(ix, iy, ex, ey, (60, 140, 200))

    nozzle_rms = float(np.sqrt(np.mean(np.array(nozzle_rms_x)**2 + np.array(nozzle_rms_y)**2)))
    eddy_rms = float(np.sqrt(np.mean(np.array(eddy_rms_x)**2 + np.array(eddy_rms_y)**2)))

    cv2.putText(
        canvas,
        f"arrow scale: {scale:.0f}x  |  nozzle RMS={nozzle_rms:.2f}px  eddy RMS={eddy_rms:.2f}px",
        (30, H - 20), font, 0.5, (50, 50, 50), 1, cv2.LINE_AA,
    )
    cv2.circle(canvas, (810, H - 15), 5, (200, 140, 60), -1)
    cv2.putText(canvas, "nozzle", (820, H - 10), font, 0.42, (60, 60, 60), 1)
    cv2.drawMarker(canvas, (880, H - 15), (60, 140, 200), cv2.MARKER_DIAMOND, 10, 2)
    cv2.putText(canvas, "eddy", (895, H - 10), font, 0.42, (60, 60, 60), 1)

    cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 6])

    return nozzle_rms, eddy_rms


# ── plot 4: image-space scatter, before/after correction ─────────────────────


def _write_image_space_scatter(
    nozzle_accepted: list[dict],
    eddy_detected: list[dict],
    model: dict,
    y_axis_vector: tuple[float, float],
    dx_solved: float,
    dy_solved: float,
    dz_solved: float,
    path: Path,
) -> None:
    """Show where each feature lands in image space before and after correction."""
    W, H = 1100, 600
    canvas = np.full((H, W, 3), 248, dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX

    cv2.putText(
        canvas,
        "Image-space positions  (left: raw commanded  |  right: eddy corrected by offset)",
        (30, 38), font, 0.68, (20, 20, 20), 2, cv2.LINE_AA,
    )

    nozzle_xs = [r["center_px"][0] for r in nozzle_accepted]
    nozzle_ys = [r["center_px"][1] for r in nozzle_accepted]
    eddy_xs = [r["image_x_px"] for r in eddy_detected]
    eddy_ys = [r["image_y_px"] for r in eddy_detected]

    # predict eddy positions after offset correction
    eddy_pred_xs = []
    eddy_pred_ys = []
    for rec in eddy_detected:
        px, py = _eval_nozzle_model(
            model,
            rec["commanded_x_mm"] + dx_solved,
            rec["commanded_z_mm"] + dz_solved,
        )
        px += y_axis_vector[0] * dy_solved
        py += y_axis_vector[1] * dy_solved
        eddy_pred_xs.append(px)
        eddy_pred_ys.append(py)

    all_img_x = nozzle_xs + eddy_xs + eddy_pred_xs
    all_img_y = nozzle_ys + eddy_ys + eddy_pred_ys
    ix_min = min(all_img_x) - 30
    ix_max = max(all_img_x) + 30
    iy_min = min(all_img_y) - 30
    iy_max = max(all_img_y) + 30

    panels = [
        (55, 55, 510, H - 50, "raw  (eddy at commanded position)"),
        (560, 55, W - 50, H - 50, f"δx={dx_solved:+.2f} δy={dy_solved:+.2f} δz={dz_solved:+.2f} mm"),
    ]

    for panel_idx, (left, top, right, bottom, title) in enumerate(panels):
        cv2.putText(
            canvas, title, (left, top - 8), font, 0.48, (50, 50, 50), 1, cv2.LINE_AA,
        )
        _axis_labels(
            canvas, (left, top, right, bottom),
            ix_min, ix_max, iy_min, iy_max,
            "image X (px)", "image Y (px)",
        )

        # nozzle
        for x, y in zip(nozzle_xs, nozzle_ys):
            px, py = _plot_point(x, ix_min, ix_max, y, iy_min, iy_max, (left, top, right, bottom))
            cv2.circle(canvas, (px, py), 5, (60, 160, 60), -1, cv2.LINE_AA)

        # eddy measured
        for x, y in zip(eddy_xs, eddy_ys):
            px, py = _plot_point(x, ix_min, ix_max, y, iy_min, iy_max, (left, top, right, bottom))
            cv2.drawMarker(canvas, (px, py), (200, 60, 60), cv2.MARKER_DIAMOND, 10, 2, cv2.LINE_AA)

        # eddy predicted (right panel only)
        if panel_idx == 1:
            for mx, my, px_pred, py_pred in zip(eddy_xs, eddy_ys, eddy_pred_xs, eddy_pred_ys):
                px_m, py_m = _plot_point(
                    mx, ix_min, ix_max, my, iy_min, iy_max, (left, top, right, bottom),
                )
                px_p, py_p = _plot_point(
                    px_pred, ix_min, ix_max, py_pred, iy_min, iy_max, (left, top, right, bottom),
                )
                cv2.line(canvas, (px_m, py_m), (px_p, py_p), (180, 180, 60), 1, cv2.LINE_AA)
                cv2.drawMarker(
                    canvas, (px_p, py_p), (60, 60, 200), cv2.MARKER_CROSS, 8, 2, cv2.LINE_AA,
                )

    # legend
    lx, ly = 820, 60
    cv2.circle(canvas, (lx, ly), 5, (60, 160, 60), -1)
    cv2.putText(canvas, "nozzle", (lx + 12, ly + 5), font, 0.38, (60, 60, 60), 1)
    cv2.drawMarker(canvas, (lx, ly + 20), (200, 60, 60), cv2.MARKER_DIAMOND, 10, 2)
    cv2.putText(canvas, "eddy measured", (lx + 12, ly + 25), font, 0.38, (60, 60, 60), 1)
    cv2.drawMarker(canvas, (lx, ly + 40), (60, 60, 200), cv2.MARKER_CROSS, 8, 2)
    cv2.putText(canvas, "eddy predicted", (lx + 12, ly + 45), font, 0.38, (60, 60, 60), 1)

    cv2.imwrite(str(path), canvas, [cv2.IMWRITE_PNG_COMPRESSION, 6])


# ── main test ─────────────────────────────────────────────────────────────────


def test_eddy_nozzle_offset_from_results():
    """Solve for the eddy-fiducial → nozzle-tip offset in printer XZ coordinates.

    Loads pre-computed result JSON files, fits (δx, δz) such that the nozzle
    polynomial camera model applied at (commanded_x + δx, commanded_z + δz)
    best predicts the observed eddy fiducial image positions.
    """
    if not NOZZLE_RESULT_JSON.is_file() or not EDDY_RESULT_JSON.is_file():
        pytest.skip(
            "local result JSON files absent — see docstring for download instructions"
        )

    # ── load data ─────────────────────────────────────────────────────────────

    nozzle_result = json.loads(NOZZLE_RESULT_JSON.read_text(encoding="utf-8"))
    eddy_result = json.loads(EDDY_RESULT_JSON.read_text(encoding="utf-8"))

    nozzle_diag = nozzle_result["diagnostics"]
    eddy_diag = eddy_result["diagnostics"]

    model = nozzle_diag["models"]["T0"]
    nozzle_accepted = [
        r for r in nozzle_diag["registrations"]
        if r["accepted_for_projection_model"]
    ]
    eddy_detected = [r for r in eddy_diag["records"] if r["detected"]]

    print(
        f"\nData: {len(nozzle_accepted)} nozzle registrations  "
        f"|  {len(eddy_detected)} eddy detections"
    )
    print(f"Nozzle X: {min(r['x_mm'] for r in nozzle_accepted):.1f} – "
          f"{max(r['x_mm'] for r in nozzle_accepted):.1f} mm")
    print(f"Eddy X:   {min(r['commanded_x_mm'] for r in eddy_detected):.1f} – "
          f"{max(r['commanded_x_mm'] for r in eddy_detected):.1f} mm")

    # ── image_y_axis_vector ───────────────────────────────────────────────────
    # This is d(image_position)/d(printer_Y) — captures how printer Y shifts
    # the image.  The polynomial model was fitted at fixed capture Y, so any
    # printer-Y offset of the eddy sensor adds a constant image shift via this
    # vector.
    y_axis_raw = nozzle_diag.get("image_y_axis_vector_px_per_mm", [0.0, -10.0])
    y_axis_vector: tuple[float, float] = (float(y_axis_raw[0]), float(y_axis_raw[1]))

    # ── initial guess ─────────────────────────────────────────────────────────
    x_ref = float(model["x_ref_mm"])
    z_ref = float(model["z_ref_mm"])
    dx_coeff = model["position_coefficients"][1][0]   # d(image_x)/d(printer_x)
    intercept_x_at_ref = model["position_coefficients"][0][0]
    intercept_y_at_ref = model["position_coefficients"][0][1]

    # δy: use the median image_y difference divided by yvec_y
    median_eddy_img_y = float(np.median([r["image_y_px"] for r in eddy_detected]))
    dy0 = (median_eddy_img_y - intercept_y_at_ref) / y_axis_vector[1]

    # δx: use median image_x (after subtracting δy contribution) / dx_coeff
    median_eddy_img_x = float(np.median([r["image_x_px"] for r in eddy_detected]))
    median_eddy_cmd_x = float(np.median([r["commanded_x_mm"] for r in eddy_detected]))
    corrected_img_x = median_eddy_img_x - y_axis_vector[0] * dy0
    x_for_corrected_img = x_ref + (corrected_img_x - intercept_x_at_ref) / dx_coeff
    dx0 = x_for_corrected_img - median_eddy_cmd_x
    dz0 = 0.0

    print(f"\nInitial guess:  δx={dx0:+.2f} mm  δy={dy0:+.2f} mm  δz={dz0:+.2f} mm")

    # ── optimise ──────────────────────────────────────────────────────────────

    result_opt = least_squares(
        _eddy_residuals,
        x0=[dx0, dy0, dz0],
        args=(model, eddy_detected, y_axis_vector),
        method="lm",
        ftol=1e-10,
        xtol=1e-10,
        gtol=1e-10,
    )
    assert result_opt.success or result_opt.cost < 1.0, (
        f"optimiser did not converge: {result_opt.message}"
    )

    dx_solved, dy_solved, dz_solved = (
        float(result_opt.x[0]), float(result_opt.x[1]), float(result_opt.x[2])
    )
    residuals_final = result_opt.fun
    rms_px = float(np.sqrt(np.mean(residuals_final**2)))
    max_err_px = float(np.max(np.abs(residuals_final)))

    print(f"\n{'='*55}")
    print(f"  SOLVED OFFSET  (eddy fiducial relative to nozzle tip)")
    print(f"  δx = {dx_solved:+8.3f} mm   (printer X axis)")
    print(f"  δy = {dy_solved:+8.3f} mm   (printer Y axis)")
    print(f"  δz = {dz_solved:+8.3f} mm   (printer Z axis)")
    print(f"{'='*55}")
    print(f"  Fit RMS:     {rms_px:.3f} px")
    print(f"  Max error:   {max_err_px:.3f} px")
    print(f"  Iterations:  {result_opt.nfev}")

    # ── write output plots ─────────────────────────────────────────────────────

    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        + "-" + __import__("uuid").uuid4().hex[:8]
    )
    run_root = OUTPUT_ROOT / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    plot_cmd_x = run_root / "commanded_x_vs_image_x.png"
    plot_cmd_z = run_root / "commanded_z_vs_image_y.png"
    plot_residuals = run_root / "residuals.png"
    plot_image_space = run_root / "image_space_scatter.png"

    _write_commanded_x_vs_image_x(
        nozzle_accepted, eddy_detected, model, dx_solved, dz_solved, plot_cmd_x,
    )
    _write_commanded_z_vs_image_y(
        nozzle_accepted, eddy_detected, model, dx_solved, dz_solved, plot_cmd_z,
    )
    nozzle_rms, eddy_rms = _write_residuals_plot(
        nozzle_accepted, eddy_detected, model, y_axis_vector,
        dx_solved, dy_solved, dz_solved, plot_residuals,
    )
    _write_image_space_scatter(
        nozzle_accepted, eddy_detected, model, y_axis_vector,
        dx_solved, dy_solved, dz_solved, plot_image_space,
    )

    # ── save result JSON ───────────────────────────────────────────────────────

    summary = {
        "run_id": run_id,
        "dx_mm": dx_solved,
        "dy_mm": dy_solved,
        "dz_mm": dz_solved,
        "rms_px": rms_px,
        "max_error_px": max_err_px,
        "nozzle_model_rms_px": float(model["position_fit_rms_px"]),
        "eddy_fit_rms_px": eddy_rms,
        "nozzle_fit_rms_px": nozzle_rms,
        "n_nozzle": len(nozzle_accepted),
        "n_eddy": len(eddy_detected),
        "nozzle_job_id": nozzle_result.get("job_id"),
        "eddy_job_id": eddy_result.get("job_id"),
    }
    (run_root / "offset_result.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8",
    )

    print(f"\nOUTPUT:\n  {run_root.resolve()}")
    print("  commanded_x_vs_image_x.png")
    print("  commanded_z_vs_image_y.png")
    print("  residuals.png")
    print("  image_space_scatter.png")
    print("  offset_result.json")

    # ── assertions ────────────────────────────────────────────────────────────

    assert rms_px < 8.0, f"eddy fit RMS too high: {rms_px:.2f} px"
    assert max_err_px < 20.0, f"eddy max error too high: {max_err_px:.2f} px"

    for p in (plot_cmd_x, plot_cmd_z, plot_residuals, plot_image_space):
        assert p.is_file(), f"plot missing: {p}"
