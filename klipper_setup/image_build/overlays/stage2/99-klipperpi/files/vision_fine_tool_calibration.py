#!/usr/bin/env python3
"""Stage 5.1 fiducial-plane single-tool XYZ calculation and gate artifacts."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

_logger = logging.getLogger(__name__)


class FineToolCalibrationError(RuntimeError):
    pass


MODEL_FAMILY = "quadratic_x_linear_z_position_v1"
MODEL_TERMS = (
    "constant",
    "dx",
    "dz",
    "dx_dz",
    "dx_squared",
    "dx_squared_dz",
)


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


def _design(x_mm: float, z_mm: float, x_ref_mm: float, z_ref_mm: float) -> np.ndarray:
    dx = float(x_mm) - float(x_ref_mm)
    dz = float(z_mm) - float(z_ref_mm)
    return np.asarray(
        [1.0, dx, dz, dx * dz, dx * dx, dx * dx * dz],
        dtype=np.float64,
    )


def _position(model: dict[str, Any], x_mm: float, z_mm: float) -> np.ndarray:
    return _design(
        x_mm,
        z_mm,
        float(model["x_ref_mm"]),
        float(model["z_ref_mm"]),
    ) @ np.asarray(model["position_coefficients"], dtype=np.float64)


def _x_vector(model: dict[str, Any], x_mm: float, z_mm: float) -> np.ndarray:
    coefficients = np.asarray(model["position_coefficients"], dtype=np.float64)
    dx = float(x_mm) - float(model["x_ref_mm"])
    dz = float(z_mm) - float(model["z_ref_mm"])
    return (
        coefficients[1]
        + coefficients[3] * dz
        + 2.0 * coefficients[4] * dx
        + 2.0 * coefficients[5] * dx * dz
    )


def _x_vector_z_slope(model: dict[str, Any], x_mm: float) -> np.ndarray:
    coefficients = np.asarray(model["position_coefficients"], dtype=np.float64)
    dx = float(x_mm) - float(model["x_ref_mm"])
    return coefficients[3] + 2.0 * coefficients[5] * dx


def _fit_model(
    records: list[dict[str, Any]],
    *,
    x_ref_mm: float,
    z_ref_mm: float,
) -> dict[str, Any]:
    if len(records) < 12:
        raise FineToolCalibrationError("too few direct tip positions for scale field")
    design = np.asarray(
        [
            _design(record["x_mm"], record["z_mm"], x_ref_mm, z_ref_mm)
            for record in records
        ],
        dtype=np.float64,
    )
    positions = np.asarray(
        [record["center_px"] for record in records],
        dtype=np.float64,
    )
    if np.linalg.matrix_rank(design) < len(MODEL_TERMS):
        raise FineToolCalibrationError("tip-position design matrix is singular")
    coefficients = np.linalg.lstsq(design, positions, rcond=None)[0]
    residuals = positions - design @ coefficients
    return _finite(
        {
            "model_family": MODEL_FAMILY,
            "model_terms": MODEL_TERMS,
            "x_ref_mm": float(x_ref_mm),
            "z_ref_mm": float(z_ref_mm),
            "position_coefficients": coefficients,
            "position_fit_rms_px": float(
                np.sqrt(np.mean(np.sum(residuals**2, axis=1)))
            ),
            "position_fit_input": "all_supplied_absolute_coordinates",
            "position_fit_input_count": len(records),
            "pairwise_local_scales_used_for_position_fit": 0,
            "accepted_count": len(records),
            "accepted_sequences": [int(record["seq"]) for record in records],
        }
    )


def _accepted_records(
    model: dict[str, Any],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    accepted_sequences = {int(item) for item in model.get("accepted_sequences", [])}
    accepted = [
        record
        for record in records
        if not accepted_sequences or int(record["seq"]) in accepted_sequences
    ]
    if len(accepted) < 12:
        raise FineToolCalibrationError("projection fact has too few accepted records")
    return accepted


def _full_row_coverage(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for z_mm in sorted({float(record["z_mm"]) for record in records}):
        selected = [
            record for record in records if abs(float(record["z_mm"]) - z_mm) < 1e-9
        ]
        x_values = sorted({float(record["x_mm"]) for record in selected})
        if len(x_values) < 2:
            continue
        rows.append(
            {
                "z_mm": z_mm,
                "accepted_count": len(x_values),
                "x_min_mm": x_values[0],
                "x_max_mm": x_values[-1],
                "x_span_mm": x_values[-1] - x_values[0],
            }
        )
    return rows


def _magnitude_crossing(
    base_vector: np.ndarray,
    z_slope: np.ndarray,
    fiducial_scale: float,
    z_ref_mm: float,
    preferred_z_mm: float,
) -> tuple[float | None, list[float]]:
    a = float(np.dot(z_slope, z_slope))
    b = 2.0 * float(np.dot(base_vector, z_slope))
    c = float(np.dot(base_vector, base_vector) - fiducial_scale**2)
    roots: list[float] = []
    if a < 1e-12:
        if abs(b) >= 1e-12:
            roots = [float(z_ref_mm - c / b)]
    else:
        discriminant = b * b - 4.0 * a * c
        if discriminant >= 0.0:
            root = math.sqrt(discriminant)
            roots = [
                float(z_ref_mm + (-b - root) / (2.0 * a)),
                float(z_ref_mm + (-b + root) / (2.0 * a)),
            ]
    selected = (
        min(roots, key=lambda item: abs(item - preferred_z_mm)) if roots else None
    )
    return selected, roots


def _scale_crossing(
    model: dict[str, Any],
    *,
    fiducial_reference_x_mm: float,
    fiducial_x_vector_px_per_mm: np.ndarray,
    fiducial_plane_z_mm: float,
) -> dict[str, Any]:
    z_ref = float(model["z_ref_mm"])
    fiducial_scale = float(np.linalg.norm(fiducial_x_vector_px_per_mm))
    if fiducial_scale <= 1e-9:
        raise FineToolCalibrationError("fiducial X vector has zero magnitude")
    fiducial_direction = fiducial_x_vector_px_per_mm / fiducial_scale
    base_vector = _x_vector(model, fiducial_reference_x_mm, z_ref)
    z_slope = _x_vector_z_slope(model, fiducial_reference_x_mm)
    projected_slope = float(np.dot(z_slope, fiducial_direction))
    if abs(projected_slope) < 1e-6:
        raise FineToolCalibrationError(
            "transported nozzle X scale has insufficient Z dependence"
        )
    projected_base = float(np.dot(base_vector, fiducial_direction))
    commanded_z_at_fiducial = float(
        z_ref + (fiducial_scale - projected_base) / projected_slope
    )
    slope_norm_squared = float(np.dot(z_slope, z_slope))
    closest_vector_z = float(
        z_ref
        + np.dot(
            z_slope,
            fiducial_x_vector_px_per_mm - base_vector,
        )
        / slope_norm_squared
    )
    magnitude_z, magnitude_roots = _magnitude_crossing(
        base_vector,
        z_slope,
        fiducial_scale,
        z_ref,
        commanded_z_at_fiducial,
    )
    crossing_vector = _x_vector(
        model,
        fiducial_reference_x_mm,
        commanded_z_at_fiducial,
    )
    return _finite(
        {
            "fiducial_reference_printer_x_mm": fiducial_reference_x_mm,
            "fiducial_x_vector_px_per_mm": fiducial_x_vector_px_per_mm,
            "fiducial_x_scale_px_per_mm": fiducial_scale,
            "fiducial_x_direction_unit": fiducial_direction,
            "transported_vector_at_model_reference_z_px_per_mm": base_vector,
            "transported_vector_z_slope_px_per_mm_per_mm": z_slope,
            "projected_scale_at_model_reference_z_px_per_mm": projected_base,
            "projected_scale_z_slope_px_per_mm_per_mm": projected_slope,
            "commanded_z_at_fiducial_plane_mm": commanded_z_at_fiducial,
            "closest_full_vector_commanded_z_mm": closest_vector_z,
            "magnitude_crossing_commanded_z_mm": magnitude_z,
            "magnitude_crossing_roots_mm": magnitude_roots,
            "crossing_vector_px_per_mm": crossing_vector,
            "crossing_vector_residual_px_per_mm": crossing_vector
            - fiducial_x_vector_px_per_mm,
            "fiducial_plane_printer_z_mm": fiducial_plane_z_mm,
            "bed_referenced_z_at_commanded_zero_mm": fiducial_plane_z_mm
            - commanded_z_at_fiducial,
        }
    )


def _projective_matrix_from_correspondences(
    world_points: np.ndarray, image_points: np.ndarray
) -> np.ndarray:
    rows = []
    for world, image in zip(world_points, image_points):
        homogeneous = np.asarray([*world, 1.0], dtype=np.float64)
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


def _affine_projective_initialization(
    world_points: np.ndarray, image_points: np.ndarray
) -> np.ndarray:
    normalized = _normalized_world(world_points)
    design = np.column_stack((normalized, np.ones(len(normalized), dtype=np.float64)))
    coefficients = np.linalg.lstsq(design, image_points, rcond=None)[0]
    return np.asarray(
        [
            coefficients[:, 0],
            coefficients[:, 1],
            [0.0, 0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


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
    patch_to_printer_xy: np.ndarray,
    patch_origin_printer_xy: np.ndarray,
    patch_points_mm: np.ndarray,
    metric_observations: list[dict[str, Any]],
    corner_observations: list[dict[str, Any]],
    corner_xyz_mm: np.ndarray,
    fiducial_plane_z_mm: float,
    registrations: list[dict[str, Any]],
    tool: str,
    tool_z_residual_mm: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    tool_xy_residual = parameters[11:13]
    world_points = []
    image_points = []
    weights = []
    labels = []
    absolute_patch_xy = (
        patch_points_mm @ patch_to_printer_xy.T + patch_origin_printer_xy
    )
    for observation in metric_observations:
        commanded_y = float(observation["commanded_y_mm"])
        for absolute_xy, image_xy in zip(absolute_patch_xy, observation["centers_px"]):
            world_points.append(
                [
                    float(absolute_xy[0]),
                    float(absolute_xy[1] + commanded_y),
                    fiducial_plane_z_mm,
                ]
            )
            image_points.append(image_xy)
            weights.append(1.0)
            labels.append("bed_fiducial")
    for observation in corner_observations:
        commanded_y = float(observation["commanded_y_mm"])
        world_points.append(
            [
                float(corner_xyz_mm[0]),
                float(corner_xyz_mm[1] + commanded_y),
                float(corner_xyz_mm[2]),
            ]
        )
        image_points.append(observation["pixel_px"])
        weights.append(2.0)
        labels.append("bed_tab_corner")
    for record in registrations:
        if str(record["tool"]) != tool:
            raise FineToolCalibrationError(
                f"{tool} calculation received a {record['tool']} registration"
            )
        world_points.append(
            [
                float(record["x_mm"]) + float(tool_xy_residual[0]),
                float(tool_xy_residual[1]),
                float(record["z_mm"]) + float(tool_z_residual_mm),
            ]
        )
        image_points.append(record["center_px"])
        weights.append(1.0)
        labels.append(f"nozzle_{tool}")
    return (
        np.asarray(world_points, dtype=np.float64),
        np.asarray(image_points, dtype=np.float64),
        np.asarray(weights, dtype=np.float64),
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


def _fit_joint_projective_xy(
    *,
    registrations: list[dict[str, Any]],
    metric_observations: list[dict[str, Any]],
    corner_observations: list[dict[str, Any]],
    patch_points_mm: list[list[float]],
    patch_to_printer_xy: list[list[float]],
    patch_origin_printer_xy_mm: list[float],
    corner_xyz_mm: list[float],
    fiducial_plane_z_mm: float,
    tool: str,
    tool_z_residual_mm: float,
) -> dict[str, Any]:
    if len(metric_observations) < 4:
        raise FineToolCalibrationError(
            "joint XY solve needs at least four metric observations"
        )
    if len(corner_observations) < 3:
        raise FineToolCalibrationError(
            "joint XY solve needs at least three corner observations"
        )
    observation_args = {
        "patch_to_printer_xy": np.asarray(patch_to_printer_xy, dtype=np.float64),
        "patch_origin_printer_xy": np.asarray(
            patch_origin_printer_xy_mm, dtype=np.float64
        ),
        "patch_points_mm": np.asarray(patch_points_mm, dtype=np.float64),
        "metric_observations": metric_observations,
        "corner_observations": corner_observations,
        "corner_xyz_mm": np.asarray(corner_xyz_mm, dtype=np.float64),
        "fiducial_plane_z_mm": float(fiducial_plane_z_mm),
        "registrations": registrations,
        "tool": tool,
        "tool_z_residual_mm": tool_z_residual_mm,
    }
    temporary = np.r_[np.zeros(11), np.zeros(2)]
    world, image, _weights, _labels = _joint_observations(
        parameters=temporary, **observation_args
    )
    initial_matrix = _affine_projective_initialization(world, image)
    parameters = temporary.copy()
    parameters[:11] = _encode_projective(initial_matrix)

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
                1e-6 * max(1.0, abs(float(parameters[index]))) if index < 11 else 1e-4
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
                step = np.linalg.solve(normal + damping * np.diag(diagonal), -gradient)
            except np.linalg.LinAlgError:
                damping *= 10.0
                continue
            trial_parameters = parameters + step
            try:
                trial_residuals, trial_weights, _trial_labels = evaluate(
                    trial_parameters
                )
                trial_objective = _huber_objective(trial_residuals, trial_weights)
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
        if not accepted_step or converged:
            break

    residuals, base_weights, labels = evaluate(parameters)
    source_rms = {}
    for label in sorted(set(labels)):
        selected = residuals[np.asarray([item == label for item in labels])]
        source_rms[label] = float(np.sqrt(np.mean(np.sum(selected**2, axis=1))))
    return _finite(
        {
            "converged": converged,
            "iteration_count": iteration_count,
            "camera_matrix_normalized": _decode_projective(parameters[:11]),
            "patch_origin_printer_xy_mm": patch_origin_printer_xy_mm,
            "tool": tool,
            "tool_xy_residual_mm": parameters[11:13],
            "source_rms_px": source_rms,
            "joint_rms_px": float(
                np.sqrt(
                    np.sum(base_weights[:, None] * residuals**2)
                    / (2.0 * np.sum(base_weights))
                )
            ),
            "maximum_residual_px": float(np.max(np.linalg.norm(residuals, axis=1))),
        }
    )


def _stability_checks(
    *,
    model: dict[str, Any],
    records: list[dict[str, Any]],
    crossing_arguments: dict[str, Any],
) -> dict[str, Any]:
    baseline = _scale_crossing(model, **crossing_arguments)
    baseline_z = float(baseline["commanded_z_at_fiducial_plane_mm"])
    trials = []
    x_values = sorted({float(record["x_mm"]) for record in records})
    interior_x = set(x_values[1:-1])
    for record in records:
        if float(record["x_mm"]) not in interior_x:
            continue
        retained = [item for item in records if int(item["seq"]) != int(record["seq"])]
        trial_model = _fit_model(
            retained,
            x_ref_mm=float(model["x_ref_mm"]),
            z_ref_mm=float(model["z_ref_mm"]),
        )
        crossing = _scale_crossing(trial_model, **crossing_arguments)
        trial_z = float(crossing["commanded_z_at_fiducial_plane_mm"])
        trials.append(
            {
                "kind": "leave_one_x_observation",
                "left_out_sequence": int(record["seq"]),
                "left_out_x_mm": float(record["x_mm"]),
                "left_out_z_mm": float(record["z_mm"]),
                "commanded_z_at_fiducial_plane_mm": trial_z,
                "change_mm": trial_z - baseline_z,
            }
        )
    for row in _full_row_coverage(records):
        retained = [
            record
            for record in records
            if abs(float(record["z_mm"]) - float(row["z_mm"])) > 1e-9
        ]
        if len(retained) < 12:
            continue
        try:
            trial_model = _fit_model(
                retained,
                x_ref_mm=float(model["x_ref_mm"]),
                z_ref_mm=float(model["z_ref_mm"]),
            )
            crossing = _scale_crossing(trial_model, **crossing_arguments)
        except FineToolCalibrationError:
            continue
        trial_z = float(crossing["commanded_z_at_fiducial_plane_mm"])
        trials.append(
            {
                "kind": "leave_one_full_z_row",
                "left_out_z_mm": float(row["z_mm"]),
                "commanded_z_at_fiducial_plane_mm": trial_z,
                "change_mm": trial_z - baseline_z,
            }
        )
    return _finite(
        {
            "baseline_commanded_z_at_fiducial_plane_mm": baseline_z,
            "trials": trials,
            "maximum_change_mm": max(
                (abs(float(item["change_mm"])) for item in trials),
                default=0.0,
            ),
            "maximum_observation_change_mm": max(
                (
                    abs(float(item["change_mm"]))
                    for item in trials
                    if item["kind"] == "leave_one_x_observation"
                ),
                default=0.0,
            ),
            "maximum_full_row_change_mm": max(
                (
                    abs(float(item["change_mm"]))
                    for item in trials
                    if item["kind"] == "leave_one_full_z_row"
                ),
                default=0.0,
            ),
        }
    )


def _solve_tool(
    *,
    model: dict[str, Any],
    records: list[dict[str, Any]],
    fiducial_reference_xy_mm: np.ndarray,
    fiducial_x_vector_px_per_mm: np.ndarray,
    fiducial_plane_z_mm: float,
    capture_y_mm: float,
) -> dict[str, Any]:
    accepted = _accepted_records(model, records)
    crossing_arguments = {
        "fiducial_reference_x_mm": float(fiducial_reference_xy_mm[0]),
        "fiducial_x_vector_px_per_mm": fiducial_x_vector_px_per_mm,
        "fiducial_plane_z_mm": fiducial_plane_z_mm,
    }
    crossing = _scale_crossing(model, **crossing_arguments)
    crossing_z = float(crossing["commanded_z_at_fiducial_plane_mm"])
    reference_x = float(model["x_ref_mm"])
    tip_pixel = _position(model, reference_x, crossing_z)
    reference_commanded_xyz = np.asarray(
        [reference_x, capture_y_mm, crossing_z],
        dtype=np.float64,
    )
    coordinate_residual = np.asarray(
        [0.0, 0.0, fiducial_plane_z_mm - crossing_z],
        dtype=np.float64,
    )
    measured_xyz = reference_commanded_xyz + coordinate_residual
    stability = _stability_checks(
        model=model,
        records=accepted,
        crossing_arguments=crossing_arguments,
    )
    coverage = _full_row_coverage(accepted)
    measured_x_values = [float(record["x_mm"]) for record in accepted]
    extrapolation = max(
        0.0,
        min(measured_x_values) - float(fiducial_reference_xy_mm[0]),
        float(fiducial_reference_xy_mm[0]) - max(measured_x_values),
    )
    return _finite(
        {
            "reference_commanded_xyz_mm": reference_commanded_xyz,
            "measured_nozzle_xyz_mm": measured_xyz,
            "coordinate_residual_xyz_mm": coordinate_residual,
            "tip_pixel_at_fiducial_plane_px": tip_pixel,
            "lateral_extrapolation_distance_mm": extrapolation,
            "measured_x_range_mm": [
                min(measured_x_values),
                max(measured_x_values),
            ],
            "measured_z_range_mm": [
                min(float(record["z_mm"]) for record in accepted),
                max(float(record["z_mm"]) for record in accepted),
            ],
            "full_row_coverage": coverage,
            "scale_crossing": crossing,
            "stability": stability,
        }
    )


def generated_calibration(
    old_datums: dict[str, dict[str, float]],
    *,
    tool: str,
    residual_xyz_mm: list[float],
) -> dict[str, Any]:
    old = {
        tool_name: {
            axis: float(old_datums[tool_name][f"{axis}_endstop"])
            for axis in ("x", "y", "z")
        }
        for tool_name in ("t0", "t1")
    }
    new = {tool_name: dict(values) for tool_name, values in old.items()}
    target = tool.lower()
    for index, axis in enumerate(("x", "y", "z")):
        new[target][axis] += float(residual_xyz_mm[index])
    return {
        "tool": tool,
        "persisted_calib": {"old": old, "new": new},
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
    tool: str,
    projection: dict[str, Any],
    registrations: list[dict[str, Any]],
    metric_observations: list[dict[str, Any]],
    corner_observations: list[dict[str, Any]],
    physical_reference: dict[str, Any],
    mapping: dict[str, Any],
    partial_bed: dict[str, Any],
    old_datums: dict[str, dict[str, float]],
) -> dict[str, Any]:
    if tool not in {"T0", "T1"}:
        raise FineToolCalibrationError(f"unsupported tool {tool!r}")
    fiducial_xy = np.asarray(
        projection["fiducial_reference_printer_xy_mm"],
        dtype=np.float64,
    )
    fiducial_x_vector = np.asarray(
        projection["fiducial_x_vector_at_fine_capture_px_per_mm"],
        dtype=np.float64,
    )
    fiducial_z = float(projection["fiducial_plane_printer_z_mm"])
    capture_y = float(projection["fine_capture_y_mm"])
    reasons = []
    warnings = []
    model = projection["tool_models"][tool]
    if model.get("model_family") != MODEL_FAMILY:
        raise FineToolCalibrationError(f"{tool} projection model is not {MODEL_FAMILY}")
    if any(str(record.get("tool")) != tool for record in registrations):
        raise FineToolCalibrationError(
            f"{tool} calculation received registrations from another tool"
        )
    accepted_registrations = _accepted_records(model, registrations)
    accepted_sequences = {int(record["seq"]) for record in accepted_registrations}
    discarded_sequences = [
        int(record["seq"])
        for record in registrations
        if int(record["seq"]) not in accepted_sequences
    ]
    _logger.info(
        "stage5.1 registration input tool=%s provided=%d accepted_green=%d "
        "discarded_rejected=%d discarded_sequences=%s",
        tool,
        len(registrations),
        len(accepted_registrations),
        len(discarded_sequences),
        ",".join(str(item) for item in discarded_sequences) or "none",
    )
    solved = _solve_tool(
        model=model,
        records=accepted_registrations,
        fiducial_reference_xy_mm=fiducial_xy,
        fiducial_x_vector_px_per_mm=fiducial_x_vector,
        fiducial_plane_z_mm=fiducial_z,
        capture_y_mm=capture_y,
    )
    solved["projection_model"] = model
    tools = {tool: solved}
    if float(model["position_fit_rms_px"]) > 1.5:
        reasons.append(f"{tool} position fit RMS {model['position_fit_rms_px']:.3f} px")
    rows = solved["full_row_coverage"]
    expected_row_count = len({float(record["z_mm"]) for record in registrations})
    if len(rows) < expected_row_count:
        reasons.append(
            f"{tool} has only {len(rows)} usable X rows from "
            f"{expected_row_count} captured Z heights"
        )
    for row in rows:
        if int(row["accepted_count"]) < 4 or float(row["x_span_mm"]) < 8.0:
            reasons.append(
                f"{tool} Z={row['z_mm']:.3f} row has "
                f"{row['accepted_count']} accepted X positions over "
                f"{row['x_span_mm']:.3f} mm; at least 4 positions over "
                "8.000 mm are required"
            )
    crossing = solved["scale_crossing"]
    z_crossing = float(crossing["commanded_z_at_fiducial_plane_mm"])
    z_min, z_max = solved["measured_z_range_mm"]
    row_z = sorted(float(row["z_mm"]) for row in rows)
    row_interval = max(
        (second - first for first, second in zip(row_z, row_z[1:])),
        default=4.0,
    )
    if not z_min - row_interval <= z_crossing <= z_max + row_interval:
        reasons.append(
            f"{tool} fiducial-plane crossing Z={z_crossing:+.3f} mm is "
            f"outside the measured Z={z_min:.3f}..{z_max:.3f} mm range by "
            "more than one sampled row interval"
        )
    projected_slope = float(crossing["projected_scale_z_slope_px_per_mm_per_mm"])
    if abs(projected_slope) < 0.01:
        reasons.append(f"{tool} transported scale is not Z-identifiable")
    magnitude_z = crossing["magnitude_crossing_commanded_z_mm"]
    if magnitude_z is None or abs(float(magnitude_z) - z_crossing) > 0.25:
        reasons.append(
            f"{tool} scalar scale checks disagree: image-X crossing "
            f"{z_crossing:+.3f} mm versus vector-magnitude crossing "
            f"{'unresolved' if magnitude_z is None else f'{float(magnitude_z):+.3f} mm'}"
        )
    closest_z = float(crossing["closest_full_vector_commanded_z_mm"])
    full_vector_difference = abs(closest_z - z_crossing)
    if full_vector_difference > 0.75:
        reasons.append(
            f"{tool} 2D vector check disagrees: image-X crossing "
            f"{z_crossing:+.3f} mm versus closest full-vector match "
            f"{closest_z:+.3f} mm ({full_vector_difference:.3f} mm apart)"
        )
    elif full_vector_difference > 0.25:
        warnings.append(
            f"{tool} image-X crossing and closest full-vector match are "
            f"{full_vector_difference:.3f} mm apart"
        )
    observation_trials = [
        item
        for item in solved["stability"]["trials"]
        if item["kind"] == "leave_one_x_observation"
    ]
    worst_observation = max(
        observation_trials,
        key=lambda item: abs(float(item["change_mm"])),
        default=None,
    )
    observation_stability = float(solved["stability"]["maximum_observation_change_mm"])
    observation_message = (
        f"{tool} single-sample sensitivity check: omitting the sample at "
        f"X={worst_observation['left_out_x_mm']:.3f}, "
        f"Z={worst_observation['left_out_z_mm']:.3f} mm changes the computed "
        f"fiducial-plane crossing by {observation_stability:.3f} mm"
        if worst_observation is not None
        else f"{tool} single-sample sensitivity check could not be run"
    )
    if observation_stability > 1.50:
        reasons.append(observation_message)
    elif observation_stability > 0.50:
        warnings.append(observation_message)
    row_trials = [
        item
        for item in solved["stability"]["trials"]
        if item["kind"] == "leave_one_full_z_row"
    ]
    worst_row = max(
        row_trials,
        key=lambda item: abs(float(item["change_mm"])),
        default=None,
    )
    row_stability = float(solved["stability"]["maximum_full_row_change_mm"])
    row_message = (
        f"{tool} full-row sensitivity check: refitting after omitting all "
        f"accepted samples at Z={worst_row['left_out_z_mm']:.3f} mm changes "
        f"the computed fiducial-plane crossing from {z_crossing:+.3f} to "
        f"{float(worst_row['commanded_z_at_fiducial_plane_mm']):+.3f} mm "
        f"({row_stability:.3f} mm)"
        if worst_row is not None
        else f"{tool} full-row sensitivity check could not be run"
    )
    if row_stability > 2.0:
        reasons.append(row_message)
    elif row_stability > 0.50:
        warnings.append(row_message)
    if float(solved["lateral_extrapolation_distance_mm"]) > 15.0:
        warnings.append(
            f"{tool} scale field is extrapolated "
            f"{solved['lateral_extrapolation_distance_mm']:.3f} mm "
            "to the fiducial reference X"
        )

    z_residual = float(solved["coordinate_residual_xyz_mm"][2])
    joint_xy = _fit_joint_projective_xy(
        registrations=accepted_registrations,
        metric_observations=metric_observations,
        corner_observations=corner_observations,
        patch_points_mm=physical_reference["centers_patch_xy_mm"],
        patch_to_printer_xy=mapping["patch_to_printer_xy_matrix"],
        patch_origin_printer_xy_mm=mapping["patch_origin_printer_xy_mm"],
        corner_xyz_mm=partial_bed["corner_printer_xyz_mm"],
        fiducial_plane_z_mm=fiducial_z,
        tool=tool,
        tool_z_residual_mm=z_residual,
    )
    projective_xy = np.asarray(joint_xy["tool_xy_residual_mm"], dtype=np.float64)
    corner_y = float(partial_bed["corner_printer_xyz_mm"][1])
    aligned_corner_command_y = float(projective_xy[1] - corner_y)
    xy_residual = np.asarray(
        [
            projective_xy[0],
            aligned_corner_command_y - corner_y,
        ],
        dtype=np.float64,
    )
    residual = np.asarray(
        [xy_residual[0], xy_residual[1], z_residual],
        dtype=np.float64,
    )
    solved["coordinate_residual_xyz_mm"] = residual.tolist()
    solved["reference_commanded_xyz_mm"] = [
        float(model["x_ref_mm"]),
        corner_y,
        z_crossing,
    ]
    solved["measured_nozzle_xyz_mm"] = [
        float(model["x_ref_mm"]) + xy_residual[0],
        aligned_corner_command_y,
        fiducial_z,
    ]
    solved["projective_camera_y_mm"] = float(projective_xy[1])
    solved["bed_tab_corner_aligned_command_y_mm"] = aligned_corner_command_y
    for axis, value, limit in zip("XYZ", residual, (25.0, 5.0, 2.0)):
        if abs(float(value)) > limit:
            reasons.append(
                f"{tool} {axis} correction {float(value):+.3f} mm "
                f"exceeds {limit:.3f} mm"
            )
    if not joint_xy["converged"]:
        warnings.append("joint projective XY fit stopped before step convergence")
    if float(joint_xy["joint_rms_px"]) > 1.5:
        reasons.append(f"joint projective XY RMS is {joint_xy['joint_rms_px']:.3f} px")
    elif float(joint_xy["joint_rms_px"]) > 0.9:
        warnings.append(f"joint projective XY RMS is {joint_xy['joint_rms_px']:.3f} px")
    for source, rms in joint_xy["source_rms_px"].items():
        if float(rms) > 3.0:
            reasons.append(f"{source} projective RMS is {float(rms):.3f} px")

    calibration = generated_calibration(
        old_datums,
        tool=tool,
        residual_xyz_mm=solved["coordinate_residual_xyz_mm"],
    )
    generated_new = calibration["generated_klipper"]["new"]
    if not -100.0 <= generated_new["t0_x_position_endstop"] <= -40.0:
        reasons.append("generated T0 X endstop is outside the safe range")
    if not 320.0 <= generated_new["t1_x_position_endstop"] <= 380.0:
        reasons.append("generated T1 X endstop is outside the safe range")
    if not -25.0 <= generated_new["y_position_endstop"] <= -5.0:
        reasons.append("generated shared Y endstop is outside the safe range")
    if not 285.0 <= generated_new["z_position_endstop"] <= 300.0:
        reasons.append("generated shared Z endstop is outside the safe range")
    for axis in ("t1_y_gcode_offset", "t1_z_gcode_offset"):
        if abs(float(generated_new[axis])) > 5.0:
            reasons.append(f"generated {axis} is outside +/-5 mm")
    unique_reasons = sorted(set(reasons))
    unique_warnings = sorted(set(warnings))
    _logger.info(
        "stage5.1 result tool=%s accepted=%s accepted_green=%d "
        "discarded_rejected=%d rejection_count=%d warning_count=%d",
        tool,
        not unique_reasons,
        len(accepted_registrations),
        len(discarded_sequences),
        len(unique_reasons),
        len(unique_warnings),
    )
    for reason in unique_reasons:
        _logger.info(
            "analysis rejected stage=stage5.1_acceptance_gate tool=%s reason=%s",
            tool,
            reason,
        )
    for warning in unique_warnings:
        _logger.info(
            "analysis warning stage=stage5.1_acceptance_gate tool=%s reason=%s",
            tool,
            warning,
        )
    return _finite(
        {
            "accepted": not unique_reasons,
            "tool": tool,
            "reasons": unique_reasons,
            "warnings": unique_warnings,
            "registration_usage": {
                "provided_count": len(registrations),
                "accepted_green_count": len(accepted_registrations),
                "discarded_rejected_count": len(discarded_sequences),
                "accepted_sequences": sorted(accepted_sequences),
                "discarded_sequences": discarded_sequences,
            },
            "reference": {
                "fiducial_reference_printer_xy_mm": fiducial_xy,
                "fiducial_x_vector_at_fine_capture_px_per_mm": fiducial_x_vector,
                "fiducial_plane_printer_z_mm": fiducial_z,
                "fine_capture_y_mm": capture_y,
            },
            "tools": tools,
            "joint_projective_xy": joint_xy,
            "calibration": calibration,
        }
    )


def _map_plot_point(
    x_value: float,
    y_value: float,
    *,
    x_limits: tuple[float, float],
    y_limits: tuple[float, float],
    rectangle: tuple[int, int, int, int],
) -> tuple[int, int]:
    left, top, right, bottom = rectangle
    x = left + (x_value - x_limits[0]) * (right - left) / max(
        1e-9, x_limits[1] - x_limits[0]
    )
    y = bottom - (y_value - y_limits[0]) * (bottom - top) / max(
        1e-9, y_limits[1] - y_limits[0]
    )
    return int(round(x)), int(round(y))


def _write_scale_transport(result: dict[str, Any], path: Path) -> None:
    canvas = np.full((900, 1500, 3), 24, dtype=np.uint8)
    colors = {"T0": (70, 230, 100), "T1": (230, 110, 230)}
    fiducial_scale = float(
        np.linalg.norm(
            result["reference"]["fiducial_x_vector_at_fine_capture_px_per_mm"]
        )
    )
    for column, tool in enumerate((result["tool"],)):
        left = 70 + column * 740
        rectangle = (left, 110, left + 650, 790)
        item = result["tools"][tool]
        model = item["projection_model"]
        crossing = item["scale_crossing"]
        direction = np.asarray(
            crossing["fiducial_x_direction_unit"],
            dtype=np.float64,
        )
        x_fid = float(crossing["fiducial_reference_printer_x_mm"])
        z_cross = float(crossing["commanded_z_at_fiducial_plane_mm"])
        z_values = np.linspace(-3.0, 13.0, 321)
        scales = [
            float(np.dot(_x_vector(model, x_fid, z), direction)) for z in z_values
        ]
        y_min = min(min(scales), fiducial_scale) - 0.25
        y_max = max(max(scales), fiducial_scale) + 0.25
        cv2.rectangle(
            canvas,
            (rectangle[0], rectangle[1]),
            (rectangle[2], rectangle[3]),
            (100, 100, 100),
            1,
        )
        points = [
            _map_plot_point(
                float(z),
                scale,
                x_limits=(-3.0, 13.0),
                y_limits=(y_min, y_max),
                rectangle=rectangle,
            )
            for z, scale in zip(z_values, scales)
        ]
        cv2.polylines(canvas, [np.asarray(points)], False, colors[tool], 3)
        line_y = _map_plot_point(
            0.0,
            fiducial_scale,
            x_limits=(-3.0, 13.0),
            y_limits=(y_min, y_max),
            rectangle=rectangle,
        )[1]
        cv2.line(
            canvas,
            (rectangle[0], line_y),
            (rectangle[2], line_y),
            (0, 220, 255),
            2,
        )
        crossing_point = _map_plot_point(
            z_cross,
            fiducial_scale,
            x_limits=(-3.0, 13.0),
            y_limits=(y_min, y_max),
            rectangle=rectangle,
        )
        cv2.drawMarker(
            canvas,
            crossing_point,
            (0, 255, 255),
            cv2.MARKER_TILTED_CROSS,
            24,
            3,
        )
        cv2.putText(
            canvas,
            (
                f"{tool}: crossing Zcmd={z_cross:+.4f}, "
                "bed residual="
                f"{crossing['bed_referenced_z_at_commanded_zero_mm']:+.4f} mm"
            ),
            (left, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.70,
            colors[tool],
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            (
                f"Xfid={x_fid:.3f}; extrapolation="
                f"{item['lateral_extrapolation_distance_mm']:.3f} mm"
            ),
            (left, 85),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (225, 225, 225),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "commanded Z [mm]",
            (left + 250, 840),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.60,
            (220, 220, 220),
            1,
            cv2.LINE_AA,
        )
    if not cv2.imwrite(str(path), canvas):
        raise FineToolCalibrationError("failed to write scale-transport plot")


def _write_scale_vs_x(result: dict[str, Any], path: Path) -> None:
    canvas = np.full((900, 1500, 3), 24, dtype=np.uint8)
    row_colors = {
        1.0: (80, 180, 255),
        5.0: (80, 240, 120),
        9.0: (240, 120, 220),
    }
    for column, tool in enumerate((result["tool"],)):
        left = 70 + column * 740
        rectangle = (left, 110, left + 650, 790)
        item = result["tools"][tool]
        model = item["projection_model"]
        crossing = item["scale_crossing"]
        direction = np.asarray(
            crossing["fiducial_x_direction_unit"],
            dtype=np.float64,
        )
        x_fid = float(crossing["fiducial_reference_printer_x_mm"])
        x_values = np.linspace(x_fid, 199.0, 300)
        rows = [float(row["z_mm"]) for row in item["full_row_coverage"]]
        all_scales = [
            float(np.dot(_x_vector(model, x, z), direction))
            for z in rows
            for x in x_values
        ]
        y_limits = (min(all_scales) - 0.2, max(all_scales) + 0.2)
        cv2.rectangle(
            canvas,
            (rectangle[0], rectangle[1]),
            (rectangle[2], rectangle[3]),
            (100, 100, 100),
            1,
        )
        for z in rows:
            scales = [
                float(np.dot(_x_vector(model, x, z), direction)) for x in x_values
            ]
            points = [
                _map_plot_point(
                    float(x),
                    scale,
                    x_limits=(x_fid, 199.0),
                    y_limits=y_limits,
                    rectangle=rectangle,
                )
                for x, scale in zip(x_values, scales)
            ]
            color = row_colors.get(z, (200, 200, 200))
            cv2.polylines(canvas, [np.asarray(points)], False, color, 3)
            cv2.putText(
                canvas,
                f"Z={z:g}",
                (rectangle[2] - 85, points[-1][1] - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.50,
                color,
                1,
                cv2.LINE_AA,
            )
        measured_min, measured_max = item["measured_x_range_mm"]
        for x_value, color in (
            (x_fid, (0, 255, 255)),
            (float(measured_min), (255, 180, 60)),
            (float(measured_max), (255, 180, 60)),
        ):
            x_pixel = _map_plot_point(
                x_value,
                y_limits[0],
                x_limits=(x_fid, 199.0),
                y_limits=y_limits,
                rectangle=rectangle,
            )[0]
            cv2.line(
                canvas,
                (x_pixel, rectangle[1]),
                (x_pixel, rectangle[3]),
                color,
                2,
            )
        cv2.putText(
            canvas,
            f"{tool}: local printer-X scale transported to Xfid",
            (left, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.70,
            (235, 235, 235),
            2,
            cv2.LINE_AA,
        )
    if not cv2.imwrite(str(path), canvas):
        raise FineToolCalibrationError("failed to write scale-versus-X plot")


def write_artifacts(result: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    summary = np.full((760, 1400, 3), 24, dtype=np.uint8)
    cv2.putText(
        summary,
        "Stage 5.1 fiducial-plane fine tool XYZ gate",
        (40, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.05,
        (245, 245, 245),
        2,
        cv2.LINE_AA,
    )
    state = "ACCEPTED - CANDIDATE ONLY" if result["accepted"] else "REJECTED"
    state_color = (80, 220, 100) if result["accepted"] else (80, 80, 255)
    cv2.putText(
        summary,
        state,
        (40, 105),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.88,
        state_color,
        2,
        cv2.LINE_AA,
    )
    colors = {"T0": (80, 220, 100), "T1": (240, 120, 220)}

    def formatted(value: Any) -> str:
        return "unresolved" if value is None else f"{float(value):+.4f}"

    for column, tool in enumerate((result["tool"],)):
        x0 = 45 + column * 675
        item = result["tools"][tool]
        crossing = item["scale_crossing"]
        rows = [
            (
                "residual XYZ: "
                + ", ".join(
                    f"{float(value):+.4f}"
                    for value in item["coordinate_residual_xyz_mm"]
                )
                + " mm"
            ),
            (
                "Zcmd at fiducial plane: "
                f"{crossing['commanded_z_at_fiducial_plane_mm']:+.4f} mm"
            ),
            (
                "bed Z at commanded zero: "
                f"{crossing['bed_referenced_z_at_commanded_zero_mm']:+.4f} mm"
            ),
            (
                "projection / magnitude / full-vector Z: "
                f"{crossing['commanded_z_at_fiducial_plane_mm']:+.4f} / "
                f"{formatted(crossing['magnitude_crossing_commanded_z_mm'])} / "
                f"{crossing['closest_full_vector_commanded_z_mm']:+.4f}"
            ),
            (
                "worst single-sample / full-row refit change: "
                f"{item['stability']['maximum_observation_change_mm']:.4f} / "
                f"{item['stability']['maximum_full_row_change_mm']:.4f} mm"
            ),
        ]
        cv2.putText(
            summary,
            tool,
            (x0, 170),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.95,
            colors[tool],
            2,
            cv2.LINE_AA,
        )
        for row_index, text in enumerate(rows):
            cv2.putText(
                summary,
                text,
                (x0, 215 + row_index * 42),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.53,
                (230, 230, 230),
                1,
                cv2.LINE_AA,
            )
    y = 485
    for reason in result["reasons"][:7]:
        cv2.putText(
            summary,
            "- " + reason,
            (45, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (100, 150, 255),
            1,
            cv2.LINE_AA,
        )
        y += 32
    summary_path = artifact_dir / "candidate_summary.png"
    if not cv2.imwrite(str(summary_path), summary):
        raise FineToolCalibrationError("failed to write candidate summary")
    transport_path = artifact_dir / "scale_transport_to_fiducial_plane.png"
    _write_scale_transport(result, transport_path)
    scale_x_path = artifact_dir / "local_scale_vs_printer_x.png"
    _write_scale_vs_x(result, scale_x_path)
    data_path = artifact_dir / "calculation.json"
    data_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "candidate_summary": _artifact(summary_path),
        "scale_transport_to_fiducial_plane": _artifact(transport_path),
        "local_scale_vs_printer_x": _artifact(scale_x_path),
        "calculation": _artifact(data_path),
    }
