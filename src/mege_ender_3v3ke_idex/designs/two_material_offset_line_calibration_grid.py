"""Two-material IDEX absolute X/Y calibration against the painted bed grid.

Usage:
    cd <project_root> && ./run.sh path/to/two_material_offset_line_calibration_grid.py
    cd <project_root> && ./run.sh --slice path/to/two_material_offset_line_calibration_grid.py
"""

import logging
import os
import re
from pathlib import Path

from mege_3devops.process_data.mege_ender_3v3ke_idex import (
    SAFE_BED_DEPTH_MM,
    SAFE_BED_ORIGIN,
    SAFE_BED_WIDTH_MM,
    copy_dual_pla_04_offset_calibration_process_data,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "klipper_setup"
    / "klipper_config"
    / "printer.cfg"
)
STEPPER_X_SECTION = "stepper_x"
STEPPER_Y_SECTION = "stepper_y"
DUAL_CARRIAGE_SECTION = "dual_carriage"
TOOL_STATE_SECTION = "gcode_macro _IDEX_TOOL_STATE"

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

X_T0_PART_NAME = "absolute_x_grid_alignment_t0"
X_T1_PART_NAME = "absolute_x_grid_alignment_t1"
Y_T0_PART_NAME = "absolute_y_grid_alignment_t0"
Y_T1_PART_NAME = "absolute_y_grid_alignment_t1"

T0_COLOR = (0.95, 0.08, 0.04)
T1_COLOR = (0.0, 0.32, 1.0)


