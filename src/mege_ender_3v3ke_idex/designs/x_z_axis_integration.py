"""
X Z Axis Integration

Usage:
    cd <project_root> && ./run.sh path/to/x_z_axis_integration.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/x_z_axis_integration.py
"""

import logging
import os

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (  # noqa: F401
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.nema_motors import (  # noqa: F401
    create_nema_composite,
)
from mege_ender_3v3ke_idex.designs.printer_frame import (  # noqa: F401
    create_printer_frame,
)
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (  # noqa: F401
    create_four_screws_mount_assembly,
)
from mege_ender_3v3ke_idex.designs.x_axis import create_x_axis  # noqa: F401
from mege_ender_3v3ke_idex.designs.z_axis import create_z_axis  # noqa: F401
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


def create_x_z_axis_integration():
    """Create the x_z_axis_integration part."""
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
    part = create_x_z_axis_integration()
    parts.add(part, "x_z_axis_integration", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("x_z_axis_integration created successfully!")


if __name__ == "__main__":
    main()
