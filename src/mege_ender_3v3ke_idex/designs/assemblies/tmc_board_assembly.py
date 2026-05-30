"""TMC board assembly."""

from mege_ender_3v3ke_idex.designs.assemblies.pin_header_board_helpers import (
    create_dil_board,
    create_sil_header,
)
from shellforgepy.simple import *


def create_tmc_board_assembly(
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
    x_axis_mcu_tmc_board_y_pins,
    x_axis_mcu_tmc_board_int_width,
    x_axis_mcu_tmc_board_thickness,
    x_axis_mcu_tmc_board_cooler_size,
    x_axis_mcu_tmc_board_cooler_height,
    x_axis_mcu_tmc_board_chip_thickness,
    x_axis_mcu_tmc_chip_y_size_rasterized,
    x_axis_mcu_tmc_current_potentiometer_underside_thickness,
    x_axis_mcu_tmc_current_potentiometer_underside_size_rasterized,
    x_axis_mcu_tmc_pin_cutter_slack=0.5,
):
    retval = create_dil_board(
        int_x_distance=x_axis_mcu_tmc_board_int_width,
        num_y_pins=x_axis_mcu_tmc_board_y_pins,
        board_thickness=x_axis_mcu_tmc_board_thickness,
        board_corner_radius=None,
        dil_pitch=x_axis_mcu_dil_pitch,
        wire_wrap_pin_side=x_axis_mcu_wire_wrap_pin_side,
        wire_wrap_pin_length=x_axis_mcu_wire_wrap_pin_length,
        wire_wrap_pin_base_thickness=x_axis_mcu_wire_wrap_pin_base_thickness,
        wire_wrap_pin_base_width=x_axis_mcu_wire_wrap_pin_base_width,
        top_pin_length=x_axis_mcu_top_pin_length,
        pin_cutter_slack=x_axis_mcu_tmc_pin_cutter_slack,
        base_cutter_slack=x_axis_mcu_electronics_holder_slack,
        base_cutter_vertical_slack=x_axis_mcu_base_cutter_vertical_slack,
        board_cutter_slack=x_axis_mcu_electronics_board_cutter_slack,
        y_overhang_in_pins=0.5,
    )

    board_plain = retval.get_follower_part_by_name("board")
    board_dil = retval.get_follower_part_by_name("dil")

    cooler = create_box(
        x_axis_mcu_tmc_board_cooler_size,
        x_axis_mcu_tmc_board_cooler_size,
        x_axis_mcu_tmc_board_cooler_height,
    )
    cooler = align(cooler, board_plain, Alignment.CENTER)
    cooler = align(cooler, board_plain, Alignment.STACK_TOP)
    cooler = align(cooler, board_dil, Alignment.FRONT)
    cooler = translate(0, x_axis_mcu_dil_pitch, 0)(cooler)

    retval = retval.fuse(cooler)
    retval.add_named_non_production_part(cooler, "cooler")

    additional_pins = create_sil_header(
        num_y_pins=2,
        dil_pitch=x_axis_mcu_dil_pitch,
        wire_wrap_pin_side=x_axis_mcu_wire_wrap_pin_side,
        wire_wrap_pin_length=x_axis_mcu_wire_wrap_pin_length,
        wire_wrap_pin_base_thickness=x_axis_mcu_wire_wrap_pin_base_thickness,
        wire_wrap_pin_base_width=x_axis_mcu_wire_wrap_pin_base_width,
        top_pin_length=x_axis_mcu_top_pin_length,
        pin_cutter_slack=0.0,
        base_cutter_slack=x_axis_mcu_electronics_holder_slack,
        base_cutter_vertical_slack=x_axis_mcu_base_cutter_vertical_slack,
    )
    additional_pins = rotate(90)(additional_pins)
    additional_pins = align(additional_pins, board_dil, Alignment.LEFT)
    additional_pins = translate(x_axis_mcu_dil_pitch, 0, 0)(additional_pins)
    additional_pins = align(additional_pins, board_dil, Alignment.BACK)
    retval = retval.fuse(additional_pins)
    retval.cutters.extend(additional_pins.cutters)
    retval.add_named_non_production_part(
        additional_pins.leaders_followers_fused(),
        "additional_pins",
    )

    chip = create_box(
        (x_axis_mcu_tmc_board_int_width - 1.5) * x_axis_mcu_dil_pitch,
        x_axis_mcu_tmc_chip_y_size_rasterized * x_axis_mcu_dil_pitch,
        x_axis_mcu_tmc_board_chip_thickness,
    )
    chip = align(chip, board_plain, Alignment.CENTER)
    chip = align(chip, board_plain, Alignment.STACK_BOTTOM)
    retval = retval.fuse(chip)
    retval.add_named_non_production_part(chip, "chip")

    chip_size = get_bounding_box_size(chip)
    chip_cutter = create_box(
        chip_size[0] + 2 * x_axis_mcu_electronics_holder_slack,
        chip_size[1] + 2 * x_axis_mcu_electronics_holder_slack,
        chip_size[2] + x_axis_mcu_electronics_holder_slack,
    )
    chip_cutter = align(chip_cutter, chip, Alignment.CENTER)
    chip_cutter = align(chip_cutter, chip, Alignment.TOP)

    potentiometer_underside = create_box(
        x_axis_mcu_tmc_current_potentiometer_underside_size_rasterized
        * x_axis_mcu_dil_pitch,
        x_axis_mcu_dil_pitch,
        x_axis_mcu_tmc_current_potentiometer_underside_thickness,
    )
    potentiometer_underside = align(
        potentiometer_underside,
        board_plain,
        Alignment.CENTER,
    )
    potentiometer_underside = align(
        potentiometer_underside,
        board_dil,
        Alignment.BACK,
    )
    potentiometer_underside = align(
        potentiometer_underside,
        board_dil,
        Alignment.RIGHT,
    )
    potentiometer_underside = align(
        potentiometer_underside,
        board_plain,
        Alignment.STACK_BOTTOM,
    )
    potentiometer_underside = translate(-x_axis_mcu_dil_pitch * 1.5, 0, 0)(
        potentiometer_underside
    )
    retval = retval.fuse(potentiometer_underside)
    retval.add_named_non_production_part(
        potentiometer_underside,
        "potentiometer_underside",
    )

    potentiometer_size = get_bounding_box_size(potentiometer_underside)
    potentiometer_cutter = create_box(
        potentiometer_size[0] + 2 * x_axis_mcu_electronics_holder_slack,
        potentiometer_size[1] + 2 * x_axis_mcu_electronics_holder_slack,
        potentiometer_size[2] + x_axis_mcu_electronics_holder_slack,
    )
    potentiometer_cutter = align(
        potentiometer_cutter,
        potentiometer_underside,
        Alignment.CENTER,
    )
    potentiometer_cutter = align(
        potentiometer_cutter,
        potentiometer_underside,
        Alignment.TOP,
    )

    retval.cutters.append(chip_cutter)
    retval.cutters.append(potentiometer_cutter)

    return retval