def get_config_section(config_text, section_name):
    match = re.search(
        rf"^\[{re.escape(section_name)}\]\n(?P<body>.*?)(?=^\[|\Z)",
        config_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise ValueError(f"Missing [{section_name}] section in Klipper config")
    return match.group("body")


def parse_tool_state_float(tool_state_section, variable_name):
    match = re.search(
        rf"^\s*variable_{re.escape(variable_name)}\s*:\s*(?P<value>\S+)\s*$",
        tool_state_section,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError(f"Missing variable_{variable_name} in _IDEX_TOOL_STATE")

    try:
        return float(match.group("value"))
    except ValueError:
        raise ValueError(f"variable_{variable_name} must be numeric") from None


def parse_config_float(section, section_name, setting_name):
    match = re.search(
        rf"^\s*{re.escape(setting_name)}\s*:\s*(?P<value>\S+)\s*$",
        section,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError(f"Missing {setting_name} in [{section_name}]")

    try:
        return float(match.group("value"))
    except ValueError:
        raise ValueError(
            f"{setting_name} in [{section_name}] must be numeric"
        ) from None


def parse_bed_grid_zero(config_text):
    tool_state = get_config_section(config_text, TOOL_STATE_SECTION)
    return (
        parse_tool_state_float(tool_state, "bed_grid_zero_x"),
        parse_tool_state_float(tool_state, "bed_grid_zero_y"),
    )


def read_bed_grid_zero(config_path=CONFIG_PATH):
    return parse_bed_grid_zero(config_path.read_text(encoding="utf-8"))


def parse_x_endstop_values(config_text):
    stepper_x = get_config_section(config_text, STEPPER_X_SECTION)
    dual_carriage = get_config_section(config_text, DUAL_CARRIAGE_SECTION)

    t0_x_endstop = parse_config_float(
        stepper_x,
        STEPPER_X_SECTION,
        "position_endstop",
    )
    t1_x_endstop = parse_config_float(
        dual_carriage,
        DUAL_CARRIAGE_SECTION,
        "position_endstop",
    )
    t1_x_max = parse_config_float(
        dual_carriage,
        DUAL_CARRIAGE_SECTION,
        "position_max",
    )
    if abs(t1_x_endstop - t1_x_max) > 1e-9:
        raise ValueError(
            "[dual_carriage] position_endstop and position_max must stay equal "
            "for right-endstop X calibration labels"
        )

    return {
        "t0_x_endstop": t0_x_endstop,
        "t1_x_endstop": t1_x_endstop,
    }


def read_x_endstop_values(config_path=CONFIG_PATH):
    return parse_x_endstop_values(config_path.read_text(encoding="utf-8"))


def parse_y_calibration_values(config_text):
    stepper_y = get_config_section(config_text, STEPPER_Y_SECTION)
    tool_state = get_config_section(config_text, TOOL_STATE_SECTION)

    return {
        "t0_y_endstop": parse_config_float(
            stepper_y,
            STEPPER_Y_SECTION,
            "position_endstop",
        ),
        "t1_y_offset": parse_tool_state_float(tool_state, "t1_y_offset"),
    }


def read_y_calibration_values(config_path=CONFIG_PATH):
    return parse_y_calibration_values(config_path.read_text(encoding="utf-8"))


def grid_coordinate(zero_mm, index):
    return round(zero_mm + index * GRID_PITCH_MM, 4)


def grid_positions_by_index(zero_mm, first_index, last_index):
    return tuple(
        grid_coordinate(zero_mm, index) for index in range(first_index, last_index + 1)
    )


def create_grid_cutouts(bed_grid_zero):
    zero_x_mm, zero_y_mm = bed_grid_zero

    def x(index):
        return grid_coordinate(zero_x_mm, index)

    def y(index):
        return grid_coordinate(zero_y_mm, index)

    return (
        {
            "name": "kingroon_logo_panel_outline",
            "x_min": x(-3),
            "x_max": x(4),
            "y_min": y(1),
            "y_max": y(3),
            "fillet_radius": 7.0,
        },
        {
            "name": "z_guide_panel_outline",
            "x_min": x(-4),
            "x_max": x(5),
            "y_min": y(-2.5),
            "y_max": y(-1.5),
            "fillet_radius": 7.0,
        },
    )


def visible_panel_cutouts(grid_cutouts):
    return tuple(
        cutout for cutout in grid_cutouts if cutout["name"].endswith("_outline")
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


def cutout_intersects_x(cutout, center_x_mm):
    half_line_width_mm = GRID_LINE_WIDTH_MM / 2 + GRID_CUTOUT_MARGIN_MM
    return (
        cutout["x_min"] - half_line_width_mm
        <= center_x_mm
        <= cutout["x_max"] + half_line_width_mm
    )


def cutout_intersects_y(cutout, center_y_mm):
    half_line_width_mm = GRID_LINE_WIDTH_MM / 2 + GRID_CUTOUT_MARGIN_MM
    return (
        cutout["y_min"] - half_line_width_mm
        <= center_y_mm
        <= cutout["y_max"] + half_line_width_mm
    )


def create_vertical_grid_line_segment(center_x_mm, min_y_mm, max_y_mm):
    return create_box(
        GRID_LINE_WIDTH_MM,
        max_y_mm - min_y_mm,
        GRID_LINE_HEIGHT_MM,
        origin=(center_x_mm - GRID_LINE_WIDTH_MM / 2, min_y_mm, 0),
    )


def create_horizontal_grid_line_segment(center_y_mm, min_x_mm, max_x_mm):
    return create_box(
        max_x_mm - min_x_mm,
        GRID_LINE_WIDTH_MM,
        GRID_LINE_HEIGHT_MM,
        origin=(min_x_mm, center_y_mm - GRID_LINE_WIDTH_MM / 2, 0),
    )


def create_painted_bed_grid_lines(bed_grid_zero=None):
    if bed_grid_zero is None:
        bed_grid_zero = read_bed_grid_zero()

    zero_x_mm, zero_y_mm = bed_grid_zero
    x_positions_mm = grid_positions_by_index(
        zero_x_mm, GRID_X_INDEX_MIN, GRID_X_INDEX_MAX
    )
    y_positions_mm = grid_positions_by_index(
        zero_y_mm, GRID_Y_INDEX_MIN, GRID_Y_INDEX_MAX
    )
    min_x_mm = min(x_positions_mm) - GRID_LINE_OVERHANG_MM
    min_y_mm = min(y_positions_mm) - GRID_LINE_OVERHANG_MM
    max_x_mm = max(x_positions_mm) + GRID_LINE_OVERHANG_MM
    max_y_mm = max(y_positions_mm) + GRID_LINE_OVERHANG_MM
    grid_cutouts = create_grid_cutouts(bed_grid_zero)

    collector = PartCollector()
    for x_mm in x_positions_mm:
        blocked_intervals = (
            (
                cutout["y_min"] - GRID_CUTOUT_MARGIN_MM,
                cutout["y_max"] + GRID_CUTOUT_MARGIN_MM,
            )
            for cutout in grid_cutouts
            if cutout_intersects_x(cutout, x_mm)
        )
        for segment_start_mm, segment_end_mm in subtract_intervals(
            min_y_mm, max_y_mm, blocked_intervals
        ):
            collector = collector.fuse(
                create_vertical_grid_line_segment(
                    x_mm, segment_start_mm, segment_end_mm
                )
            )

    for y_mm in y_positions_mm:
        blocked_intervals = (
            (
                cutout["x_min"] - GRID_CUTOUT_MARGIN_MM,
                cutout["x_max"] + GRID_CUTOUT_MARGIN_MM,
            )
            for cutout in grid_cutouts
            if cutout_intersects_y(cutout, y_mm)
        )
        for segment_start_mm, segment_end_mm in subtract_intervals(
            min_x_mm, max_x_mm, blocked_intervals
        ):
            collector = collector.fuse(
                create_horizontal_grid_line_segment(
                    y_mm, segment_start_mm, segment_end_mm
                )
            )

    return collector


def create_bed_surface():
    retval = create_box(
        ACTUAL_BED_WIDTH_MM,
        ACTUAL_BED_DEPTH_MM,
        ACTUAL_BED_HEIGHT_MM,
        origin=(
            ACTUAL_BED_ORIGIN_X_MM,
            ACTUAL_BED_ORIGIN_Y_MM,
            -ACTUAL_BED_HEIGHT_MM,
        ),
    )
    retval = translate(0, 0, -0.05)(retval)
    return retval


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
    inner_width_mm = width_mm - 2 * line_width_mm
    inner_depth_mm = depth_mm - 2 * line_width_mm
    inner_radius_mm = max(0.01, fillet_radius_mm - line_width_mm)
    frame_cutter = create_filleted_box(
        inner_width_mm,
        inner_depth_mm,
        height_mm * 4,
        fillet_radius=inner_radius_mm,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    frame_cutter = align(frame_cutter, frame, Alignment.CENTER)
    frame = frame.cut(frame_cutter)
    return translate(origin[0], origin[1], origin[2])(frame)


def create_frame():
    return create_filleted_outline(
        PAINTED_FRAME_SIZE_MM,
        PAINTED_FRAME_SIZE_MM,
        line_width_mm=PAINTED_FRAME_LINE_WIDTH_MM,
        height_mm=PAINTED_FRAME_HEIGHT_MM,
        fillet_radius_mm=PAINTED_FRAME_FILLET_RADIUS_MM,
        origin=(PAINTED_FRAME_ORIGIN_X_MM, PAINTED_FRAME_ORIGIN_Y_MM, 0),
    )


def create_panel_outline(cutout):
    return create_filleted_outline(
        cutout["x_max"] - cutout["x_min"],
        cutout["y_max"] - cutout["y_min"],
        line_width_mm=PANEL_OUTLINE_WIDTH_MM,
        height_mm=PANEL_OUTLINE_HEIGHT_MM,
        fillet_radius_mm=cutout["fillet_radius"],
        origin=(cutout["x_min"], cutout["y_min"], 0),
    )


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

    bb_center = get_bounding_box_center(label)
    return rotate(45, center=bb_center)(label)


def create_calibration_label_below(text, center_x_mm, top_y_mm):
    label = create_calibration_vector_label(text)
    min_point, max_point = get_bounding_box(label)
    center_x = (min_point[0] + max_point[0]) / 2
    return translate(
        center_x_mm - center_x,
        top_y_mm - max_point[1],
        0,
    )(label)


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
    label = translate(
        right_x_mm - max_point[0],
        center_y_mm - center_y,
        0,
    )(label)

    min_point, max_point = get_bounding_box(label)
    shift_y_mm = 0.0
    if min_y_mm is not None and min_point[1] < min_y_mm:
        shift_y_mm = max(shift_y_mm, min_y_mm - min_point[1])
    if max_y_mm is not None and max_point[1] + shift_y_mm > max_y_mm:
        shift_y_mm = min(shift_y_mm, max_y_mm - max_point[1])
    if shift_y_mm:
        label = translate(0, shift_y_mm, 0)(label)

    return label


def create_calibration_vertical_segment(center_x_mm, y_min_mm, y_max_mm):
    return create_box(
        CALIBRATION_LINE_WIDTH_MM,
        y_max_mm - y_min_mm,
        CALIBRATION_HEIGHT_MM,
        origin=(center_x_mm - CALIBRATION_LINE_WIDTH_MM / 2, y_min_mm, 0),
    )


def create_calibration_horizontal_segment(center_y_mm, x_min_mm, x_max_mm):
    return create_box(
        x_max_mm - x_min_mm,
        CALIBRATION_LINE_WIDTH_MM,
        CALIBRATION_HEIGHT_MM,
        origin=(x_min_mm, center_y_mm - CALIBRATION_LINE_WIDTH_MM / 2, 0),
    )


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

    slab = create_box(
        max_x - min_x,
        max_y - min_y,
        CALIBRATION_LABEL_PAD_THICKNESS_MM,
        origin=(min_x, min_y, 0),
    )
    return slab, (min_x, min_y, max_x, max_y)


def create_calibration_label_connector(center_x_mm, start_y_mm, end_y_mm):
    min_y = min(start_y_mm, end_y_mm)
    max_y = max(start_y_mm, end_y_mm)
    return create_box(
        CALIBRATION_LABEL_CONNECTOR_WIDTH_MM,
        max_y - min_y,
        CALIBRATION_LABEL_PAD_THICKNESS_MM,
        origin=(center_x_mm - CALIBRATION_LABEL_CONNECTOR_WIDTH_MM / 2, min_y, 0),
    )


def create_calibration_label_horizontal_connector(start_x_mm, end_x_mm, center_y_mm):
    min_x = min(start_x_mm, end_x_mm)
    max_x = max(start_x_mm, end_x_mm)
    return create_box(
        max_x - min_x,
        CALIBRATION_LABEL_CONNECTOR_WIDTH_MM,
        CALIBRATION_LABEL_PAD_THICKNESS_MM,
        origin=(min_x, center_y_mm - CALIBRATION_LABEL_CONNECTOR_WIDTH_MM / 2, 0),
    )


def fuse_labels_stacked_on_slab(label_collector, labels, slab):
    for label in labels:
        label_collector = label_collector.fuse(align(label, slab, Alignment.STACK_TOP))
    return label_collector


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
            create_calibration_vertical_segment(
                line_center_x_mm,
                line_y_min_mm,
                line_y_max_mm,
            )
        )

        label = create_calibration_label_below(
            format_endpoint_label(x_endstop_mm + offset_mm),
            line_center_x_mm,
            label_top_y_mm,
        )
        label_entries.append(
            {
                "label": label,
                "center_x_mm": line_center_x_mm,
            }
        )

    labels = [entry["label"] for entry in label_entries]
    slab, (_, _, _, slab_max_y) = create_calibration_label_slab(labels)
    base_collector = base_collector.fuse(slab)
    label_collector = fuse_labels_stacked_on_slab(label_collector, labels, slab)

    for entry in label_entries:
        base_collector = base_collector.fuse(
            create_calibration_label_connector(
                entry["center_x_mm"],
                slab_max_y - CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM,
                line_y_min_mm + CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM,
            )
        )

    return base_collector, label_collector


def create_absolute_x_alignment_materials(
    bed_grid_zero=None,
    x_endstop_values=None,
):
    if bed_grid_zero is None:
        bed_grid_zero = read_bed_grid_zero()
    if x_endstop_values is None:
        x_endstop_values = read_x_endstop_values()

    _, zero_y_mm = bed_grid_zero
    grid_cutouts = create_grid_cutouts(bed_grid_zero)
    logo_panel = next(
        cutout for cutout in grid_cutouts if cutout["name"] == "kingroon_logo_panel_outline"
    )
    lower_panel = next(
        cutout for cutout in grid_cutouts if cutout["name"] == "z_guide_panel_outline"
    )

    t0_pattern, t0_labels = create_absolute_x_alignment_pattern(
        bed_grid_zero=bed_grid_zero,
        x_endstop_mm=x_endstop_values["t0_x_endstop"],
        line_y_min_mm=grid_coordinate(zero_y_mm, -1),
        line_y_max_mm=grid_coordinate(zero_y_mm, 0),
        label_panel=lower_panel,
    )
    t1_pattern, t1_labels = create_absolute_x_alignment_pattern(
        bed_grid_zero=bed_grid_zero,
        x_endstop_mm=x_endstop_values["t1_x_endstop"],
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


def create_absolute_y_alignment_pattern(
    *,
    bed_grid_zero,
    calibration_value_mm,
    line_x_min_mm,
    line_x_max_mm,
    line_offset_sign,
):
    _, zero_y_mm = bed_grid_zero
    label_right_x_mm = line_x_min_mm - CALIBRATION_LABEL_GAP_MM
    label_min_y_mm = SAFE_BED_ORIGIN[1] + CALIBRATION_LABEL_PAD_MARGIN_MM
    label_max_y_mm = (
        SAFE_BED_ORIGIN[1] + SAFE_BED_DEPTH_MM - CALIBRATION_LABEL_PAD_MARGIN_MM
    )
    base_collector = PartCollector()
    label_collector = PartCollector()
    label_entries = []

    for grid_index, offset_mm in zip(
        range(CALIBRATION_GRID_Y_INDEX_MIN, CALIBRATION_GRID_Y_INDEX_MAX + 1),
        CALIBRATION_OFFSET_CANDIDATES_MM,
    ):
        painted_grid_y_mm = grid_coordinate(zero_y_mm, grid_index)
        line_center_y_mm = painted_grid_y_mm + line_offset_sign * offset_mm
        base_collector = base_collector.fuse(
            create_calibration_horizontal_segment(
                line_center_y_mm,
                line_x_min_mm,
                line_x_max_mm,
            )
        )

        label = create_calibration_label_left(
            format_endpoint_label(calibration_value_mm + offset_mm),
            label_right_x_mm,
            line_center_y_mm,
            min_y_mm=label_min_y_mm,
            max_y_mm=label_max_y_mm,
        )
        label_entries.append(
            {
                "label": label,
                "center_y_mm": line_center_y_mm,
            }
        )

    labels = [entry["label"] for entry in label_entries]
    slab, (_, _, slab_max_x, _) = create_calibration_label_slab(labels)
    base_collector = base_collector.fuse(slab)
    label_collector = fuse_labels_stacked_on_slab(label_collector, labels, slab)

    for entry in label_entries:
        base_collector = base_collector.fuse(
            create_calibration_label_horizontal_connector(
                slab_max_x - CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM,
                line_x_min_mm + CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM,
                entry["center_y_mm"],
            )
        )

    return base_collector, label_collector


def create_absolute_y_alignment_materials(
    bed_grid_zero=None,
    y_calibration_values=None,
):
    if bed_grid_zero is None:
        bed_grid_zero = read_bed_grid_zero()
    if y_calibration_values is None:
        y_calibration_values = read_y_calibration_values()

    zero_x_mm, _ = bed_grid_zero
    t0_line_x_min_mm = grid_coordinate(zero_x_mm, -2)
    t0_line_x_max_mm = grid_coordinate(zero_x_mm, -1)
    t1_line_x_min_mm = grid_coordinate(zero_x_mm, 2)
    t1_line_x_max_mm = grid_coordinate(zero_x_mm, 3)

    t0_pattern, t0_labels = create_absolute_y_alignment_pattern(
        bed_grid_zero=bed_grid_zero,
        calibration_value_mm=y_calibration_values["t0_y_endstop"],
        line_x_min_mm=t0_line_x_min_mm,
        line_x_max_mm=t0_line_x_max_mm,
        line_offset_sign=-1,
    )
    t1_pattern, t1_labels = create_absolute_y_alignment_pattern(
        bed_grid_zero=bed_grid_zero,
        calibration_value_mm=y_calibration_values["t1_y_offset"],
        line_x_min_mm=t1_line_x_min_mm,
        line_x_max_mm=t1_line_x_max_mm,
        line_offset_sign=1,
    )

    t0_material = PartCollector()
    t0_material = t0_material.fuse(t0_pattern)
    t0_material = t0_material.fuse(t1_labels)

    t1_material = PartCollector()
    t1_material = t1_material.fuse(t1_pattern)
    t1_material = t1_material.fuse(t0_labels)

    return t0_material, t1_material


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


def add_painted_bed_preview_parts(parts, plate_prefix, bed_grid_zero, grid_cutouts):
    preview_part_names = []

    def add_preview_part(part, name, color):
        preview_name = f"{plate_prefix}_{name}"
        parts.add(
            part,
            preview_name,
            color=color,
            skip_in_production=True,
        )
        preview_part_names.append(preview_name)

    add_preview_part(
        create_bed_surface(),
        "painted_bed_surface",
        ACTUAL_BED_COLOR,
    )
    add_preview_part(
        create_painted_bed_grid_lines(bed_grid_zero),
        "painted_bed_grid_1in",
        GRID_LINE_COLOR,
    )
    add_preview_part(
        create_frame(),
        "painted_bed_frame",
        PAINTED_FRAME_COLOR,
    )

    for cutout in visible_panel_cutouts(grid_cutouts):
        add_preview_part(
            create_panel_outline(cutout),
            cutout["name"],
            PANEL_OUTLINE_COLOR,
        )

    return tuple(preview_part_names)


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()
    bed_grid_zero = read_bed_grid_zero()
    grid_cutouts = create_grid_cutouts(bed_grid_zero)
    x_preview_part_names = ()
    y_preview_part_names = ()
    if not PROD:
        x_preview_part_names = add_painted_bed_preview_parts(
            parts,
            "x_plate",
            bed_grid_zero,
            grid_cutouts,
        )
        y_preview_part_names = add_painted_bed_preview_parts(
            parts,
            "y_plate",
            bed_grid_zero,
            grid_cutouts,
        )

    t0_alignment, t1_alignment = create_absolute_x_alignment_materials(
        bed_grid_zero=bed_grid_zero,
    )
    y_t0_alignment, y_t1_alignment = create_absolute_y_alignment_materials(
        bed_grid_zero=bed_grid_zero,
    )
    assert_absolute_patterns_fit_dual_area(
        [t0_alignment, t1_alignment, y_t0_alignment, y_t1_alignment]
    )
    parts.add(
        t0_alignment,
        X_T0_PART_NAME,
        color=T0_COLOR,
        obj_metadata={
            "production_group": "absolute_x_grid_alignment",
            "slicer_filament_id": 1,
            "tool": "T0",
        },
    )
    parts.add(
        t1_alignment,
        X_T1_PART_NAME,
        color=T1_COLOR,
        obj_metadata={
            "production_group": "absolute_x_grid_alignment",
            "slicer_filament_id": 2,
            "tool": "T1",
        },
    )
    parts.add(
        y_t0_alignment,
        Y_T0_PART_NAME,
        color=T0_COLOR,
        obj_metadata={
            "production_group": "absolute_y_grid_alignment",
            "slicer_filament_id": 1,
            "tool": "T0",
        },
    )
    parts.add(
        y_t1_alignment,
        Y_T1_PART_NAME,
        color=T1_COLOR,
        obj_metadata={
            "production_group": "absolute_y_grid_alignment",
            "slicer_filament_id": 2,
            "tool": "T1",
        },
    )

    plates = [
        {
            "name": "absolute_x_grid_alignment",
            "parts": [
                *x_preview_part_names,
                X_T0_PART_NAME,
                X_T1_PART_NAME,
            ],
        },
        {
            "name": "absolute_y_grid_alignment",
            "parts": [
                *y_preview_part_names,
                Y_T0_PART_NAME,
                Y_T1_PART_NAME,
            ],
        },
    ]

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
        plates=plates,
    )

    _logger.info("two-material absolute X/Y grid alignment calibration completed.")


if __name__ == "__main__":
    main()
