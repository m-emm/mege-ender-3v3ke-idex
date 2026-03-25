import math

from shellforgepy.simple import *


def create_hollow_profile(
    profile_length, prifile_depth, profile_height, wall_thickness
):
    outer = create_box(profile_length, prifile_depth, profile_height)
    inner = create_box(
        profile_length - 2 * wall_thickness,
        prifile_depth - 2 * wall_thickness,
        profile_height - 2 * wall_thickness,
    )
    inner = align(inner, outer, Alignment.CENTER)
    return outer.cut(inner)


def create_hollow_profile_ring(
    outer_diameter, profile_depth, profile_height, wall_thickness, angle=None
):

    ring = create_ring(
        outer_diameter / 2,
        outer_diameter / 2 - profile_depth,
        profile_height,
        angle=angle,
    )

    cutter_angle = None

    if angle is not None:
        average_radius = outer_diameter / 2 - profile_depth / 2
        wall_thickness_angle = math.degrees(wall_thickness / average_radius)
        wall_angle = 2 * wall_thickness_angle
        cutter_angle = angle - wall_angle

    inner_cutter = create_ring(
        (outer_diameter - 2 * wall_thickness) / 2,
        (outer_diameter + 2 * wall_thickness) / 2 - profile_depth,
        profile_height - 2 * wall_thickness,
        angle=cutter_angle,
    )
    if angle is not None:
        inner_cutter = rotate(wall_angle / 2)(inner_cutter)

    inner_cutter = align(inner_cutter, ring, Alignment.CENTER, axes=[2])

    return ring.cut(inner_cutter)
