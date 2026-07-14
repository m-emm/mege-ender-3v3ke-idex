"""Exploratory fixed frame for the T1/right/top Tap packaging study."""

from shellforgepy.simple import *


def create_idex_tap_t1_assembly(
    *,
    fixed_tool_head_mount,
    x_axis_carriage,
    mgn7h_rail_with_carriage,
    mgn7h_rail_length,
    mgn7h_rail_width,
    mgn7h_rail_mount_hole_pitch,
    mgn7h_rail_mount_hole_end_offset,
    mgn7h_rail_mount_hole_diameter,
    idex_tap_frame_height,
    idex_tap_frame_thickness,
    idex_tap_frame_mount_flange_depth,
    idex_tap_frame_mount_flange_thickness,
    idex_tap_frame_mount_screw_size,
    idex_tap_shuttle_height,
):
    """Create a loose fixed Tap frame around the placed right-side context."""

    fixed_tool_head_mount_size = get_bounding_box_size(fixed_tool_head_mount.leader)
    mount_flange = create_box(
        fixed_tool_head_mount_size[0],
        idex_tap_frame_mount_flange_depth,
        idex_tap_frame_mount_flange_thickness,
    )

    mount_flange = align(mount_flange, fixed_tool_head_mount, Alignment.CENTER)
    mount_flange = align(mount_flange, fixed_tool_head_mount, Alignment.STACK_TOP)
    mount_flange = align(mount_flange, x_axis_carriage, Alignment.STACK_FRONT)

    rail_plate_width = max(idex_tap_shuttle_height, mgn7h_rail_width + 16)
    rail_plate = create_box(
        rail_plate_width,
        idex_tap_frame_thickness,
        idex_tap_frame_height,
    )
    rail_plate = align(rail_plate, mgn7h_rail_with_carriage, Alignment.CENTER)
    rail_plate = align(rail_plate, fixed_tool_head_mount, Alignment.STACK_BOTTOM)
    rail_plate = align(rail_plate, mgn7h_rail_with_carriage, Alignment.STACK_BACK)

    rail_plate = mgn7h_rail_with_carriage.use_as_cutter_on(rail_plate)
    fixed_frame = mount_flange  # .fuse(rail_plate)

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

    tap = LeaderFollowersCuttersPart(leader=fixed_frame)
    tap.add_named_follower(rail_plate, "idex_tap_rail_plate")
    tap.add_named_cutter(frame_mount_holes, "frame_mount_holes")
    tap.add_named_cutter(rail_mount_holes, "rail_mount_holes")

    return tap
