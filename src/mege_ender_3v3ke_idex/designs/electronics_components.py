"""Reusable electronics component geometry."""

from shellforgepy.simple import *


def create_terminal_block(
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
    """Create a two-position screw terminal block envelope."""

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
