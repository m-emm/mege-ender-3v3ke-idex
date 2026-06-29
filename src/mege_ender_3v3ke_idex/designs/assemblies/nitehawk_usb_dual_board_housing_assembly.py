"""Dual Nitehawk USB daughterboard wall housing assembly."""

from shellforgepy.simple import *

BIG_THING = 500
LID_BOSS_WINDOW_KEEPOUT_MARGIN = 2.0


def create_nitehawk_usb_dual_board_housing_assembly(
    *,
    nitehawk_usb_board,
    nitehawk_usb_dual_housing_wall_thickness,
    nitehawk_usb_dual_housing_corner_fillet_radius,
    nitehawk_usb_dual_housing_board_gap,
    nitehawk_usb_dual_housing_board_side_margin,
    nitehawk_usb_dual_housing_board_bottom_margin,
    nitehawk_usb_dual_housing_board_top_margin,
    nitehawk_usb_dual_housing_board_standoff_height,
    nitehawk_usb_dual_housing_board_boss_diameter,
    nitehawk_usb_dual_housing_board_screw_size,
    nitehawk_usb_dual_housing_board_screw_length,
    nitehawk_usb_dual_housing_self_threading_core_radius_adjustment,
    nitehawk_usb_dual_housing_self_threading_lead_in,
    nitehawk_usb_dual_housing_component_clearance,
    nitehawk_usb_dual_housing_lid_thickness,
    nitehawk_usb_dual_housing_lid_body_clearance,
    nitehawk_usb_dual_housing_lid_outer_overhang,
    nitehawk_usb_dual_housing_lid_rim_depth,
    nitehawk_usb_dual_housing_lid_rim_thickness,
    nitehawk_usb_dual_housing_lid_rim_clearance,
    nitehawk_usb_dual_housing_lid_screw_size,
    nitehawk_usb_dual_housing_lid_screw_length,
    nitehawk_usb_dual_housing_lid_screw_inset,
    nitehawk_usb_dual_housing_lid_screw_boss_diameter,
    nitehawk_usb_dual_housing_cable_slit_x_size,
    nitehawk_usb_dual_housing_cable_slit_y_margin,
    nitehawk_usb_dual_housing_cable_slit_z_size,
    nitehawk_usb_dual_housing_cable_slit_floor_clearance,
    nitehawk_usb_dual_housing_cable_slit_fillet_radius,
    nitehawk_usb_dual_housing_rear_connector_slit_x_size,
    nitehawk_usb_dual_housing_rear_connector_slit_y_margin,
    nitehawk_usb_dual_housing_cable_tie_slot_x_size,
    nitehawk_usb_dual_housing_cable_tie_slot_y_size,
    nitehawk_usb_dual_housing_cable_tie_slot_pair_spacing,
    nitehawk_usb_dual_housing_cable_tie_slot_x_offset_from_back,
    nitehawk_usb_dual_housing_profile_mount_spine_width,
    nitehawk_usb_dual_housing_profile_mount_spine_thickness,
    nitehawk_usb_dual_housing_profile_mount_spine_height,
    nitehawk_usb_dual_housing_profile_mount_screw_size,
    nitehawk_usb_dual_housing_profile_mount_screw_length,
    nitehawk_usb_dual_housing_profile_mount_hole_spacing,
):
    """Create a compact lidded housing for two Nitehawk USB daughterboards."""

    board_1 = nitehawk_usb_board.prefixed_copy("board_1")
    board_1 = rotate(-90, axis=(0, 1, 0))(board_1)
    board_1 = rotate(-90, axis=(1, 0, 0))(board_1)

    raw_board_bboxes = [
        get_bounding_box(part) for _, part in board_1.get_named_follower_items()
    ]
    raw_board_bbox = (
        tuple(min(bbox[0][axis] for bbox in raw_board_bboxes) for axis in range(3)),
        tuple(max(bbox[1][axis] for bbox in raw_board_bboxes) for axis in range(3)),
    )
    raw_board_size = tuple(
        raw_board_bbox[1][axis] - raw_board_bbox[0][axis] for axis in range(3)
    )
    wall = nitehawk_usb_dual_housing_wall_thickness

    housing_width = (
        2 * raw_board_size[1]
        + nitehawk_usb_dual_housing_board_gap
        + 2 * wall
        + 2 * nitehawk_usb_dual_housing_board_side_margin
    )
    housing_height = (
        raw_board_size[2]
        + 2 * wall
        + nitehawk_usb_dual_housing_board_bottom_margin
        + nitehawk_usb_dual_housing_board_top_margin
    )
    housing_depth = (
        wall
        + nitehawk_usb_dual_housing_board_standoff_height
        + raw_board_size[0]
        + nitehawk_usb_dual_housing_component_clearance
        + nitehawk_usb_dual_housing_lid_rim_depth
        + nitehawk_usb_dual_housing_lid_body_clearance
    )

    housing_reference = create_box(housing_depth, housing_width, housing_height)
    housing_box = create_filleted_box(
        housing_depth,
        housing_width,
        housing_height,
        fillet_radius=nitehawk_usb_dual_housing_corner_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
    )
    inner_space_cutter = create_box(
        housing_depth - wall + 1,
        housing_width - 2 * wall,
        housing_height - 2 * wall,
        origin=(-1, wall, wall),
    )
    housing_box = housing_box.cut(inner_space_cutter)

    board_back_x = (
        housing_depth - wall - nitehawk_usb_dual_housing_board_standoff_height
    )
    board_bottom_z = wall + nitehawk_usb_dual_housing_board_bottom_margin
    board_1_y = wall + nitehawk_usb_dual_housing_board_side_margin
    board_1 = translate(
        board_back_x - raw_board_bbox[1][0],
        board_1_y - raw_board_bbox[0][1],
        board_bottom_z - raw_board_bbox[0][2],
    )(board_1)

    board_2 = nitehawk_usb_board.prefixed_copy("board_2")
    board_2 = rotate(-90, axis=(0, 1, 0))(board_2)
    board_2 = rotate(-90, axis=(1, 0, 0))(board_2)
    board_2_bboxes = [
        get_bounding_box(part) for _, part in board_2.get_named_follower_items()
    ]
    board_2_bbox = (
        tuple(min(bbox[0][axis] for bbox in board_2_bboxes) for axis in range(3)),
        tuple(max(bbox[1][axis] for bbox in board_2_bboxes) for axis in range(3)),
    )
    board_2_y = board_1_y + raw_board_size[1] + nitehawk_usb_dual_housing_board_gap
    board_2 = translate(
        board_back_x - board_2_bbox[1][0],
        board_2_y - board_2_bbox[0][1],
        board_bottom_z - board_2_bbox[0][2],
    )(board_2)

    board_bosses = PartCollector()
    board_pilot_holes = PartCollector()
    board_mount_screws = PartCollector()
    board_mount_holes = []
    board_mount_specs = [
        (board_1, "board_1", "mounting_hole_front_left"),
        (board_1, "board_1", "mounting_hole_front_right"),
        (board_1, "board_1", "mounting_hole_back"),
        (board_2, "board_2", "mounting_hole_front_left"),
        (board_2, "board_2", "mounting_hole_front_right"),
        (board_2, "board_2", "mounting_hole_back"),
    ]
    for board, board_name, hole_name in board_mount_specs:
        board_hole = board.get_cutter_part_by_name(f"{board_name}_{hole_name}")
        board_pcb = board.get_follower_part_by_name(f"{board_name}_board")
        board_pcb_bbox = get_bounding_box(board_pcb)
        hole_center = get_bounding_box_center(board_hole)
        boss = create_cylinder(
            nitehawk_usb_dual_housing_board_boss_diameter / 2,
            nitehawk_usb_dual_housing_board_standoff_height,
            origin=(
                board_back_x,
                hole_center[1],
                hole_center[2],
            ),
            direction=(1, 0, 0),
        )
        board_bosses = board_bosses.fuse(boss)

        pilot_hole_length = housing_depth - board_pcb_bbox[0][0] + 2
        pilot_hole = create_self_threading_hole_cutter(
            nitehawk_usb_dual_housing_board_screw_size,
            pilot_hole_length,
            core_radius_adjustment=(
                nitehawk_usb_dual_housing_self_threading_core_radius_adjustment
            ),
            lead_in=nitehawk_usb_dual_housing_self_threading_lead_in,
        )
        pilot_hole = rotate(-90, axis=(0, 1, 0))(pilot_hole)
        pilot_hole = align(pilot_hole, boss, Alignment.CENTER, axes=[1, 2])
        pilot_hole = align(pilot_hole, boss, Alignment.LEFT)
        board_pilot_holes = board_pilot_holes.fuse(pilot_hole)
        board_mount_holes.append((f"{board_name}_{hole_name}", pilot_hole))

        screw = create_cylinder_screw(
            nitehawk_usb_dual_housing_board_screw_size,
            nitehawk_usb_dual_housing_board_screw_length,
        )
        screw = rotate(-90, axis=(0, 1, 0))(screw)
        screw = translate(
            board_pcb_bbox[0][0] + nitehawk_usb_dual_housing_board_screw_length,
            hole_center[1],
            hole_center[2],
        )(screw)
        board_mount_screws = board_mount_screws.fuse(screw)

    housing_box = housing_box.fuse(board_bosses)
    housing_box = housing_box.cut(board_pilot_holes)

    lid_screw_bosses = PartCollector()
    lid_pilot_holes = PartCollector()
    lid_clearance_holes = PartCollector()
    lid_screws = PartCollector()
    lid_bosses = []
    lid_screw_positions = []
    lid_outer_x = (
        -nitehawk_usb_dual_housing_lid_body_clearance
        - nitehawk_usb_dual_housing_lid_thickness
    )
    lid_screw_record = MScrew.from_size(nitehawk_usb_dual_housing_lid_screw_size)
    for y_alignment in [Alignment.FRONT, Alignment.BACK]:
        for z_alignment in [Alignment.BOTTOM, Alignment.TOP]:
            y = (
                nitehawk_usb_dual_housing_lid_screw_inset
                if y_alignment == Alignment.FRONT
                else housing_width - nitehawk_usb_dual_housing_lid_screw_inset
            )
            z = (
                nitehawk_usb_dual_housing_lid_screw_inset
                if z_alignment == Alignment.BOTTOM
                else housing_height - nitehawk_usb_dual_housing_lid_screw_inset
            )
            lid_boss = create_cylinder(
                nitehawk_usb_dual_housing_lid_screw_boss_diameter / 2,
                housing_depth - wall,
                origin=(0, y, z),
                direction=(1, 0, 0),
            )
            lid_screw_bosses = lid_screw_bosses.fuse(lid_boss)
            lid_bosses.append(lid_boss)

            lid_pilot_hole = create_self_threading_hole_cutter(
                nitehawk_usb_dual_housing_lid_screw_size,
                housing_depth + 2,
                core_radius_adjustment=(
                    nitehawk_usb_dual_housing_self_threading_core_radius_adjustment
                ),
                lead_in=nitehawk_usb_dual_housing_self_threading_lead_in,
            )
            lid_pilot_hole = rotate(-90, axis=(0, 1, 0))(lid_pilot_hole)
            lid_pilot_hole = align(
                lid_pilot_hole, lid_boss, Alignment.CENTER, axes=[1, 2]
            )
            lid_pilot_hole = align(lid_pilot_hole, lid_boss, Alignment.LEFT)
            lid_pilot_holes = lid_pilot_holes.fuse(lid_pilot_hole)

            lid_clearance_hole = create_cylinder(
                lid_screw_record.clearance_hole_loose / 2,
                nitehawk_usb_dual_housing_lid_thickness + 1,
                origin=(
                    lid_outer_x - 0.5,
                    y,
                    z,
                ),
                direction=(1, 0, 0),
            )
            lid_clearance_holes = lid_clearance_holes.fuse(lid_clearance_hole)
            lid_screw_positions.append((y, z, lid_pilot_hole, lid_clearance_hole))

            lid_screw = create_cylinder_screw(
                nitehawk_usb_dual_housing_lid_screw_size,
                nitehawk_usb_dual_housing_lid_screw_length,
            )
            lid_screw = rotate(-90, axis=(0, 1, 0))(lid_screw)
            lid_screw = translate(
                lid_outer_x + nitehawk_usb_dual_housing_lid_screw_length,
                y,
                z,
            )(lid_screw)
            lid_screws = lid_screws.fuse(lid_screw)

    housing_box = housing_box.fuse(lid_screw_bosses)
    housing_box = housing_box.cut(lid_pilot_holes)

    lid_boss_window_keepouts = PartCollector()
    for lid_boss in lid_bosses:
        lid_boss_window_keepout = materialize_bounding_box(
            lid_boss,
            x_enlargement=2 * LID_BOSS_WINDOW_KEEPOUT_MARGIN,
            y_enlargement=2 * LID_BOSS_WINDOW_KEEPOUT_MARGIN,
            z_enlargement=2 * LID_BOSS_WINDOW_KEEPOUT_MARGIN,
        )
        lid_boss_window_keepouts = lid_boss_window_keepouts.fuse(
            lid_boss_window_keepout
        )

    cable_slit_length = housing_width - 2 * (
        wall + nitehawk_usb_dual_housing_cable_slit_y_margin
    )
    cable_slit_x = (
        nitehawk_usb_dual_housing_lid_rim_depth
        + nitehawk_usb_dual_housing_lid_body_clearance
    )
    cable_slit_x_size = min(
        nitehawk_usb_dual_housing_cable_slit_x_size,
        housing_depth
        - wall
        - nitehawk_usb_dual_housing_cable_slit_floor_clearance
        - cable_slit_x,
    )
    cable_slit = create_filleted_box(
        cable_slit_x_size,
        cable_slit_length,
        nitehawk_usb_dual_housing_cable_slit_z_size,
        fillet_radius=min(
            nitehawk_usb_dual_housing_cable_slit_fillet_radius,
            nitehawk_usb_dual_housing_cable_slit_z_size / 2 - 0.1,
        ),
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    cable_slit = translate(
        cable_slit_x,
        wall + nitehawk_usb_dual_housing_cable_slit_y_margin,
        -1,
    )(cable_slit)
    cable_slit = cable_slit.cut(lid_boss_window_keepouts)
    housing_box = housing_box.cut(cable_slit)

    rear_connector_slits = PartCollector()
    rear_connector_slit_items = []
    rear_connector_slit_z_size = wall + 2
    for board_index, board in [(1, board_1), (2, board_2)]:
        connector = board.get_follower_part_by_name(f"board_{board_index}_front_plug")
        connector_bbox = get_bounding_box(connector)
        connector_center = get_bounding_box_center(connector)
        connector_slit_y_size = (
            connector_bbox[1][1]
            - connector_bbox[0][1]
            + 2 * nitehawk_usb_dual_housing_rear_connector_slit_y_margin
        )
        connector_slit = create_filleted_box(
            min(
                nitehawk_usb_dual_housing_rear_connector_slit_x_size,
                cable_slit_x_size,
            ),
            connector_slit_y_size,
            rear_connector_slit_z_size,
            fillet_radius=min(
                nitehawk_usb_dual_housing_cable_slit_fillet_radius,
                rear_connector_slit_z_size / 2 - 0.1,
            ),
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
        )
        connector_slit = translate(
            cable_slit_x,
            connector_center[1] - connector_slit_y_size / 2,
            housing_height - wall - 1,
        )(connector_slit)
        connector_slit = connector_slit.cut(lid_boss_window_keepouts)
        rear_connector_slits = rear_connector_slits.fuse(connector_slit)
        rear_connector_slit_items.append(
            (f"rear_connector_cable_slit_board_{board_index}", connector_slit)
        )
    housing_box = housing_box.cut(rear_connector_slits)

    cable_tie_slots = PartCollector()
    cable_tie_slot_items = []
    cable_tie_x = housing_depth - wall
    cable_tie_z = wall + nitehawk_usb_dual_housing_cable_tie_slot_x_offset_from_back
    for board_index, board_y_min in enumerate([board_1_y, board_2_y], start=1):
        board_center_y = board_y_min + raw_board_size[1] / 2
        for side, y_offset in [
            ("front", -nitehawk_usb_dual_housing_cable_tie_slot_pair_spacing / 2),
            ("back", nitehawk_usb_dual_housing_cable_tie_slot_pair_spacing / 2),
        ]:
            cable_tie_slot = create_box(
                wall + 2,
                nitehawk_usb_dual_housing_cable_tie_slot_y_size,
                nitehawk_usb_dual_housing_cable_tie_slot_x_size,
                origin=(
                    cable_tie_x - 1,
                    board_center_y
                    + y_offset
                    - nitehawk_usb_dual_housing_cable_tie_slot_y_size / 2,
                    cable_tie_z - nitehawk_usb_dual_housing_cable_tie_slot_x_size / 2,
                ),
            )
            cable_tie_slots = cable_tie_slots.fuse(cable_tie_slot)
            cable_tie_slot_items.append(
                (f"cable_tie_slot_board_{board_index}_{side}", cable_tie_slot)
            )
    housing_box = housing_box.cut(cable_tie_slots)

    profile_mount_center_y = housing_width / 2
    profile_mount_center_z = housing_height / 2
    profile_mount_holes = PartCollector()
    profile_mount_hole_items = []
    profile_mount_screws = PartCollector()
    profile_screw_record = MScrew.from_size(
        nitehawk_usb_dual_housing_profile_mount_screw_size
    )
    for hole_name, z_offset in [
        ("bottom", -nitehawk_usb_dual_housing_profile_mount_hole_spacing / 2),
        ("top", nitehawk_usb_dual_housing_profile_mount_hole_spacing / 2),
    ]:
        hole = create_cylinder(
            profile_screw_record.clearance_hole_normal / 2,
            wall + 3,
            origin=(
                housing_depth - wall - 1,
                profile_mount_center_y,
                profile_mount_center_z + z_offset,
            ),
            direction=(1, 0, 0),
        )
        profile_mount_holes = profile_mount_holes.fuse(hole)
        profile_mount_hole_items.append((f"profile_mount_hole_{hole_name}", hole))

        profile_mount_screw = create_cylinder_screw(
            nitehawk_usb_dual_housing_profile_mount_screw_size,
            nitehawk_usb_dual_housing_profile_mount_screw_length,
        )
        profile_mount_screw = rotate(-90, axis=(0, 1, 0))(profile_mount_screw)
        profile_mount_screw = translate(
            housing_depth - wall + nitehawk_usb_dual_housing_profile_mount_screw_length,
            profile_mount_center_y,
            profile_mount_center_z + z_offset,
        )(profile_mount_screw)
        profile_mount_screws = profile_mount_screws.fuse(profile_mount_screw)

    housing_box = housing_box.cut(profile_mount_holes)

    lid_width = housing_width + 2 * nitehawk_usb_dual_housing_lid_outer_overhang
    lid_height = housing_height + 2 * nitehawk_usb_dual_housing_lid_outer_overhang

    lid_base = create_filleted_box(
        nitehawk_usb_dual_housing_lid_thickness,
        lid_width,
        lid_height,
        fillet_radius=nitehawk_usb_dual_housing_corner_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
    )
    lid_base = align(lid_base, housing_reference, Alignment.CENTER, axes=[1, 2])
    lid_base = align(
        lid_base,
        housing_reference,
        Alignment.STACK_LEFT,
        stack_gap=nitehawk_usb_dual_housing_lid_body_clearance,
    )

    lid_rim_outer_width = (
        housing_width - 2 * wall - 2 * nitehawk_usb_dual_housing_lid_rim_clearance
    )
    lid_rim_outer_height = (
        housing_height - 2 * wall - 2 * nitehawk_usb_dual_housing_lid_rim_clearance
    )
    lid_rim_inner_width = lid_rim_outer_width - 2 * (
        nitehawk_usb_dual_housing_lid_rim_thickness
    )
    lid_rim_inner_height = lid_rim_outer_height - 2 * (
        nitehawk_usb_dual_housing_lid_rim_thickness
    )
    lid_rim_fillet_radius = min(
        nitehawk_usb_dual_housing_corner_fillet_radius,
        nitehawk_usb_dual_housing_lid_rim_thickness / 2 - 0.1,
    )
    lid_rim = create_filleted_box(
        nitehawk_usb_dual_housing_lid_body_clearance
        + nitehawk_usb_dual_housing_lid_rim_depth,
        lid_rim_outer_width,
        lid_rim_outer_height,
        fillet_radius=lid_rim_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
    )
    lid_rim_inner_cutter = create_box(
        nitehawk_usb_dual_housing_lid_body_clearance
        + nitehawk_usb_dual_housing_lid_rim_depth
        + 2,
        lid_rim_inner_width,
        lid_rim_inner_height,
    )
    lid_rim_inner_cutter = align(lid_rim_inner_cutter, lid_rim, Alignment.CENTER)
    lid_rim = lid_rim.cut(lid_rim_inner_cutter)
    lid_rim = align(lid_rim, housing_reference, Alignment.CENTER, axes=[1, 2])
    lid_rim = align(lid_rim, lid_base, Alignment.STACK_RIGHT)
    for lid_boss in lid_bosses:
        lid_boss_relief_cutter = materialize_bounding_box(
            lid_boss,
            x_enlargement=nitehawk_usb_dual_housing_lid_body_clearance + 0.2,
            y_enlargement=nitehawk_usb_dual_housing_lid_screw_inset,
            z_enlargement=nitehawk_usb_dual_housing_lid_screw_inset,
        )
        lid_rim = lid_rim.cut(lid_boss_relief_cutter)

    lid_outer_lip_inner_width = (
        housing_width + 2 * nitehawk_usb_dual_housing_lid_rim_clearance
    )
    lid_outer_lip_inner_height = (
        housing_height + 2 * nitehawk_usb_dual_housing_lid_rim_clearance
    )
    lid_outer_lip_outer_width = lid_outer_lip_inner_width + 2 * (
        nitehawk_usb_dual_housing_lid_rim_thickness
    )
    lid_outer_lip_outer_height = lid_outer_lip_inner_height + 2 * (
        nitehawk_usb_dual_housing_lid_rim_thickness
    )
    lid_outer_lip = create_filleted_box(
        nitehawk_usb_dual_housing_lid_body_clearance
        + nitehawk_usb_dual_housing_lid_rim_depth,
        lid_outer_lip_outer_width,
        lid_outer_lip_outer_height,
        fillet_radius=lid_rim_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT],
    )
    lid_outer_lip_inner_cutter = create_box(
        nitehawk_usb_dual_housing_lid_body_clearance
        + nitehawk_usb_dual_housing_lid_rim_depth
        + 2,
        lid_outer_lip_inner_width,
        lid_outer_lip_inner_height,
    )
    lid_outer_lip_inner_cutter = align(
        lid_outer_lip_inner_cutter, lid_outer_lip, Alignment.CENTER
    )
    lid_outer_lip = lid_outer_lip.cut(lid_outer_lip_inner_cutter)
    lid_outer_lip = align(
        lid_outer_lip, housing_reference, Alignment.CENTER, axes=[1, 2]
    )
    lid_outer_lip = align(lid_outer_lip, lid_base, Alignment.STACK_RIGHT)
    lid = lid_base.fuse(lid_rim).fuse(lid_outer_lip)
    lid = lid.cut(lid_clearance_holes)

    profile_mount_reference = create_box(
        0.4,
        nitehawk_usb_dual_housing_profile_mount_spine_width,
        nitehawk_usb_dual_housing_profile_mount_spine_height,
    )
    profile_mount_reference = align(
        profile_mount_reference, housing_reference, Alignment.CENTER, axes=[1, 2]
    )
    profile_mount_reference = align(
        profile_mount_reference, housing_reference, Alignment.RIGHT
    )

    housing = LeaderFollowersCuttersPart(leader=housing_box)
    housing.add_named_follower(lid, "nitehawk_usb_dual_housing_lid")
    housing.add_named_cutter(inner_space_cutter, "inner_space")
    housing.add_named_cutter(board_pilot_holes, "board_mount_pilot_holes")
    housing.add_named_cutter(lid_pilot_holes, "lid_mount_pilot_holes")
    housing.add_named_cutter(lid_clearance_holes, "lid_mount_clearance_holes")
    housing.add_named_cutter(cable_slit, "cable_slit")
    housing.add_named_cutter(rear_connector_slits, "rear_connector_cable_slits")
    housing.add_named_cutter(cable_tie_slots, "cable_tie_slots")
    housing.add_named_cutter(profile_mount_holes, "profile_mount_holes")

    for name, cutter in board_mount_holes:
        housing.add_named_cutter(cutter, f"{name}_pilot_hole")
    for index, (_, _, pilot_hole, clearance_hole) in enumerate(
        lid_screw_positions, start=1
    ):
        housing.add_named_cutter(pilot_hole, f"lid_mount_pilot_hole_{index}")
        housing.add_named_cutter(clearance_hole, f"lid_mount_clearance_hole_{index}")
    for name, cutter in cable_tie_slot_items:
        housing.add_named_cutter(cutter, name)
    for name, cutter in rear_connector_slit_items:
        housing.add_named_cutter(cutter, name)
    for name, cutter in profile_mount_hole_items:
        housing.add_named_cutter(cutter, name)

    for board in [board_1, board_2]:
        for name, part in board.get_named_follower_items():
            housing.add_named_non_production_part(part, name)

    housing.add_named_non_production_part(
        housing_reference, "nitehawk_usb_dual_housing_body_reference"
    )
    housing.add_named_non_production_part(
        profile_mount_reference, "profile_mount_reference"
    )
    housing.add_named_non_production_part(board_mount_screws, "board_mount_screws")
    housing.add_named_non_production_part(lid_screws, "lid_mount_screws")
    housing.add_named_non_production_part(profile_mount_screws, "profile_mount_screws")

    return housing
