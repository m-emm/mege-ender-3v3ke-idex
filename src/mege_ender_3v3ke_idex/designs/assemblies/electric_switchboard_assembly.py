"""24 V electric switchboard enclosure assembly."""

from shellforgepy.simple import *


def create_electric_switchboard_assembly(
    *,
    emergency_button,
    fuse_holder,
    electric_switchboard_height,
    electric_switchboard_width,
    electric_switchboard_depth,
    electric_switchboard_wall_thickness,
    electric_switchboard_cable_hole_count,
    electric_switchboard_cable_hole_diameter,
    electric_switchboard_cable_hole_pitch,
    electric_switchboard_cable_hole_z_offset_from_open_bottom,
    electric_switchboard_fuse_holder_bottom_clearance,
    electric_switchboard_mount_flange_screw_size,
    electric_switchboard_mount_flange_width,
    electric_switchboard_mount_flange_length,
    electric_switchboard_mount_flange_thickness,
    electric_switchboard_mount_flange_fillet_radius,
):
    """Create an open-bottom switchboard box with panel-mounted controls."""

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

    emergency_button = rotate(90)(emergency_button)

    emergency_button = emergency_button.aligned_from_non_production_part(
        "mount_panel_reference",
        top_panel_reference,
        Alignment.CENTER,
    )
    switchboard_box = switchboard_box.cut(
        emergency_button.get_cutter_part_by_name("neck_mount_hole")
    )

    fuse_holder_front_panel_reference = create_box(
        electric_switchboard_width,
        electric_switchboard_wall_thickness,
        electric_switchboard_height,
    )
    fuse_holder = rotate(-90, axis=(0, 0, 1))(fuse_holder)
    fuse_holder = fuse_holder.aligned_from_non_production_part(
        "mount_panel_reference",
        fuse_holder_front_panel_reference,
        Alignment.CENTER,
        axes=[0, 1],
    )
    fuse_holder = fuse_holder.aligned_from_non_production_part(
        "mount_panel_reference",
        fuse_holder_front_panel_reference,
        Alignment.BOTTOM,
    )
    fuse_holder = translate(0, 0, electric_switchboard_fuse_holder_bottom_clearance)(
        fuse_holder
    )
    switchboard_box = switchboard_box.cut(
        fuse_holder.get_cutter_part_by_name("mount_hole")
    )

    mount_flange_screw_hole_diameter = MScrew.from_size(
        electric_switchboard_mount_flange_screw_size
    ).clearance_hole_normal
    mount_flange_screw_holes = PartCollector()
    mount_flanges = PartCollector()
    for side in [Alignment.FRONT, Alignment.BACK]:
        mount_flange = create_filleted_box(
            electric_switchboard_mount_flange_width,
            electric_switchboard_mount_flange_length,
            electric_switchboard_mount_flange_thickness,
            fillet_radius=electric_switchboard_mount_flange_fillet_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM, side.opposite],
        )
        mount_flange = align(mount_flange, switchboard_box, Alignment.CENTER, axes=[0])
        mount_flange = align(mount_flange, switchboard_box, side.stack_alignment)
        mount_flange = align(mount_flange, switchboard_box, Alignment.BOTTOM)
        mount_flanges = mount_flanges.fuse(mount_flange)

        mount_flange_screw_hole = create_cylinder(
            mount_flange_screw_hole_diameter / 2,
            electric_switchboard_mount_flange_thickness + 2,
            origin=(
                get_bounding_box_center(mount_flange)[0],
                get_bounding_box_center(mount_flange)[1],
                -1,
            ),
        )
        mount_flange_screw_holes = mount_flange_screw_holes.fuse(
            mount_flange_screw_hole
        )

    switchboard_box = switchboard_box.fuse(mount_flanges)
    switchboard_box = switchboard_box.cut(mount_flange_screw_holes)

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
    switchboard.add_named_cutter(mount_flange_screw_holes, "mount_flange_screw_holes")

    for name, part in emergency_button.get_named_follower_items():
        switchboard.add_named_non_production_part(part, f"emergency_button_{name}")

    for name, part in emergency_button.get_named_cutter_items():
        switchboard.add_named_cutter(part, f"emergency_button_{name}")

    for name, part in emergency_button.get_named_non_production_part_items():
        switchboard.add_named_non_production_part(part, f"emergency_button_{name}")

    for name, part in fuse_holder.get_named_follower_items():
        switchboard.add_named_non_production_part(part, f"fuse_holder_{name}")

    for name, part in fuse_holder.get_named_cutter_items():
        switchboard.add_named_cutter(part, f"fuse_holder_{name}")

    for name, part in fuse_holder.get_named_non_production_part_items():
        switchboard.add_named_non_production_part(part, f"fuse_holder_{name}")

    return switchboard
