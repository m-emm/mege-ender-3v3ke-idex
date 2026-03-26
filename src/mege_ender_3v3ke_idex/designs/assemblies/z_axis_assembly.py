"""Declarative dual z-axis assembly."""

from mege_ender_3v3ke_idex.designs.idex_parameters import (
    z_axis_base_z_offset,
    z_axis_carriage_x_axis_connector_thickness,
    z_axis_x_offset_from_center,
    z_axis_y_offset,
)
from mege_ender_3v3ke_idex.designs.z_axis import (
    create_carriage,
    create_top_bridge_profile,
    create_z_axis,
)
from shellforgepy.simple import *


def create_z_axis_assembly(*, carriage_z_offset, context=None):
    """Create the dual z-axis assembly in canonical local coordinates."""

    del context

    positioned_z_axes = {}
    positioned_carriages = {}

    leader = PartCollector()
    follower_items = []
    non_production_items = []

    for side in [Alignment.LEFT, Alignment.RIGHT]:
        side_name = side.name.lower()

        z_axis = create_z_axis(side)
        z_axis = translate(0, 0, z_axis_base_z_offset)(z_axis)
        z_axis = translate(
            side.sign * z_axis_x_offset_from_center,
            z_axis_y_offset,
            0,
        )(z_axis)

        positioned_z_axes[side_name] = z_axis

        carriage = create_carriage(
            z_axis.get_named_non_production_part("guide_rod"),
            z_axis.get_named_non_production_part("threaded_rod"),
            z_axis,
        )
        carriage = translate(0, 0, carriage_z_offset)(carriage)
        positioned_carriages[side_name] = carriage

        leader = leader.fuse(z_axis.leader)
        non_production_items.append((f"{side_name}_profile", z_axis.leader))

        for name, follower in z_axis.get_named_follower_items():
            follower_items.append((f"{side_name}_{name}", follower))

        for name, part in z_axis.get_named_non_production_part_items():
            part_name = name if name == "top_bridge_profile" else f"{side_name}_{name}"
            non_production_items.append((part_name, part))

    top_bridge_profile = create_top_bridge_profile(positioned_z_axes)
    non_production_items.append(("top_bridge_profile", top_bridge_profile))

    carriages_fused = PartCollector()
    for side_name, carriage in positioned_carriages.items():
        follower_items.append((f"{side_name}_carriage", carriage.leader))
        carriages_fused = carriages_fused.fuse(carriage.leaders_followers_fused())

        for name, follower in carriage.get_named_follower_items():
            follower_items.append((f"{side_name}_{name}", follower))

        for name, part in carriage.get_named_non_production_part_items():
            non_production_items.append((f"{side_name}_{name}", part))

    non_production_items.append(("carriages_fused", carriages_fused))
    non_production_items.append(
        (
            "x_axis_alignment_reference",
            translate(0, 0, z_axis_carriage_x_axis_connector_thickness)(carriages_fused),
        )
    )

    retval = LeaderFollowersCuttersPart(leader=leader)

    for name, follower in follower_items:
        retval.add_named_follower(follower, name)

    for name, part in non_production_items:
        retval.add_named_non_production_part(part, name)

    return retval