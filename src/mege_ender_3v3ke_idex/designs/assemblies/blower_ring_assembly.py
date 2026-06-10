"""Standalone blower ring assembly."""

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

    path_lengths = []
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
        path_lengths.append(
            feeder_ring_average_radius * math.radians(path_angle_degrees)
        )

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


def _blower_air_squeeze_scale(*, tip_scale, relative_x, blower_tube_length):
    return tip_scale + relative_x / blower_tube_length * (1 - tip_scale)


def _blower_outer_squeeze_scale(
    *,
    air_scale,
    blowers_duct_diameter,
    blowers_wall,
):
    inner_radius = blowers_duct_diameter / 2
    outer_radius = inner_radius + blowers_wall
    return (inner_radius * air_scale + blowers_wall) / outer_radius


def create_blower_ring_assembly(
    *,
    blower_center_offset,
    blowers_down_angle,
    blowers_duct_diameter,
    blowers_nozzle_center_distance,
    blowers_wall,
    feeder_ring_extra_angle,
    feeder_ring_height,
    feeder_ring_inner_diameter,
    feeder_ring_rotation_angle,
    feeder_ring_wall,
    feeder_ring_width,
    num_blowers,
):
    """Create the standalone blower nozzles and feeder ring."""

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

        def squeeze_z_transform_function(point, squeeze_scale_function):
            x, y, z = point
            relative_x = x - blower_tube_bb[0][0]
            air_scale = _blower_air_squeeze_scale(
                tip_scale=blowers_nozzle_tip_scale,
                relative_x=relative_x,
                blower_tube_length=blower_tube_length,
            )
            scale_factor = squeeze_scale_function(air_scale)
            relative_z = z - blower_tube_center[2]
            new_relative_z = relative_z * scale_factor
            new_z = blower_tube_center[2] + new_relative_z
            return x, y, new_z

        def blower_outer_transform_function(point):
            return squeeze_z_transform_function(
                point,
                lambda air_scale: _blower_outer_squeeze_scale(
                    air_scale=air_scale,
                    blowers_duct_diameter=blowers_duct_diameter,
                    blowers_wall=blowers_wall,
                ),
            )

        def blower_air_transform_function(point):
            return squeeze_z_transform_function(point, lambda air_scale: air_scale)

        blower_tube = transform_with_function_tesselating(
            blower_tube,
            blower_outer_transform_function,
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
            blower_air_transform_function,
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

    blower_ring = blower_tubes.fuse(feeder_ring)
    blower_ring = blower_ring.cut(blower_tube_cutters)
    blower_ring = blower_ring.cut(feeder_ring_cutter)
    blower_ring = rotate(feeder_ring_rotation_angle + 180, axis=(0, 0, 1))(blower_ring)

    blower_ring_bbox = get_bounding_box(blower_ring)
    blower_ring = translate(0, 0, -blower_ring_bbox[0][2])(blower_ring)
    return LeaderFollowersCuttersPart(blower_ring)
