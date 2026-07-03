"""Single-plate two-material IDEX absolute X/Y calibration against the bed grid.

Usage:
    cd <project_root> && ./run.sh --slice \
        src/mege_ender_3v3ke_idex/designs/two_material_offset_line_calibration_grid_xy.py \
        --plate absolute_xy_grid_alignment

Layout:
    T0 X: left lower vertical grid lines, T1 labels below.
    T1 X: right lower vertical grid lines, T0 labels below.
    T0 Y: left upper horizontal grid lines, T1 labels to the right.
    T1 Y: right upper horizontal grid lines, T0 labels to the left.
"""

import logging

from mege_3devops.process_data.mege_ender_3v3ke_idex import (
    SAFE_BED_DEPTH_MM,
    SAFE_BED_ORIGIN,
    SAFE_BED_WIDTH_MM,
    copy_dual_pla_06_offset_calibration_process_data,
)
from mege_ender_3v3ke_idex.designs.two_material_offset_line_calibration_grid import *

_logger = logging.getLogger(__name__)

XY_PLATE_NAME = "absolute_xy_grid_alignment"

XY_T0_MATERIAL_PART_NAME = "absolute_xy_grid_alignment_t0_material"
XY_T1_MATERIAL_PART_NAME = "absolute_xy_grid_alignment_t1_material"

XY_OFFSET_CANDIDATES_MM = (-0.2, -0.1, 0.0, 0.1, 0.2)
XY_GRID_SEGMENT_MARGIN_MM = 3.0

XY_T0_X_GRID_INDICES = (-4, -3, -2, -1, 0)
XY_T1_X_GRID_INDICES = (1, 2, 3, 4, 5)
XY_Y_GRID_INDICES = (2, 3, 4, 5, 6)

CALIBRATION_PART_METADATA = {
    XY_T0_MATERIAL_PART_NAME: {
        "production_group": XY_PLATE_NAME,
        "slicer_filament_id": 1,
        "tool": "T0",
    },
    XY_T1_MATERIAL_PART_NAME: {
        "production_group": XY_PLATE_NAME,
        "slicer_filament_id": 2,
        "tool": "T1",
    },
}


def copy_xy_offset_calibration_process_data():
    process_data = copy_dual_pla_06_offset_calibration_process_data()
    process_data["process_overrides"]["wipe_tower_x"] = "105"
    process_data["process_overrides"]["wipe_tower_y"] = "220"
    return process_data


def shift_part_inside_bounds(
    part,
    *,
    min_x_mm=None,
    max_x_mm=None,
    min_y_mm=None,
    max_y_mm=None,
):
    min_point, max_point = get_bounding_box(part)
    shift_x_mm = 0.0
    shift_y_mm = 0.0

    if min_x_mm is not None and min_point[0] < min_x_mm:
        shift_x_mm = max(shift_x_mm, min_x_mm - min_point[0])
    if max_x_mm is not None and max_point[0] + shift_x_mm > max_x_mm:
        shift_x_mm = min(shift_x_mm, max_x_mm - max_point[0])
    if min_y_mm is not None and min_point[1] < min_y_mm:
        shift_y_mm = max(shift_y_mm, min_y_mm - min_point[1])
    if max_y_mm is not None and max_point[1] + shift_y_mm > max_y_mm:
        shift_y_mm = min(shift_y_mm, max_y_mm - max_point[1])

    if shift_x_mm or shift_y_mm:
        return translate(shift_x_mm, shift_y_mm, 0)(part)
    return part


def create_calibration_label_below_inside_safe_x(text, center_x_mm, top_y_mm):
    label = create_calibration_label_below(text, center_x_mm, top_y_mm)
    return shift_part_inside_bounds(
        label,
        min_x_mm=SAFE_BED_ORIGIN[0] + CALIBRATION_LABEL_PAD_MARGIN_MM,
        max_x_mm=SAFE_BED_ORIGIN[0]
        + SAFE_BED_WIDTH_MM
        - CALIBRATION_LABEL_PAD_MARGIN_MM,
    )


def create_calibration_label_right(
    text,
    left_x_mm,
    center_y_mm,
    *,
    min_y_mm=None,
    max_y_mm=None,
):
    label = create_calibration_vector_label(text)
    min_point, max_point = get_bounding_box(label)
    center_y = (min_point[1] + max_point[1]) / 2
    label = translate(left_x_mm - min_point[0], center_y_mm - center_y, 0)(label)
    return shift_part_inside_bounds(
        label,
        min_y_mm=min_y_mm,
        max_y_mm=max_y_mm,
    )


