import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

BIG_THING = 500
normal_pin_side = 0.65
wire_wrap_pin_side = 0.63
wire_wrap_pin_length = 12.1
wire_wrap_pin_base_thickness = 2.43
wire_wrap_pin_base_width = 2.5
dil_pitch = 2.54
standard_pin_length = 5.7

top_pin_length = 2.8

pcb_thickness = 1.1

default_top_pin_length = top_pin_length


def create_pins(
    num_y_pins, pin_length=wire_wrap_pin_length, pin_side=wire_wrap_pin_side
):
    pins = PartCollector()
    for j in range(num_y_pins):
        pin = create_box(pin_side, pin_side, pin_length)

        pin = translate(
            dil_pitch / 2 - (pin_side / 2),
            j * dil_pitch + (dil_pitch / 2) - (pin_side / 2),
            wire_wrap_pin_base_thickness,
        )(pin)
        pins = pins.fuse(pin)
    return pins


def create_sil(
    num_y_pins,
    pin_length=wire_wrap_pin_length,
    pin_side=wire_wrap_pin_side,
    top_pin_length=None,
    base_thickness=wire_wrap_pin_base_thickness,
    pin_cutter_slack=0.0,
    base_cutter_slack=None,
    base_cutter_vertical_slack=None,
    add_top_pin_cutters=False,
) -> LeaderFollowersCuttersPart:

    base = create_box(
        wire_wrap_pin_base_width, dil_pitch * (num_y_pins), base_thickness
    )

    if base_cutter_vertical_slack is None:
        base_cutter_vertical_slack = base_cutter_slack

    cutters = []
    if base_cutter_slack is not None:
        base_cutter = create_box(
            wire_wrap_pin_base_width + 2 * base_cutter_slack,
            dil_pitch * (num_y_pins) + 2 * base_cutter_slack,
            base_thickness + 2 * base_cutter_vertical_slack,
        )
        base_cutter = align(base_cutter, base, Alignment.CENTER)
        cutters.append(base_cutter)

    if top_pin_length is None:
        effective_top_pin_length = 0
    else:
        effective_top_pin_length = top_pin_length

    pins = PartCollector()
    top_pins = PartCollector()
    pin_cutters = PartCollector()
    for j in range(num_y_pins):
        pin = create_box(pin_side, pin_side, pin_length)

        pin = translate(
            dil_pitch / 2 - (pin_side / 2),
            j * dil_pitch + (dil_pitch / 2) - (pin_side / 2),
            0,
        )(pin)
        pins = pins.fuse(pin)

        pin_cutter = create_box(
            pin_side + 2 * pin_cutter_slack,
            pin_side + 2 * pin_cutter_slack,
            pin_length + 2 * pin_cutter_slack,
        )
        pin_cutter = align(pin_cutter, pin, Alignment.CENTER)
        pin_cutters = pin_cutters.fuse(pin_cutter)

        if effective_top_pin_length > 0:
            top_pin = create_box(pin_side, pin_side, top_pin_length)
            top_pin = translate(
                dil_pitch / 2 - (pin_side / 2),
                j * dil_pitch + (dil_pitch / 2) - (pin_side / 2),
                -base_thickness,
            )(top_pin)
            top_pins = top_pins.fuse(top_pin)

            if add_top_pin_cutters:
                top_pin_cutter = create_box(
                    pin_side + 2 * pin_cutter_slack,
                    pin_side + 2 * pin_cutter_slack,
                    top_pin_length + 2 * pin_cutter_slack,
                )
                top_pin_cutter = translate(
                    dil_pitch / 2 - (pin_side / 2) - pin_cutter_slack,
                    j * dil_pitch + (dil_pitch / 2) - (pin_side / 2) - pin_cutter_slack,
                    -base_thickness - pin_cutter_slack,
                )(top_pin_cutter)
                pin_cutters = pin_cutters.fuse(top_pin_cutter)

    cutters.append(pin_cutters)
    retval = base.fuse(pins)

    retval = LeaderFollowersCuttersPart(retval, cutters=cutters)

    if effective_top_pin_length > 0:
        retval.add_named_follower(top_pins, "top_pins")
    else:
        raise ValueError("kaput")

    retval = rotate(180, axis=(0, 1, 0))(retval)

    return retval


