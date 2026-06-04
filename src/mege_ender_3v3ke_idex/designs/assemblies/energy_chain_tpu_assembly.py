"""TPU energy chain skeleton assembly."""

import math

from mege_ender_3v3ke_idex.designs.plug_and_hole import create_plug
from shellforgepy.simple import *

BIG_THING = 500


def _spiral_antiderivative(radius, spiral_b):
    return 0.5 * (
        radius * math.sqrt(radius * radius + spiral_b * spiral_b)
        + spiral_b
        * spiral_b
        * math.log(radius + math.sqrt(radius * radius + spiral_b * spiral_b))
    )


def _spiral_arc_length(theta, outer_radius, spiral_b):
    radius = outer_radius - spiral_b * theta
    return (
        _spiral_antiderivative(outer_radius, spiral_b)
        - _spiral_antiderivative(radius, spiral_b)
    ) / spiral_b


def _minimum_outer_spiral_radius(
    *,
    total_path_length,
    inner_radius,
    spiral_revolution_spacing,
):
    spiral_b = spiral_revolution_spacing / (2 * math.pi)
    lower = inner_radius + 1e-6
    upper = max(lower + spiral_revolution_spacing, lower + total_path_length / math.pi)

    def available_length(radius):
        theta_end = (radius - inner_radius) / spiral_b
        return _spiral_arc_length(theta_end, radius, spiral_b)

    while available_length(upper) < total_path_length:
        upper *= 2

    for _ in range(80):
        middle = (lower + upper) / 2
        if available_length(middle) < total_path_length:
            lower = middle
        else:
            upper = middle

    return upper, spiral_b


def _theta_at_spiral_length(target_length, outer_radius, spiral_b):
    lower = 0
    upper = outer_radius / spiral_b

    for _ in range(80):
        middle = (lower + upper) / 2
        if _spiral_arc_length(middle, outer_radius, spiral_b) < target_length:
            lower = middle
        else:
            upper = middle

    return upper


def _spiral_point(path_length, outer_radius, spiral_b):
    theta = _theta_at_spiral_length(path_length, outer_radius, spiral_b)
    radius = outer_radius - spiral_b * theta
    return radius * math.cos(theta), radius * math.sin(theta)


def _rotate_xy(point, angle_degrees):
    angle = math.radians(angle_degrees)
    x, y = point
    return (
        x * math.cos(angle) - y * math.sin(angle),
        x * math.sin(angle) + y * math.cos(angle),
    )


def _placed_xy(local_point, position, angle_degrees):
    rotated = _rotate_xy(local_point, angle_degrees)
    return position[0] + rotated[0], position[1] + rotated[1]


def _normalize_degrees(angle):
    return (angle + 180) % 360 - 180


def _normalize_3d(vector):
    length = math.sqrt(sum(component * component for component in vector))
    return tuple(component / length for component in vector)


def _dot_3d(left, right):
    return sum(a * b for a, b in zip(left, right))


