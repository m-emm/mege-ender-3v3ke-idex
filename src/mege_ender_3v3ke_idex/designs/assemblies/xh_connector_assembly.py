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
XH_CONNECTOR_PIN_CENTER_X_FROM_LEFT = 2.35
XH_CONNECTOR_WALL_THICKNESS = 0.8
XH_CONNECTOR_FLOOR_THICKNESS = 0.8
XH_CONNECTOR_KEYING_SLIT_DEPTH = 1.2
XH_CONNECTOR_KEYING_SLIT_WIDTH = 1.0
XH_CONNECTOR_KEYING_SLIT_HEIGHT = 4.2


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

    pin_row_span = create_box(
        0.1,
        (xh_connector_num_pins - 1) * XH_CONNECTOR_PITCH,
        0.1,
    )
    pin_row_span = align(pin_row_span, housing, Alignment.CENTER, axes=[1])

    keying_slits = PartCollector()
    for slit_alignment in [Alignment.FRONT, Alignment.BACK]:
        keying_slit = create_box(
            XH_CONNECTOR_KEYING_SLIT_DEPTH,
            XH_CONNECTOR_KEYING_SLIT_WIDTH,
            XH_CONNECTOR_KEYING_SLIT_HEIGHT,
        )
        keying_slit = align(keying_slit, housing, Alignment.EDGE_LEFT)
        keying_slit = translate(XH_CONNECTOR_KEYING_SLIT_DEPTH / 2, 0, 0)(keying_slit)
        keying_slit = align(keying_slit, pin_row_span, slit_alignment.edge_alignment)
        keying_slit = align(keying_slit, housing, Alignment.TOP)
        keying_slits = keying_slits.fuse(keying_slit)
    housing = housing.cut(keying_slits)

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
    pins = align(pins, housing, Alignment.CENTER, axes=[1])
    pins = align(pins, housing, Alignment.EDGE_LEFT)
    pins = translate(XH_CONNECTOR_PIN_CENTER_X_FROM_LEFT, 0, 0)(pins)
    pins = align(pins, housing, Alignment.TOP)

    assembly = LeaderFollowersCuttersPart(leader=housing)
    assembly.add_named_non_production_part(pins, "pins")

    return assembly
