"""
Y Axis

Usage:
    cd <project_root> && ./run.sh path/to/y_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/y_axis.py
"""

import logging
import os

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12h_rail_with_carriages
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# Optional slicer process overrides
PROCESS_DATA = {
    "filament": "FilamentPLAMegeMaster",
    "process_overrides": {
        "nozzle_diameter": "0.6",
        "layer_height": "0.2",
    },
}


def create_y_axis():
    """Create the y_axis part."""

    rails = []
    for i in [-1, 1]:

        rail_side_name = "left" if i == -1 else "right"
        profile = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_2020, length_mm=y_axis_profile_length
        )

        profile = rotate(90, axis=(1, 0, 0))(profile)
        profile = align(profile, None, Alignment.CENTER)
        profile = translate(i * y_axis_rail_spacing / 2, 0, 0)(profile)

        rail_side_name = "left" if i == -1 else "right"
        rail = create_mgn12h_rail_with_carriages(
            y_axis_rail_length,
            carriage_offsets=[
                -y_axis_carriage_spacing / 2,
                y_axis_carriage_spacing / 2,
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

    rails_part = rails[0].fuse(rails[1])

    return rails_part


def main():

    from mege_ender_3v3ke_idex.designs.printer_frame import (  # noqa: F401
        create_printer_frame,
    )

    logging.basicConfig(level=logging.INFO)

    _logger.info(f"y_axis_profile_length: {y_axis_profile_length}")
    _logger.info(f"y_axis_rail_length: {y_axis_rail_length}")

    parts = PartList()

    frame = create_printer_frame()

    parts.add(frame, "printer_frame", flip=False, skip_in_production=True)

    for name, npp in frame.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    y_axis = create_y_axis()

    y_axis = align(y_axis, frame, Alignment.CENTER, axes=[0, 1])
    y_axis_profile_left = y_axis.get_non_production_part_by_name("profile_left")

    axis_aligner = align_translation(
        y_axis_profile_left, frame, Alignment.CENTER, axes=[2]
    )

    y_axis = axis_aligner(y_axis)

    parts.add(y_axis.leader, "y_axis", flip=False, skip_in_production=True)

    for name, follower in y_axis.get_named_follower_items():
        parts.add(follower, name, flip=False, skip_in_production=True)

    for name, npp in y_axis.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("y_axis created successfully!")


if __name__ == "__main__":
    main()
