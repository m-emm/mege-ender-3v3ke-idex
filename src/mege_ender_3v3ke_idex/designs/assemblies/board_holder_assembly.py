"""Assembly wrapper for the simplified MCU board holder."""

from mege_ender_3v3ke_idex.designs.plug_and_hole import create_plug
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
    base_plate = align(base_plate, enclosure_reference, Alignment.CENTER, axes=[0, 1])
    base_plate_bbox = get_bounding_box(base_plate)
    base_plate = translate(0, 0, board_z_offset - base_plate_bbox[1][2])(base_plate)

    return base_plate


def _fuse_parts(parts):
    if not parts:
        raise ValueError("Need at least one part to fuse.")

    fused = parts[0]
    for part in parts[1:]:
        fused = fused.fuse(part)
    return fused


def _create_cut_box_from_xy(
    x_min,
    x_max,
    y_min,
    y_max,
    *,
    z_min,
    z_height,
):
    return create_box(
        x_max - x_min,
        y_max - y_min,
        z_height,
        origin=(x_min, y_min, z_min),
    )


def _resolve_strap_definitions(
    *,
    board_part,
    dil_pitch,
    strap_pin_indices,
    y_overhang_in_pins=0.5,
):
    board_bbox = get_bounding_box(board_part)

    if strap_pin_indices is None:
        return [
            {
                "pin_index": None,
                "center_y": (board_bbox[0][1] + board_bbox[1][1]) / 2,
            }
        ]

    num_y_pins = int(
        round(
            ((board_bbox[1][1] - board_bbox[0][1]) - 2 * y_overhang_in_pins * dil_pitch)
            / dil_pitch
        )
    )
    strap_definitions = []
    for pin_index in strap_pin_indices:
        if pin_index < 0 or pin_index >= num_y_pins:
            raise ValueError(
                f"Cross strap pin index {pin_index} is outside the valid range "
                f"0..{num_y_pins - 1}."
            )
        center_y = (
            board_bbox[0][1]
            + y_overhang_in_pins * dil_pitch
            + (pin_index + 0.5) * dil_pitch
        )
        strap_definitions.append({"pin_index": int(pin_index), "center_y": center_y})

    return strap_definitions


def _get_board_part(board_assembly):
    if "board" in board_assembly.follower_indices_by_name:
        return board_assembly.get_follower_part_by_name("board")

    board_follower_names = [
        name
        for name in board_assembly.follower_indices_by_name
        if name.endswith("_board")
    ]
    if len(board_follower_names) != 1:
        raise ValueError("Could not resolve a unique board follower.")
    return board_assembly.get_follower_part_by_name(board_follower_names[0])


def _cut_cover_window_for_dil_board(
    *,
    cover,
    board_part,
    cover_z_min,
    tpu_cover_thickness,
    overlap_mm,
    strap_width,
    dil_pitch,
    strap_pin_indices,
):
    board_bbox = get_bounding_box(board_part)
    x_min = board_bbox[0][0] + overlap_mm
    x_max = board_bbox[1][0] - overlap_mm
    y_min = board_bbox[0][1] + overlap_mm
    y_max = board_bbox[1][1] - overlap_mm

    if x_max <= x_min:
        raise ValueError("Cover overlap left no window width for board.")

    board_window = _create_cut_box_from_xy(
        x_min,
        x_max,
        y_min,
        y_max,
        z_min=cover_z_min - 1.0,
        z_height=tpu_cover_thickness + 2.0,
    )
    cover = cover.cut(board_window)

    strap_metadata = []
    for strap_index, strap_definition in enumerate(
        _resolve_strap_definitions(
            board_part=board_part,
            dil_pitch=dil_pitch,
            strap_pin_indices=strap_pin_indices,
        )
    ):
        strap = create_box(
            x_max - x_min,
            strap_width,
            tpu_cover_thickness,
            origin=(
                x_min,
                strap_definition["center_y"] - strap_width / 2,
                cover_z_min,
            ),
        )
        cover = cover.fuse(strap)
        strap_metadata.append(
            {
                "pin_index": strap_definition["pin_index"],
                "center_y": strap_definition["center_y"],
                "width": strap_width,
                "bbox": get_bounding_box(strap),
            }
        )

    return cover, strap_metadata


