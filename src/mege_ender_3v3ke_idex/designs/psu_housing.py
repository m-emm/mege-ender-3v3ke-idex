"""
Psu Housing

Usage:
    cd <project_root> && ./run.sh path/to/psu_housing.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/psu_housing.py
"""

import logging
import os

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

cheap_psu_length = 205
cheap_psu_width = 50
cheap_psu_height = 22.9
cheap_psu_srcrew_slit_width = 3.65
cheap_psu_srcrew_slit_depth = 6.1
cheap_psu_base_thickness = 1.5
cheap_psu_body_length = 162


creality_psu_width = 114.7
creality_psu_length = 215
creality_psu_height = 29.7
creality_psu_mount_screw_size = "M4"
creality_psu_mount_screw_hole_length_inset = 32.3
creality_psu_mount_screw_hole_z_offset_from_bottom = 12


def create_creality_psu():
    pass


def crate_cheap_psu():
    pass


def create_psu_housing():
    """Create the psu_housing part."""
    # Example: simple box with a cylindrical hole
    width = 30
    depth = 20
    height = 10
    hole_radius = 4

    # Create base box
    part = create_box(width, depth, height)

    # Create a hole cutter
    hole = create_cylinder(hole_radius, height + 2)
    hole = align(hole, part, Alignment.CENTER)
    hole = translate(0, 0, -1)(hole)

    # Cut the hole
    part = part.cut(hole)

    return part


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_psu_housing()
    parts.add(part, "psu_housing", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("psu_housing created successfully!")


if __name__ == "__main__":
    main()
