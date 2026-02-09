"""
Bt Pi Tft 43

Usage:
    cd <project_root> && ./run.sh path/to/bt_pi_tft_43.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/bt_pi_tft_43.py
"""

import copy
import logging
import math
import os

import numpy as np
from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLACF_04_HS)

PROCESS_DATA["process_overrides"].update(
    {
        "wall_loops": "2",
        "bottom_shell_layers": "1",
        "top_shell_layers": "1",
        "sparse_infill_density": "25%",
    }
)

BIG_THING = 500

tft_height = 67.3
tft_width = 105.75
tft_with_board_thickness = 7.6
tft_screw_holder_height = 6.2
tft_screw_holder_diameter = 5.52
tft_screw_size = "M3"
tft_screw_holders_envelope_width = 102.92
tft_screw_holders_envelope_height = 64.5

tft_screw_holders_center_to_center_distance_width = (
    tft_screw_holders_envelope_width - tft_screw_holder_diameter
)
tft_screw_holders_center_to_center_distance_height = (
    tft_screw_holders_envelope_height - tft_screw_holder_diameter
)

tft_screw_holders_inset = (tft_width - tft_screw_holders_envelope_width) / 2

tft_cable_width = 16
tft_cable_clearance = 1

tft_screen_clearance = 0.2
tft_button_2_offset = 26
tft_button_1_offset = 13.7

raspi_width = 55.6
raspi_flight_height = 24
raspi_inward_offset = 10
raspi_connections_height = 17.2

raspi_board_length = 84.88
raspi_connectors_oversize = 1

tft_housing_wall_thickness = 1.5
tft_housing_border = 20
tft_housing_fillet_radius = 4

tft_housing_height = 60
tft_housing_front_screen_thickness = 2.5
tft_housing_lip_size = 0.75
tft_housing_screw_plate_size = 6
tft_housing_screw_plate_thickness = 2

tft_housing_air_hole_size = 4
tft_housing_air_hole_spacing = 10
tft_air_hole_border = 5


def creaate_tft():

    tft_with_board = create_box(tft_width, tft_height, tft_with_board_thickness)

    screw_holders = []
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for tb in [Alignment.FRONT, Alignment.BACK]:
            screw_holder = create_cylinder(
                tft_screw_holder_diameter / 2, tft_screw_holder_height
            )
            screw_holder = align(screw_holder, tft_with_board, lr)
            screw_holder = align(screw_holder, tft_with_board, tb)
            screw_holder = align(screw_holder, tft_with_board, Alignment.STACK_TOP)

            screw_holder = translate(
                -lr.sign * tft_screw_holders_inset,
                -tb.sign * tft_screw_holders_inset,
                0,
            )(screw_holder)
            screw_holders.append(screw_holder)

    for screw_holder in screw_holders:
        tft_with_board = tft_with_board.fuse(screw_holder)

    retval = LeaderFollowersCuttersPart(
        tft_with_board, followers=screw_holders, cutters=[]
    )

    return retval


