"""Simplified JST XH connector reference assembly."""

from mege_ender_3v3ke_idex.designs.assemblies.pin_header_board_helpers import (
    create_sil_header,
)
from shellforgepy.simple import *


XH_CONNECTOR_PITCH = 2.5
XH_CONNECTOR_BODY_WIDTH_EXTRA = 4.9
XH_CONNECTOR_HOUSING_DEPTH = 5.75
XH_CONNECTOR_HOUSING_HEIGHT = 7.0
XH_CONNECTOR_PIN_SIDE = 0.64
XH_CONNECTOR_PIN_TAIL_LENGTH = 3.4
XH_CONNECTOR_WALL_THICKNESS = 0.8
XH_CONNECTOR_FLOOR_THICKNESS = 0.8


def create_xh_connector_assembly(*, xh_connector_num_pins):
    if xh_connector_num_pins < 2:
        raise ValueError("xh_connector_num_pins must be at least 2")

    housing_width = (
        xh_connector_num_pins - 1
    ) * XH_CONNECTOR_PITCH + XH_CONNECTOR_BODY_WIDTH_EXTRA
    housing = create_box(
        XH_CONNECTOR_HOUSING_DEPTH,
        housing_width,
        XH_CONNECTOR_HOUSING_HEIGHT,
    )

    housing_inner_cutter = materialize_bounding_box(
        housing,
        x_enlargement=-2 * XH_CONNECTOR_WALL_THICKNESS,
        y_enlargement=-2 * XH_CONNECTOR_WALL_THICKNESS,
        z_enlargement=-XH_CONNECTOR_FLOOR_THICKNESS,
    )
    housing_inner_cutter = align(housing_inner_cutter, housing, Alignment.CENTER)
    housing_inner_cutter = align(housing_inner_cutter, housing, Alignment.TOP)
    housing = housing.cut(housing_inner_cutter)

    pin_header = create_sil_header(
        num_y_pins=xh_connector_num_pins,
        dil_pitch=XH_CONNECTOR_PITCH,
        wire_wrap_pin_side=XH_CONNECTOR_PIN_SIDE,
        wire_wrap_pin_length=XH_CONNECTOR_PIN_TAIL_LENGTH,
        wire_wrap_pin_base_thickness=XH_CONNECTOR_FLOOR_THICKNESS,
        wire_wrap_pin_base_width=XH_CONNECTOR_PITCH,
        top_pin_length=XH_CONNECTOR_HOUSING_HEIGHT + XH_CONNECTOR_PIN_TAIL_LENGTH,
    )
    pins = pin_header.get_follower_part_by_name("top_pins")
    pins = align(pins, housing, Alignment.CENTER, axes=[0, 1])
    pins = align(pins, housing, Alignment.TOP)

    assembly = LeaderFollowersCuttersPart(leader=housing)
    assembly.add_named_non_production_part(pins, "pins")
    assembly.add_named_cutter(housing_inner_cutter, "housing_inner_cutter")

    return assembly
