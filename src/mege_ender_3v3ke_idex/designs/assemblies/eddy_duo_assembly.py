"""BIGTREETECH Eddy Duo probe reference assembly."""

from shellforgepy.simple import *


def create_eddy_duo_assembly(
    *,
    eddy_duo_width,
    eddy_duo_depth,
    eddy_duo_height,
    eddy_duo_main_body_depth,
    eddy_duo_upper_section_height,
    eddy_duo_top_flat_width,
    eddy_duo_top_flat_depth,
    eddy_duo_top_facet_height,
    eddy_duo_base_lip_height,
    eddy_duo_lower_flat_width,
    eddy_duo_mounting_hole_diameter,
    eddy_duo_mounting_hole_spacing,
    eddy_duo_mounting_hole_center_from_top,
    eddy_duo_coil_center_depth_offset,
    eddy_duo_fiducial_outer_ring_diameter,
    eddy_duo_fiducial_inner_ring_diameter,
    eddy_duo_fiducial_cross_length,
    eddy_duo_fiducial_stroke_width,
    eddy_duo_fiducial_marking_height,
):
    """Create a simplified, dimensionally accurate Eddy Duo reference model."""

    lower_section_height = eddy_duo_height - eddy_duo_upper_section_height

    full_body = create_box(eddy_duo_width, eddy_duo_depth, eddy_duo_height)
    front_lip_depth = eddy_duo_depth - eddy_duo_main_body_depth

    front_cutter = create_box(500, 500, 500)

    front_cutter = align(front_cutter, full_body, Alignment.CENTER)
    front_cutter = align(front_cutter, full_body, Alignment.BOTTOM)
    front_cutter = align(
        front_cutter, full_body, Alignment.STACK_FRONT, stack_gap=-front_lip_depth
    )
    front_cutter = translate(0, 0, lower_section_height)(front_cutter)

    body = full_body.cut(front_cutter)

    front_lip = create_pyramid_stump(
        eddy_duo_width,
        eddy_duo_lower_flat_width,
        2 * lower_section_height,
        2 * eddy_duo_base_lip_height,
        front_lip_depth,
    )

    front_lip, _ = cut_in_two(front_lip, cut_normal=(0, 1, 0))

    front_lip = rotate(90, axis=(1, 0, 0))(front_lip)

    front_lip = align(front_lip, body, Alignment.CENTER)
    front_lip = align(front_lip, body, Alignment.FRONT)
    front_lip = align(front_lip, body, Alignment.BOTTOM)

    front_lip_cutter = materialize_bounding_box(front_lip)
    body = body.cut(front_lip_cutter)

    top_facet = create_pyramid_stump(
        eddy_duo_width,
        eddy_duo_width,
        2 * eddy_duo_main_body_depth,
        2 * eddy_duo_top_flat_depth,
        eddy_duo_top_facet_height,
    )
    top_facet, _ = cut_in_two(top_facet, cut_normal=(0, 1, 0))

    top_facet = rotate(180)(top_facet)

    top_facet = align(top_facet, body, Alignment.CENTER)
    top_facet = align(top_facet, body, Alignment.TOP)
    top_facet = align(top_facet, body, Alignment.FRONT)

    top_facet_cutter = materialize_bounding_box(top_facet)
    body = body.cut(top_facet_cutter)
    body = body.fuse(top_facet)
    body = body.fuse(front_lip)

    mounting_holes = []
    mounting_hole_center_height = (
        eddy_duo_height - eddy_duo_mounting_hole_center_from_top
    )
    for side in (-1, 1):
        mounting_hole = create_cylinder(
            eddy_duo_mounting_hole_diameter / 2,
            eddy_duo_depth * 2,
            direction=(0, 1, 0),
        )
        mounting_hole = align(mounting_hole, body, Alignment.CENTER)
        mounting_hole = translate(
            side * eddy_duo_mounting_hole_spacing / 2,
            0,
            mounting_hole_center_height - eddy_duo_height / 2,
        )(mounting_hole)
        body = body.cut(mounting_hole)
        mounting_holes.append(mounting_hole)

    outer_ring = create_cylinder(
        eddy_duo_fiducial_outer_ring_diameter / 2,
        eddy_duo_fiducial_marking_height,
    )
    outer_ring_inner_cutter = create_cylinder(
        eddy_duo_fiducial_outer_ring_diameter / 2 - eddy_duo_fiducial_stroke_width,
        eddy_duo_fiducial_marking_height + 2,
    )
    outer_ring_inner_cutter = align(
        outer_ring_inner_cutter,
        outer_ring,
        Alignment.CENTER,
    )
    outer_ring = outer_ring.cut(outer_ring_inner_cutter)
    outer_ring = align(outer_ring, body, Alignment.CENTER)
    outer_ring = align(outer_ring, body, Alignment.STACK_BOTTOM)
    outer_ring = translate(0, eddy_duo_coil_center_depth_offset, 0)(outer_ring)

    inner_ring = create_cylinder(
        eddy_duo_fiducial_inner_ring_diameter / 2,
        eddy_duo_fiducial_marking_height,
    )
    inner_ring_inner_cutter = create_cylinder(
        eddy_duo_fiducial_inner_ring_diameter / 2 - eddy_duo_fiducial_stroke_width,
        eddy_duo_fiducial_marking_height + 2,
    )
    inner_ring_inner_cutter = align(
        inner_ring_inner_cutter,
        inner_ring,
        Alignment.CENTER,
    )
    inner_ring = inner_ring.cut(inner_ring_inner_cutter)
    inner_ring = align(inner_ring, body, Alignment.CENTER)
    inner_ring = align(inner_ring, body, Alignment.STACK_BOTTOM)
    inner_ring = translate(0, eddy_duo_coil_center_depth_offset, 0)(inner_ring)

    cross_x = create_box(
        eddy_duo_fiducial_cross_length,
        eddy_duo_fiducial_stroke_width,
        eddy_duo_fiducial_marking_height,
    )
    cross_x = align(cross_x, body, Alignment.CENTER)
    cross_x = align(cross_x, body, Alignment.STACK_BOTTOM)
    cross_x = translate(0, eddy_duo_coil_center_depth_offset, 0)(cross_x)

    cross_y = create_box(
        eddy_duo_fiducial_stroke_width,
        eddy_duo_fiducial_cross_length,
        eddy_duo_fiducial_marking_height,
    )
    cross_y = align(cross_y, body, Alignment.CENTER)
    cross_y = align(cross_y, body, Alignment.STACK_BOTTOM)
    cross_y = translate(0, eddy_duo_coil_center_depth_offset, 0)(cross_y)

    fiducial = outer_ring.fuse(inner_ring).fuse(cross_x).fuse(cross_y)
    fiducial = align(fiducial, body, Alignment.STACK_BOTTOM)

    eddy_duo = LeaderFollowersCuttersPart(leader=body)
    eddy_duo.add_named_cutter(mounting_holes[0], "mounting_hole_left")
    eddy_duo.add_named_cutter(mounting_holes[1], "mounting_hole_right")
    eddy_duo.add_named_non_production_part(fiducial, "fiducial")

    return eddy_duo
