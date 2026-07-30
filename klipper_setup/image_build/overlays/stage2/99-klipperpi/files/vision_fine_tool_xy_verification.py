#!/usr/bin/env python3
"""Independent six-frame X/Y verification for an active Stage 5.1 calibration."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from vision_bed_fiducial import detect_four_fiducials
from vision_nozzle_fine_xz import _crop, _match_template_scaled


class FineToolVerificationError(RuntimeError):
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
    return np.asarray([1.0, dx, dz, dx * dz]) @ np.asarray(
        model["position_coefficients"], dtype=np.float64
    )


def _x_vector(model: dict[str, Any], z_mm: float) -> np.ndarray:
    coefficients = np.asarray(model["position_coefficients"], dtype=np.float64)
    return coefficients[1] + coefficients[3] * (
        float(z_mm) - float(model["z_ref_mm"])
    )


def analyze(
    frame_paths: list[Path],
    artifact_dir: Path,
    *,
    frames: list[dict[str, Any]],
    reference: dict[str, Any],
) -> dict[str, Any]:
    if len(frame_paths) != 6 or len(frames) != 6:
        raise FineToolVerificationError(
            "fine X/Y verification requires exactly six frames"
        )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    image_y = np.asarray(
        reference["image_y_axis_vector_px_per_mm"], dtype=np.float64
    )
    records = []
    images = []
    for path, frame in zip(frame_paths, frames):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FineToolVerificationError(f"cannot decode {path}")
        images.append(image)
        tool = frame["tool"]
        tool_reference = reference["tools"][tool]
        source_path = Path(tool_reference["source_frame_path"])
        source_hash = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
        if source_hash != tool_reference["source_frame_sha256"]:
            raise FineToolVerificationError(
                f"{tool} source template frame hash mismatch"
            )
        source = cv2.imread(
            str(source_path), cv2.IMREAD_COLOR
        )
        if source is None:
            raise FineToolVerificationError(
                f"cannot decode {tool} source template frame"
            )
        template, _origin = _crop(
            source,
            np.asarray(tool_reference["source_center_px"], dtype=np.float64),
            int(tool_reference["template_size_px"]),
        )
        residual = np.asarray(
            tool_reference["coordinate_residual_xyz_mm"], dtype=np.float64
        )
        commanded = np.asarray(frame["commanded_position_mm"], dtype=np.float64)
        old_equivalent_x = commanded[0] - residual[0]
        old_equivalent_z = commanded[2] - residual[2]
        predicted_tip = _position(
            tool_reference["projection_model"],
            old_equivalent_x,
            old_equivalent_z,
        )
        match = _match_template_scaled(
            template,
            image,
            predicted_tip,
            search_size=int(reference["tip_search_size_px"]),
        )
        observed_tip = np.asarray(match["center_px"], dtype=np.float64)
        x_vector = _x_vector(
            tool_reference["projection_model"], old_equivalent_z
        )
        tip_delta = observed_tip - predicted_tip
        x_residual = float(np.dot(tip_delta, x_vector) / np.dot(x_vector, x_vector))

        old_equivalent_y = commanded[1] - residual[1]
        expected_markers = (
            np.asarray(reference["reference_marker_centers_px"], dtype=np.float64)
            + image_y
            * (
                old_equivalent_y
                - float(reference["metric_reference_capture_y_mm"])
            )
        )
        detection = detect_four_fiducials(
            image, reference_centers_px=expected_markers
        )
        observed_markers = np.asarray(detection["centers_px"], dtype=np.float64)
        marker_delta = np.mean(observed_markers - expected_markers, axis=0)
        y_residual = float(np.dot(marker_delta, image_y) / np.dot(image_y, image_y))
        records.append(
            {
                "seq": int(frame["seq"]),
                "tool": tool,
                "pose": frame["pose"],
                "commanded_position_mm": commanded,
                "predicted_tip_center_px": predicted_tip,
                "observed_tip_center_px": observed_tip,
                "tip_delta_px": tip_delta,
                "x_residual_mm": x_residual,
                "expected_marker_centers_px": expected_markers,
                "observed_marker_centers_px": observed_markers,
                "marker_delta_px": marker_delta,
                "y_residual_mm": y_residual,
                "minimum_correlation": match["minimum_correlation"],
                "median_correlation": match["median_correlation"],
                "representation_spread_px": match[
                    "representation_spread_px"
                ],
            }
        )

    reasons = []
    warnings = []
    tool_results = {}
    for tool in ("T0", "T1"):
        tool_records = [record for record in records if record["tool"] == tool]
        center = next(record for record in tool_records if record["pose"] == "center")
        x_dither = next(
            record for record in tool_records if record["pose"] == "x_dither"
        )
        y_dither = next(
            record for record in tool_records if record["pose"] == "y_dither"
        )
        x_residuals = [float(record["x_residual_mm"]) for record in tool_records]
        y_residuals = [float(record["y_residual_mm"]) for record in tool_records]
        observed_x_delta = (
            np.asarray(x_dither["observed_tip_center_px"])
            - np.asarray(center["observed_tip_center_px"])
        )
        expected_x_delta = (
            np.asarray(x_dither["predicted_tip_center_px"])
            - np.asarray(center["predicted_tip_center_px"])
        )
        observed_y_delta = (
            np.mean(np.asarray(y_dither["observed_marker_centers_px"]), axis=0)
            - np.mean(np.asarray(center["observed_marker_centers_px"]), axis=0)
        )
        expected_y_delta = image_y * float(reference["y_dither_mm"])
        tool_results[tool] = {
            "absolute_x_residual_mm": float(np.median(x_residuals)),
            "absolute_y_residual_mm": float(np.median(y_residuals)),
            "x_dither_observed_px": observed_x_delta,
            "x_dither_expected_px": expected_x_delta,
            "x_dither_vector_error_px": float(
                np.linalg.norm(observed_x_delta - expected_x_delta)
            ),
            "y_dither_observed_px": observed_y_delta,
            "y_dither_expected_px": expected_y_delta,
            "y_dither_vector_error_px": float(
                np.linalg.norm(observed_y_delta - expected_y_delta)
            ),
        }
        if max(abs(value) for value in x_residuals) > 0.25:
            reasons.append(f"{tool} absolute X residual exceeds 0.25 mm")
        if max(abs(value) for value in y_residuals) > 0.25:
            reasons.append(f"{tool} absolute Y residual exceeds 0.25 mm")
        if tool_results[tool]["x_dither_vector_error_px"] > 2.0:
            reasons.append(f"{tool} X-dither vector error exceeds 2 px")
        if tool_results[tool]["y_dither_vector_error_px"] > 2.0:
            reasons.append(f"{tool} Y-dither vector error exceeds 2 px")
        for record in tool_records:
            if float(record["minimum_correlation"]) < 0.45:
                reasons.append(
                    f"{tool} {record['pose']} correlation is below 0.45"
                )
            if float(record["representation_spread_px"]) > 2.0:
                reasons.append(
                    f"{tool} {record['pose']} registration representations disagree"
                )

    relative_x = (
        tool_results["T1"]["absolute_x_residual_mm"]
        - tool_results["T0"]["absolute_x_residual_mm"]
    )
    relative_y = (
        tool_results["T1"]["absolute_y_residual_mm"]
        - tool_results["T0"]["absolute_y_residual_mm"]
    )
    if abs(relative_x) > 0.20:
        reasons.append("T1-minus-T0 X residual exceeds 0.20 mm")
    if abs(relative_y) > 0.20:
        reasons.append("T1-minus-T0 Y residual exceeds 0.20 mm")

    panel_width = 640
    panel_height = 360
    sheet = np.zeros((panel_height * 2, panel_width * 3, 3), dtype=np.uint8)
    for index, (image, record) in enumerate(zip(images, records)):
        overlay = image.copy()
        expected = tuple(
            np.rint(record["predicted_tip_center_px"]).astype(int)
        )
        observed = tuple(
            np.rint(record["observed_tip_center_px"]).astype(int)
        )
        cv2.drawMarker(overlay, expected, (255, 255, 0), cv2.MARKER_CROSS, 28, 2)
        cv2.drawMarker(overlay, observed, (0, 255, 0), cv2.MARKER_CROSS, 22, 2)
        for point in record["expected_marker_centers_px"]:
            cv2.circle(overlay, tuple(np.rint(point).astype(int)), 18, (255, 255, 0), 2)
        for point in record["observed_marker_centers_px"]:
            cv2.circle(overlay, tuple(np.rint(point).astype(int)), 12, (0, 255, 0), 2)
        cv2.putText(
            overlay,
            (
                f"{record['tool']} {record['pose']} "
                f"Xres={record['x_residual_mm']:+.3f} "
                f"Yres={record['y_residual_mm']:+.3f} mm"
            ),
            (24, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (0, 255, 255),
            2,
            cv2.LINE_AA,
        )
        resized = cv2.resize(overlay, (panel_width, panel_height))
        row, column = divmod(index, 3)
        sheet[
            row * panel_height : (row + 1) * panel_height,
            column * panel_width : (column + 1) * panel_width,
        ] = resized
    overlay_path = artifact_dir / "fine_xy_verification_overlay.jpg"
    if not cv2.imwrite(str(overlay_path), sheet):
        raise FineToolVerificationError("failed to write verification overlay")

    return _finite(
        {
            "accepted": not reasons,
            "reasons": sorted(set(reasons)),
            "warnings": warnings,
            "tool_results": tool_results,
            "t1_minus_t0_x_residual_mm": relative_x,
            "t1_minus_t0_y_residual_mm": relative_y,
            "records": records,
            "z_verification_status": "pending_eddy_verification",
            "artifacts": {
                "fine_xy_verification_overlay": _artifact(overlay_path)
            },
        }
    )
