"""Panasonic AQ-A AC output SSR reference assembly."""

from shellforgepy.simple import *


def create_panasonic_ssr_assembly(
    *,
    panasonic_ssr_width,
    panasonic_ssr_length,
    panasonic_ssr_height,
    panasonic_ssr_corner_fillet_radius,
    panasonic_ssr_mount_hole_diameter,
    panasonic_ssr_mount_hole_pitch,
    panasonic_ssr_terminal_screw_x_inset,
    panasonic_ssr_output_terminal_y_inset,
    panasonic_ssr_input_terminal_y_inset,
    panasonic_ssr_output_terminal_screw_size,
    panasonic_ssr_input_terminal_screw_size,
    panasonic_ssr_terminal_screw_head_height,
    panasonic_ssr_output_cover_depth,
    panasonic_ssr_input_cover_depth,
    panasonic_ssr_cover_recess_depth,
):
    """Create a datasheet-sized Panasonic AQ-A solid state relay reference."""

    ssr_body = create_filleted_box(
        panasonic_ssr_width,
        panasonic_ssr_length,
        panasonic_ssr_height,
        fillet_radius=panasonic_ssr_corner_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    mounting_holes = PartCollector()
    mounting_hole_y_positions = [
        panasonic_ssr_length / 2 - panasonic_ssr_mount_hole_pitch / 2,
        panasonic_ssr_length / 2 + panasonic_ssr_mount_hole_pitch / 2,
    ]
    for mounting_hole_y in mounting_hole_y_positions:
        mounting_hole = create_cylinder(
            panasonic_ssr_mount_hole_diameter / 2,
            panasonic_ssr_height + 2,
            origin=(panasonic_ssr_width / 2, mounting_hole_y, -1),
        )
        ssr_body = ssr_body.cut(mounting_hole)
        mounting_holes = mounting_holes.fuse(mounting_hole)

    output_cover = create_box(
        panasonic_ssr_width,
        panasonic_ssr_output_cover_depth,
        panasonic_ssr_cover_recess_depth,
        origin=(
            0,
            panasonic_ssr_length - panasonic_ssr_output_cover_depth,
            panasonic_ssr_height - panasonic_ssr_cover_recess_depth,
        ),
    )
    input_cover = create_box(
        panasonic_ssr_width,
        panasonic_ssr_input_cover_depth,
        panasonic_ssr_cover_recess_depth,
        origin=(0, 0, panasonic_ssr_height - panasonic_ssr_cover_recess_depth),
    )

    terminal_x_positions = [
        panasonic_ssr_terminal_screw_x_inset,
        panasonic_ssr_width - panasonic_ssr_terminal_screw_x_inset,
    ]
    output_terminal_screws = PartCollector()
    input_terminal_screws = PartCollector()
    output_screw_radius = (
        MScrew.from_size(
            panasonic_ssr_output_terminal_screw_size
        ).cylinder_head_diameter
        / 2
    )
    input_screw_radius = (
        MScrew.from_size(panasonic_ssr_input_terminal_screw_size).cylinder_head_diameter
        / 2
    )

    for terminal_x in terminal_x_positions:
        output_terminal_screw = create_cylinder(
            output_screw_radius,
            panasonic_ssr_terminal_screw_head_height,
            origin=(
                terminal_x,
                panasonic_ssr_length - panasonic_ssr_output_terminal_y_inset,
                panasonic_ssr_height - panasonic_ssr_terminal_screw_head_height,
            ),
        )
        output_terminal_screws = output_terminal_screws.fuse(output_terminal_screw)

        input_terminal_screw = create_cylinder(
            input_screw_radius,
            panasonic_ssr_terminal_screw_head_height,
            origin=(
                terminal_x,
                panasonic_ssr_input_terminal_y_inset,
                panasonic_ssr_height - panasonic_ssr_terminal_screw_head_height,
            ),
        )
        input_terminal_screws = input_terminal_screws.fuse(input_terminal_screw)

    ssr_reference = ssr_body.fuse(output_cover)
    ssr_reference = ssr_reference.fuse(input_cover)
    ssr_reference = ssr_reference.fuse(output_terminal_screws)
    ssr_reference = ssr_reference.fuse(input_terminal_screws)

    ssr = LeaderFollowersCuttersPart(leader=ssr_body)
    ssr.add_named_follower(ssr_body, "body")
    ssr.add_named_follower(output_cover, "output_terminal_cover")
    ssr.add_named_follower(input_cover, "input_terminal_cover")
    ssr.add_named_follower(output_terminal_screws, "output_terminal_screws")
    ssr.add_named_follower(input_terminal_screws, "input_terminal_screws")
    ssr.add_named_cutter(mounting_holes, "mounting_holes")
    ssr.add_named_cutter(
        mounting_holes,
        "mounting_hole_pattern",
    )
    ssr.add_named_non_production_part(ssr_reference, "reference")

    for mounting_hole_index, mounting_hole_y in enumerate(mounting_hole_y_positions):
        mounting_hole = create_cylinder(
            panasonic_ssr_mount_hole_diameter / 2,
            panasonic_ssr_height + 2,
            origin=(panasonic_ssr_width / 2, mounting_hole_y, -1),
        )
        ssr.add_named_cutter(mounting_hole, f"mounting_hole_{mounting_hole_index + 1}")

    return ssr
