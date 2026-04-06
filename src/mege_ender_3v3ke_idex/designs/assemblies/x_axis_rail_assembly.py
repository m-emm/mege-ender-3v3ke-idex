"""Declarative x-axis rail assembly."""

from mege_ender_3v3ke_idex.designs.mgh_linear import (
    create_mgn12h_rail_with_carriages,
    mgn_12h_carriage_length,
)
from shellforgepy.metrics import record_length_metric
from shellforgepy.simple import *


def _get_profile_part(x_axis_lower_profile):
    return (
        x_axis_lower_profile.leader
        if hasattr(x_axis_lower_profile, "leader")
        else x_axis_lower_profile
    )


def create_x_axis_rail_assembly(
    *, x_axis_lower_profile, x_axis_rail_length, carriage_end_clearance
):
    """Create the x-axis rail and carriage references from the lower profile."""

    lower_axis_profile = _get_profile_part(x_axis_lower_profile)
    carriage_offset = (
        x_axis_rail_length / 2 - mgn_12h_carriage_length / 2 - carriage_end_clearance
    )

    record_length_metric("linear_rail", "MGN12", "x_axis_rail", x_axis_rail_length)

    rail_with_carriages = create_mgn12h_rail_with_carriages(
        length_mm=x_axis_rail_length,
        carriage_offsets=[-carriage_offset, carriage_offset],
    )
    rail_with_carriages = align(
        rail_with_carriages,
        lower_axis_profile,
        Alignment.CENTER,
        axes=[0, 1],
    )
    rail_with_carriages = align(
        rail_with_carriages,
        lower_axis_profile,
        Alignment.STACK_TOP,
    )
    return rail_with_carriages
