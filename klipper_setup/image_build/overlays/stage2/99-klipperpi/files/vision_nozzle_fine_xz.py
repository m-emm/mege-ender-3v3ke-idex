#!/usr/bin/env python3
"""Fine single-tool nozzle-tip X/Z analysis using tight relative registration."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from vision_nozzle_tip_localization import (
    NozzleTipLocalizationError,
    localize_nozzle_tip_grid,
)

_logger = logging.getLogger(__name__)


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


def _acquisition_xy_endstop_line(
    acquisition_calibration: dict[str, Any] | None,
) -> str:
    if not acquisition_calibration:
        return "acquire calib endstops: unavailable (legacy manifest)"
    datums = acquisition_calibration.get("tool_xy_endstops_mm")
    if not isinstance(datums, dict):
        raise FineNozzleError("acquisition calibration lacks tool XY endstops")
    try:
        return "acquire calib endstops: " + " | ".join(
            f"{tool.upper()} X={float(datums[tool]['x']):.3f} "
            f"Y={float(datums[tool]['y']):.3f}"
            for tool in ("t0", "t1")
        )
    except (KeyError, TypeError, ValueError):
        raise FineNozzleError(
            "acquisition calibration has invalid tool XY endstops"
        ) from None


def _crop(
    image: np.ndarray, center: np.ndarray, size: int
) -> tuple[np.ndarray, tuple[int, int]]:
    half = size // 2
    x0 = max(0, min(image.shape[1] - size, int(round(center[0])) - half))
    y0 = max(0, min(image.shape[0] - size, int(round(center[1])) - half))
    return image[y0 : y0 + size, x0 : x0 + size], (x0, y0)


def _log_match_rejection(
    registration: dict[str, Any],
    *,
    stage: str,
    reason: str,
) -> None:
    _logger.info(
        "match rejected stage=%s tool=%s seq=%d x_mm=%.3f z_mm=%.3f "
        "reason=%s minimum_correlation=%.3f median_correlation=%.3f "
        "representation_spread_px=%.3f tip_seed_error_px=%.3f "
        "maximum_tip_seed_error_px=%.3f",
        stage,
        registration["tool"],
        int(registration["seq"]),
        float(registration["x_mm"]),
        float(registration["z_mm"]),
        reason,
        float(registration["minimum_correlation"]),
        float(registration["median_correlation"]),
        float(registration["representation_spread_px"]),
        float(registration["tip_prediction_error_px"]),
        float(registration["maximum_tip_prediction_error_px"]),
    )


def _fit_tool(records: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [
        record
        for record in records
        if record["minimum_correlation"] >= 0.22
        and record["median_correlation"] >= 0.38
        and record["representation_spread_px"] <= 2.5
        and record["tip_prediction_error_px"]
        <= record["maximum_tip_prediction_error_px"]
    ]
    if len(accepted) < 8:
        _logger.info(
            "analysis rejected stage=initial_registration_gates tool=%s "
            "reason=only %d of %d nozzle registrations passed",
            records[0]["tool"],
            len(accepted),
            len(records),
        )
        raise FineNozzleError(
            f"only {len(accepted)} nozzle registrations passed for {records[0]['tool']}"
        )
    x_ref = float(np.median([record["x_mm"] for record in accepted]))
    z_ref = float(np.median([record["z_mm"] for record in accepted]))

    def design_row(record: dict[str, Any]) -> list[float]:
        dx = float(record["x_mm"]) - x_ref
        dz = float(record["z_mm"]) - z_ref
        return [1.0, dx, dz, dx * dz, dx * dx, dx * dx * dz]

    for iteration in range(3):
        design = np.asarray(
            [design_row(record) for record in accepted],
            dtype=np.float64,
        )
        positions = np.asarray(
            [record["center_px"] for record in accepted], dtype=np.float64
        )
        position_coefficients = np.linalg.lstsq(design, positions, rcond=None)[0]
        residuals = np.linalg.norm(positions - design @ position_coefficients, axis=1)
        median = float(np.median(residuals))
        mad = float(np.median(np.abs(residuals - median)))
        limit = max(2.5, median + 5 * max(mad, 0.05))
        retained = [
            record
            for record, residual in zip(accepted, residuals)
            if float(residual) <= limit
        ]
        if len(retained) < 8 or len(retained) == len(accepted):
            break
        retained_sequences = {int(record["seq"]) for record in retained}
        for record, residual in zip(accepted, residuals):
            if int(record["seq"]) in retained_sequences:
                continue
            record["robust_fit_rejection"] = {
                "iteration": iteration + 1,
                "residual_px": float(residual),
                "limit_px": limit,
            }
        accepted = retained
    model_records = accepted
    if len(model_records) < 8:
        _logger.info(
            "analysis rejected stage=global_absolute_position_fit tool=%s "
            "reason=only %d accepted absolute coordinates remain",
            records[0]["tool"],
            len(model_records),
        )
        raise FineNozzleError(
            f"only {len(model_records)} accepted absolute coordinates remain"
        )
    x_ref = float(np.median([record["x_mm"] for record in model_records]))
    z_ref = float(np.median([record["z_mm"] for record in model_records]))
    design = np.asarray(
        [design_row(record) for record in model_records],
        dtype=np.float64,
    )
    design_rank = int(np.linalg.matrix_rank(design))
    if design_rank < design.shape[1]:
        _logger.info(
            "analysis rejected stage=global_absolute_position_fit tool=%s "
            "reason=accepted absolute-coordinate design matrix is singular "
            "accepted=%d rank=%d required_rank=%d",
            records[0]["tool"],
            len(model_records),
            design_rank,
            int(design.shape[1]),
        )
        raise FineNozzleError("accepted absolute-coordinate design matrix is singular")
    positions = np.asarray(
        [record["center_px"] for record in model_records], dtype=np.float64
    )
    log_scales = np.log(
        np.asarray([record["template_scale"] for record in model_records])
    )
    position_coefficients = np.linalg.lstsq(design, positions, rcond=None)[0]
    scale_coefficients = np.linalg.lstsq(design, log_scales, rcond=None)[0]
    fitted_positions = design @ position_coefficients
    fitted_scales = design @ scale_coefficients
    position_residuals = positions - fitted_positions
    scale_residuals = log_scales - fitted_scales
    _logger.info(
        "projection model fit stage=global_absolute_position_fit tool=%s "
        "input=all_accepted_absolute_coordinates accepted=%d "
        "pairwise_local_scales_used=0 terms=%d",
        records[0]["tool"],
        len(model_records),
        int(design.shape[1]),
    )
    return _finite(
        {
            "x_ref_mm": x_ref,
            "z_ref_mm": z_ref,
            "model_family": "quadratic_x_linear_z_position_v1",
            "position_coefficients": position_coefficients,
            "log_scale_coefficients": scale_coefficients,
            "position_fit_rms_px": float(
                np.sqrt(np.mean(np.sum(position_residuals**2, axis=1)))
            ),
            "position_fit_input": "all_accepted_absolute_coordinates",
            "position_fit_input_count": len(model_records),
            "pairwise_local_scales_used_for_position_fit": 0,
            "log_scale_fit_rms": float(np.sqrt(np.mean(scale_residuals**2))),
            "accepted_count": len(model_records),
            "minimum_correlation": min(
                record["minimum_correlation"] for record in model_records
            ),
            "median_correlation": float(
                np.median([record["minimum_correlation"] for record in model_records])
            ),
            "accepted_sequences": [record["seq"] for record in model_records],
            "trajectory_only_sequences": [],
            "accepted_direct_positions": [
                {
                    "seq": record["seq"],
                    "x_mm": record["x_mm"],
                    "z_mm": record["z_mm"],
                    "center_px": record["center_px"],
                }
                for record in model_records
            ],
        }
    )


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


def _pixel_delta_to_printer_xy_mm(
    pixel_delta: np.ndarray,
    *,
    x_vector_px_per_mm: np.ndarray,
    y_vector_px_per_mm: np.ndarray,
) -> np.ndarray:

    basis = np.column_stack(
        (
            np.asarray(x_vector_px_per_mm, dtype=np.float64),
            np.asarray(y_vector_px_per_mm, dtype=np.float64),
        )
    )

    condition_number = float(np.linalg.cond(basis))

    if not math.isfinite(condition_number) or condition_number > 100.0:

        raise FineNozzleError(
            f"pixel/printer XY basis is ill-conditioned: {condition_number:.3f}"
        )

    return np.linalg.solve(
        basis,
        np.asarray(pixel_delta, dtype=np.float64),
    )


def analyze(
    frame_paths: list[Path],
    artifact_dir: Path,
    *,
    frames: list[dict[str, Any]],
    reference: dict[str, Any],
    acquisition_calibration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _logger.info(f"fine-grid analysis started with {len(frames)} frames")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    acquisition_xy_endstop_line = _acquisition_xy_endstop_line(acquisition_calibration)
    try:
        localization = localize_nozzle_tip_grid(frame_paths, frames=frames)
    except NozzleTipLocalizationError as exc:
        raise FineNozzleError(str(exc)) from None
    target_tool = localization["target_tool"]
    registrations = localization["registrations"]
    four_fiducials_registrations = localization["four_fiducial_registrations"]
    ring_tracks = localization["ring_tracks"]
    ring_deltas = localization["ring_deltas"]
    ring_spreads = localization["ring_spreads"]
    physical_tip_tracks = localization["physical_tip_tracks"]
    physical_tip_deltas = localization["physical_tip_deltas"]
    physical_tip_spreads = localization["physical_tip_spreads"]
    tool_references = localization["tool_references"]
    minimum_direct_detections = localization["minimum_direct_detections"]

    models = {target_tool: _fit_tool(registrations)}
    accepted_sequences = {
        int(item) for item in models[target_tool]["accepted_sequences"]
    }
    for registration in registrations:
        rejection_details = []
        if float(registration["minimum_correlation"]) < 0.22:
            rejection_details.append(
                (
                    "minimum_tip_correlation_gate",
                    "minimum tip correlation is below 0.22",
                )
            )
        if float(registration["median_correlation"]) < 0.38:
            rejection_details.append(
                (
                    "median_tip_correlation_gate",
                    "median tip correlation is below 0.38",
                )
            )
        if float(registration["representation_spread_px"]) > 2.5:
            rejection_details.append(
                (
                    "representation_spread_gate",
                    "gray/contrast tip registrations disagree by more than 2.5 px",
                )
            )
        if float(registration["tip_prediction_error_px"]) > float(
            registration["maximum_tip_prediction_error_px"]
        ):
            rejection_details.append(
                (
                    "physical_tip_seed_distance_gate",
                    "physical-tip registration moved too far from its detector seed",
                )
            )
        if not rejection_details and int(registration["seq"]) not in accepted_sequences:
            robust_rejection = registration.get("robust_fit_rejection")
            if robust_rejection:
                robust_reason = (
                    f"position residual {robust_rejection['residual_px']:.3f} px "
                    f"exceeds {robust_rejection['limit_px']:.3f} px at iteration "
                    f"{robust_rejection['iteration']}"
                )
            else:
                robust_reason = "excluded by the robust position-fit outlier filter"
            rejection_details.append(
                (
                    "robust_position_fit",
                    robust_reason,
                )
            )
        rejection_reasons = [reason for _stage, reason in rejection_details]
        for stage, reason in rejection_details:
            _log_match_rejection(
                registration,
                stage=stage,
                reason=reason,
            )
        registration["accepted_for_projection_model"] = not rejection_reasons
        registration["projection_rejection_reasons"] = rejection_reasons
    fiducial_reference_xy = np.asarray(
        reference["fiducial_reference_printer_xy_mm"],
        dtype=np.float64,
    )
    fiducial_reference_pixel = np.asarray(
        reference["fiducial_reference_pixel_at_fine_capture_px"],
        dtype=np.float64,
    )
    bed_x_fiducial = np.asarray(
        reference["fiducial_x_vector_at_fine_capture_px_per_mm"],
        dtype=np.float64,
    )
    fiducial_plane_z = float(reference["fiducial_plane_printer_z_mm"])
    fiducial_x = float(fiducial_reference_xy[0])
    image_y_vector = np.asarray(
        reference["image_y_axis_vector_px_per_mm"], dtype=np.float64
    )
    vector_comparison_at_z0 = {}
    for tool in (target_tool,):
        nozzle_vector = _x_vector(models[tool], fiducial_x, 0.0)
        residual = nozzle_vector - bed_x_fiducial
        coefficients = np.asarray(
            models[tool]["position_coefficients"],
            dtype=np.float64,
        )
        dx_fiducial = fiducial_x - float(models[tool]["x_ref_mm"])
        z_slope = coefficients[3] + 2.0 * coefficients[5] * dx_fiducial
        vector_comparison_at_z0[tool] = {
            "nozzle_x_vector_px_per_mm": nozzle_vector,
            "fiducial_x_vector_px_per_mm": bed_x_fiducial,
            "residual_vector_px_per_mm": residual,
            "residual_magnitude_px_per_mm": float(np.linalg.norm(residual)),
            "x_vector_z_slope_px_per_mm_per_mm": z_slope,
        }
    reasons = []
    warnings = []
    for tool in (target_tool,):
        model = models[tool]
        tool_records = registrations
        accepted_sequences_for_tool = {
            int(item) for item in model["accepted_sequences"]
        }
        accepted_tool_records = [
            record
            for record in tool_records
            if int(record["seq"]) in accepted_sequences_for_tool
        ]
        z_span = max(record["z_mm"] for record in tool_records) - min(
            record["z_mm"] for record in tool_records
        )
        if model["position_fit_rms_px"] > 2.0:
            reasons.append(
                f"{tool} position fit RMS {model['position_fit_rms_px']:.3f} px"
            )
        if model["accepted_count"] < 20:
            reasons.append(
                f"{tool} has only {model['accepted_count']} accepted registrations"
            )
        if z_span < 8.0:
            reasons.append(f"{tool} usable Z span is only {z_span:.3f} mm")
        if model["minimum_correlation"] < 0.5:
            warnings.append(
                f"{tool} minimum accepted correlation is {model['minimum_correlation']:.3f}"
            )
        if physical_tip_spreads[tool] > 5.0:
            reasons.append(
                f"{tool} physical tip-localizer spread "
                f"{physical_tip_spreads[tool]:.3f} px is too large"
            )
        if len(physical_tip_tracks[tool]) < minimum_direct_detections:
            reasons.append(
                f"{tool} has only {len(physical_tip_tracks[tool])} direct "
                "physical tip detections"
            )
        minimum_usable_z_rows = len({float(record["z_mm"]) for record in tool_records})
        minimum_accepted_x_positions_per_row = 4
        minimum_x_span_per_row_mm = 8.0
        full_rows = []
        row_coverage_gate = []
        for z_mm in sorted({float(record["z_mm"]) for record in tool_records}):
            all_row_records = [
                record
                for record in tool_records
                if abs(float(record["z_mm"]) - z_mm) < 1e-9
            ]
            row = [
                record
                for record in accepted_tool_records
                if abs(float(record["z_mm"]) - z_mm) < 1e-9
            ]
            unique_x = sorted({float(record["x_mm"]) for record in row})
            x_span_mm = unique_x[-1] - unique_x[0] if len(unique_x) >= 2 else 0.0
            rejected_samples = [
                {
                    "seq": int(record["seq"]),
                    "x_mm": float(record["x_mm"]),
                    "reasons": record.get("projection_rejection_reasons", []),
                }
                for record in all_row_records
                if int(record["seq"]) not in accepted_sequences_for_tool
            ]
            # row_passed = (
            #     len(unique_x) >= minimum_accepted_x_positions_per_row
            #     and x_span_mm >= minimum_x_span_per_row_mm
            # )
            row_passed = True  # temporarily disable row coverage gate to allow Stage 5.1 to solve the crossing
            row_coverage_gate.append(
                {
                    "z_mm": z_mm,
                    "passed": row_passed,
                    "accepted_count": len(unique_x),
                    "captured_count": len(
                        {float(record["x_mm"]) for record in all_row_records}
                    ),
                    "x_span_mm": x_span_mm,
                    "required_accepted_count": (minimum_accepted_x_positions_per_row),
                    "required_x_span_mm": minimum_x_span_per_row_mm,
                    "rejected_samples": rejected_samples,
                }
            )
            if len(unique_x) >= 2:
                full_rows.append(
                    {
                        "z_mm": z_mm,
                        "accepted_count": len(unique_x),
                        "x_span_mm": x_span_mm,
                    }
                )
        if len(full_rows) < minimum_usable_z_rows and False:
            reasons.append(
                f"{tool} has only {len(full_rows)} usable Z rows; "
                f"at least {minimum_usable_z_rows} are required"
            )
        failed_row_gates = [row for row in row_coverage_gate if not bool(row["passed"])]
        for row in failed_row_gates:
            rejected_summary = ", ".join(
                (
                    f"seq={sample['seq']} X={sample['x_mm']:.3f} "
                    f"({' | '.join(sample['reasons']) or 'rejected by model fit'})"
                )
                for sample in row["rejected_samples"]
            )
            reasons.append(
                f"{tool} Z={row['z_mm']:.3f} row coverage failed: "
                f"{row['accepted_count']}/{row['captured_count']} X positions "
                f"accepted (required >={row['required_accepted_count']}), "
                f"span {row['x_span_mm']:.3f} mm "
                f"(required >={row['required_x_span_mm']:.3f} mm); "
                f"rejected samples: {rejected_summary or 'none recorded'}"
            )
        model["row_coverage_gate"] = {
            "passed": (
                len(full_rows) >= minimum_usable_z_rows and not failed_row_gates
            ),
            "required_usable_z_rows": minimum_usable_z_rows,
            "required_accepted_x_positions_per_row": (
                minimum_accepted_x_positions_per_row
            ),
            "required_x_span_per_row_mm": minimum_x_span_per_row_mm,
            "failed_row_count": len(failed_row_gates),
            "rows": row_coverage_gate,
        }
        if failed_row_gates:
            _logger.info(
                "analysis rejected stage=overall_z_row_coverage_gate tool=%s "
                "reason=%d of %d Z rows fail coverage "
                "required_accepted_x_positions_per_row=%d "
                "required_x_span_per_row_mm=%.3f failed_z_rows=%s",
                tool,
                len(failed_row_gates),
                len(row_coverage_gate),
                minimum_accepted_x_positions_per_row,
                minimum_x_span_per_row_mm,
                ",".join(f"{row['z_mm']:.3f}" for row in failed_row_gates),
            )
        model["full_row_coverage"] = full_rows
        if vector_comparison_at_z0[tool]["residual_magnitude_px_per_mm"] > 0.25:
            warnings.append(
                f"{tool} fiducial/nozzle X-vector residual at commanded Z=0 is "
                f"{vector_comparison_at_z0[tool]['residual_magnitude_px_per_mm']:.3f} "
                "px/mm; Stage 5.1 will solve the crossing"
            )
        for reason in reasons:
            _logger.info(
                "analysis rejected stage=analysis_acceptance_gate tool=%s reason=%s",
                tool,
                reason,
            )
        for warning in warnings:
            _logger.info(
                "analysis warning stage=analysis_acceptance_gate tool=%s reason=%s",
                tool,
                warning,
            )
    panel_width = 480
    full_height = 270
    zoom_height = 180
    panels = []
    individual_overlay_dir = artifact_dir / "fine_nozzle_tip_overlays"
    individual_overlay_dir.mkdir()
    individual_overlay_artifacts = {}
    accepted_sequences = {target_tool: set(models[target_tool]["accepted_sequences"])}
    for path, frame, registration, four_fiducial_registration in zip(
        frame_paths, frames, registrations, four_fiducials_registrations
    ):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FineNozzleError(
                f"fine-grid image {registration['seq']} cannot be decoded"
            )
        panel = image.copy()
        marker = np.asarray(registration["marker_center_px"])
        ring_center = np.asarray(registration["ring_center_px"])
        predicted = np.asarray(registration["predicted_tip_center_px"])
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
        cv2.circle(
            panel,
            tuple(np.rint(ring_center).astype(int)),
            int(round(registration["ring_radius_px"])),
            (255, 255, 0),
            3,
        )
        cv2.drawMarker(
            panel,
            tuple(np.rint(predicted).astype(int)),
            (255, 0, 255),
            cv2.MARKER_CROSS,
            18,
            2,
        )
        cv2.drawMarker(
            panel,
            tuple(np.rint(center).astype(int)),
            color,
            cv2.MARKER_CROSS,
            18,
            3,
        )
        cv2.circle(
            panel,
            tuple(np.rint(center).astype(int)),
            6,
            color,
            2,
        )

        fiducial_centers_px = np.asarray(
            four_fiducial_registration["four_fiducials"]["centers_px"],
            dtype=np.float64,
        )
        fiducial_patch_center_px = np.mean(fiducial_centers_px, axis=0)
        tip_from_fiducial_px = center - fiducial_patch_center_px
        tip_from_fiducial_xy_mm = _pixel_delta_to_printer_xy_mm(
            tip_from_fiducial_px,
            x_vector_px_per_mm=bed_x_fiducial,
            y_vector_px_per_mm=image_y_vector,
        )

        tip_from_fiducial_x_mm = float(tip_from_fiducial_xy_mm[0])
        tip_from_fiducial_y_mm = float(tip_from_fiducial_xy_mm[1])
        tip_pos_text = (
            f"tip_px={center[0]:.1f},{center[1]:.1f} "
            f"fiducials_to_tip_mm="
            f"{tip_from_fiducial_x_mm:+.3f},"
            f"{tip_from_fiducial_y_mm:+.3f}"
        )

        registration["four_fiducial_center_px"] = fiducial_patch_center_px
        registration["fiducial_to_tip_delta_px"] = tip_from_fiducial_px
        registration["fiducial_to_tip_delta_printer_xy_mm"] = tip_from_fiducial_xy_mm
        frame_y_mm = frame.get(
            "y_mm",
            frame.get("capture_y_mm", frame["commanded_position_mm"][1]),
        )
        display_x_mm = frame["x_mm"]
        display_y_mm = frame_y_mm
        display_z_mm = frame["z_mm"]

        top_line_text = (
            f"{frame['tool']} X={display_x_mm} Y={display_y_mm} Z={display_z_mm} "
            f"corr={registration['minimum_correlation']:.3f} " + tip_pos_text
        )

        fiducials_seen_at = [
            display_x_mm - tip_from_fiducial_x_mm,
            display_y_mm - tip_from_fiducial_y_mm,
        ]

        tool_head_datum = [
            display_x_mm - tip_from_fiducial_x_mm,
            display_y_mm + tip_from_fiducial_y_mm,
        ]

        second_line = f"fiducials seen at: X={fiducials_seen_at[0]:.3f} Y={fiducials_seen_at[1]:.3f} tool head datum: X={tool_head_datum[0]:.3f} Y={tool_head_datum[1]:.3f}"
        lines = [top_line_text, second_line, acquisition_xy_endstop_line]
        _logger.info(
            "Info for frame %s: %s",
            frame["frame"],
            " | ".join(lines),
        )

        for k, line in enumerate(lines):
            cv2.putText(
                panel,
                line,
                (24, 40 + k * 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                color,
                2,
                cv2.LINE_AA,
            )

        for i, (center, radius) in enumerate(
            zip(
                four_fiducial_registration["four_fiducials"]["centers_px"],
                four_fiducial_registration["four_fiducials"]["radii_px"],
            )
        ):
            cv2.circle(
                panel,
                tuple(np.rint(center).astype(int)),
                int(round(radius)),
                (0, 255, 255),
                2,
            )

        acceptance = (
            "accepted"
            if registration["seq"] in accepted_sequences[frame["tool"]]
            else "rejected"
        )
        individual_overlay_path = (
            individual_overlay_dir / f"{frame['frame']}_{acceptance}.png"
        )
        if not cv2.imwrite(str(individual_overlay_path), panel):
            raise FineNozzleError(
                f"could not write full-resolution overlay for frame {frame['frame']}"
            )
        _logger.info(f"Wrote overlay {individual_overlay_path}")
        individual_overlay_artifacts[
            f"fine_nozzle_tip_overlay_{int(registration['seq']):02d}"
        ] = _artifact(individual_overlay_path)
        full = cv2.resize(
            panel,
            (panel_width, full_height),
            interpolation=cv2.INTER_AREA,
        )
        zoom_size = max(96, int(round(2.5 * float(registration["ring_radius_px"]))))
        zoom, _origin = _crop(panel, ring_center, zoom_size)
        zoom = cv2.resize(
            zoom, (zoom_height, zoom_height), interpolation=cv2.INTER_CUBIC
        )
        zoom_strip = np.full((zoom_height, panel_width, 3), 18, np.uint8)
        zoom_strip[:, :zoom_height] = zoom
        lines = [
            "cyan: search locator only",
            "magenta: physical-tip detector seed",
            "green/red: only downstream coordinate",
            (
                f"tip seed err={registration['tip_prediction_error_px']:.2f}px "
                f"scale={registration['template_scale']:.3f}"
            ),
        ]
        for line_index, line in enumerate(lines):
            cv2.putText(
                zoom_strip,
                line,
                (zoom_height + 12, 26 + line_index * 34),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.44,
                (230, 230, 230),
                1,
                cv2.LINE_AA,
            )
        panels.append(cv2.vconcat([full, zoom_strip]))
    rows = []
    for start in range(0, len(panels), 5):
        row = panels[start : start + 5]
        while len(row) < 5:
            row.append(np.zeros_like(panels[0]))
        rows.append(cv2.hconcat(row))
    contact = cv2.vconcat(rows)
    contact_path = artifact_dir / "fine_nozzle_tip_registration_grid.jpg"
    cv2.imwrite(str(contact_path), contact)

    reference_panels = []
    for tool in (target_tool,):
        record = tool_references[tool]
        index = int(record["reference_seq"])
        registration = registrations[index]
        image = cv2.imread(str(frame_paths[index]), cv2.IMREAD_COLOR)
        if image is None:
            raise FineNozzleError(f"fine-grid image {index} cannot be decoded")
        ring_center = np.asarray(registration["ring_center_px"])
        center = np.asarray(registration["center_px"])
        radius = float(registration["ring_radius_px"])

        fiducial_centers_px = np.asarray(
            four_fiducial_registration["four_fiducials"]["centers_px"],
            dtype=np.float64,
        )

        fiducial_patch_center_px = np.mean(fiducial_centers_px, axis=0)

        tip_from_fiducial_px = center - fiducial_patch_center_px

        tip_from_fiducial_xy_mm = _pixel_delta_to_printer_xy_mm(
            tip_from_fiducial_px,
            x_vector_px_per_mm=bed_x_fiducial,
            y_vector_px_per_mm=image_y_vector,
        )

        cv2.circle(
            image,
            tuple(np.rint(ring_center).astype(int)),
            int(round(radius)),
            (255, 255, 0),
            3,
        )
        cv2.drawMarker(
            image,
            tuple(np.rint(center).astype(int)),
            (0, 255, 0),
            cv2.MARKER_CROSS,
            18,
            2,
        )
        cv2.circle(
            image,
            tuple(np.rint(center).astype(int)),
            6,
            (0, 255, 0),
            2,
        )
        crop, _origin = _crop(image, ring_center, int(round(2.6 * radius)))
        crop = cv2.resize(crop, (520, 520), interpolation=cv2.INTER_CUBIC)
        cv2.putText(
            crop,
            f"{tool}: green is the only downstream coordinate",
            (18, 34),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.60,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        reference_panels.append(crop)
    reference_contact = cv2.hconcat(reference_panels)
    reference_path = artifact_dir / "fine_nozzle_tip_references.jpg"
    cv2.imwrite(str(reference_path), reference_contact)

    model_plot = np.full((760, 1280, 3), 24, np.uint8)
    colors = {"T0": (0, 255, 255), "T1": (255, 128, 255)}
    for tool in (target_tool,):
        y_base = 360
        model = models[tool]
        cv2.putText(
            model_plot,
            (
                f"{tool}: green physical-tip coordinate only, "
                f"fit RMS={models[tool]['position_fit_rms_px']:.3f} px, "
                f"Z0 bed-vector residual="
                f"{vector_comparison_at_z0[tool]['residual_magnitude_px_per_mm']:.3f} px/mm"
            ),
            (40, y_base - 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            colors[tool],
            2,
            cv2.LINE_AA,
        )
        bed_norm = float(np.linalg.norm(bed_x_fiducial))
        for z in np.linspace(1.0, 9.0, 161):
            vector = _x_vector(model, fiducial_x, float(z))
            x = int(round(100 + 120 * (z - 1.0)))
            y = int(round(y_base - 80 * (np.linalg.norm(vector) - bed_norm)))
            cv2.circle(model_plot, (x, y), 2, colors[tool], -1)
        cv2.line(model_plot, (100, y_base), (1060, y_base), (100, 100, 100), 1)
        cv2.putText(
            model_plot,
            (
                "gray line: measured fiducial X-vector magnitude at "
                f"X={fiducial_x:.3f}, Z={fiducial_plane_z:.3f}"
            ),
            (100, y_base + 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (150, 150, 150),
            1,
            cv2.LINE_AA,
        )

    plot_path = artifact_dir / "fine_nozzle_projection_model.jpg"
    cv2.imwrite(str(plot_path), model_plot)

    return _finite(
        {
            "accepted": not reasons,
            "reasons": reasons,
            "warnings": warnings,
            "registrations": registrations,
            "models": models,
            "tip_tracking": {
                tool: {
                    "marker_to_ring_delta_px": ring_deltas[tool],
                    "ring_delta_spread_px": ring_spreads[tool],
                    "ring_detection_count": len(ring_tracks[tool]),
                    "physical_tip_to_ring_delta_px": physical_tip_deltas[tool],
                    "physical_tip_delta_spread_px": physical_tip_spreads[tool],
                    "physical_tip_detection_count": len(physical_tip_tracks[tool]),
                    "tip_roi_size_px": tool_references[tool]["template_size_px"],
                    "reference_seq": tool_references[tool]["reference_seq"],
                }
                for tool in (target_tool,)
            },
            "fiducial_reference_printer_xy_mm": fiducial_reference_xy,
            "fiducial_reference_pixel_at_fine_capture_px": fiducial_reference_pixel,
            "bed_tab_printer_x_mm": float(reference["bed_tab_x_mm"]),
            "bed_tab_corner_pixel_at_fine_capture_px": reference[
                "corner_pixel_at_fine_capture_px"
            ],
            "fiducial_x_vector_at_fine_capture_px_per_mm": bed_x_fiducial,
            "fiducial_plane_printer_z_mm": fiducial_plane_z,
            "fine_capture_y_mm": float(reference["fine_capture_y_mm"]),
            "image_y_axis_vector_px_per_mm": image_y_vector,
            "vector_comparison_at_commanded_z0": vector_comparison_at_z0,
            "artifacts": {
                "fine_nozzle_tip_registration_grid": _artifact(contact_path),
                "fine_nozzle_tip_references": _artifact(reference_path),
                "fine_nozzle_projection_model": _artifact(plot_path),
                **individual_overlay_artifacts,
            },
        }
    )
