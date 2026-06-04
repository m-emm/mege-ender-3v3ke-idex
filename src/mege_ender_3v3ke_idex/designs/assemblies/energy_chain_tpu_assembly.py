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


def _theta_at_spiral_length(
    target_length,
    outer_radius,
    spiral_b,
    minimum_radius,
):
    lower = 0
    upper = (outer_radius - minimum_radius) / spiral_b

    for _ in range(80):
        middle = (lower + upper) / 2
        if _spiral_arc_length(middle, outer_radius, spiral_b) < target_length:
            lower = middle
        else:
            upper = middle

    return upper


def _spiral_radius_at_path_length(path_length, outer_radius, spiral_b, minimum_radius):
    theta = _theta_at_spiral_length(
        path_length,
        outer_radius,
        spiral_b,
        minimum_radius,
    )
    return outer_radius - spiral_b * theta


def _spiral_point(path_length, outer_radius, spiral_b, minimum_radius):
    theta = _theta_at_spiral_length(
        path_length,
        outer_radius,
        spiral_b,
        minimum_radius,
    )
    radius = outer_radius - spiral_b * theta
    return radius * math.cos(theta), radius * math.sin(theta)


def _rotate_xy(point, angle_degrees):
    angle = math.radians(angle_degrees)
    x, y = point
    return (
        x * math.cos(angle) - y * math.sin(angle),
        x * math.sin(angle) + y * math.cos(angle),
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
    start_xy,
    end_xy,
    midpoint_radius,
    energy_chain_link_length,
    energy_chain_link_connector_thickness,
    energy_chain_width,
    current_position,
    current_angle,
    next_position,
    next_angle,
):
    start = (start_xy[0], start_xy[1], energy_chain_width / 2)
    end = (end_xy[0], end_xy[1], energy_chain_width / 2)
    inner_radius = midpoint_radius - energy_chain_link_connector_thickness / 2
    outer_radius = midpoint_radius + energy_chain_link_connector_thickness / 2
    if inner_radius <= 0:
        return _create_straight_spiral_connector(
            start=start,
            end=end,
            energy_chain_link_connector_thickness=energy_chain_link_connector_thickness,
            energy_chain_width=energy_chain_width,
        )

    third_point_on_plane = (0, 0, energy_chain_width / 2)
    connector = create_ring_segment_between_points(
        start,
        end,
        third_point_on_plane,
        inner_radius,
        outer_radius,
        energy_chain_width,
    )
    connector = connector.fuse(
        _create_connector_edge_pad(
            position=current_position,
            angle=current_angle,
            local_edge_y=energy_chain_link_length,
            inside_direction=-1,
            energy_chain_link_connector_thickness=energy_chain_link_connector_thickness,
            energy_chain_width=energy_chain_width,
        )
    )
    return connector.fuse(
        _create_connector_edge_pad(
            position=next_position,
            angle=next_angle,
            local_edge_y=0,
            inside_direction=1,
            energy_chain_link_connector_thickness=energy_chain_link_connector_thickness,
            energy_chain_width=energy_chain_width,
        )
    )


def _create_connector_edge_pad(
    *,
    position,
    angle,
    local_edge_y,
    inside_direction,
    energy_chain_link_connector_thickness,
    energy_chain_width,
):
    pad_overlap = 0.2
    pad_length = 2 * pad_overlap
    origin_y = -pad_overlap if inside_direction > 0 else -pad_length + pad_overlap
    pad = create_box(
        energy_chain_link_connector_thickness,
        pad_length,
        energy_chain_width,
        origin=(0, origin_y, 0),
    )
    pad = translate(0, local_edge_y, 0)(pad)
    pad = rotate(angle)(pad)
    return translate(position[0], position[1], 0)(pad)


def _create_straight_spiral_connector(
    *,
    start,
    end,
    energy_chain_link_connector_thickness,
    energy_chain_width,
):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    connector_length = math.hypot(dx, dy)
    connector_angle = math.degrees(math.atan2(dy, dx)) - 90
    connector = create_box(
        energy_chain_link_connector_thickness,
        connector_length,
        energy_chain_width,
        origin=(-energy_chain_link_connector_thickness / 2, -connector_length / 2, 0),
    )
    connector = rotate(connector_angle)(connector)
    return translate((start[0] + end[0]) / 2, (start[1] + end[1]) / 2, 0)(connector)


