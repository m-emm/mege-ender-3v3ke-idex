"""Declarative single-side z-axis assembly."""

from mege_ender_3v3ke_idex.designs.idex_parameters import (
    BIG_THING,
    motor_mount_axle_clearance,
    motor_mount_boss_clearance,
    motor_mount_boss_clearance_z,
    motor_mount_plate_fillet_radius,
    motor_mount_plate_thickness,
    z_axis_carriage_x_axis_connector_thickness,
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
    z_axis_pillow_block_bearing_z_offset,
    z_axis_rod_clamp_gap,
)
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from mege_ender_3v3ke_idex.designs.z_axis import (
    create_axial_ball_bearing_8_x_19,
    create_axial_bearing_stopper,
    create_axial_rod_clamp,
    create_carriage,
    create_pillow_block_bearing,
    create_profile_mount_plate,
    create_top_mount,
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


def _get_rods_parts(z_axis_rods):
    guide_rod = z_axis_rods.leader if hasattr(z_axis_rods, "leader") else z_axis_rods
    threaded_rod = z_axis_rods.get_named_non_production_part("threaded_rod")
    return guide_rod, threaded_rod


def _fuse_named_followers(part):
    fused = PartCollector()
    for _, follower in part.get_named_follower_items():
        fused = fused.fuse(follower)
    return fused


def _create_z_axis_mechanics(side_alignment, profile, guide_rod, threaded_rod):
    mechanics = LeaderFollowersCuttersPart(guide_rod)
    mechanics.add_named_non_production_part(threaded_rod, "threaded_rod")

    pillow_block_bearing = create_pillow_block_bearing().prefixed_copy(
        "pillow_block_bearing"
    )
    pillow_block_bearing = rotate(-90, axis=(1, 0, 0))(pillow_block_bearing)
    pillow_block_bearing = align(pillow_block_bearing, threaded_rod, Alignment.CENTER)
    pillow_block_bearing = align(pillow_block_bearing, threaded_rod, Alignment.BOTTOM)
    pillow_block_bearing = translate(0, 0, z_axis_pillow_block_bearing_z_offset)(
        pillow_block_bearing
    )

    mechanics.add_named_non_production_part(
        pillow_block_bearing.leader,
        "pillow_block_bearing_body",
    )
    for name, part in pillow_block_bearing.get_named_non_production_part_items():
        mechanics.add_named_non_production_part(part, name)
    for name, cutter in pillow_block_bearing.get_named_cutter_items():
        mechanics.add_named_cutter(cutter, name)

    axial_bearing_stopper = create_axial_bearing_stopper()
    axial_bearing_stopper = align(
        axial_bearing_stopper,
        threaded_rod,
        Alignment.CENTER,
    )
    axial_bearing_stopper = align(
        axial_bearing_stopper,
        pillow_block_bearing,
        Alignment.STACK_TOP,
    )
    mechanics.add_named_follower(axial_bearing_stopper, "axial_bearing_stopper")

    axial_bearing = create_axial_ball_bearing_8_x_19()
    axial_bearing = align(axial_bearing, threaded_rod, Alignment.CENTER)
    axial_bearing = align(axial_bearing, axial_bearing_stopper, Alignment.STACK_TOP)
    mechanics.add_named_non_production_part(axial_bearing, "axial_bearing")

    rod_clamp = create_axial_rod_clamp()
    rod_clamp = align(rod_clamp, threaded_rod, Alignment.CENTER)
    rod_clamp = align(rod_clamp, axial_bearing, Alignment.STACK_TOP)
    for name, part in rod_clamp.get_named_non_production_part_items():
        mechanics.add_named_non_production_part(part, name)
    for name, part in rod_clamp.get_named_follower_items():
        mechanics.add_named_follower(part, name)

    motor = create_nema_composite(
        axle_clearance=motor_mount_axle_clearance,
        boss_clearance=motor_mount_boss_clearance,
        boss_clearance_z=motor_mount_boss_clearance_z,
    )
    if side_alignment == Alignment.LEFT:
        motor = rotate(180)(motor)

    motor = align(motor, threaded_rod, Alignment.CENTER)
    motor = align(motor, profile, Alignment.BOTTOM)

    coupler = motor.get_named_follower("coupler")
    threaded_rod_part = mechanics.get_named_non_production_part("threaded_rod")
    coupler_aligner = align_translation(
        threaded_rod_part,
        coupler,
        Alignment.STACK_TOP,
        stack_gap=0,
    )
    mechanics = coupler_aligner(mechanics)
    guide_rod = mechanics.leader
    threaded_rod = mechanics.get_named_non_production_part("threaded_rod")

    pillow_base = mechanics.get_named_non_production_part("pillow_block_bearing_base")
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
    pillow_bearing_mount_plate = mechanics.use_as_cutter_on(pillow_bearing_mount_plate)

    profile_plane_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    profile_plane_cutter = align(
        profile_plane_cutter,
        pillow_bearing_mount_plate,
        Alignment.CENTER,
    )
    profile_plane_cutter = align(profile_plane_cutter, profile, Alignment.FRONT)
    pillow_bearing_mount_plate = pillow_bearing_mount_plate.cut(profile_plane_cutter)

    for cutter_index in range(2):
        cutter = mechanics.get_named_cutter(
            f"pillow_block_bearing_mount_hole_cutter_{cutter_index}"
        )
        nut_cutter = create_nut("M4", no_hole=True, slack=0.2)
        nut_cutter = rotate(90, axis=(1, 0, 0))(nut_cutter)
        nut_cutter = align(nut_cutter, cutter, Alignment.CENTER)
        nut_cutter = align(nut_cutter, pillow_bearing_mount_plate, Alignment.BACK)
        pillow_bearing_mount_plate = pillow_bearing_mount_plate.cut(nut_cutter)

    pillow_bearing_profile_mount_plate = create_profile_mount_plate()
    pillow_bearing_profile_mount_plate = align(
        pillow_bearing_profile_mount_plate,
        pillow_bearing_mount_plate,
        Alignment.CENTER,
    )
    pillow_bearing_profile_mount_plate = align(
        pillow_bearing_profile_mount_plate,
        pillow_bearing_mount_plate,
        Alignment.BACK,
    )
    pillow_bearing_profile_mount_plate = align(
        pillow_bearing_profile_mount_plate,
        pillow_bearing_mount_plate,
        Alignment.STACK_TOP,
    )
    pillow_bearing_mount_plate = pillow_bearing_mount_plate.fuse(
        pillow_bearing_profile_mount_plate
    )
    mechanics.add_named_follower(
        pillow_bearing_mount_plate,
        "pillow_bearing_mount_plate",
    )

    mechanics.add_named_non_production_part(mechanics.leader, "guide_rod")
    for name, part in motor.get_named_follower_items():
        mechanics.add_named_non_production_part(part, name)

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

    for name, part in screws_mount_assembly.get_named_non_production_part_items():
        mechanics.add_named_non_production_part(part, f"guide_rod_clamp_{name}")

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

    mechanics.add_named_follower(mount_plate_clamp_part, "mount_plate_clamp_part")
    mechanics.add_named_follower(mount_plate_back, "mount_plate_back")

    top_mount = create_top_mount(guide_rod, threaded_rod, profile)
    mechanics.add_named_follower(top_mount.leader, "top_mount")
    mechanics.add_named_follower(
        top_mount.get_named_follower("top_mount_clamp"),
        "top_mount_clamp",
    )
    for name, part in top_mount.get_named_non_production_part_items():
        mechanics.add_named_non_production_part(part, f"top_mount_{name}")

    return mechanics


def create_z_axis_side_assembly(
    *,
    z_axis_profile,
    z_axis_rods,
    side,
    carriage_z_offset,
    z_axis_base_z_offset,
    context=None,
):
    """Create one z-axis side against an already placed profile assembly."""

    del context

    side_alignment = _to_side_alignment(side)
    profile = _get_profile_part(z_axis_profile)
    guide_rod, threaded_rod = _get_rods_parts(z_axis_rods)

    z_axis = _create_z_axis_mechanics(
        side_alignment,
        profile,
        guide_rod,
        threaded_rod,
    )
    z_axis = translate(0, 0, z_axis_base_z_offset)(z_axis)

    carriage = create_carriage(
        z_axis.get_named_non_production_part("guide_rod"),
        z_axis.get_named_non_production_part("threaded_rod"),
        profile,
    )
    carriage = translate(0, 0, carriage_z_offset)(carriage)

    leader = _fuse_named_followers(z_axis)
    leader = leader.fuse(carriage.leader)

    retval = LeaderFollowersCuttersPart(leader=leader)

    for name, follower in z_axis.get_named_follower_items():
        retval.add_named_follower(follower, name)

    retval.add_named_follower(carriage.leader, "carriage")
    for name, follower in carriage.get_named_follower_items():
        retval.add_named_follower(follower, name)

    for name, part in z_axis.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)

    for name, part in carriage.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)

    carriage_fused = carriage.leaders_followers_fused()
    retval.add_named_non_production_part(carriage_fused, "carriage_fused")
    retval.add_named_non_production_part(
        translate(0, 0, z_axis_carriage_x_axis_connector_thickness)(carriage_fused),
        "x_axis_alignment_reference",
    )

    return retval
