from assembly_defaults import assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.extruder_cage_assembly import (
    create_extruder_cage_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.sprite_extruder_assembly import (
    create_sprite_extruder_assembly,
)
from shellforgepy.simple import get_volume


def _recut_delta(part, cutter):
    return get_volume(part) - get_volume(part.cut(cutter))


def test_extruder_cage_exposes_mounting_interfaces_and_screw_visuals():
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
    assert "left_mount_plate" not in cage.follower_indices_by_name
    assert "right_mount_plate" not in cage.follower_indices_by_name

    for follower_name in [
        "sprite_mount_base_plate",
        "part_fan_side_mount_plate",
        "part_fan_front_mount_plate",
        "part_fan_front_mount_plate_connector",
        "nitehawk_rear_mount_plate",
    ]:
        cage.get_follower_part_by_name(follower_name)

    for screw_name in [
        "sprite_mount_screw_left",
        "sprite_mount_screw_right",
        "nitehawk_mount_screw_0",
        "nitehawk_mount_screw_1",
    ]:
        cage.get_non_production_part_by_name(screw_name)

    for cutter_name in [
        "mount_hole_cutter",
        "nitehawk_mount_hole_0",
        "nitehawk_mount_hole_1",
        "nitehawk_mount_nut_pocket_0",
        "nitehawk_mount_nut_pocket_1",
    ]:
        recut_delta = _recut_delta(cage.leader, cage.get_named_cutter(cutter_name))
        assert recut_delta < 0.01