def _spiral_link_placements(
    *,
    energy_chain_num_links,
    energy_chain_max_diameter_on_print_bed,
    energy_chain_base_thickness,
    energy_chain_width,
    energy_chain_link_length,
    energy_chain_link_connector_thickness,
    energy_chain_link_connector_width,
    energy_chain_channel_height,
    energy_chain_channel_wall_thickness,
):
    if energy_chain_num_links < 1:
        raise ValueError("energy_chain_num_links must be at least 1")

    radial_footprint = (
        energy_chain_base_thickness + energy_chain_channel_height + energy_chain_width
    )
    connector_lane_x = energy_chain_link_connector_thickness / 2
    outer_radius = energy_chain_max_diameter_on_print_bed / 2 - (
        radial_footprint - connector_lane_x
    )
    minimum_radius = radial_footprint / 2
    spiral_revolution_spacing = radial_footprint + max(
        1.0, energy_chain_channel_wall_thickness
    )
    spiral_b = spiral_revolution_spacing / (2 * math.pi)
    link_pitch = energy_chain_link_length + energy_chain_link_connector_width
    required_path_length = (
        energy_chain_num_links - 1
    ) * link_pitch + energy_chain_link_length
    maximum_theta = (outer_radius - minimum_radius) / spiral_b

    if maximum_theta <= 0:
        raise ValueError(
            "energy_chain_max_diameter_on_print_bed is too small for the link footprint"
        )

    available_path_length = _spiral_arc_length(
        maximum_theta,
        outer_radius,
        spiral_b,
    )
    if required_path_length > available_path_length:
        raise ValueError(
            "Energy chain does not fit in the configured spiral: "
            f"requires {required_path_length:.2f} mm of path, "
            f"but only {available_path_length:.2f} mm are available before "
            f"the centerline radius reaches {minimum_radius:.2f} mm"
        )

    placements = []
    for index in range(energy_chain_num_links):
        start_path_length = index * link_pitch
        end_path_length = start_path_length + energy_chain_link_length
        start_point = _spiral_point(
            start_path_length,
            outer_radius,
            spiral_b,
            minimum_radius,
        )
        end_point = _spiral_point(
            end_path_length,
            outer_radius,
            spiral_b,
            minimum_radius,
        )
        dx = end_point[0] - start_point[0]
        dy = end_point[1] - start_point[1]
        angle = math.degrees(math.atan2(dy, dx)) - 90
        connector_lane_offset = _rotate_xy(
            (connector_lane_x, 0),
            angle,
        )
        position = (
            start_point[0] - connector_lane_offset[0],
            start_point[1] - connector_lane_offset[1],
        )
        placements.append((position, angle))

    return placements, outer_radius, spiral_b, minimum_radius


def create_energy_chain_tpu_assembly(
    *,
    energy_chain_num_links,
    energy_chain_max_diameter_on_print_bed,
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
    placements, outer_radius, spiral_b, minimum_radius = _spiral_link_placements(
        energy_chain_num_links=energy_chain_num_links,
        energy_chain_max_diameter_on_print_bed=(energy_chain_max_diameter_on_print_bed),
        energy_chain_base_thickness=energy_chain_base_thickness,
        energy_chain_width=energy_chain_width,
        energy_chain_link_length=energy_chain_link_length,
        energy_chain_link_connector_thickness=energy_chain_link_connector_thickness,
        energy_chain_link_connector_width=energy_chain_link_connector_width,
        energy_chain_channel_height=energy_chain_channel_height,
        energy_chain_channel_wall_thickness=energy_chain_channel_wall_thickness,
    )
    link_pitch = energy_chain_link_length + energy_chain_link_connector_width

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
        connector_start_path_length = index * link_pitch + energy_chain_link_length
        connector_end_path_length = (index + 1) * link_pitch
        connector = _create_spiral_connector(
            start_xy=_spiral_point(
                connector_start_path_length,
                outer_radius,
                spiral_b,
                minimum_radius,
            ),
            end_xy=_spiral_point(
                connector_end_path_length,
                outer_radius,
                spiral_b,
                minimum_radius,
            ),
            midpoint_radius=_spiral_radius_at_path_length(
                (connector_start_path_length + connector_end_path_length) / 2,
                outer_radius,
                spiral_b,
                minimum_radius,
            ),
            energy_chain_link_length=energy_chain_link_length,
            energy_chain_link_connector_thickness=energy_chain_link_connector_thickness,
            energy_chain_width=energy_chain_width,
            current_position=position,
            current_angle=angle,
            next_position=next_position,
            next_angle=next_angle,
        )
        chain = chain.fuse(connector)

    retval = LeaderFollowersCuttersPart(leader=chain)
    retval.add_named_non_production_part(first_walls_2, "walls_2")
    return retval
