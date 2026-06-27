"""Lean context scene for the z-axis top profile gussets."""

from shellforgepy.simple import *


def create_z_axis_top_profile_gussets_assembly(**_kwargs):
    """Return a tiny placeholder; visualization is sourced from dependencies."""

    return LeaderFollowersCuttersPart(leader=create_box(0.1, 0.1, 0.1))
