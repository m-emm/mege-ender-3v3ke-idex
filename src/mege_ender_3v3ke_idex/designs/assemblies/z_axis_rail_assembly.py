"""Declarative Z-axis MGN12 rail assembly."""

from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12h_rail_with_carriages
from shellforgepy.metrics import record_length_metric


def create_z_axis_rail_assembly(*, z_axis_rail_length):
    """Create one MGN12 rail with bottom and top MGN12H carriages."""

    record_length_metric(
        "linear_rail",
        "MGN12",
        "z_axis_rail",
        z_axis_rail_length,
    )

    return create_mgn12h_rail_with_carriages(
        length_mm=z_axis_rail_length,
        carriage_offsets=[224, 178],
        carriage_names=["bottom_carriage", "top_carriage"],
    )
