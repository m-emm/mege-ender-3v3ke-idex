"""
Nitehawk Holder

Usage:
    cd <project_root> && ./run.sh path/to/nitehawk_holder.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/nitehawk_holder.py
"""

import copy
import logging
import math
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401; Keep the materials menu around, in case we want to switch back to other materials
    PROCESS_DATA_PETG_04_HS,
    PROCESS_DATA_PLACF_04_HS,
    PROCESS_DATA_PLAGFHT_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.nitehawk_holder import (
    align_holder_to_extruder,
    create_nitehawk_holder,
)
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLAGFHT_04_HS)
BIG_THING = 500

part_fan_size = 40.2
part_fan_fillet_radius = 2
part_fan_thickness = 10.5
part_fan_screw_size = "M2.5"
part_fan_screw_hole_inset = 2.5
part_fan_screw_mount_cutout_size = 5.3
part_fan_screw_mount_cutout_fillet_radius = 2
part_fan_screw_mount_base_thickness = 3.5
part_fan_window_width = 28
part_fan_window_height = 8.1
part_fan_hole_diameter = 31
part_fan_diameter = 30
part_fan_axis_from_left_offset = 17.2



part_fan_parameters = {
    Alignment.LEFT: {
        "base_rotation": 0,
        "around_angle": 0,
        "x_offset": 25,
        "y_offset": 20,
        "z_offset": 10,
        "rotation": 90,
        "tilt": 0,
    },
    Alignment.RIGHT: {
        "base_rotation": 0,
        "around_angle": 90,
        "x_offset": 20,
        "y_offset": 4,
        "z_offset": 0,
        "rotation": 20,
        "tilt": 0,
    },
}


num_blowers = 3
blower_center_offset = 4
blowers_down_angle = 35
blowers_duct_diameter = 6
blowers_wall = 1.5
blowers_nozzle_center_distance = 10

feeder_ring_height = 10
feeder_ring_width = 10

feeder_ring_inner_diameter = 37
feeder_ring_wall = 1.5
feeder_ring_extra_angle = 10

feeder_ring_rotation_angle = -10


def crate_ducts():

    blower_tube_cutters = PartCollector()
    blower_tubes = PartCollector()
    for i in range(num_blowers):

        blower_tube_length = (
            feeder_ring_inner_diameter / 2
            - blowers_nozzle_center_distance
            + feeder_ring_wall
        ) + math.tan(math.radians(blowers_down_angle)) * blowers_duct_diameter

        blower_tube = create_cylinder(
            blowers_duct_diameter / 2 + blowers_wall,
            blower_tube_length,
            direction=(1, 0, 0),
        )

        blower_tube = translate(
            blowers_nozzle_center_distance, blower_center_offset, 0
        )(blower_tube)

        blower_tube_cutter = create_cylinder(
            blowers_duct_diameter / 2,
            blower_tube_length + 2 * blowers_wall,
            direction=(1, 0, 0),
        )
        blower_tube_cutter = align(blower_tube_cutter, blower_tube, Alignment.CENTER)

        blower_tube = rotate(
            -blowers_down_angle, axis=(0, 1, 0), center=(blower_tube_length, 0, 0)
        )(blower_tube)
        blower_tube_cutter = rotate(
            -blowers_down_angle,
            axis=(0, 1, 0),
            center=(blower_tube_length, 0, 0),
        )(blower_tube_cutter)

        angle = (i) * 360 / num_blowers

        blower_tube = rotate(angle)(blower_tube)
        blower_tube_cutter = rotate(angle)(blower_tube_cutter)

        blower_tubes = blower_tubes.fuse(blower_tube)
        blower_tube_cutters = blower_tube_cutters.fuse(blower_tube_cutter)

    feeder_ring_angle = 360 / (num_blowers + 1) * num_blowers + feeder_ring_extra_angle
    feeder_ring_outer_radius = (
        feeder_ring_inner_diameter / 2 + feeder_ring_width + feeder_ring_wall
    )
    feeder_ring_inner_radius = feeder_ring_inner_diameter / 2
    feeder_ring_average_radius = (
        feeder_ring_outer_radius + feeder_ring_inner_radius
    ) / 2

    feeder_ring_equivalent_angle_for_wall = (
        feeder_ring_wall / feeder_ring_average_radius * (180 / math.pi)
    )

    feeder_ring = create_ring(
        feeder_ring_outer_radius,
        feeder_ring_inner_radius,
        feeder_ring_height,
        angle=feeder_ring_angle,
    )

    feeder_ring_cutter = create_ring(
        feeder_ring_inner_diameter / 2 + feeder_ring_width,
        feeder_ring_inner_diameter / 2 + feeder_ring_wall,
        feeder_ring_height - 2 * feeder_ring_wall,
        angle=feeder_ring_angle - 2 * feeder_ring_equivalent_angle_for_wall,
    )

    feeder_ring_cutter = rotate(feeder_ring_equivalent_angle_for_wall)(
        feeder_ring_cutter
    )

    feeder_ring_cutter = align(
        feeder_ring_cutter, feeder_ring, Alignment.CENTER, axes=[2]
    )

    feeder_ring = feeder_ring.cut(feeder_ring_cutter)

    feeder_ring = rotate(-(360 / num_blowers - 360 / (num_blowers + 1)) / 2)(
        feeder_ring
    )

    retval = blower_tubes.fuse(feeder_ring)

    retval = retval.cut(blower_tube_cutters)

    retval = rotate(feeder_ring_rotation_angle)(retval)

    retval_bbox = get_bounding_box(retval)

    retval = translate(0, 0, -retval_bbox[0][2])(retval)

    return retval


