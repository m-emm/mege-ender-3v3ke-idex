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
BIG_THING = 500
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

hot_side_holes_back_holes_z_distance = 19

motor_hole_y_pitch = 24
motor_hole_z_pitch = 20

side_holes_depth = 4

fan_thickness = 14

extruder_mount_screw_size = "M3"

lever_width = 14.5
lever_thickness = 4
lever_length = 23
lever_angle = 45
lever_center_offset = 4.4
lever_front_inset = 1


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

    mount_hole_cutter = motor_composite.get_named_cutter("mount_holes")

    side_holes_drills = PartCollector()
    hot_side_hole_diameter = MScrew.from_size(extruder_mount_screw_size).core_hole / 2
    hot_side_hole = create_cylinder(hot_side_hole_diameter, BIG_THING)
    hot_side_hole = rotate(90, axis=(0, 1, 0))(hot_side_hole)
    hot_side_hole = align(hot_side_hole, front, Alignment.CENTER)
    hot_side_hole = align(hot_side_hole, front, Alignment.BACK)
    hot_side_hole = align(hot_side_hole, front, Alignment.TOP)
    hot_side_hole = align(
        hot_side_hole, front, Alignment.STACK_LEFT, stack_gap=-side_holes_depth
    )
    hot_side_hole = translate(
        0, hot_side_hole_diameter / 2, hot_side_hole_diameter / 2
    )(hot_side_hole)

    hot_side_holes = []

    for i in [0, 1]:
        current_side_hole = translate(
            0,
            -hot_side_holes_back_distance - i * hot_side_holes_y_pitch,
            -hot_side_holes_back_holes_z_distance,
        )(hot_side_hole)

        side_holes_drills = side_holes_drills.fuse(current_side_hole)
        hot_side_holes.append(current_side_hole)

    for i in [0, 1]:
        top_distance = (
            hot_side_holes_top_distance_back
            if i == 0
            else hot_side_holes_top_distance_front
        )
        current_side_hole = translate(
            0,
            -hot_side_holes_back_distance - i * hot_side_holes_y_pitch,
            -top_distance,
        )(hot_side_hole)

        side_holes_drills = side_holes_drills.fuse(current_side_hole)
        hot_side_holes.append(current_side_hole)

    motor_holes = []
    motor_hole_drills = PartCollector()

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            for tb in [Alignment.TOP, Alignment.BOTTOM]:
                if tb == Alignment.TOP and lr == Alignment.RIGHT:
                    continue  # Skip top right holes
                hole = create_cylinder(hot_side_hole_diameter, BIG_THING)
                hole = rotate(90, axis=(0, 1, 0))(hole)

                hole = align(hole, motor, Alignment.CENTER)
                hole = align(
                    hole, motor, lr.stack_alignment, stack_gap=-side_holes_depth
                )

                hole = translate(
                    0,
                    fb.sign * motor_hole_y_pitch / 2,
                    tb.sign * motor_hole_z_pitch / 2,
                )(hole)
                motor_hole_drills = motor_hole_drills.fuse(hole)
                motor_holes.append(hole)

    motor_hole_drills = LeaderFollowersCuttersPart(motor_hole_drills)
    for i, hole in enumerate(motor_holes):
        motor_hole_drills.add_named_cutter(hole, f"motor_hole_{i}")

    motor_hole_drills = align(motor_hole_drills, motor, Alignment.CENTER)

    motor = motor.cut(motor_hole_drills.leader)

    retval = motor.fuse(front)

    retval = retval.cut(mount_hole_cutter)

    retval = retval.cut(side_holes_drills)

    retval = LeaderFollowersCuttersPart(retval)
    for i, hole in enumerate(hot_side_holes):
        retval.add_named_cutter(hole, f"hot_side_hole_{i}")

    for cutter_name, cutter in motor_hole_drills.get_named_cutter_items():
        retval.add_named_cutter(cutter, cutter_name)

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

    # lever_width = 14.5
    # lever_thickness = 4
    # lever_length = 23
    # lever_angle = 45
    # lever_center_offset = 4.4

    lever = create_box(lever_thickness, lever_length, lever_width)

    lever = align(lever, front, Alignment.CENTER)
    lever = align(lever, front, Alignment.STACK_BACK)
    lever = align(lever, front, Alignment.TOP)

    lever = translate(lever_center_offset, lever_front_inset, 0)(lever)

    lever_bbox = get_bounding_box(lever)
    lever_rotation_center = (
        (lever_bbox[0][0] + lever_bbox[1][0]) / 2,
        lever_bbox[0][1],
        0,
    )

    lever = rotate(-lever_angle, axis=(0, 0, 1), center=lever_rotation_center)(lever)
    lever = translate(lever_center_offset, 0, -lever_front_inset)(lever)
    retval.add_named_non_production_part(lever, "lever")

    fan = create_box(fan_thickness, front_size[1], front_size[2])
    fan = align(fan, front, Alignment.CENTER)
    fan = align(fan, front, Alignment.FRONT)
    fan = align(fan, front, Alignment.STACK_RIGHT)
    retval.add_named_non_production_part(fan, "fan")

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    extruder = create_sprite_extruder()
    parts.add(extruder, "sprite_extruder", flip=False)

    for name, npp in extruder.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    mount_plates = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        mount_plate = create_box(3, 40, 60)
        mount_plate = align(mount_plate, extruder, Alignment.CENTER)
        mount_plate = align(mount_plate, extruder, lr.stack_alignment, stack_gap=6)
        mount_plate = extruder.use_as_cutter_on(mount_plate)
        mount_plates = mount_plates.fuse(mount_plate)

    parts.add(mount_plates, "mount_plates", flip=False, skip_in_production=True)

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
