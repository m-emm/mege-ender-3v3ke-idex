"""24 V electric switchboard enclosure assembly."""

from shellforgepy.simple import *


def create_electric_switchboard_assembly(
    *,
    emergency_button,
    electric_switchboard_height,
    electric_switchboard_width,
    electric_switchboard_depth,
    electric_switchboard_wall_thickness,
    electric_switchboard_cable_hole_count,
    electric_switchboard_cable_hole_diameter,
    electric_switchboard_cable_hole_pitch,
    electric_switchboard_cable_hole_z_offset_from_open_bottom,
):
    """Create an open-bottom switchboard box with a top emergency button."""

    switchboard_box = create_box(
        electric_switchboard_width,
        electric_switchboard_depth,
        electric_switchboard_height,
    )

    inner_space_cutter = create_box(
        electric_switchboard_width - 2 * electric_switchboard_wall_thickness,
        electric_switchboard_depth - 2 * electric_switchboard_wall_thickness,
        electric_switchboard_height - electric_switchboard_wall_thickness + 1,
        origin=(
            electric_switchboard_wall_thickness,
            electric_switchboard_wall_thickness,
            -1,
        ),
    )
    switchboard_box = switchboard_box.cut(inner_space_cutter)

    top_panel_reference = create_box(
        electric_switchboard_width,
        electric_switchboard_depth,
        electric_switchboard_wall_thickness,
        origin=(
            0,
            0,
            electric_switchboard_height - electric_switchboard_wall_thickness,
        ),
    )

    emergency_button = emergency_button.aligned_from_non_production_part(
        "mount_panel_reference",
        top_panel_reference,
        Alignment.CENTER,
    )
    switchboard_box = switchboard_box.cut(
        emergency_button.get_cutter_part_by_name("neck_mount_hole")
    )

    cable_hole_radius = electric_switchboard_cable_hole_diameter / 2
    cable_hole_length = electric_switchboard_wall_thickness + 2
    first_cable_hole_y = (
        electric_switchboard_depth / 2
        - electric_switchboard_cable_hole_pitch
        * (electric_switchboard_cable_hole_count - 1)
        / 2
    )

    left_cable_holes = PartCollector()
    right_cable_holes = PartCollector()
    for cable_hole_index in range(electric_switchboard_cable_hole_count):
        cable_hole_y = (
            first_cable_hole_y
            + cable_hole_index * electric_switchboard_cable_hole_pitch
        )
        left_cable_hole = create_cylinder(
            cable_hole_radius,
            cable_hole_length,
            origin=(
                -1,
                cable_hole_y,
                electric_switchboard_cable_hole_z_offset_from_open_bottom,
            ),
            direction=(1, 0, 0),
        )
        right_cable_hole = create_cylinder(
            cable_hole_radius,
            cable_hole_length,
            origin=(
                electric_switchboard_width - electric_switchboard_wall_thickness,
                cable_hole_y,
                electric_switchboard_cable_hole_z_offset_from_open_bottom,
            ),
            direction=(1, 0, 0),
        )
        left_cable_holes = left_cable_holes.fuse(left_cable_hole)
        right_cable_holes = right_cable_holes.fuse(right_cable_hole)

    switchboard_box = switchboard_box.cut(left_cable_holes)
    switchboard_box = switchboard_box.cut(right_cable_holes)

    switchboard = LeaderFollowersCuttersPart(leader=switchboard_box)
    switchboard.add_named_cutter(left_cable_holes, "left_cable_holes")
    switchboard.add_named_cutter(right_cable_holes, "right_cable_holes")

    for name, part in emergency_button.get_named_follower_items():
        switchboard.add_named_non_production_part(part, f"emergency_button_{name}")

    for name, part in emergency_button.get_named_cutter_items():
        switchboard.add_named_cutter(part, f"emergency_button_{name}")

    for name, part in emergency_button.get_named_non_production_part_items():
        switchboard.add_named_non_production_part(part, f"emergency_button_{name}")

    return switchboard
