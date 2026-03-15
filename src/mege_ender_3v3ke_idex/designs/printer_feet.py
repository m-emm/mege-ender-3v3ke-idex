"""
Printer Feet

Usage:
    cd <project_root> && ./run.sh path/to/printer_feet.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/printer_feet.py
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


def create_printer_feet():
    """Create the printer_feet part."""
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

    from mege_ender_3v3ke_idex.designs.printer_frame import (  # noqa: F401
        create_printer_frame,
    )

    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    frame = create_printer_frame()
    parts.add(frame, "printer_frame", flip=False)

    # Create the part
    part = create_printer_feet()
    parts.add(part, "printer_feet", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("printer_feet created successfully!")


if __name__ == "__main__":
    main()
