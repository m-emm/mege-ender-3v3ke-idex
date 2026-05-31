"""Printable TPU umbilical cable guide for the x-axis."""

from shellforgepy.simple import *


def _create_centered_arc_band(centerline_radius, radial_thickness, depth):
    inner_radius = centerline_radius - radial_thickness / 2
    outer_radius = centerline_radius + radial_thickness / 2

    return create_ring_segment_between_points(
        p1=(-centerline_radius, 0, 0),
        p2=(centerline_radius, 0, 0),
        third_point_on_plane=(0, 0, -centerline_radius),
        inner_radius=inner_radius,
        outer_radius=outer_radius,
        height=depth,
    )


def create_umbilical_guide_assembly(
    *,
    x_axis_umbilical_guide_radius,
    x_axis_umbilical_guide_cable_diameter,
    x_axis_umbilical_guide_inner_width,
    x_axis_umbilical_guide_wall_thickness,
    x_axis_umbilical_guide_depth,
):
    """Create a front-open TPU U-channel following a semicircular x-axis path."""

    del x_axis_umbilical_guide_cable_diameter

    radius = x_axis_umbilical_guide_radius
    inner_width = x_axis_umbilical_guide_inner_width
    wall_thickness = x_axis_umbilical_guide_wall_thickness
    depth = x_axis_umbilical_guide_depth

    channel_inner_radius = radius - inner_width / 2
    channel_outer_radius = radius + inner_width / 2
    outside_inner_radius = channel_inner_radius - wall_thickness
    outside_outer_radius = channel_outer_radius + wall_thickness

    inner_side_wall = create_ring_segment_between_points(
        p1=(
            -(outside_inner_radius + channel_inner_radius) / 2,
            0,
            0,
        ),
        p2=((outside_inner_radius + channel_inner_radius) / 2, 0, 0),
        third_point_on_plane=(
            0,
            0,
            -(outside_inner_radius + channel_inner_radius) / 2,
        ),
        inner_radius=outside_inner_radius,
        outer_radius=channel_inner_radius,
        height=depth,
    )

    outer_side_wall = create_ring_segment_between_points(
        p1=(
            -(channel_outer_radius + outside_outer_radius) / 2,
            0,
            0,
        ),
        p2=((channel_outer_radius + outside_outer_radius) / 2, 0, 0),
        third_point_on_plane=(
            0,
            0,
            -(channel_outer_radius + outside_outer_radius) / 2,
        ),
        inner_radius=channel_outer_radius,
        outer_radius=outside_outer_radius,
        height=depth,
    )

    side_walls = inner_side_wall.fuse(outer_side_wall)

    back_wall = _create_centered_arc_band(
        radius,
        inner_width + 2 * wall_thickness,
        wall_thickness,
    )
    back_wall = align(back_wall, side_walls, Alignment.BACK)

    guide = side_walls.fuse(back_wall)
    return LeaderFollowersCuttersPart(leader=guide)
