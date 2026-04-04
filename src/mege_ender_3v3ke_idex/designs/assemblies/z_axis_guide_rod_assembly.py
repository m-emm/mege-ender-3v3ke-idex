"""Declarative z-axis guide rod assembly."""

from mege_ender_3v3ke_idex.designs.idex_parameters import (
    z_axis_guide_rod_diameter,
    z_axis_guide_rod_length,
    z_axis_guide_rod_profile_distance,
)
from shellforgepy.simple import *


def _get_profile_part(z_axis_profile):
    return (
        z_axis_profile.leader if hasattr(z_axis_profile, "leader") else z_axis_profile
    )


def create_z_axis_guide_rod_assembly(
    *, z_axis_profile, z_axis_base_z_offset, context=None
):
    """Create one guide rod against a placed Z profile."""

    del context

    profile = _get_profile_part(z_axis_profile)

    guide_rod = create_cylinder(z_axis_guide_rod_diameter / 2, z_axis_guide_rod_length)
    guide_rod = align(guide_rod, profile, Alignment.CENTER)
    guide_rod = align(guide_rod, profile, Alignment.STACK_FRONT)
    guide_rod = align(guide_rod, profile, Alignment.BOTTOM)
    guide_rod = translate(0, -z_axis_guide_rod_profile_distance, 0)(guide_rod)

    return translate(0, 0, z_axis_base_z_offset)(guide_rod)
