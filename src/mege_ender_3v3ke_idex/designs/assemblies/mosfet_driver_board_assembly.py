"""MOSFET driver board assembly."""

from shellforgepy.simple import *


def _create_terminal_block(
    *,
    terminal_block_length,
    terminal_block_width,
    terminal_block_height,
    terminal_block_top_taper_height,
    terminal_block_top_width,
    terminal_block_window_side_margin,
    terminal_block_window_center_divider,
    terminal_block_window_bottom_lip,
    terminal_block_window_top_lip,
    terminal_block_window_back_wall,
):
    if terminal_block_top_taper_height <= 0:
        raise ValueError("terminal_block_top_taper_height must be positive.")
    if terminal_block_top_taper_height >= terminal_block_height:
        raise ValueError(
            "terminal_block_top_taper_height must be smaller than the total height."
        )
    if terminal_block_top_width <= 0:
        raise ValueError("terminal_block_top_width must be positive.")
    if terminal_block_top_width > terminal_block_width:
        raise ValueError(
            "terminal_block_top_width must not exceed terminal_block_width."
        )

    base_height = terminal_block_height - terminal_block_top_taper_height
    base = create_box(
        terminal_block_length,
        terminal_block_width,
        base_height,
    )
    cap = create_pyramid_stump(
        terminal_block_length,
        terminal_block_length,
        terminal_block_width,
        terminal_block_top_width,
        terminal_block_top_taper_height,
    )
    cap = align(cap, base, Alignment.CENTER, axes=[0, 1])
    cap = align(cap, base, Alignment.STACK_TOP)

    window_width = (
        terminal_block_length
        - 2 * terminal_block_window_side_margin
        - terminal_block_window_center_divider
    ) / 2
    if window_width <= 0:
        raise ValueError("Terminal block window width must be positive.")

    window_height = (
        base_height - terminal_block_window_bottom_lip - terminal_block_window_top_lip
    )
    if window_height <= 0:
        raise ValueError("Terminal block window height must be positive.")

    if terminal_block_window_back_wall <= 0:
        raise ValueError("terminal_block_window_back_wall must be positive.")
    if terminal_block_window_back_wall >= terminal_block_width:
        raise ValueError(
            "terminal_block_window_back_wall must be smaller than terminal_block_width."
        )

    block = base.fuse(cap)
    window_depth = terminal_block_width - terminal_block_window_back_wall
    for window_index in range(2):
        window = create_box(
            window_width,
            window_depth + 0.02,
            window_height,
            origin=(
                terminal_block_window_side_margin
                + window_index * (window_width + terminal_block_window_center_divider),
                terminal_block_width - window_depth - 0.01,
                terminal_block_window_bottom_lip,
            ),
        )
        block = block.cut(window)

    return block


