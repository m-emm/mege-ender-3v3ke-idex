"""Rear-only bracket for the z-axis top bridge profile."""

from mege_ender_3v3ke_idex.designs.hollow_profiles import create_hollow_profile_ring
from shellforgepy.simple import *


def _side_alignment_from_name(side):
    normalized_side = str(side).strip().lower()
    if normalized_side == "left":
        return Alignment.LEFT
    if normalized_side == "right":
        return Alignment.RIGHT
    raise ValueError(f"Unsupported z-axis top profile gusset side '{side}'")


def create_z_axis_top_profile_gusset_assembly(
    *,
    side,
    BIG_THING,
    z_axis_top_bridge_profile_back_offset,
    z_axis_top_profile_gusset_wall_thickness,
    z_axis_top_profile_gusset_fillet_radius,
    z_axis_top_profile_gusset_profile_clearance,
    z_axis_top_profile_gusset_z_mount_width,
    z_axis_top_profile_gusset_z_mount_height,
    z_axis_top_profile_gusset_top_eye_length,
    z_axis_top_profile_gusset_top_eye_width,
    z_axis_top_profile_gusset_top_eye_thickness,
    z_axis_top_profile_gusset_profile_outer_diameter,
    z_axis_top_profile_gusset_profile_width,
    z_axis_top_profile_gusset_profile_wall,
    z_axis_top_profile_gusset_profile_height,
    z_axis_top_profile_gusset_screw_size,
    z_axis_top_profile_gusset_screw_length,
    z_axis_top_profile_gusset_z_screw_inset,
    z_axis_top_profile_gusset_top_screw_inset,
    z_axis_top_profile_gusset_screw_head_clearance,
):
    """Create one side of the rear z-axis top profile bracket."""

    side_alignment = _side_alignment_from_name(side)
    z_profile_size = 40
    top_profile_size = 20
    reference_thickness = 0.2

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

    z_mount_plate = create_box(
        z_axis_top_profile_gusset_z_mount_width,
        z_axis_top_profile_gusset_wall_thickness,
        z_axis_top_profile_gusset_z_mount_height,
    )
    z_mount_plate = align(
        z_mount_plate,
        z_profile_contact_reference,
        Alignment.CENTER,
    )
    z_mount_plate = align(
        z_mount_plate,
        z_profile_contact_reference,
        Alignment.STACK_BACK,
    )
    z_mount_plate = align(z_mount_plate, z_profile_contact_reference, Alignment.TOP)

    hollow_momentum_profile = create_hollow_profile_ring(
        z_axis_top_profile_gusset_profile_outer_diameter,
        profile_depth=z_axis_top_profile_gusset_profile_width,
        profile_height=z_axis_top_profile_gusset_profile_height,
        wall_thickness=z_axis_top_profile_gusset_profile_wall,
        angle=90,
    )
    hollow_momentum_profile = rotate(-90, axis=(1, 0, 0))(hollow_momentum_profile)
    if side_alignment == Alignment.RIGHT:
        hollow_momentum_profile = mirror((1, 0, 0))(hollow_momentum_profile)

    hollow_momentum_profile = align(
        hollow_momentum_profile,
        z_mount_plate,
        Alignment.BOTTOM,
    )

    hollow_momentum_profile = align(
        hollow_momentum_profile,
        z_mount_plate,
        side_alignment.opposite.stack_alignment,
    )
    hollow_momentum_profile = align(
        hollow_momentum_profile,
        z_profile_contact_reference,
        Alignment.STACK_BACK,
    )

    top_profile_footprint_reference = create_box(
        z_axis_top_profile_gusset_top_eye_length,
        top_profile_size,
        top_profile_size,
    )
    top_profile_footprint_reference = align(
        top_profile_footprint_reference,
        z_profile_contact_reference,
        side_alignment,
    )
    top_profile_footprint_reference = align(
        top_profile_footprint_reference,
        z_profile_contact_reference,
        Alignment.STACK_BACK,
        stack_gap=z_axis_top_bridge_profile_back_offset,
    )

    top_profile_bottom_lip = create_box(
        z_axis_top_profile_gusset_top_eye_length,
        z_axis_top_profile_gusset_top_eye_width,
        z_axis_top_profile_gusset_top_eye_thickness,
    )
    top_profile_bottom_lip = align(
        top_profile_bottom_lip,
        top_profile_footprint_reference,
        Alignment.CENTER,
    )
    top_profile_bottom_lip = align(
        top_profile_bottom_lip,
        hollow_momentum_profile,
        Alignment.STACK_TOP,
    )

    top_profile_bottom_lip = align(
        top_profile_bottom_lip, z_mount_plate, side_alignment
    )

    gusset = PartCollector()
    for feature in (
        z_mount_plate,
        top_profile_bottom_lip,
        hollow_momentum_profile,
    ):
        gusset = gusset.fuse(feature)

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
        screw_axis_reference = create_cylinder(
            screw_hole_radius,
            z_axis_top_profile_gusset_wall_thickness,
            direction=(0, 1, 0),
        )
        screw_axis_reference = align(
            screw_axis_reference,
            z_mount_plate,
            Alignment.CENTER,
            axes=[1],
        )
        screw_axis_reference = translate(0, 0, screw_z)(screw_axis_reference)

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
        screw_visual = align(screw_visual, z_mount_plate, Alignment.BACK)
        screw_visual = translate(0, screw_spec.cylinder_head_height, 0)(screw_visual)
        screw_visuals.append((f"z_mount_screw_{screw_index}", screw_visual))

    top_screw_side_x = side_alignment.sign * z_profile_size / 2
    top_screw_offsets_from_side = (
        z_axis_top_profile_gusset_top_screw_inset,
        z_axis_top_profile_gusset_top_eye_length
        - z_axis_top_profile_gusset_top_screw_inset,
    )
    for screw_index, screw_offset_from_side in enumerate(top_screw_offsets_from_side):
        screw_x = top_screw_side_x - side_alignment.sign * screw_offset_from_side
        screw_axis_reference = create_cylinder(
            screw_hole_radius,
            z_axis_top_profile_gusset_top_eye_thickness,
        )
        screw_axis_reference = align(
            screw_axis_reference,
            top_profile_bottom_lip,
            Alignment.CENTER,
            axes=[1, 2],
        )
        screw_axis_reference = translate(screw_x, 0, 0)(screw_axis_reference)

        screw_cutter = create_cylinder(screw_hole_radius, BIG_THING)
        screw_cutter = align(screw_cutter, screw_axis_reference, Alignment.CENTER)
        gusset = gusset.cut(screw_cutter)

        screw_visual = create_cylinder_screw(
            z_axis_top_profile_gusset_screw_size,
            z_axis_top_profile_gusset_screw_length,
        )
        screw_visual = rotate(180, axis=(1, 0, 0))(screw_visual)
        screw_visual = align(
            screw_visual,
            screw_axis_reference,
            Alignment.CENTER,
            axes=[0, 1],
        )
        screw_visual = align(screw_visual, top_profile_bottom_lip, Alignment.BOTTOM)
        screw_visual = translate(0, 0, -screw_spec.cylinder_head_height)(screw_visual)
        screw_visuals.append((f"top_profile_screw_{screw_index}", screw_visual))

    gusset_size = get_bounding_box_size(gusset)
    side_walls = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        wall = create_box(
            z_axis_top_profile_gusset_wall_thickness,
            gusset_size[1],
            BIG_THING / 3,
        )

        wall = align(wall, z_mount_plate, Alignment.CENTER)
        wall = align(wall, top_profile_bottom_lip, Alignment.STACK_BOTTOM)
        wall = align(wall, gusset, Alignment.FRONT)
        wall = align(wall, z_mount_plate, lr)

        side_walls = side_walls.fuse(wall)

    side_wall_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    side_wall_cutter = align(side_wall_cutter, z_mount_plate, Alignment.CENTER)

    side_wall_cutter = align(side_wall_cutter, z_mount_plate, Alignment.STACK_BOTTOM)
    side_walls = side_walls.cut(side_wall_cutter)

    z_mount_plate_size = get_bounding_box_size(z_mount_plate)
    bottom_wall = create_box(
        z_mount_plate_size[0],
        gusset_size[1],
        z_axis_top_profile_gusset_wall_thickness,
    )
    bottom_wall = align(bottom_wall, z_mount_plate, Alignment.CENTER)
    bottom_wall = align(bottom_wall, z_mount_plate, Alignment.BOTTOM)
    bottom_wall = align(bottom_wall, z_mount_plate, Alignment.FRONT)

    gusset = gusset.fuse(side_walls)
    gusset = gusset.fuse(bottom_wall)

    retval = LeaderFollowersCuttersPart(leader=gusset)
    retval.add_named_follower(top_profile_bottom_lip, "top_profile_bottom_lip")
    retval.add_named_non_production_part(
        z_profile_contact_reference,
        "z_profile_contact_reference",
    )
    for name, screw_visual in screw_visuals:
        retval.add_named_non_production_part(screw_visual, name)

    return retval
