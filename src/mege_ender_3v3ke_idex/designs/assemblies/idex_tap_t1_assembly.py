"""Exploratory fixed frame for the T1/right/top Tap packaging study."""

from shellforgepy.simple import *


def create_idex_tap_t1_assembly(
    *,
    fixed_tool_head_mount,
    x_axis_profile,
    x_axis_carriage,
    sprite_extruder_right,
    extruder_cage_right,
    mgn7h_rail_with_carriage,
    opb991t11z_sensor,
    mgn7h_rail_length,
    mgn7h_rail_width,
    mgn7h_rail_mount_hole_pitch,
    mgn7h_rail_mount_hole_end_offset,
    mgn7h_rail_mount_hole_diameter,
    idex_tap_frame_width,
    idex_tap_frame_height,
    idex_tap_frame_thickness,
    idex_tap_frame_mount_flange_depth,
    idex_tap_frame_mount_flange_thickness,
    idex_tap_frame_mount_screw_size,
    idex_tap_shuttle_height,
    idex_tap_total_travel,
    idex_tap_down_stop_contact_diameter,
    idex_tap_overtravel_stop_contact_diameter,
    idex_tap_sensor_bracket_width,
    idex_tap_sensor_bracket_height,
    idex_tap_sensor_bracket_thickness,
    idex_tap_sensor_bracket_x_offset,
    idex_tap_sensor_bracket_z_offset,
    idex_tap_magnet_diameter,
    idex_tap_magnet_height,
    idex_tap_magnet_count,
    idex_tap_magnet_center_spacing,
    idex_tap_magnet_retainer_thickness,
):
    """Create a loose fixed Tap frame around the placed right-side context."""

    idex_tap_magnet_retainer_clearance = 0.1
    # Future Tap geometry will build around this placed right toolhead context.
    _ = (
        x_axis_profile,
        sprite_extruder_right,
        extruder_cage_right,
        mgn7h_rail_with_carriage,
        opb991t11z_sensor,
    )

    fixed_tool_head_mount_size = get_bounding_box_size(fixed_tool_head_mount.leader)
    mount_flange = create_box(
        fixed_tool_head_mount_size[0],
        idex_tap_frame_mount_flange_depth,
        idex_tap_frame_mount_flange_thickness,
    )

    mount_flange = align(mount_flange, fixed_tool_head_mount, Alignment.CENTER)
    mount_flange = align(mount_flange, fixed_tool_head_mount, Alignment.STACK_BOTTOM)
    mount_flange = align(mount_flange, x_axis_carriage, Alignment.STACK_FRONT)

    rail_plate_width = max(idex_tap_shuttle_height, mgn7h_rail_width + 16)
    rail_plate = create_box(
        rail_plate_width,
        idex_tap_frame_thickness,
        idex_tap_frame_height,
    )
    rail_plate = align(rail_plate, mount_flange, Alignment.CENTER, axes=[0, 1])
    rail_plate = align(rail_plate, mount_flange, Alignment.STACK_BOTTOM)
    rail_plate = align(rail_plate, mount_flange, Alignment.BACK)

    fixed_frame = mount_flange # .fuse(rail_plate)

    fixed_mount_center = get_bounding_box_center(fixed_tool_head_mount.leader)
    frame_mount_holes = PartCollector()
    frame_mount_hole_centers = []
    frame_mount_hole_radius = (
        MScrew.from_size(idex_tap_frame_mount_screw_size).clearance_hole_normal / 2
    )
    for cutter_name, cutter in fixed_tool_head_mount.get_named_cutter_items():
        if cutter_name == "extruder_cutout":
            cutter_center = get_bounding_box_center(cutter)
            cutter_size = get_bounding_box_size(cutter)
            cutout = create_box(
                cutter_size[0],
                cutter_size[1],
                idex_tap_frame_mount_flange_thickness + 2,
            )
            cutout = align(cutout, mount_flange, Alignment.CENTER)
            cutout = translate(
                cutter_center[0] - fixed_mount_center[0],
                cutter_center[1] - fixed_mount_center[1],
                0,
            )(cutout)
            fixed_frame = fixed_frame.cut(cutout)
            continue

        if not cutter_name.startswith("hole_drill_"):
            continue
        cutter_center = get_bounding_box_center(cutter)
        cutter_size = get_bounding_box_size(cutter)
        frame_mount_hole_radius = max(cutter_size[0], cutter_size[1]) / 2
        frame_mount_hole_centers.append(
            (
                cutter_center[0] - fixed_mount_center[0],
                cutter_center[1] - fixed_mount_center[1],
            )
        )

    for hole_x, hole_y in sorted(set(frame_mount_hole_centers)):
        mount_hole = create_cylinder(
            frame_mount_hole_radius,
            idex_tap_frame_mount_flange_thickness + 2,
        )
        mount_hole = align(mount_hole, mount_flange, Alignment.CENTER)
        mount_hole = translate(hole_x, hole_y, 0)(mount_hole)
        fixed_frame = fixed_frame.cut(mount_hole)
        frame_mount_holes = frame_mount_holes.fuse(mount_hole)

    rail_mount_holes = PartCollector()
    rail_mount_hole_z = -mgn7h_rail_length / 2 + mgn7h_rail_mount_hole_end_offset
    rail_mount_last_hole_z = mgn7h_rail_length / 2 - mgn7h_rail_mount_hole_end_offset
    while rail_mount_hole_z <= rail_mount_last_hole_z + 0.001:
        rail_hole = create_cylinder(
            mgn7h_rail_mount_hole_diameter / 2,
            idex_tap_frame_thickness + 4,
            direction=(0, 1, 0),
        )
        rail_hole = align(rail_hole, rail_plate, Alignment.CENTER)
        rail_hole = translate(0, 0, rail_mount_hole_z)(rail_hole)
        fixed_frame = fixed_frame.cut(rail_hole)
        rail_mount_holes = rail_mount_holes.fuse(rail_hole)
        rail_mount_hole_z += mgn7h_rail_mount_hole_pitch

    sensor_bracket = create_box(
        idex_tap_sensor_bracket_width,
        idex_tap_sensor_bracket_thickness,
        idex_tap_sensor_bracket_height,
    )
    sensor_bracket = align(sensor_bracket, rail_plate, Alignment.CENTER, axes=[2])
    sensor_bracket = align(sensor_bracket, rail_plate, Alignment.STACK_RIGHT)
    sensor_bracket = align(sensor_bracket, rail_plate, Alignment.STACK_FRONT)
    sensor_bracket = translate(
        idex_tap_sensor_bracket_x_offset,
        0,
        idex_tap_sensor_bracket_z_offset,
    )(sensor_bracket)

    magnet_retainers = PartCollector()
    magnets = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        retainer = create_box(
            idex_tap_magnet_diameter + idex_tap_magnet_retainer_thickness,
            idex_tap_magnet_diameter + idex_tap_magnet_retainer_thickness,
            idex_tap_magnet_height + idex_tap_magnet_retainer_thickness,
        )
        retainer = align(retainer, rail_plate, Alignment.BOTTOM)
        retainer = align(retainer, rail_plate, Alignment.STACK_FRONT)
        retainer = align(retainer, rail_plate, lr)

        magnet = create_cylinder(
            idex_tap_magnet_diameter / 2,
            idex_tap_magnet_height,
        )
        magnet = align(magnet, retainer, Alignment.CENTER)
        magnet = align(magnet, retainer, Alignment.BOTTOM)
        magnets = magnets.fuse(magnet)

        magnet_cutter = create_cylinder(
            idex_tap_magnet_diameter / 2 + idex_tap_magnet_retainer_clearance,
            idex_tap_magnet_height,
        )

        magnet_cutter = align(magnet_cutter, magnet, Alignment.CENTER)
        retainer = retainer.cut(magnet_cutter)
        magnet_retainers = magnet_retainers.fuse(retainer)

    overtravel_stop = create_cylinder(
        idex_tap_overtravel_stop_contact_diameter / 2,
        idex_tap_frame_thickness,
        direction=(0, 1, 0),
    )
    overtravel_stop = align(overtravel_stop, rail_plate, Alignment.CENTER, axes=[0, 2])
    overtravel_stop = align(overtravel_stop, rail_plate, Alignment.STACK_FRONT)
    overtravel_stop = align(overtravel_stop, rail_plate, Alignment.LEFT)
    overtravel_stop = translate(
        0,
        0,
        idex_tap_shuttle_height / 2 + idex_tap_total_travel,
    )(overtravel_stop)

    tap = LeaderFollowersCuttersPart(leader=fixed_frame)
    tap.add_named_follower(rail_plate, "idex_tap_rail_plate")
    tap.add_named_follower(sensor_bracket, "idex_tap_sensor_bracket")
    tap.add_named_follower(overtravel_stop, "idex_tap_overtravel_stop")
    tap.add_named_follower(magnet_retainers, "idex_tap_magnet_retainers")
    tap.add_named_cutter(frame_mount_holes, "frame_mount_holes")
    tap.add_named_cutter(rail_mount_holes, "rail_mount_holes")
    tap.add_named_non_production_part(magnets, "magnets")

    return tap
