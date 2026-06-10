"""Part fan v2 assembly built from standalone injected fan artifacts."""

from shellforgepy.simple import *


def create_part_fan_assembly_v2(
    *,
    sprite_extruder,
    front_part_fan,
    side_part_fan,
    blower_ring,
):
    _ = sprite_extruder

    front_mount_plate = front_part_fan.get_named_follower("mount_plate")
    front_outlet = front_part_fan.get_named_follower("outlet")
    side_mount_plate = side_part_fan.get_named_follower("mount_plate")
    side_outlet = side_part_fan.get_named_follower("outlet")

    fused_part_fan = front_mount_plate
    fused_part_fan = fused_part_fan.fuse(front_outlet)
    fused_part_fan = fused_part_fan.fuse(side_mount_plate)
    fused_part_fan = fused_part_fan.fuse(side_outlet)

    front_part_fan_cutter = front_outlet.fuse(front_part_fan.leader)
    front_part_fan_cutter = create_convex_hull(front_part_fan_cutter)

    blower_ring_with_cut = blower_ring.leader.cut(front_part_fan_cutter)
    fused_part_fan = fused_part_fan.fuse(blower_ring_with_cut)

    # blower_ring_convex_hull = create_convex_hull(blower_ring) # we will use this later to cut the side fan duct

    retval = LeaderFollowersCuttersPart(fused_part_fan)
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
