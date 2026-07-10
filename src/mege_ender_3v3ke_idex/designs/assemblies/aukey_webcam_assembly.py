"""Standalone Aukey webcam reference mock assembly."""

import math

from shellforgepy.simple import *


def create_aukey_webcam_assembly(
    *,
    aukey_webcam_body_width,
    aukey_webcam_body_depth,
    aukey_webcam_body_height,
    aukey_webcam_lens_diameter,
    aukey_webcam_lens_depth,
    aukey_webcam_holder_front_width,
    aukey_webcam_holder_back_width,
    aukey_webcam_holder_thickness,
    aukey_webcam_holder_depth,
    aukey_webcam_body_to_holder_gap,
    aukey_webcam_body_cutter_angle,
    aukey_webcam_holder_back_offset,
    aukey_webcam_holder_link_cylinder_diameter,
    aukey_webcam_holder_link_cylinder_height,
):
    body = create_rounded_slab(
        aukey_webcam_body_width,
        2 * aukey_webcam_body_depth,
        aukey_webcam_body_height,
        aukey_webcam_body_depth,
    )
    body, _ = cut_in_two(body, cut_normal=(0, 1, 0))

    body_cutter = create_box(600, 500, 500)
    body_cutter = align(body_cutter, body, Alignment.CENTER)

    body_cutter_keepout = create_pyramid_stump(
        aukey_webcam_body_width,
        aukey_webcam_body_width,
        aukey_webcam_body_height,
        aukey_webcam_body_height
        - (aukey_webcam_body_depth)
        * math.tan(math.radians(aukey_webcam_body_cutter_angle)),
        aukey_webcam_body_depth,
    )

    body_cutter_keepout = rotate(-90, axis=(1, 0, 0))(body_cutter_keepout)
    body_cutter_keepout = align(body_cutter_keepout, body, Alignment.CENTER)
    body_cutter_keepout = align(body_cutter_keepout, body, Alignment.FRONT)

    body_cutter = body_cutter.cut(body_cutter_keepout)

    body = body.cut(body_cutter)

    lens = create_cylinder(aukey_webcam_lens_diameter / 2, aukey_webcam_lens_depth)
    lens = rotate(90, axis=(1, 0, 0))(lens)
    lens = align(lens, body, Alignment.CENTER)
    lens = align(
        lens, body, Alignment.STACK_FRONT, stack_gap=-aukey_webcam_lens_depth / 2
    )

    bottom_holder = create_pyramid_stump(
        aukey_webcam_holder_front_width,
        aukey_webcam_holder_back_width,
        aukey_webcam_holder_thickness,
        aukey_webcam_holder_thickness,
        aukey_webcam_holder_depth,
    )
    bottom_holder = rotate(-90, axis=(1, 0, 0))(bottom_holder)
    bottom_holder = align(bottom_holder, body, Alignment.CENTER)
    bottom_holder = align(
        bottom_holder,
        body,
        Alignment.STACK_BOTTOM,
        stack_gap=aukey_webcam_body_to_holder_gap,
    )

    bottom_holder = align(bottom_holder, body, Alignment.FRONT)
    bottom_holder = translate(0, aukey_webcam_holder_back_offset, 0)(bottom_holder)

    bottom_holder_link_cylinder = create_cylinder(
        aukey_webcam_holder_link_cylinder_diameter / 2,
        aukey_webcam_holder_link_cylinder_height,
    )

    bottom_holder_link_cylinder = align(
        bottom_holder_link_cylinder, body, Alignment.CENTER
    )
    bottom_holder_link_cylinder = align(
        bottom_holder_link_cylinder, body, Alignment.EDGE_BACK
    )

    bottom_holder_link_cylinder = align(
        bottom_holder_link_cylinder, bottom_holder, Alignment.EDGE_TOP
    )

    bottom_holder = bottom_holder.fuse(bottom_holder_link_cylinder)

    assembly = LeaderFollowersCuttersPart(leader=body)
    assembly.add_named_non_production_part(lens, "lens")
    assembly.add_named_non_production_part(bottom_holder, "bottom_holder")
    return assembly
