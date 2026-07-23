"""Join the lower belt-carriage remainder into the left extruder cage."""

from shellforgepy.simple import *

SPRITE_EXTRUDER_CUTTER_Y_ENLARGEMENT = 100


def join_left_belt_carriage_with_cage(
    *,
    extruder_cage,
    belt_carriage,
    sprite_extruder,
    tool_head_mount_machined,
    axis_profile,
):
    """Return a cage containing the carriage outside the Sprite envelope."""

    bridge_reference = belt_carriage.get_named_non_production_part("bridge_reference")
    joined_extruder_cage = extruder_cage.copy()

    belt_carriage_remainder = belt_carriage.cut(extruder_cage)
    joined_belt_carriage = belt_carriage_remainder

    bridge_size = get_bounding_box_size(bridge_reference)
    bridge_extension = materialize_bounding_box(
        joined_belt_carriage, y_size=bridge_size[1], z_size=6
    )
    bridge_extension = align(
        bridge_extension, joined_belt_carriage, Alignment.STACK_BOTTOM
    )
    bridge_extension = align(bridge_extension, bridge_reference, Alignment.FRONT)

    joined_belt_carriage = joined_belt_carriage.fuse(bridge_extension)

    top_plate = materialize_bounding_box(tool_head_mount_machined)
    top_plate = align(top_plate, tool_head_mount_machined, Alignment.STACK_TOP)

    profile_cutter = materialize_bounding_box(axis_profile, z_size=100, y_size=100)
    profile_cutter = align(profile_cutter, axis_profile, Alignment.FRONT)

    top_plate = top_plate.cut(profile_cutter)

    sprite_extruder_cutter = materialize_bounding_box(
        tool_head_mount_machined, z_size=100, x_enlargement=-20
    )
    sprite_extruder_cutter = align(
        sprite_extruder_cutter, sprite_extruder, Alignment.BACK
    )
    sprite_extruder_cutter = translate(0, 3, 0)(sprite_extruder_cutter)

    top_plate = top_plate.cut(sprite_extruder_cutter)

    top_plate = tool_head_mount_machined.use_as_cutter_on(top_plate)

    joined_belt_carriage.add_named_follower(top_plate, "belt_carriage_top_plate")
    # joined_extruder_cage.add_consumed_part_ref(belt_carriage.part_ref_for_leader())

    return {
        "extruder_cage": joined_extruder_cage,
        "belt_carriage": joined_belt_carriage,
    }