def _cross_3d(left, right):
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _create_energy_chain_tpu_link(
    *,
    energy_chain_width,
    energy_chain_base_thickness,
    energy_chain_link_length,
    energy_chain_plug_diameter,
    energy_chain_plug_angle_deg,
    energy_chain_plug_height,
    energy_chain_plug_slit_width,
    energy_chain_plug_base_thickness,
    energy_chain_plug_fillet_radius,
    energy_chain_plug_wall_thickness,
    energy_chain_plug_lip_height,
    energy_chain_plug_lip_size,
    energy_chain_plug_lip_top_gap,
    energy_chain_plug_hole_slack,
    energy_chain_channel_wall_thickness,
    energy_chain_channel_link_thickness,
    energy_chain_channel_link_width,
    energy_chain_channel_height,
    energy_chain_plug_plate_width,
    include_non_production_part,
):
    """Create one printable TPU energy-chain link in local coordinates."""

    closure_rotation_center = (
        energy_chain_base_thickness
        + energy_chain_channel_height
        + energy_chain_channel_link_width / 2,
        0,
        energy_chain_channel_link_thickness * 0.75,
    )

    fixed_link_body = PartCollector()

    plate = create_box(
        energy_chain_base_thickness,
        energy_chain_link_length,
        energy_chain_width,
    )

    fixed_link_body = fixed_link_body.fuse(plate)

    channel_wall_1 = create_box(
        energy_chain_channel_height,
        energy_chain_link_length,
        energy_chain_channel_wall_thickness,
    )

    channel_wall_1 = align(channel_wall_1, plate, Alignment.CENTER)
    channel_wall_1 = align(channel_wall_1, plate, Alignment.BOTTOM)
    channel_wall_1 = align(channel_wall_1, plate, Alignment.STACK_RIGHT)
    fixed_link_body = fixed_link_body.fuse(channel_wall_1)

    channel_link_1 = create_box(
        energy_chain_channel_link_width,
        energy_chain_link_length,
        energy_chain_channel_link_thickness,
    )
    channel_link_1 = align(channel_link_1, channel_wall_1, Alignment.CENTER)
    channel_link_1 = align(channel_link_1, channel_wall_1, Alignment.STACK_RIGHT)
    channel_link_1 = align(channel_link_1, channel_wall_1, Alignment.BOTTOM)
    fixed_link_body = fixed_link_body.fuse(channel_link_1)

    channel_wall_2 = create_box(
        energy_chain_width - energy_chain_plug_plate_width,
        energy_chain_link_length,
        energy_chain_channel_wall_thickness,
    )

    channel_wall_2 = align(channel_wall_2, channel_link_1, Alignment.CENTER)
    channel_wall_2 = align(channel_wall_2, channel_link_1, Alignment.BOTTOM)
    channel_wall_2 = align(channel_wall_2, channel_link_1, Alignment.STACK_RIGHT)

    plug_base = create_box(
        energy_chain_plug_plate_width - energy_chain_channel_link_width,
        energy_chain_link_length,
        energy_chain_channel_wall_thickness + energy_chain_channel_height,
    )

    plug_base = align(plug_base, channel_wall_2, Alignment.CENTER)
    plug_base = align(plug_base, channel_wall_2, Alignment.BOTTOM)
    plug_base = align(plug_base, channel_wall_2, Alignment.STACK_RIGHT)

    channel_wall_2 = channel_wall_2.fuse(plug_base)

    plug = create_plug(
        plug_diameter=energy_chain_plug_diameter,
        plug_angle_deg=energy_chain_plug_angle_deg,
        plug_height=energy_chain_plug_height,
        plug_wall_thickness=energy_chain_plug_wall_thickness,
        plug_base_thickness=energy_chain_plug_base_thickness,
        plug_slit_width=energy_chain_plug_slit_width,
        fillet_radius=energy_chain_plug_fillet_radius,
        plug_lip_height=energy_chain_plug_lip_height,
        plug_lip_size=energy_chain_plug_lip_size,
        plug_lip_top_gap=energy_chain_plug_lip_top_gap,
    )
    plug = align(plug, plug_base, Alignment.CENTER, axes=[0, 1])
    plug = align(plug, plug_base, Alignment.STACK_TOP)
    channel_wall_2 = channel_wall_2.fuse(plug)

    hole_cutter = create_cylinder(
        energy_chain_plug_diameter / 2 + energy_chain_plug_hole_slack,
        BIG_THING,
    )
    hole_cutter = align(hole_cutter, plug, Alignment.CENTER)
    hole_cutter = rotate(-90, axis=(0, 1, 0), center=closure_rotation_center)(
        hole_cutter
    )

    fixed_link_body = fixed_link_body.cut(hole_cutter)
    leader = fixed_link_body.fuse(channel_wall_2)

    retval = LeaderFollowersCuttersPart(leader=leader)
    if include_non_production_part:
        retval.add_named_non_production_part(channel_wall_2, "walls_2")
    return retval


