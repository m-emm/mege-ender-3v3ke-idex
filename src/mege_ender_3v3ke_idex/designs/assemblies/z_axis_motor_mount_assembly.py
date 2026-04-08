"""Declarative z-axis motor mount assembly."""

import math

from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from mege_ender_3v3ke_idex.designs.z_axis_components import (
    create_pillow_block_bearing,
    create_profile_mount_plate,
)
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


def _get_threaded_rod_part(z_axis_threaded_rod):
    return (
        z_axis_threaded_rod.leader
        if hasattr(z_axis_threaded_rod, "leader")
        else z_axis_threaded_rod
    )


def _get_threaded_rod_coupler_reference(z_axis_threaded_rod):
    return z_axis_threaded_rod.get_named_non_production_part("coupler_reference")


def create_z_axis_motor_mount_assembly(
    *,
    z_axis_profile,
    z_axis_guide_rod,
    z_axis_threaded_rod,
    side,
    BIG_THING,
    motor_mount_axle_clearance,
    motor_mount_boss_clearance,
    motor_mount_boss_clearance_z,
    motor_mount_plate_fillet_radius,
    motor_mount_plate_thickness,
    z_axis_cylinder_head_clearance,
    z_axis_additional_screw_mount_clearance,
    z_axis_default_clearance_hole_type,
    z_axis_default_screw_nut_cutter_clearance,
    z_axis_guide_rod_clamp_depth,
    z_axis_guide_rod_clamp_rod_clearance,
    z_axis_guide_rod_clamp_screw_length,
    z_axis_guide_rod_clamp_screw_size,
    z_axis_guide_rod_clamp_thickness,
    z_axis_guide_rod_clamp_width,
    z_axis_guide_rod_diameter,
    z_axis_motor_mount_plate_depth,
    z_axis_motor_mount_plate_profile_distance,
    z_axis_motor_mount_plate_size,
    z_axis_motor_mount_plate_box_wall,
    z_axis_profile_mount_plate_fillet_radius,
    z_axis_profile_mount_plate_height,
    z_axis_profile_mount_plate_num_holes,
    z_axis_profile_mount_plate_screw_inset,
    z_axis_profile_mount_plate_thickness,
    z_axis_profile_mount_plate_clearance,
    z_axis_pillow_block_bearing_z_offset,
    z_axis_pillow_block_bearing_base_gap_length,
    z_axis_pillow_block_bearing_base_overall_length,
    z_axis_pillow_block_bearing_base_thickness,
    z_axis_pillow_block_bearing_base_width,
    z_axis_pillow_block_bearing_cage_diameter,
    z_axis_pillow_block_bearing_cage_rim,
    z_axis_pillow_block_bearing_cage_thickness,
    z_axis_pillow_block_bearing_mount_hole_center_distance,
    z_axis_pillow_block_bearing_mount_hole_diameter,
    z_axis_pillow_block_bearing_mount_nut_clearance,
    z_axis_pillow_block_bearing_mount_screw_length,
    z_axis_pillow_block_bearing_mount_screw_size,
    z_axis_pillow_block_bearing_rod_holder_inner_diameter,
    z_axis_pillow_block_bearing_rod_holder_length,
    z_axis_pillow_block_bearing_rod_holder_outer_diameter,
    z_axis_pillow_block_bottom_base_bridge_width,
    z_axis_rod_clamp_gap,
):
    """Create the printable motor mount assembly for one z-axis side."""

    side_alignment = _to_side_alignment(side)
    profile = _get_profile_part(z_axis_profile)
    guide_rod = _get_guide_rod_part(z_axis_guide_rod)
    threaded_rod = _get_threaded_rod_part(z_axis_threaded_rod)
    coupler = _get_threaded_rod_coupler_reference(z_axis_threaded_rod)

    motor = create_nema_composite(
        axle_clearance=motor_mount_axle_clearance,
        boss_clearance=motor_mount_boss_clearance,
        boss_clearance_z=motor_mount_boss_clearance_z,
    )

    if side_alignment == Alignment.RIGHT:
        motor = rotate(180)(motor)

    motor = align(motor, threaded_rod, Alignment.CENTER, axes=[0, 1])
    motor = align(motor, profile, Alignment.BOTTOM)

    motor_body = motor.get_named_follower("body")
    mount_plate = create_filleted_box(
        z_axis_motor_mount_plate_size,
        z_axis_motor_mount_plate_depth,
        motor_mount_plate_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    mount_plate = align(mount_plate, threaded_rod, Alignment.CENTER, axes=[0])

    mount_plate = align(mount_plate, motor_body, Alignment.STACK_TOP)
    mount_plate = align(
        mount_plate,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_motor_mount_plate_profile_distance,
    )

    pillow_block_bearing = create_pillow_block_bearing(
        BIG_THING=BIG_THING,
        z_axis_pillow_block_bearing_base_gap_length=z_axis_pillow_block_bearing_base_gap_length,
        z_axis_pillow_block_bearing_base_overall_length=z_axis_pillow_block_bearing_base_overall_length,
        z_axis_pillow_block_bearing_base_thickness=z_axis_pillow_block_bearing_base_thickness,
        z_axis_pillow_block_bearing_base_width=z_axis_pillow_block_bearing_base_width,
        z_axis_pillow_block_bearing_cage_diameter=z_axis_pillow_block_bearing_cage_diameter,
        z_axis_pillow_block_bearing_cage_rim=z_axis_pillow_block_bearing_cage_rim,
        z_axis_pillow_block_bearing_cage_thickness=z_axis_pillow_block_bearing_cage_thickness,
        z_axis_pillow_block_bearing_mount_hole_center_distance=z_axis_pillow_block_bearing_mount_hole_center_distance,
        z_axis_pillow_block_bearing_mount_hole_diameter=z_axis_pillow_block_bearing_mount_hole_diameter,
        z_axis_pillow_block_bearing_mount_screw_length=z_axis_pillow_block_bearing_mount_screw_length,
        z_axis_pillow_block_bearing_mount_screw_size=z_axis_pillow_block_bearing_mount_screw_size,
        z_axis_pillow_block_bearing_rod_holder_inner_diameter=z_axis_pillow_block_bearing_rod_holder_inner_diameter,
        z_axis_pillow_block_bearing_rod_holder_length=z_axis_pillow_block_bearing_rod_holder_length,
        z_axis_pillow_block_bearing_rod_holder_outer_diameter=z_axis_pillow_block_bearing_rod_holder_outer_diameter,
        z_axis_pillow_block_bottom_base_bridge_width=z_axis_pillow_block_bottom_base_bridge_width,
    ).prefixed_copy("pillow_block_bearing")
    pillow_block_bearing = rotate(-90, axis=(1, 0, 0))(pillow_block_bearing)
    pillow_block_bearing = align(pillow_block_bearing, threaded_rod, Alignment.CENTER)
    pillow_block_bearing = align(
        pillow_block_bearing,
        coupler,
        Alignment.STACK_TOP,
        stack_gap=z_axis_pillow_block_bearing_z_offset,
    )

    pillow_base = pillow_block_bearing.get_named_non_production_part(
        "pillow_block_bearing_base"
    )
    pillow_base_size = get_bounding_box_size(pillow_base)

    pillow_bearing_mount_plate = create_box(
        pillow_base_size[0],
        BIG_THING,
        pillow_base_size[2],
    )
    pillow_bearing_mount_plate = align(
        pillow_bearing_mount_plate,
        pillow_base,
        Alignment.CENTER,
    )
    pillow_bearing_mount_plate = align(
        pillow_bearing_mount_plate,
        pillow_base,
        Alignment.STACK_BACK,
    )
    pillow_bearing_mount_plate = pillow_block_bearing.use_as_cutter_on(
        pillow_bearing_mount_plate
    )

    profile_plane_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    profile_plane_cutter = align(
        profile_plane_cutter,
        pillow_bearing_mount_plate,
        Alignment.CENTER,
    )
    profile_plane_cutter = align(profile_plane_cutter, profile, Alignment.FRONT)
    pillow_bearing_mount_plate = pillow_bearing_mount_plate.cut(profile_plane_cutter)

    profile_mount_plates = PartCollector()
    for alignment in [Alignment.LEFT, Alignment.RIGHT]:
        profile_mount_plate = create_profile_mount_plate(
            profile_mount_width=z_axis_motor_mount_plate_size,
            z_axis_profile_mount_plate_thickness=z_axis_profile_mount_plate_thickness,
            z_axis_profile_mount_plate_height=z_axis_profile_mount_plate_height,
            z_axis_profile_mount_plate_fillet_radius=z_axis_profile_mount_plate_fillet_radius,
            BIG_THING=BIG_THING,
            num_holes=z_axis_profile_mount_plate_num_holes,
            screw_inset=z_axis_profile_mount_plate_screw_inset,
        )
        profile_mount_plate = rotate(90)(profile_mount_plate)
        profile_mount_plate = align(profile_mount_plate, mount_plate, Alignment.CENTER)
        profile_mount_plate = align(
            profile_mount_plate,
            mount_plate,
            Alignment.STACK_BACK,
            stack_gap=-motor_mount_plate_thickness,
        )
        profile_mount_plate = align(profile_mount_plate, mount_plate, Alignment.BOTTOM)
        profile_mount_plate = align(
            profile_mount_plate,
            z_axis_profile,
            alignment.stack_alignment,
            stack_gap=z_axis_profile_mount_plate_clearance,
        )
        profile_mount_plates = profile_mount_plates.fuse(profile_mount_plate)

    spacer_cutter_size = 2 * pillow_base_size[2] / math.sqrt(2)
    pillow_block_bearing_screw_spacer_cutter = create_box(
        BIG_THING,
        spacer_cutter_size,
        spacer_cutter_size,
    )
    pillow_block_bearing_screw_spacer_cutter = rotate(45, axis=(1, 0, 0))(
        pillow_block_bearing_screw_spacer_cutter
    )
    pillow_block_bearing_screw_spacer_cutter = align(
        pillow_block_bearing_screw_spacer_cutter,
        pillow_base,
        Alignment.CENTER,
    )
    pillow_block_bearing_screw_spacer_cutter = align(
        pillow_block_bearing_screw_spacer_cutter,
        profile_mount_plates,
        Alignment.EDGE_FRONT,
    )
    profile_mount_plates = profile_mount_plates.cut(
        pillow_block_bearing_screw_spacer_cutter
    )

    guide_rod_clamp = create_filleted_box(
        z_axis_guide_rod_clamp_width,
        z_axis_guide_rod_clamp_depth,
        z_axis_guide_rod_clamp_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    guide_rod_clamp = align(guide_rod_clamp, mount_plate, Alignment.CENTER)
    guide_rod_clamp = align(guide_rod_clamp, guide_rod, Alignment.CENTER, axes=[0, 1])
    guide_rod_clamp = align(guide_rod_clamp, mount_plate, Alignment.STACK_TOP)

    mount_plate_box = create_filleted_box(
        z_axis_motor_mount_plate_size,
        z_axis_motor_mount_plate_size,
        z_axis_guide_rod_clamp_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    mount_plate_box_cutter = create_filleted_box(
        z_axis_motor_mount_plate_size - 2 * z_axis_motor_mount_plate_box_wall,
        z_axis_motor_mount_plate_size - 2 * z_axis_motor_mount_plate_box_wall,
        z_axis_guide_rod_clamp_thickness,
        motor_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.BOTTOM, Alignment.TOP],
    )
    mount_plate_box_cutter = align(
        mount_plate_box_cutter, mount_plate_box, Alignment.CENTER
    )
    mount_plate_box = mount_plate_box.cut(mount_plate_box_cutter)
    mount_plate_box = align(mount_plate_box, mount_plate, Alignment.CENTER)
    mount_plate_box = align(mount_plate_box, mount_plate, Alignment.STACK_TOP)
    mount_plate_box = align(mount_plate_box, z_axis_profile, Alignment.STACK_FRONT)

    mount_plate_box_side_hole_cutter_size = (
        z_axis_guide_rod_clamp_thickness * 0.8 / math.sqrt(2)
    )

    mount_plate_box_side_hole_cutter = create_filleted_box(
        BIG_THING,
        mount_plate_box_side_hole_cutter_size,
        mount_plate_box_side_hole_cutter_size,
        fillet_radius=mount_plate_box_side_hole_cutter_size / 4,
    )

    mount_plate_box_side_hole_cutter = rotate(45, axis=(1, 0, 0))(
        mount_plate_box_side_hole_cutter
    )

    mount_plate_box_side_hole_cutter = align(
        mount_plate_box_side_hole_cutter, mount_plate_box, Alignment.CENTER
    )
    mount_plate_box = mount_plate_box.cut(mount_plate_box_side_hole_cutter)

    mount_plate_box_back = create_box(
        z_axis_motor_mount_plate_size,
        z_axis_motor_mount_plate_box_wall,
        z_axis_profile_mount_plate_height - z_axis_profile_mount_plate_fillet_radius,
    )

    mount_plate_box_back = align(
        mount_plate_box_back, mount_plate_box, Alignment.CENTER
    )
    mount_plate_box_back = align(mount_plate_box_back, mount_plate_box, Alignment.BACK)
    mount_plate_box_back = align(
        mount_plate_box_back, profile_mount_plates, Alignment.BOTTOM
    )

    mount_plate_box = mount_plate_box.fuse(mount_plate_box_back)

    mount_plate = mount_plate.fuse(mount_plate_box)

    mount_plate = motor.use_as_cutter_on(mount_plate)

    screws_mount_assembly = create_four_screws_mount_assembly(
        guide_rod_clamp,
        z_axis_guide_rod_clamp_screw_size,
        z_axis_guide_rod_clamp_screw_length,
        Alignment.FRONT,
        flush_with_top=True,
        cylinder_head_cutter_clearance=z_axis_cylinder_head_clearance,
        clearance_type=z_axis_default_clearance_hole_type,
        additional_screw_mount_clearance=z_axis_additional_screw_mount_clearance,
        nut_cutter_clearance=z_axis_default_screw_nut_cutter_clearance,
    )
    guide_rod_clamp = screws_mount_assembly.use_as_cutter_on(guide_rod_clamp)

    guide_rod_cutter = create_cylinder(
        z_axis_guide_rod_diameter / 2 + z_axis_guide_rod_clamp_rod_clearance,
        2 * BIG_THING,
    )
    guide_rod_cutter = align(guide_rod_cutter, guide_rod, Alignment.CENTER)

    mount_plate = mount_plate.fuse(guide_rod_clamp)
    mount_plate = mount_plate.fuse(profile_mount_plates)
    mount_plate = mount_plate.cut(guide_rod_cutter)
    mount_plate = mount_plate.fuse(pillow_bearing_mount_plate)

    for cutter_index in range(2):
        cutter = pillow_block_bearing.get_named_cutter(
            f"pillow_block_bearing_mount_hole_cutter_{cutter_index}"
        )
        nut_cutter = create_nut(
            z_axis_pillow_block_bearing_mount_screw_size,
            no_hole=True,
            slack=z_axis_pillow_block_bearing_mount_nut_clearance,
        )
        nut_cutter = rotate(90, axis=(1, 0, 0))(nut_cutter)
        nut_cutter = align(nut_cutter, cutter, Alignment.CENTER)
        nut_cutter = align(nut_cutter, pillow_bearing_mount_plate, Alignment.BACK)
        mount_plate = mount_plate.cut(nut_cutter)

    pillow_bearing_mount_plate_size = get_bounding_box_size(pillow_bearing_mount_plate)

    for tb in [Alignment.TOP, Alignment.BOTTOM]:
        pillow_bearing_mount_plate_support = create_right_triangle(
            pillow_bearing_mount_plate_size[1],
            pillow_bearing_mount_plate_size[1],
            pillow_bearing_mount_plate_size[0],
            extrusion_direction=(1, 0, 0),
            a_normal=(0, 0, -tb.sign),
            b_normal=(0, -1, 0),
        )
        pillow_bearing_mount_plate_support = align(
            pillow_bearing_mount_plate_support,
            pillow_bearing_mount_plate,
            Alignment.CENTER,
        )
        pillow_bearing_mount_plate_support = align(
            pillow_bearing_mount_plate_support,
            pillow_bearing_mount_plate,
            tb.stack_alignment,
        )

        mount_plate = mount_plate.fuse(pillow_bearing_mount_plate_support)

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

    retval.add_named_non_production_part(
        pillow_block_bearing.leader,
        "pillow_block_bearing_body",
    )
    for name, part in pillow_block_bearing.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)
    for name, part in motor.get_named_follower_items():
        retval.add_named_non_production_part(part, name)
    for name, part in screws_mount_assembly.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, f"guide_rod_clamp_{name}")

    return retval
