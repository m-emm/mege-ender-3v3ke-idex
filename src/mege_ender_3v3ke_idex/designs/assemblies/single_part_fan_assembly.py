"""Standalone single part fan assembly."""

import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

part_fan_overall_clearance = 0.2


def create_single_part_fan_assembly(
    *,
    part_fan_axis_from_left_offset,
    part_fan_body_cutter_clearance,
    part_fan_fillet_radius,
    part_fan_hole_diameter,
    part_fan_mount_plate_blow_direction_offset,
    part_fan_mount_plate_blow_direction_oversize,
    part_fan_mount_plate_cross_oversize,
    part_fan_mount_plate_thickness,
    part_fan_nut_cutter_clearance,
    part_fan_outlet_connector_length,
    part_fan_outlet_wall,
    part_fan_screw_hole_inset,
    part_fan_screw_mount_base_thickness,
    part_fan_screw_mount_cutout_size,
    part_fan_screw_size,
    part_fan_size,
    part_fan_thickness,
    part_fan_window_cutter_outside_length,
    part_fan_window_height,
    part_fan_window_width,
    BIG_THING,
):
    """Create one standalone part fan with its outlet and mount plate artifacts."""

    big_thing = BIG_THING
    outlet_length = 2
    outlet_clearance = 0.25
    outlet_inner_duct_length = 3.5

    body = create_filleted_box(
        part_fan_size,
        part_fan_size,
        part_fan_thickness,
        part_fan_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    mount_plate = create_filleted_box(
        part_fan_size + part_fan_mount_plate_cross_oversize,
        part_fan_size + part_fan_mount_plate_blow_direction_oversize,
        part_fan_mount_plate_thickness,
        part_fan_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    mount_plate = align(mount_plate, body, Alignment.CENTER)
    mount_plate = align(mount_plate, body, Alignment.BACK)
    mount_plate = align(mount_plate, body, Alignment.STACK_BOTTOM)
    mount_plate = translate(0, -part_fan_mount_plate_blow_direction_offset, 0)(
        mount_plate
    )

    if part_fan_body_cutter_clearance > 0:
        body_cutter = create_box(
            part_fan_size + part_fan_body_cutter_clearance * 2,
            part_fan_size + part_fan_body_cutter_clearance * 2,
            part_fan_thickness + part_fan_body_cutter_clearance * 2,
        )
        body_cutter = align(body_cutter, body, Alignment.CENTER)
    else:
        body_cutter = body.copy()

    screw_hole_diameter = MScrew.from_size(part_fan_screw_size).clearance_hole_normal

    screw_hole_cutters_map = {}
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            hole = create_cylinder(
                screw_hole_diameter / 2,
                part_fan_thickness + 2 * part_fan_mount_plate_thickness,
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
                part_fan_screw_size,
                slack=part_fan_nut_cutter_clearance,
            )
            nut_cutter = align(nut_cutter, hole, Alignment.CENTER)
            nut_cutter = align(nut_cutter, mount_plate, Alignment.BOTTOM)
            mount_plate = mount_plate.cut(nut_cutter)

            screw_hole_cutters_map[(lr, fb)] = hole

            mount_cutout = create_cylinder(
                part_fan_screw_mount_cutout_size / 2,
                big_thing,
            )
            mount_cutout = align(mount_cutout, hole, Alignment.CENTER)
            mount_cutout = align(mount_cutout, body, Alignment.BOTTOM)
            mount_cutout = translate(
                0,
                0,
                part_fan_screw_mount_base_thickness,
            )(mount_cutout)
            body = body.cut(mount_cutout)

            additional_cutter = create_box(
                part_fan_screw_mount_cutout_size,
                part_fan_screw_mount_cutout_size,
                big_thing,
            )
            additional_cutter = align(additional_cutter, mount_cutout, Alignment.CENTER)
            additional_cutter = align(additional_cutter, mount_cutout, Alignment.BOTTOM)
            additional_cutter = align(additional_cutter, mount_cutout, lr.opposite)
            additional_cutter = align(additional_cutter, mount_cutout, fb.opposite)

            body = body.cut(
                translate(lr.sign * part_fan_screw_mount_cutout_size / 2, 0, 0)(
                    additional_cutter
                )
            )
            body = body.cut(
                translate(0, fb.sign * part_fan_screw_mount_cutout_size / 2, 0)(
                    additional_cutter
                )
            )

    fan_hole = create_cylinder(part_fan_hole_diameter / 2, big_thing)
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
        part_fan_size / 2 + part_fan_window_cutter_outside_length,
        part_fan_window_height,
    )
    window_cutter = align(window_cutter, body, Alignment.CENTER)
    window_cutter = align(
        window_cutter,
        body,
        Alignment.STACK_FRONT,
        stack_gap=-part_fan_size / 2,
    )
    body = body.cut(window_cutter)

    body_stand_in = materialize_bounding_box(body)

    _logger.info(
        f"Expanding side fan stand in by {part_fan_overall_clearance}mm for clearance"
    )

    fan_clearance_cutter = expand(body_stand_in, part_fan_overall_clearance)
    mount_plate = mount_plate.cut(fan_clearance_cutter)

    retval = LeaderFollowersCuttersPart(body)
    retval.add_named_cutter(window_cutter, "window_cutter")

    for (lr, fb), hole in screw_hole_cutters_map.items():
        retval.add_named_cutter(
            hole,
            f"screw_hole_cutters_{lr.name.lower()}_{fb.name.lower()}",
        )
    retval.add_named_cutter(body_cutter, "body_cutter")
    retval.add_named_follower(mount_plate, "mount_plate")

    outlet = create_box(part_fan_size, outlet_length, part_fan_thickness)
    outlet = align(outlet, body, Alignment.CENTER)
    outlet = align(outlet, body, Alignment.STACK_FRONT, stack_gap=outlet_clearance)

    outlet_window_cutter = align(window_cutter, outlet, Alignment.STACK_FRONT)
    outlet = outlet.cut(outlet_window_cutter)

    outlet_inner_duct = create_box(
        part_fan_window_width - 2 * outlet_clearance,
        part_fan_outlet_connector_length + outlet_clearance + outlet_inner_duct_length,
        part_fan_window_height - 2 * outlet_clearance,
    )
    outlet_inner_duct = align(outlet_inner_duct, window_cutter, Alignment.CENTER)
    outlet_inner_duct = align(outlet_inner_duct, outlet, Alignment.FRONT)

    outlet_inner_duct_cutter = create_box(
        part_fan_window_width - 2 * outlet_clearance - 2 * part_fan_outlet_wall,
        big_thing,
        part_fan_window_height - 2 * outlet_clearance - 2 * part_fan_outlet_wall,
    )
    outlet_inner_duct_cutter = align(
        outlet_inner_duct_cutter,
        outlet_inner_duct,
        Alignment.CENTER,
    )
    outlet = outlet.cut(outlet_inner_duct_cutter)
    outlet_inner_duct = outlet_inner_duct.cut(outlet_inner_duct_cutter)
    outlet = outlet.fuse(outlet_inner_duct)
    retval.add_named_follower(outlet, "outlet")

    _logger.info(f"Adding cutter")
    retval.add_named_cutter(fan_clearance_cutter, "fan_clearance_cutter")

    return retval
