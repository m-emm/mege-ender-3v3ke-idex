"""
Sprite Extruder

Usage:
    cd <project_root> && ./run.sh path/to/sprite_extruder.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/sprite_extruder.py
"""

import logging
import os

from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
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


def create_sprite_extruder():
    """Create the sprite_extruder part."""
    # Example: simple box with a cylindrical hole

    motor_composite = create_nema_composite(body_thickness=26.5)
    motor = motor_composite.get_named_follower("body")
    front = create_nema_composite(body_thickness=23.2)
    front = front.get_named_follower("body")
    front = rotate(180, axis=(0, 1, 0))(front)
    front = align(front, motor, Alignment.CENTER)
    front = align(front, motor, Alignment.STACK_TOP)

    cooler_height = 13.6
    front_size = get_bounding_box_size(front)
    cooler = create_box(front_size[0], cooler_height, front_size[2])

    cooler_groove_width = 1.25
    cooler_groove_depth = 3.5
    cooler_groove_pitch = 2.5
    num_cooler_grooves = 4

    groove_cutter = PartCollector()
    for i in range(num_cooler_grooves):
        groove = create_box(100, cooler_groove_width, 100)
        groove = translate(0, i * cooler_groove_pitch, 0)(groove)
        groove_cutter = groove_cutter.fuse(groove)

    groove_cutter = align(groove_cutter, cooler, Alignment.CENTER)
    groove_cutter = align(groove_cutter, cooler, Alignment.BACK)
    groove_cutter = align(
        groove_cutter, cooler, Alignment.STACK_TOP, stack_gap=-cooler_groove_depth
    )

    cooler = cooler.cut(groove_cutter)

    cooler = align(cooler, front, Alignment.CENTER)
    cooler = align(cooler, front, Alignment.FRONT)
    cooler_size = get_bounding_box_size(cooler)
    cooler_cutter = create_box(cooler_size[0], cooler_size[1], cooler_size[2])
    cooler_cutter = align(cooler_cutter, cooler, Alignment.CENTER)
    front = front.cut(cooler_cutter)

    front = front.fuse(cooler)

    retval = motor.fuse(front)

    mount_nole_cutter = motor_composite.get_named_cutter("mount_holes")
    retval = retval.cut(mount_nole_cutter)

    retval = LeaderFollowersCuttersPart(retval)
    retval.add_named_cutter(mount_nole_cutter, "mount_holes")

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_sprite_extruder()
    parts.add(part, "sprite_extruder", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("sprite_extruder created successfully!")


if __name__ == "__main__":
    main()