def create_dil(
    int_x_distance,
    num_y_pins,
    pin_length=wire_wrap_pin_length,
    pin_side=wire_wrap_pin_side,
    top_pin_length=None,
    base_thickness=wire_wrap_pin_base_thickness,
    pin_cutter_slack=0.0,
    base_cutter_slack=None,
    base_cutter_vertical_slack=None,
):

    base = create_sil(
        num_y_pins,
        pin_length=pin_length,
        pin_side=pin_side,
        top_pin_length=top_pin_length,
        base_thickness=base_thickness,
        pin_cutter_slack=pin_cutter_slack,
        base_cutter_slack=base_cutter_slack,
        base_cutter_vertical_slack=base_cutter_vertical_slack,
    )

    base_right = translate(int_x_distance * dil_pitch, 0, 0)(base)

    base = base.prefixed_copy("left_")
    base_right = base_right.prefixed_copy("right_")

    retval = base.fuse(base_right)

    return retval


def create_dil_board(
    int_x_distance,
    num_y_pins,
    board_thickness,
    board_corner_radius=None,
    pin_length=wire_wrap_pin_length,
    pin_side=wire_wrap_pin_side,
    top_pin_length=None,
    base_thickness=wire_wrap_pin_base_thickness,
    pin_cutter_slack=0.0,
    base_cutter_slack=None,
    base_cutter_vertical_slack=None,
    board_cutter_slack=0.0,
    x_overhang_in_pins=0.0,
    y_overhang_in_pins=0.5,
):

    boards = {}
    for key, slack in [("plain", 0), ("with_slack", board_cutter_slack)]:
        if board_corner_radius is None:
            board = create_box(
                int_x_distance * dil_pitch
                + wire_wrap_pin_base_width
                + 2 * x_overhang_in_pins * dil_pitch
                + 2 * slack,
                num_y_pins * dil_pitch + 2 * slack + 2 * y_overhang_in_pins * dil_pitch,
                board_thickness + 2 * slack,
            )
        else:
            board = create_filleted_box(
                int_x_distance * dil_pitch
                + wire_wrap_pin_base_width
                + 2 * x_overhang_in_pins * dil_pitch
                + 2 * slack,
                num_y_pins * dil_pitch + 2 * slack + 2 * y_overhang_in_pins * dil_pitch,
                board_thickness + 2 * slack,
                board_corner_radius,
                no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
            )
        boards[key] = board

    boards["with_slack"] = align(
        boards["with_slack"], boards["plain"], Alignment.CENTER
    )

    boards_lfc = LeaderFollowersCuttersPart(
        boards["plain"], cutters=[boards["with_slack"]]
    )

    boards_lfc.add_named_follower(boards["plain"], "board")

    dil = create_dil(
        int_x_distance,
        num_y_pins,
        pin_length=pin_length,
        pin_side=pin_side,
        top_pin_length=top_pin_length,
        base_thickness=base_thickness,
        pin_cutter_slack=pin_cutter_slack,
        base_cutter_slack=base_cutter_slack,
        base_cutter_vertical_slack=base_cutter_vertical_slack,
    )

    dil = align(dil, boards_lfc, Alignment.CENTER)
    dil = align(dil, boards_lfc, Alignment.STACK_BOTTOM, stack_gap=0)

    retval = dil.fuse(boards_lfc)

    retval.add_named_follower(dil, "dil")

    return retval


def create_sil_board(
    num_y_pins,
    board_x_size_in_pins,
    board_thickness,
    board_corner_radius=None,
    pin_length=wire_wrap_pin_length,
    pin_side=wire_wrap_pin_side,
    top_pin_length=None,
    base_thickness=wire_wrap_pin_base_thickness,
    pin_cutter_slack=0.0,
    base_cutter_slack=None,
    base_cutter_vertical_slack=None,
    board_cutter_slack=0.0,
    y_overhang_in_pins=0.5,
):

    boards = {}
    for key, slack in [("plain", 0), ("with_slack", board_cutter_slack)]:
        if board_corner_radius is None:
            board = create_box(
                board_x_size_in_pins * dil_pitch + 2 * slack,
                num_y_pins * dil_pitch + 2 * slack + 2 * y_overhang_in_pins * dil_pitch,
                board_thickness + 2 * slack,
            )
        else:
            board = create_filleted_box(
                board_x_size_in_pins * dil_pitch + 2 * slack,
                num_y_pins * dil_pitch + 2 * slack + 2 * y_overhang_in_pins * dil_pitch,
                board_thickness + 2 * slack,
                board_corner_radius,
                no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
            )
        boards[key] = board

    boards["with_slack"] = align(
        boards["with_slack"], boards["plain"], Alignment.CENTER
    )

    boards = LeaderFollowersCuttersPart(boards["plain"], cutters=[boards["with_slack"]])

    sil = create_sil(
        num_y_pins,
        pin_length=pin_length,
        pin_side=pin_side,
        top_pin_length=top_pin_length,
        base_thickness=base_thickness,
        pin_cutter_slack=pin_cutter_slack,
        base_cutter_slack=base_cutter_slack,
        base_cutter_vertical_slack=base_cutter_vertical_slack,
    )
    sil = align(sil, boards, Alignment.CENTER)
    sil = align(sil, boards, Alignment.RIGHT)
    sil = align(sil, boards, Alignment.STACK_BOTTOM)

    retval = sil.fuse(boards)

    return retval