def _create_tpu_cover(
    *,
    base_plate,
    pico_board,
    translated_tmc_boards,
    additional_pins,
    x_axis_mcu_dil_pitch,
    board_holder_tpu_cover_thickness,
    board_holder_tpu_cover_gap_above_base,
    board_holder_tpu_cover_pin_overlap_in_pitches,
    board_holder_tpu_cover_cross_strap_width_in_pitches,
):
    if board_holder_tpu_cover_gap_above_base < 0:
        raise ValueError("board_holder_tpu_cover_gap_above_base must be non-negative.")

    base_bbox = get_bounding_box(base_plate)
    cover_z_min = base_bbox[1][2] + board_holder_tpu_cover_gap_above_base
    cover = create_box(
        base_bbox[1][0] - base_bbox[0][0],
        base_bbox[1][1] - base_bbox[0][1],
        board_holder_tpu_cover_thickness,
        origin=(base_bbox[0][0], base_bbox[0][1], cover_z_min),
    )

    overlap_mm = board_holder_tpu_cover_pin_overlap_in_pitches * x_axis_mcu_dil_pitch
    strap_width = (
        board_holder_tpu_cover_cross_strap_width_in_pitches * x_axis_mcu_dil_pitch
    )

    strap_metadata = {"pico_board": [], "tmc_boards": []}

    cover, strap_metadata["pico_board"] = _cut_cover_window_for_dil_board(
        cover=cover,
        board_part=_get_board_part(pico_board),
        cover_z_min=cover_z_min,
        tpu_cover_thickness=board_holder_tpu_cover_thickness,
        overlap_mm=overlap_mm,
        strap_width=strap_width,
        dil_pitch=x_axis_mcu_dil_pitch,
        strap_pin_indices=[3, 10, 17],
    )

    for tmc_board in translated_tmc_boards:
        cover, current_tmc_strap_metadata = _cut_cover_window_for_dil_board(
            cover=cover,
            board_part=_get_board_part(tmc_board),
            cover_z_min=cover_z_min,
            tpu_cover_thickness=board_holder_tpu_cover_thickness,
            overlap_mm=overlap_mm,
            strap_width=strap_width,
            dil_pitch=x_axis_mcu_dil_pitch,
            strap_pin_indices=[1,6],
        )
        strap_metadata["tmc_boards"].append(current_tmc_strap_metadata)

    additional_pins_bbox = get_bounding_box(additional_pins.get_named_non_production_part("pins"))
    additional_pins_window = _create_cut_box_from_xy(
        additional_pins_bbox[0][0],
        additional_pins_bbox[1][0],
        additional_pins_bbox[0][1],
        additional_pins_bbox[1][1],
        z_min=cover_z_min - 1.0,
        z_height=board_holder_tpu_cover_thickness + 2.0,
    )
    cover = cover.cut(additional_pins_window)

    return cover, strap_metadata


