"""Fast two-material IDEX X/Y offset line calibration.

Usage:
    cd <project_root> && ./run.sh --slice path/to/two_material_offset_line_calibration.py
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

CALIBRATION_HEIGHT_MM = 0.8
LINE_WIDTH_MM = 0.7
LINE_SEGMENT_LENGTH_MM = 18.0
ZERO_LINE_SEGMENT_LENGTH_MM = 26.0
INTER_MATERIAL_AIR_GAP_MM = 8.0
CANDIDATE_PITCH_MM = 10.0
PATTERN_GAP_MM = 16.0
LABEL_SIZE_MM = 4.5
LABEL_STROKE_WIDTH_MM = 0.6
LABEL_GAP_MM = 2.0
LABEL_PAD_THICKNESS_MM = 0.4
LABEL_TEXT_THICKNESS_MM = CALIBRATION_HEIGHT_MM - LABEL_PAD_THICKNESS_MM
LABEL_PAD_MARGIN_MM = 1.5
LABEL_PAD_CONNECTOR_WIDTH_MM = LINE_WIDTH_MM
LABEL_PAD_CONNECTOR_OVERLAP_MM = 0.3
SPINE_WIDTH_MM = LINE_WIDTH_MM

OFFSET_STEP_MM = 0.1
OFFSET_COUNT_EACH_SIDE = 5
OFFSET_CANDIDATES_MM = tuple(
    round((index - OFFSET_COUNT_EACH_SIDE) * OFFSET_STEP_MM, 1)
    for index in range(2 * OFFSET_COUNT_EACH_SIDE + 1)
)
OFFSET_RANGE_MM = max(abs(offset) for offset in OFFSET_CANDIDATES_MM)

X_PATTERN_WIDTH_MM = (
    CANDIDATE_PITCH_MM * (len(OFFSET_CANDIDATES_MM) - 1)
    + 2 * OFFSET_RANGE_MM
    + LINE_WIDTH_MM
)
X_PATTERN_HEIGHT_MM = 2 * ZERO_LINE_SEGMENT_LENGTH_MM + INTER_MATERIAL_AIR_GAP_MM
Y_PATTERN_WIDTH_MM = 2 * ZERO_LINE_SEGMENT_LENGTH_MM + INTER_MATERIAL_AIR_GAP_MM
Y_PATTERN_HEIGHT_MM = (
    CANDIDATE_PITCH_MM * (len(OFFSET_CANDIDATES_MM) - 1)
    + 2 * OFFSET_RANGE_MM
    + LINE_WIDTH_MM
)

X_PATTERN_X_START_MM = OFFSET_RANGE_MM + LINE_WIDTH_MM / 2
X_PATTERN_Y_BOTTOM_MM = max(0.0, (Y_PATTERN_HEIGHT_MM - X_PATTERN_HEIGHT_MM) / 2)
X_PATTERN_GAP_CENTER_Y_MM = (
    X_PATTERN_Y_BOTTOM_MM + ZERO_LINE_SEGMENT_LENGTH_MM + INTER_MATERIAL_AIR_GAP_MM / 2
)

Y_PATTERN_LEFT_MM = X_PATTERN_WIDTH_MM + PATTERN_GAP_MM
Y_PATTERN_SPLIT_CENTER_X_MM = (
    Y_PATTERN_LEFT_MM + ZERO_LINE_SEGMENT_LENGTH_MM + INTER_MATERIAL_AIR_GAP_MM / 2
)
Y_PATTERN_Y_START_MM = OFFSET_RANGE_MM + LINE_WIDTH_MM / 2

T0_COLOR = (0.95, 0.08, 0.04)
T1_COLOR = (0.0, 0.32, 1.0)

CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "klipper_setup"
    / "klipper_config"
    / "printer.cfg"
)
TOOL_STATE_SECTION = "gcode_macro _IDEX_TOOL_STATE"


def get_config_section(config_text, section_name):
    match = re.search(
        rf"^\[{re.escape(section_name)}\]\n(?P<body>.*?)(?=^\[|\Z)",
        config_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        raise ValueError(f"Missing [{section_name}] section in Klipper config")
    return match.group("body")


def parse_tool_state_offset(tool_state_section, offset_name):
    match = re.search(
        rf"^\s*variable_{re.escape(offset_name)}\s*:\s*(?P<value>\S+)\s*$",
        tool_state_section,
        flags=re.MULTILINE,
    )
    if match is None:
        raise ValueError(f"Missing variable_{offset_name} in _IDEX_TOOL_STATE")

    try:
        return float(match.group("value"))
    except ValueError:
        raise ValueError(f"variable_{offset_name} must be a numeric offset") from None


def parse_idex_tool_xy_offsets(config_text):
    tool_state = get_config_section(config_text, TOOL_STATE_SECTION)
    offsets = {
        "t0_x": parse_tool_state_offset(tool_state, "t0_x_offset"),
        "t0_y": parse_tool_state_offset(tool_state, "t0_y_offset"),
        "t1_x": parse_tool_state_offset(tool_state, "t1_x_offset"),
        "t1_y": parse_tool_state_offset(tool_state, "t1_y_offset"),
    }

    if offsets["t0_x"] != 0.0 or offsets["t0_y"] != 0.0:
        raise ValueError(
            "T0 X/Y offsets must be 0.0 before generating T1 calibration labels: "
            f"t0_x={offsets['t0_x']}, t0_y={offsets['t0_y']}"
        )

    return offsets


def read_idex_tool_xy_offsets(config_path=CONFIG_PATH):
    return parse_idex_tool_xy_offsets(config_path.read_text(encoding="utf-8"))


def format_offset_label(offset_mm):
    rounded_offset_mm = round(offset_mm, 1)
    if rounded_offset_mm == 0:
        rounded_offset_mm = 0.0
    return f"{rounded_offset_mm:.1f}"


def create_vector_label(text):
    label = create_vector_text_object(
        text,
        size=LABEL_SIZE_MM,
        thickness=LABEL_TEXT_THICKNESS_MM,
        stroke_width=LABEL_STROKE_WIDTH_MM,
    )

    bb_center = get_bounding_box_center(label)
    return rotate(45, center=bb_center)(label)


def create_label_below(text, center_x_mm, top_y_mm):
    label = create_vector_label(text)
    min_point, max_point = get_bounding_box(label)
    center_x = (min_point[0] + max_point[0]) / 2
    return translate(
        center_x_mm - center_x,
        top_y_mm - max_point[1],
        LABEL_PAD_THICKNESS_MM,
    )(label)


def create_label_left(text, right_x_mm, center_y_mm):
    label = create_vector_label(text)
    min_point, max_point = get_bounding_box(label)
    center_y = (min_point[1] + max_point[1]) / 2
    return translate(
        right_x_mm - max_point[0],
        center_y_mm - center_y,
        LABEL_PAD_THICKNESS_MM,
    )(label)


def create_vertical_segment(center_x_mm, start_y_mm, length_mm):
    return create_box(
        LINE_WIDTH_MM,
        length_mm,
        CALIBRATION_HEIGHT_MM,
        origin=(center_x_mm - LINE_WIDTH_MM / 2, start_y_mm, 0),
    )


def create_horizontal_segment(start_x_mm, center_y_mm, length_mm):
    return create_box(
        length_mm,
        LINE_WIDTH_MM,
        CALIBRATION_HEIGHT_MM,
        origin=(start_x_mm, center_y_mm - LINE_WIDTH_MM / 2, 0),
    )


def create_horizontal_spine(start_x_mm, end_x_mm, center_y_mm):
    return create_box(
        end_x_mm - start_x_mm,
        SPINE_WIDTH_MM,
        CALIBRATION_HEIGHT_MM,
        origin=(start_x_mm, center_y_mm - SPINE_WIDTH_MM / 2, 0),
    )


def create_vertical_spine(center_x_mm, start_y_mm, end_y_mm):
    return create_box(
        SPINE_WIDTH_MM,
        end_y_mm - start_y_mm,
        CALIBRATION_HEIGHT_MM,
        origin=(center_x_mm - SPINE_WIDTH_MM / 2, start_y_mm, 0),
    )


def create_label_slab(labels):
    min_x = min(get_bounding_box(label)[0][0] for label in labels) - LABEL_PAD_MARGIN_MM
    min_y = min(get_bounding_box(label)[0][1] for label in labels) - LABEL_PAD_MARGIN_MM
    max_x = max(get_bounding_box(label)[1][0] for label in labels) + LABEL_PAD_MARGIN_MM
    max_y = max(get_bounding_box(label)[1][1] for label in labels) + LABEL_PAD_MARGIN_MM

    slab = create_box(
        max_x - min_x,
        max_y - min_y,
        LABEL_PAD_THICKNESS_MM,
        origin=(min_x, min_y, 0),
    )
    return slab, (min_x, min_y, max_x, max_y)


def create_label_vertical_connector(center_x_mm, start_y_mm, end_y_mm):
    min_y = min(start_y_mm, end_y_mm)
    max_y = max(start_y_mm, end_y_mm)
    return create_box(
        LABEL_PAD_CONNECTOR_WIDTH_MM,
        max_y - min_y,
        LABEL_PAD_THICKNESS_MM,
        origin=(center_x_mm - LABEL_PAD_CONNECTOR_WIDTH_MM / 2, min_y, 0),
    )


def create_label_horizontal_connector(start_x_mm, end_x_mm, center_y_mm):
    min_x = min(start_x_mm, end_x_mm)
    max_x = max(start_x_mm, end_x_mm)
    return create_box(
        max_x - min_x,
        LABEL_PAD_CONNECTOR_WIDTH_MM,
        LABEL_PAD_THICKNESS_MM,
        origin=(min_x, center_y_mm - LABEL_PAD_CONNECTOR_WIDTH_MM / 2, 0),
    )


def fuse_x_label_slab(t0_collector, x_label_entries):
    labels = [entry["label"] for entry in x_label_entries]
    slab, (_, _, _, slab_max_y) = create_label_slab(labels)
    t0_collector = t0_collector.fuse(slab)

    for entry in x_label_entries:
        connector = create_label_vertical_connector(
            entry["center_x_mm"],
            slab_max_y - LABEL_PAD_CONNECTOR_OVERLAP_MM,
            entry["line_start_y_mm"] + LABEL_PAD_CONNECTOR_OVERLAP_MM,
        )
        t0_collector = t0_collector.fuse(connector)

    return t0_collector


def fuse_y_label_slab(t0_collector, y_label_entries):
    labels = [entry["label"] for entry in y_label_entries]
    slab, (_, _, slab_max_x, _) = create_label_slab(labels)
    t0_collector = t0_collector.fuse(slab)

    for entry in y_label_entries:
        connector = create_label_horizontal_connector(
            slab_max_x - LABEL_PAD_CONNECTOR_OVERLAP_MM,
            entry["line_start_x_mm"] + LABEL_PAD_CONNECTOR_OVERLAP_MM,
            entry["center_y_mm"],
        )
        t0_collector = t0_collector.fuse(connector)

    return t0_collector


def fuse_removal_spines(t0_collector, t1_collector):
    x_nominal_centers = (
        X_PATTERN_X_START_MM + index * CANDIDATE_PITCH_MM
        for index in range(len(OFFSET_CANDIDATES_MM))
    )
    x_shifted_centers = (
        X_PATTERN_X_START_MM + index * CANDIDATE_PITCH_MM + offset_mm
        for index, offset_mm in enumerate(OFFSET_CANDIDATES_MM)
    )
    x_nominal_centers = tuple(x_nominal_centers)
    x_shifted_centers = tuple(x_shifted_centers)

    x_t0_spine_y_mm = (
        X_PATTERN_GAP_CENTER_Y_MM
        - INTER_MATERIAL_AIR_GAP_MM / 2
        - LINE_SEGMENT_LENGTH_MM / 2
    )
    x_t1_spine_y_mm = (
        X_PATTERN_GAP_CENTER_Y_MM
        + INTER_MATERIAL_AIR_GAP_MM / 2
        + LINE_SEGMENT_LENGTH_MM / 2
    )
    t0_collector = t0_collector.fuse(
        create_horizontal_spine(
            min(x_nominal_centers) - LINE_WIDTH_MM / 2,
            max(x_nominal_centers) + LINE_WIDTH_MM / 2,
            x_t0_spine_y_mm,
        )
    )
    t1_collector = t1_collector.fuse(
        create_horizontal_spine(
            min(x_shifted_centers) - LINE_WIDTH_MM / 2,
            max(x_shifted_centers) + LINE_WIDTH_MM / 2,
            x_t1_spine_y_mm,
        )
    )

    y_nominal_centers = (
        Y_PATTERN_Y_START_MM + index * CANDIDATE_PITCH_MM
        for index in range(len(OFFSET_CANDIDATES_MM))
    )
    y_shifted_centers = (
        Y_PATTERN_Y_START_MM + index * CANDIDATE_PITCH_MM + offset_mm
        for index, offset_mm in enumerate(OFFSET_CANDIDATES_MM)
    )
    y_nominal_centers = tuple(y_nominal_centers)
    y_shifted_centers = tuple(y_shifted_centers)

    y_t0_spine_x_mm = (
        Y_PATTERN_SPLIT_CENTER_X_MM
        - INTER_MATERIAL_AIR_GAP_MM / 2
        - LINE_SEGMENT_LENGTH_MM / 2
    )
    y_t1_spine_x_mm = (
        Y_PATTERN_SPLIT_CENTER_X_MM
        + INTER_MATERIAL_AIR_GAP_MM / 2
        + LINE_SEGMENT_LENGTH_MM / 2
    )
    t0_collector = t0_collector.fuse(
        create_vertical_spine(
            y_t0_spine_x_mm,
            min(y_nominal_centers) - LINE_WIDTH_MM / 2,
            max(y_nominal_centers) + LINE_WIDTH_MM / 2,
        )
    )
    t1_collector = t1_collector.fuse(
        create_vertical_spine(
            y_t1_spine_x_mm,
            min(y_shifted_centers) - LINE_WIDTH_MM / 2,
            max(y_shifted_centers) + LINE_WIDTH_MM / 2,
        )
    )

    return t0_collector, t1_collector


def create_offset_line_materials(t1_x_offset_mm=None, t1_y_offset_mm=None):
    if t1_x_offset_mm is None or t1_y_offset_mm is None:
        current_offsets = read_idex_tool_xy_offsets()
        if t1_x_offset_mm is None:
            t1_x_offset_mm = current_offsets["t1_x"]
        if t1_y_offset_mm is None:
            t1_y_offset_mm = current_offsets["t1_y"]

    t0_collector = PartCollector()
    t1_collector = PartCollector()
    t0_collector, t1_collector = fuse_removal_spines(t0_collector, t1_collector)
    x_label_entries = []
    y_label_entries = []

    for index, offset_mm in enumerate(OFFSET_CANDIDATES_MM):
        segment_length_mm = LINE_SEGMENT_LENGTH_MM
        if offset_mm == 0.0:
            segment_length_mm = ZERO_LINE_SEGMENT_LENGTH_MM

        x_nominal_mm = X_PATTERN_X_START_MM + index * CANDIDATE_PITCH_MM
        t0_start_y_mm = (
            X_PATTERN_GAP_CENTER_Y_MM
            - INTER_MATERIAL_AIR_GAP_MM / 2
            - segment_length_mm
        )
        t1_start_y_mm = X_PATTERN_GAP_CENTER_Y_MM + INTER_MATERIAL_AIR_GAP_MM / 2

        t0_vertical = create_vertical_segment(
            x_nominal_mm,
            t0_start_y_mm,
            segment_length_mm,
        )
        t1_vertical = create_vertical_segment(
            x_nominal_mm + offset_mm,
            t1_start_y_mm,
            segment_length_mm,
        )

        t0_collector = t0_collector.fuse(t0_vertical)
        t1_collector = t1_collector.fuse(t1_vertical)

        x_label = create_label_below(
            format_offset_label(t1_x_offset_mm + offset_mm),
            x_nominal_mm,
            X_PATTERN_Y_BOTTOM_MM - LABEL_GAP_MM,
        )
        x_label_entries.append(
            {
                "label": x_label,
                "center_x_mm": x_nominal_mm,
                "line_start_y_mm": t0_start_y_mm,
            }
        )

        y_nominal_mm = Y_PATTERN_Y_START_MM + index * CANDIDATE_PITCH_MM
        t0_start_x_mm = (
            Y_PATTERN_SPLIT_CENTER_X_MM
            - INTER_MATERIAL_AIR_GAP_MM / 2
            - segment_length_mm
        )
        t1_start_x_mm = Y_PATTERN_SPLIT_CENTER_X_MM + INTER_MATERIAL_AIR_GAP_MM / 2

        t0_horizontal = create_horizontal_segment(
            t0_start_x_mm,
            y_nominal_mm,
            segment_length_mm,
        )
        t1_horizontal = create_horizontal_segment(
            t1_start_x_mm,
            y_nominal_mm + offset_mm,
            segment_length_mm,
        )

        t0_collector = t0_collector.fuse(t0_horizontal)
        t1_collector = t1_collector.fuse(t1_horizontal)

        y_label = create_label_left(
            format_offset_label(t1_y_offset_mm + offset_mm),
            Y_PATTERN_LEFT_MM - LABEL_GAP_MM,
            y_nominal_mm,
        )
        y_label_entries.append(
            {
                "label": y_label,
                "center_y_mm": y_nominal_mm,
                "line_start_x_mm": t0_start_x_mm,
            }
        )

    t0_collector = fuse_x_label_slab(t0_collector, x_label_entries)
    t0_collector = fuse_y_label_slab(t0_collector, y_label_entries)

    for label_entry in x_label_entries + y_label_entries:
        t1_collector = t1_collector.fuse(label_entry["label"])

    return t0_collector, t1_collector


def assert_pattern_fits_dual_area(parts):
    min_x = min(get_bounding_box(part)[0][0] for part in parts)
    min_y = min(get_bounding_box(part)[0][1] for part in parts)
    max_x = max(get_bounding_box(part)[1][0] for part in parts)
    max_y = max(get_bounding_box(part)[1][1] for part in parts)

    width = max_x - min_x
    depth = max_y - min_y
    if width > SAFE_BED_WIDTH_MM or depth > SAFE_BED_DEPTH_MM:
        raise ValueError(
            "Two-material calibration pattern does not fit the dual-safe area: "
            f"size=({width}, {depth}), "
            f"bed=({SAFE_BED_WIDTH_MM}, {SAFE_BED_DEPTH_MM})"
        )


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    t0_part, t1_part = create_offset_line_materials()
    assert_pattern_fits_dual_area([t0_part, t1_part])

    parts.add(
        t0_part,
        "offset_line_calibration_t0_nominal",
        color=T0_COLOR,
        obj_metadata={
            "production_group": "offset_line_calibration",
            "slicer_filament_id": 1,
            "tool": "T0",
        },
    )
    parts.add(
        t1_part,
        "offset_line_calibration_t1_shifted",
        color=T1_COLOR,
        obj_metadata={
            "production_group": "offset_line_calibration",
            "slicer_filament_id": 2,
            "tool": "T1",
        },
    )

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=copy_dual_pla_04_offset_calibration_process_data(),
        prod_gap=4,
        bed_width=SAFE_BED_WIDTH_MM,
        bed_depth=SAFE_BED_DEPTH_MM,
        prod_origin=SAFE_BED_ORIGIN,
    )

    _logger.info("two-material offset line calibration design completed.")


if __name__ == "__main__":
    main()
