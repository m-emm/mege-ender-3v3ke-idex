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


def _plot_point(x_value, y_value, *, x_limits, y_limits, rectangle):
    left, top, right, bottom = rectangle
    x = left + (x_value - x_limits[0]) * (right - left) / (
        x_limits[1] - x_limits[0]
    )
    y = bottom - (y_value - y_limits[0]) * (bottom - top) / (
        y_limits[1] - y_limits[0]
    )
    return int(round(x)), int(round(y))


def _write_downstream_absolute_x_plot(tool, result, path):
    canvas = np.full((1000, 1000, 3), 245, dtype=np.uint8)
    cv2.putText(
        canvas,
        f"Stage 5 {tool}: absolute image X versus commanded Z",
        (45, 55),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.18,
        (20, 20, 20),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        (
            "circles: accepted green coordinates   red X: discarded   "
            "solid lines: fitted projection model"
        ),
        (45, 92),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (45, 45, 45),
        2,
        cv2.LINE_AA,
    )
    colors = [
        (210, 80, 50),
        (50, 140, 210),
        (70, 170, 70),
        (170, 80, 180),
        (40, 170, 190),
        (180, 120, 50),
        (110, 110, 110),
    ]
    for tool_index, tool in enumerate((tool,)):
        model = result["models"][tool]
        registrations = result["registrations"]
        accepted_sequences = {int(item) for item in model["accepted_sequences"]}
        commanded_x_values = sorted(
            {float(record["x_mm"]) for record in registrations}
        )
        commanded_z_values = sorted(
            {float(record["z_mm"]) for record in registrations}
        )
        predicted_x_values = [
            _model_center_x_px(model, commanded_x, commanded_z)
            for commanded_x in commanded_x_values
            for commanded_z in np.linspace(
                commanded_z_values[0], commanded_z_values[-1], 121
            )
        ]
        measured_x_values = [
            float(record["center_px"][0]) for record in registrations
        ]
        y_min = min(measured_x_values + predicted_x_values)
        y_max = max(measured_x_values + predicted_x_values)
        y_margin = max(5.0, 0.08 * (y_max - y_min))
        y_limits = (y_min - y_margin, y_max + y_margin)
        x_limits = (commanded_z_values[0], commanded_z_values[-1])
        panel_left = 70 + tool_index * 930
        rectangle = (panel_left + 90, 275, panel_left + 850, 860)

        cv2.putText(
            canvas,
            (
                f"{tool}: measured center_px[0] used downstream "
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

        for tick_z in commanded_z_values:
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

        dense_z_values = np.linspace(x_limits[0], x_limits[1], 121)
        for index, commanded_x in enumerate(commanded_x_values):
            color = colors[index]
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
            cv2.polylines(canvas, [line_points], False, color, 2, cv2.LINE_AA)
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
            "left: adjacent accepted-coordinate scales and model extrapolation   "
            "right: extrapolated scale versus commanded Z and fiducial-scale crossing"
        ),
        (45, 92),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.61,
        (45, 45, 45),
        2,
        cv2.LINE_AA,
    )
    z_colors = [
        (60, 160, 70),
        (50, 150, 210),
        (170, 90, 180),
        (210, 100, 55),
    ]
    for tool_index, tool in enumerate((tool,)):
        model = result["models"][tool]
        registrations = result["registrations"]
        accepted_sequences = {int(item) for item in model["accepted_sequences"]}
        accepted = [
            record
            for record in registrations
            if int(record["seq"]) in accepted_sequences
        ]
        measured_x_min = min(float(record["x_mm"]) for record in registrations)
        measured_x_max = max(float(record["x_mm"]) for record in registrations)
        commanded_z_values = sorted(
            {float(record["z_mm"]) for record in registrations}
        )
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

        measured_scale_points = {}
        for commanded_z in commanded_z_values:
            row = sorted(
                (
                    record
                    for record in accepted
                    if abs(float(record["z_mm"]) - commanded_z) < 1e-9
                ),
                key=lambda record: float(record["x_mm"]),
            )
            points = []
            for first, second in zip(row, row[1:]):
                delta_x_mm = float(second["x_mm"]) - float(first["x_mm"])
                if delta_x_mm <= 0.0:
                    continue
                image_delta = np.asarray(
                    second["center_px"], dtype=np.float64
                ) - np.asarray(first["center_px"], dtype=np.float64)
                points.append(
                    (
                        0.5 * (float(first["x_mm"]) + float(second["x_mm"])),
                        float(np.dot(image_delta / delta_x_mm, fiducial_direction)),
                    )
                )
            measured_scale_points[commanded_z] = points

        extrapolation_x_limits = (
            fiducial_x - 2.0,
            measured_x_max + 2.0,
        )
        dense_x = np.linspace(*extrapolation_x_limits, 181)
        left_values = [
            projected_scale(float(commanded_x), commanded_z)
            for commanded_z in commanded_z_values
            for commanded_x in dense_x
        ] + [
            scale
            for points in measured_scale_points.values()
            for _commanded_x, scale in points
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
                f"fit RMS={float(model['position_fit_rms_px']):.3f} px"
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
            "Lateral scale field and extrapolation",
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
            for commanded_x, measured_scale in measured_scale_points[commanded_z]:
                point = _plot_point(
                    commanded_x,
                    measured_scale,
                    x_limits=extrapolation_x_limits,
                    y_limits=left_y_limits,
                    rectangle=left_rectangle,
                )
                cv2.circle(canvas, point, 6, (25, 25, 25), 2, cv2.LINE_AA)
                cv2.circle(canvas, point, 4, color, -1, cv2.LINE_AA)
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
                f"fiducial scale={fiducial_scale:.6f} px/mm; "
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

    analyzer = _analyzer_module()
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + uuid4().hex[:8]
    )
    run_root = OUTPUT_ROOT / "runs" / run_id
    run_root.mkdir(parents=True)
    summaries = []
    replay_results = {}

    for tool, capture_dir in CAPTURES.items():
        manifest = json.loads(
            (capture_dir / "manifest.json").read_text(encoding="utf-8")
        )
        assert {frame["tool"] for frame in manifest["frames"]} == {tool}
        frame_paths = [
            capture_dir / "frames" / f"{frame['frame']}.jpg"
            for frame in manifest["frames"]
        ]
        assert len(frame_paths) == 28
        assert all(path.is_file() for path in frame_paths)

        artifact_dir = run_root / tool.lower()
        result = analyzer.analyze(
            frame_paths,
            artifact_dir,
            frames=manifest["frames"],
            reference=manifest["fine_reference"],
        )
        replay_results[tool] = result
        (artifact_dir / "result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        for artifact_name in EXPECTED_ARTIFACTS:
            jpeg_path = Path(result["artifacts"][artifact_name]["path"])
            assert jpeg_path.is_file()
            png_path = jpeg_path.with_suffix(".png")
            image = cv2.imread(str(jpeg_path), cv2.IMREAD_COLOR)
            assert image is not None
            assert cv2.imwrite(str(png_path), image)

        individual_overlays = {
            name: Path(artifact["path"])
            for name, artifact in result["artifacts"].items()
            if name.startswith(INDIVIDUAL_OVERLAY_PREFIX)
        }
        assert len(individual_overlays) == len(frame_paths)
        for sequence, source_path in enumerate(frame_paths):
            overlay_path = individual_overlays[
                f"{INDIVIDUAL_OVERLAY_PREFIX}{sequence:02d}"
            ]
            source_image = cv2.imread(str(source_path), cv2.IMREAD_COLOR)
            overlay_image = cv2.imread(str(overlay_path), cv2.IMREAD_COLOR)
            assert source_image is not None
            assert overlay_image is not None
            assert overlay_image.shape == source_image.shape

        model = result["models"][tool]
        reasons = result["reasons"] or ["none"]
        summaries.extend(
            [
                f"## {tool}",
                "",
                f"- Source job: `{manifest['job_id']}`",
                f"- Analyzer accepted: `{bool(result['accepted'])}`",
                f"- Accepted coordinates: `{model['accepted_count']}`",
                f"- Position-fit RMS: `{model['position_fit_rms_px']:.6f} px`",
                f"- Reasons: {'; '.join(reasons)}",
                "- Files:",
                f"  - [registration grid]({tool.lower()}/fine_nozzle_tip_registration_grid.png)",
                f"  - [tip reference]({tool.lower()}/fine_nozzle_tip_references.png)",
                f"  - [projection model]({tool.lower()}/fine_nozzle_projection_model.png)",
                f"  - [absolute image X versus commanded Z]"
                f"({tool.lower()}/downstream_absolute_x_vs_commanded_z.png)",
                f"  - [fiducial-X extrapolation preview]"
                f"({tool.lower()}/fiducial_x_extrapolation_preview.png)",
                f"  - Individual full-resolution overlays: "
                f"`{tool.lower()}/fine_nozzle_tip_overlays/` "
                f"({len(individual_overlays)} PNG files)",
                f"  - [result JSON]({tool.lower()}/result.json)",
                "",
            ]
        )

    for tool, result in replay_results.items():
        tool_output = run_root / tool.lower()
        _write_downstream_absolute_x_plot(
            tool,
            result,
            tool_output / "downstream_absolute_x_vs_commanded_z.png",
        )
        _write_fiducial_x_extrapolation_preview(
            tool,
            result,
            tool_output / "fiducial_x_extrapolation_preview.png",
        )
    summary_path = run_root / "inspection_summary.md"
    summary_path.write_text(
        "# Local Step 5 captured-image replay\n\n"
        "The green cross is the coordinate passed into each projection model.\n\n"
        "Downstream-coordinate and fiducial-extrapolation plots are generated "
        "as separate T0 and T1 images.\n\n"
        + "\n".join(summaries),
        encoding="utf-8",
    )

    print(f"\nSTEP 5 REPLAY OUTPUT DIRECTORY:\n{run_root.resolve()}")
    print("\nGENERATED FILES:")
    for path in sorted(item for item in run_root.rglob("*") if item.is_file()):
        print(path.resolve())
