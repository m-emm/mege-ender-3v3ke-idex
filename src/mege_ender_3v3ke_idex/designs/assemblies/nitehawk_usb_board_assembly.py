"""Nitehawk USB daughterboard assembly."""

from mege_ender_3v3ke_idex.designs.electronics_components import (
    create_terminal_block,
)
from shellforgepy.simple import *


def _validate_positive(name, value):
    if value <= 0:
        raise ValueError(f"{name} must be positive.")


def _validate_board_point(name, *, x, y, board_length, board_width):
    if not 0 <= x <= board_length:
        raise ValueError(f"{name} x position is outside the board.")
    if not 0 <= y <= board_width:
        raise ValueError(f"{name} y position is outside the board.")


def _validate_component_on_board(
    name,
    *,
    x,
    y,
    length,
    width,
    board_length,
    board_width,
):
    if x < 0 or y < 0 or x + length > board_length or y + width > board_width:
        raise ValueError(f"{name} footprint is outside the board.")


def _create_clearance_cutter(part, *, xy_slack, z_slack):
    bbox = get_bounding_box(part)
    size = (
        bbox[1][0] - bbox[0][0],
        bbox[1][1] - bbox[0][1],
        bbox[1][2] - bbox[0][2],
    )
    return create_box(
        size[0] + 2 * xy_slack,
        size[1] + 2 * xy_slack,
        size[2] + 2 * z_slack,
        origin=(
            bbox[0][0] - xy_slack,
            bbox[0][1] - xy_slack,
            bbox[0][2] - z_slack,
        ),
    )


