"""Declarative single-side z-axis core assembly."""

from mege_ender_3v3ke_idex.designs.assemblies.z_axis_assembly_common import (
    coerce_side_alignment,
)
from mege_ender_3v3ke_idex.designs.z_axis import create_z_axis_core_from_profile


def create_z_axis_core_assembly(*, z_axis_profile, side, context=None):
    """Create the rods, motor mount, and lower supports for one z-axis side."""

    del context

    return create_z_axis_core_from_profile(
        coerce_side_alignment(side),
        z_axis_profile,
    )
