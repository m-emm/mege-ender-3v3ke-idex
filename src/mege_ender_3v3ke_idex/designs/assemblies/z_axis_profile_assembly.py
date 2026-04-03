"""Declarative single z-axis profile assembly."""

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import z_axis_profile_length
from shellforgepy.metrics import record_length_metric
from shellforgepy.simple import *


def _normalize_side(side):
    normalized_side = str(side).strip().lower()
    if normalized_side == "left":
        return normalized_side
    if normalized_side == "right":
        return normalized_side
    raise ValueError(f"Unsupported z-axis side '{side}'")


def create_z_axis_profile_assembly(*, side, context=None):
    """Create a standalone z-axis profile in canonical local coordinates."""

    del context

    normalized_side = _normalize_side(side)
    record_length_metric(
        "extrusion_profile",
        ExtrusionProfileType.PROFILE_4040.value,
        f"{normalized_side}_z_axis_profile",
        z_axis_profile_length,
    )

    profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_4040,
        length_mm=z_axis_profile_length,
    )
    return LeaderFollowersCuttersPart(leader=profile)
