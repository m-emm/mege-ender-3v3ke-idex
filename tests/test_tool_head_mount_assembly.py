from mege_ender_3v3ke_idex.designs import idex_parameters
from mege_ender_3v3ke_idex.designs.assemblies.tool_head_mount_assembly import (
    _create_sprite_mount_hole_guides,
    create_tool_head_mount_assembly,
)
from mege_ender_3v3ke_idex.designs.sprite_extruder import (
    BIG_THING,
    create_sprite_extruder,
    extruder_mount_screw_size,
)
from shellforgepy.simple import get_volume


def _build_mount(drive_position):
    return create_tool_head_mount_assembly(
        sprite_extruder=create_sprite_extruder(),
        extruder_mount_screw_size=extruder_mount_screw_size,
        x_axis_profile_length=idex_parameters.x_axis_profile_length,
        x_axis_profile_pitch=idex_parameters.x_axis_profile_pitch,
        tool_head_mount_base_plate_height=idex_parameters.tool_head_mount_base_plate_height,
        tool_head_mount_base_plate_thickness=idex_parameters.tool_head_mount_base_plate_thickness,
        tool_head_mount_belt_clamp_base_thickness=idex_parameters.tool_head_mount_belt_clamp_base_thickness,
        tool_head_mount_belt_clamp_length=idex_parameters.tool_head_mount_belt_clamp_length,
        tool_head_mount_belt_clamp_thickness=idex_parameters.tool_head_mount_belt_clamp_thickness,
        tool_head_mount_belt_clamp_y_offset=idex_parameters.tool_head_mount_belt_clamp_y_offset,
        tool_head_mount_belt_deflector_belt_clearance=idex_parameters.tool_head_mount_belt_deflector_belt_clearance,
        tool_head_mount_belt_deflector_cage_thickness=idex_parameters.tool_head_mount_belt_deflector_cage_thickness,
        tool_head_mount_belt_deflector_into_profile_distance=idex_parameters.tool_head_mount_belt_deflector_into_profile_distance,
        tool_head_mount_belt_deflector_thickness=idex_parameters.tool_head_mount_belt_deflector_thickness,
        tool_head_mount_belt_path_cutter_clearance=idex_parameters.tool_head_mount_belt_path_cutter_clearance,
        tool_head_mount_carriage_mount_plate_fillet_radius=idex_parameters.tool_head_mount_carriage_mount_plate_fillet_radius,
        tool_head_mount_carriage_mount_plate_thickness=idex_parameters.tool_head_mount_carriage_mount_plate_thickness,
        tool_head_mount_carriage_mount_plate_width=idex_parameters.tool_head_mount_carriage_mount_plate_width,
        tool_head_mount_clamp_base_cutter_clearance=idex_parameters.tool_head_mount_clamp_base_cutter_clearance,
        tool_head_mount_extruder_cutout_carriage_gap=idex_parameters.tool_head_mount_extruder_cutout_carriage_gap,
        tool_head_mount_extruder_cutout_fillet_radius=idex_parameters.tool_head_mount_extruder_cutout_fillet_radius,
        tool_head_mount_extruder_cutout_width=idex_parameters.tool_head_mount_extruder_cutout_width,
        tool_head_mount_plate_carriage_clearance=idex_parameters.tool_head_mount_plate_carriage_clearance,
        tool_head_mount_side_plate_depth=idex_parameters.tool_head_mount_side_plate_depth,
        tool_head_mount_side_plate_height=idex_parameters.tool_head_mount_side_plate_height,
        tool_head_mount_side_plate_thickness=idex_parameters.tool_head_mount_side_plate_thickness,
        tool_head_mount_side_stiffener_thickness=idex_parameters.tool_head_mount_side_stiffener_thickness,
        tool_head_mount_sprite_mount_screw_length=10,
        tool_head_mount_tool_head_base_plate_clearance=idex_parameters.tool_head_mount_tool_head_base_plate_clearance,
        tool_head_mount_tool_head_x_offset=idex_parameters.tool_head_mount_tool_head_x_offset,
        tool_head_mount_tool_head_z_offset=idex_parameters.tool_head_mount_tool_head_z_offset,
        tool_head_mount_x_offset=idex_parameters.tool_head_mount_x_offset,
        tool_head_mount_y_extension=idex_parameters.tool_head_mount_y_extension,
        drive_position=drive_position,
        BIG_THING=BIG_THING,
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