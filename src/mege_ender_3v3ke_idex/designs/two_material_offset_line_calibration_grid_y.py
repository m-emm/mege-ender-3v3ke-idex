"""Two-material IDEX absolute Y calibration against the painted bed grid.

Usage:
    cd <project_root> && ./run.sh --slice path/to/two_material_offset_line_calibration_grid_y.py
"""

import logging

from mege_3devops.process_data.mege_ender_3v3ke_idex import (
    SAFE_BED_DEPTH_MM,
    SAFE_BED_ORIGIN,
    SAFE_BED_WIDTH_MM,
    copy_dual_pla_04_offset_calibration_process_data,
)
from mege_ender_3v3ke_idex.designs.two_material_offset_line_calibration_grid import *

_logger = logging.getLogger(__name__)

Y_T0_PLATE_NAME = "absolute_y_t0_grid_alignment"
Y_T1_PLATE_NAME = "absolute_y_t1_grid_alignment"

Y_T0_LINES_PART_NAME = "absolute_y_t0_grid_alignment_t0_lines"
Y_T0_LABELS_PART_NAME = "absolute_y_t0_grid_alignment_t1_labels"
Y_T1_LINES_PART_NAME = "absolute_y_t1_grid_alignment_t1_lines"
Y_T1_LABELS_PART_NAME = "absolute_y_t1_grid_alignment_t0_labels"

CALIBRATION_PART_METADATA = {
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
    slab, (slab_min_x, slab_min_y, _, _) = create_calibration_label_slab(labels)
    line_x_min_mm = max(
        SAFE_BED_ORIGIN[0],
        slab_min_x - 2 * GRID_PITCH_MM + CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM,
    )
    line_x_max_mm = line_x_min_mm + GRID_PITCH_MM
    base_collector = base_collector.fuse(slab)
    for label in labels:
        text_collector = text_collector.fuse(align(label, slab, Alignment.STACK_TOP))

    text_collector = text_collector.fuse(
        create_calibration_label_grounding_marker(
            slab_min_x,
            slab_min_y,
            context="Y",
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


def create_plate_definitions(preview_part_names_by_plate=None):
    if preview_part_names_by_plate is None:
        preview_part_names_by_plate = {}

    return [
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


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()
    calibration = read_grid_calibration()
    bed_grid_zero = calibration["bed_grid_zero"]
    preview_part_names_by_plate = {}

    if not PROD:
        preview_part_names_by_plate = {
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
            y_t0_lines,
            y_t0_labels,
            y_t1_lines,
            y_t1_labels,
        ]
    )

    add_calibration_part(
        parts,
        y_t0_lines,
        Y_T0_LINES_PART_NAME,
        T0_COLOR,
        CALIBRATION_PART_METADATA,
    )
    add_calibration_part(
        parts,
        y_t0_labels,
        Y_T0_LABELS_PART_NAME,
        T1_COLOR,
        CALIBRATION_PART_METADATA,
    )
    add_calibration_part(
        parts,
        y_t1_lines,
        Y_T1_LINES_PART_NAME,
        T1_COLOR,
        CALIBRATION_PART_METADATA,
    )
    add_calibration_part(
        parts,
        y_t1_labels,
        Y_T1_LABELS_PART_NAME,
        T0_COLOR,
        CALIBRATION_PART_METADATA,
    )

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

    _logger.info("two-material absolute Y grid alignment calibration completed.")


if __name__ == "__main__":
    main()
