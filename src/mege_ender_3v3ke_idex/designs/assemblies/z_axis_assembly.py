"""Declarative dual z-axis assembly."""

from shellforgepy.simple import *


def create_z_axis_assembly(
    *,
    left_z_axis_profile,
    right_z_axis_profile,
    left_z_axis,
    right_z_axis,
):
    """Aggregate the split left/right z-axis assemblies."""

    del left_z_axis_profile
    del right_z_axis_profile
    side_assemblies = {
        "left": left_z_axis,
        "right": right_z_axis,
    }

    x_axis_alignment_reference = PartCollector()
    fixed_hardware = PartCollector()

    for z_axis in side_assemblies.values():
        fixed_hardware = fixed_hardware.fuse(z_axis.leader)

    retval = LeaderFollowersCuttersPart(leader=fixed_hardware)

    for side_name, z_axis in side_assemblies.items():
        for name, follower in z_axis.get_named_follower_items():
            retval.add_named_follower(follower, f"{side_name}_{name}")

        for name, part in z_axis.get_named_non_production_part_items():
            if name == "x_axis_alignment_reference":
                continue
            retval.add_named_non_production_part(part, f"{side_name}_{name}")

        x_axis_alignment_reference = x_axis_alignment_reference.fuse(
            z_axis.get_named_non_production_part("x_axis_alignment_reference")
        )

    retval.add_named_non_production_part(
        x_axis_alignment_reference,
        "x_axis_alignment_reference",
    )

    return retval
