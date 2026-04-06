"""Declarative z-axis threaded rod assembly."""

from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from shellforgepy.simple import *


def create_z_axis_threaded_rod_assembly(
    *,
    z_axis_threaded_rod_coupler_overlap,
    z_axis_threaded_rod_diameter,
    z_axis_threaded_rod_length,
    context=None,
):
    """Create one threaded rod with local motor-body/coupler placement references."""

    del context

    motor_reference = create_nema_composite()
    motor_body_reference = motor_reference.get_named_follower("body")
    coupler_reference = motor_reference.get_named_follower("coupler")

    threaded_rod = create_cylinder(
        z_axis_threaded_rod_diameter / 2,
        z_axis_threaded_rod_length,
    )
    threaded_rod = align(
        threaded_rod,
        coupler_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )
    threaded_rod = align(
        threaded_rod,
        coupler_reference,
        Alignment.STACK_TOP,
        stack_gap=-z_axis_threaded_rod_coupler_overlap,
    )

    retval = LeaderFollowersCuttersPart(leader=threaded_rod)
    retval.add_named_non_production_part(
        motor_body_reference,
        "motor_body_reference",
    )
    retval.add_named_non_production_part(
        coupler_reference,
        "coupler_reference",
    )

    return retval
