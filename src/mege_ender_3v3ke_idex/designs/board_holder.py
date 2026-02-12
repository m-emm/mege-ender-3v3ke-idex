"""
Board Holder

Usage:
    cd <project_root> && ./run.sh path/to/board_holder.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/board_holder.py
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
from mege_ender_3v3ke_idex.designs.linear_guide import create_linear_guide
from mege_ender_3v3ke_idex.designs.mcu_housing_x_axis import create_pico_w_board
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

electronics_boards_holder_offset = 0.005


def create_board_holder():
    """Create the board_holder part."""
    # Example: simple box with a cylindrical hole
    width = 30
    depth = 20
    height = 10
    hole_radius = 4

    # Create base box
    part = create_box(width, depth, height)

    # Create a hole cutter
    hole = create_cylinder(hole_radius, height + 2)
    hole = align(hole, part, Alignment.CENTER)
    hole = translate(0, 0, -1)(hole)

    # Cut the hole
    part = part.cut(hole)

    return part


def main():

    base_plate_border = 10
    base_plate_thickness = 3.1

    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    pico = create_pico_w_board()

    pico_pcb = pico.get_follower_part_by_name("board")
    pico_dil = pico.get_follower_part_by_name("dil")

    parts.add(pico, "pico_w_board", flip=False, skip_in_production=True)

    pico_size = get_bounding_box_size(pico)

    base_plate_size = (
        pico_size[0] + 2 * base_plate_border,
        pico_size[1] + 2 * base_plate_border / 3,
        base_plate_thickness,
    )

    base_plate = create_box(*base_plate_size)

    base_plate = align(base_plate, pico, Alignment.CENTER, axes=[0, 1])
    boards_holder_bb = get_bounding_box(base_plate)
    base_plate = translate(
        0, 0, -boards_holder_bb[1][2] + electronics_boards_holder_offset
    )(base_plate)

    base_plate = pico.use_as_cutter_on(base_plate)

    holder_thickness = 5
    holder_width = 5
    holder_fb_clearance = 2
    holder_inset = 1.2
    holder_z_offset = 1.5

    holders = PartCollector()

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        holder_length = pico_size[1] - 2 * holder_fb_clearance
        holder = create_box(holder_width, holder_length, holder_thickness)

        holder_cutter_side_size = holder_thickness / math.sqrt(2)
        holder_cutter = create_box(
            holder_cutter_side_size, BIG_THING, holder_cutter_side_size
        )
        holder_cutter = rotate(45, axis=(0, 1, 0))(holder_cutter)
        holder_cutter = align(holder_cutter, holder, Alignment.CENTER)
        holder_cutter = align(holder_cutter, holder, lr.opposite)
        holder_cutter = translate(-lr.sign * holder_thickness / 2, 0, 0)(holder_cutter)
        holder = holder.cut(holder_cutter)
        holder = align(holder, pico_pcb, Alignment.CENTER)
        holder = align(holder, pico_pcb, Alignment.TOP)
        holder = align(holder, pico, lr.stack_alignment)
        inset_x_offset = -lr.sign * holder_inset if lr == Alignment.RIGHT else 0

        holder = translate(inset_x_offset, 0, holder_z_offset)(holder)

        if lr == Alignment.LEFT:
            holder_bottom_cutter = create_box(
                holder_thickness / 2, holder_length, holder_thickness / 2
            )
            holder_bottom_cutter = align(holder_bottom_cutter, holder, Alignment.CENTER)
            holder_bottom_cutter = align(holder_bottom_cutter, holder, Alignment.BOTTOM)
            holder_bottom_cutter = align(holder_bottom_cutter, holder, Alignment.RIGHT)
            holder = holder.cut(holder_bottom_cutter)

        holders = holders.fuse(holder)
        if lr == Alignment.RIGHT:
            right_holder = holder

    holders = align(holders, base_plate, Alignment.BOTTOM)

    holder_guide_width = 10

    holder_carriage_width = 5
    holder_guide_thickness = base_plate_thickness
    holder_guide_clearance = 0.4
    holder_guide_end_border = 1
    holder_travel_length = 4
    holder_carriage_length = holder_travel_length * 3

    central_spring_width = 7
    central_spring_clearance = 1.0
    central_spring_thickness = 0.85

    right_holder_size = get_bounding_box_size(right_holder)
    right_holder_cutter = create_box(
        right_holder_size[0] + holder_travel_length,
        right_holder_size[1] + 2 * holder_fb_clearance,
        BIG_THING,
    )
    right_holder_cutter = align(right_holder_cutter, right_holder, Alignment.CENTER)
    right_holder_cutter = align(right_holder_cutter, right_holder, Alignment.LEFT)

    holder_guide_length = holder_travel_length * 3.1 + holder_guide_end_border

    linear_guides = PartCollector()
    carriages = PartCollector()
    linear_guide_cutters = PartCollector()

    for fb in [Alignment.FRONT, Alignment.BACK]:

        linear_guide = create_linear_guide(
            guide_length=holder_guide_length,
            guide_width=holder_guide_width,
            carriage_length=holder_carriage_length,
            carriage_width=holder_carriage_width,
            thickness=holder_guide_thickness,
            guide_end_border=holder_guide_end_border,
            guide_clearance=holder_guide_clearance,
            skip_back_end_border=True,
        )

        linear_guide = rotate(90)(linear_guide)

        linear_guide = align(linear_guide, holders, Alignment.CENTER)
        linear_guide = align(linear_guide, holders, Alignment.BOTTOM)
        linear_guide = align(
            linear_guide, holders, Alignment.STACK_RIGHT, stack_gap=holder_travel_length
        )
        linear_guide = align(linear_guide, holders, fb)
        linear_guide = translate(0, -fb.sign * holder_width * 2, 0)(linear_guide)

        linear_guides = linear_guides.fuse(linear_guide.leader)

        linear_guide_size = get_bounding_box_size(linear_guide)

        linear_guide_cutter = create_box(
            linear_guide_size[0] + 2 * holder_inset, linear_guide_size[1], BIG_THING
        )

        linear_guide_cutter = align(linear_guide_cutter, linear_guide, Alignment.CENTER)
        linear_guide_cutter = align(linear_guide_cutter, linear_guide, Alignment.RIGHT)

        linear_guide_cutters = linear_guide_cutters.fuse(linear_guide_cutter)

        carriage = linear_guide.get_follower_part_by_name("carriage")
        carriage = align(carriage, holders, Alignment.STACK_RIGHT)

        carriages = carriages.fuse(carriage)

    central_spring_length = 4 * holder_travel_length

    central_spring_cutter = create_box(
        central_spring_length,
        central_spring_width + 2 * central_spring_clearance,
        BIG_THING,
    )
    central_spring_cutter = align(central_spring_cutter, holders, Alignment.CENTER)
    central_spring_cutter = align(central_spring_cutter, holders, Alignment.BOTTOM)
    central_spring_cutter = align(central_spring_cutter, holders, Alignment.STACK_RIGHT)

    central_spring = create_spring(
        spring_thickness=central_spring_thickness,
        spring_height=base_plate_thickness,
        spring_width=central_spring_width,
        spring_pitch=central_spring_thickness * 2.5,
        spring_total_length=central_spring_length,
    )

    central_spring = rotate(90)(central_spring)
    central_spring = align(central_spring, holders, Alignment.CENTER)
    central_spring = align(central_spring, holders, Alignment.BOTTOM)
    central_spring = align(central_spring, holders, Alignment.STACK_RIGHT)

    holders = holders.fuse(carriages)

    base_plate_bbox = get_bounding_box(base_plate)
    relevant_parts_fused = (
        holders.fuse(linear_guides)
        .fuse(central_spring)
        .fuse(linear_guide_cutters)
        .fuse(central_spring_cutter)
    )
    relevant_parts_bbox = get_bounding_box(relevant_parts_fused)

    right_extenxion_size = relevant_parts_bbox[1][0] - base_plate_bbox[1][0]
    right_extenxion = create_box(
        right_extenxion_size,
        base_plate_size[1],
        base_plate_size[2],
    )

    right_extenxion = align(right_extenxion, base_plate, Alignment.CENTER)
    right_extenxion = align(right_extenxion, base_plate, Alignment.STACK_RIGHT)

    base_plate = base_plate.fuse(right_extenxion)

    base_plate = base_plate.cut(right_holder_cutter)
    base_plate = base_plate.cut(linear_guide_cutters)
    base_plate = pico.use_as_cutter_on(base_plate)

    base_plate = base_plate.cut(central_spring_cutter)

    holders = holders.fuse(base_plate)
    holders = holders.fuse(linear_guides)
    holders = holders.fuse(central_spring)

    parts.add(holders, f"holders", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("board_holder created successfully!")


if __name__ == "__main__":
    main()
