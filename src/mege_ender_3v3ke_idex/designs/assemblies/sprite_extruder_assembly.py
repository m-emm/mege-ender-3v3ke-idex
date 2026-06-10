"""Declarative sprite extruder assembly."""

import math

from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from shellforgepy.simple import *


def create_sprite_extruder_assembly(
    *,
    hotend_diameter,
    hotend_overall_length,
    nozzle_diameter,
    nozzle_length,
    nozzle_screw_length,
    nozzle_y_offset,
    nozzle_tip_diameter,
    hot_side_holes_y_pitch,
    hot_side_holes_back_distance,
    hot_side_holes_top_distance_back,
    hot_side_holes_top_distance_front,
    hot_side_holes_back_holes_z_distance,
    motor_hole_y_pitch,
    motor_hole_z_pitch,
    side_holes_depth,
    fan_thickness,
    extruder_mount_screw_size,
    lever_width,
    lever_thickness,
    lever_length,
    lever_angle,
    lever_center_offset,
    lever_front_inset,
    hotend_x_distance_from_right_edge,
    BIG_THING,
):
    """Create the sprite extruder assembly."""

    big_thing = BIG_THING
    hotend_length = hotend_overall_length - nozzle_length - nozzle_screw_length

    motor_composite = create_nema_composite(body_thickness=26.5)
    motor_composite = rotate(90, axis=(1, 0, 0))(motor_composite)
    motor = motor_composite.get_named_follower("body")

    front_compound = create_nema_composite(body_thickness=23.2)
    front_compound = rotate(90, axis=(1, 0, 0))(front_compound)

    front = LeaderFollowersCuttersPart(front_compound.get_named_follower("body"))
    front = front.merge_except_leader(front_compound)

    front = align(front, motor, Alignment.CENTER)
    front = align(front, motor, Alignment.STACK_BACK)

    cooler_height = 13.6
    front_size = get_bounding_box_size(front)
    cooler = create_box(front_size[0], cooler_height, front_size[2])

    cooler_groove_width = 1.25
    cooler_groove_depth = 3.5
    cooler_groove_pitch = 2.5
    num_cooler_grooves = 4

    groove_cutter = PartCollector()
    for i in range(num_cooler_grooves):
        groove = create_box(100, cooler_groove_depth, cooler_groove_width)
        groove = translate(0, 0, i * cooler_groove_pitch)(groove)
        groove_cutter = groove_cutter.fuse(groove)

    groove_cutter = align(groove_cutter, cooler, Alignment.CENTER)
    groove_cutter = align(groove_cutter, cooler, Alignment.BACK)
    groove_cutter = align(groove_cutter, cooler, Alignment.BOTTOM)
    groove_cutter = translate(0, 0, cooler_groove_width)(groove_cutter)

    cooler = cooler.cut(groove_cutter)
    cooler = align(cooler, front, Alignment.CENTER)
    cooler = align(cooler, front, Alignment.BACK)

    cooler_cutter = create_box(*get_bounding_box_size(cooler))
    cooler_cutter = align(cooler_cutter, cooler, Alignment.CENTER)
    front = front.cut(cooler_cutter)
    front = front.fuse(cooler)

    mount_hole_cutter = motor_composite.get_named_cutter("mount_holes")
    mount_hole_cutter = align(mount_hole_cutter, motor, Alignment.CENTER, axes=[0, 2])
    mount_hole_cutter = align(mount_hole_cutter, motor, Alignment.STACK_BACK)

    side_holes_drills = PartCollector()
    hot_side_hole_radius = MScrew.from_size(extruder_mount_screw_size).core_hole / 2
    mount_hole_diameter = MScrew.from_size(
        extruder_mount_screw_size
    ).clearance_hole_loose

    hot_side_hole = create_cylinder(hot_side_hole_radius, big_thing)
    hot_side_hole = rotate(90, axis=(0, 1, 0))(hot_side_hole)
    hot_side_hole = align(hot_side_hole, front, Alignment.CENTER)
    hot_side_hole = align(hot_side_hole, front, Alignment.TOP)
    hot_side_hole = align(hot_side_hole, front, Alignment.BACK)
    hot_side_hole = align(
        hot_side_hole,
        front,
        Alignment.STACK_RIGHT,
        stack_gap=-side_holes_depth,
    )
    hot_side_hole = translate(
        0,
        hot_side_hole_radius / 2,
        hot_side_hole_radius / 2,
    )(hot_side_hole)

    hot_side_holes = []
    hot_side_mount_holes = []

    for i in [0, 1]:
        current_side_hole = translate(
            0,
            -hot_side_holes_back_holes_z_distance,
            -hot_side_holes_back_distance - i * hot_side_holes_y_pitch,
        )(hot_side_hole)
        side_holes_drills = side_holes_drills.fuse(current_side_hole)
        hot_side_holes.append(current_side_hole)

        hot_side_mount_hole = create_cylinder(mount_hole_diameter / 2, big_thing)
        hot_side_mount_hole = rotate(90, axis=(0, 1, 0))(hot_side_mount_hole)
        hot_side_mount_hole = align(
            hot_side_mount_hole,
            current_side_hole,
            Alignment.CENTER,
        )
        hot_side_mount_hole = align(
            hot_side_mount_hole,
            front,
            Alignment.STACK_RIGHT,
        )
        hot_side_mount_holes.append(hot_side_mount_hole)

    for i in [0, 1]:
        top_distance = (
            hot_side_holes_top_distance_back
            if i == 0
            else hot_side_holes_top_distance_front
        )
        current_side_hole = translate(
            0,
            -top_distance,
            -hot_side_holes_back_distance - i * hot_side_holes_y_pitch,
        )(hot_side_hole)
        side_holes_drills = side_holes_drills.fuse(current_side_hole)
        hot_side_holes.append(current_side_hole)

        hot_side_mount_hole = create_cylinder(mount_hole_diameter / 2, big_thing)
        hot_side_mount_hole = rotate(90, axis=(0, 1, 0))(hot_side_mount_hole)
        hot_side_mount_hole = align(
            hot_side_mount_hole,
            current_side_hole,
            Alignment.CENTER,
        )
        hot_side_mount_hole = align(
            hot_side_mount_hole,
            front,
            Alignment.STACK_RIGHT,
        )
        hot_side_mount_holes.append(hot_side_mount_hole)

    motor_holes = []
    mount_holes = []
    motor_hole_drills = PartCollector()

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            for tb in [Alignment.TOP, Alignment.BOTTOM]:
                if tb == Alignment.TOP and lr == Alignment.LEFT:
                    continue

                hole = create_cylinder(hot_side_hole_radius, big_thing)
                hole = rotate(90, axis=(0, 1, 0))(hole)
                hole = align(hole, motor, Alignment.CENTER)
                hole = align(
                    hole,
                    motor,
                    lr.stack_alignment,
                    stack_gap=-side_holes_depth,
                )
                hole = translate(
                    0,
                    tb.sign * motor_hole_z_pitch / 2,
                    fb.sign * motor_hole_y_pitch / 2,
                )(hole)
                motor_hole_drills = motor_hole_drills.fuse(hole)
                motor_holes.append(hole)

                mount_hole = create_cylinder(mount_hole_diameter / 2, big_thing)
                mount_hole = rotate(90, axis=(0, 1, 0))(mount_hole)
                mount_hole = align(mount_hole, hole, Alignment.CENTER)
                mount_hole = align(mount_hole, motor, lr.stack_alignment)
                mount_holes.append(mount_hole)

    motor_hole_drills = LeaderFollowersCuttersPart(motor_hole_drills)
    for i, hole in enumerate(motor_holes):
        motor_hole_drills.add_named_cutter(hole, f"motor_hole_{i}")
        motor_hole_drills.add_named_cutter(mount_holes[i], f"mount_hole_{i}")
    for i, hole in enumerate(hot_side_mount_holes):
        motor_hole_drills.add_named_cutter(hole, f"hot_side_mount_hole_{i}")

    motor_hole_drills = align(motor_hole_drills, motor, Alignment.CENTER)
    motor = motor.cut(motor_hole_drills.leader)

    retval = motor.fuse(front.leader)
    retval = retval.cut(mount_hole_cutter)
    retval = retval.cut(side_holes_drills)

    retval = LeaderFollowersCuttersPart(retval)
    for i, hole in enumerate(hot_side_holes):
        retval.add_named_cutter(hole, f"hot_side_hole_{i}")
    for cutter_name, cutter in motor_hole_drills.get_named_cutter_items():
        retval.add_named_cutter(cutter, cutter_name)

    hotend = create_cylinder(hotend_diameter / 2, hotend_length)

    points = []
    polygon_size = nozzle_diameter
    for i in range(6):
        angle = i * math.pi / 3
        x = polygon_size * 0.5 * math.cos(angle)
        y = polygon_size * 0.5 * math.sin(angle)
        points.append((x, y))

    nozzle_screw = create_extruded_polygon(points, nozzle_screw_length)
    nozzle_screw = align(nozzle_screw, hotend, Alignment.CENTER)
    nozzle_screw = align(nozzle_screw, hotend, Alignment.STACK_TOP)
    hotend = hotend.fuse(nozzle_screw)

    nozzle = create_cone(nozzle_diameter / 2, nozzle_tip_diameter / 2, nozzle_length)
    nozzle = align(nozzle, hotend, Alignment.CENTER)
    nozzle = align(nozzle, hotend, Alignment.STACK_TOP)
    hotend = hotend.fuse(nozzle)

    hotend = rotate(180, axis=(1, 0, 0))(hotend)
    hotend = align(hotend, cooler, Alignment.CENTER)
    hotend = align(hotend, retval, Alignment.STACK_BOTTOM)
    hotend = align(hotend, retval, Alignment.BACK)
    hotend = align(hotend, retval, Alignment.LEFT)
    hotend = translate(
        hotend_x_distance_from_right_edge - hotend_diameter / 2,
        -nozzle_y_offset + hotend_diameter / 2,
        0,
    )(hotend)

    hotend_size = get_bounding_box_size(hotend)
    assert math.isclose(
        hotend_size[2],
        hotend_overall_length,
        rel_tol=0.0,
        abs_tol=1e-6,
    ), f"Hotend overall length is {hotend_size[2]}, expected {hotend_overall_length}"
    retval.add_named_non_production_part(hotend, "hotend")

    lever = create_box(lever_thickness, lever_width, lever_length)
    lever = align(lever, front, Alignment.CENTER)
    lever = align(lever, front, Alignment.STACK_TOP)
    lever = align(lever, front, Alignment.BACK)
    lever = translate(-lever_center_offset, 0, lever_front_inset)(lever)

    lever_bbox = get_bounding_box(lever)
    lever_rotation_center = (
        (lever_bbox[0][0] + lever_bbox[1][0]) / 2,
        0,
        lever_bbox[0][2],
    )
    lever = rotate(
        -lever_angle,
        axis=(0, 1, 0),
        center=lever_rotation_center,
    )(lever)
    lever = translate(-lever_center_offset, -lever_front_inset, 0)(lever)
    retval.add_named_non_production_part(lever, "lever")

    fan_size = 30
    fan = create_box(fan_thickness, fan_size, front_size[2])

    fan_hole_diameter = 28
    fan_hole_top_distance = 1.5
    fan_hole_cutter = create_cylinder(
        fan_hole_diameter / 2,
        BIG_THING,
        direction=(1, 0, 0),
    )

    fan_hole_cutter = align(fan_hole_cutter, fan, Alignment.CENTER)
    fan_hole_cutter = align(fan_hole_cutter, fan, Alignment.TOP)
    fan_hole_cutter = translate(0, 0, -fan_hole_top_distance)(fan_hole_cutter)

    fan = fan.cut(fan_hole_cutter)

    fan = align(fan, front, Alignment.CENTER)
    fan = align(fan, front, Alignment.BACK)
    fan = align(fan, front, Alignment.STACK_LEFT)
    retval.add_named_non_production_part(fan, "fan")
    retval.add_named_cutter(mount_hole_cutter, "mount_hole_cutter")

    return retval
