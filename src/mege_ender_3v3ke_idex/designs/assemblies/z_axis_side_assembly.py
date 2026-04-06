"""Declarative single-side z-axis assembly."""

from shellforgepy.simple import *


def _get_rod_part(rod):
    return rod.leader if hasattr(rod, "leader") else rod


def _fuse_printable_parts(*parts):
    fused = PartCollector()
    for part in parts:
        fused = fused.fuse(part.leader)
        for _, follower in part.get_named_follower_items():
            fused = fused.fuse(follower)
    return fused


def _copy_followers_to_followers(target, source, *, leader_name=None):
    if leader_name is not None:
        target.add_named_follower(source.leader, leader_name)

    for name, follower in source.get_named_follower_items():
        target.add_named_follower(follower, name)


def _copy_non_production_parts(target, source, *, prefix=""):
    for name, part in source.get_named_non_production_part_items():
        target.add_named_non_production_part(part, f"{prefix}{name}")


def create_z_axis_side_assembly(
    *,
    z_axis_profile,
    z_axis_guide_rod,
    z_axis_threaded_rod,
    z_axis_bottom_support,
    z_axis_motor_mount,
    z_axis_guide_rod_top_mount,
    z_axis_carriage,
):
    """Create one z-axis side against already built subassemblies."""
    del z_axis_profile

    guide_rod = _get_rod_part(z_axis_guide_rod)
    threaded_rod = _get_rod_part(z_axis_threaded_rod)

    leader = _fuse_printable_parts(
        z_axis_bottom_support,
        z_axis_motor_mount,
        z_axis_guide_rod_top_mount,
    )
    retval = LeaderFollowersCuttersPart(leader=leader)

    _copy_followers_to_followers(
        retval,
        z_axis_bottom_support,
        leader_name="pillow_bearing_mount_plate",
    )
    _copy_followers_to_followers(
        retval,
        z_axis_motor_mount,
        leader_name="mount_plate_back",
    )
    _copy_followers_to_followers(
        retval,
        z_axis_guide_rod_top_mount,
        leader_name="top_mount",
    )
    _copy_followers_to_followers(
        retval,
        z_axis_carriage,
        leader_name="carriage",
    )

    retval.add_named_non_production_part(guide_rod, "guide_rod")
    retval.add_named_non_production_part(
        threaded_rod,
        "threaded_rod",
    )
    _copy_non_production_parts(retval, z_axis_bottom_support)
    _copy_non_production_parts(retval, z_axis_motor_mount)
    _copy_non_production_parts(
        retval,
        z_axis_guide_rod_top_mount,
        prefix="top_mount_",
    )
    _copy_non_production_parts(retval, z_axis_carriage)

    return retval
