"""Declarative part fan assembly."""

import math

from shellforgepy.simple import *

BLOWERS_NOZZLE_TIP_SCALE_MIN = 0.25
BLOWERS_NOZZLE_TIP_SCALE_MAX = 0.75


def _shortest_angle_distance_degrees(angle_a, angle_b):
    return abs((angle_a - angle_b + 180) % 360 - 180)


def _rotate_xy(point, angle_degrees):
    x, y = point
    angle = math.radians(angle_degrees)
    return (
        x * math.cos(angle) - y * math.sin(angle),
        x * math.sin(angle) + y * math.cos(angle),
    )


def _blower_nozzle_tip_angle_degrees(
    *,
    blower_index,
    num_blowers,
    feeder_ring_inner_diameter,
    blowers_nozzle_center_distance,
    feeder_ring_wall,
    blowers_down_angle,
    blowers_duct_diameter,
    blower_center_offset,
    feeder_ring_rotation_angle,
):
    blower_tube_length = (
        feeder_ring_inner_diameter / 2
        - blowers_nozzle_center_distance
        + feeder_ring_wall
    ) + math.tan(math.radians(blowers_down_angle)) * blowers_duct_diameter
    nozzle_tip_x = blower_tube_length + (
        blowers_nozzle_center_distance - blower_tube_length
    ) * math.cos(math.radians(-blowers_down_angle))
    nozzle_tip_y = blower_center_offset
    nozzle_tip_x, nozzle_tip_y = _rotate_xy(
        (nozzle_tip_x, nozzle_tip_y),
        blower_index * 360 / num_blowers + feeder_ring_rotation_angle,
    )
    return math.degrees(math.atan2(nozzle_tip_y, nozzle_tip_x)) % 360


def _blower_fan_entry_angle_degrees(
    *,
    feeder_ring_inner_diameter,
    feeder_ring_width,
    feeder_ring_wall,
):
    feeder_ring_inner_radius = feeder_ring_inner_diameter / 2
    feeder_ring_outer_radius = (
        feeder_ring_inner_radius + feeder_ring_width + feeder_ring_wall
    )
    feeder_ring_average_radius = (
        feeder_ring_outer_radius + feeder_ring_inner_radius
    ) / 2
    fan_entry_x = -(feeder_ring_inner_radius + feeder_ring_wall)
    fan_entry_y = math.sqrt(max(feeder_ring_average_radius**2 - fan_entry_x**2, 0))
    return math.degrees(math.atan2(fan_entry_y, fan_entry_x)) % 360


def _blower_feeder_ring_path_metrics(
    *,
    num_blowers,
    feeder_ring_inner_diameter,
    blowers_nozzle_center_distance,
    feeder_ring_width,
    feeder_ring_wall,
    blowers_down_angle,
    blowers_duct_diameter,
    blower_center_offset,
    feeder_ring_rotation_angle,
):
    feeder_ring_inner_radius = feeder_ring_inner_diameter / 2
    feeder_ring_outer_radius = (
        feeder_ring_inner_radius + feeder_ring_width + feeder_ring_wall
    )
    feeder_ring_average_radius = (
        feeder_ring_outer_radius + feeder_ring_inner_radius
    ) / 2
    fan_entry_angle_degrees = _blower_fan_entry_angle_degrees(
        feeder_ring_inner_diameter=feeder_ring_inner_diameter,
        feeder_ring_width=feeder_ring_width,
        feeder_ring_wall=feeder_ring_wall,
    )

    metrics = []
    for blower_index in range(num_blowers):
        nozzle_tip_angle_degrees = _blower_nozzle_tip_angle_degrees(
            blower_index=blower_index,
            num_blowers=num_blowers,
            feeder_ring_inner_diameter=feeder_ring_inner_diameter,
            blowers_nozzle_center_distance=blowers_nozzle_center_distance,
            feeder_ring_wall=feeder_ring_wall,
            blowers_down_angle=blowers_down_angle,
            blowers_duct_diameter=blowers_duct_diameter,
            blower_center_offset=blower_center_offset,
            feeder_ring_rotation_angle=feeder_ring_rotation_angle,
        )
        path_angle_degrees = _shortest_angle_distance_degrees(
            nozzle_tip_angle_degrees,
            fan_entry_angle_degrees,
        )
        path_length = feeder_ring_average_radius * math.radians(path_angle_degrees)
        metrics.append(
            {
                "fan_entry_angle_degrees": fan_entry_angle_degrees,
                "nozzle_tip_angle_degrees": nozzle_tip_angle_degrees,
                "path_angle_degrees": path_angle_degrees,
                "path_length": path_length,
            }
        )
    return metrics


