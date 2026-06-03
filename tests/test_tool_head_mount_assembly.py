from assembly_defaults import DEFAULTS, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.sprite_extruder_assembly import (
    create_sprite_extruder_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.tool_head_mount_assembly import (
    _create_sprite_mount_hole_guides,
    create_tool_head_mount_assembly,
)
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.simple import create_box, get_volume

TOOL_HEAD_MOUNT_TOP_BOX_WALL = 2
TOOL_HEAD_MOUNT_TOP_BOX_HEIGHT = 8
TOOL_HEAD_MOUNT_BELT_CLAMP_THICKNESS = 7
TOOL_HEAD_MOUNT_EXTRUDER_CUTOUT_CARRIAGE_GAP = 4
TOOL_HEAD_MOUNT_PLATE_CARRIAGE_CLEARANCE = 4
TOOL_HEAD_MOUNT_Y_EXTENSION = DEFAULTS["tool_head_mount_side_plate_depth"] + 1


def _build_mount(drive_position):
    carriage = LeaderFollowersCuttersPart(create_box(34.7, 27, 8))
    x_axis_belt_carriage = LeaderFollowersCuttersPart(create_box(70, 12, 14))
    sprite_extruder = create_sprite_extruder_assembly(
        **assembly_kwargs(create_sprite_extruder_assembly)
    )

    return create_tool_head_mount_assembly(
        **assembly_kwargs(
            create_tool_head_mount_assembly,
            carriage=carriage,
            sprite_extruder=sprite_extruder,
            x_axis_belt_carriage=x_axis_belt_carriage,
            tool_head_mount_belt_clamp_thickness=(
                TOOL_HEAD_MOUNT_BELT_CLAMP_THICKNESS
            ),
            tool_head_mount_extruder_cutout_carriage_gap=(
                TOOL_HEAD_MOUNT_EXTRUDER_CUTOUT_CARRIAGE_GAP
            ),
            tool_head_mount_plate_carriage_clearance=(
                TOOL_HEAD_MOUNT_PLATE_CARRIAGE_CLEARANCE
            ),
            tool_head_mount_sprite_mount_screw_length=10,
            tool_head_mount_y_extension=TOOL_HEAD_MOUNT_Y_EXTENSION,
            drive_position=drive_position,
            tool_head_mount_top_box_wall=TOOL_HEAD_MOUNT_TOP_BOX_WALL,
            tool_head_mount_top_box_height=TOOL_HEAD_MOUNT_TOP_BOX_HEIGHT,
        )
    )


def test_tool_head_mount_exposes_sprite_mount_screws_and_holes_for_top_and_bottom():
    for drive_position in ["bottom", "top"]:
        mount = _build_mount(drive_position)

        mount.get_non_production_part_by_name("sprite_mount_screw_left")
        mount.get_non_production_part_by_name("sprite_mount_screw_right")

        mount_hole_cutter = mount.get_named_cutter("mount_hole_cutter")
        hole_guides = _create_sprite_mount_hole_guides(
            mount_hole_cutter=mount_hole_cutter,
        )

        assert [name for name, _ in hole_guides] == ["left", "right"]

        leader_volume = get_volume(mount.leader)
        for _, hole_guide in hole_guides:
            recut_delta = leader_volume - get_volume(mount.leader.cut(hole_guide))
            assert recut_delta < 0.01
