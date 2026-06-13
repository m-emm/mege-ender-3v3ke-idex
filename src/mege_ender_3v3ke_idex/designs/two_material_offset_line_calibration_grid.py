"""Two-material IDEX absolute offset calibration grid preview.

Usage:
    cd <project_root> && ./run.sh path/to/two_material_offset_line_calibration_grid.py
"""

import logging
import os
import re
from pathlib import Path

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "klipper_setup"
    / "klipper_config"
    / "printer.cfg"
)
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


def parse_bed_grid_zero(config_text):
    tool_state = get_config_section(config_text, TOOL_STATE_SECTION)
    return (
        parse_tool_state_float(tool_state, "bed_grid_zero_x"),
        parse_tool_state_float(tool_state, "bed_grid_zero_y"),
    )


def read_bed_grid_zero(config_path=CONFIG_PATH):
    return parse_bed_grid_zero(config_path.read_text(encoding="utf-8"))


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


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()
    bed_grid_zero = read_bed_grid_zero()
    grid_cutouts = create_grid_cutouts(bed_grid_zero)

    parts.add(
        create_bed_surface(),
        "painted_bed_surface",
        color=ACTUAL_BED_COLOR,
        skip_in_production=True,
    )

    grid_lines = create_painted_bed_grid_lines(bed_grid_zero)
    parts.add(
        grid_lines,
        "painted_bed_grid_1in",
        color=GRID_LINE_COLOR,
        skip_in_production=True,
    )

    frame = create_frame()
    parts.add(
        frame,
        "painted_bed_frame",
        color=PAINTED_FRAME_COLOR,
        skip_in_production=True,
    )

    for cutout in visible_panel_cutouts(grid_cutouts):
        parts.add(
            create_panel_outline(cutout),
            cutout["name"],
            color=PANEL_OUTLINE_COLOR,
            skip_in_production=True,
        )

    # This preview intentionally exports visualization-only parts.
    os.environ["SHELLFORGEPY_PRODUCTION"] = "0"
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=False,
        prod_gap=4,
        bed_width=ACTUAL_BED_WIDTH_MM,
        bed_depth=ACTUAL_BED_DEPTH_MM,
        prod_origin=(ACTUAL_BED_ORIGIN_X_MM, ACTUAL_BED_ORIGIN_Y_MM),
    )

    _logger.info("two-material offset line calibration grid preview completed.")


if __name__ == "__main__":
    main()
