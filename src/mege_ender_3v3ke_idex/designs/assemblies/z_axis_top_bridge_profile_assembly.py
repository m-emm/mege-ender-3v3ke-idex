"""Declarative top bridge profile assembly for the dual z-axis."""

from mege_ender_3v3ke_idex.designs.z_axis_components import create_top_bridge_profile
from shellforgepy.simple import *


def _get_profile_part(profile):
    return profile.leader if hasattr(profile, "leader") else profile


def create_z_axis_top_bridge_profile_assembly(
    *,
    z_axis_profile_left,
    z_axis_profile_right,
):
    """Create the fixed top bridge profile from positioned z-axis profiles."""

    bridge = create_top_bridge_profile(
        {
            "left": _get_profile_part(z_axis_profile_left),
            "right": _get_profile_part(z_axis_profile_right),
        }
    )
    return LeaderFollowersCuttersPart(leader=bridge)
