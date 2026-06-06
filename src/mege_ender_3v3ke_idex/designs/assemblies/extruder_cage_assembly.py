"""Standalone extruder cage assembly skeleton."""

from shellforgepy.simple import *


def create_extruder_cage_assembly(
    *,
    sprite_extruder,
    extruder_cage_mount_plate_thickness,
    extruder_cage_flange_thickness,
    extruder_cage_screw_size,
):
    """Create a standalone extruder cage around the injected sprite extruder."""

    _ = (extruder_cage_flange_thickness, extruder_cage_screw_size)

    sprite_extruder_size = get_bounding_box_size(sprite_extruder)

    left_mount_plate = create_box(
        extruder_cage_mount_plate_thickness,
        sprite_extruder_size[1],
        sprite_extruder_size[2],
    )
    left_mount_plate = align(left_mount_plate, sprite_extruder, Alignment.CENTER)
    left_mount_plate = align(left_mount_plate, sprite_extruder, Alignment.STACK_LEFT)

    right_mount_plate = create_box(
        extruder_cage_mount_plate_thickness,
        sprite_extruder_size[1],
        sprite_extruder_size[2],
    )
    right_mount_plate = align(right_mount_plate, sprite_extruder, Alignment.CENTER)
    right_mount_plate = align(right_mount_plate, sprite_extruder, Alignment.STACK_RIGHT)

    cage = LeaderFollowersCuttersPart(left_mount_plate.fuse(right_mount_plate))
    cage.add_named_follower(left_mount_plate, "left_mount_plate")
    cage.add_named_follower(right_mount_plate, "right_mount_plate")

    return cage
