"""Declarative z-axis rods assembly."""

from mege_ender_3v3ke_idex.designs.idex_parameters import (
    motor_mount_axle_clearance,
    motor_mount_boss_clearance,
    motor_mount_boss_clearance_z,
    z_axis_guide_rod_diameter,
    z_axis_guide_rod_length,
    z_axis_guide_rod_profile_distance,
    z_axis_thraded_rod_z_offset,
    z_axis_threaded_rod_diameter,
    z_axis_threaded_rod_length,
    z_axis_threaded_rod_profile_distance,
)
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from shellforgepy.simple import *


def _get_profile_part(z_axis_profile):
    return (
        z_axis_profile.leader if hasattr(z_axis_profile, "leader") else z_axis_profile
    )


def create_z_axis_rods_assembly(*, z_axis_profile, z_axis_base_z_offset, context=None):
    """Create one guide rod and one threaded rod against a placed Z profile."""

    del context

    profile = _get_profile_part(z_axis_profile)

    guide_rod = create_cylinder(z_axis_guide_rod_diameter / 2, z_axis_guide_rod_length)
    guide_rod = align(guide_rod, profile, Alignment.CENTER)
    guide_rod = align(guide_rod, profile, Alignment.STACK_FRONT)
    guide_rod = align(guide_rod, profile, Alignment.BOTTOM)
    guide_rod = translate(0, -z_axis_guide_rod_profile_distance, 0)(guide_rod)

    threaded_rod = create_cylinder(
        z_axis_threaded_rod_diameter / 2,
        z_axis_threaded_rod_length,
    )
    threaded_rod = align(threaded_rod, guide_rod, Alignment.CENTER)
    threaded_rod = align(threaded_rod, guide_rod, Alignment.BOTTOM)
    threaded_rod = align(
        threaded_rod,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_threaded_rod_profile_distance,
    )
    threaded_rod = translate(0, 0, z_axis_thraded_rod_z_offset)(threaded_rod)

    retval = LeaderFollowersCuttersPart(leader=guide_rod)
    retval.add_named_non_production_part(threaded_rod, "threaded_rod")

    # Preserve the current rod-to-coupler relationship without yet splitting
    # motor placement into its own assembly.
    motor = create_nema_composite(
        axle_clearance=motor_mount_axle_clearance,
        boss_clearance=motor_mount_boss_clearance,
        boss_clearance_z=motor_mount_boss_clearance_z,
    )
    motor = align(motor, threaded_rod, Alignment.CENTER)
    motor = align(motor, profile, Alignment.BOTTOM)

    coupler = motor.get_named_follower("coupler")
    threaded_rod_part = retval.get_named_non_production_part("threaded_rod")
    coupler_aligner = align_translation(
        threaded_rod_part,
        coupler,
        Alignment.STACK_TOP,
        stack_gap=0,
    )

    retval = coupler_aligner(retval)
    return translate(0, 0, z_axis_base_z_offset)(retval)
