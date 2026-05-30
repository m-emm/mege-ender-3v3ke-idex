"""Pico W board assembly."""

from mege_ender_3v3ke_idex.designs.assemblies.pin_header_board_helpers import (
    create_dil_board,
)
from shellforgepy.simple import *


def create_pico_w_board_assembly(
    *,
    x_axis_mcu_dil_pitch,
    x_axis_mcu_wire_wrap_pin_side,
    x_axis_mcu_wire_wrap_pin_length,
    x_axis_mcu_wire_wrap_pin_base_thickness,
    x_axis_mcu_wire_wrap_pin_base_width,
    x_axis_mcu_top_pin_length,
    x_axis_mcu_electronics_holder_slack,
    x_axis_mcu_electronics_board_cutter_slack,
    x_axis_mcu_base_cutter_vertical_slack,
    x_axis_mcu_pico_board_thickness,
    x_axis_mcu_pico_board_y_pins,
    x_axis_mcu_pico_board_int_width,
    x_axis_mcu_pico_board_corner_radius,
    x_axis_mcu_pico_board_micro_usb_socket_offset,
    x_axis_mcu_pico_bar_cutter_slack,
    x_axis_mcu_micro_usb_socket_width,
    x_axis_mcu_micro_usb_socket_thickness,
    x_axis_mcu_micro_usb_socket_depth,
):
    retval = create_dil_board(
        int_x_distance=x_axis_mcu_pico_board_int_width,
        num_y_pins=x_axis_mcu_pico_board_y_pins,
        board_thickness=x_axis_mcu_pico_board_thickness,
        board_corner_radius=x_axis_mcu_pico_board_corner_radius,
        dil_pitch=x_axis_mcu_dil_pitch,
        wire_wrap_pin_side=x_axis_mcu_wire_wrap_pin_side,
        wire_wrap_pin_length=x_axis_mcu_wire_wrap_pin_length,
        wire_wrap_pin_base_thickness=x_axis_mcu_wire_wrap_pin_base_thickness,
        wire_wrap_pin_base_width=x_axis_mcu_wire_wrap_pin_base_width,
        top_pin_length=x_axis_mcu_top_pin_length,
        pin_cutter_slack=0.0,
        base_cutter_slack=x_axis_mcu_electronics_holder_slack,
        base_cutter_vertical_slack=x_axis_mcu_base_cutter_vertical_slack,
        board_cutter_slack=x_axis_mcu_electronics_board_cutter_slack,
        y_overhang_in_pins=0.5,
    )

    micro_usb_socket = create_rounded_slab(
        x_axis_mcu_micro_usb_socket_width,
        x_axis_mcu_micro_usb_socket_thickness,
        x_axis_mcu_micro_usb_socket_depth,
        x_axis_mcu_micro_usb_socket_thickness / 2,
    )
    micro_usb_socket = rotate(90, axis=(1, 0, 0))(micro_usb_socket)
    micro_usb_socket = align(micro_usb_socket, retval, Alignment.CENTER)
    micro_usb_socket = align(micro_usb_socket, retval, Alignment.FRONT)
    micro_usb_socket = align(micro_usb_socket, retval, Alignment.STACK_TOP)
    micro_usb_socket = translate(
        0,
        -x_axis_mcu_pico_board_micro_usb_socket_offset,
        0,
    )(micro_usb_socket)

    micro_usb_socket_size = get_bounding_box_size(micro_usb_socket)
    micro_usb_socket_slack = 0.8
    micro_usb_socket_cutter = create_box(
        micro_usb_socket_size[0] + 2 * micro_usb_socket_slack,
        micro_usb_socket_size[1] + 2 * micro_usb_socket_slack,
        micro_usb_socket_size[2] + 2 * micro_usb_socket_slack,
    )
    micro_usb_socket_cutter = align(
        micro_usb_socket_cutter,
        micro_usb_socket,
        Alignment.CENTER,
    )

    retval = retval.fuse(micro_usb_socket)
    retval.cutters.append(micro_usb_socket_cutter)
    retval.add_named_non_production_part(micro_usb_socket, "micro_usb_socket")

    board_pcb = retval.get_follower_part_by_name("board")
    board_pcb_size = get_bounding_box_size(board_pcb)

    support_bars = PartCollector()
    support_bar_cutters = PartCollector()
    for bar_range in [(2, 2), (9, 10), (17, 17)]:
        support_bar = create_box(
            board_pcb_size[0],
            x_axis_mcu_dil_pitch * (bar_range[1] - bar_range[0] + 1),
            x_axis_mcu_wire_wrap_pin_base_thickness,
        )
        support_bar = align(support_bar, board_pcb, Alignment.CENTER)
        support_bar = align(support_bar, board_pcb, Alignment.FRONT)
        support_bar = align(support_bar, board_pcb, Alignment.STACK_BOTTOM)
        support_bar = translate(0, x_axis_mcu_dil_pitch * bar_range[0], 0)(support_bar)
        support_bars = support_bars.fuse(support_bar)

        support_bar_cutter = create_box(
            board_pcb_size[0],
            x_axis_mcu_dil_pitch * (bar_range[1] - bar_range[0] + 1)
            + 2 * x_axis_mcu_pico_bar_cutter_slack,
            x_axis_mcu_wire_wrap_pin_base_thickness,
        )
        support_bar_cutter = align(support_bar_cutter, support_bar, Alignment.CENTER)
        support_bar_cutters = support_bar_cutters.fuse(support_bar_cutter)

    retval = retval.fuse(support_bars)
    retval.cutters.append(support_bar_cutters)
    retval.add_named_non_production_part(support_bars, "support_bars")

    top_center = get_bounding_box_center(retval)
    return rotate(180, center=top_center)(retval)
