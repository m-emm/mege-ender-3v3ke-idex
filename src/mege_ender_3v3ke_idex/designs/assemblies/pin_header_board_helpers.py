"""Shared pin-header board geometry for electronics assemblies."""

from shellforgepy.simple import *


def create_sil_header(
    *,
    num_y_pins,
    dil_pitch,
    wire_wrap_pin_side,
    wire_wrap_pin_length,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_base_width,
    top_pin_length,
    pin_cutter_slack=0.0,
    base_cutter_slack=None,
    base_cutter_vertical_slack=None,
):
    base = create_box(
        wire_wrap_pin_base_width,
        dil_pitch * num_y_pins,
        wire_wrap_pin_base_thickness,
    )

    if base_cutter_vertical_slack is None:
        base_cutter_vertical_slack = base_cutter_slack

    cutters = []
    cutter_names = []
    if base_cutter_slack is not None:
        base_cutter = create_box(
            wire_wrap_pin_base_width + 2 * base_cutter_slack,
            dil_pitch * num_y_pins + 2 * base_cutter_slack,
            wire_wrap_pin_base_thickness + 2 * base_cutter_vertical_slack,
        )
        base_cutter = align(base_cutter, base, Alignment.CENTER)
        cutters.append(base_cutter)
        cutter_names.append("base_cutters")

    pins = PartCollector()
    top_pins = PartCollector()
    pin_cutters = PartCollector()
    for j in range(num_y_pins):
        pin = create_box(
            wire_wrap_pin_side,
            wire_wrap_pin_side,
            wire_wrap_pin_length,
        )
        pin = translate(
            dil_pitch / 2 - wire_wrap_pin_side / 2,
            j * dil_pitch + dil_pitch / 2 - wire_wrap_pin_side / 2,
            0,
        )(pin)
        pins = pins.fuse(pin)

        pin_cutter = create_box(
            wire_wrap_pin_side + 2 * pin_cutter_slack,
            wire_wrap_pin_side + 2 * pin_cutter_slack,
            wire_wrap_pin_length + 2 * pin_cutter_slack,
        )
        pin_cutter = align(pin_cutter, pin, Alignment.CENTER)
        pin_cutters = pin_cutters.fuse(pin_cutter)

        current_top_pin = create_box(
            wire_wrap_pin_side,
            wire_wrap_pin_side,
            top_pin_length,
        )
        current_top_pin = translate(
            dil_pitch / 2 - wire_wrap_pin_side / 2,
            j * dil_pitch + dil_pitch / 2 - wire_wrap_pin_side / 2,
            -wire_wrap_pin_base_thickness,
        )(current_top_pin)
        top_pins = top_pins.fuse(current_top_pin)

    cutters.append(pin_cutters)
    cutter_names.append("pin_cutters")

    retval = base.fuse(pins)
    retval = LeaderFollowersCuttersPart(
        retval,
        cutters=cutters,
        cutter_names=cutter_names,
    )
    retval.add_named_follower(top_pins, "top_pins")

    return rotate(180, axis=(0, 1, 0))(retval)


def create_dil_header(
    *,
    int_x_distance,
    num_y_pins,
    dil_pitch,
    wire_wrap_pin_side,
    wire_wrap_pin_length,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_base_width,
    top_pin_length,
    pin_cutter_slack=0.0,
    base_cutter_slack=None,
    base_cutter_vertical_slack=None,
):
    left = create_sil_header(
        num_y_pins=num_y_pins,
        dil_pitch=dil_pitch,
        wire_wrap_pin_side=wire_wrap_pin_side,
        wire_wrap_pin_length=wire_wrap_pin_length,
        wire_wrap_pin_base_thickness=wire_wrap_pin_base_thickness,
        wire_wrap_pin_base_width=wire_wrap_pin_base_width,
        top_pin_length=top_pin_length,
        pin_cutter_slack=pin_cutter_slack,
        base_cutter_slack=base_cutter_slack,
        base_cutter_vertical_slack=base_cutter_vertical_slack,
    ).prefixed_copy("left")

    right = create_sil_header(
        num_y_pins=num_y_pins,
        dil_pitch=dil_pitch,
        wire_wrap_pin_side=wire_wrap_pin_side,
        wire_wrap_pin_length=wire_wrap_pin_length,
        wire_wrap_pin_base_thickness=wire_wrap_pin_base_thickness,
        wire_wrap_pin_base_width=wire_wrap_pin_base_width,
        top_pin_length=top_pin_length,
        pin_cutter_slack=pin_cutter_slack,
        base_cutter_slack=base_cutter_slack,
        base_cutter_vertical_slack=base_cutter_vertical_slack,
    )
    right = translate(int_x_distance * dil_pitch, 0, 0)(right)
    right = right.prefixed_copy("right")

    return left.fuse(right)


def create_dil_board(
    *,
    int_x_distance,
    num_y_pins,
    board_thickness,
    board_corner_radius,
    dil_pitch,
    wire_wrap_pin_side,
    wire_wrap_pin_length,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_base_width,
    top_pin_length,
    pin_cutter_slack=0.0,
    base_cutter_slack=None,
    base_cutter_vertical_slack=None,
    board_cutter_slack=0.0,
    x_overhang_in_pins=0.0,
    y_overhang_in_pins=0.5,
):
    board_x_size = (
        int_x_distance * dil_pitch
        + wire_wrap_pin_base_width
        + 2 * x_overhang_in_pins * dil_pitch
    )
    board_y_size = num_y_pins * dil_pitch + 2 * y_overhang_in_pins * dil_pitch

    if board_corner_radius is None:
        board = create_box(board_x_size, board_y_size, board_thickness)
    else:
        board = create_filleted_box(
            board_x_size,
            board_y_size,
            board_thickness,
            board_corner_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
        )

    board_cutter = create_box(
        board_x_size + 2 * board_cutter_slack,
        board_y_size + 2 * board_cutter_slack,
        board_thickness + 2 * board_cutter_slack,
    )
    board_cutter = align(board_cutter, board, Alignment.CENTER)

    board_lfc = LeaderFollowersCuttersPart(board, cutters=[board_cutter])

    dil = create_dil_header(
        int_x_distance=int_x_distance,
        num_y_pins=num_y_pins,
        dil_pitch=dil_pitch,
        wire_wrap_pin_side=wire_wrap_pin_side,
        wire_wrap_pin_length=wire_wrap_pin_length,
        wire_wrap_pin_base_thickness=wire_wrap_pin_base_thickness,
        wire_wrap_pin_base_width=wire_wrap_pin_base_width,
        top_pin_length=top_pin_length,
        pin_cutter_slack=pin_cutter_slack,
        base_cutter_slack=base_cutter_slack,
        base_cutter_vertical_slack=base_cutter_vertical_slack,
    )
    dil = align(dil, board_lfc, Alignment.CENTER)
    dil = align(dil, board_lfc, Alignment.STACK_BOTTOM)

    retval = dil.fuse(board_lfc)
    retval.add_named_follower(board, "board")
    retval.add_named_follower(dil.leaders_followers_fused(), "dil")

    return retval
