"""Simplified blower reference assembly."""

from shellforgepy.simple import *


def create_blower_assembly(
    *,
    blower_body_size,
    blower_thickness,
    blower_hole_diameter,
    blower_mount_hole_diameter,
    blower_wall_thickness,
    blower_left_body_size_reduction,
    blower_outlet_inner_height,
    blower_outlet_inner_width,
    blower_mount_hole_1_center_y_offset,
    blower_mount_hole_1_center_x_offset,
    blower_mount_hole_2_center_y_offset,
    blower_mount_hole_2_center_x_offset,
    blower_outlet_end_from_center,
):
    """Create the blower body as a cylindrical reference volume."""

    center_reference = create_box(0.01, 0.01, 0.01)

    body_raw = create_cylinder(blower_body_size / 2, blower_thickness)
    body_raw = align(body_raw, center_reference, Alignment.CENTER)
    body_raw = align(body_raw, center_reference, Alignment.BOTTOM)

    body, _ = cut_in_two(body_raw, cut_normal=(1, 0, 0))

    left_body = create_cylinder(blower_body_size / 2, blower_thickness)
    left_body = align(left_body, center_reference, Alignment.CENTER)
    left_body = align(left_body, center_reference, Alignment.BOTTOM)

    _, left_body = cut_in_two(
        left_body,
        cut_normal=(1, 0, 0),
        cut_thickness=blower_left_body_size_reduction,
    )

    left_body = align(left_body, center_reference, Alignment.STACK_LEFT)

    body = body.fuse(left_body)

    blower_hole = create_cylinder(blower_hole_diameter / 2, 200)
    blower_hole = align(blower_hole, body_raw, Alignment.CENTER)
    blower_hole = align(blower_hole, body_raw, Alignment.BOTTOM)
    blower_hole = translate(0, 0, blower_wall_thickness)(blower_hole)

    body = body.cut(blower_hole)

    blower_inner_space_cutter = create_cylinder(
        blower_body_size / 2 - blower_wall_thickness - blower_left_body_size_reduction,
        blower_thickness - 2 * blower_wall_thickness,
    )
    blower_inner_space_cutter = align(blower_inner_space_cutter, body, Alignment.CENTER)
    body = body.cut(blower_inner_space_cutter)
    duct_cutter = create_box(
        blower_body_size / 2, blower_outlet_inner_height, blower_outlet_inner_width
    )
    duct_cutter = align(duct_cutter, body, Alignment.CENTER)
    duct_cutter = align(duct_cutter, center_reference, Alignment.STACK_RIGHT)
    duct_cutter = align(duct_cutter, body, Alignment.BACK)

    duct_cutter = translate(-blower_outlet_end_from_center, -blower_wall_thickness, 0)(
        duct_cutter
    )

    duct = materialize_bounding_box(
        duct_cutter,
        y_enlargement=blower_wall_thickness,
        z_enlargement=blower_wall_thickness,
    )

    duct = duct.cut(duct_cutter)
    duct = duct.cut(blower_inner_space_cutter)

    body = body.cut(duct_cutter)
    body = body.fuse(duct)

    return body
