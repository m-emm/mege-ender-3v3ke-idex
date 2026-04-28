"""Assembly wrapper for the x-axis MCU board holder."""

import math

from shellforgepy.simple import *


def _arc_from_chord_and_sagitta(length, sagitta):
    if sagitta <= 0:
        raise ValueError("sagitta must be > 0")
    if length <= 0:
        raise ValueError("length must be > 0")

    radius = ((length / 2) ** 2 + sagitta**2) / (2 * sagitta)
    x_value = length / (2 * radius)
    x_value = max(-1.0, min(1.0, x_value))
    angle = 2 * math.asin(x_value)
    return radius, angle


def _create_leaf_spring(
    *,
    spring_length,
    spring_thickness,
    spring_height,
    spring_mid_deflection,
):
    spring_radius, spring_angle = _arc_from_chord_and_sagitta(
        spring_length,
        spring_mid_deflection,
    )
    spring_angle = math.degrees(spring_angle)

    spring = create_ring(
        outer_radius=spring_radius,
        inner_radius=spring_radius - spring_thickness,
        height=spring_height,
        angle=spring_angle,
    )
    spring = rotate(-spring_angle / 2 + 90)(spring)
    return align(spring, None, Alignment.CENTER, axes=[0, 1])


def _create_linear_guide(
    *,
    carriage_width,
    carriage_length,
    guide_length,
    guide_width,
    thickness,
    guide_end_border,
    guide_clearance=0.1,
    skip_back_end_border=False,
):
    guide_rail_side = thickness * math.sqrt(2) / 2
    inner_length = guide_length - 2 * guide_end_border
    if skip_back_end_border:
        inner_length += guide_end_border

    carriage = create_box(carriage_width, carriage_length, thickness)

    carriage_rails = PartCollector()
    for left_right_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        carriage_guide_rail = create_box(
            guide_rail_side,
            carriage_length,
            guide_rail_side,
        )
        carriage_guide_rail = rotate(45, axis=(0, 1, 0))(carriage_guide_rail)
        carriage_guide_rail = align(
            carriage_guide_rail,
            carriage,
            Alignment.CENTER,
        )
        carriage_guide_rail = align(
            carriage_guide_rail,
            carriage,
            left_right_alignment,
        )
        carriage_guide_rail = translate(
            left_right_alignment.sign * thickness / 2,
            0,
            0,
        )(carriage_guide_rail)
        carriage_rails = carriage_rails.fuse(carriage_guide_rail)

    guide_frame = create_box(guide_width, guide_length, thickness)
    guide_frame = align(guide_frame, carriage, Alignment.CENTER)

    guide_raw_cutter = create_box(
        carriage_width + 2 * guide_clearance,
        inner_length,
        500,
    )
    guide_raw_cutter = align(guide_raw_cutter, guide_frame, Alignment.CENTER)
    if skip_back_end_border:
        guide_raw_cutter = align(guide_raw_cutter, guide_frame, Alignment.BACK)

    guide_frame = guide_frame.cut(guide_raw_cutter)

    guide_cutters = PartCollector()
    for left_right_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        guide_cut = create_box(guide_rail_side, inner_length, guide_rail_side)
        guide_cut = rotate(45, axis=(0, 1, 0))(guide_cut)
        guide_cut = align(guide_cut, carriage, Alignment.CENTER)
        guide_cut = align(guide_cut, carriage, left_right_alignment)
        guide_cut = translate(
            left_right_alignment.sign * (guide_clearance + thickness / 2),
            0,
            0,
        )(guide_cut)
        if skip_back_end_border:
            guide_cut = align(guide_cut, guide_frame, Alignment.BACK)
        guide_cutters = guide_cutters.fuse(guide_cut)

    guide_frame = guide_frame.cut(guide_cutters)
    carriage = carriage.fuse(carriage_rails)

    retval = LeaderFollowersCuttersPart(guide_frame)
    retval.add_named_follower(carriage, "carriage")
    return retval