def _blower_nozzle_tip_scales(
    *,
    num_blowers,
    feeder_ring_inner_diameter,
    blowers_nozzle_center_distance,
    feeder_ring_width,
    feeder_ring_wall,
    blowers_down_angle,
    blowers_duct_diameter,
    blower_center_offset,
    feeder_ring_rotation_angle,
):
    metrics = _blower_feeder_ring_path_metrics(
        num_blowers=num_blowers,
        feeder_ring_inner_diameter=feeder_ring_inner_diameter,
        blowers_nozzle_center_distance=blowers_nozzle_center_distance,
        feeder_ring_width=feeder_ring_width,
        feeder_ring_wall=feeder_ring_wall,
        blowers_down_angle=blowers_down_angle,
        blowers_duct_diameter=blowers_duct_diameter,
        blower_center_offset=blower_center_offset,
        feeder_ring_rotation_angle=feeder_ring_rotation_angle,
    )
    path_lengths = [metric["path_length"] for metric in metrics]
    shortest_path = min(path_lengths)
    path_span = max(path_lengths) - shortest_path
    if path_span <= 0:
        return [0.4 for _ in path_lengths]

    return [
        BLOWERS_NOZZLE_TIP_SCALE_MIN
        + (path_length - shortest_path)
        / path_span
        * (BLOWERS_NOZZLE_TIP_SCALE_MAX - BLOWERS_NOZZLE_TIP_SCALE_MIN)
        for path_length in path_lengths
    ]


def _create_duct_extension(
    *,
    duct_extension_width,
    part_fan_duct_extension_length,
    feeder_ring_height,
    feeder_ring_wall,
):
    duct_extension_body = create_box(
        duct_extension_width,
        part_fan_duct_extension_length,
        feeder_ring_height,
    )
    duct_extension_cutter = create_box(
        duct_extension_width - feeder_ring_wall * 2,
        part_fan_duct_extension_length - 2 * feeder_ring_wall,
        feeder_ring_height - 2 * feeder_ring_wall,
    )
    duct_extension_cutter = align(
        duct_extension_cutter,
        duct_extension_body,
        Alignment.CENTER,
    )

    duct_extension = duct_extension_body.cut(duct_extension_cutter)
    retval = LeaderFollowersCuttersPart(duct_extension)
    retval.add_named_cutter(duct_extension_body, "duct_extension_body_cutter")
    return retval