def main():

    dempo_parts = PartList()

    if True:
        sil_8 = create_sil(
            8, top_pin_length=default_top_pin_length, base_cutter_slack=0.5
        )
        dempo_parts.add(
            sil_8.leaders_followers_fused(), "sil_8", skip_in_production=True
        )

        dil_4_8 = create_dil(
            4, 8, top_pin_length=default_top_pin_length, base_cutter_slack=0.5
        )

        dil_4_8 = align(dil_4_8, sil_8, Alignment.STACK_RIGHT, stack_gap=20)

        dempo_parts.add(
            dil_4_8.leaders_followers_fused(), "dil_4_8", skip_in_production=False
        )

        dil_board_4_8 = create_dil_board(
            num_y_pins=8,
            int_x_distance=4,
            board_thickness=1.6,
            board_corner_radius=2.0,
            top_pin_length=default_top_pin_length,
            board_cutter_slack=0.5,
            base_cutter_slack=0.5,
        )

        dil_board_4_8 = align(
            dil_board_4_8, dil_4_8, Alignment.STACK_RIGHT, stack_gap=20
        )

        dempo_parts.add(
            dil_board_4_8.leaders_followers_fused(),
            "dil_board_4_8",
            skip_in_production=False,
        )

        sil_board = create_sil_board(
            num_y_pins=8,
            board_x_size_in_pins=6,
            board_thickness=1.6,
            board_corner_radius=2.0,
            top_pin_length=default_top_pin_length,
            board_cutter_slack=0.5,
            base_cutter_slack=0.5,
        )

        sil_board = align(sil_board, dil_board_4_8, Alignment.STACK_RIGHT, stack_gap=20)
        dempo_parts.add(
            sil_board.leaders_followers_fused(),
            "sil_board",
            skip_in_production=False,
        )

        fused_boards = PartCollector()
        fused_cutters = PartCollector()
        for board in [sil_8, dil_4_8, dil_board_4_8, sil_board]:
            fused_boards = fused_boards.fuse(board)

            if board.cutters is not None:
                for cutter in board.cutters:
                    fused_cutters = fused_cutters.fuse(cutter)

        fused_bb = get_bounding_box_size(fused_boards)

        base = create_box(fused_bb[0] + 20, fused_bb[1] + 20, 1.5)

        base = align(base, fused_boards, Alignment.CENTER)
        base = align(base, sil_8, Alignment.TOP)

        base = fused_boards.use_as_cutter_on(base)
        dempo_parts.add(base, "base", skip_in_production=True)

        fused_cutters = translate(0, 50, 0)(fused_cutters)

        dempo_parts.add(fused_cutters, "all_cutters", skip_in_production=True)

    # sil_10 = create_sil(10, top_pin_length=default_top_pin_length, base_cutter_slack=0.5)
    # dempo_parts.add(sil_10.leaders_followers_fused(), "sil_8", skip_in_production=True)

    # fused_cutters = PartCollector()
    # for cutter in sil_10.cutters:
    #     fused_cutters = fused_cutters.fuse(cutter)
    # dempo_parts.add(fused_cutters, "all_cutters", skip_in_production=True)

    arrange_and_export(
        dempo_parts.as_list(),
    )


if __name__ == "__main__":
    format = "%(asctime)s - %(name)s - %(levelname)s: %(message)s"
    logging.basicConfig(level=logging.INFO, format=format)
    main()
