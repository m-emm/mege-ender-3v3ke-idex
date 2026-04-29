"""Assembly wrapper for the simplified MCU board holder."""

from shellforgepy.simple import *


def _create_board_holder(
    *,
    board,
    board_pcb=None,
    board_pcb_follower_name="board",
    board_cutting_part=None,
    base_plate_border=7.0,
    base_plate_border_y_ratio=1.0 / 3.0,
    base_plate_x_size_override=None,
    base_plate_y_size_override=None,
    base_plate_thickness=3.1,
    board_z_offset=0.005,
):
    if board_pcb is None:
        board_pcb = board.get_follower_part_by_name(board_pcb_follower_name)

    def cut_with_board(part):
        if board_cutting_part is not None:
            return part.cut(board_cutting_part)
        if hasattr(board, "use_as_cutter_on"):
            return board.use_as_cutter_on(part)
        return part.cut(board)

    board_size = get_bounding_box_size(board)

    base_plate_size = (
        (
            base_plate_x_size_override
            if base_plate_x_size_override is not None
            else board_size[0] + 2 * base_plate_border
        ),
        (
            base_plate_y_size_override
            if base_plate_y_size_override is not None
            else board_size[1] + 2 * base_plate_border * base_plate_border_y_ratio
        ),
        base_plate_thickness,
    )

    base_plate = create_box(*base_plate_size)
    base_plate = align(base_plate, board, Alignment.CENTER, axes=[0, 1])
    base_plate_bbox = get_bounding_box(base_plate)
    base_plate = translate(0, 0, -base_plate_bbox[1][2] + board_z_offset)(base_plate)
    base_plate = cut_with_board(base_plate)

    return LeaderFollowersCuttersPart(base_plate)


def _create_enclosing_base_plate(
    *,
    enclosure_reference,
    base_plate_border,
    base_plate_y_size_min,
    base_plate_thickness,
    board_z_offset,
):
    enclosure_size = get_bounding_box_size(enclosure_reference)
    base_plate_x_size = enclosure_size[0] + 2 * base_plate_border
    base_plate_y_size = max(
        enclosure_size[1] + 2 * base_plate_border,
        base_plate_y_size_min,
    )

    base_plate = create_box(
        base_plate_x_size,
        base_plate_y_size,
        base_plate_thickness,
    )
    base_plate = align(
        base_plate, enclosure_reference, Alignment.CENTER, axes=[0, 1]
    )
    base_plate_bbox = get_bounding_box(base_plate)
    base_plate = translate(0, 0, board_z_offset - base_plate_bbox[1][2])(base_plate)

    return base_plate


def _cut_mount_screw_holes(
    *,
    holder,
    mount_screw_size,
    mount_screw_hole_inset,
    big_thing,
):
    mount_screw_holes = PartCollector()
    for left_right_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        for front_back_alignment in [Alignment.FRONT, Alignment.BACK]:
            screw_hole = create_cylinder(
                MScrew.from_size(mount_screw_size).clearance_hole_normal / 2,
                big_thing,
            )
            screw_hole = align(screw_hole, holder, Alignment.CENTER)
            screw_hole = align(screw_hole, holder, left_right_alignment)
            screw_hole = align(screw_hole, holder, front_back_alignment)
            screw_hole = translate(
                -left_right_alignment.sign * mount_screw_hole_inset,
                -front_back_alignment.sign * mount_screw_hole_inset,
                0,
            )(screw_hole)
            mount_screw_holes = mount_screw_holes.fuse(screw_hole)

    holder = holder.cut(mount_screw_holes)
    holder.add_named_cutter(mount_screw_holes, "mount_screw_holes")
    return holder


def _get_named_tmc_board_visual_prefix(index):
    if index == 0:
        return "tmc_board"
    return f"tmc_board_{index + 1}"


def _get_named_tmc_holder_prefix(index):
    if index == 0:
        return "tmc"
    return f"tmc_{index + 1}"


def _create_tmc_board_row(
    *,
    pico_board,
    tmc_board_template,
    tmc_board_count,
):
    if tmc_board_count < 1:
        raise ValueError("tmc_board_count must be at least 1")

    first_tmc_board = tmc_board_template.copy()
    first_tmc_board = align(first_tmc_board, pico_board, Alignment.FRONT)

    tmc_board_size = get_bounding_box_size(first_tmc_board)
    pico_board_size = get_bounding_box_size(pico_board)
    inter_board_gap = pico_board_size[1] - 2 * tmc_board_size[1]
    if inter_board_gap < 0:
        raise ValueError("TMC board row gap became negative")

    tmc_board_pitch = tmc_board_size[1] + inter_board_gap

    tmc_boards = []
    previous_tmc_board = first_tmc_board
    tmc_boards.append(previous_tmc_board)

    for tmc_index in range(1, tmc_board_count):
        current_tmc_board = tmc_board_template.copy()
        current_tmc_board = align(
            current_tmc_board,
            previous_tmc_board,
            Alignment.STACK_BACK,
            stack_gap=inter_board_gap,
        )
        current_tmc_board = current_tmc_board.prefixed_copy(
            _get_named_tmc_holder_prefix(tmc_index)
        )
        tmc_boards.append(current_tmc_board)
        previous_tmc_board = current_tmc_board

    tmc_board_row = tmc_boards[0]
    for current_tmc_board in tmc_boards[1:]:
        tmc_board_row = tmc_board_row.fuse(current_tmc_board)

    return tmc_board_row, tmc_boards, tmc_board_pitch


