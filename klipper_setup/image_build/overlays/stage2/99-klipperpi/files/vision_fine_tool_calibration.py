#!/usr/bin/env python3
"""Stage 5.1 fine T0/T1 XYZ calculation and report artifacts."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np


class FineToolCalibrationError(RuntimeError):
    pass


def _finite(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
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


def _position(model: dict[str, Any], x_mm: float, z_mm: float) -> np.ndarray:
    dx = float(x_mm) - float(model["x_ref_mm"])
    dz = float(z_mm) - float(model["z_ref_mm"])
    design = np.asarray([1.0, dx, dz, dx * dz], dtype=np.float64)
    return design @ np.asarray(model["position_coefficients"], dtype=np.float64)


def _x_vector(model: dict[str, Any], z_mm: float) -> np.ndarray:
    coefficients = np.asarray(model["position_coefficients"], dtype=np.float64)
    return coefficients[1] + coefficients[3] * (
        float(z_mm) - float(model["z_ref_mm"])
    )


def _fit_model(
    records: list[dict[str, Any]],
    *,
    x_ref_mm: float,
    z_ref_mm: float,
) -> dict[str, Any]:
    if len(records) < 8:
        raise FineToolCalibrationError("too few registrations for stability fit")
    design = np.asarray(
        [
            [
                1.0,
                float(record["x_mm"]) - x_ref_mm,
                float(record["z_mm"]) - z_ref_mm,
                (float(record["x_mm"]) - x_ref_mm)
                * (float(record["z_mm"]) - z_ref_mm),
            ]
            for record in records
        ],
        dtype=np.float64,
    )
    positions = np.asarray(
        [record["center_px"] for record in records], dtype=np.float64
    )
    coefficients = np.linalg.lstsq(design, positions, rcond=None)[0]
    residuals = positions - design @ coefficients
    return {
        "x_ref_mm": float(x_ref_mm),
        "z_ref_mm": float(z_ref_mm),
        "position_coefficients": coefficients.tolist(),
        "position_fit_rms_px": float(
            np.sqrt(np.mean(np.sum(residuals**2, axis=1)))
        ),
    }


def _homography_jacobian(
    homography: np.ndarray, point: np.ndarray
) -> np.ndarray:
    x, y = [float(item) for item in point]
    h = homography
    denominator = h[2, 0] * x + h[2, 1] * y + h[2, 2]
    u_numerator = h[0, 0] * x + h[0, 1] * y + h[0, 2]
    v_numerator = h[1, 0] * x + h[1, 1] * y + h[1, 2]
    return np.asarray(
        [
            [
                (h[0, 0] * denominator - u_numerator * h[2, 0])
                / denominator**2,
                (h[0, 1] * denominator - u_numerator * h[2, 1])
                / denominator**2,
            ],
            [
                (h[1, 0] * denominator - v_numerator * h[2, 0])
                / denominator**2,
                (h[1, 1] * denominator - v_numerator * h[2, 0])
                / denominator**2,
            ],
        ],
        dtype=np.float64,
    )


def _patch_to_printer_matrix(
    metric: dict[str, Any], projection: dict[str, Any]
) -> np.ndarray:
    homography = np.asarray(
        metric["patch_to_image_homography"], dtype=np.float64
    )
    patch_center = np.asarray(
        metric["patch_reference_center_xy_mm"], dtype=np.float64
    )
    jacobian = _homography_jacobian(homography, patch_center)
    bed_x = np.asarray(
        projection["bed_x_vector_fiducial_plane_px_per_mm"],
        dtype=np.float64,
    )
    patch_x = np.linalg.solve(jacobian, bed_x)
    patch_x /= np.linalg.norm(patch_x)
    measured_patch_y = -np.asarray(
        metric["patch_y_vector_per_printer_y_mm"], dtype=np.float64
    )
    measured_patch_y /= np.linalg.norm(measured_patch_y)
    patch_y = np.asarray([-patch_x[1], patch_x[0]], dtype=np.float64)
    if float(np.dot(patch_y, measured_patch_y)) < 0:
        patch_y *= -1.0
    printer_to_patch = np.column_stack((patch_x, patch_y))
    return np.linalg.inv(printer_to_patch)


def _projective_matrix_from_correspondences(
    world_points: np.ndarray, image_points: np.ndarray
) -> np.ndarray:
    rows = []
    for world, image in zip(world_points, image_points):
        x, y, z = world
        homogeneous = np.asarray([x, y, z, 1.0], dtype=np.float64)
        u, v = image
        rows.append(np.r_[homogeneous, np.zeros(4), -u * homogeneous])
        rows.append(np.r_[np.zeros(4), homogeneous, -v * homogeneous])
    _u, _s, vh = np.linalg.svd(np.asarray(rows, dtype=np.float64))
    matrix = vh[-1].reshape(3, 4)
    if abs(float(matrix[2, 3])) < 1e-7:
        raise FineToolCalibrationError(
            "joint projective initialization has an invalid scale"
        )
    return matrix / matrix[2, 3]


def _encode_projective(matrix: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            matrix[0, 0],
            matrix[0, 1],
            matrix[0, 2],
            matrix[0, 3],
            matrix[1, 0],
            matrix[1, 1],
            matrix[1, 2],
            matrix[1, 3],
            matrix[2, 0],
            matrix[2, 1],
            matrix[2, 2],
        ],
        dtype=np.float64,
    )


def _decode_projective(values: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            values[0:4],
            values[4:8],
            [values[8], values[9], values[10], 1.0],
        ],
        dtype=np.float64,
    )


def _normalized_world(world: np.ndarray) -> np.ndarray:
    return np.column_stack(
        (
            (world[:, 0] - 173.0) / 20.0,
            world[:, 1] / 20.0,
            world[:, 2] / 10.0,
        )
    )


def _project(matrix: np.ndarray, world: np.ndarray) -> np.ndarray:
    normalized = _normalized_world(world)
    homogeneous = np.column_stack(
        (normalized, np.ones(len(normalized), dtype=np.float64))
    )
    projected = homogeneous @ matrix.T
    denominators = projected[:, 2]
    if np.any(np.abs(denominators) < 1e-5):
        raise FineToolCalibrationError(
            "joint projective model crosses the camera plane"
        )
    return projected[:, :2] / denominators[:, None]


def _joint_observations(
    *,
    parameters: np.ndarray,
    patch_to_printer: np.ndarray,
    patch_points_mm: np.ndarray,
    metric_centers: np.ndarray,
    metric_commanded_y_mm: np.ndarray,
    fiducial_plane_z_mm: float,
    corner_pixels: np.ndarray,
    corner_commanded_y_mm: np.ndarray,
    corner_xyz_mm: np.ndarray,
    registrations: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    patch_translation = parameters[11:13]
    tool_residuals = {
        "T0": parameters[13:16],
        "T1": parameters[16:19],
    }
    world_points = []
    image_points = []
    base_weights = []
    labels = []
    for centers, commanded_y in zip(metric_centers, metric_commanded_y_mm):
        absolute_xy = (
            patch_points_mm @ patch_to_printer.T + patch_translation
        )
        for absolute, image in zip(absolute_xy, centers):
            world_points.append(
                [
                    float(absolute[0]),
                    float(absolute[1] - commanded_y),
                    float(fiducial_plane_z_mm),
                ]
            )
            image_points.append(image)
            base_weights.append(1.0)
            labels.append("bed_fiducial")
    for image, commanded_y in zip(corner_pixels, corner_commanded_y_mm):
        world_points.append(
            [
                float(corner_xyz_mm[0]),
                float(corner_xyz_mm[1] - commanded_y),
                float(corner_xyz_mm[2]),
            ]
        )
        image_points.append(image)
        base_weights.append(2.0)
        labels.append("bed_tab_corner")
    for record in registrations:
        residual = tool_residuals[record["tool"]]
        world_points.append(
            [
                float(record["x_mm"]) + residual[0],
                residual[1],
                float(record["z_mm"]) + residual[2],
            ]
        )
        image_points.append(record["center_px"])
        base_weights.append(1.0)
        labels.append(f"nozzle_{record['tool']}")
    return (
        np.asarray(world_points, dtype=np.float64),
        np.asarray(image_points, dtype=np.float64),
        np.asarray(base_weights, dtype=np.float64),
        labels,
    )


def _huber_objective(residuals: np.ndarray, weights: np.ndarray) -> float:
    norms = np.linalg.norm(residuals, axis=1)
    delta = 2.0
    losses = np.where(
        norms <= delta,
        0.5 * norms**2,
        delta * (norms - 0.5 * delta),
    )
    return float(np.sum(weights * losses))


def _fit_joint_projective(
    *,
    projection: dict[str, Any],
    partial_bed: dict[str, Any],
    registrations: list[dict[str, Any]],
    metric: dict[str, Any],
    metric_centers_px: list[list[list[float]]],
    metric_commanded_y_mm: list[float],
    corner_pixels_px: list[list[float]],
    corner_commanded_y_mm: list[float],
    patch_points_mm: list[list[float]],
    fiducial_plane_z_mm: float,
    initial_tools: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    patch_to_printer = _patch_to_printer_matrix(metric, projection)
    corner_patch = np.asarray(
        partial_bed["corner_patch_xy_mm"], dtype=np.float64
    )
    corner_xyz = np.asarray(
        partial_bed["corner_printer_xyz_mm"], dtype=np.float64
    )
    patch_translation = (
        corner_xyz[:2] - patch_to_printer @ corner_patch
    )
    initial_residuals = np.r_[
        initial_tools["T0"]["coordinate_residual_xyz_mm"],
        initial_tools["T1"]["coordinate_residual_xyz_mm"],
    ]
    temporary = np.r_[np.zeros(11), patch_translation, initial_residuals]
    observation_args = {
        "patch_to_printer": patch_to_printer,
        "patch_points_mm": np.asarray(patch_points_mm, dtype=np.float64),
        "metric_centers": np.asarray(metric_centers_px, dtype=np.float64),
        "metric_commanded_y_mm": np.asarray(
            metric_commanded_y_mm, dtype=np.float64
        ),
        "fiducial_plane_z_mm": float(fiducial_plane_z_mm),
        "corner_pixels": np.asarray(corner_pixels_px, dtype=np.float64),
        "corner_commanded_y_mm": np.asarray(
            corner_commanded_y_mm, dtype=np.float64
        ),
        "corner_xyz_mm": corner_xyz,
        "registrations": registrations,
    }
    world, image, _weights, _labels = _joint_observations(
        parameters=temporary, **observation_args
    )
    initial_matrix = _projective_matrix_from_correspondences(
        _normalized_world(world), image
    )
    parameters = np.r_[
        _encode_projective(initial_matrix),
        patch_translation,
        initial_residuals,
    ]

    def evaluate(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[str]]:
        world_values, image_values, weights, labels = _joint_observations(
            parameters=values, **observation_args
        )
        predicted = _project(_decode_projective(values[:11]), world_values)
        return predicted - image_values, weights, labels

    damping = 1e-3
    converged = False
    iteration_count = 0
    for iteration in range(80):
        iteration_count = iteration + 1
        residuals, base_weights, _labels = evaluate(parameters)
        norms = np.linalg.norm(residuals, axis=1)
        robust = np.minimum(1.0, 2.0 / np.maximum(norms, 1e-9))
        point_weights = np.sqrt(base_weights * robust)
        weighted_residual = (residuals * point_weights[:, None]).ravel()
        jacobian = np.empty((weighted_residual.size, parameters.size))
        for index in range(parameters.size):
            epsilon = (
                1e-6 * max(1.0, abs(float(parameters[index])))
                if index < 11
                else 1e-4
            )
            trial = parameters.copy()
            trial[index] += epsilon
            trial_residual, _trial_weights, _trial_labels = evaluate(trial)
            jacobian[:, index] = (
                (trial_residual - residuals) * point_weights[:, None] / epsilon
            ).ravel()
        normal = jacobian.T @ jacobian
        gradient = jacobian.T @ weighted_residual
        diagonal = np.maximum(np.diag(normal), 1e-9)
        objective = _huber_objective(residuals, base_weights)
        accepted_step = False
        for _attempt in range(12):
            try:
                step = np.linalg.solve(
                    normal + damping * np.diag(diagonal), -gradient
                )
            except np.linalg.LinAlgError:
                damping *= 10.0
                continue
            trial_parameters = parameters + step
            try:
                trial_residuals, trial_weights, _trial_labels = evaluate(
                    trial_parameters
                )
                trial_objective = _huber_objective(
                    trial_residuals, trial_weights
                )
            except FineToolCalibrationError:
                trial_objective = math.inf
            if trial_objective < objective:
                parameters = trial_parameters
                damping = max(1e-8, damping * 0.35)
                accepted_step = True
                if float(np.linalg.norm(step)) < 1e-7:
                    converged = True
                break
            damping *= 5.0
        if not accepted_step:
            break
        if converged:
            break

    residuals, base_weights, labels = evaluate(parameters)
    matrix = _decode_projective(parameters[:11])
    source_rms = {}
    for label in sorted(set(labels)):
        selected = residuals[np.asarray([item == label for item in labels])]
        source_rms[label] = float(
            np.sqrt(np.mean(np.sum(selected**2, axis=1)))
        )
    tool_residuals = {
        "T0": parameters[13:16],
        "T1": parameters[16:19],
    }
    tools = {}
    for tool in ("T0", "T1"):
        residual = tool_residuals[tool]
        tools[tool] = {
            "coordinate_residual_xyz_mm": residual,
            "reference_commanded_xyz_mm": [
                float(projection["tool_models"][tool]["x_ref_mm"]),
                -14.0,
                -float(residual[2]),
            ],
            "measured_nozzle_xyz_mm": [
                float(projection["tool_models"][tool]["x_ref_mm"])
                + float(residual[0]),
                -14.0 + float(residual[1]),
                0.0,
            ],
            "commanded_z_at_print_plane_mm": -float(residual[2]),
        }
    return _finite(
        {
            "converged": converged,
            "iteration_count": iteration_count,
            "camera_matrix_normalized": matrix,
            "world_normalization": {
                "x_origin_mm": 173.0,
                "x_scale_mm": 20.0,
                "y_origin_mm": 0.0,
                "y_scale_mm": 20.0,
                "z_origin_mm": 0.0,
                "z_scale_mm": 10.0,
            },
            "patch_to_printer_xy_matrix": patch_to_printer,
            "patch_origin_printer_xy_mm": parameters[11:13],
            "tools": tools,
            "source_rms_px": source_rms,
            "joint_rms_px": float(
                np.sqrt(
                    np.sum(
                        base_weights[:, None] * residuals**2
                    )
                    / (2.0 * np.sum(base_weights))
                )
            ),
            "maximum_residual_px": float(
                np.max(np.linalg.norm(residuals, axis=1))
            ),
        }
    )


def _solve_tool(
    model: dict[str, Any],
    *,
    bed_x_vector: np.ndarray,
    physical_y_vector: np.ndarray,
    corner_pixel: np.ndarray,
    corner_xyz_mm: np.ndarray,
    reference_commanded_x_mm: float,
    capture_y_mm: float,
) -> dict[str, Any]:
    coefficients = np.asarray(model["position_coefficients"], dtype=np.float64)
    slope = coefficients[3]
    slope_norm_squared = float(np.dot(slope, slope))
    if slope_norm_squared < 1e-6:
        raise FineToolCalibrationError(
            "nozzle X-scale/Z slope is too small to identify the print plane"
        )
    z_ref = float(model["z_ref_mm"])
    x_at_z_ref = coefficients[1]
    commanded_z_at_print_plane = z_ref + float(
        np.dot(slope, bed_x_vector - x_at_z_ref) / slope_norm_squared
    )
    nozzle_x_vector = _x_vector(model, commanded_z_at_print_plane)
    vector_residual = nozzle_x_vector - bed_x_vector

    tip_pixel = _position(
        model, reference_commanded_x_mm, commanded_z_at_print_plane
    )
    basis = np.column_stack((bed_x_vector, physical_y_vector))
    condition = float(np.linalg.cond(basis))
    if not math.isfinite(condition) or condition > 25.0:
        raise FineToolCalibrationError(
            f"bed image basis is singular or ill-conditioned ({condition:.3f})"
        )
    bed_delta_xy = np.linalg.solve(basis, tip_pixel - corner_pixel)
    measured_xyz = np.asarray(
        [
            corner_xyz_mm[0] + bed_delta_xy[0],
            corner_xyz_mm[1] + bed_delta_xy[1],
            0.0,
        ],
        dtype=np.float64,
    )
    reference_commanded_xyz = np.asarray(
        [
            reference_commanded_x_mm,
            capture_y_mm,
            commanded_z_at_print_plane,
        ],
        dtype=np.float64,
    )
    residual = measured_xyz - reference_commanded_xyz
    return _finite(
        {
            "reference_commanded_xyz_mm": reference_commanded_xyz,
            "measured_nozzle_xyz_mm": measured_xyz,
            "coordinate_residual_xyz_mm": residual,
            "commanded_z_at_print_plane_mm": commanded_z_at_print_plane,
            "tip_pixel_at_print_plane_px": tip_pixel,
            "nozzle_x_vector_at_print_plane_px_per_mm": nozzle_x_vector,
            "bed_x_vector_at_print_plane_px_per_mm": bed_x_vector,
            "x_vector_residual_px_per_mm": vector_residual,
            "x_vector_residual_magnitude_px_per_mm": float(
                np.linalg.norm(vector_residual)
            ),
            "bed_image_basis_condition": condition,
        }
    )


def _stability_checks(
    model: dict[str, Any],
    records: list[dict[str, Any]],
    solve_arguments: dict[str, Any],
) -> dict[str, Any]:
    accepted_sequences = {
        int(item) for item in model.get("accepted_sequences", [])
    }
    accepted = [
        record
        for record in records
        if not accepted_sequences or int(record["seq"]) in accepted_sequences
    ]
    baseline = _solve_tool(model, **solve_arguments)
    baseline_residual = np.asarray(
        baseline["coordinate_residual_xyz_mm"], dtype=np.float64
    )
    trials = []
    groups = [
        ("x", value)
        for value in sorted({float(record["x_mm"]) for record in accepted})
    ] + [
        ("z", value)
        for value in sorted({float(record["z_mm"]) for record in accepted})
    ]
    for axis, value in groups:
        retained = [
            record
            for record in accepted
            if abs(float(record[f"{axis}_mm"]) - value) > 1e-9
        ]
        if len(retained) < 8:
            continue
        trial_model = _fit_model(
            retained,
            x_ref_mm=float(model["x_ref_mm"]),
            z_ref_mm=float(model["z_ref_mm"]),
        )
        trial = _solve_tool(trial_model, **solve_arguments)
        trial_residual = np.asarray(
            trial["coordinate_residual_xyz_mm"], dtype=np.float64
        )
        delta = trial_residual - baseline_residual
        trials.append(
            {
                "left_out_axis": axis,
                "left_out_value_mm": value,
                "coordinate_residual_xyz_mm": trial_residual.tolist(),
                "change_from_full_fit_xyz_mm": delta.tolist(),
                "change_magnitude_mm": float(np.linalg.norm(delta)),
            }
        )
    return {
        "trials": trials,
        "maximum_change_mm": max(
            (float(item["change_magnitude_mm"]) for item in trials), default=0.0
        ),
        "maximum_axis_change_mm": max(
            (
                max(abs(float(value)) for value in item["change_from_full_fit_xyz_mm"])
                for item in trials
            ),
            default=0.0,
        ),
    }


def generated_calibration(
    old_datums: dict[str, dict[str, float]],
    residuals: dict[str, list[float]],
) -> dict[str, Any]:
    old = {
        tool: {
            axis: float(old_datums[tool][f"{axis}_endstop"])
            for axis in ("x", "y", "z")
        }
        for tool in ("t0", "t1")
    }
    new = {
        tool: {
            axis: old[tool][axis] + float(residuals[tool][index])
            for index, axis in enumerate(("x", "y", "z"))
        }
        for tool in ("t0", "t1")
    }
    return {
        "persisted_calib": {
            "old": old,
            "new": new,
        },
        "generated_klipper": {
            "old": {
                "t0_x_position_endstop": old["t0"]["x"],
                "t1_x_position_endstop": old["t1"]["x"],
                "y_position_endstop": old["t0"]["y"],
                "z_position_endstop": old["t0"]["z"],
                "t1_y_gcode_offset": old["t0"]["y"] - old["t1"]["y"],
                "t1_z_gcode_offset": old["t0"]["z"] - old["t1"]["z"],
            },
            "new": {
                "t0_x_position_endstop": new["t0"]["x"],
                "t1_x_position_endstop": new["t1"]["x"],
                "y_position_endstop": new["t0"]["y"],
                "z_position_endstop": new["t0"]["z"],
                "t1_y_gcode_offset": new["t0"]["y"] - new["t1"]["y"],
                "t1_z_gcode_offset": new["t0"]["z"] - new["t1"]["z"],
            },
        },
    }


def calculate_candidate(
    *,
    projection: dict[str, Any],
    partial_bed: dict[str, Any],
    registrations: list[dict[str, Any]],
    old_datums: dict[str, dict[str, float]],
    capture_y_mm: float,
    metric: dict[str, Any] | None = None,
    metric_centers_px: list[list[list[float]]] | None = None,
    metric_commanded_y_mm: list[float] | None = None,
    corner_pixels_px: list[list[float]] | None = None,
    corner_commanded_y_mm: list[float] | None = None,
    patch_points_mm: list[list[float]] | None = None,
    fiducial_plane_z_mm: float | None = None,
) -> dict[str, Any]:
    bed_x = np.asarray(
        projection["bed_x_vector_print_plane_px_per_mm"], dtype=np.float64
    )
    image_y = np.asarray(
        projection["image_y_axis_vector_px_per_mm"], dtype=np.float64
    )
    physical_y = -image_y
    corner_xyz = np.asarray(
        partial_bed["corner_printer_xyz_mm"], dtype=np.float64
    )
    corner_pixel = np.asarray(
        partial_bed["corner_pixel_xy_px"], dtype=np.float64
    ) + image_y * (
        float(capture_y_mm)
        - float(partial_bed["corner_pixel_capture_y_mm"])
    )
    reference_x = float(
        np.mean(
            [
                float(projection["tool_models"][tool]["x_ref_mm"])
                for tool in ("T0", "T1")
            ]
        )
    )
    solve_arguments = {
        "bed_x_vector": bed_x,
        "physical_y_vector": physical_y,
        "corner_pixel": corner_pixel,
        "corner_xyz_mm": corner_xyz,
        "reference_commanded_x_mm": reference_x,
        "capture_y_mm": float(capture_y_mm),
    }
    tools = {}
    for tool in ("T0", "T1"):
        model = projection["tool_models"][tool]
        solved = _solve_tool(model, **solve_arguments)
        solved["stability"] = _stability_checks(
            model,
            [record for record in registrations if record["tool"] == tool],
            solve_arguments,
        )
        tools[tool] = solved

    joint_arguments = (
        metric,
        metric_centers_px,
        metric_commanded_y_mm,
        corner_pixels_px,
        corner_commanded_y_mm,
        patch_points_mm,
        fiducial_plane_z_mm,
    )
    joint = None
    if any(item is not None for item in joint_arguments):
        if any(item is None for item in joint_arguments):
            raise FineToolCalibrationError(
                "joint projective inputs must be supplied as one complete set"
            )
        joint = _fit_joint_projective(
            projection=projection,
            partial_bed=partial_bed,
            registrations=registrations,
            metric=metric,
            metric_centers_px=metric_centers_px,
            metric_commanded_y_mm=metric_commanded_y_mm,
            corner_pixels_px=corner_pixels_px,
            corner_commanded_y_mm=corner_commanded_y_mm,
            patch_points_mm=patch_points_mm,
            fiducial_plane_z_mm=float(fiducial_plane_z_mm),
            initial_tools=tools,
        )
        for tool in ("T0", "T1"):
            tools[tool]["nearest_vector_diagnostic"] = {
                key: tools[tool][key]
                for key in (
                    "reference_commanded_xyz_mm",
                    "measured_nozzle_xyz_mm",
                    "coordinate_residual_xyz_mm",
                    "commanded_z_at_print_plane_mm",
                )
            }
            tools[tool].update(joint["tools"][tool])

    residuals = {
        "t0": tools["T0"]["coordinate_residual_xyz_mm"],
        "t1": tools["T1"]["coordinate_residual_xyz_mm"],
    }
    calibration = generated_calibration(old_datums, residuals)
    reasons = []
    warnings = []
    if joint is not None:
        if not joint["converged"]:
            warnings.append(
                "joint projective optimizer stopped before the sub-step "
                "convergence threshold"
            )
        if float(joint["joint_rms_px"]) > 1.0:
            reasons.append(
                f"joint projective RMS is {joint['joint_rms_px']:.3f} px"
            )
        source_limits = {
            "bed_fiducial": 1.5,
            "bed_tab_corner": 1.0,
            "nozzle_T0": 1.5,
            "nozzle_T1": 1.5,
        }
        for source, limit in source_limits.items():
            value = float(joint["source_rms_px"].get(source, math.inf))
            if value > limit:
                reasons.append(
                    f"joint {source} RMS {value:.3f} px exceeds {limit:.3f} px"
                )
    for tool in ("T0", "T1"):
        result = tools[tool]
        residual = result["coordinate_residual_xyz_mm"]
        limits = (25.0, 5.0, 2.0)
        for axis, value, limit in zip("XYZ", residual, limits):
            if abs(float(value)) > limit:
                reasons.append(
                    f"{tool} {axis} correction {float(value):+.3f} mm "
                    f"exceeds {limit:.3f} mm"
                )
        z0 = float(result["commanded_z_at_print_plane_mm"])
        if abs(z0) > 2.0:
            reasons.append(
                f"{tool} fitted print plane is commanded Z={z0:+.3f} mm, "
                "not near commanded Z=0"
            )
        vector_residual = float(
            result["x_vector_residual_magnitude_px_per_mm"]
        )
        if vector_residual > 0.25:
            reasons.append(
                f"{tool} full 2-D X-vector residual is "
                f"{vector_residual:.3f} px/mm"
            )
        stability = float(result["stability"]["maximum_axis_change_mm"])
        if stability > 0.50:
            reasons.append(
                f"{tool} leave-one-row/level correction changes by "
                f"{stability:.3f} mm"
            )
        elif stability > 0.25:
            warnings.append(
                f"{tool} leave-one-row/level correction changes by "
                f"{stability:.3f} mm"
            )

    generated_new = calibration["generated_klipper"]["new"]
    if not -100.0 <= generated_new["t0_x_position_endstop"] <= -40.0:
        reasons.append("generated T0 X endstop is outside the declared safe range")
    if not 320.0 <= generated_new["t1_x_position_endstop"] <= 380.0:
        reasons.append("generated T1 X endstop is outside the declared safe range")
    if not -25.0 <= generated_new["y_position_endstop"] <= -5.0:
        reasons.append("generated shared Y endstop is outside the safe range")
    if not 285.0 <= generated_new["z_position_endstop"] <= 300.0:
        reasons.append("generated shared Z endstop is outside the safe range")
    for axis in ("t1_y_gcode_offset", "t1_z_gcode_offset"):
        if abs(float(generated_new[axis])) > 5.0:
            reasons.append(f"generated {axis} is outside +/-5 mm")

    return _finite(
        {
            "accepted": not reasons,
            "reasons": reasons,
            "warnings": warnings,
            "reference": {
                "capture_y_mm": float(capture_y_mm),
                "reference_commanded_x_mm": reference_x,
                "corner_pixel_at_capture_px": corner_pixel,
                "corner_printer_xyz_mm": corner_xyz,
                "bed_x_vector_print_plane_px_per_mm": bed_x,
                "physical_y_vector_px_per_mm": physical_y,
            },
            "tools": tools,
            "joint_projective_model": joint,
            "calibration": calibration,
            "z_verification_status": "pending_eddy_verification",
        }
    )


def write_artifacts(result: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    canvas = np.full((720, 1280, 3), 24, dtype=np.uint8)
    colors = {"T0": (80, 220, 100), "T1": (240, 120, 220)}
    cv2.putText(
        canvas,
        "Stage 5.1 fine tool XYZ calculation",
        (40, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.15,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )
    state = "ACCEPTED" if result["accepted"] else "REJECTED - NOT APPLIED"
    state_color = (80, 220, 100) if result["accepted"] else (80, 80, 255)
    cv2.putText(
        canvas,
        state,
        (40, 105),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.95,
        state_color,
        2,
        cv2.LINE_AA,
    )
    for column, tool in enumerate(("T0", "T1")):
        x0 = 45 + column * 615
        item = result["tools"][tool]
        cv2.putText(
            canvas,
            tool,
            (x0, 170),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            colors[tool],
            2,
            cv2.LINE_AA,
        )
        rows = [
            "residual XYZ: "
            + ", ".join(
                f"{float(value):+.3f}"
                for value in item["coordinate_residual_xyz_mm"]
            )
            + " mm",
            (
                "commanded Z at print plane: "
                f"{float(item['commanded_z_at_print_plane_mm']):+.3f} mm"
            ),
            (
                "2-D vector residual: "
                f"{float(item['x_vector_residual_magnitude_px_per_mm']):.3f} px/mm"
            ),
            (
                "max leave-out axis change: "
                f"{float(item['stability']['maximum_axis_change_mm']):.3f} mm"
            ),
        ]
        for row, text in enumerate(rows):
            cv2.putText(
                canvas,
                text,
                (x0, 220 + row * 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (230, 230, 230),
                1,
                cv2.LINE_AA,
            )
    y = 440
    cv2.putText(
        canvas,
        "Gates",
        (40, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )
    for reason in result["reasons"][:7]:
        y += 35
        cv2.putText(
            canvas,
            "- " + reason,
            (45, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (100, 150, 255),
            1,
            cv2.LINE_AA,
        )
    summary_path = artifact_dir / "candidate_summary.png"
    if not cv2.imwrite(str(summary_path), canvas):
        raise FineToolCalibrationError("failed to write candidate summary")

    data_path = artifact_dir / "calculation.json"
    data_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "candidate_summary": _artifact(summary_path),
        "calculation": _artifact(data_path),
    }
