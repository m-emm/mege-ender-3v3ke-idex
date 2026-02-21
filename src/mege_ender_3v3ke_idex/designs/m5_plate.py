"""
M5 Plate

Usage:
    cd <project_root> && ./run.sh path/to/m5_plate.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/m5_plate.py
"""
import copy
import logging
import os
from collections import defaultdict
from pathlib import Path

import numpy as np
from mege_3devops.process_data.mender3.process_data_04_high_speed import (
    PROCESS_DATA_PETGCF_04_HS,
)
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.endstop_holder import create_endstop_holder
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt2_idler
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.mgh_linear import (
    create_mgn12h_carriage,
    create_mgn12h_rail,
)
from mege_ender_3v3ke_idex.designs.motor_mount import create_motor_stack
from mege_ender_3v3ke_idex.designs.tool_head_mount import create_tool_head_mount
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"


BIG_THING = 500



PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)
PROCESS_DATA["process_overrides"]["sparse_infill_density"] = "90%"

angle_plate_width = 28
angle_plate_length = 28
angle_plate_thickness = 5
angle_plate_fillet_radius = 3


def create_angle_plate():
    """Create the angle_plate part."""
    plate = create_filleted_box(angle_plate_width, angle_plate_length, angle_plate_thickness, angle_plate_fillet_radius, no_fillets_at=[Alignment.TOP, Alignment.BOTTOM])

    hole_drill_diameter = MScrew.from_size("M5").clearance_hole_loose

    hole_drill = create_cylinder(hole_drill_diameter / 2, BIG_THING)
    hole_drill = align(hole_drill, plate, Alignment.CENTER)

    plate = plate.cut(hole_drill)

    return plate
    




def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part

    part = create_angle_plate()
    parts.add(part, "m5_plate", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("m5_plate created successfully!")


if __name__ == "__main__":
    main()
