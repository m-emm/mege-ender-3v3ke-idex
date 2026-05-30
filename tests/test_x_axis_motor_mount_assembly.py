from mege_ender_3v3ke_idex.designs import idex_parameters
from mege_ender_3v3ke_idex.designs.assemblies.x_axis_motor_mount_assembly import (
    create_x_axis_motor_mount_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.x_axis_profile_assembly import (
    create_x_axis_profile_assembly,
)
from shellforgepy.simple import get_volume


def _build_profiles():
    lower = create_x_axis_profile_assembly(
        profile_name="x_axis_lower_profile",
        x_axis_profile_length=idex_parameters.x_axis_profile_length,
    )
    top = create_x_axis_profile_assembly(
        profile_name="x_axis_top_profile",
        x_axis_profile_length=idex_parameters.x_axis_profile_length,
    )
    return lower, top


def test_x_axis_motor_mount_assembly_exposes_expected_parts_for_top_and_bottom():
    lower, top = _build_profiles()
    profiles_by_position = {
        "bottom": lower,
        "top": top,
    }

    for profile_position in ("bottom", "top"):
        assembly = create_x_axis_motor_mount_assembly(
            profile_to_align=profiles_by_position[profile_position],
            profile_position=profile_position,
        )

        assert get_volume(assembly.leader) > 0

        assembly.get_follower_part_by_name("mount_shield")
        assembly.get_follower_part_by_name("mount_plate")
        assembly.get_follower_part_by_name("mount_flange")
        assembly.get_follower_part_by_name("motor_bridge")
        assembly.get_follower_part_by_name("mount_plate_connector")

        assembly.get_non_production_part_by_name("axis_holding_counter_flange")
        assembly.get_non_production_part_by_name("axle")
        assembly.get_non_production_part_by_name("idlers")
        assembly.get_non_production_part_by_name("motor_visual")
        assembly.get_non_production_part_by_name("profile_to_align")
