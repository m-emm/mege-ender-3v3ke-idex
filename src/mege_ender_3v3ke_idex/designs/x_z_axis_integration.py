"""
X Z Axis Integration

Usage:
    cd <project_root> && ./run.sh path/to/x_z_axis_integration.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/x_z_axis_integration.py
"""

import logging
import os

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.mgh_linear import (
    create_mgn12h_rail_with_carriages,
    mgn_12h_carriage_length,
)
from mege_ender_3v3ke_idex.designs.z_axis import (
    create_minimal_z_axis_reference,
    create_positioned_x_z_axis_assembly,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = {
    "filament": "FilamentPLAMegeMaster",
    "process_overrides": {
        "nozzle_diameter": "0.6",
        "layer_height": "0.2",
    },
}

X_AXIS_CARRIAGE_END_CLEARANCE = 3

PROFILE_COLOR = (0.84, 0.84, 0.86)
ROD_COLOR = (0.76, 0.82, 0.88)
X_AXIS_COLOR = (0.66, 0.82, 0.96)
X_AXIS_RAIL_COLOR = (0.74, 0.88, 0.94)
Z_CARRIAGE_COLOR = (0.98, 0.78, 0.62)
Z_CLAMP_COLOR = (0.95, 0.70, 0.72)
BEARING_COLOR = (0.82, 0.93, 0.78)


def create_x_axis_reference():
    lower_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_2020, length_mm=axis_profile_length
    )
    lower_axis_profile = rotate(90, axis=(0, 1, 0))(lower_axis_profile)

    top_axis_profile = translate(0, 0, x_axis_profile_pitch)(lower_axis_profile)

    carriage_offset = (
        x_axis_rail_length / 2
        - mgn_12h_carriage_length / 2
        - X_AXIS_CARRIAGE_END_CLEARANCE
    )

    rail_with_carriages = create_mgn12h_rail_with_carriages(
        length_mm=x_axis_rail_length,
        carriage_offsets=[-carriage_offset, carriage_offset],
    )
    rail_with_carriages = align(
        rail_with_carriages,
        lower_axis_profile,
        Alignment.CENTER,
        axes=[0, 1],
    )
    rail_with_carriages = align(
        rail_with_carriages, lower_axis_profile, Alignment.STACK_TOP
    )

    retval = LeaderFollowersCuttersPart(lower_axis_profile.fuse(top_axis_profile))
    retval.add_named_non_production_part(lower_axis_profile, "lower_axis_profile")
    retval.add_named_non_production_part(top_axis_profile, "top_axis_profile")
    retval.add_named_non_production_part(rail_with_carriages.leader, "rail")

    for carriage_name in ["carriage_1", "carriage_2"]:
        retval.add_named_non_production_part(
            rail_with_carriages.get_named_follower(carriage_name),
            carriage_name,
        )

    return retval


def create_x_z_axis_integration():
    x_axis_reference = create_x_axis_reference()
    positioned_z_axes, positioned_carriages, x_axis_reference = (
        create_positioned_x_z_axis_assembly(
            x_axis_reference,
            create_minimal_z_axis_reference,
        )
    )

    return positioned_z_axes, positioned_carriages, x_axis_reference


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    z_axis_references, carriages, x_axis_reference = create_x_z_axis_integration()

    for side_name, z_axis_reference in z_axis_references.items():
        parts.add(
            z_axis_reference.leader,
            f"{side_name}_z_axis_profile",
            flip=False,
            skip_in_production=True,
            color=PROFILE_COLOR,
        )
        parts.add(
            z_axis_reference.get_named_non_production_part("guide_rod"),
            f"{side_name}_guide_rod",
            flip=False,
            skip_in_production=True,
            color=ROD_COLOR,
        )
        parts.add(
            z_axis_reference.get_named_non_production_part("threaded_rod"),
            f"{side_name}_threaded_rod",
            flip=False,
            skip_in_production=True,
            color=ROD_COLOR,
        )

    z_animation = {f"z_axis": (0, 0, 200)}

    for side_name, carriage in carriages.items():
        parts.add(
            carriage.leader,
            f"{side_name}_z_axis_carriage",
            flip=False,
            skip_in_production=True,
            color=Z_CARRIAGE_COLOR,
            animation=z_animation,
        )
        for clamp_name, clamp in carriage.get_named_follower_items():
            parts.add(
                clamp,
                f"{side_name}_{clamp_name}",
                flip=False,
                skip_in_production=True,
                color=Z_CLAMP_COLOR,
                animation=z_animation,
            )
        for bearing_name in ["top_bearing", "bottom_bearing"]:
            parts.add(
                carriage.get_named_non_production_part(bearing_name),
                f"{side_name}_{bearing_name}",
                flip=False,
                skip_in_production=True,
                color=BEARING_COLOR,
                animation=z_animation,
            )

    parts.add(
        x_axis_reference.get_named_non_production_part("lower_axis_profile"),
        "x_axis_lower_profile",
        flip=False,
        skip_in_production=True,
        color=PROFILE_COLOR,
        animation=z_animation,
    )
    parts.add(
        x_axis_reference.get_named_non_production_part("top_axis_profile"),
        "x_axis_top_profile",
        flip=False,
        skip_in_production=True,
        color=PROFILE_COLOR,
        animation=z_animation,
    )
    parts.add(
        x_axis_reference.get_named_non_production_part("rail"),
        "x_axis_rail",
        flip=False,
        skip_in_production=True,
        color=X_AXIS_RAIL_COLOR,
        animation=z_animation,
    )
    for movement_sign, carriage_name in zip([1, -1], ["carriage_1", "carriage_2"]):
        parts.add(
            x_axis_reference.get_named_non_production_part(carriage_name),
            f"x_axis_{carriage_name}",
            flip=False,
            skip_in_production=True,
            color=X_AXIS_COLOR,
            animation={
                **{f"x_{carriage_name}": (300 * movement_sign, 0, 0)},
                **z_animation,
            },
        )

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        export_individual_parts=False,
    )

    _logger.info("x_z_axis_integration created successfully!")


if __name__ == "__main__":
    main()
