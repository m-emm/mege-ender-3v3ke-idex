import math

from assembly_defaults import DEFAULTS, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.extruder_cage_assembly import (
    create_extruder_cage_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.sprite_extruder_assembly import (
    create_sprite_extruder_assembly,
)
from shellforgepy.simple import get_bounding_box, get_bounding_box_size, get_volume


def test_extruder_cage_wraps_sprite_extruder_with_left_and_right_mount_plates():
    sprite_extruder = create_sprite_extruder_assembly(
        **assembly_kwargs(create_sprite_extruder_assembly)
    )

    cage = create_extruder_cage_assembly(
        **assembly_kwargs(
            create_extruder_cage_assembly,
            sprite_extruder=sprite_extruder,
        )
    )

    assert get_volume(cage.leader) > 0

    sprite_extruder_size = get_bounding_box_size(sprite_extruder)
    sprite_extruder_bbox = get_bounding_box(sprite_extruder)
    mount_plate_thickness = DEFAULTS["extruder_cage_mount_plate_thickness"]

    left_mount_plate = cage.get_follower_part_by_name("left_mount_plate")
    right_mount_plate = cage.get_follower_part_by_name("right_mount_plate")

    for mount_plate in [left_mount_plate, right_mount_plate]:
        mount_plate_size = get_bounding_box_size(mount_plate)
        assert math.isclose(
            mount_plate_size[0],
            mount_plate_thickness,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
        assert math.isclose(
            mount_plate_size[1],
            sprite_extruder_size[1],
            rel_tol=0.0,
            abs_tol=1e-6,
        )
        assert math.isclose(
            mount_plate_size[2],
            sprite_extruder_size[2],
            rel_tol=0.0,
            abs_tol=1e-6,
        )

    left_mount_plate_bbox = get_bounding_box(left_mount_plate)
    right_mount_plate_bbox = get_bounding_box(right_mount_plate)

    assert math.isclose(
        left_mount_plate_bbox[1][0],
        sprite_extruder_bbox[0][0],
        rel_tol=0.0,
        abs_tol=1e-6,
    )
    assert math.isclose(
        right_mount_plate_bbox[0][0],
        sprite_extruder_bbox[1][0],
        rel_tol=0.0,
        abs_tol=1e-6,
    )