def _create_spiral_connector(
    *,
    current_position,
    current_angle,
    next_position,
    next_angle,
    energy_chain_link_length,
    energy_chain_link_connector_thickness,
    energy_chain_link_connector_width,
    energy_chain_width,
    energy_chain_base_thickness,
):
    connector_embed = min(
        energy_chain_link_length * 0.45,
        max(energy_chain_base_thickness * 1.5, energy_chain_link_connector_width * 3),
    )

    start_xy = _placed_xy(
        (
            energy_chain_link_connector_thickness / 2,
            energy_chain_link_length - connector_embed,
        ),
        current_position,
        current_angle,
    )
    end_xy = _placed_xy(
        (energy_chain_link_connector_thickness / 2, connector_embed),
        next_position,
        next_angle,
    )
    start = (start_xy[0], start_xy[1], energy_chain_width / 2)
    end = (end_xy[0], end_xy[1], energy_chain_width / 2)

    dx = end_xy[0] - start_xy[0]
    dy = end_xy[1] - start_xy[1]
    connector_length = math.hypot(dx, dy)
    connector_length = max(connector_length, 1e-6)
    angle_delta = abs(_normalize_degrees(next_angle - current_angle))

    if angle_delta < 1:
        return _create_straight_spiral_connector(
            start=start,
            end=end,
            connector_length=connector_length,
            energy_chain_link_connector_thickness=energy_chain_link_connector_thickness,
            energy_chain_width=energy_chain_width,
        )

    middle_radius = connector_length / (
        2 * math.sin(math.radians(angle_delta) / 2)
    )
    middle_radius = max(middle_radius, connector_length / 2 + 1e-6)
    inner_radius = middle_radius - energy_chain_link_connector_thickness / 2
    outer_radius = middle_radius + energy_chain_link_connector_thickness / 2
    if inner_radius <= 0:
        return _create_straight_spiral_connector(
            start=start,
            end=end,
            connector_length=connector_length,
            energy_chain_link_connector_thickness=energy_chain_link_connector_thickness,
            energy_chain_width=energy_chain_width,
        )

    midpoint = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    chord_half_length = connector_length / 2
    distance_to_center = math.sqrt(
        max(0, middle_radius * middle_radius - chord_half_length * chord_half_length)
    )
    if distance_to_center <= 1e-6:
        return _create_straight_spiral_connector(
            start=start,
            end=end,
            connector_length=connector_length,
            energy_chain_link_connector_thickness=energy_chain_link_connector_thickness,
            energy_chain_width=energy_chain_width,
        )

    chord_perpendicular = (-dy / connector_length, dx / connector_length)
    center_candidates = [
        (
            midpoint[0] + chord_perpendicular[0] * distance_to_center,
            midpoint[1] + chord_perpendicular[1] * distance_to_center,
            energy_chain_width / 2,
        ),
        (
            midpoint[0] - chord_perpendicular[0] * distance_to_center,
            midpoint[1] - chord_perpendicular[1] * distance_to_center,
            energy_chain_width / 2,
        ),
    ]
    current_direction = (*_rotate_xy((0, 1), current_angle), 0)
    next_direction = (*_rotate_xy((0, 1), next_angle), 0)

    def tangent_score(center):
        edge = (end[0] - start[0], end[1] - start[1], 0)
        center_side = (
            center[0] - midpoint[0],
            center[1] - midpoint[1],
            0,
        )
        plane_normal = _normalize_3d(_cross_3d(edge, center_side))
        start_radius = (start[0] - center[0], start[1] - center[1], 0)
        end_radius = (end[0] - center[0], end[1] - center[1], 0)
        start_tangent = _normalize_3d(_cross_3d(plane_normal, start_radius))
        end_tangent = _normalize_3d(_cross_3d(plane_normal, end_radius))
        return _dot_3d(start_tangent, current_direction) + _dot_3d(
            end_tangent, next_direction
        )

    center = max(center_candidates, key=tangent_score)
    return create_ring_segment_between_points(
        start,
        end,
        center,
        inner_radius,
        outer_radius,
        energy_chain_width,
    )


def _create_straight_spiral_connector(
    *,
    start,
    end,
    connector_length,
    energy_chain_link_connector_thickness,
    energy_chain_width,
):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    connector_angle = math.degrees(math.atan2(dy, dx)) - 90
    connector = create_box(
        energy_chain_link_connector_thickness,
        connector_length,
        energy_chain_width,
        origin=(-energy_chain_link_connector_thickness / 2, -connector_length / 2, 0),
    )
    connector = rotate(connector_angle)(connector)
    return translate((start[0] + end[0]) / 2, (start[1] + end[1]) / 2, 0)(
        connector
    )


def _spiral_link_placements(
    *,
    energy_chain_num_links,
    link_pitch,
    radial_footprint,
    energy_chain_channel_wall_thickness,
):
    total_path_length = energy_chain_num_links * link_pitch
    inner_radius = radial_footprint / 2
    spiral_revolution_spacing = radial_footprint + max(
        1.0, energy_chain_channel_wall_thickness
    )
    outer_radius, spiral_b = _minimum_outer_spiral_radius(
        total_path_length=total_path_length,
        inner_radius=inner_radius,
        spiral_revolution_spacing=spiral_revolution_spacing,
    )

    raw_placements = []
    for index in range(energy_chain_num_links):
        current_point = _spiral_point(index * link_pitch, outer_radius, spiral_b)
        next_point = _spiral_point((index + 1) * link_pitch, outer_radius, spiral_b)
        dx = next_point[0] - current_point[0]
        dy = next_point[1] - current_point[1]
        angle = math.degrees(math.atan2(dy, dx)) - 90
        raw_placements.append((current_point, angle))

    first_point, first_angle = raw_placements[0]
    placements = []
    for current_point, angle in raw_placements:
        normalized_point = _rotate_xy(
            (current_point[0] - first_point[0], current_point[1] - first_point[1]),
            -first_angle,
        )
        placements.append((normalized_point, angle - first_angle))

    return placements


