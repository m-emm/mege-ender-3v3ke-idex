"""SIL clamp assembly."""

from mege_ender_3v3ke_idex.designs.assemblies.pin_header_board_helpers import (
    create_sil_header,
)
from shellforgepy.simple import *


def create_sil_clamp_assembly(
    *,
    x_axis_mcu_dil_pitch,
    x_axis_mcu_wire_wrap_pin_side,
    x_axis_mcu_wire_wrap_pin_length,
    x_axis_mcu_wire_wrap_pin_base_thickness,
    x_axis_mcu_wire_wrap_pin_base_width,
    x_axis_mcu_top_pin_length,
    board_holder_additional_pins_num_pins,
    board_holder_additional_pins_base_plate_length,
    board_holder_base_plate_thickness,
    BIG_THING,
):
    holder_slack = 0.3
    base_cutter_vertical_slack = 0.2
    lip_size = 0.85

    pins = create_sil_header(
        num_y_pins=board_holder_additional_pins_num_pins,
        dil_pitch=x_axis_mcu_dil_pitch,
        wire_wrap_pin_side=x_axis_mcu_wire_wrap_pin_side,
        wire_wrap_pin_length=x_axis_mcu_wire_wrap_pin_length,
        wire_wrap_pin_base_thickness=x_axis_mcu_wire_wrap_pin_base_thickness,
        wire_wrap_pin_base_width=x_axis_mcu_wire_wrap_pin_base_width,
        top_pin_length=x_axis_mcu_top_pin_length,
        pin_cutter_slack=0.5,
        base_cutter_slack=holder_slack,
        base_cutter_vertical_slack=base_cutter_vertical_slack,
    )
    pins_size = get_bounding_box_size(pins)

    base_plate = create_box(
        board_holder_additional_pins_base_plate_length,
        pins_size[1] + 2 * x_axis_mcu_dil_pitch,
        board_holder_base_plate_thickness,
    )
    base_plate = translate(0, 0, -board_holder_base_plate_thickness)(base_plate)

    pins = align(pins, base_plate, Alignment.CENTER, axes=[0, 1])
    base_plate = pins.use_as_cutter_on(base_plate)

    slit_cutter = create_box(
        0.4,
        pins_size[1] + 4 * x_axis_mcu_dil_pitch,
        BIG_THING,
    )
    slit_cutter = align(slit_cutter, pins, Alignment.CENTER)
    base_plate = base_plate.cut(slit_cutter)
    flat_base_plate = base_plate

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
    lip = translate(holder_slack, 0, 0)(lip)
    lip = align(lip, base_plate, Alignment.STACK_TOP)
    base_plate = base_plate.fuse(lip)

    lip_holder = create_box(lip_size, pins_size[1], lip_size)
    lip_holder = align(lip_holder, lip, Alignment.CENTER)
    lip_holder = align(lip_holder, lip, Alignment.STACK_RIGHT)
    base_plate = base_plate.fuse(lip_holder)

    retval = LeaderFollowersCuttersPart(base_plate)
    retval.add_named_follower(flat_base_plate, "additional_pins_base_plate")
    retval.add_named_non_production_part(pins.leader, "pins")
    retval.add_named_non_production_part(
        pins.get_follower_part_by_name("top_pins"),
        "top_pins",
    )
    retval.add_named_cutter(pins.get_cutter_part_by_name("pin_cutters"), "pin_cutters")

    return retval
