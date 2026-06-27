"""Rear-only gusset for the z-axis top bridge profile."""

from shellforgepy.simple import *


def create_z_axis_top_profile_gusset_assembly(
    *,
    side,
    BIG_THING,
    z_axis_top_bridge_profile_back_offset,
    z_axis_top_bridge_profile_drop,
    z_axis_top_profile_gusset_wall_thickness,
    z_axis_top_profile_gusset_rib_thickness,
    z_axis_top_profile_gusset_fillet_radius,
    z_axis_top_profile_gusset_profile_clearance,
    z_axis_top_profile_gusset_z_mount_width,
    z_axis_top_profile_gusset_z_mount_height,
    z_axis_top_profile_gusset_top_eye_length,
    z_axis_top_profile_gusset_top_eye_width,
    z_axis_top_profile_gusset_top_eye_thickness,
    z_axis_top_profile_gusset_screw_size,
    z_axis_top_profile_gusset_screw_length,
    z_axis_top_profile_gusset_z_screw_inset,
    z_axis_top_profile_gusset_top_screw_inset,
    z_axis_top_profile_gusset_screw_head_clearance,
):
    """Create one side of the rear z-axis top profile gusset."""

    normalized_side = str(side).strip().lower()
    if normalized_side == "left":
        side_alignment = Alignment.LEFT
    elif normalized_side == "right":
        side_alignment = Alignment.RIGHT
    else:
        raise ValueError(f"Unsupported z-axis top profile gusset side '{side}'")

    side_sign = side_alignment.sign
    inward_sign = -side_sign
    z_profile_size = 40
    top_profile_size = 20
    reference_thickness = 0.2
    wall_thickness = z_axis_top_profile_gusset_wall_thickness
    fillet_radius = z_axis_top_profile_gusset_fillet_radius
    profile_clearance = z_axis_top_profile_gusset_profile_clearance

    z_profile_contact_reference = create_box(
        z_profile_size,
        reference_thickness,
        z_axis_top_profile_gusset_z_mount_height,
        origin=(
            -z_profile_size / 2,
            -reference_thickness,
            -z_axis_top_profile_gusset_z_mount_height,
        ),
    )

    top_profile_x_min = min(
        side_sign * z_profile_size / 2,
        side_sign * z_profile_size / 2
        + inward_sign * z_axis_top_profile_gusset_top_eye_length,
    )
    top_profile_contact_reference = create_box(
        z_axis_top_profile_gusset_top_eye_length,
        top_profile_size,
        top_profile_size,
        origin=(
            top_profile_x_min,
            z_axis_top_bridge_profile_back_offset,
            -z_axis_top_bridge_profile_drop - top_profile_size,
        ),
    )

    rear_plate = create_filleted_box(
        z_axis_top_profile_gusset_z_mount_width,
        wall_thickness,
        z_axis_top_profile_gusset_z_mount_height,
        fillet_radius,
        no_fillets_at=[Alignment.FRONT, Alignment.TOP],
    )
    rear_plate = align(
        rear_plate,
        z_profile_contact_reference,
        Alignment.CENTER,
        axes=[0],
    )
    rear_plate = align(
        rear_plate,
        z_profile_contact_reference,
        Alignment.STACK_BACK,
    )
    rear_plate = align(rear_plate, z_profile_contact_reference, Alignment.TOP)

    top_eye = create_filleted_box(
        z_axis_top_profile_gusset_top_eye_length,
        z_axis_top_profile_gusset_top_eye_width,
        z_axis_top_profile_gusset_top_eye_thickness,
        fillet_radius,
        no_fillets_at=[Alignment.BOTTOM],
    )
    top_eye = align(
        top_eye,
        top_profile_contact_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )
    top_eye = align(
        top_eye,
        top_profile_contact_reference,
        Alignment.STACK_TOP,
        stack_gap=profile_clearance,
    )

    bridge_rear_wall = create_filleted_box(
        z_axis_top_profile_gusset_top_eye_length,
        wall_thickness,
        top_profile_size
        + z_axis_top_profile_gusset_top_eye_thickness
        + profile_clearance,
        fillet_radius,
        no_fillets_at=[Alignment.FRONT],
    )
    bridge_rear_wall = align(
        bridge_rear_wall,
        top_profile_contact_reference,
        Alignment.CENTER,
        axes=[0],
    )
    bridge_rear_wall = align(
        bridge_rear_wall,
        top_profile_contact_reference,
        Alignment.STACK_BACK,
        stack_gap=profile_clearance,
    )
    bridge_rear_wall = align(
        bridge_rear_wall,
        top_profile_contact_reference,
        Alignment.BOTTOM,
    )

    bridge_bottom_lip = create_filleted_box(
        z_axis_top_profile_gusset_top_eye_length,
        z_axis_top_profile_gusset_top_eye_width,
        wall_thickness,
        fillet_radius,
        no_fillets_at=[Alignment.TOP],
    )
    bridge_bottom_lip = align(
        bridge_bottom_lip,
        top_profile_contact_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )
    bridge_bottom_lip = align(
        bridge_bottom_lip,
        top_profile_contact_reference,
        Alignment.STACK_BOTTOM,
        stack_gap=profile_clearance,
    )

    rib_horizontal_span = max(
        wall_thickness * 4,
        z_axis_top_profile_gusset_top_eye_length
        - z_profile_size / 2
        - z_axis_top_profile_gusset_z_mount_width / 2
        + wall_thickness,
    )
    rib_vertical_rise = min(
        z_axis_top_profile_gusset_z_mount_height
        - z_axis_top_profile_gusset_z_screw_inset
        - wall_thickness,
        z_axis_top_profile_gusset_z_mount_height * 0.7,
    )
    rib = create_right_triangle(
        rib_horizontal_span,
        rib_vertical_rise,
        z_axis_top_profile_gusset_rib_thickness,
        extrusion_direction=(0, 1, 0),
        b_normal=(0, 0, -1),
        a_normal=(side_alignment.sign, 0, 0),
    )

    rib = align(rib, rear_plate, Alignment.CENTER)
    rib = align(rib, rear_plate, Alignment.FRONT)
    rib = align(rib, rear_plate, Alignment.BOTTOM)
    rib = align(rib, rear_plate, side_alignment.opposite.stack_alignment)

    gusset = rear_plate.fuse(top_eye)
    gusset = gusset.fuse(bridge_rear_wall)
    gusset = gusset.fuse(bridge_bottom_lip)
    gusset = gusset.fuse(rib)

    screw_spec = MScrew.from_size(z_axis_top_profile_gusset_screw_size)
    screw_hole_radius = screw_spec.clearance_hole_loose / 2
    screw_visuals = []

    for screw_index, screw_z in enumerate(
        [
            -z_axis_top_profile_gusset_z_screw_inset,
            -z_axis_top_profile_gusset_z_mount_height
            + z_axis_top_profile_gusset_z_screw_inset,
        ]
    ):
        screw_x = 0
        screw_axis_reference = create_cylinder(
            screw_hole_radius,
            wall_thickness,
            direction=(0, 1, 0),
        )
        screw_axis_reference = align(
            screw_axis_reference,
            rear_plate,
            Alignment.CENTER,
            axes=[1],
        )
        screw_axis_reference = translate(screw_x, 0, screw_z)(screw_axis_reference)

        screw_cutter = create_cylinder(
            screw_hole_radius,
            BIG_THING,
            direction=(0, 1, 0),
        )
        screw_cutter = align(screw_cutter, screw_axis_reference, Alignment.CENTER)
        gusset = gusset.cut(screw_cutter)

        screw_visual = create_cylinder_screw(
            z_axis_top_profile_gusset_screw_size,
            z_axis_top_profile_gusset_screw_length,
        )
        screw_visual = rotate(-90, axis=(1, 0, 0))(screw_visual)
        screw_visual = align(screw_visual, screw_axis_reference, Alignment.CENTER)
        screw_visual = align(screw_visual, rear_plate, Alignment.BACK)
        screw_visual = translate(0, screw_spec.cylinder_head_height, 0)(screw_visual)
        screw_visuals.append((f"z_mount_screw_{screw_index}", screw_visual))

    top_screw_y = z_axis_top_bridge_profile_back_offset + top_profile_size / 2
    top_screw_side_x = side_sign * z_profile_size / 2
    for screw_index, screw_x in enumerate(
        [
            top_screw_side_x + inward_sign * z_axis_top_profile_gusset_top_screw_inset,
            top_screw_side_x
            + inward_sign
            * (
                z_axis_top_profile_gusset_top_eye_length
                - z_axis_top_profile_gusset_top_screw_inset
            ),
        ]
    ):
        screw_axis_reference = create_cylinder(
            screw_hole_radius,
            z_axis_top_profile_gusset_top_eye_thickness,
        )
        screw_axis_reference = align(
            screw_axis_reference,
            top_eye,
            Alignment.CENTER,
            axes=[2],
        )
        screw_axis_reference = translate(screw_x, top_screw_y, 0)(screw_axis_reference)

        screw_cutter = create_cylinder(screw_hole_radius, BIG_THING)
        screw_cutter = align(screw_cutter, screw_axis_reference, Alignment.CENTER)
        gusset = gusset.cut(screw_cutter)

        screw_visual = create_cylinder_screw(
            z_axis_top_profile_gusset_screw_size,
            z_axis_top_profile_gusset_screw_length,
        )
        screw_visual = align(screw_visual, screw_axis_reference, Alignment.CENTER)
        screw_visual = align(screw_visual, top_eye, Alignment.TOP)
        screw_visual = translate(0, 0, screw_spec.cylinder_head_height)(screw_visual)
        screw_visuals.append((f"top_profile_screw_{screw_index}", screw_visual))

    retval = LeaderFollowersCuttersPart(leader=gusset)
    retval.add_named_non_production_part(
        z_profile_contact_reference,
        "z_profile_contact_reference",
    )
    retval.add_named_non_production_part(
        top_profile_contact_reference,
        "top_profile_contact_reference",
    )
    for name, screw_visual in screw_visuals:
        retval.add_named_non_production_part(screw_visual, name)

    return retval
