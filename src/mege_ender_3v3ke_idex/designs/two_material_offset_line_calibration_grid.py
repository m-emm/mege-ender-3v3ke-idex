"""Two-material IDEX absolute X/Y calibration against the painted bed grid.

Usage:
    cd <project_root> && ./run.sh path/to/two_material_offset_line_calibration_grid.py
    cd <project_root> && ./run.sh --slice path/to/two_material_offset_line_calibration_grid.py
"""

import logging
import os
from pathlib import Path

import yaml
from mege_3devops.process_data.mege_ender_3v3ke_idex import (
    SAFE_BED_DEPTH_MM,
    SAFE_BED_ORIGIN,
    SAFE_BED_WIDTH_MM,
    copy_dual_pla_04_offset_calibration_process_data,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

CALIB_PATH = (
    Path(__file__).resolve().parents[3]
    / "klipper_setup"
    / "klipper_config"
    / "calib.yaml"
)

ACTUAL_BED_WIDTH_MM = 310.0
ACTUAL_BED_DEPTH_MM = 310.0
ACTUAL_BED_COLOR = (0.015, 0.016, 0.014)
ACTUAL_BED_HEIGHT_MM = 0.08

PAINTED_FRAME_SIZE_MM = 300.0
PAINTED_FRAME_INSET_MM = (ACTUAL_BED_WIDTH_MM - PAINTED_FRAME_SIZE_MM) / 2
PAINTED_FRAME_ORIGIN_X_MM = -24.0
ACTUAL_BED_ORIGIN_X_MM = PAINTED_FRAME_ORIGIN_X_MM - PAINTED_FRAME_INSET_MM

PAINTED_FRAME_BACK_Y_MM = 296.0
PAINTED_FRAME_ORIGIN_Y_MM = PAINTED_FRAME_BACK_Y_MM - PAINTED_FRAME_SIZE_MM
ACTUAL_BED_ORIGIN_Y_MM = PAINTED_FRAME_ORIGIN_Y_MM - PAINTED_FRAME_INSET_MM
PAINTED_FRAME_LINE_WIDTH_MM = 0.9
PAINTED_FRAME_FILLET_RADIUS_MM = 5.0
PAINTED_FRAME_HEIGHT_MM = 0.25
PAINTED_FRAME_COLOR = (0.72, 0.72, 0.68)

GRID_PITCH_MM = 25.4
GRID_LINE_WIDTH_MM = 0.45
GRID_LINE_HEIGHT_MM = 0.2
GRID_LINE_COLOR = (0.72, 0.72, 0.68)
GRID_LINE_OVERHANG_MM = GRID_PITCH_MM / 3
GRID_CUTOUT_MARGIN_MM = 1.2
GRID_X_INDEX_MIN = -4
GRID_X_INDEX_MAX = 5
GRID_Y_INDEX_MIN = -3
GRID_Y_INDEX_MAX = 6

PANEL_OUTLINE_WIDTH_MM = 0.6
PANEL_OUTLINE_HEIGHT_MM = 0.24
PANEL_OUTLINE_COLOR = (0.72, 0.72, 0.68)

CALIBRATION_HEIGHT_MM = 0.6
CALIBRATION_LINE_WIDTH_MM = 0.7
CALIBRATION_LABEL_SIZE_MM = 4.5
CALIBRATION_LABEL_STROKE_WIDTH_MM = 0.6
CALIBRATION_LABEL_TEXT_THICKNESS_MM = 0.2
CALIBRATION_LABEL_PAD_THICKNESS_MM = 0.2
CALIBRATION_LABEL_PAD_MARGIN_MM = 3.0
CALIBRATION_LABEL_GAP_MM = 2.0
CALIBRATION_LABEL_GROUNDING_MARKER_SIZE_MM = 1.0
CALIBRATION_LABEL_GROUNDING_MARKER_GAP_MM = 1.0
CALIBRATION_LABEL_CONNECTOR_WIDTH_MM = CALIBRATION_LINE_WIDTH_MM
CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM = 0.3

CALIBRATION_GRID_X_INDEX_MIN = -4
CALIBRATION_GRID_X_INDEX_MAX = 4
CALIBRATION_GRID_Y_INDEX_MIN = -3
CALIBRATION_GRID_Y_INDEX_MAX = 5
CALIBRATION_OFFSET_STEP_MM = 0.2
CALIBRATION_OFFSET_CANDIDATES_MM = tuple(
    round(index * CALIBRATION_OFFSET_STEP_MM, 1)
    for index in range(CALIBRATION_GRID_X_INDEX_MIN, CALIBRATION_GRID_X_INDEX_MAX + 1)
)

X_PLATE_NAME = "absolute_x_grid_alignment"
Y_T0_PLATE_NAME = "absolute_y_t0_grid_alignment"
Y_T1_PLATE_NAME = "absolute_y_t1_grid_alignment"

X_T0_PART_NAME = "absolute_x_grid_alignment_t0"
X_T1_PART_NAME = "absolute_x_grid_alignment_t1"
Y_T0_LINES_PART_NAME = "absolute_y_t0_grid_alignment_t0_lines"
Y_T0_LABELS_PART_NAME = "absolute_y_t0_grid_alignment_t1_labels"
Y_T1_LINES_PART_NAME = "absolute_y_t1_grid_alignment_t1_lines"
Y_T1_LABELS_PART_NAME = "absolute_y_t1_grid_alignment_t0_labels"

T0_COLOR = (0.95, 0.08, 0.04)
T1_COLOR = (0.0, 0.32, 1.0)

CALIBRATION_PART_METADATA = {
    X_T0_PART_NAME: {
        "production_group": X_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    },
    X_T1_PART_NAME: {
        "production_group": X_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    },
    Y_T0_LINES_PART_NAME: {
        "production_group": Y_T0_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    },
    Y_T0_LABELS_PART_NAME: {
        "production_group": Y_T0_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    },
    Y_T1_LINES_PART_NAME: {
        "production_group": Y_T1_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    },
    Y_T1_LABELS_PART_NAME: {
        "production_group": Y_T1_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    },
}


def read_grid_calibration(calib_path=CALIB_PATH):
    calibration = yaml.safe_load(calib_path.read_text(encoding="utf-8"))
    tools = calibration["tools"]
    t0 = tools["t0"]
    t1 = tools["t1"]

    return {
        "bed_grid_zero": (
            float(calibration["bed_grid_zero"]["x"]),
            float(calibration["bed_grid_zero"]["y"]),
        ),
        "t0_x_endstop": float(t0["x_endstop"]),
        "t1_x_endstop": float(t1["x_endstop"]),
        "t0_y_endstop": float(t0["y_endstop"]),
        "t1_y_endstop": float(t1["y_endstop"]),
    }


def grid_coordinate(zero_mm, index):
    return round(zero_mm + index * GRID_PITCH_MM, 4)


def create_grid_cutouts(bed_grid_zero):
    zero_x_mm, zero_y_mm = bed_grid_zero
    return (
        {
            "name": "kingroon_logo_panel_outline",
            "x_min": grid_coordinate(zero_x_mm, -3),
            "x_max": grid_coordinate(zero_x_mm, 4),
            "y_min": grid_coordinate(zero_y_mm, 1),
            "y_max": grid_coordinate(zero_y_mm, 3),
            "fillet_radius": 7.0,
        },
        {
            "name": "z_guide_panel_outline",
            "x_min": grid_coordinate(zero_x_mm, -4),
            "x_max": grid_coordinate(zero_x_mm, 5),
            "y_min": grid_coordinate(zero_y_mm, -2.5),
            "y_max": grid_coordinate(zero_y_mm, -1.5),
            "fillet_radius": 7.0,
        },
    )


def subtract_intervals(start_mm, end_mm, blocked_intervals):
    open_intervals = []
    cursor_mm = start_mm

    for blocked_start_mm, blocked_end_mm in sorted(blocked_intervals):
        blocked_start_mm = max(start_mm, blocked_start_mm)
        blocked_end_mm = min(end_mm, blocked_end_mm)
        if blocked_end_mm <= cursor_mm:
            continue

        if blocked_start_mm > cursor_mm:
            open_intervals.append((cursor_mm, blocked_start_mm))
        cursor_mm = max(cursor_mm, blocked_end_mm)

    if cursor_mm < end_mm:
        open_intervals.append((cursor_mm, end_mm))

    return tuple(
        (segment_start_mm, segment_end_mm)
        for segment_start_mm, segment_end_mm in open_intervals
        if segment_end_mm - segment_start_mm > 0.1
    )


def create_painted_bed_grid_lines(bed_grid_zero):
    zero_x_mm, zero_y_mm = bed_grid_zero
    x_positions_mm = tuple(
        grid_coordinate(zero_x_mm, index)
        for index in range(GRID_X_INDEX_MIN, GRID_X_INDEX_MAX + 1)
    )
    y_positions_mm = tuple(
        grid_coordinate(zero_y_mm, index)
        for index in range(GRID_Y_INDEX_MIN, GRID_Y_INDEX_MAX + 1)
    )
    min_x_mm = min(x_positions_mm) - GRID_LINE_OVERHANG_MM
    min_y_mm = min(y_positions_mm) - GRID_LINE_OVERHANG_MM
    max_x_mm = max(x_positions_mm) + GRID_LINE_OVERHANG_MM
    max_y_mm = max(y_positions_mm) + GRID_LINE_OVERHANG_MM
    grid_cutouts = create_grid_cutouts(bed_grid_zero)

    collector = PartCollector()
    for x_mm in x_positions_mm:
        half_width = GRID_LINE_WIDTH_MM / 2 + GRID_CUTOUT_MARGIN_MM
        blocked_intervals = (
            (
                cutout["y_min"] - GRID_CUTOUT_MARGIN_MM,
                cutout["y_max"] + GRID_CUTOUT_MARGIN_MM,
            )
            for cutout in grid_cutouts
            if cutout["x_min"] - half_width <= x_mm <= cutout["x_max"] + half_width
        )
        for segment_start_mm, segment_end_mm in subtract_intervals(
            min_y_mm, max_y_mm, blocked_intervals
        ):
            collector = collector.fuse(
                create_box(
                    GRID_LINE_WIDTH_MM,
                    segment_end_mm - segment_start_mm,
                    GRID_LINE_HEIGHT_MM,
                    origin=(
                        x_mm - GRID_LINE_WIDTH_MM / 2,
                        segment_start_mm,
                        0,
                    ),
                )
            )

    for y_mm in y_positions_mm:
        half_width = GRID_LINE_WIDTH_MM / 2 + GRID_CUTOUT_MARGIN_MM
        blocked_intervals = (
            (
                cutout["x_min"] - GRID_CUTOUT_MARGIN_MM,
                cutout["x_max"] + GRID_CUTOUT_MARGIN_MM,
            )
            for cutout in grid_cutouts
            if cutout["y_min"] - half_width <= y_mm <= cutout["y_max"] + half_width
        )
        for segment_start_mm, segment_end_mm in subtract_intervals(
            min_x_mm, max_x_mm, blocked_intervals
        ):
            collector = collector.fuse(
                create_box(
                    segment_end_mm - segment_start_mm,
                    GRID_LINE_WIDTH_MM,
                    GRID_LINE_HEIGHT_MM,
                    origin=(
                        segment_start_mm,
                        y_mm - GRID_LINE_WIDTH_MM / 2,
                        0,
                    ),
                )
            )

    return collector


def create_filleted_outline(
    width_mm,
    depth_mm,
    *,
    line_width_mm,
    height_mm,
    fillet_radius_mm,
    origin,
):
    frame = create_filleted_box(
        width_mm,
        depth_mm,
        height_mm,
        fillet_radius=fillet_radius_mm,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    frame_cutter = create_filleted_box(
        width_mm - 2 * line_width_mm,
        depth_mm - 2 * line_width_mm,
        height_mm * 4,
        fillet_radius=max(0.01, fillet_radius_mm - line_width_mm),
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    frame_cutter = align(frame_cutter, frame, Alignment.CENTER)
    frame = frame.cut(frame_cutter)
    return translate(origin[0], origin[1], origin[2])(frame)


def format_endpoint_label(endpoint_mm):
    rounded_endpoint_mm = round(endpoint_mm, 1)
    if rounded_endpoint_mm == 0:
        rounded_endpoint_mm = 0.0
    return f"{rounded_endpoint_mm:.1f}"


def create_calibration_vector_label(text):
    label = create_vector_text_object(
        text,
        size=CALIBRATION_LABEL_SIZE_MM,
        thickness=CALIBRATION_LABEL_TEXT_THICKNESS_MM,
        stroke_width=CALIBRATION_LABEL_STROKE_WIDTH_MM,
    )
    return rotate(45, center=get_bounding_box_center(label))(label)


def create_calibration_label_below(text, center_x_mm, top_y_mm):
    label = create_calibration_vector_label(text)
    min_point, max_point = get_bounding_box(label)
    center_x = (min_point[0] + max_point[0]) / 2
    return translate(center_x_mm - center_x, top_y_mm - max_point[1], 0)(label)


def create_calibration_label_left(
    text,
    right_x_mm,
    center_y_mm,
    *,
    min_y_mm=None,
    max_y_mm=None,
):
    label = create_calibration_vector_label(text)
    min_point, max_point = get_bounding_box(label)
    center_y = (min_point[1] + max_point[1]) / 2
    label = translate(right_x_mm - max_point[0], center_y_mm - center_y, 0)(label)

    min_point, max_point = get_bounding_box(label)
    shift_y_mm = 0.0
    if min_y_mm is not None and min_point[1] < min_y_mm:
        shift_y_mm = max(shift_y_mm, min_y_mm - min_point[1])
    if max_y_mm is not None and max_point[1] + shift_y_mm > max_y_mm:
        shift_y_mm = min(shift_y_mm, max_y_mm - max_point[1])
    if shift_y_mm:
        label = translate(0, shift_y_mm, 0)(label)

    return label


def create_calibration_label_slab(labels):
    min_x = (
        min(get_bounding_box(label)[0][0] for label in labels)
        - CALIBRATION_LABEL_PAD_MARGIN_MM
    )
    min_y = (
        min(get_bounding_box(label)[0][1] for label in labels)
        - CALIBRATION_LABEL_PAD_MARGIN_MM
    )
    max_x = (
        max(get_bounding_box(label)[1][0] for label in labels)
        + CALIBRATION_LABEL_PAD_MARGIN_MM
    )
    max_y = (
        max(get_bounding_box(label)[1][1] for label in labels)
        + CALIBRATION_LABEL_PAD_MARGIN_MM
    )
    return (
        create_box(
            max_x - min_x,
            max_y - min_y,
            CALIBRATION_LABEL_PAD_THICKNESS_MM,
            origin=(min_x, min_y, 0),
        ),
        (min_x, min_y, max_x, max_y),
    )


def create_absolute_x_alignment_pattern(
    *,
    bed_grid_zero,
    x_endstop_mm,
    line_y_min_mm,
    line_y_max_mm,
    label_panel,
):
    zero_x_mm, _ = bed_grid_zero
    label_top_y_mm = label_panel["y_max"] - CALIBRATION_LABEL_GAP_MM
    base_collector = PartCollector()
    label_collector = PartCollector()
    label_entries = []

    for grid_index, offset_mm in zip(
        range(CALIBRATION_GRID_X_INDEX_MIN, CALIBRATION_GRID_X_INDEX_MAX + 1),
        CALIBRATION_OFFSET_CANDIDATES_MM,
    ):
        painted_grid_x_mm = grid_coordinate(zero_x_mm, grid_index)
        line_center_x_mm = painted_grid_x_mm - offset_mm
        base_collector = base_collector.fuse(
            create_box(
                CALIBRATION_LINE_WIDTH_MM,
                line_y_max_mm - line_y_min_mm,
                CALIBRATION_HEIGHT_MM,
                origin=(
                    line_center_x_mm - CALIBRATION_LINE_WIDTH_MM / 2,
                    line_y_min_mm,
                    0,
                ),
            )
        )

        label_entries.append(
            {
                "label": create_calibration_label_below(
                    format_endpoint_label(x_endstop_mm + offset_mm),
                    line_center_x_mm,
                    label_top_y_mm,
                ),
                "center_x_mm": line_center_x_mm,
            }
        )

    labels = [entry["label"] for entry in label_entries]
    slab, (_, _, _, slab_max_y) = create_calibration_label_slab(labels)
    base_collector = base_collector.fuse(slab)

    for label in labels:
        label_collector = label_collector.fuse(align(label, slab, Alignment.STACK_TOP))

    for entry in label_entries:
        connector_start_y = slab_max_y - CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM
        connector_end_y = line_y_min_mm + CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM
        min_y = min(connector_start_y, connector_end_y)
        max_y = max(connector_start_y, connector_end_y)
        base_collector = base_collector.fuse(
            create_box(
                CALIBRATION_LABEL_CONNECTOR_WIDTH_MM,
                max_y - min_y,
                CALIBRATION_LABEL_PAD_THICKNESS_MM,
                origin=(
                    entry["center_x_mm"] - CALIBRATION_LABEL_CONNECTOR_WIDTH_MM / 2,
                    min_y,
                    0,
                ),
            )
        )

    return base_collector, label_collector


def create_absolute_x_alignment_materials(calibration):
    bed_grid_zero = calibration["bed_grid_zero"]
    _, zero_y_mm = bed_grid_zero
    grid_cutouts = create_grid_cutouts(bed_grid_zero)
    logo_panel = next(
        cutout
        for cutout in grid_cutouts
        if cutout["name"] == "kingroon_logo_panel_outline"
    )
    lower_panel = next(
        cutout for cutout in grid_cutouts if cutout["name"] == "z_guide_panel_outline"
    )

    t0_pattern, t0_labels = create_absolute_x_alignment_pattern(
        bed_grid_zero=bed_grid_zero,
        x_endstop_mm=calibration["t0_x_endstop"],
        line_y_min_mm=grid_coordinate(zero_y_mm, -1),
        line_y_max_mm=grid_coordinate(zero_y_mm, 0),
        label_panel=lower_panel,
    )
    t1_pattern, t1_labels = create_absolute_x_alignment_pattern(
        bed_grid_zero=bed_grid_zero,
        x_endstop_mm=calibration["t1_x_endstop"],
        line_y_min_mm=grid_coordinate(zero_y_mm, 3),
        line_y_max_mm=grid_coordinate(zero_y_mm, 4),
        label_panel=logo_panel,
    )

    t0_material = PartCollector()
    t0_material = t0_material.fuse(t0_pattern)
    t0_material = t0_material.fuse(t1_labels)

    t1_material = PartCollector()
    t1_material = t1_material.fuse(t1_pattern)
    t1_material = t1_material.fuse(t0_labels)

    return t0_material, t1_material


def y_line_center_for_calibration_offset(painted_grid_y_mm, offset_mm):
    return painted_grid_y_mm - offset_mm


def create_absolute_y_alignment_materials(
    *,
    bed_grid_zero,
    calibration_value_mm,
):
    zero_x_mm, zero_y_mm = bed_grid_zero
    label_right_x_mm = grid_coordinate(zero_x_mm, -2) - CALIBRATION_LABEL_GAP_MM
    label_min_y_mm = SAFE_BED_ORIGIN[1] + CALIBRATION_LABEL_PAD_MARGIN_MM
    label_max_y_mm = (
        SAFE_BED_ORIGIN[1] + SAFE_BED_DEPTH_MM - CALIBRATION_LABEL_PAD_MARGIN_MM
    )
    base_collector = PartCollector()
    text_collector = PartCollector()
    label_entries = []

    for grid_index, offset_mm in zip(
        range(CALIBRATION_GRID_Y_INDEX_MIN, CALIBRATION_GRID_Y_INDEX_MAX + 1),
        CALIBRATION_OFFSET_CANDIDATES_MM,
    ):
        painted_grid_y_mm = grid_coordinate(zero_y_mm, grid_index)
        line_center_y_mm = y_line_center_for_calibration_offset(
            painted_grid_y_mm,
            offset_mm,
        )
        label_entries.append(
            {
                "label": create_calibration_label_left(
                    format_endpoint_label(calibration_value_mm + offset_mm),
                    label_right_x_mm,
                    line_center_y_mm,
                    min_y_mm=label_min_y_mm,
                    max_y_mm=label_max_y_mm,
                ),
                "center_y_mm": line_center_y_mm,
            }
        )

    labels = [entry["label"] for entry in label_entries]
    slab, (slab_min_x, slab_min_y, slab_max_x, _) = create_calibration_label_slab(
        labels
    )
    line_x_min_mm = max(
        SAFE_BED_ORIGIN[0],
        slab_min_x - 2 * GRID_PITCH_MM + CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM,
    )
    line_x_max_mm = line_x_min_mm + GRID_PITCH_MM
    base_collector = base_collector.fuse(slab)
    for label in labels:
        text_collector = text_collector.fuse(align(label, slab, Alignment.STACK_TOP))

    grounding_marker_y_mm = (
        slab_min_y
        - CALIBRATION_LABEL_GROUNDING_MARKER_GAP_MM
        - CALIBRATION_LABEL_GROUNDING_MARKER_SIZE_MM
    )
    if grounding_marker_y_mm < SAFE_BED_ORIGIN[1]:
        raise ValueError(
            "Y label grounding marker does not fit below the label slab: "
            f"marker_y={grounding_marker_y_mm}, safe_y={SAFE_BED_ORIGIN[1]}"
        )
    text_collector = text_collector.fuse(
        create_box(
            CALIBRATION_LABEL_GROUNDING_MARKER_SIZE_MM,
            CALIBRATION_LABEL_GROUNDING_MARKER_SIZE_MM,
            CALIBRATION_LABEL_PAD_THICKNESS_MM,
            origin=(
                slab_min_x + CALIBRATION_LABEL_PAD_MARGIN_MM,
                grounding_marker_y_mm,
                0,
            ),
        )
    )

    for entry in label_entries:
        base_collector = base_collector.fuse(
            create_box(
                line_x_max_mm - line_x_min_mm,
                CALIBRATION_LINE_WIDTH_MM,
                CALIBRATION_HEIGHT_MM,
                origin=(
                    line_x_min_mm,
                    entry["center_y_mm"] - CALIBRATION_LINE_WIDTH_MM / 2,
                    0,
                ),
            )
        )
        connector_start_x_mm = line_x_max_mm - CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM
        connector_end_x_mm = slab_min_x + CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM
        start_x_mm = min(connector_start_x_mm, connector_end_x_mm)
        end_x_mm = max(connector_start_x_mm, connector_end_x_mm)
        base_collector = base_collector.fuse(
            create_box(
                end_x_mm - start_x_mm,
                CALIBRATION_LABEL_CONNECTOR_WIDTH_MM,
                CALIBRATION_LABEL_PAD_THICKNESS_MM,
                origin=(
                    start_x_mm,
                    entry["center_y_mm"] - CALIBRATION_LABEL_CONNECTOR_WIDTH_MM / 2,
                    0,
                ),
            )
        )

    return base_collector, text_collector


def assert_absolute_patterns_fit_dual_area(parts):
    tolerance_mm = 1e-6
    min_x = min(get_bounding_box(part)[0][0] for part in parts)
    min_y = min(get_bounding_box(part)[0][1] for part in parts)
    max_x = max(get_bounding_box(part)[1][0] for part in parts)
    max_y = max(get_bounding_box(part)[1][1] for part in parts)
    width = max_x - SAFE_BED_ORIGIN[0]
    depth = max_y - SAFE_BED_ORIGIN[1]
    if (
        min_x < SAFE_BED_ORIGIN[0] - tolerance_mm
        or min_y < SAFE_BED_ORIGIN[1] - tolerance_mm
    ):
        raise ValueError(
            "Absolute alignment pattern starts outside the dual-safe area: "
            f"min=({min_x}, {min_y}), origin={SAFE_BED_ORIGIN}"
        )
    if (
        width > SAFE_BED_WIDTH_MM + tolerance_mm
        or depth > SAFE_BED_DEPTH_MM + tolerance_mm
    ):
        raise ValueError(
            "Absolute alignment pattern does not fit the dual-safe area: "
            f"bounds=(({min_x}, {min_y}), ({max_x}, {max_y})), "
            f"bed=({SAFE_BED_WIDTH_MM}, {SAFE_BED_DEPTH_MM})"
        )


def add_painted_bed_preview_parts(parts, plate_prefix, bed_grid_zero):
    preview_part_names = []

    def add_preview_part(part, name, color):
        preview_name = f"{plate_prefix}_{name}"
        parts.add(part, preview_name, color=color, skip_in_production=True)
        preview_part_names.append(preview_name)

    bed_surface = create_box(
        ACTUAL_BED_WIDTH_MM,
        ACTUAL_BED_DEPTH_MM,
        ACTUAL_BED_HEIGHT_MM,
        origin=(
            ACTUAL_BED_ORIGIN_X_MM,
            ACTUAL_BED_ORIGIN_Y_MM,
            -ACTUAL_BED_HEIGHT_MM,
        ),
    )
    add_preview_part(
        translate(0, 0, -0.05)(bed_surface),
        "painted_bed_surface",
        ACTUAL_BED_COLOR,
    )
    add_preview_part(
        create_painted_bed_grid_lines(bed_grid_zero),
        "painted_bed_grid_1in",
        GRID_LINE_COLOR,
    )
    add_preview_part(
        create_filleted_outline(
            PAINTED_FRAME_SIZE_MM,
            PAINTED_FRAME_SIZE_MM,
            line_width_mm=PAINTED_FRAME_LINE_WIDTH_MM,
            height_mm=PAINTED_FRAME_HEIGHT_MM,
            fillet_radius_mm=PAINTED_FRAME_FILLET_RADIUS_MM,
            origin=(PAINTED_FRAME_ORIGIN_X_MM, PAINTED_FRAME_ORIGIN_Y_MM, 0),
        ),
        "painted_bed_frame",
        PAINTED_FRAME_COLOR,
    )

    for cutout in create_grid_cutouts(bed_grid_zero):
        if not cutout["name"].endswith("_outline"):
            continue
        add_preview_part(
            create_filleted_outline(
                cutout["x_max"] - cutout["x_min"],
                cutout["y_max"] - cutout["y_min"],
                line_width_mm=PANEL_OUTLINE_WIDTH_MM,
                height_mm=PANEL_OUTLINE_HEIGHT_MM,
                fillet_radius_mm=cutout["fillet_radius"],
                origin=(cutout["x_min"], cutout["y_min"], 0),
            ),
            cutout["name"],
            PANEL_OUTLINE_COLOR,
        )

    return tuple(preview_part_names)


def create_plate_definitions(preview_part_names_by_plate=None):
    if preview_part_names_by_plate is None:
        preview_part_names_by_plate = {}

    return [
        {
            "name": X_PLATE_NAME,
            "parts": [
                *preview_part_names_by_plate.get(X_PLATE_NAME, ()),
                X_T0_PART_NAME,
                X_T1_PART_NAME,
            ],
        },
        {
            "name": Y_T0_PLATE_NAME,
            "parts": [
                *preview_part_names_by_plate.get(Y_T0_PLATE_NAME, ()),
                Y_T0_LINES_PART_NAME,
                Y_T0_LABELS_PART_NAME,
            ],
        },
        {
            "name": Y_T1_PLATE_NAME,
            "parts": [
                *preview_part_names_by_plate.get(Y_T1_PLATE_NAME, ()),
                Y_T1_LINES_PART_NAME,
                Y_T1_LABELS_PART_NAME,
            ],
        },
    ]


def add_calibration_part(parts, part, name, color):
    parts.add(
        part,
        name,
        color=color,
        obj_metadata=CALIBRATION_PART_METADATA[name],
    )


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()
    calibration = read_grid_calibration()
    bed_grid_zero = calibration["bed_grid_zero"]
    preview_part_names_by_plate = {}

    if not PROD:
        preview_part_names_by_plate = {
            X_PLATE_NAME: add_painted_bed_preview_parts(
                parts,
                "x_plate",
                bed_grid_zero,
            ),
            Y_T0_PLATE_NAME: add_painted_bed_preview_parts(
                parts,
                "y_t0_plate",
                bed_grid_zero,
            ),
            Y_T1_PLATE_NAME: add_painted_bed_preview_parts(
                parts,
                "y_t1_plate",
                bed_grid_zero,
            ),
        }

    x_t0_alignment, x_t1_alignment = create_absolute_x_alignment_materials(calibration)
    y_t0_lines, y_t0_labels = create_absolute_y_alignment_materials(
        bed_grid_zero=bed_grid_zero,
        calibration_value_mm=calibration["t0_y_endstop"],
    )
    y_t1_lines, y_t1_labels = create_absolute_y_alignment_materials(
        bed_grid_zero=bed_grid_zero,
        calibration_value_mm=calibration["t1_y_endstop"],
    )
    assert_absolute_patterns_fit_dual_area(
        [
            x_t0_alignment,
            x_t1_alignment,
            y_t0_lines,
            y_t0_labels,
            y_t1_lines,
            y_t1_labels,
        ]
    )

    add_calibration_part(parts, x_t0_alignment, X_T0_PART_NAME, T0_COLOR)
    add_calibration_part(parts, x_t1_alignment, X_T1_PART_NAME, T1_COLOR)
    add_calibration_part(parts, y_t0_lines, Y_T0_LINES_PART_NAME, T0_COLOR)
    add_calibration_part(parts, y_t0_labels, Y_T0_LABELS_PART_NAME, T1_COLOR)
    add_calibration_part(parts, y_t1_lines, Y_T1_LINES_PART_NAME, T1_COLOR)
    add_calibration_part(parts, y_t1_labels, Y_T1_LABELS_PART_NAME, T0_COLOR)

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=(
            copy_dual_pla_04_offset_calibration_process_data() if PROD else None
        ),
        prod_gap=4,
        bed_width=SAFE_BED_WIDTH_MM if PROD else ACTUAL_BED_WIDTH_MM,
        bed_depth=SAFE_BED_DEPTH_MM if PROD else ACTUAL_BED_DEPTH_MM,
        prod_origin=(
            SAFE_BED_ORIGIN
            if PROD
            else (ACTUAL_BED_ORIGIN_X_MM, ACTUAL_BED_ORIGIN_Y_MM)
        ),
        preserve_model_coordinates=PROD,
        plates=create_plate_definitions(preview_part_names_by_plate),
    )

    _logger.info("two-material absolute X/Y grid alignment calibration completed.")


if __name__ == "__main__":
    main()
