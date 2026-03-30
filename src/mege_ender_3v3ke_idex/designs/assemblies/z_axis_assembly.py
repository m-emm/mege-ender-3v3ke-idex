"""Declarative dual z-axis assembly."""

from mege_ender_3v3ke_idex.designs.z_axis import create_top_bridge_profile
from shellforgepy.simple import *


def create_z_axis_assembly(
    *,
    left_z_axis_profile,
    right_z_axis_profile,
    left_z_axis,
    right_z_axis,
    context=None,
):
    """Aggregate the split left/right z-axis assemblies."""

    del context

    profiles = {
        "left": left_z_axis_profile,
        "right": right_z_axis_profile,
    }
    side_assemblies = {
        "left": left_z_axis,
        "right": right_z_axis,
    }

    retval = LeaderFollowersCuttersPart(
        leader=left_z_axis_profile.fuse(right_z_axis_profile)
    )

    retval.add_named_non_production_part(
        create_top_bridge_profile(profiles),
        "top_bridge_profile",
    )

    carriages_fused = PartCollector()
    x_axis_alignment_reference = PartCollector()

    for side_name, z_axis in side_assemblies.items():
        for name, follower in z_axis.get_named_follower_items():
            retval.add_named_follower(follower, f"{side_name}_{name}")

        for name, part in z_axis.get_named_non_production_part_items():
            if name in {"carriage_fused", "x_axis_alignment_reference"}:
                continue
            retval.add_named_non_production_part(part, f"{side_name}_{name}")

        carriages_fused = carriages_fused.fuse(
            z_axis.get_named_non_production_part("carriage_fused")
        )
        x_axis_alignment_reference = x_axis_alignment_reference.fuse(
            z_axis.get_named_non_production_part("x_axis_alignment_reference")
        )

    retval.add_named_non_production_part(carriages_fused, "carriages_fused")
    retval.add_named_non_production_part(
        x_axis_alignment_reference,
        "x_axis_alignment_reference",
    )

    return retval
