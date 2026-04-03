"""Declarative single-side z-axis assembly."""

from mege_ender_3v3ke_idex.designs.idex_parameters import (
    z_axis_carriage_x_axis_connector_thickness,
)
from mege_ender_3v3ke_idex.designs.z_axis import create_carriage, create_top_mount
from shellforgepy.simple import *


def _get_profile_part(z_axis_profile):
    return (
        z_axis_profile.leader if hasattr(z_axis_profile, "leader") else z_axis_profile
    )


def _get_rods_parts(z_axis_rods):
    guide_rod = z_axis_rods.leader if hasattr(z_axis_rods, "leader") else z_axis_rods
    threaded_rod = z_axis_rods.get_named_non_production_part("threaded_rod")
    return guide_rod, threaded_rod


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
    z_axis_rods,
    z_axis_bottom_support,
    z_axis_motor_mount,
    carriage_z_offset,
    z_axis_base_z_offset,
    context=None,
):
    """Create one z-axis side against already built subassemblies."""

    del context

    profile = _get_profile_part(z_axis_profile)
    guide_rod, threaded_rod = _get_rods_parts(z_axis_rods)

    translated_rods = translate(0, 0, z_axis_base_z_offset)(z_axis_rods)
    bottom_support = translate(0, 0, z_axis_base_z_offset)(z_axis_bottom_support)
    motor_mount = translate(0, 0, z_axis_base_z_offset)(z_axis_motor_mount)

    top_mount = create_top_mount(guide_rod, threaded_rod, profile)
    top_mount = translate(0, 0, z_axis_base_z_offset)(top_mount)

    carriage = create_carriage(guide_rod, threaded_rod, profile)
    carriage = translate(0, 0, z_axis_base_z_offset + carriage_z_offset)(carriage)

    leader = _fuse_printable_parts(bottom_support, motor_mount, top_mount, carriage)
    retval = LeaderFollowersCuttersPart(leader=leader)

    _copy_followers_to_followers(
        retval,
        bottom_support,
        leader_name="pillow_bearing_mount_plate",
    )
    _copy_followers_to_followers(
        retval,
        motor_mount,
        leader_name="mount_plate_back",
    )

    retval.add_named_follower(top_mount.leader, "top_mount")
    retval.add_named_follower(
        top_mount.get_named_follower("top_mount_clamp"),
        "top_mount_clamp",
    )

    retval.add_named_follower(carriage.leader, "carriage")
    for name, follower in carriage.get_named_follower_items():
        retval.add_named_follower(follower, name)

    retval.add_named_non_production_part(translated_rods.leader, "guide_rod")
    retval.add_named_non_production_part(
        translated_rods.get_named_non_production_part("threaded_rod"),
        "threaded_rod",
    )
    _copy_non_production_parts(retval, bottom_support)
    _copy_non_production_parts(retval, motor_mount)
    _copy_non_production_parts(retval, top_mount, prefix="top_mount_")
    _copy_non_production_parts(retval, carriage)

    carriage_fused = carriage.leaders_followers_fused()
    retval.add_named_non_production_part(carriage_fused, "carriage_fused")
    retval.add_named_non_production_part(
        translate(0, 0, z_axis_carriage_x_axis_connector_thickness)(carriage_fused),
        "x_axis_alignment_reference",
    )

    return retval
