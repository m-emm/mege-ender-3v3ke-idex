"""Declarative single-side z-axis assembly."""

from shellforgepy.simple import *


def create_z_axis_side_assembly(
    *,
    z_axis_core,
    z_axis_top_mount,
    z_axis_carriage,
    context=None,
):
    """Expose one z-axis side from its modular sub-assemblies."""

    del context

    retval = LeaderFollowersCuttersPart(leader=z_axis_core.leader)

    for name, follower in z_axis_core.get_named_follower_items():
        retval.add_named_follower(follower, name)

    for name, part in z_axis_core.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)

    retval.add_named_follower(z_axis_top_mount.leader, "top_mount")
    for name, follower in z_axis_top_mount.get_named_follower_items():
        retval.add_named_follower(follower, name)
    for name, part in z_axis_top_mount.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, f"top_mount_{name}")

    retval.add_named_follower(z_axis_carriage.leader, "carriage")
    for name, follower in z_axis_carriage.get_named_follower_items():
        retval.add_named_follower(follower, name)
    for name, part in z_axis_carriage.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)

    return retval
