"""Declarative y-axis assembly."""

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.metrics_collector import (
    Material,
    record_length_metric,
    record_weight_metric,
)
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12ca_rail_with_carriages
from mege_ender_3v3ke_idex.designs.print_bed import Y_AXIS_MOVING_MASS_ASSEMBLY_ID
from shellforgepy.simple import *


def _record_y_axis_carriage_weight_metrics(y_axis):
    carriage_volume_mm3 = 0.0
    for name, part in y_axis.get_named_follower_items():
        if "carriage" not in name:
            continue
        carriage_volume_mm3 += get_volume(part)

    if carriage_volume_mm3 > 0:
        record_weight_metric(
            Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
            Material.STEEL,
            carriage_volume_mm3,
            part_id="mgn12ca_carriages",
        )


def _get_y_axis_carriages_fused(y_axis):
    y_axis_carriages = PartCollector()
    for name, follower in y_axis.get_named_follower_items():
        if "carriage" not in name:
            continue
        y_axis_carriages = y_axis_carriages.fuse(follower)
    return y_axis_carriages


def create_y_axis_assembly(
    *,
    y_axis_rail_spacing,
    y_axis_rail_length,
    y_axis_profile_length,
    y_axis_carriage_spacing,
    mgn_12ca_carriage_length,
    record_metrics=False,
    context=None,
):
    """Create the y-axis assembly in a canonical local coordinate system."""

    del context

    rails = []
    for side_sign in (-1, 1):
        rail_side_name = "left" if side_sign == -1 else "right"

        if record_metrics:
            record_length_metric(
                "extrusion_profile",
                ExtrusionProfileType.PROFILE_2020.value,
                f"y_axis_profile_{rail_side_name}",
                y_axis_profile_length,
            )

        profile = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_2020,
            length_mm=y_axis_profile_length,
        )
        profile = rotate(90, axis=(1, 0, 0))(profile)
        profile = align(profile, None, Alignment.CENTER)
        profile = translate(side_sign * y_axis_rail_spacing / 2, 0, 0)(profile)

        if record_metrics:
            record_length_metric(
                "linear_rail",
                "MGN12",
                f"y_axis_rail_{rail_side_name}",
                y_axis_rail_length,
            )

        rail = create_mgn12ca_rail_with_carriages(
            y_axis_rail_length,
            carriage_offsets=[
                -y_axis_rail_length / 2 + mgn_12ca_carriage_length / 2,
                -y_axis_rail_length / 2
                + y_axis_carriage_spacing
                + mgn_12ca_carriage_length / 2,
            ],
            carriage_names=["carriage_front", "carriage_back"],
        )
        rail = rotate(90)(rail)
        rail = rail.prefixed_copy(f"rail_{rail_side_name}")
        rail.rename_follower(
            f"rail_{rail_side_name}_carriage_front",
            f"carriage_front_carriage_{rail_side_name}",
        )
        rail.rename_follower(
            f"rail_{rail_side_name}_carriage_back",
            f"carriage_back_carriage_{rail_side_name}",
        )
        rail = align(rail, profile, Alignment.CENTER)
        rail = align(rail, profile, Alignment.STACK_TOP)
        rail.add_named_non_production_part(profile, f"profile_{rail_side_name}")

        rails.append(rail)

    y_axis = rails[0].fuse(rails[1])
    y_axis.add_named_non_production_part(
        _get_y_axis_carriages_fused(y_axis),
        "carriages_fused",
    )

    if record_metrics:
        _record_y_axis_carriage_weight_metrics(y_axis)

    return y_axis
