"""Angled 2020 profile for a rear Z-axis strut."""

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from shellforgepy.metrics import record_length_metric
from shellforgepy.simple import *


def create_z_axis_back_strut_assembly(
    *, z_axis_back_strut_length, z_axis_back_strut_angle
):
    """Create a 2020 profile tilted out of vertical around the X axis."""

    record_length_metric(
        "extrusion_profile",
        ExtrusionProfileType.PROFILE_2020.value,
        "z_axis_back_strut",
        z_axis_back_strut_length,
    )

    profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_2020,
        length_mm=z_axis_back_strut_length,
    )
    profile = rotate(z_axis_back_strut_angle, axis=(1, 0, 0))(profile)
    return LeaderFollowersCuttersPart(leader=profile)
