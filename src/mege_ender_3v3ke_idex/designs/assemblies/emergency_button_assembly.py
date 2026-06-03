"""Emergency stop button reference assembly."""

from shellforgepy.simple import *


def create_emergency_button_assembly(
    *,
    emergency_button_button_diameter,
    emergency_button_button_thickness,
    emergency_button_neck_diameter,
    emergency_button_neck_height,
    emergency_button_neck_silver_collar_height,
    emergency_button_neck_collar_wall_thickness,
    emergency_button_neck_collar_fit_clearance,
    emergency_button_neck_collar_gap,
    emergency_button_body_width,
    emergency_button_body_length,
    emergency_button_body_height,
    emergency_button_neck_mount_hole_diameter,
    emergency_button_neck_mount_hole_clearance,
):
    """Create a simplified emergency stop button with aligned holder cutters."""

    body = create_box(
        emergency_button_body_length,
        emergency_button_body_width,
        emergency_button_body_height,
    )

    emergency_button_neck_collar_inner_diameter = (
        emergency_button_neck_diameter - 2 * emergency_button_neck_collar_wall_thickness
    )
    emergency_button_neck_top_diameter = (
        emergency_button_neck_collar_inner_diameter
        - emergency_button_neck_collar_fit_clearance
    )
    emergency_button_neck_lower_height = (
        emergency_button_neck_height
        - emergency_button_neck_silver_collar_height
        - emergency_button_neck_collar_gap
    )
    emergency_button_neck_top_height = (
        emergency_button_neck_silver_collar_height + emergency_button_neck_collar_gap
    )

    lower_neck = create_cylinder(
        emergency_button_neck_diameter / 2,
        emergency_button_neck_lower_height,
    )
    lower_neck = align(lower_neck, body, Alignment.CENTER)
    lower_neck = align(lower_neck, body, Alignment.STACK_TOP)

    top_neck = create_cylinder(
        emergency_button_neck_top_diameter / 2,
        emergency_button_neck_top_height,
    )
    top_neck = align(top_neck, lower_neck, Alignment.CENTER)
    top_neck = align(top_neck, lower_neck, Alignment.STACK_TOP)
    neck = lower_neck.fuse(top_neck)

    silver_collar = create_ring(
        emergency_button_neck_diameter / 2,
        emergency_button_neck_collar_inner_diameter / 2,
        emergency_button_neck_silver_collar_height,
    )
    silver_collar = align(silver_collar, top_neck, Alignment.CENTER, axes=[0, 1])
    silver_collar = align(
        silver_collar,
        top_neck,
        Alignment.STACK_TOP,
        stack_gap=-emergency_button_neck_silver_collar_height,
    )

    mount_panel_reference = create_cylinder(
        emergency_button_neck_mount_hole_diameter / 2,
        emergency_button_neck_collar_gap,
    )
    mount_panel_reference = align(
        mount_panel_reference, lower_neck, Alignment.CENTER, axes=[0, 1]
    )
    mount_panel_reference = align(
        mount_panel_reference, lower_neck, Alignment.STACK_TOP
    )

    button_disc = create_cylinder(
        emergency_button_button_diameter / 2,
        emergency_button_button_thickness,
    )
    button_disc = align(button_disc, silver_collar, Alignment.CENTER)
    button_disc = align(button_disc, silver_collar, Alignment.STACK_TOP)

    button_reference = body.fuse(neck).fuse(silver_collar).fuse(button_disc)

    cutter_height = (
        emergency_button_body_height
        + emergency_button_neck_height
        + emergency_button_button_thickness
        + 20
    )
    neck_mount_hole = create_cylinder(
        (
            emergency_button_neck_mount_hole_diameter
            + emergency_button_neck_mount_hole_clearance
        )
        / 2,
        cutter_height,
    )
    neck_mount_hole = align(neck_mount_hole, button_reference, Alignment.CENTER)

    neck_clearance = create_cylinder(
        (emergency_button_neck_diameter + emergency_button_neck_mount_hole_clearance)
        / 2,
        cutter_height,
    )
    neck_clearance = align(neck_clearance, button_reference, Alignment.CENTER)

    assembly = LeaderFollowersCuttersPart(leader=body)
    assembly.add_named_follower(body, "body")
    assembly.add_named_follower(neck, "neck")
    assembly.add_named_follower(silver_collar, "silver_collar")
    assembly.add_named_follower(button_disc, "button_disc")
    assembly.add_named_non_production_part(button_reference, "button_reference")
    assembly.add_named_non_production_part(
        mount_panel_reference, "mount_panel_reference"
    )
    assembly.add_named_cutter(neck_mount_hole, "neck_mount_hole")
    assembly.add_named_cutter(neck_clearance, "neck_clearance")

    return assembly