def _create_cover_plugs(
    *,
    cover,
    big_thing,
    board_holder_tpu_cover_gap_above_base,
    board_holder_plug_corner_inset,
    board_holder_plug_positions,
    board_holder_plug_diameter,
    board_holder_plug_angle_deg,
    board_holder_plug_height,
    board_holder_plug_wall_thickness,
    board_holder_plug_base_thickness,
    board_holder_plug_slit_width,
    board_holder_plug_fillet_radius,
    board_holder_plug_lip_height,
    board_holder_plug_lip_size,
    board_holder_plug_lip_top_gap,
    board_holder_plug_no_inner_hole,
    board_holder_plug_hole_slack,
):
    anchor_thickness = 1e-3
    if board_holder_plug_positions is None:
        plug_anchors = []
        for left_right_alignment in [Alignment.LEFT, Alignment.RIGHT]:
            for front_back_alignment in [Alignment.FRONT, Alignment.BACK]:
                plug_anchor = create_box(
                    anchor_thickness,
                    anchor_thickness,
                    anchor_thickness,
                )
                plug_anchor = align(
                    plug_anchor, cover, left_right_alignment.edge_alignment
                )
                plug_anchor = align(
                    plug_anchor, cover, front_back_alignment.edge_alignment
                )
                plug_anchor = align(plug_anchor, cover, Alignment.BOTTOM)
                plug_anchor = translate(
                    -left_right_alignment.sign * board_holder_plug_corner_inset,
                    -front_back_alignment.sign * board_holder_plug_corner_inset,
                    0,
                )(plug_anchor)
                plug_anchors.append(plug_anchor)
    else:
        plug_anchors = []
        for x_pos, y_pos in board_holder_plug_positions:
            plug_anchor = create_box(
                anchor_thickness,
                anchor_thickness,
                anchor_thickness,
                origin=(
                    x_pos - anchor_thickness / 2,
                    y_pos - anchor_thickness / 2,
                    -anchor_thickness / 2,
                ),
            )
            plug_anchor = align(plug_anchor, cover, Alignment.BOTTOM)
            plug_anchors.append(plug_anchor)

    cover_with_plugs = cover
    hole_cutters = []
    effective_plug_height = (
        board_holder_plug_height + board_holder_tpu_cover_gap_above_base
    )
    for plug_anchor in plug_anchors:
        plug = create_plug(
            plug_diameter=board_holder_plug_diameter,
            plug_angle_deg=board_holder_plug_angle_deg,
            plug_height=effective_plug_height,
            plug_wall_thickness=board_holder_plug_wall_thickness,
            plug_base_thickness=board_holder_plug_base_thickness,
            plug_slit_width=board_holder_plug_slit_width,
            fillet_radius=board_holder_plug_fillet_radius,
            plug_lip_height=board_holder_plug_lip_height,
            plug_lip_size=board_holder_plug_lip_size,
            plug_lip_top_gap=board_holder_plug_lip_top_gap,
            no_inner_hole=board_holder_plug_no_inner_hole,
        )
        plug = rotate(180, axis=(1, 0, 0))(plug)
        plug = align(plug, plug_anchor, Alignment.CENTER, axes=[0, 1])
        plug = align(plug, plug_anchor, Alignment.STACK_BOTTOM, stack_gap=0)
        cover_with_plugs = cover_with_plugs.fuse(plug)

        hole_cutter = create_cylinder(
            board_holder_plug_diameter / 2 + board_holder_plug_hole_slack,
            big_thing,
        )
        hole_cutter = align(hole_cutter, plug, Alignment.CENTER)
        hole_cutters.append(hole_cutter)

    return cover_with_plugs, hole_cutters


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
    x_axis_mcu_dil_pitch,
    board_holder_tpu_cover_thickness,
    board_holder_tpu_cover_gap_above_base,
    board_holder_tpu_cover_pin_overlap_in_pitches,
    board_holder_tpu_cover_cross_strap_width_in_pitches,
    board_holder_plug_corner_inset,
    board_holder_plug_positions,
    board_holder_plug_diameter,
    board_holder_plug_angle_deg,
    board_holder_plug_height,
    board_holder_plug_wall_thickness,
    board_holder_plug_base_thickness,
    board_holder_plug_slit_width,
    board_holder_plug_fillet_radius,
    board_holder_plug_lip_height,
    board_holder_plug_lip_size,
    board_holder_plug_lip_top_gap,
    board_holder_plug_no_inner_hole,
    board_holder_plug_hole_slack,
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
    tmc_x_offset = pico_holder_reference_bbox[1][0] - tmc_holder_reference_bbox[0][0]

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
    additional_pins = align(additional_pins, holder_reference, Alignment.STACK_RIGHT)
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

    tpu_cover, tpu_cover_strap_metadata = _create_tpu_cover(
        base_plate=all_holders.leader,
        pico_board=pico_board,
        translated_tmc_boards=translated_tmc_boards,
        additional_pins=additional_pins,
        x_axis_mcu_dil_pitch=x_axis_mcu_dil_pitch,
        board_holder_tpu_cover_thickness=board_holder_tpu_cover_thickness,
        board_holder_tpu_cover_gap_above_base=board_holder_tpu_cover_gap_above_base,
        board_holder_tpu_cover_pin_overlap_in_pitches=board_holder_tpu_cover_pin_overlap_in_pitches,        
        board_holder_tpu_cover_cross_strap_width_in_pitches=board_holder_tpu_cover_cross_strap_width_in_pitches,
    )
    tpu_cover, cover_plug_hole_cutters = _create_cover_plugs(
        cover=tpu_cover,
        big_thing=BIG_THING,
        board_holder_tpu_cover_gap_above_base=board_holder_tpu_cover_gap_above_base,
        board_holder_plug_corner_inset=board_holder_plug_corner_inset,
        board_holder_plug_positions=board_holder_plug_positions,
        board_holder_plug_diameter=board_holder_plug_diameter,
        board_holder_plug_angle_deg=board_holder_plug_angle_deg,
        board_holder_plug_height=board_holder_plug_height,
        board_holder_plug_wall_thickness=board_holder_plug_wall_thickness,
        board_holder_plug_base_thickness=board_holder_plug_base_thickness,
        board_holder_plug_slit_width=board_holder_plug_slit_width,
        board_holder_plug_fillet_radius=board_holder_plug_fillet_radius,
        board_holder_plug_lip_height=board_holder_plug_lip_height,
        board_holder_plug_lip_size=board_holder_plug_lip_size,
        board_holder_plug_lip_top_gap=board_holder_plug_lip_top_gap,
        board_holder_plug_no_inner_hole=board_holder_plug_no_inner_hole,
        board_holder_plug_hole_slack=board_holder_plug_hole_slack,
    )
    if cover_plug_hole_cutters:
        cover_plug_holes = _fuse_parts(cover_plug_hole_cutters)
        all_holders.leader = all_holders.leader.cut(cover_plug_holes)
        all_holders.add_named_cutter(cover_plug_holes, "cover_plug_holes")
    all_holders.add_named_follower(tpu_cover, "tpu_cover")
    all_holders.additional_data["tpu_cover_straps"] = tpu_cover_strap_metadata

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
