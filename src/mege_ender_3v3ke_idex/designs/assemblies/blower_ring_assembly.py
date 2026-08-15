"""Standalone blower ring assembly."""

import math

from shellforgepy.simple import *

BLOWERS_NOZZLE_TIP_SCALE_MIN = 0.25
BLOWERS_NOZZLE_TIP_SCALE_MAX = 0.75
BIG_THING = 500


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
    ring_center_reference = create_box(
        0.1,
        0.1,
        0.1,
        origin=(-0.05, -0.05, feeder_ring_height / 2 - 0.05),
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

    blower_lip_overlap = 1.5
    blower_lip_outer_height = 6
    blower_lip_duct_thickness = 3

    blower_lip_overall_height = feeder_ring_height / 4

    blower_lip_outer_radius = feeder_ring_inner_diameter / 2 + blower_lip_overlap

    blower_bite_cutter_angle = 360 - feeder_ring_angle

    blower_lip_average_radius = (
        blower_lip_outer_radius + blowers_nozzle_center_distance
    ) / 2

    blower_lip_equivalent_angle_for_wall = (
        feeder_ring_wall / blower_lip_average_radius * (180 / math.pi)
    )

    blower_duct_bite_cutter_angle = (
        blower_bite_cutter_angle + 2 * blower_lip_equivalent_angle_for_wall
    )
    blower_lip_connector_cutter_angle = 360 - blower_duct_bite_cutter_angle

    blower_lip_duct_outer_radius = feeder_ring_inner_diameter / 2 + feeder_ring_wall
    blower_lip_duct = create_ring(
        blower_lip_duct_outer_radius,
        feeder_ring_inner_diameter / 2,
        blower_lip_duct_thickness,
        angle=blower_lip_connector_cutter_angle,
    )

    blower_lip_duct = align(blower_lip_duct, feeder_ring, Alignment.BOTTOM)

    blower_lip_duct = translate(0, 0, feeder_ring_wall)(blower_lip_duct)

    blower_lip_duct_cone = create_cone(
        feeder_ring_inner_diameter / 2,
        blowers_nozzle_center_distance,
        blower_lip_overall_height,
        angle=blower_lip_connector_cutter_angle,
    )
    blower_lip_duct_cone = rotate(180, axis=(1, 0, 0))(blower_lip_duct_cone)
    blower_lip_duct_cone = rotate(-90)(blower_lip_duct_cone)

    blower_lip_duct_cone = align(
        blower_lip_duct_cone, blower_lip_duct, Alignment.STACK_BOTTOM
    )

    blower_lip_duct_top = create_cylinder(
        feeder_ring_inner_diameter / 2,
        blower_lip_duct_thickness,
        angle=blower_lip_connector_cutter_angle,
    )
    blower_lip_duct_top = align(blower_lip_duct_top, blower_lip_duct, Alignment.TOP)

    blower_lip_duct_top_cutter = create_cone(
        feeder_ring_inner_diameter / 2,
        blowers_nozzle_center_distance,
        blower_lip_overall_height,
    )

    blower_lip_duct_top_cutter = rotate(180, axis=(1, 0, 0))(blower_lip_duct_top_cutter)

    blower_lip_duct_top_cutter = align(
        blower_lip_duct_top_cutter, blower_lip_duct_top, Alignment.TOP
    )

    blower_lip_duct_center_cutter = create_cylinder(
        blowers_nozzle_center_distance - 2, 500
    )
    blower_lip_duct_center_cutter = align(
        blower_lip_duct_center_cutter, blower_lip_duct, Alignment.CENTER, axes=[2]
    )

    blower_lip_duct = blower_lip_duct.fuse(blower_lip_duct_cone)
    blower_lip_duct = blower_lip_duct.fuse(blower_lip_duct_top)

    blower_lip_duct = blower_lip_duct.cut(blower_lip_duct_top_cutter)
    blower_lip_duct = blower_lip_duct.cut(blower_lip_duct_center_cutter)

    blower_lip_duct = feeder_ring_rotation(blower_lip_duct)
    blower_lip_duct = rotate(180 - blower_lip_equivalent_angle_for_wall)(
        blower_lip_duct
    )

    blower_lip_duct_inner_walls = PartCollector()

    blower_lip_duct_inner_wall_width = 1
    blower_lip_duct_num_inner_walls = 5

    for i in range(blower_lip_duct_num_inner_walls):

        inner_wall = create_box(500, blower_lip_duct_inner_wall_width, 500)
        inner_wall = rotate(i * 360 / blower_lip_duct_num_inner_walls)(inner_wall)
        blower_lip_duct_inner_walls = blower_lip_duct_inner_walls.fuse(inner_wall)

    blower_lip_duct_inner_walls = align(
        blower_lip_duct_inner_walls, blower_lip_duct, Alignment.CENTER, axes=[2]
    )

    blower_lip_duct = blower_lip_duct.cut(blower_lip_duct_inner_walls)

    blower_lip_cone = create_cone(
        blower_lip_outer_radius,
        blowers_nozzle_center_distance,
        feeder_ring_height / 4,
        angle=feeder_ring_angle,
    )
    blower_lip_cone = rotate(180, axis=(1, 0, 0))(blower_lip_cone)

    blower_lip_top = create_cylinder(
        blower_lip_outer_radius, blower_lip_outer_height, angle=feeder_ring_angle
    )
    blower_lip_top = rotate(180, axis=(1, 0, 0))(blower_lip_top)

    blower_lip_top = align(blower_lip_top, blower_lip_cone, Alignment.STACK_TOP)
    blower_lip = blower_lip_cone.fuse(blower_lip_top)

    blower_lip_top_cutter = create_cone(
        blower_lip_outer_radius, blowers_nozzle_center_distance, feeder_ring_height / 4
    )
    blower_lip_top_cutter = rotate(180, axis=(1, 0, 0))(blower_lip_top_cutter)

    blower_lip_top_cutter = align(blower_lip_top_cutter, blower_lip_top, Alignment.TOP)

    blower_lip = blower_lip.cut(blower_lip_top_cutter)

    blower_lip = rotate(-90 - blower_lip_equivalent_angle_for_wall)(blower_lip)

    blower_lip_center_cutter = create_cylinder(blowers_nozzle_center_distance, 500)

    blower_lip_center_cutter = align(
        blower_lip_center_cutter, blower_lip, Alignment.CENTER, axes=[2]
    )
    blower_lip = blower_lip.cut(blower_lip_center_cutter)

    blower_lip = rotate(feeder_ring_rotation_angle + 180)(blower_lip)

    blower_lip = align(
        blower_lip,
        blower_lip_duct,
        Alignment.TOP,
    )

    blower_lip = translate(
        0, 0, (blower_lip_outer_height - blower_lip_duct_thickness) / 2
    )(blower_lip)

    blower_ring = feeder_ring
    blower_ring = blower_ring.cut(feeder_ring_cutter)

    blower_ring = rotate(feeder_ring_rotation_angle + 180, axis=(0, 0, 1))(blower_ring)
    feeder_ring = rotate(feeder_ring_rotation_angle + 180, axis=(0, 0, 1))(feeder_ring)
    ring_center_reference = rotate(
        feeder_ring_rotation_angle + 180,
        axis=(0, 0, 1),
    )(ring_center_reference)

    blower_ring = blower_ring.fuse(blower_lip)
    blower_ring = blower_ring.cut(blower_lip_duct)
    feeder_ring = feeder_ring.cut(blower_lip_duct)

    blower_ring_bbox = get_bounding_box(blower_ring)
    bottom_normalization = translate(0, 0, -blower_ring_bbox[0][2])
    blower_ring = bottom_normalization(blower_ring)
    ring_center_reference = bottom_normalization(ring_center_reference)
    feeder_ring = bottom_normalization(feeder_ring)
    blower_lip_duct = bottom_normalization(blower_lip_duct)
    blower_lip = bottom_normalization(blower_lip)

    central_cutter = create_cylinder(
        feeder_ring_inner_diameter / 2 + 2 * feeder_ring_wall, BIG_THING
    )

    central_cutter = align(central_cutter, blower_ring, Alignment.TOP)
    central_cutter = translate(0, 0, -2 * feeder_ring_wall)(central_cutter)

    bottom_cutter = create_ring(
        feeder_ring_outer_radius, feeder_ring_inner_radius, BIG_THING
    )
    bottom_cutter = align(bottom_cutter, blower_ring, Alignment.TOP)
    bottom_cutter = translate(0, 0, -feeder_ring_height + feeder_ring_wall)(
        bottom_cutter
    )

    central_cutter = central_cutter.fuse(bottom_cutter)

    blower_ring, central_blower = take_bite_out_of(blower_ring, central_cutter)

    # Now add joining screws
    joining_screw_size = "M2.5"
    joining_screw_length = 10
    joining_screw_num_screws = 4
    boss_height = 5
    boss_diameter = MScrew.from_size(joining_screw_size).cylinder_head_diameter + 0.5

    joining_screw_circle_radius = (
        feeder_ring_inner_diameter / 2 + feeder_ring_outer_radius
    ) / 2

    joining_screws = None
    for i in range(joining_screw_num_screws):

        angle = i * feeder_ring_angle / (joining_screw_num_screws)

        screw_assembly = create_complete_screw_assembly(
            size=joining_screw_size,
            length=joining_screw_length,
            hole_type=HoleType.SELF_THREADING,
            extra_hole_length=1,
        )
        boss = create_cylinder(boss_diameter / 2, boss_height)

        boss = align(boss, screw_assembly, Alignment.BOTTOM)

        screw_assembly.add_named_non_production_part(boss, "boss")

        screw_assembly = rotate(180, axis=(1, 0, 0))(screw_assembly)

        screw_assembly = translate(joining_screw_circle_radius, 0, 0)(screw_assembly)
        screw_assembly = rotate(angle)(screw_assembly)

        screw_assembly = screw_assembly.prefixed_copy(f"joining_screw_{i+1}")

        if joining_screws is None:
            joining_screws = screw_assembly
        else:
            joining_screws = joining_screws.fuse(screw_assembly)

    joining_screws = rotate(180)(joining_screws)
    joining_screws = align(joining_screws, feeder_ring, Alignment.BOTTOM)

    retval = LeaderFollowersCuttersPart(blower_ring)

    screw_clearance_hole_cutters = PartCollector()

    for name, screw_part in joining_screws.get_named_non_production_part_items():
        if "complete_screw" in name:
            retval.add_named_non_production_part(screw_part, name)

            clearance_hole = create_cylinder(
                MScrew.from_size(joining_screw_size).clearance_hole_loose / 2,
                BIG_THING,
            )
            clearance_hole = align(clearance_hole, screw_part, Alignment.CENTER)
            screw_clearance_hole_cutters = screw_clearance_hole_cutters.fuse(
                clearance_hole
            )

        if "boss" in name:
            retval = retval.fuse(screw_part)

    retval = joining_screws.use_as_cutter_on(retval)
    central_blower = central_blower.cut(screw_clearance_hole_cutters)

    retval.add_named_non_production_part(
        ring_center_reference,
        "ring_center_reference",
    )
    retval.set_hidden_by_default("ring_center_reference")
    retval.add_named_follower(feeder_ring, "feeder_ring")

    feeder_ring_bottom_cutter = create_box(BIG_THING, BIG_THING, BIG_THING)
    feeder_ring_bottom_cutter = align(
        feeder_ring_bottom_cutter, feeder_ring, Alignment.CENTER
    )
    feeder_ring_bottom_cutter = align(
        feeder_ring_bottom_cutter, feeder_ring, Alignment.BOTTOM
    )

    feeder_ring_bottom_cutter = translate(0, 0, feeder_ring_wall)(
        feeder_ring_bottom_cutter
    )

    feeder_ring_bottom = feeder_ring.cut(feeder_ring_bottom_cutter)
    retval.add_named_non_production_part(feeder_ring_bottom, "feeder_ring_bottom")
    retval.set_hidden_by_default("feeder_ring_bottom")

    retval.add_named_non_production_part(blower_lip_duct, "blower_lip_duct")
    retval.set_hidden_by_default("blower_lip_duct")

    retval.add_named_non_production_part(blower_lip, "blower_lip")
    retval.set_hidden_by_default("blower_lip")

    retval.add_named_follower(central_blower, "central_blower")

    return retval
