"""Declarative dual z-axis assembly."""

from mege_ender_3v3ke_idex.designs.z_axis import create_positioned_z_axis_assembly
from shellforgepy.simple import *


def create_z_axis_assembly(*, frame, carriage_z_offset, context=None):
    """Create the positioned dual z-axis assembly in frame context."""

    del context

    positioned_z_axes, positioned_carriages = create_positioned_z_axis_assembly(
        frame=frame,
        carriage_z_offset=carriage_z_offset,
    )

    leader = PartCollector()
    follower_items = []
    non_production_items = []

    for side_name, z_axis in positioned_z_axes.items():
        leader = leader.fuse(z_axis.leader)
        non_production_items.append((f"{side_name}_profile", z_axis.leader))

        for name, follower in z_axis.get_named_follower_items():
            follower_items.append((f"{side_name}_{name}", follower))

        for name, part in z_axis.get_named_non_production_part_items():
            part_name = name if name == "top_bridge_profile" else f"{side_name}_{name}"
            non_production_items.append((part_name, part))

    for side_name, carriage in positioned_carriages.items():
        follower_items.append((f"{side_name}_carriage", carriage.leader))

        for name, follower in carriage.get_named_follower_items():
            follower_items.append((f"{side_name}_{name}", follower))

        for name, part in carriage.get_named_non_production_part_items():
            non_production_items.append((f"{side_name}_{name}", part))

    retval = LeaderFollowersCuttersPart(leader=leader)

    for name, follower in follower_items:
        retval.add_named_follower(follower, name)

    for name, part in non_production_items:
        retval.add_named_non_production_part(part, name)

    return retval