def _create_ducts(
    *,
    num_blowers,
    feeder_ring_inner_diameter,
    blowers_nozzle_center_distance,
    feeder_ring_wall,
    blowers_down_angle,
    blowers_duct_diameter,
    blowers_wall,
    blower_center_offset,
    feeder_ring_extra_angle,
    feeder_ring_width,
    feeder_ring_height,
    feeder_ring_rotation_angle,
    duct_extension_width,
    part_fan_duct_extension_length,
):
    blower_tube_cutters = PartCollector()
    blower_tubes = PartCollector()
    blowers_nozzle_tip_scales = _blower_nozzle_tip_scales(
        num_blowers=num_blowers,
        feeder_ring_inner_diameter=feeder_ring_inner_diameter,
        blowers_nozzle_center_distance=blowers_nozzle_center_distance,
        feeder_ring_width=feeder_ring_width,
        feeder_ring_wall=feeder_ring_wall,
        blowers_down_angle=blowers_down_angle,
        blowers_duct_diameter=blowers_duct_diameter,
        blower_center_offset=blower_center_offset,
        feeder_ring_rotation_angle=feeder_ring_rotation_angle,
    )
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

        blower_tube_bb = get_bounding_box(blower_tube)
        blower_tube_length = blower_tube_bb[1][0] - blower_tube_bb[0][0]
        blower_tube_center = get_bounding_box_center(blower_tube)

        blowers_nozzle_tip_scale = blowers_nozzle_tip_scales[i]

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
            return x, y, new_z

        blower_tube = transform_with_function_tesselating(
            blower_tube,
            blower_tip_transform_function,
        )

        blower_tube = translate(
            blowers_nozzle_center_distance,
            blower_center_offset,
            0,
        )(blower_tube)

        blower_tube_cutter = create_cylinder(
            blowers_duct_diameter / 2,
            blower_tube_length + 2 * blowers_wall,
            direction=(1, 0, 0),
        )
        blower_tube_cutter = transform_with_function_tesselating(
            blower_tube_cutter,
            blower_tip_transform_function,
        )
        blower_tube_cutter = align(
            blower_tube_cutter,
            blower_tube,
            Alignment.CENTER,
        )

        blower_tube = rotate(
            -blowers_down_angle,
            axis=(0, 1, 0),
            center=(blower_tube_length, 0, 0),
        )(blower_tube)
        blower_tube_cutter = rotate(
            -blowers_down_angle,
            axis=(0, 1, 0),
            center=(blower_tube_length, 0, 0),
        )(blower_tube_cutter)

        angle = i * 360 / num_blowers
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
        feeder_ring_cutter,
        feeder_ring,
        Alignment.CENTER,
        axes=[2],
    )
    feeder_ring = feeder_ring.cut(feeder_ring_cutter)

    feeder_ring_rotation = rotate(-(360 / num_blowers - 360 / (num_blowers + 1)) / 2)
    feeder_ring = feeder_ring_rotation(feeder_ring)
    feeder_ring_cutter = feeder_ring_rotation(feeder_ring_cutter)

    retval = blower_tubes.fuse(feeder_ring)
    retval = retval.cut(blower_tube_cutters)
    retval = retval.cut(feeder_ring_cutter)
    retval = rotate(feeder_ring_rotation_angle, axis=(0, 0, 1))(retval)

    retval_bbox = get_bounding_box(retval)
    duct_extension = _create_duct_extension(
        duct_extension_width=duct_extension_width,
        part_fan_duct_extension_length=part_fan_duct_extension_length,
        feeder_ring_height=feeder_ring_height,
        feeder_ring_wall=feeder_ring_wall,
    )
    duct_extension = align(duct_extension, retval, Alignment.TOP)
    duct_extension = align(duct_extension, retval, Alignment.LEFT)
    duct_extension = align(duct_extension, retval, Alignment.FRONT)

    duct_bbox_size = get_bounding_box_size(retval)
    duct_extension = translate(
        -duct_extension_width + feeder_ring_width,
        duct_bbox_size[1] / 2,
        0,
    )(duct_extension)

    duct_extension = duct_extension.cut(feeder_ring_cutter)
    retval = retval.cut(duct_extension.get_named_cutter("duct_extension_body_cutter"))
    retval = retval.fuse(duct_extension.leader)
    retval = translate(0, 0, -retval_bbox[0][2])(retval)
    return retval


