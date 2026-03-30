"""Declarative single z-axis profile assembly."""

from mege_ender_3v3ke_idex.designs.assemblies.z_axis_assembly_common import (
    coerce_side_alignment,
)
from mege_ender_3v3ke_idex.designs.z_axis import create_z_axis_profile
from shellforgepy.simple import *


def create_z_axis_profile_assembly(*, side, context=None):
    """Create a standalone z-axis profile in canonical local coordinates."""

    del context
    profile = create_z_axis_profile(
        side=coerce_side_alignment(side),
        record_metrics=False,
    )
    return LeaderFollowersCuttersPart(leader=profile)