def _create_board_holder(
    *,
    board,
    big_thing,
    board_pcb=None,
    board_pcb_follower_name="board",
    board_cutting_part=None,
    base_plate_border=7.0,
    base_plate_border_y_ratio=1.0 / 3.0,
    base_plate_x_size_override=None,
    base_plate_y_size_override=None,
    base_plate_thickness=3.1,
    board_z_offset=0.005,
    holder_thickness=6.0,
    holder_width=7,
    holder_fb_clearance=2.0,
    holder_inset=1.0,
    holder_z_offset=1.5,
    holder_guide_width=10.0,
    holder_carriage_width=5.0,
    holder_guide_thickness=None,
    holder_guide_clearance=0.35,
    holder_guide_end_border=3.0,
    holder_travel_length=3.0,
    holder_carriage_length_factor=3.0,
    holder_guide_length_factor=3.1,
    holder_board_holder_clearance=0.6,
    leaf_spring_thickness=2.0,
    leaf_spring_width=2.5,
    leaf_spring_groove_clearance=0.1,
    leaf_spring_angle=45,
    leaf_spring_preload_deflection=12,
    leaf_spring_mid_deflection=4,
    leaf_spring_holder_tower_outset=10,
    leaf_spring_holder_clearance=0.5,
    leaf_spring_holder_spring_overstand=4,
    leaf_spring_holder_tower_x_size=None,
    leaf_spring_holder_tower_y_size=None,
    leaf_spring_holder_tower_extra_height=6,
):
    if leaf_spring_holder_tower_x_size is None:
        leaf_spring_holder_tower_x_size = 4 * leaf_spring_width
    if leaf_spring_holder_tower_y_size is None:
        leaf_spring_holder_tower_y_size = 4 * leaf_spring_width
    if board_pcb is None:
        board_pcb = board.get_follower_part_by_name(board_pcb_follower_name)
    if holder_guide_thickness is None:
        holder_guide_thickness = base_plate_thickness

    def cut_with_board(part):
        if board_cutting_part is not None:
            return part.cut(board_cutting_part)
        if hasattr(board, "use_as_cutter_on"):
            return board.use_as_cutter_on(part)
        return part.cut(board)

    board_size = get_bounding_box_size(board)
    leaf_spring_length = board_size[1] + 2 * leaf_spring_holder_tower_outset

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

    holders = PartCollector()
    right_holder = None

    for left_right_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        holder_length = board_size[1] - 2 * holder_fb_clearance
        holder = create_box(holder_width, holder_length, holder_thickness)

        holder_cutter_side_size = holder_thickness / math.sqrt(2)
        holder_cutter = create_box(
            holder_cutter_side_size,
            big_thing,
            holder_cutter_side_size,
        )
        holder_cutter = rotate(45, axis=(0, 1, 0))(holder_cutter)
        holder_cutter = align(holder_cutter, holder, Alignment.CENTER)
        holder_cutter = align(holder_cutter, holder, left_right_alignment.opposite)
        holder_cutter = translate(
            -left_right_alignment.sign * holder_thickness / 2,
            0,
            0,
        )(holder_cutter)
        holder = holder.cut(holder_cutter)

        holder = align(holder, board, Alignment.CENTER)
        holder = align(holder, board_pcb, Alignment.TOP)
        holder = align(holder, board, left_right_alignment.stack_alignment)

        inset_x_offset = (
            -left_right_alignment.sign * holder_inset
            if left_right_alignment == Alignment.RIGHT
            else 0
        )
        holder = translate(inset_x_offset, 0, holder_z_offset)(holder)

        if left_right_alignment == Alignment.LEFT:
            holder_bottom_cutter = create_box(
                holder_thickness / 2,
                holder_length,
                holder_thickness / 2,
            )
            holder_bottom_cutter = align(
                holder_bottom_cutter,
                holder,
                Alignment.CENTER,
            )
            holder_bottom_cutter = align(
                holder_bottom_cutter,
                holder,
                Alignment.BOTTOM,
            )
            holder_bottom_cutter = align(
                holder_bottom_cutter,
                holder,
                Alignment.RIGHT,
            )
            holder = holder.cut(holder_bottom_cutter)

        if left_right_alignment == Alignment.RIGHT:
            holder_bbox = get_bounding_box(holder)
            leaf_spring_groove_cutter = create_box(
                leaf_spring_width + 2 * leaf_spring_groove_clearance,
                holder_length,
                4 * leaf_spring_thickness + 2 * leaf_spring_groove_clearance,
            )
            leaf_spring_groove_cutter = align(
                leaf_spring_groove_cutter,
                None,
                Alignment.CENTER,
                axes=[0, 1],
            )
            leaf_spring_groove_cutter = align(
                leaf_spring_groove_cutter,
                holder,
                Alignment.CENTER,
                axes=[1],
            )
            leaf_spring_groove_cutter = rotate(
                leaf_spring_angle,
                axis=(0, 1, 0),
            )(leaf_spring_groove_cutter)
            leaf_spring_groove_cutter = translate(
                holder_bbox[1][0],
                0,
                holder_bbox[1][2],
            )(leaf_spring_groove_cutter)

            cut_depth = leaf_spring_thickness + leaf_spring_groove_clearance
            x_offset = -math.cos(math.radians(leaf_spring_angle)) * cut_depth
            z_offset = -math.sin(math.radians(leaf_spring_angle)) * cut_depth
            leaf_spring_groove_cutter = translate(x_offset, 0, z_offset)(
                leaf_spring_groove_cutter
            )
            holder = holder.cut(leaf_spring_groove_cutter)
            right_holder = holder

        holders = holders.fuse(holder)

    if right_holder is None:
        raise ValueError("Right holder could not be generated.")

    holders = align(holders, base_plate, Alignment.BOTTOM)

    holder_carriage_length = holder_travel_length * holder_carriage_length_factor
    holder_guide_length = (
        holder_travel_length * holder_guide_length_factor + holder_guide_end_border
    )

    right_holder_size = get_bounding_box_size(right_holder)
    right_holder_cutter = create_box(
        right_holder_size[0] + holder_travel_length + holder_board_holder_clearance,
        right_holder_size[1] + 2 * holder_fb_clearance,
        big_thing,
    )
    right_holder_cutter = align(right_holder_cutter, right_holder, Alignment.CENTER)
    right_holder_cutter = align(right_holder_cutter, right_holder, Alignment.LEFT)
    right_holder_cutter = translate(-holder_board_holder_clearance, 0, 0)(
        right_holder_cutter
    )

    leaf_spring = _create_leaf_spring(
        spring_length=leaf_spring_length,
        spring_thickness=leaf_spring_thickness,
        spring_height=leaf_spring_width,
        spring_mid_deflection=leaf_spring_mid_deflection,
    )
    leaf_spring_cutter = _create_leaf_spring(
        spring_length=leaf_spring_length + 2 * leaf_spring_holder_clearance,
        spring_thickness=leaf_spring_thickness + 2 * leaf_spring_holder_clearance,
        spring_height=leaf_spring_width + 2 * leaf_spring_holder_clearance,
        spring_mid_deflection=leaf_spring_mid_deflection,
    )
    leaf_spring_preloaded = _create_leaf_spring(
        spring_length=leaf_spring_length,
        spring_thickness=leaf_spring_thickness,
        spring_height=leaf_spring_width,
        spring_mid_deflection=leaf_spring_mid_deflection
        + leaf_spring_preload_deflection,
    )
    leaf_spring_cutter = align(leaf_spring_cutter, leaf_spring, Alignment.CENTER)
    leaf_spring_preloaded = align(
        leaf_spring_preloaded,
        leaf_spring,
        Alignment.CENTER,
    )

    leaf_spring = LeaderFollowersCuttersPart(
        leader=leaf_spring,
        cutters=[leaf_spring_cutter],
    )
    leaf_spring.add_named_follower(leaf_spring_preloaded, "leaf_spring_preloaded")

    leaf_spring = rotate(-90, axis=(1, 0, 0))(leaf_spring)
    leaf_spring = rotate(90)(leaf_spring)
    leaf_spring = align(leaf_spring, None, Alignment.CENTER)

    leaf_spring_bbox = get_bounding_box(leaf_spring)
    leaf_spring = translate(0, 0, -leaf_spring_bbox[0][2])(leaf_spring)
    leaf_spring = rotate(leaf_spring_angle, axis=(0, 1, 0))(leaf_spring)
    leaf_spring = align(leaf_spring, right_holder, Alignment.CENTER, axes=[1])

    right_holder_bbox = get_bounding_box(right_holder)
    leaf_spring = translate(
        right_holder_bbox[1][0],
        0,
        right_holder_bbox[1][2],
    )(leaf_spring)

    shift_depth = leaf_spring_thickness
    x_offset = -math.cos(math.radians(leaf_spring_angle)) * shift_depth
    z_offset = -math.sin(math.radians(leaf_spring_angle)) * shift_depth
    leaf_spring = translate(x_offset, 0, z_offset)(leaf_spring)

    base_plate_bbox = get_bounding_box(base_plate)
    leaf_spring_bbox = get_bounding_box(leaf_spring)
    leaf_spring_holder_tower_height = (
        leaf_spring_bbox[1][2]
        - base_plate_bbox[1][2]
        + leaf_spring_holder_tower_extra_height
    )

    leaf_spring_holder_towers = PartCollector()
    for front_back_alignment in [Alignment.FRONT, Alignment.BACK]:
        leaf_spring_holder_tower = create_box(
            leaf_spring_holder_tower_x_size,
            leaf_spring_holder_tower_y_size,
            leaf_spring_holder_tower_height,
        )
        leaf_spring_holder_tower = align(
            leaf_spring_holder_tower,
            leaf_spring,
            Alignment.CENTER,
        )
        leaf_spring_holder_tower = align(
            leaf_spring_holder_tower,
            base_plate,
            Alignment.BOTTOM,
        )
        leaf_spring_holder_tower = align(
            leaf_spring_holder_tower,
            leaf_spring,
            front_back_alignment,
        )
        leaf_spring_holder_tower = align(
            leaf_spring_holder_tower,
            leaf_spring,
            Alignment.RIGHT,
        )
        leaf_spring_holder_tower = translate(
            leaf_spring_holder_tower_x_size / 4,
            -front_back_alignment.sign * leaf_spring_holder_spring_overstand,
            0,
        )(leaf_spring_holder_tower)
        leaf_spring_holder_tower = leaf_spring.use_as_cutter_on(
            leaf_spring_holder_tower
        )
        leaf_spring_holder_towers = leaf_spring_holder_towers.fuse(
            leaf_spring_holder_tower
        )

    linear_guides = PartCollector()
    carriages = PartCollector()
    linear_guide_cutters = PartCollector()
    for front_back_alignment in [Alignment.FRONT, Alignment.BACK]:
        linear_guide = _create_linear_guide(
            guide_length=holder_guide_length,
            guide_width=holder_guide_width,
            carriage_length=holder_carriage_length,
            carriage_width=holder_carriage_width,
            thickness=holder_guide_thickness,
            guide_end_border=holder_guide_end_border,
            guide_clearance=holder_guide_clearance,
            skip_back_end_border=True,
        )
        linear_guide = rotate(90)(linear_guide)
        linear_guide = align(linear_guide, holders, Alignment.CENTER)
        linear_guide = align(linear_guide, holders, Alignment.BOTTOM)
        linear_guide = align(
            linear_guide,
            holders,
            Alignment.STACK_RIGHT,
            stack_gap=holder_travel_length,
        )
        linear_guide = align(linear_guide, holders, front_back_alignment)

        linear_guides = linear_guides.fuse(linear_guide.leader)

        linear_guide_size = get_bounding_box_size(linear_guide)
        linear_guide_cutter = create_box(
            linear_guide_size[0] + 2 * holder_inset,
            linear_guide_size[1],
            big_thing,
        )
        linear_guide_cutter = align(
            linear_guide_cutter,
            linear_guide,
            Alignment.CENTER,
        )
        linear_guide_cutter = align(
            linear_guide_cutter,
            linear_guide,
            Alignment.RIGHT,
        )
        linear_guide_cutters = linear_guide_cutters.fuse(linear_guide_cutter)

        carriage = linear_guide.get_follower_part_by_name("carriage")
        carriage = align(carriage, holders, Alignment.STACK_RIGHT)
        carriages = carriages.fuse(carriage)

    holders = holders.fuse(carriages)

    relevant_parts = holders.fuse(linear_guides).fuse(linear_guide_cutters)
    relevant_parts_bbox = get_bounding_box(relevant_parts)

    right_extension_size = relevant_parts_bbox[1][0] - base_plate_bbox[1][0]
    right_extension = create_box(
        right_extension_size,
        base_plate_size[1],
        base_plate_size[2],
    )
    right_extension = align(right_extension, base_plate, Alignment.CENTER)
    right_extension = align(right_extension, base_plate, Alignment.STACK_RIGHT)

    base_plate = base_plate.fuse(leaf_spring_holder_towers)
    base_plate = base_plate.fuse(right_extension)
    base_plate = base_plate.cut(right_holder_cutter)
    base_plate = base_plate.cut(linear_guide_cutters)
    base_plate = cut_with_board(base_plate)

    holder_assembly = holders.fuse(base_plate).fuse(linear_guides)
    holder_assembly = LeaderFollowersCuttersPart(holder_assembly)
    holder_assembly.add_named_follower(leaf_spring.leader, "leaf_spring")
    holder_assembly.add_named_follower(
        leaf_spring.get_follower_part_by_name("leaf_spring_preloaded"),
        "leaf_spring_preloaded",
    )

    return holder_assembly


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


