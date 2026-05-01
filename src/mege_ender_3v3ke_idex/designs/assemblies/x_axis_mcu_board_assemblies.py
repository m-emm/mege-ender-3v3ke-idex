"""Self-contained x-axis MCU board assemblies."""

from shellforgepy.simple import *


def _create_sil(
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
    if base_cutter_slack is not None:
        base_cutter = create_box(
            wire_wrap_pin_base_width + 2 * base_cutter_slack,
            dil_pitch * num_y_pins + 2 * base_cutter_slack,
            wire_wrap_pin_base_thickness + 2 * base_cutter_vertical_slack,
        )
        base_cutter = align(base_cutter, base, Alignment.CENTER)
        cutters.append(base_cutter)

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

    retval = base.fuse(pins)
    retval = LeaderFollowersCuttersPart(retval, cutters=cutters)
    retval.add_named_follower(top_pins, "top_pins")

    return rotate(180, axis=(0, 1, 0))(retval)


def _create_dil(
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
    left = _create_sil(
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

    right = _create_sil(
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


def _create_dil_board(
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

    dil = _create_dil(
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


def create_pico_w_board_assembly(
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
    x_axis_mcu_pico_board_thickness,
    x_axis_mcu_pico_board_y_pins,
    x_axis_mcu_pico_board_int_width,
    x_axis_mcu_pico_board_corner_radius,
    x_axis_mcu_pico_board_micro_usb_socket_offset,
    x_axis_mcu_pico_bar_cutter_slack,
    x_axis_mcu_micro_usb_socket_width,
    x_axis_mcu_micro_usb_socket_thickness,
    x_axis_mcu_micro_usb_socket_depth,
):
    retval = _create_dil_board(
        int_x_distance=x_axis_mcu_pico_board_int_width,
        num_y_pins=x_axis_mcu_pico_board_y_pins,
        board_thickness=x_axis_mcu_pico_board_thickness,
        board_corner_radius=x_axis_mcu_pico_board_corner_radius,
        dil_pitch=x_axis_mcu_dil_pitch,
        wire_wrap_pin_side=x_axis_mcu_wire_wrap_pin_side,
        wire_wrap_pin_length=x_axis_mcu_wire_wrap_pin_length,
        wire_wrap_pin_base_thickness=x_axis_mcu_wire_wrap_pin_base_thickness,
        wire_wrap_pin_base_width=x_axis_mcu_wire_wrap_pin_base_width,
        top_pin_length=x_axis_mcu_top_pin_length,
        pin_cutter_slack=0.0,
        base_cutter_slack=x_axis_mcu_electronics_holder_slack,
        base_cutter_vertical_slack=x_axis_mcu_base_cutter_vertical_slack,
        board_cutter_slack=x_axis_mcu_electronics_board_cutter_slack,
        y_overhang_in_pins=0.5,
    )

    micro_usb_socket = create_rounded_slab(
        x_axis_mcu_micro_usb_socket_width,
        x_axis_mcu_micro_usb_socket_thickness,
        x_axis_mcu_micro_usb_socket_depth,
        x_axis_mcu_micro_usb_socket_thickness / 2,
    )
    micro_usb_socket = rotate(90, axis=(1, 0, 0))(micro_usb_socket)
    micro_usb_socket = align(micro_usb_socket, retval, Alignment.CENTER)
    micro_usb_socket = align(micro_usb_socket, retval, Alignment.FRONT)
    micro_usb_socket = align(micro_usb_socket, retval, Alignment.STACK_TOP)
    micro_usb_socket = translate(
        0,
        -x_axis_mcu_pico_board_micro_usb_socket_offset,
        0,
    )(micro_usb_socket)

    micro_usb_socket_size = get_bounding_box_size(micro_usb_socket)
    micro_usb_socket_slack = 0.8
    micro_usb_socket_cutter = create_box(
        micro_usb_socket_size[0] + 2 * micro_usb_socket_slack,
        micro_usb_socket_size[1] + 2 * micro_usb_socket_slack,
        micro_usb_socket_size[2] + 2 * micro_usb_socket_slack,
    )
    micro_usb_socket_cutter = align(
        micro_usb_socket_cutter,
        micro_usb_socket,
        Alignment.CENTER,
    )

    retval = retval.fuse(micro_usb_socket)
    retval.cutters.append(micro_usb_socket_cutter)
    retval.add_named_non_production_part(micro_usb_socket, "micro_usb_socket")

    board_pcb = retval.get_follower_part_by_name("board")
    board_pcb_size = get_bounding_box_size(board_pcb)

    support_bars = PartCollector()
    support_bar_cutters = PartCollector()
    for bar_range in [(2, 2), (9, 10), (17, 17)]:
        support_bar = create_box(
            board_pcb_size[0],
            x_axis_mcu_dil_pitch * (bar_range[1] - bar_range[0] + 1),
            x_axis_mcu_wire_wrap_pin_base_thickness,
        )
        support_bar = align(support_bar, board_pcb, Alignment.CENTER)
        support_bar = align(support_bar, board_pcb, Alignment.FRONT)
        support_bar = align(support_bar, board_pcb, Alignment.STACK_BOTTOM)
        support_bar = translate(0, x_axis_mcu_dil_pitch * bar_range[0], 0)(support_bar)
        support_bars = support_bars.fuse(support_bar)

        support_bar_cutter = create_box(
            board_pcb_size[0],
            x_axis_mcu_dil_pitch * (bar_range[1] - bar_range[0] + 1)
            + 2 * x_axis_mcu_pico_bar_cutter_slack,
            x_axis_mcu_wire_wrap_pin_base_thickness,
        )
        support_bar_cutter = align(support_bar_cutter, support_bar, Alignment.CENTER)
        support_bar_cutters = support_bar_cutters.fuse(support_bar_cutter)

    retval = retval.fuse(support_bars)
    retval.cutters.append(support_bar_cutters)
    retval.add_named_non_production_part(support_bars, "support_bars")

    top_center = get_bounding_box_center(retval)
    return rotate(180, center=top_center)(retval)


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
):
    retval = _create_dil_board(
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
        pin_cutter_slack=0.0,
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

    additional_pins = _create_sil(
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
    holder_slack = 0.1
    base_cutter_vertical_slack = 0.2
    lip_size = 0.85

    pins = _create_sil(
        num_y_pins=board_holder_additional_pins_num_pins,
        dil_pitch=x_axis_mcu_dil_pitch,
        wire_wrap_pin_side=x_axis_mcu_wire_wrap_pin_side,
        wire_wrap_pin_length=x_axis_mcu_wire_wrap_pin_length,
        wire_wrap_pin_base_thickness=x_axis_mcu_wire_wrap_pin_base_thickness,
        wire_wrap_pin_base_width=x_axis_mcu_wire_wrap_pin_base_width,
        top_pin_length=x_axis_mcu_top_pin_length,
        pin_cutter_slack=0.5,
        base_cutter_slack=holder_slack,
        base_cutter_vertical_slack=base_cutter_vertical_slack,
    )
    pins_size = get_bounding_box_size(pins)

    base_plate = create_box(
        board_holder_additional_pins_base_plate_length,
        pins_size[1] + 2 * x_axis_mcu_dil_pitch,
        board_holder_base_plate_thickness,
    )
    base_plate = translate(0, 0, -board_holder_base_plate_thickness)(base_plate)

    pins = align(pins, base_plate, Alignment.CENTER, axes=[0, 1])
    base_plate = pins.use_as_cutter_on(base_plate)

    slit_cutter = create_box(
        0.4,
        pins_size[1] + 4 * x_axis_mcu_dil_pitch,
        BIG_THING,
    )
    slit_cutter = align(slit_cutter, pins, Alignment.CENTER)
    base_plate = base_plate.cut(slit_cutter)
    flat_base_plate = base_plate

    lip = create_right_triangle(
        lip_size,
        lip_size,
        pins_size[1],
        extrusion_direction=(0, 1, 0),
        a_normal=(1, 0, 0),
        b_normal=(0, 0, -1),
    )
    lip = align(lip, pins, Alignment.CENTER)
    lip = align(lip, pins, Alignment.RIGHT)
    lip = translate(holder_slack, 0, 0)(lip)
    lip = align(lip, base_plate, Alignment.STACK_TOP)
    base_plate = base_plate.fuse(lip)

    lip_holder = create_box(lip_size, pins_size[1], lip_size)
    lip_holder = align(lip_holder, lip, Alignment.CENTER)
    lip_holder = align(lip_holder, lip, Alignment.STACK_RIGHT)
    base_plate = base_plate.fuse(lip_holder)

    retval = LeaderFollowersCuttersPart(base_plate)
    retval.add_named_follower(flat_base_plate, "additional_pins_base_plate")
    retval.add_named_non_production_part(pins.leader, "pins")
    retval.add_named_non_production_part(
        pins.get_follower_part_by_name("top_pins"),
        "top_pins",
    )

    return retval
