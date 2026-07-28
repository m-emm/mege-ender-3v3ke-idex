"""Standalone low-voltage power switchbox assembly."""

from shellforgepy.simple import *

CORNER_FILLET_RADIUS = 3.0
CUTTER_OVERSIZE = 2.0
LID_RIM_CLEARANCE = 0.3
LID_SCREW_ENGAGEMENT = 5.0
LID_SCREW_SIZE = "M3"
POST_BASE_OVERLAP = 0.5
RAIL_BASE_OVERLAP = 0.4
TERMINAL_COUNT = 4
TERMINAL_END_MARGIN = 6.0
TERMINAL_NUT_CLEARANCE = 0.3
TERMINAL_PITCH = 19.0
TERMINAL_SCREW_SIZE = "M4"
THREAD_INSET_EXTRA_RADIUS = 2.0


def create_left_lv_switchbox_assembly(
    *,
    left_lv_switchbox_width,
    left_lv_switchbox_depth,
    left_lv_switchbox_total_height,
    left_lv_switchbox_wall_thickness,
    left_lv_switchbox_bottom_thickness,
    left_lv_switchbox_lid_thickness,
    left_lv_switchbox_terminal_rail_width,
    left_lv_switchbox_terminal_rail_height,
    left_lv_switchbox_cable_entry_width,
    left_lv_switchbox_cable_entry_height,
    left_lv_switchbox_mount_flange_width,
    left_lv_switchbox_mount_flange_length,
    left_lv_switchbox_mount_flange_thickness,
):
    """Create a fixed-bottom switchbox with a terminal rail and removable lid."""

    wall_thickness = left_lv_switchbox_wall_thickness
    body_height = left_lv_switchbox_total_height - left_lv_switchbox_lid_thickness
    body_reference = create_box(
        left_lv_switchbox_width,
        left_lv_switchbox_depth,
        body_height,
    )
    housing_box = create_filleted_box(
        left_lv_switchbox_width,
        left_lv_switchbox_depth,
        body_height,
        fillet_radius=min(CORNER_FILLET_RADIUS, wall_thickness),
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )

    bottom_reference = materialize_bounding_box(
        body_reference,
        z_size=left_lv_switchbox_bottom_thickness,
    )
    bottom_reference = align(
        bottom_reference,
        body_reference,
        Alignment.BOTTOM,
    )

    inner_space = create_box(
        left_lv_switchbox_width - 2 * wall_thickness,
        left_lv_switchbox_depth - 2 * wall_thickness,
        body_height - left_lv_switchbox_bottom_thickness,
    )
    inner_space = align(inner_space, body_reference, Alignment.CENTER, axes=[0, 1])
    inner_space = align(
        inner_space,
        bottom_reference,
        Alignment.STACK_TOP,
    )

    inner_space_cutter = create_box(
        get_bounding_box_size(inner_space)[0],
        get_bounding_box_size(inner_space)[1],
        get_bounding_box_size(inner_space)[2] + CUTTER_OVERSIZE,
    )
    inner_space_cutter = align(
        inner_space_cutter,
        inner_space,
        Alignment.CENTER,
        axes=[0, 1],
    )
    inner_space_cutter = align(
        inner_space_cutter,
        bottom_reference,
        Alignment.STACK_TOP,
    )
    housing_box = housing_box.cut(inner_space_cutter)

    lid_screw = MScrew.from_size(LID_SCREW_SIZE)
    thread_inset_depth = lid_screw.thread_inset_length
    post_reference = create_thread_inset_assembly(
        size=LID_SCREW_SIZE,
        thickness=thread_inset_depth,
        extra_radius=THREAD_INSET_EXTRA_RADIUS,
        clearance_type="loose",
    ).get_named_cutter("assembly_cutter")
    post_radius = get_bounding_box_size(post_reference)[0] / 2
    post_height = body_height - left_lv_switchbox_bottom_thickness + POST_BASE_OVERLAP

    post_items = []
    post_positions = [
        ("front_left", Alignment.LEFT, Alignment.FRONT, -1, -1),
        ("back_right", Alignment.RIGHT, Alignment.BACK, 1, 1),
    ]
    for post_name, x_alignment, y_alignment, x_direction, y_direction in post_positions:
        post = create_cylinder(post_radius, post_height)
        post = align(post, body_reference, Alignment.TOP)
        post = align(post, inner_space, x_alignment)
        post = align(post, inner_space, y_alignment)
        post = translate(
            x_direction * wall_thickness / 2,
            y_direction * wall_thickness / 2,
            0,
        )(post)
        housing_box = housing_box.fuse(post)
        post_items.append((post_name, post))

    thread_inset_pocket_items = []
    thread_inset_items = []
    for index, (_post_name, post) in enumerate(post_items):
        thread_inset_assembly = create_thread_inset_assembly(
            size=LID_SCREW_SIZE,
            thickness=thread_inset_depth,
            extra_radius=THREAD_INSET_EXTRA_RADIUS,
            clearance_type="loose",
        )
        thread_inset_assembly = rotate(180, axis=(1, 0, 0))(thread_inset_assembly)
        thread_inset_assembly = align(
            thread_inset_assembly,
            post,
            Alignment.CENTER,
            axes=[0, 1],
        )
        thread_inset_assembly = align(
            thread_inset_assembly,
            post,
            Alignment.TOP,
        )

        thread_inset_boss = thread_inset_assembly.get_named_cutter("assembly_cutter")
        thread_inset_pocket = thread_inset_boss.cut(thread_inset_assembly.leader)
        housing_box = housing_box.cut(thread_inset_pocket)
        hardware_prefix = f"lid_mount_screw_{index}"
        thread_inset_pocket_items.append(
            (f"{hardware_prefix}_thread_inset_pocket", thread_inset_pocket)
        )
        thread_inset_items.append(
            (
                f"{hardware_prefix}_thread_inset",
                thread_inset_assembly.get_named_non_production_part("thread_inset"),
            )
        )

    terminal_rail_length = (
        TERMINAL_COUNT - 1
    ) * TERMINAL_PITCH + 2 * TERMINAL_END_MARGIN
    terminal_rail = create_filleted_box(
        terminal_rail_length,
        left_lv_switchbox_terminal_rail_width,
        left_lv_switchbox_terminal_rail_height,
        fillet_radius=min(
            CORNER_FILLET_RADIUS,
            left_lv_switchbox_terminal_rail_width / 4,
            left_lv_switchbox_terminal_rail_height / 4,
        ),
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    terminal_rail = align(
        terminal_rail,
        inner_space,
        Alignment.CENTER,
        axes=[0, 1],
    )
    terminal_rail = align(
        terminal_rail,
        bottom_reference,
        Alignment.STACK_TOP,
        stack_gap=-RAIL_BASE_OVERLAP,
    )


    terminal_rail = align(
        terminal_rail,
        bottom_reference,
        Alignment.FRONT,        
    )
    

    terminal_square_nut_pocket_items = []
    terminal_square_nut_items = []
    for terminal_index in range(TERMINAL_COUNT):
        terminal_x_offset = (terminal_index - (TERMINAL_COUNT - 1) / 2) * TERMINAL_PITCH
        terminal_nut_pocket = create_hidden_nut_pocket_cutter(
            TERMINAL_SCREW_SIZE,
            bottom_cutter_length=left_lv_switchbox_terminal_rail_height,
            top_cutter_length=left_lv_switchbox_terminal_rail_height,
            slack=TERMINAL_NUT_CLEARANCE,
            square_nut=True,
        )
        terminal_nut_pocket = align(
            terminal_nut_pocket,
            terminal_rail,
            Alignment.CENTER,
        )
        terminal_nut_pocket = translate(terminal_x_offset, 0, 0)(terminal_nut_pocket)
        terminal_rail = terminal_nut_pocket.use_as_cutter_on(terminal_rail)

        terminal_square_nut = create_square_nut(TERMINAL_SCREW_SIZE)
        terminal_square_nut = align(
            terminal_square_nut,
            terminal_nut_pocket.leader,
            Alignment.CENTER,
        )
        terminal_square_nut_pocket_items.append(
            (
                f"terminal_{terminal_index}_square_nut_pocket",
                terminal_nut_pocket.cutters[0],
            )
        )
        terminal_square_nut_items.append(
            (
                f"terminal_{terminal_index}_square_nut",
                terminal_square_nut,
            )
        )

    housing_box = housing_box.fuse(terminal_rail)

    cable_entry_cutter = create_filleted_box(
        left_lv_switchbox_cable_entry_width,
        wall_thickness + CUTTER_OVERSIZE,
        left_lv_switchbox_cable_entry_height,
        fillet_radius=min(
            CORNER_FILLET_RADIUS,
            left_lv_switchbox_cable_entry_width / 2 - 0.1,
            left_lv_switchbox_cable_entry_height / 2 - 0.1,
        ),
        no_fillets_at=[Alignment.FRONT, Alignment.BACK],
    )
    cable_entry_cutter = align(
        cable_entry_cutter,
        body_reference,
        Alignment.CENTER,
        axes=[0, 2],
    )
    cable_entry_cutter = align(
        cable_entry_cutter,
        body_reference,
        Alignment.BACK,
    )
    cable_entry_cutter = translate(0, CUTTER_OVERSIZE / 2, 0)(cable_entry_cutter)
    housing_box = housing_box.cut(cable_entry_cutter)

    mount_flange_screw = MScrew.from_size("M5")
    mount_flanges = PartCollector()
    mount_flange_screw_holes = PartCollector()
    for side in [Alignment.LEFT, Alignment.RIGHT]:
        mount_flange = create_filleted_box(
            left_lv_switchbox_mount_flange_length,
            left_lv_switchbox_mount_flange_width,
            left_lv_switchbox_mount_flange_thickness,
            fillet_radius=min(
                CORNER_FILLET_RADIUS,
                left_lv_switchbox_mount_flange_length / 4,
                left_lv_switchbox_mount_flange_width / 4,
            ),
            no_fillets_at=[Alignment.BOTTOM, Alignment.TOP, side.opposite],
        )
        mount_flange = align(
            mount_flange,
            body_reference,
            Alignment.CENTER,
            axes=[1],
        )
        mount_flange = align(
            mount_flange,
            body_reference,
            side.stack_alignment,
        )
        mount_flange = align(
            mount_flange,
            body_reference,
            Alignment.BOTTOM,
        )

        mount_flange_screw_hole = create_cylinder(
            mount_flange_screw.clearance_hole_normal / 2,
            left_lv_switchbox_mount_flange_thickness + CUTTER_OVERSIZE,
        )
        mount_flange_screw_hole = align(
            mount_flange_screw_hole,
            mount_flange,
            Alignment.CENTER,
        )
        mount_flanges = mount_flanges.fuse(mount_flange)
        mount_flange_screw_holes = mount_flange_screw_holes.fuse(
            mount_flange_screw_hole
        )

    housing_box = housing_box.fuse(mount_flanges)
    housing_box = housing_box.cut(mount_flange_screw_holes)

    lid_plate = create_filleted_box(
        left_lv_switchbox_width,
        left_lv_switchbox_depth,
        left_lv_switchbox_lid_thickness,
        fillet_radius=min(CORNER_FILLET_RADIUS, wall_thickness),
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    lid_plate = align(lid_plate, body_reference, Alignment.CENTER, axes=[0, 1])
    lid_plate = align(
        lid_plate,
        body_reference,
        Alignment.STACK_TOP,
    )

    lid_rim_outer_size = (
        get_bounding_box_size(inner_space)[0] - 2 * LID_RIM_CLEARANCE,
        get_bounding_box_size(inner_space)[1] - 2 * LID_RIM_CLEARANCE,
    )
    lid_rim_inner_size = (
        lid_rim_outer_size[0] - 2 * wall_thickness,
        lid_rim_outer_size[1] - 2 * wall_thickness,
    )
    lid_rim = create_filleted_box(
        lid_rim_outer_size[0],
        lid_rim_outer_size[1],
        wall_thickness,
        fillet_radius=min(CORNER_FILLET_RADIUS, wall_thickness),
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    lid_rim_inner_cutter = create_box(
        lid_rim_inner_size[0],
        lid_rim_inner_size[1],
        wall_thickness + CUTTER_OVERSIZE,
    )
    lid_rim_inner_cutter = align(
        lid_rim_inner_cutter,
        lid_rim,
        Alignment.CENTER,
    )
    lid_rim = lid_rim.cut(lid_rim_inner_cutter)
    lid_rim = align(lid_rim, inner_space, Alignment.CENTER, axes=[0, 1])
    lid_rim = align(
        lid_rim,
        lid_plate,
        Alignment.STACK_BOTTOM,
    )

    for _post_name, post in post_items:
        post_clearance = create_cylinder(
            post_radius + LID_RIM_CLEARANCE,
            wall_thickness + CUTTER_OVERSIZE,
        )
        post_clearance = align(
            post_clearance,
            post,
            Alignment.CENTER,
            axes=[0, 1],
        )
        post_clearance = align(
            post_clearance,
            lid_rim,
            Alignment.CENTER,
            axes=[2],
        )
        lid_rim = lid_rim.cut(post_clearance)

    lid = lid_plate.fuse(lid_rim)
    lid_clearance_hole_items = []
    lid_screw_items = []
    lid_screw_length = left_lv_switchbox_lid_thickness + LID_SCREW_ENGAGEMENT
    for index, (_post_name, post) in enumerate(post_items):
        clearance_hole = create_cylinder(
            lid_screw.clearance_hole_loose / 2,
            left_lv_switchbox_lid_thickness + CUTTER_OVERSIZE,
        )
        clearance_hole = align(
            clearance_hole,
            post,
            Alignment.CENTER,
            axes=[0, 1],
        )
        clearance_hole = align(
            clearance_hole,
            lid_plate,
            Alignment.CENTER,
            axes=[2],
        )
        lid = lid.cut(clearance_hole)

        screw = create_cylinder_screw(LID_SCREW_SIZE, lid_screw_length)
        screw = align(screw, post, Alignment.CENTER, axes=[0, 1])
        screw = align(
            screw,
            lid_plate,
            Alignment.STACK_TOP,
            stack_gap=-lid_screw_length,
        )
        hardware_prefix = f"lid_mount_screw_{index}"
        lid_clearance_hole_items.append(
            (f"{hardware_prefix}_clearance_hole", clearance_hole)
        )
        lid_screw_items.append((f"{hardware_prefix}_screw", screw))

    housing = LeaderFollowersCuttersPart(leader=housing_box)
    housing.add_named_follower(lid, "left_lv_switchbox_lid")
    housing.add_named_cutter(inner_space_cutter, "inner_space")
    housing.add_named_cutter(cable_entry_cutter, "cable_entry")
    housing.add_named_cutter(
        mount_flange_screw_holes,
        "mount_flange_screw_holes",
    )
    for name, cutter in terminal_square_nut_pocket_items:
        housing.add_named_cutter(cutter, name)
    for name, cutter in thread_inset_pocket_items:
        housing.add_named_cutter(cutter, name)
    for name, cutter in lid_clearance_hole_items:
        housing.add_named_cutter(cutter, name)
    for name, terminal_square_nut in terminal_square_nut_items:
        housing.add_named_non_production_part(terminal_square_nut, name)
    for name, thread_inset in thread_inset_items:
        housing.add_named_non_production_part(thread_inset, name)
    for name, screw in lid_screw_items:
        housing.add_named_non_production_part(screw, name)

    return housing