def create_vertical_x_alignment_group(
    *,
    bed_grid_zero,
    x_endstop_mm,
    grid_indices,
):
    zero_x_mm, zero_y_mm = bed_grid_zero
    line_y_min_mm = grid_coordinate(zero_y_mm, -1) + XY_GRID_SEGMENT_MARGIN_MM
    line_y_max_mm = grid_coordinate(zero_y_mm, 0) - XY_GRID_SEGMENT_MARGIN_MM
    label_top_y_mm = line_y_min_mm - CALIBRATION_LABEL_GAP_MM
    base_collector = PartCollector()
    text_collector = PartCollector()
    label_entries = []

    for grid_index, offset_mm in zip(grid_indices, XY_OFFSET_CANDIDATES_MM):
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
                "label": create_calibration_label_below_inside_safe_x(
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
        text_collector = text_collector.fuse(align(label, slab, Alignment.STACK_TOP))

    for entry in label_entries:
        connector_start_y_mm = slab_max_y - CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM
        connector_end_y_mm = line_y_min_mm + CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM
        min_y_mm = min(connector_start_y_mm, connector_end_y_mm)
        max_y_mm = max(connector_start_y_mm, connector_end_y_mm)
        base_collector = base_collector.fuse(
            create_box(
                CALIBRATION_LABEL_CONNECTOR_WIDTH_MM,
                max_y_mm - min_y_mm,
                CALIBRATION_LABEL_PAD_THICKNESS_MM,
                origin=(
                    entry["center_x_mm"] - CALIBRATION_LABEL_CONNECTOR_WIDTH_MM / 2,
                    min_y_mm,
                    0,
                ),
            )
        )

    return base_collector, text_collector


def create_horizontal_y_alignment_group(
    *,
    bed_grid_zero,
    y_endstop_mm,
    line_x_min_mm,
    line_x_max_mm,
    label_side,
):
    _, zero_y_mm = bed_grid_zero
    label_min_y_mm = SAFE_BED_ORIGIN[1] + CALIBRATION_LABEL_PAD_MARGIN_MM
    label_max_y_mm = (
        SAFE_BED_ORIGIN[1] + SAFE_BED_DEPTH_MM - CALIBRATION_LABEL_PAD_MARGIN_MM
    )
    base_collector = PartCollector()
    text_collector = PartCollector()
    label_entries = []

    for grid_index, offset_mm in zip(XY_Y_GRID_INDICES, XY_OFFSET_CANDIDATES_MM):
        painted_grid_y_mm = grid_coordinate(zero_y_mm, grid_index)
        line_center_y_mm = painted_grid_y_mm - offset_mm
        base_collector = base_collector.fuse(
            create_box(
                line_x_max_mm - line_x_min_mm,
                CALIBRATION_LINE_WIDTH_MM,
                CALIBRATION_HEIGHT_MM,
                origin=(
                    line_x_min_mm,
                    line_center_y_mm - CALIBRATION_LINE_WIDTH_MM / 2,
                    0,
                ),
            )
        )

        if label_side == "right":
            label = create_calibration_label_right(
                format_endpoint_label(y_endstop_mm + offset_mm),
                line_x_max_mm + CALIBRATION_LABEL_GAP_MM,
                line_center_y_mm,
                min_y_mm=label_min_y_mm,
                max_y_mm=label_max_y_mm,
            )
        elif label_side == "left":
            label = create_calibration_label_left(
                format_endpoint_label(y_endstop_mm + offset_mm),
                line_x_min_mm - CALIBRATION_LABEL_GAP_MM,
                line_center_y_mm,
                min_y_mm=label_min_y_mm,
                max_y_mm=label_max_y_mm,
            )
        else:
            raise ValueError(f"Unsupported label_side: {label_side}")

        label_entries.append(
            {
                "label": label,
                "center_y_mm": line_center_y_mm,
            }
        )

    labels = [entry["label"] for entry in label_entries]
    slab, (slab_min_x, _, slab_max_x, _) = create_calibration_label_slab(labels)
    base_collector = base_collector.fuse(slab)
    for label in labels:
        text_collector = text_collector.fuse(align(label, slab, Alignment.STACK_TOP))

    for entry in label_entries:
        if label_side == "right":
            connector_start_x_mm = (
                line_x_max_mm - CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM
            )
            connector_end_x_mm = slab_min_x + CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM
        else:
            connector_start_x_mm = slab_max_x - CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM
            connector_end_x_mm = line_x_min_mm + CALIBRATION_LABEL_CONNECTOR_OVERLAP_MM

        min_x_mm = min(connector_start_x_mm, connector_end_x_mm)
        max_x_mm = max(connector_start_x_mm, connector_end_x_mm)
        base_collector = base_collector.fuse(
            create_box(
                max_x_mm - min_x_mm,
                CALIBRATION_LABEL_CONNECTOR_WIDTH_MM,
                CALIBRATION_LABEL_PAD_THICKNESS_MM,
                origin=(
                    min_x_mm,
                    entry["center_y_mm"] - CALIBRATION_LABEL_CONNECTOR_WIDTH_MM / 2,
                    0,
                ),
            )
        )

    return base_collector, text_collector


def create_absolute_xy_alignment_materials(calibration):
    bed_grid_zero = calibration["bed_grid_zero"]
    zero_x_mm, _ = bed_grid_zero
    t0_material_collector = PartCollector()
    t1_material_collector = PartCollector()

    t0_x_lines, t0_x_labels = create_vertical_x_alignment_group(
        bed_grid_zero=bed_grid_zero,
        x_endstop_mm=calibration["t0_x_endstop"],
        grid_indices=XY_T0_X_GRID_INDICES,
    )
    t0_material_collector = t0_material_collector.fuse(t0_x_lines)
    t1_material_collector = t1_material_collector.fuse(t0_x_labels)

    t1_x_lines, t1_x_labels = create_vertical_x_alignment_group(
        bed_grid_zero=bed_grid_zero,
        x_endstop_mm=calibration["t1_x_endstop"],
        grid_indices=XY_T1_X_GRID_INDICES,
    )
    t1_material_collector = t1_material_collector.fuse(t1_x_lines)
    t0_material_collector = t0_material_collector.fuse(t1_x_labels)

    left_line_x_min_mm = grid_coordinate(zero_x_mm, -4) + XY_GRID_SEGMENT_MARGIN_MM
    left_line_x_max_mm = grid_coordinate(zero_x_mm, -3) - XY_GRID_SEGMENT_MARGIN_MM
    t0_y_lines, t0_y_labels = create_horizontal_y_alignment_group(
        bed_grid_zero=bed_grid_zero,
        y_endstop_mm=calibration["t0_y_endstop"],
        line_x_min_mm=left_line_x_min_mm,
        line_x_max_mm=left_line_x_max_mm,
        label_side="right",
    )
    t0_material_collector = t0_material_collector.fuse(t0_y_lines)
    t1_material_collector = t1_material_collector.fuse(t0_y_labels)

    right_line_x_min_mm = grid_coordinate(zero_x_mm, 4) + XY_GRID_SEGMENT_MARGIN_MM
    right_line_x_max_mm = grid_coordinate(zero_x_mm, 5) - XY_GRID_SEGMENT_MARGIN_MM
    t1_y_lines, t1_y_labels = create_horizontal_y_alignment_group(
        bed_grid_zero=bed_grid_zero,
        y_endstop_mm=calibration["t1_y_endstop"],
        line_x_min_mm=right_line_x_min_mm,
        line_x_max_mm=right_line_x_max_mm,
        label_side="left",
    )
    t1_material_collector = t1_material_collector.fuse(t1_y_lines)
    t0_material_collector = t0_material_collector.fuse(t1_y_labels)

    return t0_material_collector, t1_material_collector


def create_plate_definitions(preview_part_names=None):
    if preview_part_names is None:
        preview_part_names = ()

    return [
        {
            "name": XY_PLATE_NAME,
            "parts": [
                *preview_part_names,
                XY_T0_MATERIAL_PART_NAME,
                XY_T1_MATERIAL_PART_NAME,
            ],
        },
    ]


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()
    calibration = read_grid_calibration()
    bed_grid_zero = calibration["bed_grid_zero"]
    preview_part_names = ()

    if not PROD:
        preview_part_names = add_painted_bed_preview_parts(
            parts,
            "xy_plate",
            bed_grid_zero,
        )

    t0_material, t1_material = create_absolute_xy_alignment_materials(calibration)
    assert_absolute_patterns_fit_dual_area(
        [
            t0_material,
            t1_material,
        ]
    )

    add_calibration_part(
        parts,
        t0_material,
        XY_T0_MATERIAL_PART_NAME,
        T0_COLOR,
        CALIBRATION_PART_METADATA,
    )
    add_calibration_part(
        parts,
        t1_material,
        XY_T1_MATERIAL_PART_NAME,
        T1_COLOR,
        CALIBRATION_PART_METADATA,
    )

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=(copy_xy_offset_calibration_process_data() if PROD else None),
        prod_gap=4,
        bed_width=SAFE_BED_WIDTH_MM if PROD else ACTUAL_BED_WIDTH_MM,
        bed_depth=SAFE_BED_DEPTH_MM if PROD else ACTUAL_BED_DEPTH_MM,
        prod_origin=(
            SAFE_BED_ORIGIN
            if PROD
            else (ACTUAL_BED_ORIGIN_X_MM, ACTUAL_BED_ORIGIN_Y_MM)
        ),
        preserve_model_coordinates=PROD,
        plates=create_plate_definitions(preview_part_names),
    )

    _logger.info("single-plate two-material absolute X/Y calibration completed.")


if __name__ == "__main__":
    main()
