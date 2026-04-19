"""Declarative z-axis guide rod assembly."""

from shellforgepy.simple import *


def create_z_axis_guide_rod_assembly(
    *,
    z_axis_guide_rod_diameter,
    z_axis_guide_rod_length,
):
    """Create one z-axis guide rod at the origin for placement in YAML."""

    guide_rod = create_cylinder(z_axis_guide_rod_diameter / 2, z_axis_guide_rod_length)
    return guide_rod
