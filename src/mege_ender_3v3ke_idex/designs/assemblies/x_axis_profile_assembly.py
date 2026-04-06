"""Declarative single x-axis profile assembly."""

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from shellforgepy.metrics import record_length_metric
from shellforgepy.simple import *


def create_x_axis_profile_assembly(
    *, profile_name, x_axis_profile_length, profile_z_offset
):
    """Create one x-axis profile in canonical local coordinates."""

    record_length_metric(
        "extrusion_profile",
        ExtrusionProfileType.PROFILE_2020.value,
        profile_name,
        x_axis_profile_length,
    )

    profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_2020,
        length_mm=x_axis_profile_length,
    )
    profile = rotate(90, axis=(0, 1, 0))(profile)
    profile = translate(0, 0, profile_z_offset)(profile)

    return LeaderFollowersCuttersPart(leader=profile)
