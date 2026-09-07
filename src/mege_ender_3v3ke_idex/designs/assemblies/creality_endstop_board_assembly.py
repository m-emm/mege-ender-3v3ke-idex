"""Creality-style endstop board assembly."""

from shellforgepy.simple import *

big_thing = 500

default_creality_endstop_board_length = 20.2
default_creality_endstop_board_width = 20.2
default_creality_endstop_board_thickness = 1.6
default_creality_endstop_board_fillet_radius = 1.0

default_creality_endstop_board_hole_diameter = 3.0
default_creality_endstop_board_hole_front_inset = 1.3
default_creality_endstop_board_hole_side_inset = 1.1

default_creality_endstop_switch_length = 12.85
default_creality_endstop_switch_width = 6.7
default_creality_endstop_switch_thickness = 6.8
default_creality_endstop_switch_back_inset = 1.2
default_creality_endstop_switch_x_offset = 1.0

default_creality_endstop_lever_length = 16.0
default_creality_endstop_lever_width = 0.6
default_creality_endstop_lever_thickness = 0.35
default_creality_endstop_lever_height = 5
default_creality_endstop_lever_angle = 20
default_creality_endstop_lever_x_offset = 1.2
default_creality_endstop_lever_overlap = 0.2

default_creality_endstop_plug_length = 8.8
default_creality_endstop_plug_width = 9.6
default_creality_endstop_plug_thickness = 5.8
default_creality_endstop_plug_front_overhang = 3.8

default_local_up = (0.0, 0.0, 1.0)
default_local_out = (0.0, -1.0, 0.0)


def create_creality_endstop_board_assembly() -> LeaderFollowersCuttersPart:
    """Create a Creality-style mechanical endstop board model."""

    base = create_filleted_box(
        default_creality_endstop_board_length,
        default_creality_endstop_board_width,
        default_creality_endstop_board_thickness,
        default_creality_endstop_board_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    mounting_holes = []
    for left_right_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(
            default_creality_endstop_board_hole_diameter / 2, big_thing
        )
        hole = align(hole, base, Alignment.CENTER)
        hole = align(
            hole,
            base,
            Alignment.STACK_FRONT,
            stack_gap=-default_creality_endstop_board_hole_diameter
            - default_creality_endstop_board_hole_front_inset,
        )
        hole = align(
            hole,
            base,
            left_right_alignment.stack_alignment,
            stack_gap=-default_creality_endstop_board_hole_diameter
            - default_creality_endstop_board_hole_side_inset,
        )
        base = base.cut(hole)
        mounting_holes.append(hole)

    switch = create_box(
        default_creality_endstop_switch_length,
        default_creality_endstop_switch_width,
        default_creality_endstop_switch_thickness,
    )
    switch = align(switch, base, Alignment.CENTER)
    switch = align(switch, base, Alignment.STACK_TOP)
    switch = align(switch, base, Alignment.BACK)
    switch = translate(
        default_creality_endstop_switch_x_offset,
        -default_creality_endstop_switch_back_inset,
        0,
    )(switch)

    lever = create_box(
        default_creality_endstop_lever_length,
        default_creality_endstop_lever_width,
        default_creality_endstop_lever_height,
    )
    lever = rotate(default_creality_endstop_lever_angle)(lever)
    lever = align(lever, switch, Alignment.CENTER)
    lever = align(lever, switch, Alignment.LEFT)
    lever = align(
        lever,
        switch,
        Alignment.STACK_BACK,
        stack_gap=-default_creality_endstop_lever_overlap,
    )

    lever = translate(default_creality_endstop_lever_x_offset, 0, 0)(lever)

    plug = create_box(
        default_creality_endstop_plug_length,
        default_creality_endstop_plug_width,
        default_creality_endstop_plug_thickness,
    )
    plug = align(plug, base, Alignment.CENTER)
    plug = align(plug, base, Alignment.STACK_TOP)
    plug = align(plug, base, Alignment.FRONT)
    plug = translate(0, -default_creality_endstop_plug_front_overhang, 0)(plug)

    leader = base.fuse(switch).fuse(lever).fuse(plug)
    board = LeaderFollowersCuttersPart(leader)

    for index, hole in enumerate(mounting_holes):
        board.add_named_cutter(hole, f"mounting_hole_{index + 1}")

    board.add_named_non_production_part(base, "base")
    board.add_named_non_production_part(switch, "switch")
    board.add_named_non_production_part(lever, "lever")
    board.add_named_non_production_part(lever, "tongue")
    board.add_named_non_production_part(plug, "plug")
    board.add_named_non_production_part(leader, "board")

    board.set_hidden_by_default("board")

    transform = coordinate_system_transformation_function(
        origin_a=(0, 0, 0),
        up_a=default_local_up,
        out_a=default_local_out,
        origin_b=(0, 0, 0),
        up_b=default_local_up,
        out_b=default_local_out,
        degree_rotation_function_generator=rotate,
        translation_function_generator=translate,
    )
    return transform(board)
