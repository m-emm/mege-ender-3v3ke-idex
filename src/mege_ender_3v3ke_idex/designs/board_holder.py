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
from mege_ender_3v3ke_idex.designs.leaf_spring_clamp import create_leaf_spring
from mege_ender_3v3ke_idex.designs.linear_guide import create_linear_guide
from mege_ender_3v3ke_idex.designs.mcu_housing_x_axis import (
    create_pico_w_board,
    create_tmc_board,
)
from mege_ender_3v3ke_idex.designs.sil_dil import (
    create_sil,
    dil_pitch,
    top_pin_length,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_length,
    wire_wrap_pin_side,
)
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
pico_leaf_spring_angle = 45
pico_leaf_spring_prod_rotation_axis = (0, 1, 0)
pico_leaf_spring_prod_rotation_angle = 90 - pico_leaf_spring_angle
pico_leaf_spring_thickness = 3.2

base_plate_y_size = 80
base_plate_thickness = 3.1
screw_size = "M3"
screw_hole_inset = 2.5


def create_board_holder(
    board,
    board_pcb=None,
    board_pcb_follower_name="board",
    board_cutting_part=None,
    base_plate_border=7.0,
    base_plate_border_y_ratio=1.0 / 3.0,
    base_plate_x_size_override=None,
    base_plate_y_size_override=None,
    base_plate_thickness=3.1,
    board_z_offset=electronics_boards_holder_offset,
    holder_thickness=6.0,
    holder_width=5.0,
    holder_fb_clearance=2.0,
    holder_inset=1.0,
    holder_z_offset=1.5,
    holder_guide_width=10.0,
    holder_carriage_width=5.0,
    holder_guide_thickness=None,
    holder_guide_clearance=0.35,
    holder_guide_end_border=3.0,
    holder_travel_length=3.0,
    holder_carriage_length_factor=3.0,
    holder_guide_length_factor=3.1,
    holder_board_holder_clearance=0.6,
    leaf_spring_thickness=2.0,
    leaf_spring_width=2.5,
    leaf_spring_groove_clearance=0.1,
    leaf_spring_angle=45,
    leaf_spring_preload_deflection=12,
    leaf_spring_mid_deflection=4,
    leaf_spring_holder_tower_outset=10,
    leaf_spring_holder_clearance=0.5,
    leaf_spring_holder_spring_overstand=4,
    leaf_spring_holder_tower_x_size=None,
    leaf_spring_holder_tower_y_size=None,
    leaf_spring_holder_tower_extra_height=6,
):
    """Create a board holder assembly aligned to an arbitrary board.

    Returns:
        tuple(board, holder_assembly)
    """

    if leaf_spring_holder_tower_x_size is None:
        leaf_spring_holder_tower_x_size = 4 * leaf_spring_width

    if leaf_spring_holder_tower_y_size is None:
        leaf_spring_holder_tower_y_size = 4 * leaf_spring_width

    if board_pcb is None:
        if hasattr(board, "get_follower_part_by_name"):
            board_pcb = board.get_follower_part_by_name(board_pcb_follower_name)
        else:
            board_pcb = board

    if holder_guide_thickness is None:
        holder_guide_thickness = base_plate_thickness

    def cut_with_board(part):
        if board_cutting_part is not None:
            return part.cut(board_cutting_part)
        if hasattr(board, "use_as_cutter_on"):
            return board.use_as_cutter_on(part)
        return part.cut(board)

    board_size = get_bounding_box_size(board)

    leaf_spring_length = board_size[1] + 2 * leaf_spring_holder_tower_outset

    base_plate_size = (
        (
            base_plate_x_size_override
            if base_plate_x_size_override is not None
            else board_size[0] + 2 * base_plate_border
        ),
        (
            base_plate_y_size_override
            if base_plate_y_size_override is not None
            else board_size[1] + 2 * base_plate_border * base_plate_border_y_ratio
        ),
        base_plate_thickness,
    )

    base_plate = create_box(*base_plate_size)
    base_plate = align(base_plate, board, Alignment.CENTER, axes=[0, 1])
    boards_holder_bb = get_bounding_box(base_plate)
    base_plate = translate(0, 0, -boards_holder_bb[1][2] + board_z_offset)(base_plate)
    base_plate = cut_with_board(base_plate)

    holders = PartCollector()
    right_holder = None

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        holder_length = board_size[1] - 2 * holder_fb_clearance
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

        holder = align(holder, board, Alignment.CENTER)
        holder = align(holder, board_pcb, Alignment.TOP)
        holder = align(holder, board, lr.stack_alignment)

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

        if lr == Alignment.RIGHT:
            holder_bounding_box = get_bounding_box(holder)
            leaf_spring_groove_cutter = create_box(
                leaf_spring_width + 2 * leaf_spring_groove_clearance,
                holder_length,
                4 * leaf_spring_thickness + 2 * leaf_spring_groove_clearance,
            )
            leaf_spring_groove_cutter = align(
                leaf_spring_groove_cutter, None, Alignment.CENTER, axes=[0, 1]
            )
            leaf_spring_groove_cutter = align(
                leaf_spring_groove_cutter, holder, Alignment.CENTER, axes=[1]
            )

            leaf_spring_groove_cutter = rotate(leaf_spring_angle, axis=(0, 1, 0))(
                leaf_spring_groove_cutter
            )

            leaf_spring_groove_cutter = translate(
                holder_bounding_box[1][0], 0, holder_bounding_box[1][2]
            )(leaf_spring_groove_cutter)

            cut_depth = leaf_spring_thickness + leaf_spring_groove_clearance

            x_offset = -math.cos(math.radians(leaf_spring_angle)) * (cut_depth)
            z_offset = -math.sin(math.radians(leaf_spring_angle)) * (cut_depth)

            leaf_spring_groove_cutter = translate(x_offset, 0, z_offset)(
                leaf_spring_groove_cutter
            )

            holder = holder.cut(leaf_spring_groove_cutter)

            right_holder = holder

        holders = holders.fuse(holder)

    if right_holder is None:
        raise ValueError("Right holder could not be generated.")

    holders = align(holders, base_plate, Alignment.BOTTOM)

    holder_carriage_length = holder_travel_length * holder_carriage_length_factor
    holder_guide_length = (
        holder_travel_length * holder_guide_length_factor + holder_guide_end_border
    )

    right_holder_size = get_bounding_box_size(right_holder)
    right_holder_cutter = create_box(
        right_holder_size[0] + holder_travel_length + holder_board_holder_clearance,
        right_holder_size[1] + 2 * holder_fb_clearance,
        BIG_THING,
    )
    right_holder_cutter = align(right_holder_cutter, right_holder, Alignment.CENTER)
    right_holder_cutter = align(right_holder_cutter, right_holder, Alignment.LEFT)
    right_holder_cutter = translate(-holder_board_holder_clearance, 0, 0)(
        right_holder_cutter
    )

    leaf_spring = create_leaf_spring(
        spring_length=leaf_spring_length,
        spring_thickness=leaf_spring_thickness,
        spring_height=leaf_spring_width,
        spring_mid_deflection=leaf_spring_mid_deflection,
    )

    leaf_spring_cutter = create_leaf_spring(
        spring_length=leaf_spring_length + 2 * leaf_spring_holder_clearance,
        spring_thickness=leaf_spring_thickness + 2 * leaf_spring_holder_clearance,
        spring_height=leaf_spring_width + 2 * leaf_spring_holder_clearance,
        spring_mid_deflection=leaf_spring_mid_deflection,
    )

    leaf_spring_preloaded = create_leaf_spring(
        spring_length=leaf_spring_length,
        spring_thickness=leaf_spring_thickness,
        spring_height=leaf_spring_width,
        spring_mid_deflection=leaf_spring_mid_deflection
        + leaf_spring_preload_deflection,
    )

    leaf_spring_cutter = align(leaf_spring_cutter, leaf_spring, Alignment.CENTER)
    leaf_spring_preloaded = align(leaf_spring_preloaded, leaf_spring, Alignment.CENTER)

    leaf_spring = LeaderFollowersCuttersPart(
        leader=leaf_spring, cutters=[leaf_spring_cutter]
    )
    leaf_spring.add_named_follower(leaf_spring_preloaded, "leaf_spring_preloaded")

    leaf_spring = rotate(-90, axis=(1, 0, 0))(leaf_spring)

    leaf_spring = rotate(90)(leaf_spring)
    leaf_spring = align(leaf_spring, None, Alignment.CENTER)

    leaf_spring_bbox = get_bounding_box(leaf_spring)
    leaf_spring = translate(0, 0, -leaf_spring_bbox[0][2])(leaf_spring)

    leaf_spring = rotate(leaf_spring_angle, axis=(0, 1, 0))(leaf_spring)

    leaf_spring = align(leaf_spring, right_holder, Alignment.CENTER, axes=[1])
    right_holder_bounding_box = get_bounding_box(right_holder)

    leaf_spring = translate(
        right_holder_bounding_box[1][0], 0, right_holder_bounding_box[1][2]
    )(leaf_spring)

    shift_depth = leaf_spring_thickness

    x_offset = -math.cos(math.radians(leaf_spring_angle)) * (shift_depth)
    z_offset = -math.sin(math.radians(leaf_spring_angle)) * (shift_depth)
    leaf_spring = translate(x_offset, 0, z_offset)(leaf_spring)

    base_plate_bbox = get_bounding_box(base_plate)

    leaf_spring_bbox = get_bounding_box(leaf_spring)

    leaf_spring_holder_tower_height = (
        leaf_spring_bbox[1][2]
        - base_plate_bbox[1][2]
        + leaf_spring_holder_tower_extra_height
    )

    leaf_spring_holder_towers = PartCollector()
    for fb in [Alignment.FRONT, Alignment.BACK]:
        leaf_spring_holder_tower = create_box(
            leaf_spring_holder_tower_x_size,
            leaf_spring_holder_tower_y_size,
            leaf_spring_holder_tower_height,
        )
        leaf_spring_holder_tower = align(
            leaf_spring_holder_tower, leaf_spring, Alignment.CENTER
        )

        leaf_spring_holder_tower = align(
            leaf_spring_holder_tower, base_plate, Alignment.BOTTOM
        )

        leaf_spring_holder_tower = align(leaf_spring_holder_tower, leaf_spring, fb)

        leaf_spring_holder_tower = align(
            leaf_spring_holder_tower, leaf_spring, Alignment.RIGHT
        )

        leaf_spring_holder_tower = translate(
            leaf_spring_holder_tower_x_size / 4,
            -fb.sign * leaf_spring_holder_spring_overstand,
            0,
        )(leaf_spring_holder_tower)

        leaf_spring_holder_tower = leaf_spring.use_as_cutter_on(
            leaf_spring_holder_tower
        )

        leaf_spring_holder_towers = leaf_spring_holder_towers.fuse(
            leaf_spring_holder_tower
        )

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
        # linear_guide = translate(0, -fb.sign * holder_carriage_width , 0)(linear_guide)

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

    holders = holders.fuse(carriages)

    relevant_parts_fused = holders.fuse(linear_guides).fuse(linear_guide_cutters)
    relevant_parts_bbox = get_bounding_box(relevant_parts_fused)

    right_extension_size = relevant_parts_bbox[1][0] - base_plate_bbox[1][0]
    right_extension = create_box(
        right_extension_size,
        base_plate_size[1],
        base_plate_size[2],
    )
    right_extension = align(right_extension, base_plate, Alignment.CENTER)
    right_extension = align(right_extension, base_plate, Alignment.STACK_RIGHT)

    base_plate = base_plate.fuse(leaf_spring_holder_towers)
    base_plate = base_plate.fuse(right_extension)
    base_plate = base_plate.cut(right_holder_cutter)
    base_plate = base_plate.cut(linear_guide_cutters)
    base_plate = cut_with_board(base_plate)

    holder_assembly = holders.fuse(base_plate).fuse(linear_guides)

    return board, holder_assembly, leaf_spring


