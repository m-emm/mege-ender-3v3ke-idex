"""Join the lower belt-carriage remainder into the left extruder cage."""

from shellforgepy.simple import *

SPRITE_EXTRUDER_CUTTER_Y_ENLARGEMENT = 100


def join_left_belt_carriage_with_cage(
    *,
    extruder_cage,
    belt_carriage,
    sprite_extruder,
):
    """Return a cage containing the carriage outside the Sprite envelope."""

    joined_extruder_cage = extruder_cage.copy()

    belt_carriage_remainder = belt_carriage.cut(extruder_cage)
    joined_belt_carriage = belt_carriage_remainder

    bridge_extension = materialize_bounding_box(
        joined_belt_carriage, y_size=5, z_size=6
    )
    bridge_extension = align(
        bridge_extension, joined_belt_carriage, Alignment.STACK_BOTTOM
    )

    joined_belt_carriage = joined_belt_carriage.fuse(bridge_extension)
    # joined_extruder_cage.add_consumed_part_ref(belt_carriage.part_ref_for_leader())

    return {
        "extruder_cage": joined_extruder_cage,
        "belt_carriage": joined_belt_carriage,
    }
