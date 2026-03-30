"""Declarative single-side z-axis carriage assembly."""

from mege_ender_3v3ke_idex.designs.idex_parameters import (
    z_axis_carriage_x_axis_connector_thickness,
)
from mege_ender_3v3ke_idex.designs.z_axis import create_carriage
from shellforgepy.simple import translate


def create_z_axis_carriage_assembly(*, guide_rod, threaded_rod, context=None):
    """Create the carriage in its canonical local Z position."""

    del context

    carriage = create_carriage(guide_rod, threaded_rod)

    carriage_fused = carriage.leaders_followers_fused()
    carriage.add_named_non_production_part(carriage_fused, "carriage_fused")
    carriage.add_named_non_production_part(
        translate(0, 0, z_axis_carriage_x_axis_connector_thickness)(carriage_fused),
        "x_axis_alignment_reference",
    )

    return carriage