def create_housing(tft):

    housing = create_filleted_box(
        tft_width
        + 2 * tft_housing_border
        + 2 * tft_screen_clearance
        + 2 * tft_housing_wall_thickness,
        tft_height
        + 2 * tft_housing_border
        + 2 * tft_screen_clearance
        + 2 * tft_housing_wall_thickness,
        tft_housing_height,
        fillet_radius=tft_housing_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    housing_cutter = create_box(
        tft_width + 2 * tft_screen_clearance + 2 * tft_housing_border,
        tft_height + 2 * tft_screen_clearance + 2 * tft_housing_border,
        BIG_THING,
    )
    housing_cutter = align(housing_cutter, housing, Alignment.CENTER)
    housing_cutter = align(housing_cutter, housing, Alignment.BOTTOM)
    housing_cutter = translate(0, 0, tft_housing_front_screen_thickness)(housing_cutter)

    housing = housing.cut(housing_cutter)

    screen_cutter = create_box(
        tft_width + 2 * tft_screen_clearance,
        tft_height + 2 * tft_screen_clearance,
        BIG_THING,
    )
    screen_cutter = align(screen_cutter, housing, Alignment.CENTER)

    housing = housing.cut(screen_cutter)

    housing = align(housing, tft, Alignment.CENTER)
    housing = align(housing, tft, Alignment.BOTTOM)

    housing_size = get_bounding_box_size(housing)

    num_air_holes_width = math.floor(
        (housing_size[0] - 2 * tft_air_hole_border) / tft_housing_air_hole_spacing
    )
    num_air_holes_height = math.floor(
        (housing_size[1] - 2 * tft_air_hole_border) / tft_housing_air_hole_spacing
    )

    num_air_holes_z = math.ceil(
        (housing_size[2] - 2 * tft_air_hole_border) / tft_housing_air_hole_spacing
    )

    air_holes_width = PartCollector()
    for i in range(num_air_holes_width):
        for j in range(num_air_holes_z):
            air_hole_cutter = create_box(
                tft_housing_air_hole_size, BIG_THING, tft_housing_air_hole_size
            )

            air_hole_cutter = rotate(45, axis=(0, 1, 0))(air_hole_cutter)

            air_hole_cutter = translate(
                i * tft_housing_air_hole_spacing, 0, j * tft_housing_air_hole_spacing
            )(air_hole_cutter)
            air_holes_width = air_holes_width.fuse(air_hole_cutter)

    air_holes_width = align(air_holes_width, housing, Alignment.CENTER)

    housing = housing.cut(air_holes_width)

    air_holes_height = PartCollector()
    for i in range(num_air_holes_height):
        for j in range(num_air_holes_z):
            air_hole_cutter = create_box(
                BIG_THING,
                tft_housing_air_hole_size,
                tft_housing_air_hole_size,
            )

            air_hole_cutter = rotate(45, axis=(1, 0, 0))(air_hole_cutter)

            air_hole_cutter = translate(
                0, i * tft_housing_air_hole_spacing, j * tft_housing_air_hole_spacing
            )(air_hole_cutter)
            air_holes_height = air_holes_height.fuse(air_hole_cutter)

    air_holes_height = align(air_holes_height, housing, Alignment.CENTER)
    housing = housing.cut(air_holes_height)

    all_directions = [Alignment.LEFT, Alignment.RIGHT, Alignment.FRONT, Alignment.BACK]

    screw_plates = PartCollector()

    tft_center = np.array(get_bounding_box_center(tft))

    bridges = PartCollector()
    for screw_holder in tft.followers:
        screw_plate = create_box(
            tft_housing_screw_plate_size,
            tft_housing_screw_plate_size,
            tft_housing_screw_plate_thickness,
        )

        screw_hole_diameter = MScrew.from_size(tft_screw_size).clearance_hole_normal
        screw_hole = create_cylinder(screw_hole_diameter / 2, BIG_THING)
        screw_hole = align(screw_hole, screw_plate, Alignment.CENTER)
        screw_plate = screw_plate.cut(screw_hole)
        screw_plate = align(screw_plate, screw_holder, Alignment.CENTER)
        screw_plate = align(screw_plate, screw_holder, Alignment.STACK_TOP)

        screw_plates = screw_plates.fuse(screw_plate)

        screw_holder_center = np.array(get_bounding_box_center(screw_holder))

        direction_vector = screw_holder_center - tft_center
        direction_vector_signs = [int(math.copysign(1, v)) for v in direction_vector]

        _logger.info(
            f"Direction vector: {direction_vector}, signs: {direction_vector_signs}"
        )
        for direction in all_directions:
            if (
                direction_vector_signs[0] == direction.sign and direction.axis == 0
            ) or (direction_vector_signs[1] == direction.sign and direction.axis == 1):
                _logger.info(
                    f"Using direction {direction} for screw holder at {screw_holder_center}, direction signs  {direction_vector_signs} direction sign {direction.sign} and direction axis {direction.axis}"
                )
                bridge_length = (
                    tft_housing_border
                    + tft_screen_clearance
                    + tft_housing_wall_thickness * 0.25
                    + tft_screw_holders_inset
                )
                bridge = create_box(
                    (
                        tft_housing_screw_plate_size
                        if direction.axis == 1
                        else bridge_length
                    ),
                    (
                        tft_housing_screw_plate_size
                        if direction.axis == 0
                        else bridge_length
                    ),
                    tft_housing_screw_plate_thickness,
                )
                bridge = align(bridge, screw_plate, Alignment.CENTER)
                bridge = align(bridge, screw_plate, direction.stack_alignment)
                bridges = bridges.fuse(bridge)

                print_helper = create_right_triangle(
                    bridge_length,
                    bridge_length,
                    tft_housing_screw_plate_size,
                    extrusion_direction=(
                        1 if direction.axis == 1 else 0,
                        1 if direction.axis == 0 else 0,
                        0,
                    ),
                    a_normal=(
                        direction.sign if direction.axis == 0 else 0,
                        direction.sign if direction.axis == 1 else 0,
                        0,
                    ),
                    b_normal=(0, 0, 1),
                )

                print_helper = align(print_helper, bridge, Alignment.CENTER)

                print_helper = align(
                    print_helper, screw_plate, direction.stack_alignment
                )
                print_helper = align(print_helper, bridge, Alignment.STACK_TOP)
                bridges = bridges.fuse(print_helper)

    housing_size = get_bounding_box_size(housing)
    housing_inner_length = (
        housing_size[0] - 2 * tft_housing_wall_thickness - 2 * tft_housing_fillet_radius
    )
    housing_inner_width = (
        housing_size[1] - 2 * tft_housing_wall_thickness - 2 * tft_housing_fillet_radius
    )

    border_print_helpers = []
    helper_size = (
        tft_housing_border + tft_screen_clearance + tft_housing_wall_thickness / 2
    )

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        _logger.info(
            f"Creating border print helper for {lr} with helper size {helper_size} and housing inner length {housing_inner_length}"
        )

        border_print_helper = create_right_triangle(
            helper_size,
            helper_size,
            housing_inner_width,
            extrusion_direction=(0, 1, 0),
            a_normal=(lr.sign, 0, 0),
            b_normal=(0, 0, 1),
        )
        border_print_helper = align(border_print_helper, housing, Alignment.CENTER)
        border_print_helper = align(border_print_helper, housing, Alignment.BOTTOM)
        border_print_helper = align(border_print_helper, housing, lr)

        border_print_helper = translate(
            0, 0, tft_housing_front_screen_thickness - 1e-1
        )(border_print_helper)

        border_print_helpers.append(border_print_helper)

    for fb in [Alignment.FRONT, Alignment.BACK]:
        _logger.info(
            f"Creating border print helper for {fb} with helper size {helper_size} and housing inner length {housing_inner_length}"
        )
        border_print_helper = create_right_triangle(
            helper_size,
            helper_size,
            housing_inner_length,
            extrusion_direction=(1, 0, 0),
            a_normal=(0, fb.sign, 0),
            b_normal=(0, 0, 1),
        )
        border_print_helper = align(border_print_helper, housing, Alignment.CENTER)
        border_print_helper = align(border_print_helper, housing, Alignment.BOTTOM)

        border_print_helper = align(border_print_helper, housing, fb)
        border_print_helper = translate(
            0, 0, tft_housing_front_screen_thickness - 1e-1
        )(border_print_helper)

        border_print_helpers.append(border_print_helper)

    border_print_helpers_part_collector = PartCollector()
    for i, bph in enumerate(border_print_helpers):
        _logger.info(
            f"Adding border print helper to part collector: {i} / {len(border_print_helpers)}"
        )
        border_print_helpers_part_collector = border_print_helpers_part_collector.fuse(
            bph
        )

    border_print_helpers = translate(0, 0, 100)(border_print_helpers_part_collector)
    housing = housing.fuse(border_print_helpers_part_collector)

    housing = housing.fuse(bridges)
    housing = housing.fuse(screw_plates)

    return housing


def create_bt_pi_tft_43():
    """Create the bt_pi_tft_43 part."""
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
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = creaate_tft()
    parts.add(part, "bt_pi_tft_43", flip=False, skip_in_production=True)

    housing = create_housing(part)
    parts.add(housing, "bt_pi_tft_43_housing", flip=True)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("bt_pi_tft_43 created successfully!")


if __name__ == "__main__":
    main()
