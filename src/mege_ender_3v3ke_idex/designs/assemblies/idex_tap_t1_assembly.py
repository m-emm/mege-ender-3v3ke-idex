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

    lower_mount_strip_width = 7.8
    lower_mount_strip_length = 55
    lower_mount_strip_thickness = 5
    carriage_mount_plate_thickness = 4
    side_wall_thickness = 4
    carriage_mount_screw_length = 8
    lower_mount_strip_thread_inset_size = "M3"
    lower_mount_strip_thread_inset_top_material_thickness = 1
    lower_mount_strip_thread_inset_holder_thickness = (
        MScrew.from_size(lower_mount_strip_thread_inset_size).thread_inset_length
        + lower_mount_strip_thread_inset_top_material_thickness
    )
    lower_mount_strip_thread_inset_extra_radius = 1.5

    inset_boss_cutter_diameter = 10

    lower_mount_strips = PartCollector()
    lower_mount_strip_thread_inset_bosses = PartCollector()
    lower_mount_strip_thread_inset_cutters = PartCollector()
    lower_mount_strip_thread_insets = []
    inset_boss_cutters = PartCollector()
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

        for fb in [Alignment.FRONT, Alignment.BACK]:
            drill_name = f"hole_drill_{lr.name}_{fb.name}"
            drill = fixed_tool_head_mount.get_named_cutter(drill_name)
            lower_mount_strip = lower_mount_strip.cut(drill)

            thread_inset = create_thread_inset_assembly(
                size=lower_mount_strip_thread_inset_size,
                thickness=lower_mount_strip_thread_inset_holder_thickness,
                extra_radius=lower_mount_strip_thread_inset_extra_radius,
                clearance_type="close",
            )
            thread_inset = align(thread_inset, drill, Alignment.CENTER)
            thread_inset = align(
                thread_inset,
                lower_mount_strip,
                Alignment.STACK_BOTTOM,
                stack_gap=-lower_mount_strip_thickness,
            )

            thread_inset_boss = thread_inset.get_named_cutter("assembly_cutter")
            thread_inset_cutter = thread_inset_boss.cut(thread_inset.leader)
            lower_mount_strip_thread_inset_bosses = (
                lower_mount_strip_thread_inset_bosses.fuse(thread_inset_boss)
            )
            lower_mount_strip_thread_inset_cutters = (
                lower_mount_strip_thread_inset_cutters.fuse(thread_inset_cutter)
            )

            lower_mount_strip_thread_insets.append(
                thread_inset.prefixed_copy(
                    f"lower_mount_strip_thread_inset_{lr.name.lower()}_{fb.name.lower()}"
                )
            )

            if fb == Alignment.BACK:
                inset_boss_cutter = create_cylinder(inset_boss_cutter_diameter / 2, 100)
                inset_boss_cutter = rotate(90, axis=[0, 1, 0])(inset_boss_cutter)
                inset_boss_cutter = align(
                    inset_boss_cutter, thread_inset_boss, Alignment.CENTER
                )
                inset_boss_cutter = align(
                    inset_boss_cutter, thread_inset_boss, Alignment.EDGE_BOTTOM
                )
                inset_boss_cutters = inset_boss_cutters.fuse(inset_boss_cutter)

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

    front_pos_factor = 0.2
    back_mount_plate_min_y = back_mount_plate_bbox[0][1]
    back_mount_plate_min_z = back_mount_plate_bbox[0][2]
    back_mount_plate_max_z = back_mount_plate_bbox[1][2]
    lower_mount_strip_min_y = lower_mount_strips_bbox[0][1]
    lower_mount_strip_max_y = lower_mount_strips_bbox[1][1]
    lower_mount_strip_min_z = lower_mount_strips_bbox[0][2]

    new_front_y = (
        lower_mount_strip_min_y * (1 - front_pos_factor)
        + lower_mount_strip_max_y * front_pos_factor
    )

    back_pos_factor = 0.0
    new_top_back_y = (
        lower_mount_strip_max_y * (1 - back_pos_factor)
        + lower_mount_strip_min_y * back_pos_factor
    )
    mid_y_factor = 0.5
    mid_y = (
        back_mount_plate_min_y * (1 - mid_y_factor)
        + lower_mount_strip_min_y * mid_y_factor
    )

    mid_z_factor = 0.6
    mid_z = (
        back_mount_plate_min_z * (1 - mid_z_factor)
        + back_mount_plate_max_z * mid_z_factor
    )

    new_points = [
        (back_mount_plate_min_y, back_mount_plate_min_z),
        (back_mount_plate_min_y, back_mount_plate_max_z),
        (new_top_back_y, lower_mount_strip_min_z),
        (new_front_y, lower_mount_strip_min_z),
        (mid_y, mid_z),
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

    side_wall_left = align(side_wall, lower_mount_strips, Alignment.LEFT)
    side_walls = side_wall.fuse(side_wall_left)

    side_walls = side_walls.cut(inset_boss_cutters)

    part = part.fuse(side_walls)

    part = mgn7h_rail_with_carriage.use_as_cutter_on(part)
    part = part.fuse(lower_mount_strip_thread_inset_bosses)
    part = part.cut(lower_mount_strip_thread_inset_cutters)

    tap = LeaderFollowersCuttersPart(leader=part)
    for thread_inset in lower_mount_strip_thread_insets:
        for name, inset in thread_inset.get_named_non_production_part_items():
            tap.add_named_non_production_part(inset, name)

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