def create_part_fan():

    body = create_filleted_box(
        part_fan_size,
        part_fan_size,
        part_fan_thickness,
        part_fan_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    screw_hole_diameter = MScrew.from_size(part_fan_screw_size).clearance_hole_normal

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            hole = create_cylinder(screw_hole_diameter / 2, part_fan_thickness + 2)
            hole = align(hole, body, Alignment.CENTER)
            hole = align(hole, body, lr)
            hole = align(hole, body, fb)
            hole = translate(
                lr.sign * (screw_hole_diameter / 2 - part_fan_screw_hole_inset),
                fb.sign * (screw_hole_diameter / 2 - part_fan_screw_hole_inset),
                0,
            )(hole)
            body = body.cut(hole)

            mount_cutout = create_cylinder(
                part_fan_screw_mount_cutout_size / 2, BIG_THING
            )

            mount_cutout = align(mount_cutout, hole, Alignment.CENTER)
            mount_cutout = align(mount_cutout, body, Alignment.BOTTOM)

            mount_cutout = translate(
                0 * lr.sign * part_fan_screw_hole_inset,
                0 * fb.sign * part_fan_screw_hole_inset,
                part_fan_screw_mount_base_thickness,
            )(mount_cutout)
            body = body.cut(mount_cutout)

            additional_cutter = create_box(
                part_fan_screw_mount_cutout_size,
                part_fan_screw_mount_cutout_size,
                BIG_THING,
            )

            additional_cutter = align(additional_cutter, mount_cutout, Alignment.CENTER)
            additional_cutter = align(additional_cutter, mount_cutout, Alignment.BOTTOM)
            additional_cutter = align(additional_cutter, mount_cutout, lr.opposite)
            additional_cutter = align(additional_cutter, mount_cutout, fb.opposite)

            cutter_1 = translate(lr.sign * part_fan_screw_mount_cutout_size / 2, 0, 0)(
                additional_cutter
            )
            cutter_2 = translate(0, fb.sign * part_fan_screw_mount_cutout_size / 2, 0)(
                additional_cutter
            )
            body = body.cut(cutter_1)
            body = body.cut(cutter_2)

    fan_hole = create_cylinder(part_fan_hole_diameter / 2, BIG_THING)
    fan_hole = align(fan_hole, body, Alignment.CENTER)
    fan_hole = align(fan_hole, body, Alignment.BOTTOM)
    fan_hole = align(fan_hole, body, Alignment.RIGHT)
    fan_hole = translate(
        -part_fan_axis_from_left_offset + part_fan_hole_diameter / 2,
        0,
        (part_fan_thickness - part_fan_window_height) / 2,
    )(fan_hole)
    body = body.cut(fan_hole)

    window_cutter = create_box(part_fan_window_width, BIG_THING, part_fan_window_height)
    window_cutter = align(window_cutter, body, Alignment.CENTER)
    window_cutter = align(
        window_cutter, body, Alignment.STACK_FRONT, stack_gap=-part_fan_size / 2
    )

    body = body.cut(window_cutter)

    return body



def crate_angled_fans():
    fans = PartCollector()
    center_pillar = create_cylinder(0.01, 50)

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        fan = create_part_fan()
        fan = rotate(180, axis=(1, 0, 0))(fan)
        fan = rotate(lr.sign * 90, axis=(0, 0, 1))(fan)

        fan = rotate(part_fan_parameters[lr]["base_rotation"])(fan)

        fan = align(fan, None, Alignment.CENTER)

        fan = rotate(
            -lr.sign * part_fan_parameters[lr]["rotation"],
            axis=(0, 1, 0),
            center=(-lr.sign * part_fan_size / 2, 0, -part_fan_thickness / 2),
        )(fan)

        fan = rotate(-part_fan_parameters[lr]["tilt"], axis=(1, 0, 0))(fan)

        fan = align(fan, center_pillar, lr.stack_alignment)

        fan = translate(lr.sign * part_fan_parameters[lr]["x_offset"], 0, 0)(fan)

        fan = rotate(lr.sign * part_fan_parameters[lr]["around_angle"], axis=(0, 0, 1))(fan)
        fan = translate(
            0, part_fan_parameters[lr]["y_offset"], part_fan_parameters[lr]["z_offset"]
        )(fan)

        fans = fans.fuse(fan)

    fans_bbox = get_bounding_box(fans)
    fans = translate(0, 0, -fans_bbox[0][2] + part_fan_bed_clearance)(fans)

    return fans


def crate_part_fan_assembly():

    fans = crate_angled_fans()

    ducts = crate_ducts()

    ducts = translate(0, 0, part_fan_ducts_clearance)(ducts)

    retval = LeaderFollowersCuttersPart(fans)
    retval.add_named_follower(ducts, "blower_ducts")

    return retval


def main():
    logging.basicConfig(level=logging.INFO)

    parts = PartList()

    extruder = create_sprite_extruder()
    hotend = extruder.get_named_non_production_part("hotend")

    hotend = rotate(90, axis=(1, 0, 0))(hotend)
    hotend = align(hotend, None, Alignment.CENTER)

    hotend_bbox = get_bounding_box(hotend)

    hotend = translate(0, 0, -hotend_bbox[0][2])(hotend)

    parts.add(hotend, "hotend", flip=False, skip_in_production=True)

    fans = crate_part_fan_assembly()

    hotend_center = get_bounding_box_center(hotend)
    hotend_bbox = get_bounding_box(hotend)

    fans = translate(hotend_center[0], hotend_center[1], hotend_bbox[0][2])(fans)

    parts.add(fans, "angled_fans", flip=False, skip_in_production=True)

    for name, npp in fans.get_named_follower_items():
        parts.add(npp, name, flip=False, skip_in_production=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("part_fans created successfully!")


if __name__ == "__main__":
    main()