def create_energy_chain_tpu_assembly(
    *,
    energy_chain_num_links,
    energy_chain_width,
    energy_chain_base_thickness,
    energy_chain_link_length,
    energy_chain_link_connector_thickness,
    energy_chain_link_connector_width,
    energy_chain_plug_diameter,
    energy_chain_plug_angle_deg,
    energy_chain_plug_height,
    energy_chain_plug_slit_width,
    energy_chain_plug_base_thickness,
    energy_chain_plug_fillet_radius,
    energy_chain_plug_wall_thickness,
    energy_chain_plug_lip_height,
    energy_chain_plug_lip_size,
    energy_chain_plug_lip_top_gap,
    energy_chain_plug_hole_slack,
    energy_chain_channel_wall_thickness,
    energy_chain_channel_link_thickness,
    energy_chain_channel_link_width,
    energy_chain_channel_height,
    energy_chain_plug_plate_width,
):
    """Create the TPU energy chain as a spiral-printable assembly."""

    link_pitch = energy_chain_link_length + energy_chain_link_connector_width
    link_template = _create_energy_chain_tpu_link(
        energy_chain_width=energy_chain_width,
        energy_chain_base_thickness=energy_chain_base_thickness,
        energy_chain_link_length=energy_chain_link_length,
        energy_chain_plug_diameter=energy_chain_plug_diameter,
        energy_chain_plug_angle_deg=energy_chain_plug_angle_deg,
        energy_chain_plug_height=energy_chain_plug_height,
        energy_chain_plug_slit_width=energy_chain_plug_slit_width,
        energy_chain_plug_base_thickness=energy_chain_plug_base_thickness,
        energy_chain_plug_fillet_radius=energy_chain_plug_fillet_radius,
        energy_chain_plug_wall_thickness=energy_chain_plug_wall_thickness,
        energy_chain_plug_lip_height=energy_chain_plug_lip_height,
        energy_chain_plug_lip_size=energy_chain_plug_lip_size,
        energy_chain_plug_lip_top_gap=energy_chain_plug_lip_top_gap,
        energy_chain_plug_hole_slack=energy_chain_plug_hole_slack,
        energy_chain_channel_wall_thickness=energy_chain_channel_wall_thickness,
        energy_chain_channel_link_thickness=energy_chain_channel_link_thickness,
        energy_chain_channel_link_width=energy_chain_channel_link_width,
        energy_chain_channel_height=energy_chain_channel_height,
        energy_chain_plug_plate_width=energy_chain_plug_plate_width,
        include_non_production_part=True,
    )
    radial_footprint = get_bounding_box_size(link_template.leader)[0]
    placements = _spiral_link_placements(
        energy_chain_num_links=energy_chain_num_links,
        link_pitch=link_pitch,
        radial_footprint=radial_footprint,
        energy_chain_channel_wall_thickness=energy_chain_channel_wall_thickness,
    )

    chain = PartCollector()
    first_walls_2 = None
    for index, (position, angle) in enumerate(placements):
        placed_link = rotate(angle)(link_template)
        placed_link = translate(position[0], position[1], 0)(placed_link)
        chain = chain.fuse(placed_link.leader)

        if index == 0:
            first_walls_2 = placed_link.get_named_non_production_part("walls_2")

    for index, (position, angle) in enumerate(placements[:-1]):
        next_position, next_angle = placements[index + 1]
        connector = _create_spiral_connector(
            current_position=position,
            current_angle=angle,
            next_position=next_position,
            next_angle=next_angle,
            energy_chain_link_length=energy_chain_link_length,
            energy_chain_link_connector_thickness=energy_chain_link_connector_thickness,
            energy_chain_link_connector_width=energy_chain_link_connector_width,
            energy_chain_width=energy_chain_width,
            energy_chain_base_thickness=energy_chain_base_thickness,
        )
        chain = chain.fuse(connector)

    retval = LeaderFollowersCuttersPart(leader=chain)
    retval.add_named_non_production_part(first_walls_2, "walls_2")
    return retval
