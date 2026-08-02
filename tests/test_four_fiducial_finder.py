import importlib.util
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest
import logging

_logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
FILES = (
    REPO_ROOT
    / "klipper_setup"
    / "image_build"
    / "overlays"
    / "stage2"
    / "99-klipperpi"
    / "files"
)
DATASET_ROOT = (
    REPO_ROOT
    / "resources"
    / "vision_datasets"
    / "20260731_step5_green_coordinate_check"
)
OUTPUT_ROOT = REPO_ROOT / "output" / "vision_step5_green_coordinate_check"
CAPTURES = {
    "T0": DATASET_ROOT / "t0",
    "T1": DATASET_ROOT / "t1",
}
EXPECTED_ARTIFACTS = (
    "fine_nozzle_tip_registration_grid",
    "fine_nozzle_tip_references",
    "fine_nozzle_projection_model",
)
INDIVIDUAL_OVERLAY_PREFIX = "fine_nozzle_tip_overlay_"

TEST_FRAMES_DIR = Path("/tmp/test_fidu_jobs/frames/")

def _model_center_x_px(model, commanded_x_mm, commanded_z_mm):
    dx = float(commanded_x_mm) - float(model["x_ref_mm"])
    dz = float(commanded_z_mm) - float(model["z_ref_mm"])
    terms = np.asarray(
        [1.0, dx, dz, dx * dz, dx * dx, dx * dx * dz],
        dtype=np.float64,
    )
    coefficients = np.asarray(model["position_coefficients"], dtype=np.float64)
    return float(terms @ coefficients[:, 0])


def _model_x_vector_px_per_mm(model, commanded_x_mm, commanded_z_mm):
    coefficients = np.asarray(model["position_coefficients"], dtype=np.float64)
    dx = float(commanded_x_mm) - float(model["x_ref_mm"])
    dz = float(commanded_z_mm) - float(model["z_ref_mm"])
    return (
        coefficients[1]
        + coefficients[3] * dz
        + 2.0 * coefficients[4] * dx
        + 2.0 * coefficients[5] * dx * dz
    )


def _global_absolute_position_refit(model, registrations):
    accepted_sequences = {int(item) for item in model["accepted_sequences"]}
    accepted = [
        record
        for record in registrations
        if int(record["seq"]) in accepted_sequences
    ]
    x_ref = float(model["x_ref_mm"])
    z_ref = float(model["z_ref_mm"])
    design = []
    for record in accepted:
        dx = float(record["x_mm"]) - x_ref
        dz = float(record["z_mm"]) - z_ref
        design.append([1.0, dx, dz, dx * dz, dx * dx, dx * dx * dz])
    design = np.asarray(design, dtype=np.float64)
    positions = np.asarray(
        [record["center_px"] for record in accepted], dtype=np.float64
    )
    assert np.linalg.matrix_rank(design) == design.shape[1]
    coefficients = np.linalg.lstsq(design, positions, rcond=None)[0]
    refit = dict(model)
    refit["position_coefficients"] = coefficients.tolist()
    refit["position_fit_rms_px"] = float(
        np.sqrt(np.mean(np.sum((positions - design @ coefficients) ** 2, axis=1)))
    )
    assert np.allclose(
        coefficients,
        np.asarray(model["position_coefficients"], dtype=np.float64),
        rtol=1e-10,
        atol=1e-8,
    )
    return refit, accepted


def _draw_dashed_line(
    image, start, end, color, *, thickness=2, dash_length=12, gap_length=8
):
    start = np.asarray(start, dtype=np.float64)
    end = np.asarray(end, dtype=np.float64)
    delta = end - start
    length = float(np.linalg.norm(delta))
    if length <= 1e-9:
        return
    direction = delta / length
    for offset in np.arange(0.0, length, dash_length + gap_length):
        segment_end = min(length, offset + dash_length)
        cv2.line(
            image,
            tuple(np.rint(start + direction * offset).astype(int)),
            tuple(np.rint(start + direction * segment_end).astype(int)),
            color,
            thickness,
            cv2.LINE_AA,
        )


