"""Declarative x-axis rail assembly."""

from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12h_rail
from shellforgepy.metrics import record_length_metric


def create_x_axis_rail_assembly(*, x_axis_rail_length):
    """Create the standalone x-axis rail in canonical local coordinates."""

    record_length_metric("linear_rail", "MGN12", "x_axis_rail", x_axis_rail_length)

    return create_mgn12h_rail(length_mm=x_axis_rail_length)
