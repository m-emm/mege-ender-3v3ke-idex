"""Two-material IDEX absolute X calibration against the painted bed grid.

Usage:
    cd <project_root> && ./run.sh --slice path/to/two_material_offset_line_calibration_grid_x.py
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

X_T0_PLATE_NAME = "absolute_x_t0_grid_alignment"
X_T1_PLATE_NAME = "absolute_x_t1_grid_alignment"

X_T0_LINES_PART_NAME = "absolute_x_t0_grid_alignment_t0_lines"
X_T0_LABELS_PART_NAME = "absolute_x_t0_grid_alignment_t1_labels"
X_T1_LINES_PART_NAME = "absolute_x_t1_grid_alignment_t1_lines"
X_T1_LABELS_PART_NAME = "absolute_x_t1_grid_alignment_t0_labels"

CALIBRATION_PART_METADATA = {
    X_T0_LINES_PART_NAME: {
        "production_group": X_T0_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    },
    X_T0_LABELS_PART_NAME: {
        "production_group": X_T0_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    },
    X_T1_LINES_PART_NAME: {
        "production_group": X_T1_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    },
    X_T1_LABELS_PART_NAME: {
        "production_group": X_T1_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    },
}


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
    slab, (slab_min_x, slab_min_y, _, slab_max_y) = create_calibration_label_slab(
        labels
    )
    base_collector = base_collector.fuse(slab)

    for label in labels:
        label_collector = label_collector.fuse(align(label, slab, Alignment.STACK_TOP))
    label_collector = label_collector.fuse(
        create_calibration_label_grounding_marker(
            slab_min_x,
            slab_min_y,
            context="X",
        )
    )

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

    t0_lines, t0_labels = create_absolute_x_alignment_pattern(
        bed_grid_zero=bed_grid_zero,
        x_endstop_mm=calibration["t0_x_endstop"],
        line_y_min_mm=grid_coordinate(zero_y_mm, -1),
        line_y_max_mm=grid_coordinate(zero_y_mm, 0),
        label_panel=lower_panel,
    )
    t1_lines, t1_labels = create_absolute_x_alignment_pattern(
        bed_grid_zero=bed_grid_zero,
        x_endstop_mm=calibration["t1_x_endstop"],
        line_y_min_mm=grid_coordinate(zero_y_mm, 3),
        line_y_max_mm=grid_coordinate(zero_y_mm, 4),
        label_panel=logo_panel,
    )

    return t0_lines, t0_labels, t1_lines, t1_labels


def create_plate_definitions(preview_part_names_by_plate=None):
    if preview_part_names_by_plate is None:
        preview_part_names_by_plate = {}

    return [
        {
            "name": X_T0_PLATE_NAME,
            "parts": [
                *preview_part_names_by_plate.get(X_T0_PLATE_NAME, ()),
                X_T0_LINES_PART_NAME,
                X_T0_LABELS_PART_NAME,
            ],
        },
        {
            "name": X_T1_PLATE_NAME,
            "parts": [
                *preview_part_names_by_plate.get(X_T1_PLATE_NAME, ()),
                X_T1_LINES_PART_NAME,
                X_T1_LABELS_PART_NAME,
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
            X_T0_PLATE_NAME: add_painted_bed_preview_parts(
                parts,
                "x_t0_plate",
                bed_grid_zero,
            ),
            X_T1_PLATE_NAME: add_painted_bed_preview_parts(
                parts,
                "x_t1_plate",
                bed_grid_zero,
            ),
        }

    x_t0_lines, x_t0_labels, x_t1_lines, x_t1_labels = (
        create_absolute_x_alignment_materials(calibration)
    )
    assert_absolute_patterns_fit_dual_area(
        [
            x_t0_lines,
            x_t0_labels,
            x_t1_lines,
            x_t1_labels,
        ]
    )

    add_calibration_part(
        parts,
        x_t0_lines,
        X_T0_LINES_PART_NAME,
        T0_COLOR,
        CALIBRATION_PART_METADATA,
    )
    add_calibration_part(
        parts,
        x_t0_labels,
        X_T0_LABELS_PART_NAME,
        T1_COLOR,
        CALIBRATION_PART_METADATA,
    )
    add_calibration_part(
        parts,
        x_t1_lines,
        X_T1_LINES_PART_NAME,
        T1_COLOR,
        CALIBRATION_PART_METADATA,
    )
    add_calibration_part(
        parts,
        x_t1_labels,
        X_T1_LABELS_PART_NAME,
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

    _logger.info("two-material absolute X grid alignment calibration completed.")


if __name__ == "__main__":
    main()
