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

hotend_diameter = 13.9
hotend_length = 24.8
nozzle_diameter = 6.6
nozzle_length = 4.4
nozzle_tip_diameter = 1.0
hotend_inset = 2

hot_side_holes_y_pitch = 18

hot_side_holes_back_distance = 7
hot_side_holes_top_distance_back = 6.5
hot_side_holes_top_distance_front = 4
hot_side_holes_z_pitch_back = 10
hot_side_holes_z_pitch_front = 15

side_holes_depth = 4

extruder_mount_screw_size = "M3"


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

    side_holes_drills = PartCollector()
    for i in [0, 1]:
        for j in [0, 1]:
            hot_side_hole_diameter = (
                MScrew.from_size(extruder_mount_screw_size).core_hole / 2
            )
            hot_side_hole = create_cylinder(
                hot_side_hole_diameter, 2 * side_holes_depth
            )
            hot_side_hole = rotate(90, axis=(0, 1, 0))(hot_side_hole)
            hot_side_hole = align(hot_side_hole, front, Alignment.CENTER)
            hot_side_hole = align(hot_side_hole, front, Alignment.TOP)
            hot_side_hole = align(hot_side_hole, front, Alignment.BACK)
            hot_side_hole = align(
                hot_side_hole, front, Alignment.STACK_LEFT, stack_gap=-side_holes_depth
            )

            hot_side_holes_top_distance = (
                hot_side_holes_top_distance_back
                if i == 0
                else hot_side_holes_top_distance_front
            )
            hot_side_holes_z_pitch = (
                hot_side_holes_z_pitch_back if i == 0 else hot_side_holes_z_pitch_front
            )
            hot_side_hole = translate(
                0,
                -hot_side_holes_back_distance
                - i * hot_side_holes_y_pitch
                + hot_side_hole_diameter / 2,
                -hot_side_holes_top_distance
                - j * hot_side_holes_z_pitch
                + hot_side_hole_diameter / 2,
            )(hot_side_hole)

            side_holes_drills = side_holes_drills.fuse(hot_side_hole)

    retval = retval.fuse(side_holes_drills)

    retval = LeaderFollowersCuttersPart(retval)
    retval.add_named_cutter(mount_nole_cutter, "mount_holes")

    hotend = create_cylinder(hotend_diameter / 2, hotend_length)
    nozzle = create_cone(nozzle_diameter / 2, nozzle_tip_diameter / 2, nozzle_length)
    nozzle = align(nozzle, hotend, Alignment.CENTER)
    nozzle = align(nozzle, hotend, Alignment.STACK_TOP)
    hotend = hotend.fuse(nozzle)

    hotend = rotate(90, axis=(1, 0, 0))(hotend)
    hotend = align(hotend, cooler, Alignment.CENTER)
    hotend = align(hotend, cooler, Alignment.STACK_FRONT)
    hotend = align(hotend, cooler, Alignment.TOP)
    hotend = translate(0, 0, -hotend_inset)(hotend)

    retval.add_named_non_production_part(hotend, "hotend")

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_sprite_extruder()
    parts.add(part, "sprite_extruder", flip=False)

    for name, npp in part.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

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
