"""Join the lower belt-carriage remainder into the left extruder cage."""

from shellforgepy.simple import *

SPRITE_EXTRUDER_CUTTER_Y_ENLARGEMENT = 100


def join_left_belt_carriage_with_cage(
    *,
    extruder_cage,
    belt_carriage,
    sprite_extruder,
    tool_head_mount_machined,
    axis_profile,
    eddy_duo_assembly,
    x_axis_left_carriage_assembly,
):
    """Return a cage containing the carriage outside the Sprite envelope."""

    bridge_reference = belt_carriage.get_named_non_production_part("bridge_reference")
    joined_extruder_cage = extruder_cage.copy()

    belt_carriage_remainder = belt_carriage.cut(extruder_cage)
    joined_belt_carriage = belt_carriage_remainder.filtered_copy(
        ["right_clamp_thread_inset_thread_inset"]
    )

    bridge_size = get_bounding_box_size(bridge_reference)
    bridge_extension = materialize_bounding_box(
        joined_belt_carriage, y_size=bridge_size[1], z_size=6
    )
    bridge_extension = align(
        bridge_extension, joined_belt_carriage, Alignment.STACK_BOTTOM
    )
    bridge_extension = align(bridge_extension, bridge_reference, Alignment.FRONT)

    joined_belt_carriage = joined_belt_carriage.fuse(bridge_extension)

    top_plate = materialize_bounding_box(
        tool_head_mount_machined, x_enlargement=12, y_enlargement=5
    )
    top_plate = align(top_plate, tool_head_mount_machined, Alignment.STACK_TOP)

    profile_cutter = materialize_bounding_box(axis_profile, z_size=100, y_size=100)
    profile_cutter = align(profile_cutter, axis_profile, Alignment.FRONT)

    profile_cutter = translate(0, 5, 0)(profile_cutter)
    top_plate = top_plate.cut(profile_cutter)

    sprite_extruder_cutter = materialize_bounding_box(
        tool_head_mount_machined, z_size=100, x_enlargement=-20
    )
    sprite_extruder_cutter = align(
        sprite_extruder_cutter, sprite_extruder, Alignment.BACK
    )
    sprite_extruder_cutter = translate(0, 3, 0)(sprite_extruder_cutter)

    top_plate = top_plate.cut(sprite_extruder_cutter)

    top_plate = tool_head_mount_machined.use_as_cutter_on(top_plate)

    eddy_duo_size = get_bounding_box_size(eddy_duo_assembly)
    eddy_duo_mount_plate = create_box(4, eddy_duo_size[1] + 4, 200)

    eddy_duo_mount_plate = align(
        eddy_duo_mount_plate, eddy_duo_assembly, Alignment.CENTER
    )

    eddy_duo_mount_plate = align(eddy_duo_mount_plate, top_plate, Alignment.LEFT)

    eddy_duo_mount_plate = fit_part_between(
        eddy_duo_mount_plate,
        cut_normal=(0, 0, 1),
        limiting_start_part=eddy_duo_assembly,
        limiting_end_part=top_plate,
    )

    eddy_duo_mount_plate = materialize_bounding_box(
        eddy_duo_mount_plate, z_enlargement=24
    )

    eddy_duo_mount_plate = align(eddy_duo_mount_plate, top_plate, Alignment.TOP)

    eddy_duo_mounting_holes_drill = PartCollector()

    for side in [Alignment.LEFT, Alignment.RIGHT]:

        drill = eddy_duo_assembly.get_named_cutter(f"mounting_hole_{side.name.lower()}")

        drill_size = get_bounding_box_size(drill)
        drill_diameter = drill_size[1]

        long_hole = create_rounded_slab(
            3 * drill_diameter, drill_diameter, 100, drill_diameter / 2
        )

        long_hole = rotate(90, axis=(0, 1, 0))(long_hole)

        long_hole = align(long_hole, drill, Alignment.CENTER)
        eddy_duo_mounting_holes_drill.fuse(long_hole)

    eddy_duo_mount_plate = eddy_duo_mount_plate.cut(eddy_duo_mounting_holes_drill.part)

    top_plate = top_plate.fuse(eddy_duo_mount_plate)

    left_thrad_inset = belt_carriage.get_named_non_production_part(
        "left_bridge_thread_inset_thread_inset"
    )

    left_flange = create_box(7.5, 5, 10)

    left_flange = align(left_flange, left_thrad_inset, Alignment.CENTER)
    left_flange = align(left_flange, bridge_reference, Alignment.STACK_FRONT)

    left_bridge_hole_drill = belt_carriage.get_named_cutter(
        "left_carrier_left_bridge_hole_drill"
    )
    left_flange = left_flange.cut(left_bridge_hole_drill)

    left_flange_connector = materialize_bounding_box(
        sprite_extruder, x_size=6, z_size=4
    )
    left_flange_connector = align(
        left_flange_connector, left_flange, Alignment.CENTER, axes=[0]
    )
    left_flange_connector = align(
        left_flange_connector, left_flange, Alignment.STACK_BOTTOM
    )
    left_flange_connector = align(left_flange_connector, left_flange, Alignment.BACK)

    left_flange_connector_trimmer = create_box(500, 500, 500)

    left_flange_connector_trimmer = align(
        left_flange_connector_trimmer, left_flange_connector, Alignment.CENTER
    )
    left_flange_connector_trimmer = align(
        left_flange_connector_trimmer, eddy_duo_mount_plate, Alignment.STACK_FRONT
    )

    left_flange_connector = left_flange_connector.cut(left_flange_connector_trimmer)

    left_flange = left_flange.fuse(left_flange_connector)

    duo_mount_plate_and_connector_connector = create_box(8, eddy_duo_size[1], 4)

    duo_mount_plate_and_connector_connector = align(
        duo_mount_plate_and_connector_connector, eddy_duo_mount_plate, Alignment.CENTER
    )
    duo_mount_plate_and_connector_connector = align(
        duo_mount_plate_and_connector_connector,
        eddy_duo_mount_plate,
        Alignment.STACK_RIGHT,
    )
    duo_mount_plate_and_connector_connector = align(
        duo_mount_plate_and_connector_connector, left_flange_connector, Alignment.BOTTOM
    )

    left_flange = left_flange.fuse(duo_mount_plate_and_connector_connector)

    top_plate = top_plate.fuse(left_flange)

    right_clamp_hole_drill = belt_carriage.get_named_cutter("right_clamp_hole_drill")

    right_flange = create_box(10, 5, 23)
    right_flange = align(right_flange, right_clamp_hole_drill, Alignment.CENTER)
    right_flange = align(right_flange, belt_carriage, Alignment.STACK_FRONT)
    right_flange = align(right_flange, belt_carriage, Alignment.TOP)

    right_flange_connector = create_box(6, 10, 30)
    right_flange_connector = align(
        right_flange_connector, right_flange, Alignment.CENTER
    )
    right_flange_connector = align(
        right_flange_connector,
        tool_head_mount_machined,
        Alignment.STACK_RIGHT,
        stack_gap=0.2,
    )
    right_flange_connector = align(right_flange_connector, top_plate, Alignment.TOP)
    right_flange_connector = align(right_flange_connector, right_flange, Alignment.BACK)
    right_flange_connector = translate(0, -1, 0)(right_flange_connector)

    right_flange = right_flange.fuse(right_flange_connector)

    right_flange = right_flange.cut(right_clamp_hole_drill)

    right_mount_plate_reference = extruder_cage.get_named_non_production_part(
        "right_mount_plate_reference"
    )

    extruder_connector_height = 9

    right_flange_extruder_connector = create_box(4.5, 20, extruder_connector_height)
    right_flange_extruder_connector = align(
        right_flange_extruder_connector,
        right_mount_plate_reference,
        Alignment.STACK_RIGHT,
    )
    right_flange_extruder_connector = align(
        right_flange_extruder_connector, right_mount_plate_reference, Alignment.BOTTOM
    )
    right_flange_extruder_connector = align(
        right_flange_extruder_connector, right_flange_connector, Alignment.BACK
    )

    right_flange_extruder_connector = translate(0, -1.5, 0)(
        right_flange_extruder_connector
    )
    right_flange_extruder_connector = sprite_extruder.use_as_cutter_on(
        right_flange_extruder_connector
    )

    right_flange = right_flange.fuse(right_flange_extruder_connector)

    extruder_connector_enhancement = create_box(12, 5, extruder_connector_height)
    extruder_connector_enhancement = align(
        extruder_connector_enhancement,
        right_flange_extruder_connector,
        Alignment.CENTER,
    )

    extruder_connector_enhancement = align(
        extruder_connector_enhancement, right_flange_extruder_connector, Alignment.BACK
    )

    extruder_connector_enhancement = align(
        extruder_connector_enhancement, right_flange_extruder_connector, Alignment.LEFT
    )

    right_flange = right_flange.fuse(extruder_connector_enhancement)

    right_belt_path_cutter = belt_carriage.get_named_cutter("right_belt_path_cutter")
    right_flange = right_flange.cut(right_belt_path_cutter)

    top_plate = top_plate.fuse(right_flange)

    top_plate = x_axis_left_carriage_assembly.use_as_cutter_on(top_plate)

    correction_radius = 4
    right_clamp_inset_correction_cutter = create_cylinder(
        correction_radius, 100, direction=(0, 1, 0)
    )

    right_clamp_inset_correction_cutter = align(
        right_clamp_inset_correction_cutter, right_clamp_hole_drill, Alignment.CENTER
    )

    joined_belt_carriage = joined_belt_carriage.cut(right_clamp_inset_correction_cutter)

    joined_belt_carriage_bbox = get_bounding_box(joined_belt_carriage)

    bridge_reference_bbox = get_bounding_box(bridge_reference)

    correction_y_size = bridge_reference_bbox[1][1] - joined_belt_carriage_bbox[0][1]

    correction_filler = create_cylinder(
        correction_radius, correction_y_size, direction=(0, 1, 0)
    )

    correction_filler = align(
        correction_filler, right_clamp_inset_correction_cutter, Alignment.CENTER
    )
    correction_filler = align(correction_filler, joined_belt_carriage, Alignment.FRONT)

    correction_filler = correction_filler.cut(right_clamp_hole_drill)

    joined_belt_carriage = joined_belt_carriage.fuse(correction_filler)

    tool_head_mount_machined_bottom_z = get_bounding_box(tool_head_mount_machined)[0][2]
    top_plate_top, top_plate__bottom = cut_in_two(
        top_plate,
        cut_normal=(0, 0, 1),
        cut_point=(0, 0, tool_head_mount_machined_bottom_z),
    )

    top_plate_bottom_left, top_plate_bottom_right = cut_in_two(
        top_plate__bottom, cut_normal=(-1, 0, 0)
    )

    bottom_righ_back_y = get_bounding_box(right_flange_connector)[1][1]
    top_plate_top_center = get_bounding_box_center(top_plate_top)

    top_plate_top_front, top_plate_top_back = cut_in_two(
        top_plate_top,
        cut_normal=(0, 1, 0),
        cut_point=(
            top_plate_top_center[0],
            bottom_righ_back_y,
            top_plate_top_center[2],
        ),
    )

    top_plate_top_back_left, top_plate_top_back_right = cut_in_two(
        top_plate_top_back, cut_normal=(-1, 0, 0)
    )

    top_plate_top_front_front_top_left, top_plate_top_front_front_bottom_right = (
        cut_in_two(top_plate_top_front, cut_normal=(0, 0, 1))
    )

    gap_cutter = create_box(30, 100, 100)

    gap_cutter = align(
        gap_cutter, top_plate_top_front_front_bottom_right, Alignment.CENTER
    )
    gap_cutter = align(
        gap_cutter, top_plate_top_front_front_bottom_right, Alignment.EDGE_LEFT
    )
    gap_cutter = align(
        gap_cutter,
        top_plate_top_front_front_bottom_right,
        Alignment.STACK_FRONT,
        stack_gap=-0.5,
    )

    top_plate_top_front_front_bottom_right = top_plate_top_front_front_bottom_right.cut(
        gap_cutter
    )

    gap_cutter = create_box(30, 100, 100)

    gap_cutter = align(gap_cutter, top_plate_top_front_front_top_left, Alignment.CENTER)
    gap_cutter = align(
        gap_cutter, top_plate_top_front_front_top_left, Alignment.EDGE_RIGHT
    )
    gap_cutter = align(
        gap_cutter,
        top_plate_top_front_front_top_left,
        Alignment.STACK_FRONT,
        stack_gap=-0.5,
    )

    top_plate_top_front_front_top_left = top_plate_top_front_front_top_left.cut(
        gap_cutter
    )

    top_plate_left = (
        top_plate_bottom_left.fuse(top_plate_top_back_left)
        .fuse(top_plate_bottom_left)
        .fuse(top_plate_top_front_front_top_left)
    )
    top_plate_right = (
        top_plate_bottom_right.fuse(top_plate_top_back_right)
        .fuse(top_plate_bottom_right)
        .fuse(top_plate_top_front_front_bottom_right)
    )

    joined_belt_carriage.add_named_follower(
        top_plate_left, "belt_carriage_top_plate_left"
    )
    joined_belt_carriage.add_named_follower(
        top_plate_right, "belt_carriage_top_plate_right"
    )

    return {
        "extruder_cage": joined_extruder_cage,
        "belt_carriage": joined_belt_carriage,
    }
