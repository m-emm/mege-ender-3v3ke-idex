#!/usr/bin/env python3
"""Fine T0/T1 nozzle X/Z grid analysis using relative template registration."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from vision_red_marker_x_sweep import _red_candidates


class FineNozzleError(RuntimeError):
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


def _gray(image: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _clahe(image: np.ndarray) -> np.ndarray:
    return cv2.createCLAHE(2.0, (8, 8)).apply(_gray(image))


def _select_marker(
    image: np.ndarray, expected: np.ndarray, frame_index: int
) -> tuple[np.ndarray, dict[str, Any] | None]:
    candidates = _red_candidates(image, frame_index)
    if not candidates:
        return expected.copy(), None
    selected = min(
        candidates,
        key=lambda item: float(
            np.linalg.norm(np.asarray(item["center_px"]) - expected)
        ),
    )
    center = np.asarray(selected["center_px"], dtype=np.float64)
    if float(np.linalg.norm(center - expected)) > 130.0:
        return expected.copy(), None
    return center, selected


def _circle_edge_score(
    gray: np.ndarray, center: np.ndarray, radius: float
) -> float:
    angles = np.linspace(0.0, 2.0 * math.pi, 96, endpoint=False)
    scores = []
    for scale in (0.82, 0.94, 1.06, 1.18):
        xs = np.rint(center[0] + radius * scale * np.cos(angles)).astype(int)
        ys = np.rint(center[1] + radius * scale * np.sin(angles)).astype(int)
        valid = (
            (xs >= 1)
            & (xs < gray.shape[1] - 1)
            & (ys >= 1)
            & (ys < gray.shape[0] - 1)
        )
        if int(np.count_nonzero(valid)) < 80:
            return 0.0
        values = gray[ys[valid], xs[valid]].astype(np.float64)
        scores.append((float(np.mean(values)), float(np.std(values))))
    means = np.asarray([item[0] for item in scores])
    symmetry = float(np.median([item[1] for item in scores]))
    return float(np.sum(np.abs(np.diff(means))) - 0.35 * symmetry)


def _nozzle_candidates(
    image: np.ndarray, marker: np.ndarray
) -> list[dict[str, Any]]:
    height, width = image.shape[:2]
    scale = min(width / 1920.0, height / 1080.0)
    radius = int(round(190.0 * scale))
    x0 = max(0, int(round(marker[0])) - radius)
    y0 = max(0, int(round(marker[1])) - radius)
    x1 = min(width, int(round(marker[0])) + radius)
    y1 = min(height, int(round(marker[1])) + radius)
    roi = _clahe(image)[y0:y1, x0:x1]
    blurred = cv2.GaussianBlur(roi, (7, 7), 1.5)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.15,
        minDist=max(22.0, 32.0 * scale),
        param1=90,
        param2=27,
        minRadius=max(18, int(round(32 * scale))),
        maxRadius=max(35, int(round(78 * scale))),
    )
    if circles is None:
        return []
    gray = _gray(image)
    result = []
    for local_x, local_y, circle_radius in circles[0]:
        center = np.asarray([local_x + x0, local_y + y0], dtype=np.float64)
        delta = center - marker
        distance = float(np.linalg.norm(delta))
        if not 35.0 * scale <= distance <= 180.0 * scale:
            continue
        edge_score = _circle_edge_score(gray, center, float(circle_radius))
        if edge_score < 10.0:
            continue
        result.append(
            {
                "center_px": center.tolist(),
                "radius_px": float(circle_radius),
                "marker_delta_px": delta.tolist(),
                "edge_score": edge_score,
            }
        )
    return sorted(result, key=lambda item: item["edge_score"], reverse=True)[:12]


def _cluster_marker_deltas(
    candidate_sets: list[list[dict[str, Any]]],
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    entries = [
        (frame_index, candidate)
        for frame_index, candidates in enumerate(candidate_sets)
        for candidate in candidates
    ]
    if not entries:
        raise FineNozzleError("no nozzle-circle candidates detected")
    best = None
    for _seed_frame, seed in entries:
        seed_delta = np.asarray(seed["marker_delta_px"], dtype=np.float64)
        selected = []
        for frame_index, candidates in enumerate(candidate_sets):
            nearby = [
                candidate
                for candidate in candidates
                if float(
                    np.linalg.norm(
                        np.asarray(candidate["marker_delta_px"]) - seed_delta
                    )
                )
                <= 18.0
            ]
            if nearby:
                selected.append(
                    (
                        frame_index,
                        max(nearby, key=lambda item: item["edge_score"]),
                    )
                )
        if not selected:
            continue
        deltas = np.asarray(
            [item["marker_delta_px"] for _index, item in selected],
            dtype=np.float64,
        )
        center = np.median(deltas, axis=0)
        spread = float(np.median(np.linalg.norm(deltas - center, axis=1)))
        score = len(selected) * 100.0 - 8.0 * spread + sum(
            item["edge_score"] for _index, item in selected
        )
        if best is None or score > best[0]:
            best = (score, center, selected)
    if best is None:
        raise FineNozzleError("no consistent nozzle-circle trajectory")
    return best[1], [
        {"frame_index": index, **candidate} for index, candidate in best[2]
    ]


def _crop(
    image: np.ndarray, center: np.ndarray, size: int
) -> tuple[np.ndarray, tuple[int, int]]:
    half = size // 2
    x0 = max(0, min(image.shape[1] - size, int(round(center[0])) - half))
    y0 = max(0, min(image.shape[0] - size, int(round(center[1])) - half))
    return image[y0 : y0 + size, x0 : x0 + size], (x0, y0)


def _match_template_scaled(
    reference: np.ndarray,
    image: np.ndarray,
    predicted_center: np.ndarray,
) -> dict[str, Any]:
    search, (search_x, search_y) = _crop(image, predicted_center, 230)
    search_representations = {
        "gray": _gray(search),
        "clahe": _clahe(search),
    }
    reference_representations = {
        "gray": _gray(reference),
        "clahe": _clahe(reference),
    }
    records = []
    for scale in np.linspace(0.86, 1.16, 16):
        width = max(32, int(round(reference.shape[1] * scale)))
        height = max(32, int(round(reference.shape[0] * scale)))
        if width >= search.shape[1] or height >= search.shape[0]:
            continue
        centers = []
        correlations = []
        for name in ("gray", "clahe"):
            template = cv2.resize(
                reference_representations[name],
                (width, height),
                interpolation=cv2.INTER_CUBIC,
            )
            response = cv2.matchTemplate(
                search_representations[name],
                template,
                cv2.TM_CCOEFF_NORMED,
            )
            _minimum, maximum, _minimum_location, maximum_location = cv2.minMaxLoc(
                response
            )
            centers.append(
                np.asarray(
                    [
                        search_x + maximum_location[0] + width * 0.5,
                        search_y + maximum_location[1] + height * 0.5,
                    ],
                    dtype=np.float64,
                )
            )
            correlations.append(float(maximum))
        spread = float(np.linalg.norm(centers[0] - centers[1]))
        records.append(
            {
                "scale": float(scale),
                "center_px": np.mean(np.asarray(centers), axis=0),
                "minimum_correlation": min(correlations),
                "median_correlation": float(np.median(correlations)),
                "representation_spread_px": spread,
            }
        )
    if not records:
        raise FineNozzleError("no valid template scale")
    return max(
        records,
        key=lambda item: (
            item["minimum_correlation"] - 0.03 * item["representation_spread_px"]
        ),
    )


def _fit_tool(records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [
        record
        for record in records
        if record["minimum_correlation"] >= 0.42
        and record["representation_spread_px"] <= 4.0
    ]
    if len(accepted) < 8:
        raise FineNozzleError(
            f"only {len(accepted)} nozzle registrations passed for {records[0]['tool']}"
        )
    x_ref = float(np.median([record["x_mm"] for record in accepted]))
    z_ref = float(np.median([record["z_mm"] for record in accepted]))
    design = np.asarray(
        [
            [
                1.0,
                record["x_mm"] - x_ref,
                record["z_mm"] - z_ref,
                (record["x_mm"] - x_ref) * (record["z_mm"] - z_ref),
            ]
            for record in accepted
        ],
        dtype=np.float64,
    )
    positions = np.asarray(
        [record["center_px"] for record in accepted], dtype=np.float64
    )
    log_scales = np.log(
        np.asarray([record["template_scale"] for record in accepted])
    )
    position_coefficients = np.linalg.lstsq(design, positions, rcond=None)[0]
    scale_coefficients = np.linalg.lstsq(design, log_scales, rcond=None)[0]
    fitted_positions = design @ position_coefficients
    fitted_scales = design @ scale_coefficients
    position_residuals = positions - fitted_positions
    scale_residuals = log_scales - fitted_scales
    return _finite(
        {
            "x_ref_mm": x_ref,
            "z_ref_mm": z_ref,
            "position_coefficients": position_coefficients,
            "log_scale_coefficients": scale_coefficients,
            "position_fit_rms_px": float(
                np.sqrt(np.mean(np.sum(position_residuals**2, axis=1)))
            ),
            "log_scale_fit_rms": float(np.sqrt(np.mean(scale_residuals**2))),
            "accepted_count": len(accepted),
            "minimum_correlation": min(
                record["minimum_correlation"] for record in accepted
            ),
            "median_correlation": float(
                np.median(
                    [record["minimum_correlation"] for record in accepted]
                )
            ),
            "accepted_sequences": [record["seq"] for record in accepted],
        }
    )


def _evaluate_position(
    model: dict[str, Any], x_mm: float, z_mm: float
) -> np.ndarray:
    dx = x_mm - float(model["x_ref_mm"])
    dz = z_mm - float(model["z_ref_mm"])
    design = np.asarray([1.0, dx, dz, dx * dz])
    return design @ np.asarray(model["position_coefficients"], dtype=np.float64)


def _x_vector(model: dict[str, Any], z_mm: float) -> np.ndarray:
    coefficients = np.asarray(model["position_coefficients"], dtype=np.float64)
    return coefficients[1] + coefficients[3] * (
        z_mm - float(model["z_ref_mm"])
    )


def _solve_zero_command(
    model: dict[str, Any], bed_x_vector_at_print_plane: np.ndarray
) -> float:
    coefficients = np.asarray(model["position_coefficients"], dtype=np.float64)
    x_at_reference = coefficients[1]
    x_z_slope = coefficients[3]
    denominator = float(np.dot(x_z_slope, x_z_slope))
    if denominator < 1e-7:
        raise FineNozzleError("X parallax slope is too small to anchor nozzle Z")
    return float(model["z_ref_mm"]) + float(
        np.dot(bed_x_vector_at_print_plane - x_at_reference, x_z_slope)
        / denominator
    )


def _homography_jacobian(homography: np.ndarray, point: np.ndarray) -> np.ndarray:
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
                (h[1, 1] * denominator - v_numerator * h[2, 1])
                / denominator**2,
            ],
        ]
    )


def analyze(
    frame_paths: list[Path],
    artifact_dir: Path,
    *,
    frames: list[dict[str, Any]],
    reference: dict[str, Any],
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if len(frame_paths) != len(frames):
        raise FineNozzleError("fine-grid frame paths do not match the manifest")

    marker_centers = []
    marker_records = []
    candidate_sets = []
    for index, (path, frame) in enumerate(zip(frame_paths, frames)):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FineNozzleError(f"fine-grid image {index} cannot be decoded")
        expected = np.asarray(frame["expected_marker_pixel_px"], dtype=np.float64)
        marker, marker_record = _select_marker(image, expected, index)
        marker_centers.append(marker)
        marker_records.append(marker_record)
        candidate_sets.append(_nozzle_candidates(image, marker))
    cluster_delta, clustered = _cluster_marker_deltas(candidate_sets)
    clustered_by_frame = {
        int(item["frame_index"]): item for item in clustered
    }

    tool_references: dict[str, tuple[np.ndarray, np.ndarray, int]] = {}
    for tool in ("T0", "T1"):
        candidates = [
            (
                index,
                frame,
                clustered_by_frame.get(index),
            )
            for index, frame in enumerate(frames)
            if frame["tool"] == tool and clustered_by_frame.get(index) is not None
        ]
        if not candidates:
            raise FineNozzleError(f"no nozzle candidate for {tool}")
        index, _frame, selected = min(
            candidates,
            key=lambda item: (
                abs(float(item[1]["z_mm"]) - 3.0)
                + 0.1
                * abs(
                    float(item[1]["x_mm"])
                    - float(reference["bed_tab_x_mm"] + 16.0)
                )
            ),
        )
        center = np.asarray(selected["center_px"], dtype=np.float64)
        reference_image = cv2.imread(
            str(frame_paths[index]), cv2.IMREAD_COLOR
        )
        if reference_image is None:
            raise FineNozzleError(f"reference image {index} cannot be decoded")
        template, _origin = _crop(reference_image, center, 116)
        template = template.copy()
        tool_references[tool] = (template, center, index)

    registrations = []
    for index, (path, frame, marker) in enumerate(
        zip(frame_paths, frames, marker_centers)
    ):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FineNozzleError(f"fine-grid image {index} cannot be decoded")
        selected = clustered_by_frame.get(index)
        predicted = (
            np.asarray(selected["center_px"], dtype=np.float64)
            if selected is not None
            else marker + cluster_delta
        )
        template, _reference_center, reference_index = tool_references[frame["tool"]]
        match = _match_template_scaled(template, image, predicted)
        registrations.append(
            {
                "seq": index,
                "tool": frame["tool"],
                "x_mm": float(frame["x_mm"]),
                "z_mm": float(frame["z_mm"]),
                "center_px": match["center_px"],
                "template_scale": match["scale"],
                "minimum_correlation": match["minimum_correlation"],
                "median_correlation": match["median_correlation"],
                "representation_spread_px": match["representation_spread_px"],
                "marker_center_px": marker,
                "marker_detected": marker_records[index] is not None,
                "reference_seq": reference_index,
            }
        )

    models = {
        tool: _fit_tool(
            [record for record in registrations if record["tool"] == tool]
        )
        for tool in ("T0", "T1")
    }
    average_x_z_slope = np.mean(
        np.asarray(
            [
                np.asarray(models[tool]["position_coefficients"])[3]
                for tool in ("T0", "T1")
            ]
        ),
        axis=0,
    )
    metric_homography = np.asarray(
        reference["patch_to_image_homography"], dtype=np.float64
    )
    corner_patch = np.asarray(reference["corner_patch_xy_mm"], dtype=np.float64)
    patch_jacobian = _homography_jacobian(metric_homography, corner_patch)
    patch_x_unit = np.asarray(reference["patch_x_unit_vector"], dtype=np.float64)
    bed_x_fiducial = patch_jacobian @ patch_x_unit
    fiducial_plane_z = float(reference["fiducial_plane_printer_z_mm"])
    bed_x_print = bed_x_fiducial + (
        0.0 - fiducial_plane_z
    ) * average_x_z_slope
    image_y_vector = np.asarray(
        reference["image_y_axis_vector_px_per_mm"], dtype=np.float64
    )
    basis = np.column_stack([bed_x_print, image_y_vector])
    if abs(float(np.linalg.det(basis))) < 1e-6:
        raise FineNozzleError("bed X/Y image basis is singular")
    corner_pixel = np.asarray(
        reference["corner_pixel_at_fine_capture_px"], dtype=np.float64
    )
    bed_tab_x = float(reference["bed_tab_x_mm"])

    tool_facts = {}
    zero_commands = {}
    for tool in ("T0", "T1"):
        zero_command = _solve_zero_command(models[tool], bed_x_print)
        zero_commands[tool] = zero_command
        nozzle_at_anchor = _evaluate_position(models[tool], bed_tab_x, zero_command)
        in_plane = np.linalg.solve(basis, nozzle_at_anchor - corner_pixel)
        offset_xyz = [
            float(in_plane[0]),
            float(in_plane[1]),
            float(-zero_command),
        ]
        tool_facts[tool] = {
            "offset_xyz_mm_at_commanded_bed_tab": offset_xyz,
            "commanded_z_at_print_plane_mm": zero_command,
            "nozzle_pixel_at_bed_tab_and_print_plane_px": nozzle_at_anchor,
        }

    reasons = []
    warnings = []
    for tool in ("T0", "T1"):
        model = models[tool]
        if model["position_fit_rms_px"] > 4.0:
            reasons.append(
                f"{tool} position fit RMS {model['position_fit_rms_px']:.3f} px"
            )
        if model["accepted_count"] < 14:
            reasons.append(
                f"{tool} has only {model['accepted_count']} accepted registrations"
            )
        if not -12.0 <= zero_commands[tool] <= 12.0:
            reasons.append(
                f"{tool} print-plane command Z {zero_commands[tool]:.3f} mm is implausible"
            )
        if model["minimum_correlation"] < 0.5:
            warnings.append(
                f"{tool} minimum accepted correlation is {model['minimum_correlation']:.3f}"
            )
    slopes = [
        np.asarray(models[tool]["position_coefficients"], dtype=np.float64)[3]
        for tool in ("T0", "T1")
    ]
    slope_norms = [float(np.linalg.norm(item)) for item in slopes]
    if min(slope_norms) <= 1e-8 or float(np.dot(slopes[0], slopes[1])) <= 0:
        reasons.append("T0/T1 X-parallax slopes do not agree in sign")
    elif abs(slope_norms[0] - slope_norms[1]) / max(slope_norms) > 0.25:
        reasons.append("T0/T1 X-parallax slope magnitudes differ by more than 25%")

    panel_width = 480
    panels = []
    accepted_sequences = {
        tool: set(models[tool]["accepted_sequences"]) for tool in ("T0", "T1")
    }
    for path, frame, registration in zip(
        frame_paths, frames, registrations
    ):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FineNozzleError(
                f"fine-grid overlay image {registration['seq']} cannot be decoded"
            )
        panel = image.copy()
        marker = np.asarray(registration["marker_center_px"])
        center = np.asarray(registration["center_px"])
        color = (
            (0, 255, 0)
            if registration["seq"] in accepted_sequences[frame["tool"]]
            else (0, 0, 255)
        )
        cv2.drawMarker(
            panel,
            tuple(np.rint(marker).astype(int)),
            (0, 0, 255),
            cv2.MARKER_CROSS,
            24,
            3,
        )
        cv2.circle(panel, tuple(np.rint(center).astype(int)), 58, color, 3)
        cv2.drawMarker(
            panel,
            tuple(np.rint(center).astype(int)),
            color,
            cv2.MARKER_TILTED_CROSS,
            26,
            3,
        )
        cv2.putText(
            panel,
            (
                f"{frame['tool']} X={frame['x_mm']} Z={frame['z_mm']} "
                f"corr={registration['minimum_correlation']:.3f}"
            ),
            (24, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            color,
            2,
            cv2.LINE_AA,
        )
        scale = panel_width / panel.shape[1]
        panels.append(
            cv2.resize(
                panel,
                (panel_width, int(round(panel.shape[0] * scale))),
                interpolation=cv2.INTER_AREA,
            )
        )
    rows = []
    for start in range(0, len(panels), 5):
        row = panels[start : start + 5]
        while len(row) < 5:
            row.append(np.zeros_like(panels[0]))
        rows.append(cv2.hconcat(row))
    contact = cv2.vconcat(rows)
    contact_path = artifact_dir / "fine_nozzle_registration_grid.jpg"
    cv2.imwrite(str(contact_path), contact)

    model_plot = np.full((760, 1280, 3), 24, np.uint8)
    colors = {"T0": (0, 255, 255), "T1": (255, 128, 255)}
    for row, tool in enumerate(("T0", "T1")):
        y_base = 250 + row * 320
        model = models[tool]
        cv2.putText(
            model_plot,
            (
                f"{tool}: zero command Z={zero_commands[tool]:.4f} mm, "
                f"offset XYZ={tool_facts[tool]['offset_xyz_mm_at_commanded_bed_tab']}"
            ),
            (40, y_base - 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            colors[tool],
            2,
            cv2.LINE_AA,
        )
        for z in np.linspace(1.0, 5.0, 81):
            vector = _x_vector(model, float(z))
            x = int(round(100 + 240 * (z - 1.0)))
            y = int(round(y_base - 60 * (np.linalg.norm(vector) - 8.0)))
            cv2.circle(model_plot, (x, y), 2, colors[tool], -1)
        cv2.line(model_plot, (100, y_base), (1060, y_base), (100, 100, 100), 1)
    plot_path = artifact_dir / "fine_nozzle_projection_model.jpg"
    cv2.imwrite(str(plot_path), model_plot)

    return _finite(
        {
            "accepted": not reasons,
            "reasons": reasons,
            "warnings": warnings,
            "registrations": registrations,
            "models": models,
            "marker_delta_cluster_px": cluster_delta,
            "bed_x_vector_fiducial_plane_px_per_mm": bed_x_fiducial,
            "bed_x_vector_print_plane_px_per_mm": bed_x_print,
            "average_x_vector_z_slope_px_per_mm_per_mm": average_x_z_slope,
            "image_y_axis_vector_px_per_mm": image_y_vector,
            "zero_command_z_mm": zero_commands,
            "tool_facts": tool_facts,
            "artifacts": {
                "fine_nozzle_registration_grid": _artifact(contact_path),
                "fine_nozzle_projection_model": _artifact(plot_path),
            },
        }
    )