def create_mosfet_driver_board_assembly(
    *,
    mosfet_driver_board_length,
    mosfet_driver_board_width,
    mosfet_driver_board_thickness,
    mosfet_driver_mount_hole_diameter,
    mosfet_driver_mount_hole_edge_clearance,
    mosfet_driver_terminal_block_length,
    mosfet_driver_terminal_block_width,
    mosfet_driver_terminal_block_height,
    mosfet_driver_terminal_block_gap,
    mosfet_driver_terminal_block_top_taper_height,
    mosfet_driver_terminal_block_top_width,
    mosfet_driver_terminal_block_window_side_margin,
    mosfet_driver_terminal_block_window_center_divider,
    mosfet_driver_terminal_block_window_bottom_lip,
    mosfet_driver_terminal_block_window_top_lip,
    mosfet_driver_terminal_block_window_back_wall,
    mosfet_driver_package_length,
    mosfet_driver_package_width,
    mosfet_driver_package_height,
    mosfet_driver_package_gap_to_terminal_block,
):
    hole_center_offset = (
        mosfet_driver_mount_hole_edge_clearance + mosfet_driver_mount_hole_diameter / 2
    )
    if hole_center_offset * 2 >= mosfet_driver_board_width:
        raise ValueError("Mount holes do not fit within the board width.")
    if hole_center_offset * 2 >= mosfet_driver_board_length:
        raise ValueError("Mount holes do not fit within the board length.")

    terminal_block_outer_margin = (
        mosfet_driver_board_width
        - 2 * mosfet_driver_terminal_block_width
        - mosfet_driver_terminal_block_gap
    ) / 2
    if terminal_block_outer_margin < 0:
        raise ValueError("Terminal blocks do not fit within the board width.")

    terminal_block_x_origin = (
        mosfet_driver_board_length - mosfet_driver_terminal_block_length
    )
    package_x_origin = (
        terminal_block_x_origin
        - mosfet_driver_package_gap_to_terminal_block
        - mosfet_driver_package_length
    )
    if package_x_origin < 0:
        raise ValueError("MOSFET packages do not fit on the board length.")
    if mosfet_driver_package_width > mosfet_driver_terminal_block_width:
        raise ValueError(
            "MOSFET package width must not exceed the terminal block width."
        )

    board = create_box(
        mosfet_driver_board_length,
        mosfet_driver_board_width,
        mosfet_driver_board_thickness,
        origin=(0, 0, 0),
    )

    mount_hole_y_positions = [
        hole_center_offset,
        mosfet_driver_board_width - hole_center_offset,
    ]
    mount_holes = []
    for mount_hole_y in mount_hole_y_positions:
        mount_hole = create_cylinder(
            mosfet_driver_mount_hole_diameter / 2,
            mosfet_driver_board_thickness + 2,
        )
        mount_hole = translate(hole_center_offset, mount_hole_y, -1)(mount_hole)
        board = board.cut(mount_hole)
        mount_holes.append(mount_hole)

    terminal_block_front = _create_terminal_block(
        terminal_block_length=mosfet_driver_terminal_block_length,
        terminal_block_width=mosfet_driver_terminal_block_width,
        terminal_block_height=mosfet_driver_terminal_block_height,
        terminal_block_top_taper_height=mosfet_driver_terminal_block_top_taper_height,
        terminal_block_top_width=mosfet_driver_terminal_block_top_width,
        terminal_block_window_side_margin=mosfet_driver_terminal_block_window_side_margin,
        terminal_block_window_center_divider=mosfet_driver_terminal_block_window_center_divider,
        terminal_block_window_bottom_lip=mosfet_driver_terminal_block_window_bottom_lip,
        terminal_block_window_top_lip=mosfet_driver_terminal_block_window_top_lip,
        terminal_block_window_back_wall=mosfet_driver_terminal_block_window_back_wall,
    )
    terminal_block_front_center = get_bounding_box_center(terminal_block_front)
    terminal_block_front = rotate(180, center=terminal_block_front_center)(
        terminal_block_front
    )
    terminal_block_front = translate(
        terminal_block_x_origin,
        terminal_block_outer_margin,
        mosfet_driver_board_thickness,
    )(terminal_block_front)

    terminal_block_back = _create_terminal_block(
        terminal_block_length=mosfet_driver_terminal_block_length,
        terminal_block_width=mosfet_driver_terminal_block_width,
        terminal_block_height=mosfet_driver_terminal_block_height,
        terminal_block_top_taper_height=mosfet_driver_terminal_block_top_taper_height,
        terminal_block_top_width=mosfet_driver_terminal_block_top_width,
        terminal_block_window_side_margin=mosfet_driver_terminal_block_window_side_margin,
        terminal_block_window_center_divider=mosfet_driver_terminal_block_window_center_divider,
        terminal_block_window_bottom_lip=mosfet_driver_terminal_block_window_bottom_lip,
        terminal_block_window_top_lip=mosfet_driver_terminal_block_window_top_lip,
        terminal_block_window_back_wall=mosfet_driver_terminal_block_window_back_wall,
    )

    terminal_block_back = translate(
        terminal_block_x_origin,
        terminal_block_outer_margin
        + mosfet_driver_terminal_block_width
        + mosfet_driver_terminal_block_gap,
        mosfet_driver_board_thickness,
    )(terminal_block_back)

    package_y_inset = (
        mosfet_driver_terminal_block_width - mosfet_driver_package_width
    ) / 2
    mosfet_package_front = create_box(
        mosfet_driver_package_length,
        mosfet_driver_package_width,
        mosfet_driver_package_height,
        origin=(
            package_x_origin,
            terminal_block_outer_margin + package_y_inset,
            mosfet_driver_board_thickness,
        ),
    )
    mosfet_package_back = create_box(
        mosfet_driver_package_length,
        mosfet_driver_package_width,
        mosfet_driver_package_height,
        origin=(
            package_x_origin,
            terminal_block_outer_margin
            + mosfet_driver_terminal_block_width
            + mosfet_driver_terminal_block_gap
            + package_y_inset,
            mosfet_driver_board_thickness,
        ),
    )

    assembly = LeaderFollowersCuttersPart(leader=board)
    assembly.add_named_follower(board, "board")
    assembly.add_named_follower(terminal_block_front, "terminal_block_front")
    assembly.add_named_follower(terminal_block_back, "terminal_block_back")
    assembly.add_named_follower(mosfet_package_front, "mosfet_package_front")
    assembly.add_named_follower(mosfet_package_back, "mosfet_package_back")
    assembly.add_named_cutter(mount_holes[0], "mounting_hole_front")
    assembly.add_named_cutter(mount_holes[1], "mounting_hole_back")

    return assembly
