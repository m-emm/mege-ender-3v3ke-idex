"""Declarative monolithic z-axis top mount assembly."""

import copy

from shellforgepy.simple import *


def create_profile_mount_plate(
    *,
    profile_mount_width,
    z_axis_profile_mount_plate_thickness,
    z_axis_profile_mount_plate_height,
    z_axis_profile_mount_plate_fillet_radius,
    BIG_THING,
    num_holes,
    screw_inset,
):
    plate = create_box(
        profile_mount_width,
        z_axis_profile_mount_plate_thickness,
        z_axis_profile_mount_plate_height,
        # z_axis_profile_mount_plate_fillet_radius,
        # no_fillets_at=[Alignment.FRONT, Alignment.BACK, Alignment.BOTTOM],
    )

    hole_drill_diameter = MScrew.from_size("M5").clearance_hole_loose

    hole_drills = PartCollector()
    hole_pitch = (
        (z_axis_profile_mount_plate_height - 2 * screw_inset - hole_drill_diameter)
        / (num_holes - 1)
        if num_holes > 1
        else 0
    )
    for i in range(num_holes):
        hole_drill = create_cylinder(hole_drill_diameter / 2, BIG_THING)
        hole_drill = rotate(90, axis=(1, 0, 0))(hole_drill)
        hole_drill = translate(0, 0, i * hole_pitch)(hole_drill)
        hole_drills = hole_drills.fuse(hole_drill)

    hole_drills = align(hole_drills, plate, Alignment.CENTER)
    plate = plate.cut(hole_drills)

    return plate


def _get_part(part):
    return part.leader if hasattr(part, "leader") else part