def _distinct_bgr_colors(count):
    assert count > 0
    hues = np.linspace(0, 179, count, endpoint=False, dtype=np.uint8)
    hsv = np.zeros((1, count, 3), dtype=np.uint8)
    hsv[0, :, 0] = hues
    hsv[0, :, 1] = 185
    hsv[0, :, 2] = 205
    return [
        tuple(int(channel) for channel in color)
        for color in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0]
    ]


def _plot_point(x_value, y_value, *, x_limits, y_limits, rectangle):
    left, top, right, bottom = rectangle
    x = left + (x_value - x_limits[0]) * (right - left) / (
        x_limits[1] - x_limits[0]
    )
    y = bottom - (y_value - y_limits[0]) * (bottom - top) / (
        y_limits[1] - y_limits[0]
    )
    return int(round(x)), int(round(y))


def _write_downstream_absolute_x_plot(tool, result, path, *, show_model):
    canvas = np.full((1000, 1000, 3), 245, dtype=np.uint8)
    cv2.putText(
        canvas,
        (
            f"Stage 5 {tool}: global absolute-position model overlay"
            if show_model
            else f"Stage 5 {tool}: raw absolute image X versus commanded Z"
        ),
        (45, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.96,
        (20, 20, 20),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        (
            (
                "circles: measured accepted   red X: discarded   "
                "black +: fitted prediction"
            )
            if show_model
            else "circles: measured accepted coordinates   red X: discarded   no model"
        ),
        (45, 92),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (45, 45, 45),
        2,
        cv2.LINE_AA,
    )
    for tool_index, tool in enumerate((tool,)):
        registrations = result["registrations"]
        model, _accepted_records = _global_absolute_position_refit(
            result["models"][tool], registrations
        )
        accepted_sequences = {int(item) for item in model["accepted_sequences"]}
        commanded_x_values = sorted(
            {float(record["x_mm"]) for record in registrations}
        )
        colors = _distinct_bgr_colors(len(commanded_x_values))
        commanded_z_values = sorted(
            {float(record["z_mm"]) for record in registrations}
        )
        x_differences = np.diff(commanded_x_values)
        commanded_x_pitch = float(np.median(x_differences))
        assert np.allclose(x_differences, commanded_x_pitch, atol=1e-9)
        fiducial_x = float(result["fiducial_reference_printer_xy_mm"][0])
        extrapolated_commanded_x_values = []
        next_commanded_x = commanded_x_values[0] - commanded_x_pitch
        while next_commanded_x >= fiducial_x - 0.5 * commanded_x_pitch:
            extrapolated_commanded_x_values.append(next_commanded_x)
            next_commanded_x -= commanded_x_pitch

        model_z_min = -1.0
        model_z_max = commanded_z_values[-1]
        fiducial_plane_z = float(result["fiducial_plane_printer_z_mm"])
        fiducial_columns = (
            (
                "reference fiducial",
                float(result["fiducial_reference_printer_xy_mm"][0]),
                float(result["fiducial_reference_pixel_at_fine_capture_px"][0]),
                (175, 70, 165),
            ),
            (
                "bed-tab fiducial",
                float(result["bed_tab_printer_x_mm"]),
                float(result["bed_tab_corner_pixel_at_fine_capture_px"][0]),
                (35, 115, 220),
            ),
        )
        dense_z_values = np.linspace(model_z_min, model_z_max, 181)
        predicted_x_values = (
            [
                _model_center_x_px(model, commanded_x, commanded_z)
                for commanded_x in (
                    commanded_x_values + extrapolated_commanded_x_values
                )
                for commanded_z in dense_z_values
            ]
            if show_model
            else []
        )
        measured_x_values = [
            float(record["center_px"][0]) for record in registrations
        ]
        if show_model:
            measured_x_values.extend(column[2] for column in fiducial_columns)
        y_min = min(measured_x_values + predicted_x_values)
        y_max = max(measured_x_values + predicted_x_values)
        y_margin = max(5.0, 0.08 * (y_max - y_min))
        y_limits = (y_min - y_margin, y_max + y_margin)
        x_limits = (
            (model_z_min, model_z_max)
            if show_model
            else (commanded_z_values[0], commanded_z_values[-1])
        )
        panel_left = 70 + tool_index * 930
        rectangle = (panel_left + 90, 275, panel_left + 850, 860)

        cv2.putText(
            canvas,
            (
                f"{tool}: measured center_px[0] "
                f"({len(accepted_sequences)}/{len(registrations)} accepted)"
            ),
            (panel_left, 145),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.67,
            (20, 20, 20),
            2,
            cv2.LINE_AA,
        )
        legend_x = panel_left
        for index, commanded_x in enumerate(commanded_x_values):
            color = colors[index]
            item_x = legend_x + (index % 4) * 205
            item_y = 180 + (index // 4) * 31
            cv2.line(canvas, (item_x, item_y), (item_x + 28, item_y), color, 3)
            cv2.putText(
                canvas,
                f"command X={commanded_x:.1f}",
                (item_x + 36, item_y + 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.43,
                (35, 35, 35),
                1,
                cv2.LINE_AA,
            )

        if show_model:
            cv2.putText(
                canvas,
                (
                    f"global fit input={len(_accepted_records)} absolute coordinates; "
                    f"solid=measured X trajectories; dashed=extrapolated X "
                    f"{extrapolated_commanded_x_values[0]:.1f}.."
                    f"{extrapolated_commanded_x_values[-1]:.1f} mm at "
                    f"{commanded_x_pitch:.1f} mm pitch"
                ),
                (panel_left, 244),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.40,
                (35, 35, 35),
                1,
                cv2.LINE_AA,
            )

        tick_z_values = (
            [model_z_min] + commanded_z_values if show_model else commanded_z_values
        )
        for tick_z in tick_z_values:
            top_point = _plot_point(
                tick_z,
                y_limits[1],
                x_limits=x_limits,
                y_limits=y_limits,
                rectangle=rectangle,
            )
            bottom_point = _plot_point(
                tick_z,
                y_limits[0],
                x_limits=x_limits,
                y_limits=y_limits,
                rectangle=rectangle,
            )
            cv2.line(canvas, top_point, bottom_point, (215, 215, 215), 1)
            cv2.putText(
                canvas,
                f"{tick_z:.3f}",
                (bottom_point[0] - 30, rectangle[3] + 29),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.43,
                (45, 45, 45),
                1,
                cv2.LINE_AA,
            )
        for tick_x in np.linspace(y_limits[0], y_limits[1], 6):
            left_point = _plot_point(
                x_limits[0],
                float(tick_x),
                x_limits=x_limits,
                y_limits=y_limits,
                rectangle=rectangle,
            )
            right_point = _plot_point(
                x_limits[1],
                float(tick_x),
                x_limits=x_limits,
                y_limits=y_limits,
                rectangle=rectangle,
            )
            cv2.line(canvas, left_point, right_point, (225, 225, 225), 1)
            cv2.putText(
                canvas,
                f"{tick_x:.1f}",
                (rectangle[0] - 70, left_point[1] + 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.43,
                (45, 45, 45),
                1,
                cv2.LINE_AA,
            )
        cv2.rectangle(
            canvas,
            (rectangle[0], rectangle[1]),
            (rectangle[2], rectangle[3]),
            (65, 65, 65),
            2,
        )

        if show_model:
            measured_region_left = _plot_point(
                commanded_z_values[0],
                y_limits[1],
                x_limits=x_limits,
                y_limits=y_limits,
                rectangle=rectangle,
            )[0]
            cv2.rectangle(
                canvas,
                (rectangle[0], rectangle[1]),
                (measured_region_left, rectangle[3]),
                (225, 238, 245),
                -1,
            )
            cv2.rectangle(
                canvas,
                (rectangle[0], rectangle[1]),
                (rectangle[2], rectangle[3]),
                (65, 65, 65),
                2,
            )

        for index, commanded_x in enumerate(commanded_x_values):
            color = colors[index]
            if show_model:
                line_points = np.asarray(
                    [
                        _plot_point(
                            float(commanded_z),
                            _model_center_x_px(model, commanded_x, commanded_z),
                            x_limits=x_limits,
                            y_limits=y_limits,
                            rectangle=rectangle,
                        )
                        for commanded_z in dense_z_values
                    ],
                    dtype=np.int32,
                )
                cv2.polylines(
                    canvas, [line_points], False, color, 2, cv2.LINE_AA
                )
            for record in registrations:
                if abs(float(record["x_mm"]) - commanded_x) > 1e-9:
                    continue
                point = _plot_point(
                    float(record["z_mm"]),
                    float(record["center_px"][0]),
                    x_limits=x_limits,
                    y_limits=y_limits,
                    rectangle=rectangle,
                )
                if int(record["seq"]) in accepted_sequences:
                    cv2.circle(canvas, point, 7, (20, 20, 20), 2, cv2.LINE_AA)
                    cv2.circle(canvas, point, 5, color, -1, cv2.LINE_AA)
                else:
                    cv2.drawMarker(
                        canvas,
                        point,
                        (0, 0, 255),
                        cv2.MARKER_TILTED_CROSS,
                        18,
                        3,
                        cv2.LINE_AA,
                    )

        if show_model:
            fiducial_top = _plot_point(
                fiducial_plane_z,
                y_limits[1],
                x_limits=x_limits,
                y_limits=y_limits,
                rectangle=rectangle,
            )
            fiducial_bottom = _plot_point(
                fiducial_plane_z,
                y_limits[0],
                x_limits=x_limits,
                y_limits=y_limits,
                rectangle=rectangle,
            )
            _draw_dashed_line(
                canvas,
                fiducial_top,
                fiducial_bottom,
                (90, 90, 90),
                thickness=2,
                dash_length=4,
                gap_length=5,
            )
            cv2.putText(
                canvas,
                f"fiducial plane Z={fiducial_plane_z:+.3f}",
                (fiducial_top[0] + 8, rectangle[1] + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.37,
                (55, 55, 55),
                1,
                cv2.LINE_AA,
            )

            for extrapolated_index, commanded_x in enumerate(
                extrapolated_commanded_x_values
            ):
                shade = int(
                    85
                    + 95
                    * extrapolated_index
                    / max(1, len(extrapolated_commanded_x_values) - 1)
                )
                start = _plot_point(
                    model_z_min,
                    _model_center_x_px(model, commanded_x, model_z_min),
                    x_limits=x_limits,
                    y_limits=y_limits,
                    rectangle=rectangle,
                )
                end = _plot_point(
                    model_z_max,
                    _model_center_x_px(model, commanded_x, model_z_max),
                    x_limits=x_limits,
                    y_limits=y_limits,
                    rectangle=rectangle,
                )
                _draw_dashed_line(
                    canvas,
                    start,
                    end,
                    (shade, shade, shade),
                    thickness=2,
                    dash_length=10,
                    gap_length=7,
                )

            for name, printer_x, image_x, color in fiducial_columns:
                point = _plot_point(
                    fiducial_plane_z,
                    image_x,
                    x_limits=x_limits,
                    y_limits=y_limits,
                    rectangle=rectangle,
                )
                cv2.drawMarker(
                    canvas,
                    point,
                    color,
                    cv2.MARKER_DIAMOND,
                    20,
                    3,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    canvas,
                    f"{name}: printer X={printer_x:.3f}, image X={image_x:.3f}",
                    (point[0] + 12, point[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.35,
                    color,
                    1,
                    cv2.LINE_AA,
                )

            for record in _accepted_records:
                prediction = _plot_point(
                    float(record["z_mm"]),
                    _model_center_x_px(
                        model, float(record["x_mm"]), float(record["z_mm"])
                    ),
                    x_limits=x_limits,
                    y_limits=y_limits,
                    rectangle=rectangle,
                )
                cv2.drawMarker(
                    canvas,
                    prediction,
                    (15, 15, 15),
                    cv2.MARKER_CROSS,
                    11,
                    2,
                    cv2.LINE_AA,
                )

        cv2.putText(
            canvas,
            "commanded Z (mm)",
            (rectangle[0] + 290, rectangle[3] + 72),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (25, 25, 25),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "absolute image X (px)",
            (rectangle[0] - 70, rectangle[1] - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (25, 25, 25),
            2,
            cv2.LINE_AA,
        )

    assert cv2.imwrite(str(path), canvas)


def _write_fiducial_x_extrapolation_preview(tool, result, path):
    canvas = np.full((900, 2100, 3), 245, dtype=np.uint8)
    cv2.putText(
        canvas,
        "Stage 5 preview: transport nozzle X scale to the fiducial X",
        (45, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.22,
        (20, 20, 20),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        (
            "left: derivative of one global fit to accepted absolute coordinates   "
            "right: that fitted derivative transported to fiducial X"
        ),
        (45, 92),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.61,
        (45, 45, 45),
        2,
        cv2.LINE_AA,
    )
    for tool_index, tool in enumerate((tool,)):
        registrations = result["registrations"]
        model, accepted = _global_absolute_position_refit(
            result["models"][tool], registrations
        )
        accepted_sequences = {int(item) for item in model["accepted_sequences"]}
        measured_x_min = min(float(record["x_mm"]) for record in registrations)
        measured_x_max = max(float(record["x_mm"]) for record in registrations)
        commanded_z_values = sorted(
            {float(record["z_mm"]) for record in registrations}
        )
        z_colors = _distinct_bgr_colors(len(commanded_z_values))
        fiducial_x = float(result["fiducial_reference_printer_xy_mm"][0])
        fiducial_vector = np.asarray(
            result["fiducial_x_vector_at_fine_capture_px_per_mm"],
            dtype=np.float64,
        )
        fiducial_scale = float(np.linalg.norm(fiducial_vector))
        fiducial_direction = fiducial_vector / fiducial_scale

        def projected_scale(commanded_x, commanded_z):
            return float(
                np.dot(
                    _model_x_vector_px_per_mm(
                        model,
                        commanded_x,
                        commanded_z,
                    ),
                    fiducial_direction,
                )
            )

        extrapolation_x_limits = (
            fiducial_x - 2.0,
            measured_x_max + 2.0,
        )
        dense_x = np.linspace(*extrapolation_x_limits, 181)
        left_values = [
            projected_scale(float(commanded_x), commanded_z)
            for commanded_z in commanded_z_values
            for commanded_x in dense_x
        ]
        left_margin = max(0.15, 0.08 * (max(left_values) - min(left_values)))
        left_y_limits = (
            min(left_values) - left_margin,
            max(left_values) + left_margin,
        )

        coefficients = np.asarray(
            model["position_coefficients"], dtype=np.float64
        )
        dx_fiducial = fiducial_x - float(model["x_ref_mm"])
        projected_z_slope = float(
            np.dot(
                coefficients[3] + 2.0 * coefficients[5] * dx_fiducial,
                fiducial_direction,
            )
        )
        projected_at_z_ref = projected_scale(
            fiducial_x,
            float(model["z_ref_mm"]),
        )
        crossing_z = (
            float(model["z_ref_mm"])
            + (fiducial_scale - projected_at_z_ref) / projected_z_slope
            if abs(projected_z_slope) > 1e-9
            else None
        )
        right_x_limits = (
            min(
                commanded_z_values[0] - 2.0,
                (crossing_z - 2.0) if crossing_z is not None else math.inf,
            ),
            max(
                commanded_z_values[-1] + 1.0,
                (crossing_z + 2.0) if crossing_z is not None else -math.inf,
            ),
        )
        dense_z = np.linspace(*right_x_limits, 181)
        right_values = [
            projected_scale(fiducial_x, float(commanded_z))
            for commanded_z in dense_z
        ] + [fiducial_scale]
        right_margin = max(0.10, 0.10 * (max(right_values) - min(right_values)))
        right_y_limits = (
            min(right_values) - right_margin,
            max(right_values) + right_margin,
        )

        row_top = 115 + tool_index * 740
        left_rectangle = (105, row_top + 175, 1000, row_top + 590)
        right_rectangle = (1160, row_top + 175, 2055, row_top + 590)
        cv2.putText(
            canvas,
            (
                f"{tool}: {len(accepted_sequences)}/{len(registrations)} accepted; "
                f"one global absolute-coordinate fit; "
                f"RMS={float(model['position_fit_rms_px']):.3f} px"
            ),
            (55, row_top + 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.86,
            (15, 15, 15),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "Derivative of global absolute-position fit",
            (left_rectangle[0] + 215, row_top + 83),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.66,
            (25, 25, 25),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "Depth crossing at the fiducial printer X",
            (right_rectangle[0] + 205, row_top + 83),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.66,
            (25, 25, 25),
            2,
            cv2.LINE_AA,
        )
        for index, commanded_z in enumerate(commanded_z_values):
            item_x = 75 + index * 245
            item_y = row_top + 116
            cv2.line(
                canvas,
                (item_x, item_y),
                (item_x + 30, item_y),
                z_colors[index],
                3,
                cv2.LINE_AA,
            )
            cv2.putText(
                canvas,
                f"Z={commanded_z:.3f}",
                (item_x + 38, item_y + 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.44,
                (35, 35, 35),
                1,
                cv2.LINE_AA,
            )

        shade_left = _plot_point(
            measured_x_min,
            left_y_limits[1],
            x_limits=extrapolation_x_limits,
            y_limits=left_y_limits,
            rectangle=left_rectangle,
        )[0]
        cv2.rectangle(
            canvas,
            (shade_left, left_rectangle[1]),
            (left_rectangle[2], left_rectangle[3]),
            (232, 232, 232),
            -1,
        )
        for rectangle, x_limits, y_limits in (
            (left_rectangle, extrapolation_x_limits, left_y_limits),
            (right_rectangle, right_x_limits, right_y_limits),
        ):
            for tick_x in np.linspace(x_limits[0], x_limits[1], 6):
                top = _plot_point(
                    float(tick_x),
                    y_limits[1],
                    x_limits=x_limits,
                    y_limits=y_limits,
                    rectangle=rectangle,
                )
                bottom = _plot_point(
                    float(tick_x),
                    y_limits[0],
                    x_limits=x_limits,
                    y_limits=y_limits,
                    rectangle=rectangle,
                )
                cv2.line(canvas, top, bottom, (215, 215, 215), 1)
                cv2.putText(
                    canvas,
                    f"{tick_x:.1f}",
                    (bottom[0] - 25, rectangle[3] + 27),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.40,
                    (45, 45, 45),
                    1,
                    cv2.LINE_AA,
                )
            for tick_y in np.linspace(y_limits[0], y_limits[1], 6):
                left = _plot_point(
                    x_limits[0],
                    float(tick_y),
                    x_limits=x_limits,
                    y_limits=y_limits,
                    rectangle=rectangle,
                )
                right = _plot_point(
                    x_limits[1],
                    float(tick_y),
                    x_limits=x_limits,
                    y_limits=y_limits,
                    rectangle=rectangle,
                )
                cv2.line(canvas, left, right, (220, 220, 220), 1)
                cv2.putText(
                    canvas,
                    f"{tick_y:.2f}",
                    (rectangle[0] - 64, left[1] + 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.40,
                    (45, 45, 45),
                    1,
                    cv2.LINE_AA,
                )
            cv2.rectangle(
                canvas,
                (rectangle[0], rectangle[1]),
                (rectangle[2], rectangle[3]),
                (65, 65, 65),
                2,
            )

        fiducial_top = _plot_point(
            fiducial_x,
            left_y_limits[1],
            x_limits=extrapolation_x_limits,
            y_limits=left_y_limits,
            rectangle=left_rectangle,
        )
        fiducial_bottom = _plot_point(
            fiducial_x,
            left_y_limits[0],
            x_limits=extrapolation_x_limits,
            y_limits=left_y_limits,
            rectangle=left_rectangle,
        )
        _draw_dashed_line(
            canvas,
            fiducial_top,
            fiducial_bottom,
            (185, 100, 40),
            thickness=2,
        )
        for index, commanded_z in enumerate(commanded_z_values):
            color = z_colors[index]
            line_points = np.asarray(
                [
                    _plot_point(
                        float(commanded_x),
                        projected_scale(float(commanded_x), commanded_z),
                        x_limits=extrapolation_x_limits,
                        y_limits=left_y_limits,
                        rectangle=left_rectangle,
                    )
                    for commanded_x in dense_x
                ],
                dtype=np.int32,
            )
            cv2.polylines(canvas, [line_points], False, color, 2, cv2.LINE_AA)
            extrapolated_point = _plot_point(
                fiducial_x,
                projected_scale(fiducial_x, commanded_z),
                x_limits=extrapolation_x_limits,
                y_limits=left_y_limits,
                rectangle=left_rectangle,
            )
            cv2.circle(
                canvas,
                extrapolated_point,
                7,
                (20, 20, 20),
                2,
                cv2.LINE_AA,
            )
            cv2.circle(canvas, extrapolated_point, 5, color, -1, cv2.LINE_AA)

        right_line = np.asarray(
            [
                _plot_point(
                    float(commanded_z),
                    projected_scale(fiducial_x, float(commanded_z)),
                    x_limits=right_x_limits,
                    y_limits=right_y_limits,
                    rectangle=right_rectangle,
                )
                for commanded_z in dense_z
            ],
            dtype=np.int32,
        )
        cv2.polylines(canvas, [right_line], False, (120, 70, 150), 3, cv2.LINE_AA)
        for index, commanded_z in enumerate(commanded_z_values):
            point = _plot_point(
                commanded_z,
                projected_scale(fiducial_x, commanded_z),
                x_limits=right_x_limits,
                y_limits=right_y_limits,
                rectangle=right_rectangle,
            )
            cv2.circle(canvas, point, 7, (25, 25, 25), 2, cv2.LINE_AA)
            cv2.circle(canvas, point, 5, z_colors[index], -1, cv2.LINE_AA)
        fiducial_scale_left = _plot_point(
            right_x_limits[0],
            fiducial_scale,
            x_limits=right_x_limits,
            y_limits=right_y_limits,
            rectangle=right_rectangle,
        )
        fiducial_scale_right = _plot_point(
            right_x_limits[1],
            fiducial_scale,
            x_limits=right_x_limits,
            y_limits=right_y_limits,
            rectangle=right_rectangle,
        )
        _draw_dashed_line(
            canvas,
            fiducial_scale_left,
            fiducial_scale_right,
            (185, 100, 40),
            thickness=2,
        )
        if crossing_z is not None:
            crossing_top = _plot_point(
                crossing_z,
                right_y_limits[1],
                x_limits=right_x_limits,
                y_limits=right_y_limits,
                rectangle=right_rectangle,
            )
            crossing_bottom = _plot_point(
                crossing_z,
                right_y_limits[0],
                x_limits=right_x_limits,
                y_limits=right_y_limits,
                rectangle=right_rectangle,
            )
            _draw_dashed_line(
                canvas,
                crossing_top,
                crossing_bottom,
                (0, 0, 220),
                thickness=2,
                dash_length=4,
                gap_length=6,
            )
            crossing_point = _plot_point(
                crossing_z,
                fiducial_scale,
                x_limits=right_x_limits,
                y_limits=right_y_limits,
                rectangle=right_rectangle,
            )
            cv2.circle(canvas, crossing_point, 8, (20, 20, 20), 2, cv2.LINE_AA)
            cv2.circle(canvas, crossing_point, 6, (0, 80, 230), -1, cv2.LINE_AA)

        cv2.putText(
            canvas,
            "printer X (mm)",
            (left_rectangle[0] + 365, left_rectangle[3] + 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.57,
            (25, 25, 25),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "projected nozzle X scale (px/mm)",
            (left_rectangle[0] - 50, left_rectangle[1] - 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (25, 25, 25),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "commanded Z (mm)",
            (right_rectangle[0] + 340, right_rectangle[3] + 45),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.57,
            (25, 25, 25),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            "scale at fiducial X (px/mm)",
            (right_rectangle[0] - 50, right_rectangle[1] - 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.50,
            (25, 25, 25),
            2,
            cv2.LINE_AA,
        )
        crossing_text = (
            f"crossing Z={crossing_z:+.3f} mm"
            if crossing_z is not None
            else "crossing unresolved"
        )
        cv2.putText(
            canvas,
            (
                f"fiducial X={fiducial_x:.3f} mm; measured X="
                f"{measured_x_min:.3f}..{measured_x_max:.3f} mm; "
                f"extrapolation={measured_x_min - fiducial_x:.3f} mm"
            ),
            (75, row_top + 700),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.53,
            (35, 35, 35),
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            canvas,
            (
                f"fit input={len(accepted)} accepted absolute coordinates; "
                f"pairwise local scales used=0; fiducial scale="
                f"{fiducial_scale:.6f} px/mm; "
                f"scale-Z slope={projected_z_slope:+.6f} px/mm/mm; "
                f"{crossing_text}; fiducial-plane Z="
                f"{float(result['fiducial_plane_printer_z_mm']):+.3f} mm"
            ),
            (75, row_top + 735),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.53,
            (35, 35, 35),
            1,
            cv2.LINE_AA,
        )

    assert cv2.imwrite(str(path), canvas)


def _analyzer_module():
    if str(FILES) not in sys.path:
        sys.path.insert(0, str(FILES))
    spec = importlib.util.spec_from_file_location(
        "vision_nozzle_fine_xz_captured_replay",
        FILES / "vision_nozzle_fine_xz.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_replay_captured_t0_and_t1_and_render_overlays():


    missing = [
        str(capture_dir)
        for capture_dir in CAPTURES.values()
        if not (capture_dir / "manifest.json").is_file()
    ]
    if missing:
        pytest.skip("local captured datasets are absent: " + ", ".join(missing))

    _logger.info(f"Load analyzer module from {FILES / 'vision_nozzle_fine_xz.py'}")
    analyzer = _analyzer_module()
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex[:8]
    )
    run_root = OUTPUT_ROOT / "runs" / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    centers= {}

    overlay_paths = []
    for i, path in enumerate(sorted(item for item in TEST_FRAMES_DIR.rglob("*.jpg") if item.is_file())):
        _logger.info(f"{path.resolve()}")

        
        image =  cv2.imread(str(path), cv2.IMREAD_COLOR)
        four_fiducials = analyzer.detect_four_fiducials(image)


        overlay = image.copy()

        for j, candidate in enumerate(four_fiducials["candiates"]):
            cv2.circle(
                overlay,
                tuple(np.rint(candidate["center_px"]).astype(int)),
                int(round(candidate["radius_px"])),
                (255, 0, 0),
                2,
            )

        for j, (center, radius) in enumerate(
            zip(
                four_fiducials["centers_px"],    
                four_fiducials["radii_px"],
            )
        ):
            # _logger.info(f"Drawing fiducial {i} at {center} with radius {radius}")
            cv2.circle(
                overlay,
                tuple(np.rint(center).astype(int)),
                int(round(radius)),
                (0, 255, 255),
                2,
            )

        centers[str(path)] = four_fiducials["centers_px"]

        overlay_file_name = f"overlay_{i:02d}.jpg"
        overlay_paths.append(run_root / overlay_file_name)
        cv2.imwrite(str(run_root / overlay_file_name), overlay)
        _logger.info(f"Saved overlay image to {run_root / overlay_file_name}")

        # for path in sorted(item for item in run_root.rglob("*") if item.is_file()):
        #     _logger.info(f"{path.resolve()}")


    median_centers = np.median(
        np.array(list(centers.values())), axis=0
    )

    center_of_median_centers = np.mean(median_centers, axis=0)

    centers_of_centers = np.mean(
        np.array(list(centers.values())), axis=0
    )

    for i, (path, center) in enumerate(centers.items()):
        center_mean = np.mean(center, axis=0)
        offset = center_of_median_centers - center_mean

        if np.linalg.norm(offset) >10:
            overlay_path = overlay_paths[i]
            _logger.warning(
                f"Center offset for {path.name} is {offset}, which exceeds the threshold. See overlay at {overlay_path}"
            )





