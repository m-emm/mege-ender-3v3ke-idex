from assembly_defaults import assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.tool_head_mount_machined_assembly import (
    create_tool_head_mount_machined_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.x_axis_carriage_assembly import (
    create_x_axis_carriage_assembly,
)
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.simple import create_box, get_volume


def test_tool_head_mount_machined_top_is_carriage_plate_with_mount_holes():
    carriage = create_x_axis_carriage_assembly()
    sprite_extruder = LeaderFollowersCuttersPart(create_box(10, 10, 10))
    x_axis_belt_carriage = LeaderFollowersCuttersPart(create_box(10, 10, 10))

    mount = create_tool_head_mount_machined_assembly(
        **assembly_kwargs(
            create_tool_head_mount_machined_assembly,
            carriage=carriage,
            sprite_extruder=sprite_extruder,
            x_axis_belt_carriage=x_axis_belt_carriage,
            drive_position="top",
        )
    )

    assert isinstance(mount, LeaderFollowersCuttersPart)

    leader_volume = get_volume(mount.leader)
    assert leader_volume > 0

    mount_holes = carriage.get_named_cutter("mount_holes")
    recut_delta = leader_volume - get_volume(mount.leader.cut(mount_holes))
    assert abs(recut_delta) < 0.01
