"""Y-axis power-drive housing assembly."""

from shellforgepy.simple import *

LID_RIM_CLEARANCE = 0.3
LID_SCREW_SIZE = "M3"
LID_SCREW_ENGAGEMENT = 5.0
THREAD_INSET_EXTRA_RADIUS = 2.0
CORNER_FILLET_RADIUS = 3.0
CUTTER_OVERSIZE = 2.0


def create_y_axis_power_drive_housing_assembly(
    *,
    y_axis_driver_board_holder_joined,
    bigtreetech_stepper_driver,
    y_axis_power_drive_housing_wall_thickness,
    y_axis_power_drive_housing_lid_thickness,
    y_axis_power_drive_housing_board_wall_clearance,
    y_axis_power_drive_housing_z_clearance_top,
    y_axis_power_drive_housing_z_clearance_bottom,
):
    """Create an open-ended housing around the positioned Y-axis electronics."""

    physical_parts = [
        y_axis_driver_board_holder_joined.leader,
        *y_axis_driver_board_holder_joined.followers,
        *y_axis_driver_board_holder_joined.non_production_parts,
        bigtreetech_stepper_driver.leader,
        *bigtreetech_stepper_driver.non_production_parts,
    ]
    physical_bounding_boxes = [get_bounding_box(part) for part in physical_parts]
    physical_min = tuple(
        min(bounding_box[0][axis] for bounding_box in physical_bounding_boxes)
        for axis in range(3)
    )
    physical_max = tuple(
        max(bounding_box[1][axis] for bounding_box in physical_bounding_boxes)
        for axis in range(3)
    )
    physical_size = tuple(physical_max[axis] - physical_min[axis] for axis in range(3))
    physical_envelope = create_box(
        *physical_size,
        origin=physical_min,
    )

    inner_space = materialize_bounding_box(
        physical_envelope,
        x_enlargement=2 * y_axis_power_drive_housing_board_wall_clearance,
        y_enlargement=2 * y_axis_power_drive_housing_board_wall_clearance,
        z_enlargement=(
            y_axis_power_drive_housing_z_clearance_top
            + y_axis_power_drive_housing_z_clearance_bottom
        ),
    )
    inner_space = translate(
        0,
        0,
        (
            y_axis_power_drive_housing_z_clearance_top
            - y_axis_power_drive_housing_z_clearance_bottom
        )
        / 2,
    )(inner_space)

    wall_thickness = y_axis_power_drive_housing_wall_thickness
    housing_reference = materialize_bounding_box(
        inner_space,
        x_enlargement=2 * wall_thickness,
        y_enlargement=2 * wall_thickness,
    )
    housing_reference_size = get_bounding_box_size(housing_reference)
    housing_box = create_filleted_box(
        *housing_reference_size,
        fillet_radius=min(CORNER_FILLET_RADIUS, wall_thickness),
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    housing_box = align(housing_box, housing_reference, Alignment.CENTER)

    inner_space_cutter = materialize_bounding_box(
        inner_space,
        z_enlargement=CUTTER_OVERSIZE,
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
    inner_space_size = get_bounding_box_size(inner_space)

    post_positions = [
        ("front_left", Alignment.LEFT, Alignment.FRONT),
        ("back_right", Alignment.RIGHT, Alignment.BACK),
    ]
    posts = PartCollector()
    post_items = []
    for post_name, left_right_alignment, front_back_alignment in post_positions:
        post = create_cylinder(post_radius, inner_space_size[2])
        post = align(post, inner_space, Alignment.CENTER, axes=[2])
        post = align(
            post,
            inner_space,
            left_right_alignment.stack_alignment,
            stack_gap=-post_radius,
        )
        post = align(
            post,
            inner_space,
            front_back_alignment.stack_alignment,
            stack_gap=-post_radius,
        )
        posts = posts.fuse(post)
        post_items.append((post_name, post))

    housing_box = housing_box.fuse(posts)

    thread_inset_pocket_items = []
    thread_inset_items = []
    for lid_name, z_alignment in [
        ("top", Alignment.TOP),
        ("bottom", Alignment.BOTTOM),
    ]:
        for index, (_post_name, post) in enumerate(post_items):
            thread_inset_assembly = create_thread_inset_assembly(
                size=LID_SCREW_SIZE,
                thickness=thread_inset_depth,
                extra_radius=THREAD_INSET_EXTRA_RADIUS,
                clearance_type="loose",
            )
            if z_alignment == Alignment.TOP:
                thread_inset_assembly = rotate(180, axis=(1, 0, 0))(
                    thread_inset_assembly
                )
            thread_inset_assembly = align(
                thread_inset_assembly,
                post,
                Alignment.CENTER,
                axes=[0, 1],
            )
            thread_inset_assembly = align(
                thread_inset_assembly,
                post,
                z_alignment,
            )

            thread_inset_boss = thread_inset_assembly.get_named_cutter(
                "assembly_cutter"
            )
            thread_inset_pocket = thread_inset_boss.cut(thread_inset_assembly.leader)
            housing_box = housing_box.cut(thread_inset_pocket)

            hardware_prefix = f"{lid_name}_lid_mount_screw_{index}"
            thread_inset_pocket_items.append(
                (f"{hardware_prefix}_thread_inset_pocket", thread_inset_pocket)
            )
            thread_inset_items.append(
                (
                    f"{hardware_prefix}_thread_inset",
                    thread_inset_assembly.get_named_non_production_part("thread_inset"),
                )
            )

    lid_clearance_hole_items = []
    lid_screw_items = []
    lids = {}
    screw_length = y_axis_power_drive_housing_lid_thickness + LID_SCREW_ENGAGEMENT
    body_size = get_bounding_box_size(housing_box)
    inner_space_size = get_bounding_box_size(inner_space)
    rim_depth = wall_thickness
    rim_outer_size = (
        inner_space_size[0] - 2 * LID_RIM_CLEARANCE,
        inner_space_size[1] - 2 * LID_RIM_CLEARANCE,
    )
    rim_inner_size = (
        rim_outer_size[0] - 2 * wall_thickness,
        rim_outer_size[1] - 2 * wall_thickness,
    )

    for lid_name, z_alignment in [
        ("top", Alignment.TOP),
        ("bottom", Alignment.BOTTOM),
    ]:
        lid_plate = create_filleted_box(
            body_size[0],
            body_size[1],
            y_axis_power_drive_housing_lid_thickness,
            fillet_radius=min(CORNER_FILLET_RADIUS, wall_thickness),
            no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
        )
        lid_plate = align(lid_plate, housing_box, Alignment.CENTER, axes=[0, 1])
        lid_plate = align(
            lid_plate,
            housing_box,
            z_alignment.stack_alignment,
        )

        lid_rim = create_filleted_box(
            rim_outer_size[0],
            rim_outer_size[1],
            rim_depth,
            fillet_radius=min(CORNER_FILLET_RADIUS, wall_thickness),
            no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
        )
        lid_rim_inner_cutter = create_box(
            rim_inner_size[0],
            rim_inner_size[1],
            rim_depth + CUTTER_OVERSIZE,
        )
        lid_rim_inner_cutter = align(
            lid_rim_inner_cutter,
            lid_rim,
            Alignment.CENTER,
        )
        lid_rim = lid_rim.cut(lid_rim_inner_cutter)
        lid_rim = align(lid_rim, inner_space, Alignment.CENTER, axes=[0, 1])
        if z_alignment == Alignment.TOP:
            lid_rim = align(lid_rim, lid_plate, Alignment.STACK_BOTTOM)
        else:
            lid_rim = align(lid_rim, lid_plate, Alignment.STACK_TOP)

        for _post_name, post in post_items:
            post_clearance = create_cylinder(
                post_radius + LID_RIM_CLEARANCE,
                rim_depth + CUTTER_OVERSIZE,
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

        for index, (_post_name, post) in enumerate(post_items):
            clearance_hole = create_cylinder(
                lid_screw.clearance_hole_loose / 2,
                y_axis_power_drive_housing_lid_thickness + CUTTER_OVERSIZE,
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

            screw = create_cylinder_screw(LID_SCREW_SIZE, screw_length)
            if z_alignment == Alignment.BOTTOM:
                screw = rotate(180, axis=(1, 0, 0))(screw)
            screw = align(screw, post, Alignment.CENTER, axes=[0, 1])
            screw = align(
                screw,
                lid_plate,
                z_alignment.stack_alignment,
                stack_gap=-screw_length,
            )

            hardware_prefix = f"{lid_name}_lid_mount_screw_{index}"
            lid_clearance_hole_items.append(
                (f"{hardware_prefix}_clearance_hole", clearance_hole)
            )
            lid_screw_items.append((f"{hardware_prefix}_screw", screw))

        lids[lid_name] = lid

    housing = LeaderFollowersCuttersPart(leader=housing_box)
    housing.add_named_follower(
        lids["top"],
        "y_axis_power_drive_housing_top_lid",
    )
    housing.add_named_follower(
        lids["bottom"],
        "y_axis_power_drive_housing_bottom_lid",
    )
    housing.add_named_cutter(inner_space_cutter, "inner_space")
    for name, cutter in thread_inset_pocket_items:
        housing.add_named_cutter(cutter, name)
    for name, cutter in lid_clearance_hole_items:
        housing.add_named_cutter(cutter, name)
    for name, thread_inset in thread_inset_items:
        housing.add_named_non_production_part(thread_inset, name)
    for name, screw in lid_screw_items:
        housing.add_named_non_production_part(screw, name)

    housing.additional_data["physical_envelope_bbox"] = (
        physical_min,
        physical_max,
    )
    housing.additional_data["post_centers"] = {
        name: get_bounding_box_center(post) for name, post in post_items
    }
    housing.additional_data["post_radius"] = post_radius
    housing.additional_data["lid_screw_size"] = LID_SCREW_SIZE
    housing.additional_data["lid_screw_length"] = screw_length

    return housing
