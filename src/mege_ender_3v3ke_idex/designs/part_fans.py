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
    PROCESS_DATA_PLA_04_HS,
    PROCESS_DATA_PLACF_04_HS,
    PROCESS_DATA_PLAGFHT_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLAGFHT_04_HS)
PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLA_04_HS)

PROCESS_DATA["process_overrides"].update(
    {
        "enable_support": "1",
        "support_threshold_angle": "30",
        "brim_type": "no_brim",
    }
)


BIG_THING = 500


def create_duct_extension():

    duct_extension_body = create_box(
        duct_extension_width, part_fan_duct_extension_length, feeder_ring_height
    )
    duct_extension_cutter = create_box(
        duct_extension_width - feeder_ring_wall * 2,
        part_fan_duct_extension_length - 2 * feeder_ring_wall,
        feeder_ring_height - 2 * feeder_ring_wall,
    )
    duct_extension_cutter = align(
        duct_extension_cutter, duct_extension_body, Alignment.CENTER
    )

    duct_extension = duct_extension_body.cut(duct_extension_cutter)

    retval = LeaderFollowersCuttersPart(duct_extension)
    retval.add_named_cutter(duct_extension_body, "duct_extension_body_cutter")

    return retval


def crate_ducts():
    _logger.info("Creating ducts...")

    blower_tube_cutters = PartCollector()
    blower_tubes = PartCollector()
    for i in range(num_blowers):

        _logger.info(f"Creating blower tube {i+1}/{num_blowers}...")

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

        blower_tube_bb = get_bounding_box(blower_tube)
        blower_tube_length = blower_tube_bb[1][0] - blower_tube_bb[0][0]
        blower_tube_center = get_bounding_box_center(blower_tube)

        blowers_nozzle_tip_scale = 0.4

        def blower_tip_transform_function(point):
            x, y, z = point

            relative_x = x - blower_tube_bb[0][0]
            scale_factor = (
                blowers_nozzle_tip_scale
                + relative_x / blower_tube_length * (1 - blowers_nozzle_tip_scale)
            )
            relative_z = z - blower_tube_center[2]
            new_relative_z = relative_z * scale_factor
            new_z = blower_tube_center[2] + new_relative_z
            new_y = y

            return x, new_y, new_z

        blower_tube = transform_with_function_tesselating(
            blower_tube, blower_tip_transform_function
        )

        blower_tube = translate(
            blowers_nozzle_center_distance, blower_center_offset, 0
        )(blower_tube)

        blower_tube_cutter = create_cylinder(
            blowers_duct_diameter / 2,
            blower_tube_length + 2 * blowers_wall,
            direction=(1, 0, 0),
        )
        blower_tube_cutter = transform_with_function_tesselating(
            blower_tube_cutter, blower_tip_transform_function
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
        _logger.info(f"Blower tube {i+1}/{num_blowers} created.")

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

    feeder_ring_rotation = rotate((-(360 / num_blowers - 360 / (num_blowers + 1)) / 2))

    feeder_ring = feeder_ring_rotation(feeder_ring)
    feeder_ring_cutter = feeder_ring_rotation(feeder_ring_cutter)

    retval = blower_tubes.fuse(feeder_ring)

    retval = retval.cut(blower_tube_cutters)

    retval = retval.cut(feeder_ring_cutter)

    retval = rotate(feeder_ring_rotation_angle, axis=(0, 0, 1))(retval)

    retval_bbox = get_bounding_box(retval)

    duct_extension = create_duct_extension()

    duct_extension = align(duct_extension, retval, Alignment.TOP)
    duct_extension = align(duct_extension, retval, Alignment.LEFT)
    duct_extension = align(duct_extension, retval, Alignment.FRONT)

    duct_bbox_size = get_bounding_box_size(retval)
    duct_extension = translate(
        -duct_extension_width + feeder_ring_width, duct_bbox_size[1] / 2, 0
    )(duct_extension)

    duct_extension = duct_extension.cut(feeder_ring_cutter)
    retval = retval.cut(duct_extension.get_named_cutter("duct_extension_body_cutter"))
    retval = retval.fuse(duct_extension.leader)

    retval = translate(0, 0, -retval_bbox[0][2])(retval)

    return retval


def create_part_fan(
    window_cutter_outside_length=0,
    body_cutter_clearance=None,
    outlet_length=2,
    outlet_wall=1,
    outlet_clearance=0.2,
    outlet_inner_duct_length=3.5,
    mount_plate_thickness=None,
    mount_plate_blow_direction_oversize=0,
    mount_plate_cross_oversize=0,
    mount_plate_blow_direction_offset=0,
) -> LeaderFollowersCuttersPart:

    body = create_filleted_box(
        part_fan_size,
        part_fan_size,
        part_fan_thickness,
        part_fan_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    mount_plate = create_filleted_box(
        part_fan_size + mount_plate_cross_oversize,
        part_fan_size + mount_plate_blow_direction_oversize,
        mount_plate_thickness,
        part_fan_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    mount_plate = align(mount_plate, body, Alignment.CENTER)
    mount_plate = align(mount_plate, body, Alignment.BACK)
    mount_plate = align(mount_plate, body, Alignment.STACK_BOTTOM)
    mount_plate = translate(0, -mount_plate_blow_direction_offset, 0)(mount_plate)

    if body_cutter_clearance > 0:
        body_cutter = create_box(
            part_fan_size + body_cutter_clearance * 2,
            part_fan_size + body_cutter_clearance * 2,
            part_fan_thickness + body_cutter_clearance * 2,
        )
        body_cutter = align(body_cutter, body, Alignment.CENTER)
    else:
        body_cutter = body.copy()

    screw_hole_diameter = MScrew.from_size(part_fan_screw_size).clearance_hole_normal

    screw_hole_cutters = PartCollector()
    screw_hole_cutters_map = {}
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            hole = create_cylinder(
                screw_hole_diameter / 2, part_fan_thickness + 2 * mount_plate_thickness
            )
            hole = align(hole, body, Alignment.CENTER)
            hole = align(hole, body, lr)
            hole = align(hole, body, fb)
            hole = translate(
                lr.sign * (screw_hole_diameter / 2 - part_fan_screw_hole_inset),
                fb.sign * (screw_hole_diameter / 2 - part_fan_screw_hole_inset),
                0,
            )(hole)
            body = body.cut(hole)
            mount_plate = mount_plate.cut(hole)

            nut_cutter = create_nut(
                part_fan_screw_size, slack=part_fan_nut_cutter_clearance
            )

            nut_cutter = align(nut_cutter, hole, Alignment.CENTER)
            nut_cutter = align(nut_cutter, mount_plate, Alignment.BOTTOM)

            mount_plate = mount_plate.cut(nut_cutter)

            screw_hole_cutters = screw_hole_cutters.fuse(hole)
            screw_hole_cutters_map[(lr, fb)] = hole

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

    window_cutter = create_box(
        part_fan_window_width,
        part_fan_size / 2 + window_cutter_outside_length,
        part_fan_window_height,
    )
    window_cutter = align(window_cutter, body, Alignment.CENTER)
    window_cutter = align(
        window_cutter, body, Alignment.STACK_FRONT, stack_gap=-part_fan_size / 2
    )

    body = body.cut(window_cutter)

    retval = LeaderFollowersCuttersPart(body)
    retval.add_named_cutter(window_cutter, "window_cutter")

    for (lr, fb), hole in screw_hole_cutters_map.items():
        retval.add_named_cutter(
            hole, f"screw_hole_cutters_{lr.name.lower()}_{fb.name.lower()}"
        )
    retval.add_named_cutter(body_cutter, "body_cutter")
    retval.add_named_follower(mount_plate, "mount_plate")

    if outlet_length is not None:
        outlet = create_box(part_fan_size, outlet_length, part_fan_thickness)
        outlet = align(outlet, body, Alignment.CENTER)
        outlet = align(outlet, body, Alignment.STACK_FRONT, stack_gap=outlet_clearance)
        outlet = outlet.cut(window_cutter)
        outlet_inner_duct = create_box(
            part_fan_window_width - 2 * outlet_clearance,
            part_fan_outlet_connector_length
            + outlet_clearance
            + outlet_inner_duct_length,
            part_fan_window_height - 2 * outlet_clearance,
        )
        outlet_inner_duct = align(outlet_inner_duct, window_cutter, Alignment.CENTER)
        outlet_inner_duct = align(outlet_inner_duct, outlet, Alignment.FRONT)

        outtlet_inner_duct_cutter = create_box(
            part_fan_window_width - 2 * outlet_clearance - 2 * outlet_wall,
            BIG_THING,
            part_fan_window_height - 2 * outlet_clearance - 2 * outlet_wall,
        )
        outtlet_inner_duct_cutter = align(
            outtlet_inner_duct_cutter, outlet_inner_duct, Alignment.CENTER
        )
        outlet_inner_duct = outlet_inner_duct.cut(outtlet_inner_duct_cutter)

        outlet = outlet.fuse(outlet_inner_duct)
        retval.add_named_follower(outlet, "outlet")

    return retval


def crate_angled_fans(
    window_cutter_outside_length,
    body_cutter_clearance,
):
    fans = PartCollector()
    center_pillar = create_cylinder(0.01, 50)

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        fan = create_part_fan(
            window_cutter_outside_length,
            body_cutter_clearance,
            mount_plate_blow_direction_oversize=part_fan_parameters[lr][
                "mount_plate_blow_direction_oversize"
            ],
            mount_plate_cross_oversize=part_fan_parameters[lr][
                "mount_plate_cross_oversize"
            ],
            mount_plate_blow_direction_offset=part_fan_parameters[lr][
                "mount_plate_blow_direction_offset"
            ],
            mount_plate_thickness=part_fan_mount_plate_thickness,
        )
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

        fan = rotate(lr.sign * part_fan_parameters[lr]["around_angle"], axis=(0, 0, 1))(
            fan
        )
        fan = translate(
            0, part_fan_parameters[lr]["y_offset"], part_fan_parameters[lr]["z_offset"]
        )(fan)

        fan = fan.prefixed_copy(f"part_fan_{lr.name.lower()}")

        fans = fans.fuse(fan)

    fans_bbox = get_bounding_box(fans)
    fans = translate(0, 0, -fans_bbox[0][2] + part_fan_bed_clearance)(fans)

    return fans


def create_part_fan_assembly():

    fans = crate_angled_fans(
        window_cutter_outside_length=part_fan_window_cutter_outside_length,
        body_cutter_clearance=part_fan_body_cutter_clearance,
    )

    ducts = crate_ducts()

    ducts = translate(0, 0, part_fan_ducts_clearance)(ducts)

    for name, cutter in fans.get_named_cutter_items():
        if "window_cutter" in name or "body_cutter" in name:
            ducts = ducts.cut(cutter)

    for name, follower in fans.get_named_follower_items():
        if "outlet" in name or "mount_plate" in name:
            ducts = ducts.fuse(follower)

    for name, cutter in fans.get_named_cutter_items():
        if "window_cutter" in name or "body_cutter" in name:
            ducts = ducts.cut(cutter)

    for name, follower in fans.get_named_follower_items():
        if "outlet" in name or "mount_plate" in name:
            ducts = ducts.fuse(follower)

    fans.add_named_follower(ducts, "blower_ducts")

    return fans


def align_fans_to_sprite_extruder(fans, sprite_extruder):

    hotend = sprite_extruder.get_named_non_production_part("hotend")

    hotend_center = get_bounding_box_center(hotend)

    hotend_bbox = get_bounding_box(hotend)

    fans = translate(hotend_center[0], hotend_center[1], hotend_bbox[0][2])(fans)

    return fans


def main():
    logging.basicConfig(level=logging.INFO)

    parts = PartList()

    extruder = create_sprite_extruder()
    hotend = extruder.get_named_non_production_part("hotend")

    hotend = align(hotend, None, Alignment.CENTER)

    hotend_bbox = get_bounding_box(hotend)

    extruder = translate(0, 0, -hotend_bbox[0][2])(extruder)

    hotend = extruder.get_named_non_production_part("hotend")

    parts.add(hotend, "hotend", flip=False, skip_in_production=True)

    fans = create_part_fan_assembly()

    fans = align_fans_to_sprite_extruder(fans, extruder)

    parts.add(fans, "angled_fans", flip=False, skip_in_production=True)

    for name, npp in fans.get_named_follower_items():

        if "blower_ducts" in name:
            parts.add(
                npp,
                name,
                flip=True,
                skip_in_production=False,
                prod_rotation_angle=50,
                prod_rotation_axis=(1, 0, 0),
            )

    simulated_part_to_print = create_box(50, 50, 1)
    simulated_part_to_print = translate(0, 0, -1)(simulated_part_to_print)

    simulated_part_to_print = align(
        simulated_part_to_print, hotend, Alignment.CENTER, axes=[0, 1]
    )  # but not z axis - this is to simulate the part being at z = 0

    simulated_part_to_print = align(
        simulated_part_to_print, hotend, Alignment.STACK_BOTTOM
    )

    parts.add(
        simulated_part_to_print,
        "simulated_part_to_print",
        flip=False,
        skip_in_production=True,
    )

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
