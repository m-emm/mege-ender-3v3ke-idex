"""Moving shuttle for the T0 Tap mechanism."""

from shellforgepy.simple import *


def create_idex_tap_t0_shuttle_assembly(
    *,
    fixed_tool_head_mount,
    mgn7h_rail_with_carriage,
    mgn7h_carriage_mount_hole_pitch_x,
    mgn7h_carriage_mount_hole_pitch_y,
    tool_head_mount_machined_cutout_width,
    tool_head_mount_machined_sprite_mount_hole_primary_y_pitch,
    tool_head_mount_machined_sprite_mount_hole_front_y_inset,
    idex_tap_frame_height,
    idex_tap_shuttle_width,
    idex_tap_shuttle_height,
    idex_tap_shuttle_thickness,
    idex_tap_shuttle_carriage_screw_size,
    idex_tap_trigger_flag_thickness,
    idex_tap_trigger_flag_width,
    idex_tap_trigger_flag_sensor_overlap_at_rest,
    idex_tap_total_travel,
    idex_tap_magnet_height,
    idex_tap_magnet_count,
    idex_tap_magnet_center_spacing,
    idex_tap_magnet_gap_at_rest,
    idex_tap_magnet_target_screw_head_diameter,
):
    """Create the printed moving stack that rides on the MGN7H carriage."""

    fixed_mount_size = get_bounding_box_size(fixed_tool_head_mount.leader)
    carriage = mgn7h_rail_with_carriage.get_named_follower("carriage")
    _ = get_bounding_box_size(carriage)

    carriage_plate = create_box(
        idex_tap_shuttle_width,
        idex_tap_shuttle_thickness,
        idex_tap_shuttle_height,
    )

    fixed_mount_center = get_bounding_box_center(fixed_tool_head_mount.leader)
    sprite_mount_hole_x_offsets = []
    sprite_mount_hole_radius = 0
    for cutter_name, cutter in fixed_tool_head_mount.get_named_cutter_items():
        if not cutter_name.startswith("hole_drill_"):
            continue
        cutter_center = get_bounding_box_center(cutter)
        cutter_size = get_bounding_box_size(cutter)
        sprite_mount_hole_x_offsets.append(cutter_center[0] - fixed_mount_center[0])
        sprite_mount_hole_radius = max(
            sprite_mount_hole_radius,
            max(cutter_size[0], cutter_size[1]) / 2,
        )

    sprite_mount_strip_width = max(12, 2 * sprite_mount_hole_radius + 6)
    sprite_mount_face = PartCollector()
    for strip_x_offset in sorted(
        {min(sprite_mount_hole_x_offsets), max(sprite_mount_hole_x_offsets)}
    ):
        sprite_mount_strip = create_box(
            sprite_mount_strip_width,
            fixed_mount_size[1],
            fixed_mount_size[2],
        )
        sprite_mount_strip = translate(strip_x_offset, 0, 0)(sprite_mount_strip)
        sprite_mount_face = sprite_mount_face.fuse(sprite_mount_strip)

    sprite_mount_face = align(
        sprite_mount_face,
        carriage_plate,
        Alignment.CENTER,
        axes=[0],
    )
    sprite_mount_face = align(sprite_mount_face, carriage_plate, Alignment.STACK_BACK)
    sprite_mount_face = translate(
        0,
        0,
        idex_tap_frame_height / 2 + fixed_mount_size[2] / 2,
    )(sprite_mount_face)

    shuttle = carriage_plate.fuse(sprite_mount_face)

    shuttle_mount_screw = MScrew.from_size(idex_tap_shuttle_carriage_screw_size)
    shuttle_holes = PartCollector()
    for x_offset in [
        -mgn7h_carriage_mount_hole_pitch_y / 2,
        mgn7h_carriage_mount_hole_pitch_y / 2,
    ]:
        for z_offset in [
            -mgn7h_carriage_mount_hole_pitch_x / 2,
            mgn7h_carriage_mount_hole_pitch_x / 2,
        ]:
            shuttle_hole = create_cylinder(
                shuttle_mount_screw.clearance_hole_normal / 2,
                idex_tap_shuttle_thickness + 4,
                direction=(0, 1, 0),
            )
            shuttle_hole = align(shuttle_hole, carriage_plate, Alignment.CENTER)
            shuttle_hole = translate(x_offset, 0, z_offset)(shuttle_hole)
            shuttle = shuttle.cut(shuttle_hole)
            shuttle_holes = shuttle_holes.fuse(shuttle_hole)

    sprite_mount_holes = PartCollector()
    for cutter_name, cutter in fixed_tool_head_mount.get_named_cutter_items():
        if not cutter_name.startswith("hole_drill_"):
            continue
        cutter_center = get_bounding_box_center(cutter)
        cutter_size = get_bounding_box_size(cutter)
        mount_hole = create_cylinder(
            max(cutter_size[0], cutter_size[1]) / 2,
            fixed_mount_size[2] + 2,
        )
        mount_hole = align(mount_hole, sprite_mount_face, Alignment.CENTER)
        mount_hole = translate(
            cutter_center[0] - fixed_mount_center[0],
            cutter_center[1] - fixed_mount_center[1],
            0,
        )(mount_hole)
        shuttle = shuttle.cut(mount_hole)
        sprite_mount_holes = sprite_mount_holes.fuse(mount_hole)

    trigger_flag_height = (
        idex_tap_trigger_flag_sensor_overlap_at_rest + idex_tap_total_travel + 4
    )
    trigger_flag = create_box(
        idex_tap_trigger_flag_width,
        idex_tap_trigger_flag_thickness,
        trigger_flag_height,
    )
    trigger_flag = align(trigger_flag, carriage_plate, Alignment.CENTER, axes=[2])
    trigger_flag = align(trigger_flag, carriage_plate, Alignment.STACK_RIGHT)
    trigger_flag = align(trigger_flag, carriage_plate, Alignment.STACK_FRONT)

    moving_magnet_targets = PartCollector()
    magnet_stations = max(1, int(idex_tap_magnet_count))
    for station_index in range(magnet_stations):
        x_offset = (station_index - (magnet_stations - 1) / 2) * (
            idex_tap_magnet_center_spacing
        )
        target = create_cylinder(
            idex_tap_magnet_target_screw_head_diameter / 2,
            idex_tap_magnet_height,
            direction=(0, 1, 0),
        )
        target = align(target, carriage_plate, Alignment.CENTER, axes=[0, 2])
        target = align(target, carriage_plate, Alignment.STACK_BACK)
        target = translate(
            x_offset,
            -idex_tap_magnet_gap_at_rest,
            -idex_tap_shuttle_height * 0.42,
        )(target)
        moving_magnet_targets = moving_magnet_targets.fuse(target)

    shuttle_part = LeaderFollowersCuttersPart(leader=shuttle)
    shuttle_part.add_named_follower(carriage_plate, "idex_tap_carriage_plate")
    shuttle_part.add_named_follower(sprite_mount_face, "sprite_mount_face")
    shuttle_part.add_named_follower(trigger_flag, "idex_tap_trigger_flag")
    shuttle_part.add_named_cutter(shuttle_holes, "shuttle_carriage_mount_holes")
    shuttle_part.add_named_cutter(sprite_mount_holes, "sprite_mount_holes")
    shuttle_part.add_named_non_production_part(
        moving_magnet_targets,
        "moving_magnet_targets",
    )

    return shuttle_part
