"""Declarative single-side z-axis assembly."""

from mege_ender_3v3ke_idex.designs.idex_parameters import (
    z_axis_carriage_x_axis_connector_thickness,
)
from mege_ender_3v3ke_idex.designs.z_axis import (
    create_carriage,
    create_z_axis_from_profile,
)
from shellforgepy.simple import *


def _to_side_alignment(side):
    normalized_side = str(side).strip().lower()
    if normalized_side == "left":
        return Alignment.LEFT
    if normalized_side == "right":
        return Alignment.RIGHT
    raise ValueError(f"Unsupported z-axis side '{side}'")


def _get_profile_part(z_axis_profile):
    return (
        z_axis_profile.leader if hasattr(z_axis_profile, "leader") else z_axis_profile
    )


def _fuse_named_followers(part):
    fused = PartCollector()
    for _, follower in part.get_named_follower_items():
        fused = fused.fuse(follower)
    return fused


def create_z_axis_side_assembly(
    *,
    z_axis_profile,
    side,
    carriage_z_offset,
    z_axis_base_z_offset,
    context=None,
):
    """Create one z-axis side against an already placed profile assembly."""

    del context

    side_alignment = _to_side_alignment(side)
    profile = _get_profile_part(z_axis_profile)

    z_axis = create_z_axis_from_profile(side_alignment, profile)
    z_axis = translate(0, 0, z_axis_base_z_offset)(z_axis)

    carriage = create_carriage(
        z_axis.get_named_non_production_part("guide_rod"),
        z_axis.get_named_non_production_part("threaded_rod"),
        z_axis,
    )
    carriage = translate(0, 0, carriage_z_offset)(carriage)

    leader = _fuse_named_followers(z_axis)
    leader = leader.fuse(carriage.leader)

    retval = LeaderFollowersCuttersPart(leader=leader)

    for name, follower in z_axis.get_named_follower_items():
        retval.add_named_follower(follower, name)

    retval.add_named_follower(carriage.leader, "carriage")
    for name, follower in carriage.get_named_follower_items():
        retval.add_named_follower(follower, name)

    for name, part in z_axis.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)

    for name, part in carriage.get_named_non_production_part_items():
        retval.add_named_non_production_part(part, name)

    carriage_fused = carriage.leaders_followers_fused()
    retval.add_named_non_production_part(carriage_fused, "carriage_fused")
    retval.add_named_non_production_part(
        translate(0, 0, z_axis_carriage_x_axis_connector_thickness)(carriage_fused),
        "x_axis_alignment_reference",
    )

    return retval
