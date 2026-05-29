import pytest

from mege_ender_3v3ke_idex.designs.assemblies.mosfet_driver_board_assembly import (
    create_mosfet_driver_board_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_usb_board_assembly import (
    create_nitehawk_usb_board_assembly,
)
from shellforgepy.simple import get_bounding_box_center, get_bounding_box_size


NITEHAWK_USB_BOARD_PARAMS = {
    "nitehawk_usb_board_length": 30.0,
    "nitehawk_usb_board_width": 28.0,
    "nitehawk_usb_board_thickness": 1.6,
    "nitehawk_usb_board_corner_radius": 1.0,
    "nitehawk_usb_board_clearance_slack": 0.3,
    "nitehawk_usb_component_clearance_slack": 0.8,
    "nitehawk_usb_mount_hole_diameter": 3.2,
    "nitehawk_usb_mount_hole_front_left_x": 3.0,
    "nitehawk_usb_mount_hole_front_left_y": 4.0,
    "nitehawk_usb_mount_hole_front_right_x": 26.6,
    "nitehawk_usb_mount_hole_front_right_y": 4.0,
    "nitehawk_usb_mount_hole_back_x": 15.4,
    "nitehawk_usb_mount_hole_back_y": 21.8,
    "nitehawk_usb_terminal_block_length": 10.6,
    "nitehawk_usb_terminal_block_width": 8.3,
    "nitehawk_usb_terminal_block_height": 10.0,
    "nitehawk_usb_terminal_block_x": 0.3,
    "nitehawk_usb_terminal_block_y": 19.7,
    "nitehawk_usb_terminal_block_top_taper_height": 2.4,
    "nitehawk_usb_terminal_block_top_width": 6.6,
    "nitehawk_usb_terminal_block_window_side_margin": 0.8,
    "nitehawk_usb_terminal_block_window_center_divider": 1.1,
    "nitehawk_usb_terminal_block_window_bottom_lip": 0.9,
    "nitehawk_usb_terminal_block_window_top_lip": 0.7,
    "nitehawk_usb_terminal_block_window_back_wall": 1.0,
    "nitehawk_usb_usb_c_connector_length": 9.2,
    "nitehawk_usb_usb_c_connector_width": 6.4,
    "nitehawk_usb_usb_c_connector_height": 3.2,
    "nitehawk_usb_usb_c_connector_x": 20.4,
    "nitehawk_usb_usb_c_connector_y": 21.6,
    "nitehawk_usb_front_plug_length": 11.6,
    "nitehawk_usb_front_plug_width": 8.8,
    "nitehawk_usb_front_plug_height": 10.5,
    "nitehawk_usb_front_plug_x": 11.4,
    "nitehawk_usb_front_plug_y": 0.0,
    "nitehawk_usb_white_connector_length": 10.9,
    "nitehawk_usb_white_connector_width": 5.2,
    "nitehawk_usb_white_connector_height": 4.2,
    "nitehawk_usb_white_connector_x": 0.9,
    "nitehawk_usb_white_connector_y": 10.5,
}


MOSFET_DRIVER_BOARD_PARAMS = {
    "mosfet_driver_board_length": 34,
    "mosfet_driver_board_width": 17.3,
    "mosfet_driver_board_thickness": 1.2,
    "mosfet_driver_mount_hole_diameter": 2.4,
    "mosfet_driver_mount_hole_edge_clearance": 0.7,
    "mosfet_driver_terminal_block_length": 9.0,
    "mosfet_driver_terminal_block_width": 7.7,
    "mosfet_driver_terminal_block_height": 10,
    "mosfet_driver_terminal_block_gap": 1.5,
    "mosfet_driver_terminal_block_top_taper_height": 2.6,
    "mosfet_driver_terminal_block_top_width": 6.4,
    "mosfet_driver_terminal_block_window_side_margin": 0.8,
    "mosfet_driver_terminal_block_window_center_divider": 1.1,
    "mosfet_driver_terminal_block_window_bottom_lip": 1.0,
    "mosfet_driver_terminal_block_window_top_lip": 0.7,
    "mosfet_driver_terminal_block_window_back_wall": 1.0,
    "mosfet_driver_package_length": 6.9,
    "mosfet_driver_package_width": 6.1,
    "mosfet_driver_package_height": 2.4,
    "mosfet_driver_package_gap_to_terminal_block": 1.2,
    "mosfet_driver_j1_row_pin_count": 4,
    "mosfet_driver_j1_hole_diameter": 1.2,
    "mosfet_driver_j1_four_pin_row_x": 3.7,
    "mosfet_driver_j1_two_pin_row_x": 1.4,
    "mosfet_driver_j1_two_pin_y_offset": 2.55,
    "x_axis_mcu_wire_wrap_pin_side": 0.63,
    "x_axis_mcu_wire_wrap_pin_length": 12.1,
    "x_axis_mcu_wire_wrap_pin_base_thickness": 2.43,
    "x_axis_mcu_top_pin_length": 2.8,
    "x_axis_mcu_electronics_holder_slack": 0.55,
    "x_axis_mcu_electronics_board_cutter_slack": 0.3,
    "x_axis_mcu_base_cutter_vertical_slack": 1.2,
}


def test_nitehawk_usb_board_has_caliper_measured_board_size():
    board = create_nitehawk_usb_board_assembly(**NITEHAWK_USB_BOARD_PARAMS)
    board_pcb = board.get_follower_part_by_name("board")
    board_size = get_bounding_box_size(board_pcb)

    assert board_size[0] == pytest.approx(30.0)
    assert board_size[1] == pytest.approx(28.0)
    assert board_size[2] == pytest.approx(1.6)


def test_nitehawk_usb_board_exposes_holder_geometry_by_name():
    board = create_nitehawk_usb_board_assembly(**NITEHAWK_USB_BOARD_PARAMS)

    assert set(board.follower_indices_by_name) == {
        "board",
        "terminal_block",
        "usb_c_connector",
        "front_plug",
        "white_connector",
    }
    assert set(board.cutter_indices_by_name) == {
        "board_clearance",
        "terminal_block_clearance",
        "usb_c_connector_clearance",
        "front_plug_clearance",
        "white_connector_clearance",
        "mounting_hole_front_left",
        "mounting_hole_front_right",
        "mounting_hole_back",
    }


@pytest.mark.parametrize(
    ("name", "expected_center"),
    [
        ("mounting_hole_front_left", (3.0, 4.0)),
        ("mounting_hole_front_right", (26.6, 4.0)),
        ("mounting_hole_back", (15.4, 21.8)),
    ],
)
def test_nitehawk_usb_mounting_holes_match_measured_layout(name, expected_center):
    board = create_nitehawk_usb_board_assembly(**NITEHAWK_USB_BOARD_PARAMS)
    center = get_bounding_box_center(board.get_cutter_part_by_name(name))

    assert center[0] == pytest.approx(expected_center[0])
    assert center[1] == pytest.approx(expected_center[1])


def test_mosfet_driver_board_still_exposes_terminal_blocks_after_helper_extraction():
    board = create_mosfet_driver_board_assembly(**MOSFET_DRIVER_BOARD_PARAMS)

    assert "terminal_block_front" in board.follower_indices_by_name
    assert "terminal_block_back" in board.follower_indices_by_name
    assert "board_clearance" in board.cutter_indices_by_name
    assert "j1_connector_clearance" in board.cutter_indices_by_name