def _create_part_fan(
    *,
    part_fan_size,
    part_fan_thickness,
    part_fan_fillet_radius,
    part_fan_screw_size,
    part_fan_screw_hole_inset,
    part_fan_screw_mount_base_thickness,
    part_fan_screw_mount_cutout_size,
    part_fan_hole_diameter,
    part_fan_axis_from_left_offset,
    part_fan_window_width,
    part_fan_window_height,
    part_fan_outlet_connector_length,
    big_thing,
    window_cutter_outside_length=0,
    body_cutter_clearance=None,
    outlet_length=2,
    outlet_wall,
    outlet_clearance=0.2,
    outlet_inner_duct_length=3.5,
    mount_plate_thickness=None,
    mount_plate_blow_direction_oversize=0,
    mount_plate_cross_oversize=0,
    mount_plate_blow_direction_offset=0,
    part_fan_nut_cutter_clearance=0.15,
):
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

    screw_hole_cutters_map = {}
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            hole = create_cylinder(
                screw_hole_diameter / 2,
                part_fan_thickness + 2 * mount_plate_thickness,
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
        part_fan_size / 2 + window_cutter_outside_length,
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

    retval = LeaderFollowersCuttersPart(body)
    retval.add_named_cutter(window_cutter, "window_cutter")

    for (lr, fb), hole in screw_hole_cutters_map.items():
        retval.add_named_cutter(
            hole,
            f"screw_hole_cutters_{lr.name.lower()}_{fb.name.lower()}",
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

        outlet_inner_duct_cutter = create_box(
            part_fan_window_width - 2 * outlet_clearance - 2 * outlet_wall,
            big_thing,
            part_fan_window_height - 2 * outlet_clearance - 2 * outlet_wall,
        )
        outlet_inner_duct_cutter = align(
            outlet_inner_duct_cutter,
            outlet_inner_duct,
            Alignment.CENTER,
        )
        outlet_inner_duct = outlet_inner_duct.cut(outlet_inner_duct_cutter)
        outlet = outlet.fuse(outlet_inner_duct)
        retval.add_named_follower(outlet, "outlet")

    return retval


def _create_angled_fans(
    *,
    left_part_fan_parameters,
    right_part_fan_parameters,
    part_fan_window_cutter_outside_length,
    part_fan_body_cutter_clearance,
    part_fan_mount_plate_thickness,
    part_fan_size,
    part_fan_thickness,
    part_fan_fillet_radius,
    part_fan_screw_size,
    part_fan_screw_hole_inset,
    part_fan_screw_mount_base_thickness,
    part_fan_screw_mount_cutout_size,
    part_fan_hole_diameter,
    part_fan_axis_from_left_offset,
    part_fan_window_width,
    part_fan_window_height,
    part_fan_outlet_connector_length,
    part_fan_nut_cutter_clearance,
    part_fan_outlet_wall,
    big_thing,
):
    fans = PartCollector()
    center_pillar = create_cylinder(0.01, 50)
    fan_parts_by_name = {}
    fan_parameters_by_side = {
        Alignment.LEFT: left_part_fan_parameters,
        Alignment.RIGHT: right_part_fan_parameters,
    }
    # In the current toolhead-local coordinate system, the "left" configured
    # fan becomes the side-mounted blower, while the "right" configured fan
    # sits at the front of the hotend.
    fan_name_by_side = {
        Alignment.LEFT: "side_fan",
        Alignment.RIGHT: "front_fan",
    }

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        fan_parameters = fan_parameters_by_side[lr]
        fan = _create_part_fan(
            part_fan_size=part_fan_size,
            part_fan_thickness=part_fan_thickness,
            part_fan_fillet_radius=part_fan_fillet_radius,
            part_fan_screw_size=part_fan_screw_size,
            part_fan_screw_hole_inset=part_fan_screw_hole_inset,
            part_fan_screw_mount_base_thickness=part_fan_screw_mount_base_thickness,
            part_fan_screw_mount_cutout_size=part_fan_screw_mount_cutout_size,
            part_fan_hole_diameter=part_fan_hole_diameter,
            part_fan_axis_from_left_offset=part_fan_axis_from_left_offset,
            part_fan_window_width=part_fan_window_width,
            part_fan_window_height=part_fan_window_height,
            part_fan_outlet_connector_length=part_fan_outlet_connector_length,
            part_fan_nut_cutter_clearance=part_fan_nut_cutter_clearance,
            big_thing=big_thing,
            window_cutter_outside_length=part_fan_window_cutter_outside_length,
            body_cutter_clearance=part_fan_body_cutter_clearance,
            mount_plate_blow_direction_oversize=fan_parameters[
                "mount_plate_blow_direction_oversize"
            ],
            mount_plate_cross_oversize=fan_parameters["mount_plate_cross_oversize"],
            mount_plate_blow_direction_offset=fan_parameters[
                "mount_plate_blow_direction_offset"
            ],
            mount_plate_thickness=part_fan_mount_plate_thickness,
            outlet_wall=part_fan_outlet_wall,
        )
        fan = rotate(180, axis=(1, 0, 0))(fan)
        fan = rotate(lr.sign * 90)(fan)
        fan = align(fan, None, Alignment.CENTER)
        fan = rotate(
            -lr.sign * fan_parameters["rotation"],
            axis=(0, 1, 0),
            center=(-lr.sign * part_fan_size / 2, 0, -part_fan_thickness / 2),
        )(fan)
        fan = rotate(-fan_parameters["tilt"], axis=(1, 0, 0))(fan)
        fan = align(fan, center_pillar, lr.stack_alignment)
        fan = translate(lr.sign * fan_parameters["x_offset"], 0, 0)(fan)
        fan = rotate(lr.sign * fan_parameters["around_angle"], axis=(0, 0, 1))(fan)
        fan = translate(0, fan_parameters["y_offset"], fan_parameters["z_offset"])(fan)
        fan = fan.prefixed_copy(f"part_fan_{lr.name.lower()}")
        fan_parts_by_name[fan_name_by_side[lr]] = fan
        fans = fans.fuse(fan)

    return fans, fan_parts_by_name


def _align_fans_to_sprite_extruder(fans, sprite_extruder):
    hotend = sprite_extruder.get_named_non_production_part("hotend")
    hotend_center = get_bounding_box_center(hotend)
    hotend_bbox = get_bounding_box(hotend)
    return translate(hotend_center[0], hotend_center[1], hotend_bbox[0][2])(fans)


def _extend_blower_ducts(
    *,
    blower_ducts,
    sprite_extruder,
    tool_head_additional_mount_plate_clearance,
    tool_head_additional_mount_plate_depth,
    tool_head_additional_mount_plate_depth_offset,
    tool_head_additional_mount_plate_fillet_radius,
    tool_head_additional_mount_plate_height,
    tool_head_additional_mount_plate_thickness,
    tool_head_additional_mount_plate_z_offset,
    tool_head_front_mount_plate_connector_height,
    tool_head_front_mount_plate_connector_thickness,
    tool_head_front_mount_plate_connector_width,
    duct_front_mount_plate_height,
    duct_front_mount_plate_height_border,
    duct_front_mount_plate_offset,
    duct_front_mount_plate_thickness,
    duct_front_mount_plate_width,
    duct_front_mount_plate_width_border,
):
    side_mount_plate = create_filleted_box(
        tool_head_additional_mount_plate_thickness,
        tool_head_additional_mount_plate_depth,
        tool_head_additional_mount_plate_height,
        tool_head_additional_mount_plate_fillet_radius,
        no_fillets_at=[Alignment.LEFT, Alignment.RIGHT, Alignment.BOTTOM],
    )
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.CENTER)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.BACK)
    side_mount_plate = align(side_mount_plate, sprite_extruder, Alignment.BOTTOM)
    side_mount_plate = align(
        side_mount_plate,
        sprite_extruder,
        Alignment.STACK_RIGHT,
        stack_gap=tool_head_additional_mount_plate_clearance,
    )
    side_mount_plate = translate(
        0,
        tool_head_additional_mount_plate_depth_offset,
        tool_head_additional_mount_plate_z_offset,
    )(side_mount_plate)
    blower_ducts = blower_ducts.fuse(side_mount_plate)

    duct_front_mount_plate = create_box(
        duct_front_mount_plate_width,
        duct_front_mount_plate_height,
        duct_front_mount_plate_thickness,
    )
    cutout_width = (
        duct_front_mount_plate_width - 2 * duct_front_mount_plate_width_border
    )
    cutout_height = (
        duct_front_mount_plate_height - 2 * duct_front_mount_plate_height_border
    )
    cutout_fillet_radius = min(cutout_width, cutout_height) / 4

    duct_front_mount_plate_cutout = create_filleted_box(
        cutout_width,
        cutout_height,
        duct_front_mount_plate_thickness + 10,
        fillet_radius=cutout_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )
    duct_front_mount_plate_cutout = align(
        duct_front_mount_plate_cutout,
        duct_front_mount_plate,
        Alignment.CENTER,
    )
    duct_front_mount_plate = duct_front_mount_plate.cut(duct_front_mount_plate_cutout)
    duct_front_mount_plate = rotate(90, axis=(1, 0, 0))(duct_front_mount_plate)
    duct_front_mount_plate = align(
        duct_front_mount_plate,
        sprite_extruder,
        Alignment.CENTER,
    )
    duct_front_mount_plate = align(
        duct_front_mount_plate,
        sprite_extruder,
        Alignment.STACK_FRONT,
    )
    duct_front_mount_plate = align(
        duct_front_mount_plate,
        sprite_extruder,
        Alignment.BOTTOM,
    )
    duct_front_mount_plate = translate(0, 0, duct_front_mount_plate_offset)(
        duct_front_mount_plate
    )

    duct_front_mount_plate_connector = create_box(
        tool_head_front_mount_plate_connector_width,
        tool_head_front_mount_plate_connector_thickness,
        tool_head_front_mount_plate_connector_height,
    )
    duct_front_mount_plate_connector = align(
        duct_front_mount_plate_connector,
        duct_front_mount_plate,
        Alignment.BACK,
    )
    duct_front_mount_plate_connector = align(
        duct_front_mount_plate_connector,
        duct_front_mount_plate,
        Alignment.STACK_BOTTOM,
    )
    duct_front_mount_plate_connector = align(
        duct_front_mount_plate_connector,
        duct_front_mount_plate,
        Alignment.LEFT,
    )

    duct_front_flange = create_box(
        tool_head_front_mount_plate_connector_width,
        tool_head_front_mount_plate_connector_width,
        tool_head_front_mount_plate_connector_thickness,
    )

    duct_front_flange = align(
        duct_front_flange,
        duct_front_mount_plate_connector,
        Alignment.CENTER,
    )
    duct_front_flange = align(
        duct_front_flange,
        duct_front_mount_plate_connector,
        Alignment.STACK_FRONT,
    )
    duct_front_flange = align(
        duct_front_flange,
        duct_front_mount_plate_connector,
        Alignment.TOP,
    )

    blower_ducts = blower_ducts.fuse(duct_front_mount_plate_connector)
    blower_ducts = blower_ducts.fuse(duct_front_flange)

    for _, cutter in sprite_extruder.get_named_cutter_items():
        blower_ducts = blower_ducts.cut(cutter)

    return blower_ducts