def create_nitehawk_usb_board_assembly(
    *,
    nitehawk_usb_board_length,
    nitehawk_usb_board_width,
    nitehawk_usb_board_thickness,
    nitehawk_usb_board_corner_radius,
    nitehawk_usb_board_clearance_slack,
    nitehawk_usb_component_clearance_slack,
    nitehawk_usb_mount_hole_diameter,
    nitehawk_usb_mount_hole_front_left_x,
    nitehawk_usb_mount_hole_front_left_y,
    nitehawk_usb_mount_hole_front_right_x,
    nitehawk_usb_mount_hole_front_right_y,
    nitehawk_usb_mount_hole_back_x,
    nitehawk_usb_mount_hole_back_y,
    nitehawk_usb_terminal_block_length,
    nitehawk_usb_terminal_block_width,
    nitehawk_usb_terminal_block_height,
    nitehawk_usb_terminal_block_x,
    nitehawk_usb_terminal_block_y,
    nitehawk_usb_terminal_block_top_taper_height,
    nitehawk_usb_terminal_block_top_width,
    nitehawk_usb_terminal_block_window_side_margin,
    nitehawk_usb_terminal_block_window_center_divider,
    nitehawk_usb_terminal_block_window_bottom_lip,
    nitehawk_usb_terminal_block_window_top_lip,
    nitehawk_usb_terminal_block_window_back_wall,
    nitehawk_usb_usb_c_connector_length,
    nitehawk_usb_usb_c_connector_width,
    nitehawk_usb_usb_c_connector_height,
    nitehawk_usb_usb_c_connector_x,
    nitehawk_usb_usb_c_connector_y,
    nitehawk_usb_front_plug_length,
    nitehawk_usb_front_plug_width,
    nitehawk_usb_front_plug_height,
    nitehawk_usb_front_plug_x,
    nitehawk_usb_front_plug_y,
    nitehawk_usb_white_connector_length,
    nitehawk_usb_white_connector_width,
    nitehawk_usb_white_connector_height,
    nitehawk_usb_white_connector_x,
    nitehawk_usb_white_connector_y,
):
    """Create a holder-focused envelope of the Nitehawk USB daughterboard."""

    for name, value in [
        ("nitehawk_usb_board_length", nitehawk_usb_board_length),
        ("nitehawk_usb_board_width", nitehawk_usb_board_width),
        ("nitehawk_usb_board_thickness", nitehawk_usb_board_thickness),
        ("nitehawk_usb_board_clearance_slack", nitehawk_usb_board_clearance_slack),
        (
            "nitehawk_usb_component_clearance_slack",
            nitehawk_usb_component_clearance_slack,
        ),
        ("nitehawk_usb_mount_hole_diameter", nitehawk_usb_mount_hole_diameter),
    ]:
        _validate_positive(name, value)

    if nitehawk_usb_board_corner_radius < 0:
        raise ValueError("nitehawk_usb_board_corner_radius must not be negative.")

    if nitehawk_usb_board_corner_radius == 0:
        board = create_box(
            nitehawk_usb_board_length,
            nitehawk_usb_board_width,
            nitehawk_usb_board_thickness,
            origin=(0, 0, 0),
        )
    else:
        board = create_filleted_box(
            nitehawk_usb_board_length,
            nitehawk_usb_board_width,
            nitehawk_usb_board_thickness,
            nitehawk_usb_board_corner_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
        )

    mounting_holes = []
    for hole_name, x, y in [
        (
            "mounting_hole_front_left",
            nitehawk_usb_mount_hole_front_left_x,
            nitehawk_usb_mount_hole_front_left_y,
        ),
        (
            "mounting_hole_front_right",
            nitehawk_usb_mount_hole_front_right_x,
            nitehawk_usb_mount_hole_front_right_y,
        ),
        (
            "mounting_hole_back",
            nitehawk_usb_mount_hole_back_x,
            nitehawk_usb_mount_hole_back_y,
        ),
    ]:
        _validate_board_point(
            hole_name,
            x=x,
            y=y,
            board_length=nitehawk_usb_board_length,
            board_width=nitehawk_usb_board_width,
        )
        hole = create_cylinder(
            nitehawk_usb_mount_hole_diameter / 2,
            nitehawk_usb_board_thickness + 2,
        )
        hole = translate(x, y, -1)(hole)
        board = board.cut(hole)
        mounting_holes.append((hole_name, hole))

    component_specs = [
        (
            "terminal_block",
            nitehawk_usb_terminal_block_x,
            nitehawk_usb_terminal_block_y,
            nitehawk_usb_terminal_block_length,
            nitehawk_usb_terminal_block_width,
        ),
        (
            "usb_c_connector",
            nitehawk_usb_usb_c_connector_x,
            nitehawk_usb_usb_c_connector_y,
            nitehawk_usb_usb_c_connector_length,
            nitehawk_usb_usb_c_connector_width,
        ),
        (
            "front_plug",
            nitehawk_usb_front_plug_x,
            nitehawk_usb_front_plug_y,
            nitehawk_usb_front_plug_length,
            nitehawk_usb_front_plug_width,
        ),
        (
            "white_connector",
            nitehawk_usb_white_connector_x,
            nitehawk_usb_white_connector_y,
            nitehawk_usb_white_connector_length,
            nitehawk_usb_white_connector_width,
        ),
    ]
    for name, x, y, length, width in component_specs:
        _validate_positive(f"{name} length", length)
        _validate_positive(f"{name} width", width)
        _validate_component_on_board(
            name,
            x=x,
            y=y,
            length=length,
            width=width,
            board_length=nitehawk_usb_board_length,
            board_width=nitehawk_usb_board_width,
        )

    terminal_block = create_terminal_block(
        terminal_block_length=nitehawk_usb_terminal_block_length,
        terminal_block_width=nitehawk_usb_terminal_block_width,
        terminal_block_height=nitehawk_usb_terminal_block_height,
        terminal_block_top_taper_height=nitehawk_usb_terminal_block_top_taper_height,
        terminal_block_top_width=nitehawk_usb_terminal_block_top_width,
        terminal_block_window_side_margin=(
            nitehawk_usb_terminal_block_window_side_margin
        ),
        terminal_block_window_center_divider=(
            nitehawk_usb_terminal_block_window_center_divider
        ),
        terminal_block_window_bottom_lip=nitehawk_usb_terminal_block_window_bottom_lip,
        terminal_block_window_top_lip=nitehawk_usb_terminal_block_window_top_lip,
        terminal_block_window_back_wall=nitehawk_usb_terminal_block_window_back_wall,
    )
    terminal_block = rotate(180, center=get_bounding_box_center(terminal_block))(
        terminal_block
    )
    terminal_block = translate(
        nitehawk_usb_terminal_block_x,
        nitehawk_usb_terminal_block_y,
        nitehawk_usb_board_thickness,
    )(terminal_block)

    usb_c_connector = create_box(
        nitehawk_usb_usb_c_connector_length,
        nitehawk_usb_usb_c_connector_width,
        nitehawk_usb_usb_c_connector_height,
        origin=(
            nitehawk_usb_usb_c_connector_x,
            nitehawk_usb_usb_c_connector_y,
            nitehawk_usb_board_thickness,
        ),
    )

    front_plug = create_box(
        nitehawk_usb_front_plug_length,
        nitehawk_usb_front_plug_width,
        nitehawk_usb_front_plug_height,
        origin=(
            nitehawk_usb_front_plug_x,
            nitehawk_usb_front_plug_y,
            nitehawk_usb_board_thickness,
        ),
    )

    white_connector = create_box(
        nitehawk_usb_white_connector_length,
        nitehawk_usb_white_connector_width,
        nitehawk_usb_white_connector_height,
        origin=(
            nitehawk_usb_white_connector_x,
            nitehawk_usb_white_connector_y,
            nitehawk_usb_board_thickness,
        ),
    )

    assembly = LeaderFollowersCuttersPart(leader=board)
    assembly.add_named_follower(board, "board")
    assembly.add_named_follower(terminal_block, "terminal_block")
    assembly.add_named_follower(usb_c_connector, "usb_c_connector")
    assembly.add_named_follower(front_plug, "front_plug")
    assembly.add_named_follower(white_connector, "white_connector")

    assembly.add_named_cutter(
        _create_clearance_cutter(
            board,
            xy_slack=nitehawk_usb_board_clearance_slack,
            z_slack=nitehawk_usb_board_clearance_slack,
        ),
        "board_clearance",
    )
    for name, component in [
        ("terminal_block", terminal_block),
        ("usb_c_connector", usb_c_connector),
        ("front_plug", front_plug),
        ("white_connector", white_connector),
    ]:
        assembly.add_named_cutter(
            _create_clearance_cutter(
                component,
                xy_slack=nitehawk_usb_component_clearance_slack,
                z_slack=nitehawk_usb_component_clearance_slack,
            ),
            f"{name}_clearance",
        )

    for hole_name, hole in mounting_holes:
        assembly.add_named_cutter(hole, hole_name)

    return assembly