def create_board_holder_assembly(
    *,
    pico_w_board_assembly,
    tmc_board_assembly,
    additional_pins_assembly,
    board_holder_base_plate_border,
    board_holder_base_plate_y_size,
    board_holder_base_plate_thickness,
    board_holder_board_z_offset,
    board_holder_mount_screw_size,
    board_holder_mount_screw_hole_inset,
    board_holder_tmc_board_count,
    BIG_THING,
):
    """Create the simplified MCU board holder assembly."""

    pico_board = pico_w_board_assembly.copy()
    pico_holder_reference = _create_board_holder(
        board=pico_board,
        base_plate_border=board_holder_base_plate_border,
        base_plate_thickness=board_holder_base_plate_thickness,
        base_plate_y_size_override=board_holder_base_plate_y_size,
        board_z_offset=board_holder_board_z_offset,
    )

    tmc_boards, positioned_tmc_boards, tmc_board_pitch = _create_tmc_board_row(
        pico_board=pico_board,
        tmc_board_template=tmc_board_assembly,
        tmc_board_count=board_holder_tmc_board_count,
    )
    tmc_base_plate_y_size = (
        board_holder_base_plate_y_size
        + max(0, board_holder_tmc_board_count - 2) * tmc_board_pitch
    )

    tmc_holder_reference = _create_board_holder(
        board=tmc_boards,
        base_plate_border=board_holder_base_plate_border,
        base_plate_thickness=board_holder_base_plate_thickness,
        base_plate_y_size_override=tmc_base_plate_y_size,
        board_z_offset=board_holder_board_z_offset,
    )

    pico_holder_reference_bbox = get_bounding_box(pico_holder_reference)
    tmc_holder_reference_bbox = get_bounding_box(tmc_holder_reference)
    tmc_x_offset = (
        pico_holder_reference_bbox[1][0] - tmc_holder_reference_bbox[0][0]
    )

    tmc_translation = translate(tmc_x_offset, 0, 0)
    translated_tmc_board_row = tmc_translation(tmc_boards)
    translated_tmc_boards = []
    for current_tmc_board in positioned_tmc_boards:
        translated_tmc_boards.append(tmc_translation(current_tmc_board))

    holder_reference = pico_holder_reference.fuse(tmc_translation(tmc_holder_reference))

    additional_pins = additional_pins_assembly.copy()
    additional_pins = align(
        additional_pins, holder_reference, Alignment.CENTER, axes=[1]
    )
    additional_pins = align(
        additional_pins, holder_reference, Alignment.STACK_RIGHT
    )
    additional_pins = translate(0, 0, board_holder_board_z_offset)(additional_pins)

    additional_pins_base_plate_bbox = materialize_bounding_box(additional_pins.leader)
    enclosure_reference = pico_board.leaders_followers_fused().fuse(
        translated_tmc_board_row.leaders_followers_fused()
    )
    enclosure_reference = enclosure_reference.fuse(additional_pins_base_plate_bbox)

    base_plate = _create_enclosing_base_plate(
        enclosure_reference=enclosure_reference,
        base_plate_border=board_holder_base_plate_border,
        base_plate_y_size_min=board_holder_base_plate_y_size,
        base_plate_thickness=board_holder_base_plate_thickness,
        board_z_offset=board_holder_board_z_offset,
    )
    base_plate = pico_board.use_as_cutter_on(base_plate)
    base_plate = translated_tmc_board_row.use_as_cutter_on(base_plate)
    base_plate = base_plate.cut(additional_pins_base_plate_bbox)

    all_holders = LeaderFollowersCuttersPart(base_plate.fuse(additional_pins.leader))

    all_holders = _cut_mount_screw_holes(
        holder=all_holders,
        mount_screw_size=board_holder_mount_screw_size,
        mount_screw_hole_inset=board_holder_mount_screw_hole_inset,
        big_thing=BIG_THING,
    )

    all_holders = all_holders.merge_except_leader(
        pico_board.prefixed_copy("pico_board")
    )
    additional_pins_prefixed = additional_pins.prefixed_copy("additional_pins")
    for name, part in additional_pins_prefixed.get_named_non_production_part_items():
        all_holders.add_named_non_production_part(part, name)

    for tmc_index, current_tmc_board in enumerate(translated_tmc_boards):
        all_holders = all_holders.merge_except_leader(
            current_tmc_board.prefixed_copy(
                _get_named_tmc_board_visual_prefix(tmc_index)
            )
        )

    return all_holders