def create_z_axis_top_mount_assembly(
    *,
    z_axis_profile,
    z_axis_rail,
    z_axis_threaded_rod,
    creality_endstop_board_assembly,
    BIG_THING,
    z_axis_endstop_cable_hole_size,
    z_axis_endstop_profile_clearance,
    z_axis_motor_mount_plate_profile_distance,
    z_axis_profile_mount_plate_num_holes,
    z_axis_profile_mount_plate_screw_inset,
    z_axis_top_profile_mount_plate_height,
    z_axis_profile_mount_plate_clearance,
    z_axis_profile_mount_plate_thickness,
    z_axis_profile_mount_plate_fillet_radius,
    z_axis_threaded_rod_diameter,
    z_axis_top_mount_depth,
    z_axis_top_mount_fillet_radius,
    z_axis_top_mount_profile_mount_width,
    z_axis_top_mount_thickness,
    z_axis_top_mount_threaded_rod_clearance,
    z_axis_top_mount_carriage_clearance,
    z_axis_carriage_width,
    z_axis_top_mount_width,
):
    """Create one monolithic printable top mount for a z-axis side."""

    profile = _get_part(z_axis_profile)
    rail = _get_part(z_axis_rail)
    threaded_rod = _get_part(z_axis_threaded_rod)

    endstop_holder_thickness = 4.5
    endstop_holder_front_thickness = 5.5
    endstop_rail_clearance = 0.1
    endstop_holder_extra_length = 6
    endstop_holder_extra_front_size = 25
    endstop_holder_extra_front_overlap = 3
    mount_guide_width = 1.5
    mount_gap = 2
    mount_boss_diameter = 7
    nut_slack = 0.2

    long_hole_width = 3.1

    endstop_y_offset = -11

    mount_nut_slack = 0.1
    mount_nut_front_wall = 1.2

    square_nut_wall_thickness = 2

    endstop_board = copy.deepcopy(creality_endstop_board_assembly)

    endstop_board = rotate(180)(endstop_board)
    endstop_board = rotate(90, axis=(1, 0, 0))(endstop_board)
    endstop_board = rotate(-90)(endstop_board)

    endstop_board = align(endstop_board, rail, Alignment.CENTER)
    endstop_board = endstop_board.aligned_from_non_production_part(
        "base", profile, Alignment.STACK_TOP
    )
    endstop_board = align(
        endstop_board,
        rail,
        Alignment.STACK_LEFT,
        stack_gap=endstop_holder_thickness + mount_gap,
    )
    endstop_board = align(endstop_board, rail, Alignment.BACK)
    endstop_board = translate(0, endstop_y_offset, 0)(endstop_board)

    endstop_board_base = endstop_board.get_named_non_production_part("base")

    endstop_board_size = get_bounding_box_size(endstop_board)

    endstop_holder = materialize_bounding_box(
        rail,
        x_enlargement=endstop_holder_thickness,
        y_enlargement=endstop_holder_front_thickness + endstop_holder_thickness,
        z_size=endstop_board_size[2] + endstop_holder_extra_length,
    )
    endstop_holder = align(endstop_holder, endstop_board_base, Alignment.BOTTOM)
    endstop_holder = align(endstop_holder, rail, Alignment.RIGHT)

    endstop_holder = align(endstop_holder, rail, Alignment.BACK)
    endstop_holder = translate(0, endstop_holder_thickness, 0)(endstop_holder)

    endstop_holder_front_extension = materialize_bounding_box(
        endstop_holder,
        y_size=endstop_holder_extra_front_size,
        x_size=endstop_holder_thickness,
    )
    endstop_holder_front_extension = align(
        endstop_holder_front_extension, endstop_board_base, Alignment.FRONT
    )
    endstop_holder_front_extension = align(
        endstop_holder_front_extension, endstop_holder, Alignment.LEFT
    )
    endstop_holder_front_extension = translate(
        0, -endstop_holder_extra_front_overlap, 0
    )(endstop_holder_front_extension)

    endstop_holder_size = get_bounding_box_size(endstop_holder)

    long_hole_cutter = create_rounded_slab(
        endstop_holder_size[2] - 3 * long_hole_width,
        long_hole_width,
        BIG_THING,
        round_radius=long_hole_width / 2,
    )

    long_hole_cutter = rotate(90)(long_hole_cutter)
    long_hole_cutter = rotate(90, axis=(1, 0, 0))(long_hole_cutter)

    long_hole_cutter = align(long_hole_cutter, endstop_holder, Alignment.CENTER)
    long_hole_cutter = align(long_hole_cutter, rail, Alignment.CENTER, axes=[0])

    square_mount_nut = create_square_nut("M3")
    square_mount_nut = rotate(90, axis=(1, 0, 0))(square_mount_nut)

    mount_nut_groove_cutter = materialize_bounding_box(
        square_mount_nut,
        x_enlargement=2 * mount_nut_slack,
        y_enlargement=2 * mount_nut_slack,
        z_size=500,
    )

    mount_nut_groove_cutter = align(
        mount_nut_groove_cutter, long_hole_cutter, Alignment.CENTER
    )
    mount_nut_groove_cutter = align(
        mount_nut_groove_cutter, long_hole_cutter, Alignment.BOTTOM
    )
    mount_nut_groove_cutter = align(
        mount_nut_groove_cutter, endstop_holder, Alignment.FRONT
    )
    square_mount_nut_size = get_bounding_box_size(square_mount_nut)
    mount_nut_groove_cutter = translate(
        0, mount_nut_front_wall, -square_mount_nut_size[2] / 2
    )(mount_nut_groove_cutter)

    endstop_holder = endstop_holder.fuse(endstop_holder_front_extension)

    endstop_holder = endstop_holder.cut(long_hole_cutter)
    endstop_holder = endstop_holder.cut(mount_nut_groove_cutter)

    rail_cutter = materialize_bounding_box(
        rail,
        x_enlargement=2 * endstop_rail_clearance,
        y_enlargement=2 * endstop_rail_clearance,
    )

    endstop_holder = endstop_holder.cut(rail_cutter)

    mount_guides = PartCollector()
    for fb in [Alignment.FRONT, Alignment.BACK]:
        mount_guide = materialize_bounding_box(
            endstop_board_base,
            x_size=mount_gap,
            y_size=mount_guide_width,
            z_enlargement=-4,
        )
        mount_guide = align(mount_guide, endstop_board_base, fb)
        mount_guide = align(mount_guide, endstop_holder, Alignment.STACK_LEFT)
        mount_guide = align(mount_guide, endstop_board_base, Alignment.BOTTOM)
        mount_guides = mount_guides.fuse(mount_guide)

    mount_bosses = PartCollector()
    mount_hole_cutters = PartCollector()
    square_nuts = []
    for cutter in endstop_board.cutters:
        cutter = align(
            cutter,
            endstop_holder,
            Alignment.STACK_LEFT,
            stack_gap=-2 * endstop_holder_thickness,
        )

        mount_boss = create_box(
            mount_boss_diameter, mount_boss_diameter, mount_gap
        )  # create_cylinder(mount_boss_diameter/2, mount_gap)
        mount_boss = rotate(45)(mount_boss)
        mount_boss = rotate(90, axis=(0, 1, 0))(mount_boss)
        mount_boss = align(mount_boss, cutter, Alignment.CENTER)
        mount_boss = align(mount_boss, endstop_holder, Alignment.STACK_LEFT)
        mount_bosses = mount_bosses.fuse(mount_boss)

        square_nut_cutter = create_square_nut(
            "M3", slack=nut_slack, height=endstop_holder_thickness, no_hole=True
        )
        square_nut_cutter = rotate(45)(square_nut_cutter)
        square_nut_cutter = rotate(90, axis=(0, 1, 0))(square_nut_cutter)
        square_nut_cutter = align(square_nut_cutter, cutter, Alignment.CENTER)
        square_nut_cutter = align(
            square_nut_cutter,
            endstop_holder,
            Alignment.LEFT,
        )

        square_nut_cutter = translate(square_nut_wall_thickness, 0, 0)(
            square_nut_cutter
        )

        cutter_shortener = create_box(500, 500, 500)
        cutter_shortener = align(cutter_shortener, cutter, Alignment.CENTER)
        cutter_shortener = align(
            cutter_shortener,
            mount_boss,
            Alignment.STACK_RIGHT,
            stack_gap=endstop_holder_thickness,
        )

        cutter = cutter.cut(cutter_shortener)

        mount_hole_cutters = mount_hole_cutters.fuse(square_nut_cutter)
        mount_hole_cutters = mount_hole_cutters.fuse(cutter)

        square_nut = create_square_nut("M3")
        square_nut = rotate(45)(square_nut)
        square_nut = rotate(90, axis=(0, 1, 0))(square_nut)
        square_nut = align(square_nut, square_nut_cutter, Alignment.CENTER)
        square_nut = align(square_nut, square_nut_cutter, Alignment.LEFT)

        square_nuts.append(square_nut)

    endstop_holder = endstop_holder.fuse(mount_guides)
    endstop_holder = endstop_holder.fuse(mount_bosses)
    endstop_holder = endstop_holder.cut(mount_hole_cutters)

    retval = LeaderFollowersCuttersPart(leader=endstop_holder)
    for i, square_nut in enumerate(square_nuts):
        retval.add_named_non_production_part(square_nut, f"square_nut_{i}")
    for name, part in endstop_board.get_named_non_production_part_items():
        full_name = f"endstop_{name}"
        retval.add_named_non_production_part(part, full_name)
        if name == "board":
            retval.set_hidden_by_default(full_name)

    return retval
