#!/usr/bin/env python3
"""Compute the T0->T1 XYZ offset by fitting a camera model from T0 and Eddy
observations, then fitting the rigid T0->T1 translation.

The bed is deliberately ignored: only T0 nozzle and Eddy fiducial observations
are used for the camera fit.

Coordinate convention:
    T0 physical point = [commanded_x, 0, commanded_z]

    Eddy physical point =
        [commanded_x, 0, commanded_z] + fixed_t0_to_eddy_xyz_mm

    T1 physical point =
        [commanded_x, 0, commanded_z] + fitted_t0_to_t1_xyz_mm
"""

from __future__ import annotations

import hashlib
import logging
import math
from pathlib import Path
from typing import Any

import cv2
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import least_squares
from vision_calibration_graph import VisionCalibrationError, atomic_write_json

_logger = logging.getLogger(__name__)


def _project_points(
    points_xyz,
    *,
    log_fx,
    log_fy,
    cx,
    cy,
    rvec,
    tvec,
    k1,
    k2,
):

    camera_matrix = np.array(
        [
            [math.exp(log_fx), 0.0, cx],
            [0.0, math.exp(log_fy), cy],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )

    distortion = np.array(
        [k1, k2, 0.0, 0.0, 0.0],
        dtype=np.float64,
    )

    projected, _ = cv2.projectPoints(
        np.asarray(points_xyz, dtype=np.float64),
        np.asarray(rvec, dtype=np.float64),
        np.asarray(tvec, dtype=np.float64),
        camera_matrix,
        distortion,
    )

    return projected.reshape(-1, 2)


def _artifact(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def analyze_idex_xyz_offset(
    artifact_dir,
    t0_projection,
    t1_projection,
    eddy_positions,
) -> dict[str, Any]:
    """
    Fit a camera model from T0 nozzle and Eddy observations, then fit the
    rigid T0->T1 translation.

    The bed is deliberately ignored in this version.

    Coordinate convention:
        T0 physical point = [commanded_x, 0, commanded_z]

        Eddy physical point =
            [commanded_x, 0, commanded_z] + fixed_t0_to_eddy_xyz_mm

        T1 physical point =
            [commanded_x, 0, commanded_z] + fitted_t0_to_t1_xyz_mm
    """
    artifact_dir.mkdir(parents=True, exist_ok=True)

    _logger.info("analyzing IDEX XYZ offset without bed observations")

    # ------------------------------------------------------------------
    # Input extraction
    # ------------------------------------------------------------------

    t0_positions = t0_projection["tool_models"]["T0"]["accepted_direct_positions"]

    t1_positions = t1_projection["tool_models"]["T1"]["accepted_direct_positions"]

    eddy_records = [
        record
        for record in eddy_positions.get("detector_records", [])
        if record.get("detected")
    ]

    if len(t0_positions) < 6:
        raise VisionCalibrationError(
            "camera fit requires at least 6 T0 observations, "
            f"got {len(t0_positions)}"
        )

    if len(eddy_records) < 6:
        raise VisionCalibrationError(
            "camera fit requires at least 6 Eddy observations, "
            f"got {len(eddy_records)}"
        )

    if len(t1_positions) < 3:
        raise VisionCalibrationError(
            "T0->T1 fit requires at least 3 T1 observations, "
            f"got {len(t1_positions)}"
        )

    t0_cmd_xz = np.asarray(
        [[position["x_mm"], position["z_mm"]] for position in t0_positions],
        dtype=np.float64,
    )

    t0_uv = np.asarray(
        [position["center_px"] for position in t0_positions],
        dtype=np.float64,
    )

    t1_cmd_xz = np.asarray(
        [[position["x_mm"], position["z_mm"]] for position in t1_positions],
        dtype=np.float64,
    )

    t1_uv = np.asarray(
        [position["center_px"] for position in t1_positions],
        dtype=np.float64,
    )

    eddy_cmd_xz = np.asarray(
        [
            [
                record["commanded_x_mm"],
                record["commanded_z_mm"],
            ]
            for record in eddy_records
        ],
        dtype=np.float64,
    )

    eddy_uv = np.asarray(
        [
            [
                record["image_x_px"],
                record["image_y_px"],
            ]
            for record in eddy_records
        ],
        dtype=np.float64,
    )

    # Fixed for this stage.
    #
    # This is the vector from the T0 nozzle tip to the visible Eddy
    # fiducial, expressed in printer coordinates.
    fixed_t0_to_eddy_xyz_mm = np.asarray(
        [-57.391, -18.997, 1.399],
        dtype=np.float64,
    )

    image_width = 1920
    image_height = 1080

    # ------------------------------------------------------------------
    # Fit camera using T0 and Eddy only
    # ------------------------------------------------------------------

    def camera_residuals(theta: np.ndarray) -> np.ndarray:
        """
        Parameter vector:

            0  log_fx
            1  log_fy
            2  cx
            3  cy
            4:7   rvec
            7:10  tvec
            10 k1
            11 k2
        """
        log_fx, log_fy, cx, cy = theta[0:4]
        rvec = theta[4:7]
        tvec = theta[7:10]
        k1, k2 = theta[10:12]

        t0_points_xyz = np.column_stack(
            [
                t0_cmd_xz[:, 0],
                np.zeros(len(t0_cmd_xz), dtype=np.float64),
                t0_cmd_xz[:, 1],
            ]
        )

        eddy_points_xyz = np.column_stack(
            [
                (eddy_cmd_xz[:, 0] + fixed_t0_to_eddy_xyz_mm[0]),
                np.full(
                    len(eddy_cmd_xz),
                    fixed_t0_to_eddy_xyz_mm[1],
                    dtype=np.float64,
                ),
                (eddy_cmd_xz[:, 1] + fixed_t0_to_eddy_xyz_mm[2]),
            ]
        )

        points_xyz = np.vstack(
            [
                t0_points_xyz,
                eddy_points_xyz,
            ]
        )

        measured_uv = np.vstack(
            [
                t0_uv,
                eddy_uv,
            ]
        )

        predicted_uv = _project_points(
            points_xyz,
            log_fx=log_fx,
            log_fy=log_fy,
            cx=cx,
            cy=cy,
            rvec=rvec,
            tvec=tvec,
            k1=k1,
            k2=k2,
        )

        return (predicted_uv - measured_uv).reshape(-1)

    def camera_residuals_restricted(theta):

        log_f = theta[0]

        rvec = theta[1:4]

        tvec = theta[4:7]

        t0_points_xyz = np.column_stack(
            [
                t0_cmd_xz[:, 0],
                np.zeros(len(t0_cmd_xz)),
                t0_cmd_xz[:, 1],
            ]
        )

        eddy_points_xyz = np.column_stack(
            [
                eddy_cmd_xz[:, 0] + fixed_t0_to_eddy_xyz_mm[0],
                np.full(
                    len(eddy_cmd_xz),
                    fixed_t0_to_eddy_xyz_mm[1],
                ),
                eddy_cmd_xz[:, 1] + fixed_t0_to_eddy_xyz_mm[2],
            ]
        )

        points_xyz = np.vstack([t0_points_xyz, eddy_points_xyz])

        measured_uv = np.vstack([t0_uv, eddy_uv])

        predicted_uv = _project_points(
            points_xyz,
            log_fx=log_f,
            log_fy=log_f,
            cx=960.0,
            cy=540.0,
            rvec=rvec,
            tvec=tvec,
            k1=0.0,
            k2=0.0,
        )

        return (predicted_uv - measured_uv).ravel()

    _logger.info(
        "Fitting camera from %d T0 and %d Eddy observations",
        len(t0_uv),
        len(eddy_uv),
    )

    theta0_restricted = np.asarray(
        [
            np.log(900.0),
            0.0,
            2.7,
            0.0,
            -150.0,
            -60.0,
            125.0,
        ],
        dtype=np.float64,
    )
    camera_fit_restricted = least_squares(
        camera_residuals_restricted,
        theta0_restricted,
        bounds=(
            np.asarray(
                [
                    np.log(300.0),
                    -2.0 * np.pi,
                    -2.0 * np.pi,
                    -2.0 * np.pi,
                    -1000.0,
                    -1000.0,
                    1.0,
                ],
                dtype=np.float64,
            ),
            np.asarray(
                [
                    np.log(5000.0),
                    2.0 * np.pi,
                    2.0 * np.pi,
                    2.0 * np.pi,
                    1000.0,
                    1000.0,
                    2000.0,
                ],
                dtype=np.float64,
            ),
        ),
        loss="soft_l1",
        f_scale=1.0,
        x_scale="jac",
        max_nfev=3000,
        verbose=2,
    )
    _logger.info(
        "Camera fit finished: success=%s status=%d nfev=%d "
        "cost=%.6f optimality=%.6g message=%s",
        camera_fit_restricted.success,
        camera_fit_restricted.status,
        camera_fit_restricted.nfev,
        camera_fit_restricted.cost,
        camera_fit_restricted.optimality,
        camera_fit_restricted.message,
    )

    if not camera_fit_restricted.success:
        raise VisionCalibrationError(
            "camera fit failed after "
            f"{camera_fit_restricted.nfev} evaluations: "
            f"{camera_fit_restricted.message}"
        )

    # camera_parameters = {
    #     "log_fx": float(camera_fit.x[0]),
    #     "log_fy": float(camera_fit.x[1]),
    #     "cx": float(camera_fit.x[2]),
    #     "cy": float(camera_fit.x[3]),
    #     "rvec": np.asarray(
    #         camera_fit.x[4:7],
    #         dtype=np.float64,
    #     ),
    #     "tvec": np.asarray(
    #         camera_fit.x[7:10],
    #         dtype=np.float64,
    #     ),
    #     "k1": float(camera_fit.x[10]),
    #     "k2": float(camera_fit.x[11]),
    # }

    camera_parameters = {
        "log_fx": float(camera_fit_restricted.x[0]),
        "log_fy": float(camera_fit_restricted.x[0]),
        "cx": 960.0,
        "cy": 540.0,
        "rvec": np.asarray(
            camera_fit_restricted.x[1:4],
            dtype=np.float64,
        ),
        "tvec": np.asarray(
            camera_fit_restricted.x[4:7],
            dtype=np.float64,
        ),
        "k1": 0.0,
        "k2": 0.0,
    }
    # ------------------------------------------------------------------
    # Camera-model quality
    # ------------------------------------------------------------------

    camera_residual_pairs = camera_residuals_restricted(
        camera_fit_restricted.x
    ).reshape(-1, 2)
    t0_camera_residual_pairs = camera_residual_pairs[: len(t0_uv)]

    eddy_camera_residual_pairs = camera_residual_pairs[len(t0_uv) :]

    def residual_rms_px(
        residual_pairs: np.ndarray,
    ) -> float:
        residual_pairs = np.asarray(
            residual_pairs,
            dtype=np.float64,
        )

        return float(
            np.sqrt(
                np.mean(
                    np.sum(
                        residual_pairs**2,
                        axis=1,
                    )
                )
            )
        )

    def residual_median_px(
        residual_pairs: np.ndarray,
    ) -> float:
        return float(
            np.median(
                np.linalg.norm(
                    residual_pairs,
                    axis=1,
                )
            )
        )

    def residual_max_px(
        residual_pairs: np.ndarray,
    ) -> float:
        return float(
            np.max(
                np.linalg.norm(
                    residual_pairs,
                    axis=1,
                )
            )
        )

    camera_rms_px = residual_rms_px(camera_residual_pairs)

    camera_median_px = residual_median_px(camera_residual_pairs)

    camera_max_px = residual_max_px(camera_residual_pairs)

    t0_camera_rms_px = residual_rms_px(t0_camera_residual_pairs)

    eddy_camera_rms_px = residual_rms_px(eddy_camera_residual_pairs)

    camera_fit = camera_fit_restricted
    camera_model_quality = {
        "success": bool(camera_fit_restricted.success),
        "message": str(camera_fit_restricted.message),
        "status": int(camera_fit_restricted.status),
        "nfev": int(camera_fit_restricted.nfev),
        "cost": float(camera_fit_restricted.cost),
        "optimality": float(camera_fit_restricted.optimality),
        "intrinsics": {
            "fx_px": float(np.exp(camera_fit_restricted.x[0])),
            "fy_px": float(np.exp(camera_fit_restricted.x[0])),
            "cx_px": 960.0,
            "cy_px": 540.0,
            "k1": 0.0,
            "k2": 0.0,
        },
        "extrinsics": {
            "rvec_printer_to_camera": camera_fit_restricted.x[1:4].tolist(),
            "tvec_printer_to_camera_mm": camera_fit_restricted.x[4:7].tolist(),
        },
        "errors": {
            "combined_rms_px": camera_rms_px,
            "combined_median_px": camera_median_px,
            "combined_maximum_px": camera_max_px,
            "t0_rms_px": t0_camera_rms_px,
            "eddy_rms_px": eddy_camera_rms_px,
        },
        "observation_counts": {
            "t0": int(len(t0_uv)),
            "eddy": int(len(eddy_uv)),
        },
    }
    _logger.info(
        "Camera pose: rvec=%s tvec_mm=%s",
        np.array2string(
            camera_fit_restricted.x[1:4],
            precision=6,
        ),
        np.array2string(
            camera_fit_restricted.x[4:7],
            precision=6,
        ),
    )
    _logger.info(
        "Camera pose: rvec=%s tvec_mm=%s",
        np.array2string(
            camera_fit.x[4:7],
            precision=6,
        ),
        np.array2string(
            camera_fit.x[7:10],
            precision=6,
        ),
    )

    _logger.info(
        "Camera quality: combined RMS=%.4f px, "
        "median=%.4f px, max=%.4f px, "
        "T0 RMS=%.4f px, Eddy RMS=%.4f px",
        camera_rms_px,
        camera_median_px,
        camera_max_px,
        t0_camera_rms_px,
        eddy_camera_rms_px,
    )

    camera_model_quality_path = artifact_dir / "camera_model_quality.json"

    atomic_write_json(
        camera_model_quality_path,
        camera_model_quality,
    )

    camera_residual_plot = plt.figure(figsize=(8, 6))

    plt.title("Camera model reprojection residuals")

    plt.scatter(
        t0_camera_residual_pairs[:, 0],
        t0_camera_residual_pairs[:, 1],
        label="T0",
        alpha=0.7,
    )

    plt.scatter(
        eddy_camera_residual_pairs[:, 0],
        eddy_camera_residual_pairs[:, 1],
        label="Eddy",
        alpha=0.7,
    )

    plt.axhline(
        0.0,
        linewidth=1,
    )

    plt.axvline(
        0.0,
        linewidth=1,
    )

    plt.xlabel("U residual (px)")
    plt.ylabel("V residual (px)")
    plt.legend()

    camera_residual_plot_path = artifact_dir / "camera_model_residuals.png"

    camera_residual_plot.savefig(camera_residual_plot_path)

    plt.close(camera_residual_plot)

    # Residuals against image position are useful for recognizing
    # unmodelled distortion.
    residual_vs_position_plot = plt.figure(figsize=(8, 6))

    predicted_all_uv = (
        np.vstack(
            [
                t0_uv,
                eddy_uv,
            ]
        )
        + camera_residual_pairs
    )

    plt.scatter(
        predicted_all_uv[:, 0],
        camera_residual_pairs[:, 0],
        label="U residual",
        alpha=0.7,
    )

    plt.scatter(
        predicted_all_uv[:, 0],
        camera_residual_pairs[:, 1],
        label="V residual",
        alpha=0.7,
    )

    plt.axhline(
        0.0,
        linewidth=1,
    )

    plt.xlabel("Predicted image U (px)")
    plt.ylabel("Residual (px)")
    plt.legend()

    residual_vs_position_plot_path = (
        artifact_dir / "camera_residuals_vs_image_position.png"
    )

    residual_vs_position_plot.savefig(residual_vs_position_plot_path)

    plt.close(residual_vs_position_plot)

    # ------------------------------------------------------------------
    # Fit T0 -> T1 rigid translation with camera fixed
    # ------------------------------------------------------------------

    def t1_offset_residuals(
        offset_xyz: np.ndarray,
    ) -> np.ndarray:
        dx_mm, dy_mm, dz_mm = offset_xyz

        t1_points_xyz = np.column_stack(
            [
                t1_cmd_xz[:, 0] + dx_mm,
                np.full(
                    len(t1_cmd_xz),
                    dy_mm,
                    dtype=np.float64,
                ),
                t1_cmd_xz[:, 1] + dz_mm,
            ]
        )

        projected_uv = _project_points(
            t1_points_xyz,
            **camera_parameters,
        )

        return (projected_uv - t1_uv).reshape(-1)

    _logger.info(
        "Fitting T0->T1 XYZ offset from %d observations",
        len(t1_uv),
    )

    t1_fit = least_squares(
        t1_offset_residuals,
        x0=np.asarray(
            [0.0, 0.0, 0.0],
            dtype=np.float64,
        ),
        bounds=(
            np.asarray(
                [-25.0, -25.0, -10.0],
                dtype=np.float64,
            ),
            np.asarray(
                [25.0, 25.0, 10.0],
                dtype=np.float64,
            ),
        ),
        loss="soft_l1",
        f_scale=1.0,
        x_scale="jac",
        max_nfev=2000,
    )

    _logger.info(
        "T1 fit finished: success=%s status=%d nfev=%d "
        "cost=%.6f optimality=%.6g message=%s",
        t1_fit.success,
        t1_fit.status,
        t1_fit.nfev,
        t1_fit.cost,
        t1_fit.optimality,
        t1_fit.message,
    )

    if not t1_fit.success:
        raise VisionCalibrationError(
            "T0->T1 XYZ offset fit failed after "
            f"{t1_fit.nfev} evaluations: "
            f"{t1_fit.message}"
        )

    t0_t1_xyz_offset = np.asarray(
        t1_fit.x,
        dtype=np.float64,
    )

    t1_residual_pairs = t1_offset_residuals(t0_t1_xyz_offset).reshape(-1, 2)

    t1_rms_px = residual_rms_px(t1_residual_pairs)

    t1_median_px = residual_median_px(t1_residual_pairs)

    t1_max_px = residual_max_px(t1_residual_pairs)

    _logger.info(
        "Fitted T0->T1 offset: "
        "dx=%+.6f mm dy=%+.6f mm dz=%+.6f mm; "
        "RMS=%.4f px median=%.4f px max=%.4f px",
        t0_t1_xyz_offset[0],
        t0_t1_xyz_offset[1],
        t0_t1_xyz_offset[2],
        t1_rms_px,
        t1_median_px,
        t1_max_px,
    )

    t1_fit_result = {
        "t0_to_t1_xyz_offset_mm": (t0_t1_xyz_offset.tolist()),
        "reprojection_rms_px": t1_rms_px,
        "reprojection_median_px": t1_median_px,
        "reprojection_maximum_px": t1_max_px,
        "nfev": int(t1_fit.nfev),
        "cost": float(t1_fit.cost),
        "optimality": float(t1_fit.optimality),
        "message": str(t1_fit.message),
        "observation_count": int(len(t1_uv)),
    }

    t1_fit_result_path = artifact_dir / "t0_t1_xyz_fit.json"

    atomic_write_json(
        t1_fit_result_path,
        t1_fit_result,
    )

    t1_residual_plot = plt.figure(figsize=(8, 6))

    plt.title("T1 reprojection residuals")

    plt.scatter(
        t1_residual_pairs[:, 0],
        t1_residual_pairs[:, 1],
        alpha=0.7,
    )

    plt.axhline(
        0.0,
        linewidth=1,
    )

    plt.axvline(
        0.0,
        linewidth=1,
    )

    plt.xlabel("U residual (px)")
    plt.ylabel("V residual (px)")

    t1_residual_plot_path = artifact_dir / "t1_reprojection_residuals.png"

    t1_residual_plot.savefig(t1_residual_plot_path)

    plt.close(t1_residual_plot)

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    accepted = camera_rms_px < 2.0 and t1_rms_px < 2.0

    return {
        "accepted": accepted,
        "artifacts": {
            "camera_model_quality": _artifact(camera_model_quality_path),
            "camera_model_residuals": _artifact(camera_residual_plot_path),
            "camera_residuals_vs_image_position": _artifact(
                residual_vs_position_plot_path
            ),
            "t0_t1_xyz_fit": _artifact(t1_fit_result_path),
            "t1_reprojection_residuals": _artifact(t1_residual_plot_path),
        },
        "camera_model_quality": (camera_model_quality),
        "fixed_t0_to_eddy_xyz_mm": (fixed_t0_to_eddy_xyz_mm.tolist()),
        "t0_t1_xyz_offset": (t0_t1_xyz_offset.tolist()),
        "t0_t1_reprojection_rms_px": (t1_rms_px),
        "t0_t1_reprojection_median_px": (t1_median_px),
        "t0_t1_reprojection_maximum_px": (t1_max_px),
    }