def create_sil_clamp(
    num_pins, base_plate_length, base_plate_width, base_plate_thickness
):
    electronics_holder_slack = 0.1
    electronics_board_cutter_slack = 0.3
    mcu_base_cutter_vertical_slack = 0.2
    lip_size = 0.6

    pins = create_sil(
        num_y_pins=num_pins,
        pin_length=wire_wrap_pin_length,
        pin_side=wire_wrap_pin_side,
        top_pin_length=top_pin_length,
        base_thickness=wire_wrap_pin_base_thickness,
        pin_cutter_slack=0.5,
        base_cutter_slack=electronics_holder_slack,
        base_cutter_vertical_slack=mcu_base_cutter_vertical_slack,
    )

    base_plate = create_box(base_plate_length, base_plate_width, base_plate_thickness)
    base_plate = translate(0, 0, -base_plate_thickness)(base_plate)

    pins = align(pins, base_plate, Alignment.CENTER, axes=[0, 1])

    base_plate = pins.use_as_cutter_on(base_plate)

    pins_size = get_bounding_box_size(pins)

    slit_length = pins_size[1] + 4 * dil_pitch
    slit_width = 0.4

    slit_cutter = create_box(slit_width, slit_length, BIG_THING)

    slit_cutter = align(slit_cutter, pins, Alignment.CENTER)

    base_plate = base_plate.cut(slit_cutter)

    lip = create_right_triangle(
        lip_size,
        lip_size,
        pins_size[1],
        extrusion_direction=(0, 1, 0),
        a_normal=(1, 0, 0),
        b_normal=(0, 0, -1),
    )
    lip = align(lip, pins, Alignment.CENTER)
    lip = align(lip, pins, Alignment.RIGHT)
    lip = translate(electronics_holder_slack, 0, 0)(lip)
    lip = align(lip, base_plate, Alignment.TOP)

    base_plate = base_plate.fuse(lip)

    pins.add_named_follower(base_plate, "base_plate")

    pins = pins.fuse(pins.get_follower_part_by_name("top_pins"))

    return pins


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    pico = create_pico_w_board()

    pico_holder_tower_x_size = 10
    pico_holder_tower_y_size = 5
    pico_board, pico_holders, pico_leaf_spring = create_board_holder(
        board=pico,
        base_plate_border=7.0,
        base_plate_thickness=base_plate_thickness,
        base_plate_y_size_override=base_plate_y_size,
        leaf_spring_angle=pico_leaf_spring_angle,
        leaf_spring_holder_tower_x_size=pico_holder_tower_x_size,
        leaf_spring_holder_tower_y_size=pico_holder_tower_y_size,
        leaf_spring_thickness=pico_leaf_spring_thickness,
    )
    with_tmc = True

    if with_tmc:
        tmc = create_tmc_board()

        tmc = align(tmc, pico, Alignment.FRONT)

        tmc_2 = align(tmc, pico, Alignment.BACK)
        tmc_2 = tmc_2.prefixed_copy("tmc_2")

        tmc = tmc.fuse(tmc_2)

        tmc_board, tmc_holders, tmc_leaf_spring = create_board_holder(
            board=tmc,
            base_plate_border=7.0,
            base_plate_thickness=base_plate_thickness,
            base_plate_y_size_override=base_plate_y_size,
            leaf_spring_angle=pico_leaf_spring_angle,
            leaf_spring_holder_tower_x_size=pico_holder_tower_x_size,
            leaf_spring_holder_tower_y_size=pico_holder_tower_y_size,
            leaf_spring_thickness=pico_leaf_spring_thickness,
        )

        holder_gap_x = 0
        pico_holders_bbox = get_bounding_box(pico_holders)
        tmc_holders_bbox = get_bounding_box(tmc_holders)
        tmc_x_offset = pico_holders_bbox[1][0] - tmc_holders_bbox[0][0] + holder_gap_x

        tmc_board = translate(tmc_x_offset, 0, 0)(tmc_board)
        tmc_holders = translate(tmc_x_offset, 0, 0)(tmc_holders)

        parts.add(tmc_board, "tmc_board", flip=False, skip_in_production=True)

    parts.add(pico_board, "pico_w_board", flip=False, skip_in_production=True)

    all_holders = pico_holders
    if with_tmc:
        all_holders = all_holders.fuse(tmc_holders)

    additional_pins = create_sil_clamp(
        num_pins=20,
        base_plate_length=6,
        base_plate_width=base_plate_y_size,
        base_plate_thickness=base_plate_thickness,
    )
    additional_pins = additional_pins.prefixed_copy("additional_pins")

    align_pins_translation = align_translation(
        additional_pins.get_follower_part_by_name("additional_pins_base_plate"),
        all_holders,
        Alignment.CENTER,
        axes=[1],
    )
    additional_pins = align_pins_translation(additional_pins)

    align_pins_translation = align_translation(
        additional_pins.get_follower_part_by_name("additional_pins_base_plate"),
        all_holders,
        Alignment.STACK_RIGHT,
    )

    additional_pins = align_pins_translation(additional_pins)

    parts.add(additional_pins, "additional_pins", flip=False, skip_in_production=True)

    all_holders = all_holders.fuse(
        additional_pins.get_follower_part_by_name("additional_pins_base_plate")
    )

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            screw_hole = create_cylinder(
                MScrew.from_size(screw_size).clearance_hole_normal / 2, BIG_THING
            )
            screw_hole = align(screw_hole, all_holders, Alignment.CENTER)
            screw_hole = align(screw_hole, all_holders, lr)
            screw_hole = align(screw_hole, all_holders, fb)
            screw_hole = translate(
                -lr.sign * screw_hole_inset, -fb.sign * screw_hole_inset, 0
            )(screw_hole)

            all_holders = all_holders.cut(screw_hole)

    parts.add(
        all_holders, "holders", flip=False
    )  # parts.add(tmc_holders, "holders_tmc", flip=False)
    # parts.add(pico_holders, "holders_pico", flip=False)

    parts.add(
        pico_leaf_spring,
        "leaf_spring_pico",
        flip=False,
        prod_rotation_angle=pico_leaf_spring_prod_rotation_angle,
        prod_rotation_axis=pico_leaf_spring_prod_rotation_axis,
        skip_in_production=True,  # we dont print the unpreloaded spring, only the preloaded one
    )

    parts.add(
        pico_leaf_spring.get_follower_part_by_name("leaf_spring_preloaded"),
        "leaf_spring_pico_preloaded",
        flip=False,
        prod_rotation_angle=pico_leaf_spring_prod_rotation_angle,
        prod_rotation_axis=pico_leaf_spring_prod_rotation_axis,
        skip_in_production=False,  # we print the preloaded spring
    )

    parts.add(
        tmc_leaf_spring,
        "leaf_spring_tmc",
        flip=False,
        prod_rotation_angle=pico_leaf_spring_prod_rotation_angle,
        prod_rotation_axis=pico_leaf_spring_prod_rotation_axis,
        skip_in_production=True,  # we dont print the unpreloaded spring, only the preloaded one
    )

    parts.add(
        tmc_leaf_spring.get_follower_part_by_name("leaf_spring_preloaded"),
        "leaf_spring_tmc_preloaded",
        flip=False,
        prod_rotation_angle=pico_leaf_spring_prod_rotation_angle,
        prod_rotation_axis=pico_leaf_spring_prod_rotation_axis,
        skip_in_production=False,  # we print the preloaded spring
    )

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        prod_gap=5,
    )

    _logger.info("board_holder created successfully!")


if __name__ == "__main__":
    main()
