"""Declarative z-axis motor mount assembly."""

from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from mege_ender_3v3ke_idex.designs.z_axis_components import create_profile_mount_plate
from shellforgepy.simple import *


def _to_side_alignment(side):
    normalized_side = str(side).strip().lower()
    if normalized_side == "left":
        return Alignment.LEFT
    if normalized_side == "right":
        return Alignment.RIGHT
    raise ValueError(f"Unsupported z-axis side '{side}'")


def _get_profile_part(z_axis_profile):
    return (
        z_axis_profile.leader if hasattr(z_axis_profile, "leader") else z_axis_profile
    )


def _get_guide_rod_part(z_axis_guide_rod):
    return (
        z_axis_guide_rod.leader
        if hasattr(z_axis_guide_rod, "leader")
        else z_axis_guide_rod
    )


def create_z_axis_motor_mount_assembly(
    *,
    z_axis_profile,
    z_axis_guide_rod,
    side,
    BIG_THING,
    motor_mount_axle_clearance,
    motor_mount_boss_clearance,
    motor_mount_boss_clearance_z,
    motor_mount_plate_fillet_radius,
    motor_mount_plate_thickness,
    z_axis_cylinder_head_clearance,
    z_axis_default_clearance_hole_type,
    z_axis_default_screw_nut_cutter_clearance,
    z_axis_guide_rod_clamp_depth,
    z_axis_guide_rod_clamp_screw_length,
    z_axis_guide_rod_clamp_thickness,
    z_axis_guide_rod_clamp_width,
    z_axis_guide_rod_diameter,
    z_axis_motor_mount_plate_depth,
    z_axis_motor_mount_plate_profile_distance,
    z_axis_motor_mount_plate_size,
    z_axis_rod_clamp_gap,
    z_axis_threaded_rod_diameter,
    z_axis_threaded_rod_profile_distance,
    context=None,
):
    """Create the printable motor mount assembly for one z-axis side."""

    del context

    side_alignment = _to_side_alignment(side)
    profile = _get_profile_part(z_axis_profile)
    guide_rod = _get_guide_rod_part(z_axis_guide_rod)

    threaded_rod_reference = create_cylinder(
        z_axis_threaded_rod_diameter / 2, BIG_THING
    )
    threaded_rod_reference = align(
        threaded_rod_reference, guide_rod, Alignment.CENTER, axes=[0]
    )
    threaded_rod_reference = align(
        threaded_rod_reference,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_threaded_rod_profile_distance,
    )

    motor = create_nema_composite(
        axle_clearance=motor_mount_axle_clearance,
        boss_clearance=motor_mount_boss_clearance,
        boss_clearance_z=motor_mount_boss_clearance_z,
    )


    if side_alignment == Alignment.RIGHT:
        motor = rotate(180)(motor)

    motor = align(motor, threaded_rod_reference, Alignment.CENTER, axes=[0, 1])
    motor = align(motor, profile, Alignment.BOTTOM)

    motor_body = motor.get_named_follower("body")
    mount_plate = create_filleted_box(
        z_axis_motor_mount_plate_size,
        z_axis_motor_mount_plate_depth,
        motor_mount_plate_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    mount_plate = align(mount_plate, motor, Alignment.CENTER)
    mount_plate = align(mount_plate, motor_body, Alignment.STACK_TOP)
    mount_plate = align(
        mount_plate,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_motor_mount_plate_profile_distance,
    )

    profile_mount_plate = create_profile_mount_plate()
    profile_mount_plate = align(profile_mount_plate, mount_plate, Alignment.CENTER)
    profile_mount_plate = align(profile_mount_plate, mount_plate, Alignment.BACK)
    profile_mount_plate = align(profile_mount_plate, mount_plate, Alignment.STACK_TOP)

    mount_plate = motor.use_as_cutter_on(mount_plate)

    guide_rod_clamp = create_filleted_box(
        z_axis_guide_rod_clamp_width,
        z_axis_guide_rod_clamp_depth,
        z_axis_guide_rod_clamp_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    guide_rod_clamp = align(guide_rod_clamp, mount_plate, Alignment.CENTER)
    guide_rod_clamp = align(guide_rod_clamp, mount_plate, Alignment.STACK_TOP)
    guide_rod_clamp = align(guide_rod_clamp, mount_plate, Alignment.FRONT)

    screws_mount_assembly = create_four_screws_mount_assembly(
        guide_rod_clamp,
        "M3",
        z_axis_guide_rod_clamp_screw_length,
        Alignment.FRONT,
        flush_with_top=True,
        cylinder_head_cutter_clearance=z_axis_cylinder_head_clearance,
        clearance_type=z_axis_default_clearance_hole_type,
        nut_cutter_clearance=z_axis_default_screw_nut_cutter_clearance,
    )
    guide_rod_clamp = screws_mount_assembly.use_as_cutter_on(guide_rod_clamp)

    guide_rod_cutter = create_cylinder(
        z_axis_guide_rod_diameter / 2 + 0.1,
        2 * BIG_THING,
    )
    guide_rod_cutter = align(guide_rod_cutter, guide_rod, Alignment.CENTER)

    mount_plate = mount_plate.fuse(guide_rod_clamp)
    mount_plate = mount_plate.fuse(profile_mount_plate)
    mount_plate = mount_plate.cut(guide_rod_cutter)

    guide_rod_center = get_bounding_box_center(guide_rod)
    guide_rod_clamp_center = get_bounding_box_center(guide_rod_clamp)
    cut_point = (
        guide_rod_clamp_center[0],
        guide_rod_center[1],
        guide_rod_clamp_center[2],
    )
    mount_plate_back, mount_plate_clamp_part = cut_in_two(
        mount_plate,
        cut_normal=(0, 1, 0),
        cut_thickness=z_axis_rod_clamp_gap,
        cut_point=cut_point,
    )

    retval = LeaderFollowersCuttersPart(leader=mount_plate_back)
    retval.add_named_follower(mount_plate_clamp_part, "mount_plate_clamp_part")

    for name, part in motor.get_named_follower_items():
        retval.add_named_non_production_part(part, name)
    for name, part in screws_mount_assembly.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, f"guide_rod_clamp_{name}")

    return retval
