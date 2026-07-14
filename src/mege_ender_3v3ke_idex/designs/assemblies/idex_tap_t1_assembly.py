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

    lower_mount_strip_width = 9
    lower_mount_strip_length = 50
    lower_mount_strip_thickness = 5
    carriage_mount_plate_thickness = 4
    side_wall_thickness = 4
    carriage_mount_screw_length = 8

    lower_mount_strips = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        lower_mount_strip = create_box(
            lower_mount_strip_width,
            lower_mount_strip_length,
            lower_mount_strip_thickness,
        )

        lower_mount_strip = align(
            lower_mount_strip, fixed_tool_head_mount, Alignment.FRONT
        )

        lower_mount_strip = align(
            lower_mount_strip, fixed_tool_head_mount, Alignment.STACK_BOTTOM
        )

        lower_mount_strip = align(lower_mount_strip, fixed_tool_head_mount, lr)

        lower_mount_strips = lower_mount_strips.fuse(lower_mount_strip)

    lower_mount_strips = fixed_tool_head_mount.use_as_cutter_on(lower_mount_strips)

    carriage = mgn7h_rail_with_carriage.get_named_follower("carriage")

    carriage_size = get_bounding_box_size(carriage)
    fixed_tool_head_mount_size = get_bounding_box_size(fixed_tool_head_mount)

    back_mount_plate = create_box(
        fixed_tool_head_mount_size[0], carriage_mount_plate_thickness, carriage_size[2]
    )

    back_mount_plate = align(back_mount_plate, carriage, Alignment.CENTER, axes=[2])

    back_mount_plate = align(
        back_mount_plate, fixed_tool_head_mount, Alignment.CENTER, axes=[0]
    )

    back_mount_plate = align(back_mount_plate, carriage, Alignment.STACK_BACK)

    back_mount_plate_bbox = get_bounding_box(back_mount_plate)
    lower_mount_strips_bbox = get_bounding_box(lower_mount_strips)

    back_factor = 0.5
    back_mount_plate_min_y = back_mount_plate_bbox[0][1]
    back_mount_plate_min_z = back_mount_plate_bbox[0][2]
    back_mount_plate_max_z = back_mount_plate_bbox[1][2]
    lower_mount_strip_min_y = lower_mount_strips_bbox[0][1]
    lower_mount_strip_max_y = lower_mount_strips_bbox[1][1]
    lower_mount_strip_min_z = lower_mount_strips_bbox[0][2]

    new_front_y = (lower_mount_strip_min_y + lower_mount_strip_max_y) * back_factor
    new_back_y = (back_mount_plate_min_y + lower_mount_strip_min_y) * back_factor

    new_points = [
        (back_mount_plate_min_y, back_mount_plate_min_z),
        (back_mount_plate_min_y, back_mount_plate_max_z),
        (lower_mount_strip_max_y, lower_mount_strip_min_z),
        (new_front_y, lower_mount_strip_min_z),
        (new_back_y, (back_mount_plate_min_z + back_mount_plate_max_z) / 2),
    ]

    part = back_mount_plate.fuse(lower_mount_strips)

    points, faces = create_regular_polygon_geometry(30, 5, side_wall_thickness)

    for i in range(5):
        points[i][0] = new_points[i][0]
        points[i][1] = new_points[i][1]
        points[i + 5][0] = new_points[i][0]
        points[i + 5][1] = new_points[i][1]

    face_vertex_maps = convert_to_traditional_face_vertex_maps(points, faces)

    side_wall = create_solid_from_traditional_face_vertex_maps(face_vertex_maps)
    side_wall = rotate(90)(side_wall)

    side_wall = rotate(90, axis=[0, 1, 0])(side_wall)

    side_wall = align(side_wall, back_mount_plate, Alignment.STACK_FRONT)

    side_wall = align(side_wall, lower_mount_strips, Alignment.RIGHT)
    side_wall = align(side_wall, lower_mount_strips, Alignment.STACK_BOTTOM)

    part = part.fuse(side_wall)

    side_wall_left = align(side_wall, lower_mount_strips, Alignment.LEFT)

    part = part.fuse(side_wall_left)

    part = mgn7h_rail_with_carriage.use_as_cutter_on(part)

    tap = LeaderFollowersCuttersPart(leader=part)

    for name, cutter in mgn7h_rail_with_carriage.get_named_cutter_items():
        if name.startswith("carriage_mount_hole"):

            mount_screw = create_cylinder_screw("M2", carriage_mount_screw_length)
            mount_screw = rotate(-90, axis=[1, 0, 0])(mount_screw)

            mount_screw = align(mount_screw, cutter, Alignment.CENTER)
            mount_screw = align(mount_screw, back_mount_plate, Alignment.BACK)
            mount_screw = translate(0, MScrew.from_size("M2").cylinder_head_height, 0)(
                mount_screw
            )

            tap.add_named_non_production_part(
                mount_screw, f"tap_carriage_mount_screw_{name}"
            )

    # tap.add_named_follower(rail_plate, "idex_tap_rail_plate")
    # tap.add_named_cutter(frame_mount_holes, "frame_mount_holes")
    # tap.add_named_cutter(rail_mount_holes, "rail_mount_holes")

    return tap
