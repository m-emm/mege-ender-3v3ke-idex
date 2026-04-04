"""Declarative z-axis threaded rod assembly."""

from shellforgepy.simple import *


def _get_profile_part(z_axis_profile):
    return (
        z_axis_profile.leader if hasattr(z_axis_profile, "leader") else z_axis_profile
    )


def _get_motor_mount_coupler(z_axis_motor_mount):
    return z_axis_motor_mount.get_named_non_production_part("coupler")


def create_z_axis_threaded_rod_assembly(
    *,
    z_axis_profile,
    z_axis_motor_mount,
    z_axis_threaded_rod_coupler_overlap,
    z_axis_threaded_rod_diameter,
    z_axis_threaded_rod_length,
    z_axis_threaded_rod_profile_distance,
    context=None,
):
    """Create one threaded rod from the actual motor mount coupler placement."""

    del context

    profile = _get_profile_part(z_axis_profile)
    coupler = _get_motor_mount_coupler(z_axis_motor_mount)

    threaded_rod = create_cylinder(
        z_axis_threaded_rod_diameter / 2,
        z_axis_threaded_rod_length,
    )
    threaded_rod = align(threaded_rod, coupler, Alignment.CENTER, axes=[0])
    threaded_rod = align(
        threaded_rod,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_threaded_rod_profile_distance,
    )
    threaded_rod = align(
        threaded_rod,
        coupler,
        Alignment.STACK_TOP,
        stack_gap=-z_axis_threaded_rod_coupler_overlap,
    )

    return threaded_rod
