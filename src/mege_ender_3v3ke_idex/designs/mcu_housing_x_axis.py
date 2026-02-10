"""
Mcu Housing X Axis

Usage:
    cd <project_root> && ./run.sh path/to/mcu_housing_x_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/mcu_housing_x_axis.py
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
from mege_ender_3v3ke_idex.designs.sil_dil import (
    create_dil_board,
    dil_pitch,
    pcb_thickness,
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
        "wall_loops": "2",
        "bottom_shell_layers": "1",
        "top_shell_layers": "1",
        "sparse_infill_density": "25%",
        "brim_type": "no_brim",
    }
)

BIG_THING = 500

PLATE_THICKNESS = 2.0
PLATE_BORDER = 6.0

PIN_LENGTH_BELOW_BOARD = wire_wrap_pin_length
PIN_SLOT_SLACK = 0.20
BOARD_CORNER_RADIUS = 0.25 * dil_pitch

PICO_BOARD_THICKNESS = pcb_thickness
TMC_BOARD_THICKNESS = 1.6

PICO_NUM_PINS_PER_ROW = 20
PICO_ROW_SPACING = 8 * dil_pitch
PICO_BOARD_WIDTH = 21.0
PICO_BOARD_LENGTH = 51.0

TMC_NUM_PINS_PER_ROW = 8
TMC_ROW_SPACING = 4 * dil_pitch
TMC_BOARD_WIDTH = 15.2
TMC_BOARD_LENGTH = 20.3

# Approximate board placement from klipper_setup/klipper_config/pico_w_btt_tmc2226.yaml:
# PICO origin [0,20], TMC1 origin [20,18], TMC2 origin [20,9]
PICO_TO_DRIVER_RIGHT_GAP = 3.5 * dil_pitch

HEADER_CUTTER_SLACK = 0.35


base_border = 5.0
base_thickness = 2.2
electronics_boards_holder_offset = 0.005


pico_w_board_thickness = pcb_thickness
pico_w_board_y_pins = 20
pico_w_board_int_pin_distance = 8
pico_w_board_int_width = pico_w_board_int_pin_distance
pico_w_board_y_oversize = 1  # in dil pitch units
pico_w_board_corner_radius = 0.25 * dil_pitch
pico_w_board_micro_usb_socket_offset = 1.3

electronics_holder_slack = 0.4
electronics_board_cutter_slack = 0.3

usb_c_socket_thickness = 3.2
usb_c_socket_width = 8.96
usb_c_socket_depth = 7.3

micro_usb_socket_thickness = 3.0
micro_usb_socket_width = 7.0
micro_usb_socket_depth = 5.0


tmc_board_y_pins = 8
tmc_board_int_pin_distance = 4
tmc_board_int_width = tmc_board_int_pin_distance
tmc_board_y_oversize = 0  # in dil pitch units
tmc_board_corner_radius = None
tmc_board_cooler_size = 8.9
tmc_board_cooler_height = 12


board_clamp_spring_length = 10
board_clamp_spring_thickness = 1.8
board_clamp_height = 5
board_clamp_tooth_size = 0.8
board_clamp_teeth_length = 3
board_clamp_spring_side_clearance = 1
board_clamp_spring_front_cliearnce = 0.3
board_clamp_clamping_inset = 0.8


def create_board_clamp():

    clamp_spring = create_box(
        board_clamp_spring_thickness, board_clamp_spring_length, base_thickness
    )

    clamp_sping_clearance_cutter = create_box(
        board_clamp_spring_thickness + board_clamp_spring_side_clearance,
        board_clamp_spring_length + board_clamp_spring_front_cliearnce,
        BIG_THING,
    )
    clamp_sping_clearance_cutter = align(
        clamp_sping_clearance_cutter, clamp_spring, Alignment.CENTER
    )
    clamp_sping_clearance_cutter = align(
        clamp_sping_clearance_cutter, clamp_spring, Alignment.FRONT
    )
    clamp_sping_clearance_cutter = align(
        clamp_sping_clearance_cutter, clamp_spring, Alignment.LEFT
    )

    tooth_height = math.sqrt(2) * board_clamp_tooth_size

    num_teeth = math.ceil(board_clamp_height / tooth_height)

    teeth = PartCollector()
    for i in range(num_teeth):
        tooth = create_box(
            board_clamp_tooth_size, board_clamp_teeth_length, board_clamp_tooth_size
        )
        tooth = rotate(45, axis=(0, 1, 0))(tooth)

        tooth = translate(0, 0, tooth_height * i)(tooth)
        teeth = teeth.fuse(tooth)

    teeth = align(teeth, clamp_spring, Alignment.BOTTOM)
    teeth = align(teeth, clamp_spring, Alignment.BACK)
    teeth = align(teeth, clamp_spring, Alignment.LEFT)
    teeth = translate(-board_clamp_clamping_inset, 0, 0)(teeth)

    teeth_holder = create_box(
        board_clamp_spring_thickness + board_clamp_clamping_inset - tooth_height / 2,
        board_clamp_teeth_length,
        board_clamp_height,
    )
    teeth_holder = align(teeth_holder, clamp_spring, Alignment.LEFT)
    teeth_holder = align(teeth_holder, clamp_spring, Alignment.BOTTOM)
    teeth_holder = align(teeth_holder, clamp_spring, Alignment.BACK)
    teeth_holder = translate(-(board_clamp_clamping_inset - tooth_height / 2), 0, 0)(
        teeth_holder
    )
    teeth = teeth.fuse(teeth_holder)

    teeth_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)

    teeth_cutter = align(teeth_cutter, teeth_holder, Alignment.CENTER)
    teeth_cutter = align(teeth_cutter, teeth_holder, Alignment.STACK_TOP)
    teeth = teeth.cut(teeth_cutter)

    retval = LeaderFollowersCuttersPart(
        clamp_spring, cutters=[clamp_sping_clearance_cutter]
    )

    retval.add_named_follower(teeth, "teeth")

    return retval


def create_usb_c_socket():

    retval = create_rounded_slab(
        usb_c_socket_width,
        usb_c_socket_thickness,
        usb_c_socket_depth,
        usb_c_socket_thickness / 2,
    )
    retval = rotate(90, axis=(1, 0, 0))(retval)

    return retval


def create_micro_usb_socket():
    retval = create_rounded_slab(
        micro_usb_socket_width,
        micro_usb_socket_thickness,
        micro_usb_socket_depth,
        micro_usb_socket_thickness / 2,
    )
    retval = rotate(90, axis=(1, 0, 0))(retval)

    return retval


def create_pico_w_board() -> LeaderFollowersCuttersPart:

    retval = create_dil_board(
        pico_w_board_int_width,
        pico_w_board_y_pins,
        pico_w_board_thickness,
        board_corner_radius=pico_w_board_corner_radius,
        pin_length=wire_wrap_pin_length,
        pin_side=wire_wrap_pin_side,
        top_pin_length=top_pin_length,
        base_thickness=wire_wrap_pin_base_thickness,
        pin_cutter_slack=0.0,
        base_cutter_slack=electronics_holder_slack,
        board_cutter_slack=electronics_board_cutter_slack,
        y_overhang_in_pins=0.5,
    )

    micro_usb_socket = create_micro_usb_socket()
    micro_usb_socket = align(micro_usb_socket, retval, Alignment.CENTER)
    micro_usb_socket = align(micro_usb_socket, retval, Alignment.FRONT)
    micro_usb_socket = align(micro_usb_socket, retval, Alignment.STACK_TOP)

    micro_usb_socket_bbox_size = get_bounding_box_size(micro_usb_socket)

    micro_usb_socket_slack = 0.8
    micro_usb_socket_cutter = create_box(
        micro_usb_socket_bbox_size[0] + 2 * micro_usb_socket_slack,
        micro_usb_socket_bbox_size[1] + 2 * micro_usb_socket_slack,
        micro_usb_socket_bbox_size[2] + 2 * micro_usb_socket_slack,
    )
    micro_usb_socket_cutter = align(
        micro_usb_socket_cutter, micro_usb_socket, Alignment.CENTER
    )

    micro_usb_socket = translate(0, -pico_w_board_micro_usb_socket_offset, 0)(
        micro_usb_socket
    )
    retval.cutters.append(micro_usb_socket_cutter)

    retval = retval.fuse(micro_usb_socket)

    top_center = get_bounding_box_center(retval)
    retval = rotate(180, center=top_center)(retval)

    return retval


def create_tmc_board() -> LeaderFollowersCuttersPart:

    retval = create_dil_board(
        tmc_board_int_width,
        tmc_board_y_pins,
        TMC_BOARD_THICKNESS,
        board_corner_radius=tmc_board_corner_radius,
        pin_length=wire_wrap_pin_length,
        pin_side=wire_wrap_pin_side,
        top_pin_length=top_pin_length,
        base_thickness=wire_wrap_pin_base_thickness,
        pin_cutter_slack=0.0,
        base_cutter_slack=electronics_holder_slack,
        board_cutter_slack=electronics_board_cutter_slack,
        y_overhang_in_pins=0.5,
    )

    board_plain = retval.get_follower_part_by_name("board")
    cooler = create_box(
        tmc_board_cooler_size, tmc_board_cooler_size, tmc_board_cooler_height
    )
    cooler = align(cooler, board_plain, Alignment.CENTER)
    cooler = align(cooler, board_plain, Alignment.STACK_TOP)
    retval = retval.fuse(cooler)

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    pico = create_pico_w_board()

    tmc_1 = create_tmc_board()

    tmc_1 = align(
        tmc_1, pico, Alignment.STACK_RIGHT, stack_gap=PICO_TO_DRIVER_RIGHT_GAP
    )

    tmc_2 = align(
        tmc_1, pico, Alignment.STACK_RIGHT, stack_gap=PICO_TO_DRIVER_RIGHT_GAP
    )

    tmc_2 = align(tmc_1, pico, Alignment.BACK)

    both = pico.leader.fuse(tmc_1.leader).fuse(tmc_2.leader)

    bards_size = get_bounding_box_size(both)

    boards_holder = create_box(
        bards_size[0] + 2 * base_border,
        bards_size[1] + 2 * base_border,
        base_thickness,
    )

    boards_holder_bb = get_bounding_box(boards_holder)
    boards_holder = translate(
        0, 0, -boards_holder_bb[1][2] + electronics_boards_holder_offset
    )(boards_holder)

    boards_holder = align(boards_holder, both, Alignment.CENTER, axes=[0, 1])

    boards_holder = pico.use_as_cutter_on(boards_holder)
    boards_holder = tmc_1.use_as_cutter_on(boards_holder)
    boards_holder = tmc_2.use_as_cutter_on(boards_holder)
    for current_board in [pico, tmc_1, tmc_2]:

        for lr in [Alignment.LEFT, Alignment.RIGHT]:

            board_clamp_1 = create_board_clamp()
            if lr == Alignment.LEFT:
                board_clamp_1 = mirror(normal=(1, 0, 0))(board_clamp_1)

            board_clamp_1 = align(
                board_clamp_1, current_board, Alignment.CENTER, axes=[0, 1]
            )

            board_clamp_1 = align(
                board_clamp_1,
                current_board,
                lr.stack_alignment,
                stack_gap=electronics_holder_slack,
            )
            board_clamp_1 = align(board_clamp_1, boards_holder, Alignment.BOTTOM)

            boards_holder = board_clamp_1.use_as_cutter_on(boards_holder)
            boards_holder = board_clamp_1.leader.fuse(boards_holder)
            boards_holder = boards_holder.fuse(
                board_clamp_1.get_follower_part_by_name("teeth")
            )

    parts.add(pico, "pico", flip=False, skip_in_production=True)
    parts.add(tmc_1, "tmc_1", flip=False, skip_in_production=True)
    parts.add(tmc_2, "tmc_2", flip=False, skip_in_production=True)

    parts.add(boards_holder, "boards_holder", flip=False)

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("mcu_housing_x_axis created successfully!")


if __name__ == "__main__":
    main()
