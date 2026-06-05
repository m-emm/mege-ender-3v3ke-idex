"""Two-material IDEX X/Y offset calibration cross.

Usage:
    cd <project_root> && ./run.sh --slice path/to/two_material_offset_cross_calibration.py
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

CALIBRATION_HEIGHT_MM = 1.5
CENTER_VOID_MM = 3
CENTER_GAP_MM = 0.8
ARM_LENGTH_MM = 28.0
ARM_WIDTH_MM = 2.0

T0_COLOR = (0.95, 0.08, 0.04)
T1_COLOR = (0.0, 0.32, 1.0)


def create_offset_cross_materials():
    center_void = create_box(CENTER_VOID_MM, CENTER_VOID_MM, CALIBRATION_HEIGHT_MM)
    center_void = align(center_void, None, Alignment.CENTER, axes=[0, 1])

    left_arm = create_box(ARM_LENGTH_MM, ARM_WIDTH_MM, CALIBRATION_HEIGHT_MM)
    left_arm = align(left_arm, center_void, Alignment.CENTER, axes=[1])
    left_arm = align(
        left_arm, center_void, Alignment.STACK_LEFT, stack_gap=CENTER_GAP_MM
    )

    right_arm = create_box(ARM_LENGTH_MM, ARM_WIDTH_MM, CALIBRATION_HEIGHT_MM)
    right_arm = align(right_arm, center_void, Alignment.CENTER, axes=[1])
    right_arm = align(
        right_arm, center_void, Alignment.STACK_RIGHT, stack_gap=CENTER_GAP_MM
    )

    top_arm = create_box(ARM_WIDTH_MM, ARM_LENGTH_MM, CALIBRATION_HEIGHT_MM)
    top_arm = align(top_arm, center_void, Alignment.CENTER, axes=[0])
    top_arm = align(top_arm, center_void, Alignment.STACK_BACK, stack_gap=CENTER_GAP_MM)

    bottom_arm = create_box(ARM_WIDTH_MM, ARM_LENGTH_MM, CALIBRATION_HEIGHT_MM)
    bottom_arm = align(bottom_arm, center_void, Alignment.CENTER, axes=[0])
    bottom_arm = align(
        bottom_arm, center_void, Alignment.STACK_FRONT, stack_gap=CENTER_GAP_MM
    )

    t0_collector = PartCollector()
    t0_collector = t0_collector.fuse(left_arm)
    t0_collector = t0_collector.fuse(top_arm)

    t1_collector = PartCollector()
    t1_collector = t1_collector.fuse(right_arm)
    t1_collector = t1_collector.fuse(bottom_arm)

    all = t0_collector.fuse(t1_collector)


    t0_bar = create_box(2*ARM_LENGTH_MM + CENTER_VOID_MM + 2*CENTER_GAP_MM, 4*ARM_WIDTH_MM, CALIBRATION_HEIGHT_MM)
    t0_bar = align(t0_bar, all, Alignment.CENTER)
    t0_bar = align(t0_bar, all, Alignment.STACK_BACK, stack_gap=4*ARM_WIDTH_MM)

    t0_collector = t0_collector.fuse(t0_bar)

    t1_bar = align(t0_bar, all, Alignment.STACK_FRONT, stack_gap=4*ARM_WIDTH_MM)

    t1_collector = t1_collector.fuse(t1_bar)


    radius_step = 2


    t1_rings = PartCollector()
    t2_rings = PartCollector()
    for i in range(10):
        cur_radius = (i+2)*radius_step
        ring = create_ring(cur_radius, cur_radius-radius_step, CALIBRATION_HEIGHT_MM)

        if i % 2 == 0:
            t1_rings = t1_rings.fuse(ring)
        else:
            t2_rings = t2_rings.fuse(ring)


    rings_aligner = align_translation(t1_rings, all, Alignment.CENTER)
    rings_aligner = align_translation(t1_rings, all, Alignment.STACK_RIGHT, stack_gap=2*ARM_WIDTH_MM)

    t1_rings =  rings_aligner(t1_rings)
    t2_rings =  rings_aligner(t2_rings)

    t1_collector = t1_collector.fuse(t1_rings)
    t0_collector = t0_collector.fuse(t2_rings)







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

    t0_part, t1_part = create_offset_cross_materials()
    assert_pattern_fits_dual_area([t0_part, t1_part])

    parts.add(
        t0_part,
        "offset_cross_t0_left_top",
        color=T0_COLOR,
        obj_metadata={
            "production_group": "offset_cross",
            "slicer_filament_id": 1,
            "tool": "T0",
        },
    )
    parts.add(
        t1_part,
        "offset_cross_t1_right_bottom",
        color=T1_COLOR,
        obj_metadata={
            "production_group": "offset_cross",
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

    _logger.info("two-material offset cross calibration design completed.")


if __name__ == "__main__":
    main()