def create_part_fan_assembly(
    *,
    sprite_extruder,
    blower_center_offset,
    blowers_down_angle,
    blowers_duct_diameter,
    blowers_nozzle_center_distance,
    blowers_wall,
    duct_extension_width,
    feeder_ring_extra_angle,
    feeder_ring_height,
    feeder_ring_inner_diameter,
    feeder_ring_rotation_angle,
    feeder_ring_wall,
    feeder_ring_width,
    num_blowers,
    part_fan_axis_from_left_offset,
    part_fan_body_cutter_clearance,
    part_fan_clearance,
    part_fan_outlet_wall,
    part_fan_duct_extension_length,
    part_fan_ducts_clearance,
    part_fan_fillet_radius,
    part_fan_hole_diameter,
    part_fan_mount_plate_thickness,
    part_fan_nut_cutter_clearance,
    part_fan_outlet_connector_length,
    part_fan_screw_hole_inset,
    part_fan_screw_mount_base_thickness,
    part_fan_screw_mount_cutout_size,
    part_fan_screw_size,
    part_fan_size,
    part_fan_thickness,
    part_fan_window_cutter_outside_length,
    part_fan_window_height,
    part_fan_window_width,
    tool_head_additional_mount_plate_clearance,
    tool_head_additional_mount_plate_depth,
    tool_head_additional_mount_plate_depth_offset,
    tool_head_additional_mount_plate_fillet_radius,
    tool_head_additional_mount_plate_height,
    tool_head_additional_mount_plate_thickness,
    tool_head_additional_mount_plate_z_offset,
    tool_head_front_mount_plate_connector_height,
    tool_head_front_mount_plate_connector_thickness,
    tool_head_front_mount_plate_connector_width,
    duct_front_mount_plate_height,
    duct_front_mount_plate_height_border,
    duct_front_mount_plate_offset,
    duct_front_mount_plate_thickness,
    duct_front_mount_plate_width,
    duct_front_mount_plate_width_border,
    left_part_fan_parameters,
    right_part_fan_parameters,
    BIG_THING,
):
    """Create the standalone part fan assembly."""

    big_thing = BIG_THING
    fans, fan_parts_by_name = _create_angled_fans(
        left_part_fan_parameters=left_part_fan_parameters,
        right_part_fan_parameters=right_part_fan_parameters,
        part_fan_window_cutter_outside_length=part_fan_window_cutter_outside_length,
        part_fan_body_cutter_clearance=part_fan_body_cutter_clearance,
        part_fan_mount_plate_thickness=part_fan_mount_plate_thickness,
        part_fan_size=part_fan_size,
        part_fan_thickness=part_fan_thickness,
        part_fan_fillet_radius=part_fan_fillet_radius,
        part_fan_screw_size=part_fan_screw_size,
        part_fan_screw_hole_inset=part_fan_screw_hole_inset,
        part_fan_screw_mount_base_thickness=part_fan_screw_mount_base_thickness,
        part_fan_screw_mount_cutout_size=part_fan_screw_mount_cutout_size,
        part_fan_hole_diameter=part_fan_hole_diameter,
        part_fan_axis_from_left_offset=part_fan_axis_from_left_offset,
        part_fan_window_width=part_fan_window_width,
        part_fan_window_height=part_fan_window_height,
        part_fan_outlet_connector_length=part_fan_outlet_connector_length,
        part_fan_nut_cutter_clearance=part_fan_nut_cutter_clearance,
        part_fan_outlet_wall=part_fan_outlet_wall,
        big_thing=big_thing,
    )

    ducts = _create_ducts(
        num_blowers=num_blowers,
        feeder_ring_inner_diameter=feeder_ring_inner_diameter,
        blowers_nozzle_center_distance=blowers_nozzle_center_distance,
        feeder_ring_wall=feeder_ring_wall,
        blowers_down_angle=blowers_down_angle,
        blowers_duct_diameter=blowers_duct_diameter,
        blowers_wall=blowers_wall,
        blower_center_offset=blower_center_offset,
        feeder_ring_extra_angle=feeder_ring_extra_angle,
        feeder_ring_width=feeder_ring_width,
        feeder_ring_height=feeder_ring_height,
        feeder_ring_rotation_angle=feeder_ring_rotation_angle,
        duct_extension_width=duct_extension_width,
        part_fan_duct_extension_length=part_fan_duct_extension_length,
    )

    ducts = translate(0, 0, part_fan_ducts_clearance)(ducts)
    ducts_bbox = get_bounding_box(ducts)
    fans = translate(0, 0, ducts_bbox[1][2])(fans)
    fan_parts_by_name = {
        name: translate(0, 0, ducts_bbox[1][2])(fan)
        for name, fan in fan_parts_by_name.items()
    }

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
    hotend_alignment_reference = create_box(
        0.1,
        0.1,
        0.1,
        origin=(-0.05, -0.05, 0),
    )
    fans.add_named_non_production_part(
        hotend_alignment_reference,
        "hotend_alignment_reference",
    )
    fans = _align_fans_to_sprite_extruder(fans, sprite_extruder)
    fan_parts_by_name = {
        name: _align_fans_to_sprite_extruder(fan, sprite_extruder)
        for name, fan in fan_parts_by_name.items()
    }

    blower_ducts = fans.get_named_follower("blower_ducts")
    blower_ducts = _extend_blower_ducts(
        blower_ducts=blower_ducts,
        sprite_extruder=sprite_extruder,
        tool_head_additional_mount_plate_clearance=tool_head_additional_mount_plate_clearance,
        tool_head_additional_mount_plate_depth=tool_head_additional_mount_plate_depth,
        tool_head_additional_mount_plate_depth_offset=tool_head_additional_mount_plate_depth_offset,
        tool_head_additional_mount_plate_fillet_radius=tool_head_additional_mount_plate_fillet_radius,
        tool_head_additional_mount_plate_height=tool_head_additional_mount_plate_height,
        tool_head_additional_mount_plate_thickness=tool_head_additional_mount_plate_thickness,
        tool_head_additional_mount_plate_z_offset=tool_head_additional_mount_plate_z_offset,
        tool_head_front_mount_plate_connector_height=tool_head_front_mount_plate_connector_height,
        tool_head_front_mount_plate_connector_thickness=tool_head_front_mount_plate_connector_thickness,
        tool_head_front_mount_plate_connector_width=tool_head_front_mount_plate_connector_width,
        duct_front_mount_plate_height=duct_front_mount_plate_height,
        duct_front_mount_plate_height_border=duct_front_mount_plate_height_border,
        duct_front_mount_plate_offset=duct_front_mount_plate_offset,
        duct_front_mount_plate_thickness=duct_front_mount_plate_thickness,
        duct_front_mount_plate_width=duct_front_mount_plate_width,
        duct_front_mount_plate_width_border=duct_front_mount_plate_width_border,
    )
    blower_ducts = blower_ducts.cut(expand(fans.leader, part_fan_clearance))
    blower_ducts_index = fans.follower_indices_by_name["blower_ducts"]
    fans.followers[blower_ducts_index] = blower_ducts

    retval = LeaderFollowersCuttersPart(blower_ducts)
    for name, fan in fan_parts_by_name.items():
        retval.add_named_non_production_part(fan.leader, name)
    retval.add_named_non_production_part(
        fans.get_named_non_production_part("hotend_alignment_reference"),
        "hotend_alignment_reference",
    )
    return retval
