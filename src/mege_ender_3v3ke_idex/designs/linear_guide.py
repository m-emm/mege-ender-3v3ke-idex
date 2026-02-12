"""
Linear Guide

Usage:
    cd <project_root> && ./run.sh path/to/linear_guide.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/linear_guide.py
"""

import copy
import logging
import math
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.spring import create_spring
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLACF_04_HS)

PROCESS_DATA["process_overrides"].update(
    {
        "wall_loops": "1",
        "bottom_shell_layers": "1",
        "top_shell_layers": "1",
        "sparse_infill_density": "25%",
        "brim_type": "no_brim",
    }
)

BIG_THING = 500


def create_linear_guide(
    carriage_width,
    carriage_length,
    guide_length,
    guide_width,
    thickness,
    guide_end_border,
    guide_clearance=0.1,
    skip_back_end_border=False,
):
    """Create the linear_guide part."""

    guide_rail_side = thickness * math.sqrt(2) / 2
    inner_length = guide_length - 2 * guide_end_border
    if skip_back_end_border:
        inner_length += guide_end_border

    carriage = create_box(carriage_width, carriage_length, thickness)

    carriage_rails = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        carriage_guide_rail = create_box(
            guide_rail_side, carriage_length, guide_rail_side
        )

        carriage_guide_rail = rotate(45, axis=(0, 1, 0))(carriage_guide_rail)
        carriage_guide_rail = align(carriage_guide_rail, carriage, Alignment.CENTER)
        carriage_guide_rail = align(carriage_guide_rail, carriage, lr)
        carriage_guide_rail = translate(lr.sign * thickness / 2, 0, 0)(
            carriage_guide_rail
        )
        carriage_rails = carriage_rails.fuse(carriage_guide_rail)

    guide_frame = create_box(guide_width, guide_length, thickness)
    guide_frame = align(guide_frame, carriage, Alignment.CENTER)

    guide_raw_cutter = create_box(
        carriage_width + 2 * guide_clearance, inner_length, BIG_THING
    )
    guide_raw_cutter = align(guide_raw_cutter, guide_frame, Alignment.CENTER)
    if skip_back_end_border:
        guide_raw_cutter = align(guide_raw_cutter, guide_frame, Alignment.BACK)

    guide_frame = guide_frame.cut(guide_raw_cutter)

    guide_cutters = PartCollector()

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        guide_cut = create_box(guide_rail_side, inner_length, guide_rail_side)
        guide_cut = rotate(45, axis=(0, 1, 0))(guide_cut)
        guide_cut = align(guide_cut, carriage, Alignment.CENTER)
        guide_cut = align(guide_cut, carriage, lr)
        guide_cut = translate(lr.sign * (guide_clearance + thickness / 2), 0, 0)(
            guide_cut
        )
        if skip_back_end_border:
            guide_cut = align(guide_cut, guide_frame, Alignment.BACK)

        guide_cutters = guide_cutters.fuse(guide_cut)

    guide_frame = guide_frame.cut(guide_cutters)
    carriage = carriage.fuse(carriage_rails)

    retval = LeaderFollowersCuttersPart(guide_frame)
    retval.add_named_follower(carriage, "carriage")

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    carriage_width = 18
    carriage_length = 20
    guide_length = 80
    guide_width = 35
    thickness = 3.5
    guide_end_border = 5
    guide_clearance = 0.4
    spring_thickness = 1.8
    spring_pitch = 6
    # Keep the old physical spring span: 6 turns with 3 mm connector on each side.
    spring_total_length = 43.8

    # Create the part
    linear_guide = create_linear_guide(
        carriage_width=carriage_width,
        carriage_length=carriage_length,
        guide_length=guide_length,
        guide_width=guide_width,
        thickness=thickness,
        guide_end_border=guide_end_border,
        guide_clearance=guide_clearance,
    )

    spring = create_spring(
        spring_thickness=spring_thickness,
        spring_height=thickness,
        spring_width=carriage_width - 4,
        spring_pitch=spring_pitch,
        spring_total_length=spring_total_length,
    )

    spring = align(spring, linear_guide, Alignment.CENTER)

    spring = align(spring, linear_guide, Alignment.FRONT)

    spring = translate(0, guide_end_border, 0)(spring)

    carriage = linear_guide.get_follower_part_by_name("carriage")

    carriage = align(carriage, spring, Alignment.STACK_BACK)

    all = spring.fuse(carriage).fuse(linear_guide.leader)
    parts.add(all, "linear_guide_with_spring", flip=False)

    # parts.add(spring, "spring", flip=False)

    # parts.add(linear_guide, "linear_guide", flip=False)

    # parts.add(carriage, "carriage", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("linear_guide created successfully!")


if __name__ == "__main__":
    main()
