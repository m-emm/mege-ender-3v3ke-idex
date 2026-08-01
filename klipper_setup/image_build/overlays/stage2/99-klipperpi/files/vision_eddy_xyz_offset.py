#!/usr/bin/env python3
"""Compute the Eddy-fiducial → T0-nozzle-tip offset in printer XYZ coordinates.

This module is a compute-only analyzer: it consumes two pre-existing facts
  camera.nozzle_cam.nozzle_tip.t0_projection_model
  camera.nozzle_cam.eddy_fiducial.xz_image_positions

and solves for the rigid 3-D offset (δx, δy, δz) that reconciles both sets of
image-space observations through the shared camera model.

Model
-----
The nozzle fine-XZ job produces a 6-term polynomial mapping
    (printer_x, printer_z) → (image_x_px, image_y_px)
fitted at fixed capture_y_mm = -14.

When the T0 carriage is commanded to (X_cmd, Z_cmd), the Eddy sensor appears
at printer position (X_cmd + δx, Y_cmd + δy, Z_cmd + δz).  The camera sees:

    image_x = cam_x(X_cmd + δx, Z_cmd + δz) + y_vec_x · δy
    image_y = cam_y(X_cmd + δx, Z_cmd + δz) + y_vec_y · δy

where y_vec is image_y_axis_vector_px_per_mm (d(image_pos)/d(printer_Y)).

δy accounts for the fact that the polynomial model was fitted at a fixed Y;
any Y offset of the Eddy sensor adds a constant image shift via y_vec.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

ACCEPTED_MAX_RMS_PX = 12.0
ACCEPTED_MAX_ERROR_PX = 30.0
MIN_EDDY_DETECTIONS = 4


# ── polynomial camera model ───────────────────────────────────────────────────


def _eval_model(model: dict[str, Any], x_mm: float, z_mm: float) -> tuple[float, float]:
    """Evaluate the 6-term nozzle projection polynomial at (x_mm, z_mm).

    terms = [1, dx, dz, dx·dz, dx², dx²·dz]
    coefficients shape: (6, 2) — column 0 → image_x, column 1 → image_y
    """
    dx = float(x_mm) - float(model["x_ref_mm"])
    dz = float(z_mm) - float(model["z_ref_mm"])
    terms = np.array(
        [1.0, dx, dz, dx * dz, dx * dx, dx * dx * dz],
        dtype=np.float64,
    )
    coeffs = np.asarray(model["position_coefficients"], dtype=np.float64)
    pred = terms @ coeffs
    return float(pred[0]), float(pred[1])


def _residuals_and_jacobian(
    params: np.ndarray,
    model: dict[str, Any],
    y_vec: tuple[float, float],
    records: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
    """Return (residuals, Jacobian) for Gauss-Newton.

    params = [δx, δy, δz]
    Residuals shape: (2*N,)  — alternating Δpx, Δpy per detection.
    Jacobian shape:  (2*N, 3)
    """
    dx_p, dy_p, dz_p = float(params[0]), float(params[1]), float(params[2])
    yvec_x, yvec_y = y_vec
    coeffs = np.asarray(model["position_coefficients"], dtype=np.float64)  # (6,2)
    x_ref = float(model["x_ref_mm"])
    z_ref = float(model["z_ref_mm"])
    N = len(records)
    r = np.empty(2 * N, dtype=np.float64)
    J = np.empty((2 * N, 3), dtype=np.float64)
    for i, rec in enumerate(records):
        dx = (rec["commanded_x_mm"] + dx_p) - x_ref
        dz = (rec["commanded_z_mm"] + dz_p) - z_ref
        terms = np.array(
            [1.0, dx, dz, dx * dz, dx * dx, dx * dx * dz],
            dtype=np.float64,
        )
        pred = terms @ coeffs  # shape (2,)
        pred[0] += yvec_x * dy_p
        pred[1] += yvec_y * dy_p
        r[2 * i] = pred[0] - rec["image_x_px"]
        r[2 * i + 1] = pred[1] - rec["image_y_px"]
        # d(pred_x)/d(δx) = c1 + c3*dz + 2*c4*dx + 2*c5*dx*dz
        # d(pred_x)/d(δz) = c2 + c3*dx + c5*dx^2
        J[2 * i, 0] = (
            coeffs[1, 0]
            + coeffs[3, 0] * dz
            + 2 * coeffs[4, 0] * dx
            + 2 * coeffs[5, 0] * dx * dz
        )
        J[2 * i, 1] = yvec_x
        J[2 * i, 2] = coeffs[2, 0] + coeffs[3, 0] * dx + coeffs[5, 0] * dx * dx
        J[2 * i + 1, 0] = (
            coeffs[1, 1]
            + coeffs[3, 1] * dz
            + 2 * coeffs[4, 1] * dx
            + 2 * coeffs[5, 1] * dx * dz
        )
        J[2 * i + 1, 1] = yvec_y
        J[2 * i + 1, 2] = coeffs[2, 1] + coeffs[3, 1] * dx + coeffs[5, 1] * dx * dx
    return r, J


def _gauss_newton(
    x0: np.ndarray,
    model: dict[str, Any],
    y_vec: tuple[float, float],
    records: list[dict[str, Any]],
    *,
    max_iter: int = 50,
    tol: float = 1e-8,
) -> np.ndarray:
    """Minimise sum-of-squares via Gauss-Newton with backtracking line search."""
    x = x0.copy()
    for _ in range(max_iter):
        r, J = _residuals_and_jacobian(x, model, y_vec, records)
        # Normal equations: (J^T J) δ = -J^T r
        JtJ = J.T @ J
        Jtr = J.T @ r
        try:
            step = -np.linalg.solve(JtJ, Jtr)
        except np.linalg.LinAlgError:
            break
        # Armijo backtracking
        cost0 = float(r @ r)
        alpha = 1.0
        for _ in range(10):
            r_new, _ = _residuals_and_jacobian(x + alpha * step, model, y_vec, records)
            if float(r_new @ r_new) < cost0:
                break
            alpha *= 0.5
        x = x + alpha * step
        if float(np.linalg.norm(step)) < tol:
            break
    return x


def _residuals(
    params: np.ndarray,
    model: dict[str, Any],
    y_vec: tuple[float, float],
    records: list[dict[str, Any]],
) -> np.ndarray:
    r, _ = _residuals_and_jacobian(params, model, y_vec, records)
    return r


def _finite_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _finite_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_json(v) for v in value]
    if isinstance(value, (float, np.floating)) and not math.isfinite(float(value)):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


# ── main entry point ──────────────────────────────────────────────────────────


def analyze(
    *,
    t0_projection: dict[str, Any],
    eddy_positions: dict[str, Any],
) -> dict[str, Any]:
    """Solve for the Eddy fiducial XYZ offset relative to the T0 nozzle tip.

    Parameters
    ----------
    t0_projection:
        Value of fact ``camera.nozzle_cam.nozzle_tip.t0_projection_model``.
        Must contain ``tool_models["T0"]`` and
        ``image_y_axis_vector_px_per_mm``.
    eddy_positions:
        Value of fact ``camera.nozzle_cam.eddy_fiducial.xz_image_positions``.
        Must contain ``detector_records`` with per-frame
        ``commanded_x_mm``, ``commanded_z_mm``, ``detected``,
        ``image_x_px``, ``image_y_px``.

    Returns
    -------
    Result dict with keys ``accepted``, ``reasons``, ``warnings``,
    ``artifacts``, and on success the offset fields.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    # ── extract inputs ────────────────────────────────────────────────────────

    tool_models = t0_projection.get("tool_models", {})
    if "T0" not in tool_models:
        reasons.append("t0_projection_model missing T0 tool model")
        return {
            "accepted": False,
            "reasons": reasons,
            "warnings": warnings,
            "artifacts": {},
        }

    model = tool_models["T0"]
    y_axis_raw = t0_projection.get("image_y_axis_vector_px_per_mm", [0.0, -10.0])
    y_vec: tuple[float, float] = (float(y_axis_raw[0]), float(y_axis_raw[1]))

    if abs(y_vec[1]) < 1.0:
        reasons.append(f"image_y_axis_vector_px_per_mm magnitude is too small: {y_vec}")
        return {
            "accepted": False,
            "reasons": reasons,
            "warnings": warnings,
            "artifacts": {},
        }

    all_records: list[dict[str, Any]] = eddy_positions.get("detector_records", [])
    records = [r for r in all_records if r.get("detected")]

    if len(records) < MIN_EDDY_DETECTIONS:
        reasons.append(
            f"only {len(records)} eddy detections, need at least {MIN_EDDY_DETECTIONS}"
        )
        return {
            "accepted": False,
            "reasons": reasons,
            "warnings": warnings,
            "artifacts": {},
        }

    # ── initial guess ─────────────────────────────────────────────────────────
    # δy from median image_y gap (dominant term — Eddy is Y-offset from nozzle)
    intercept_y = model["position_coefficients"][0][1]
    intercept_x = model["position_coefficients"][0][0]
    dx_coeff = model["position_coefficients"][1][0]
    x_ref = float(model["x_ref_mm"])

    median_img_y = float(np.median([r["image_y_px"] for r in records]))
    dy0 = (median_img_y - intercept_y) / y_vec[1]

    median_img_x = float(np.median([r["image_x_px"] for r in records]))
    median_cmd_x = float(np.median([r["commanded_x_mm"] for r in records]))
    corrected_img_x = median_img_x - y_vec[0] * dy0
    dx0 = (x_ref + (corrected_img_x - intercept_x) / dx_coeff) - median_cmd_x
    dz0 = 0.0

    # ── least-squares solve (pure numpy Gauss-Newton) ────────────────────────

    x0 = np.array([dx0, dy0, dz0], dtype=np.float64)
    x_solved = _gauss_newton(x0, model, y_vec, records)
    dx, dy, dz = float(x_solved[0]), float(x_solved[1]), float(x_solved[2])

    residual_vec = _residuals(x_solved, model, y_vec, records)
    rms_px = float(np.sqrt(np.mean(residual_vec**2)))
    max_err_px = float(np.max(np.abs(residual_vec)))

    if rms_px > ACCEPTED_MAX_RMS_PX:
        reasons.append(
            f"eddy offset fit RMS {rms_px:.2f} px exceeds limit {ACCEPTED_MAX_RMS_PX} px"
        )
    if max_err_px > ACCEPTED_MAX_ERROR_PX:
        reasons.append(
            f"eddy offset max error {max_err_px:.2f} px exceeds limit {ACCEPTED_MAX_ERROR_PX} px"
        )

    # per-detection residual magnitudes for diagnostics
    detection_residuals = []
    for i, rec in enumerate(records):
        res_x = float(residual_vec[2 * i])
        res_y = float(residual_vec[2 * i + 1])
        detection_residuals.append(
            {
                "seq": int(rec["seq"]),
                "commanded_x_mm": float(rec["commanded_x_mm"]),
                "commanded_z_mm": float(rec["commanded_z_mm"]),
                "residual_x_px": res_x,
                "residual_y_px": res_y,
                "residual_magnitude_px": float(math.hypot(res_x, res_y)),
            }
        )

    accepted = not reasons
    return _finite_json(
        {
            "accepted": accepted,
            "reasons": reasons,
            "warnings": warnings,
            "artifacts": {},
            # offset — the primary output
            "offset_xyz_mm": [dx, dy, dz],
            # diagnostics
            "fit_rms_px": rms_px,
            "max_error_px": max_err_px,
            "n_eddy_detections": len(records),
            "n_eddy_total": len(all_records),
            "initial_guess_xyz_mm": [dx0, dy0, dz0],
            "nozzle_model_x_ref_mm": float(model["x_ref_mm"]),
            "nozzle_model_z_ref_mm": float(model["z_ref_mm"]),
            "nozzle_model_fit_rms_px": float(model.get("position_fit_rms_px", 0.0)),
            "image_y_axis_vector_px_per_mm": list(y_vec),
            "detection_residuals": detection_residuals,
        }
    )
