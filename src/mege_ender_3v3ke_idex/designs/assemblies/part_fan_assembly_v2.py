"""Part fan v2 assembly built from standalone injected fan artifacts."""

from shellforgepy.simple import *


def create_part_fan_assembly_v2(
    *,
    sprite_extruder,
    front_part_fan,
    side_part_fan,
    blower_ring,
    duct_extension_width,
    part_fan_duct_extension_length,
    feeder_ring_height,
    feeder_ring_wall,
):
    _ = sprite_extruder

    front_mount_plate = front_part_fan.get_named_follower("mount_plate")
    front_outlet = front_part_fan.get_named_follower("outlet")
    side_mount_plate = side_part_fan.get_named_follower("mount_plate")
    side_outlet = side_part_fan.get_named_follower("outlet")

    fused_front_part_fan = front_mount_plate
    fused_front_part_fan = fused_front_part_fan.fuse(front_outlet)
    fused_front_part_fan = fused_front_part_fan.fuse(side_mount_plate)
    fused_front_part_fan = fused_front_part_fan.fuse(side_outlet)

    duct_extension_body = create_box(
        duct_extension_width, part_fan_duct_extension_length, feeder_ring_height
    )

    duct_extension = align(duct_extension_body, side_outlet, Alignment.CENTER)
    duct_extension = align(duct_extension, blower_ring, Alignment.TOP)

    duct_extension = align(duct_extension, side_outlet, Alignment.FRONT)

    side_fan_fused = side_part_fan.leader.fuse(side_outlet)

    side_fan_cutter = create_convex_hull(side_fan_fused)
    blower_ring_cutter = create_convex_hull(blower_ring.leader)

    duct_extension = duct_extension.cut(side_fan_cutter)
    duct_extension = duct_extension.cut(blower_ring_cutter)
    duct_extension_air_cutter = create_box(
        duct_extension_width - 2 * feeder_ring_wall,
        part_fan_duct_extension_length - 2 * feeder_ring_wall,
        feeder_ring_height - 2 * feeder_ring_wall,
    )

    duct_extension_air_cutter = align(
        duct_extension_air_cutter, duct_extension, Alignment.CENTER
    )
    duct_extension = duct_extension.cut(duct_extension_air_cutter)

    front_part_fan_cutter = create_convex_hull(front_part_fan.leader, front_outlet)

    blower_ring_with_cut = blower_ring.leader.cut(front_part_fan_cutter)
    blower_ring_with_cut = blower_ring_with_cut.cut(duct_extension_air_cutter)

    fused_front_part_fan = fused_front_part_fan.fuse(blower_ring_with_cut)
    fused_front_part_fan = fused_front_part_fan.fuse(duct_extension)

    retval = LeaderFollowersCuttersPart(fused_front_part_fan)
    retval.add_consumed_part_ref(
        front_part_fan.part_ref_for_named_follower("mount_plate")
    )
    retval.add_consumed_part_ref(front_part_fan.part_ref_for_named_follower("outlet"))
    retval.add_consumed_part_ref(
        side_part_fan.part_ref_for_named_follower("mount_plate")
    )
    retval.add_consumed_part_ref(side_part_fan.part_ref_for_named_follower("outlet"))
    retval.add_consumed_part_ref(blower_ring.part_ref_for_leader())

    return retval
