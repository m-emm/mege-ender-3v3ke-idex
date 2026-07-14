"""Moving shuttle for the T1 Tap mechanism."""

from shellforgepy.simple import *


def create_idex_tap_t1_shuttle_assembly(
    *,
    fixed_tool_head_mount,
    mgn7h_rail_with_carriage,
    idex_tap_t1,
    sprite_extruder_right,
    extruder_cage_right,
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

    # Future shuttle geometry will build around this placed right toolhead context.
    _ = fixed_tool_head_mount, idex_tap_t1, sprite_extruder_right, extruder_cage_right

    carriage = mgn7h_rail_with_carriage.get_named_follower("carriage")
    _ = get_bounding_box_size(carriage)

    shuttle = create_box(
        idex_tap_shuttle_width,
        idex_tap_shuttle_thickness,
        idex_tap_shuttle_height,
    )

    shuttle = align(shuttle, carriage, Alignment.CENTER)
    shuttle = align(shuttle, carriage, Alignment.STACK_BACK)

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
            shuttle_hole = align(shuttle_hole, shuttle, Alignment.CENTER)
            shuttle_hole = translate(x_offset, 0, z_offset)(shuttle_hole)
            shuttle = shuttle.cut(shuttle_hole)
            shuttle_holes = shuttle_holes.fuse(shuttle_hole)

    shuttle_part = LeaderFollowersCuttersPart(leader=shuttle)
    # shuttle_part.add_named_follower(carriage_plate, "idex_tap_carriage_plate")
    shuttle_part.add_named_cutter(shuttle_holes, "shuttle_carriage_mount_holes")
    # shuttle_part.add_named_non_production_part(
    #     moving_magnet_targets,
    #     "moving_magnet_targets",
    # )

    return shuttle_part
