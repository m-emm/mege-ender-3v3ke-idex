"""Declarative standalone x-axis carriage assembly."""

from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12h_carriage


def create_x_axis_carriage_assembly(**_kwargs):
    """Create one standalone MGN12H carriage assembly."""

    carriage = create_mgn12h_carriage()

    if carriage.cutters:
        carriage.add_named_cutter(carriage.cutters[0], "mount_holes")

    return carriage