def create_board_holder_assembly(
    *,
    pico_w_board_assembly,
    tmc_board_assembly,
    additional_pins_assembly,
    board_holder_base_plate_border,
    board_holder_base_plate_y_size,
    board_holder_base_plate_thickness,
    board_holder_board_z_offset,
    board_holder_leaf_spring_angle,
    board_holder_leaf_spring_thickness,
    board_holder_leaf_spring_holder_tower_x_size,
    board_holder_leaf_spring_holder_tower_y_size,
    board_holder_mount_screw_size,
    board_holder_mount_screw_hole_inset,
    BIG_THING,
):
    """Create the x-axis MCU board holder assembly."""

    pico_board = pico_w_board_assembly.copy()
    pico_holders = _create_board_holder(
        board=pico_board,
        big_thing=BIG_THING,
        base_plate_border=board_holder_base_plate_border,
        base_plate_thickness=board_holder_base_plate_thickness,
        base_plate_y_size_override=board_holder_base_plate_y_size,
        board_z_offset=board_holder_board_z_offset,
        leaf_spring_angle=board_holder_leaf_spring_angle,
        leaf_spring_holder_tower_x_size=board_holder_leaf_spring_holder_tower_x_size,
        leaf_spring_holder_tower_y_size=board_holder_leaf_spring_holder_tower_y_size,
        leaf_spring_thickness=board_holder_leaf_spring_thickness,
    )
    all_holders = pico_holders.prefixed_copy("pico")

    tmc_board_front = tmc_board_assembly.copy()
    tmc_board_front = align(tmc_board_front, pico_board, Alignment.FRONT)

    tmc_board_back = tmc_board_assembly.copy()
    tmc_board_back = align(tmc_board_back, pico_board, Alignment.BACK)
    tmc_board_back = tmc_board_back.prefixed_copy("tmc_2")

    tmc_boards = tmc_board_front.fuse(tmc_board_back)
    tmc_holders = _create_board_holder(
        board=tmc_boards,
        big_thing=BIG_THING,
        base_plate_border=board_holder_base_plate_border,
        base_plate_thickness=board_holder_base_plate_thickness,
        base_plate_y_size_override=board_holder_base_plate_y_size,
        board_z_offset=board_holder_board_z_offset,
        leaf_spring_angle=board_holder_leaf_spring_angle,
        leaf_spring_holder_tower_x_size=board_holder_leaf_spring_holder_tower_x_size,
        leaf_spring_holder_tower_y_size=board_holder_leaf_spring_holder_tower_y_size,
        leaf_spring_thickness=board_holder_leaf_spring_thickness,
    )

    pico_holders_bbox = get_bounding_box(pico_holders)
    tmc_holders_bbox = get_bounding_box(tmc_holders)
    tmc_x_offset = pico_holders_bbox[1][0] - tmc_holders_bbox[0][0]

    tmc_translation = translate(tmc_x_offset, 0, 0)
    tmc_board_front = tmc_translation(tmc_board_front)
    tmc_board_back = tmc_translation(tmc_board_back)
    tmc_holders = tmc_translation(tmc_holders).prefixed_copy("tmc")

    all_holders = all_holders.fuse(tmc_holders)

    additional_pins = additional_pins_assembly.copy()
    additional_pins = align(additional_pins, all_holders, Alignment.CENTER, axes=[1])
    additional_pins = align(additional_pins, all_holders, Alignment.STACK_RIGHT)
    all_holders = all_holders.fuse(additional_pins.leader)

    all_holders = _cut_mount_screw_holes(
        holder=all_holders,
        mount_screw_size=board_holder_mount_screw_size,
        mount_screw_hole_inset=board_holder_mount_screw_hole_inset,
        big_thing=BIG_THING,
    )

    all_holders = all_holders.merge_except_leader(
        pico_board.prefixed_copy("pico_board")
    )
    all_holders = all_holders.merge_except_leader(
        tmc_board_front.prefixed_copy("tmc_board")
    )
    all_holders = all_holders.merge_except_leader(
        tmc_board_back.prefixed_copy("tmc_board_2")
    )
    all_holders = all_holders.merge_except_leader(
        additional_pins.prefixed_copy("additional_pins")
    )

    return all_holders
