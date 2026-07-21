"""SIL clamp assembly."""

from mege_ender_3v3ke_idex.designs.assemblies.pin_header_board_helpers import (
    create_sil_pin_line_clamp,
)


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
    _ = BIG_THING
    return create_sil_pin_line_clamp(
        num_pins=board_holder_additional_pins_num_pins,
        dil_pitch=x_axis_mcu_dil_pitch,
        wire_wrap_pin_side=x_axis_mcu_wire_wrap_pin_side,
        wire_wrap_pin_length=x_axis_mcu_wire_wrap_pin_length,
        wire_wrap_pin_base_thickness=x_axis_mcu_wire_wrap_pin_base_thickness,
        wire_wrap_pin_base_width=x_axis_mcu_wire_wrap_pin_base_width,
        top_pin_length=x_axis_mcu_top_pin_length,
        base_plate_length=board_holder_additional_pins_base_plate_length,
        base_plate_thickness=board_holder_base_plate_thickness,
        holder_slack=0.3,
        base_cutter_vertical_slack=0.2,
        lip_size=0.85,
        slit_width=0.4,
    )
