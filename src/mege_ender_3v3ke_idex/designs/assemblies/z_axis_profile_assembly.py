"""Declarative single z-axis profile assembly."""

from mege_ender_3v3ke_idex.designs.z_axis import create_z_axis_profile
from shellforgepy.simple import *


def _to_side_alignment(side):
    normalized_side = str(side).strip().lower()
    if normalized_side == "left":
        return Alignment.LEFT
    if normalized_side == "right":
        return Alignment.RIGHT
    raise ValueError(f"Unsupported z-axis side '{side}'")


def create_z_axis_profile_assembly(*, side, context=None):
    """Create a standalone z-axis profile in canonical local coordinates."""

    del context
    profile = create_z_axis_profile(
        side=_to_side_alignment(side),
        record_metrics=False,
    )
    return LeaderFollowersCuttersPart(leader=profile)
