"""Fast two-material IDEX X/Y offset line calibration.

Usage:
    cd <project_root> && ./run.sh --slice path/to/two_material_offset_line_calibration.py
"""

import logging
import os

from mege_3devops.process_data.mege_ender_3v3ke_idex import (
    SAFE_BED_DEPTH_MM,
    SAFE_BED_ORIGIN,
    SAFE_BED_WIDTH_MM,
    copy_dual_pla_04_offset_calibration_process_data,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

CALIBRATION_HEIGHT_MM = 0.6
LINE_WIDTH_MM = 0.7
LINE_SEGMENT_LENGTH_MM = 18.0
ZERO_LINE_SEGMENT_LENGTH_MM = 26.0
INTER_MATERIAL_AIR_GAP_MM = 8.0
CANDIDATE_PITCH_MM = 7.0
PATTERN_GAP_MM = 16.0

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


def create_offset_line_materials():
    t0_collector = PartCollector()
    t1_collector = PartCollector()

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
