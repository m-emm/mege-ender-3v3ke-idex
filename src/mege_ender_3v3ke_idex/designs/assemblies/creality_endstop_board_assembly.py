"""Creality-style endstop board assembly."""

from shellforgepy.simple import *

BIG_THING = 500

DEFAULT_CREALITY_ENDSTOP_BOARD_LENGTH = 20.2
DEFAULT_CREALITY_ENDSTOP_BOARD_WIDTH = 20.2
DEFAULT_CREALITY_ENDSTOP_BOARD_THICKNESS = 1.6
DEFAULT_CREALITY_ENDSTOP_BOARD_FILLET_RADIUS = 1.0

DEFAULT_CREALITY_ENDSTOP_BOARD_HOLE_DIAMETER = 3.0
DEFAULT_CREALITY_ENDSTOP_BOARD_HOLE_FRONT_INSET = 1.3
DEFAULT_CREALITY_ENDSTOP_BOARD_HOLE_SIDE_INSET = 1.1

DEFAULT_CREALITY_ENDSTOP_SWITCH_LENGTH = 12.85
DEFAULT_CREALITY_ENDSTOP_SWITCH_WIDTH = 6.7
DEFAULT_CREALITY_ENDSTOP_SWITCH_THICKNESS = 6.8
DEFAULT_CREALITY_ENDSTOP_SWITCH_BACK_INSET = 1.2
DEFAULT_CREALITY_ENDSTOP_SWITCH_X_OFFSET = 1.0

DEFAULT_CREALITY_ENDSTOP_LEVER_LENGTH = 16.0
DEFAULT_CREALITY_ENDSTOP_LEVER_WIDTH = 0.6
DEFAULT_CREALITY_ENDSTOP_LEVER_THICKNESS = 0.35
DEFAULT_CREALITY_ENDSTOP_LEVER_HEIGHT = 5
DEFAULT_CREALITY_ENDSTOP_LEVER_ANGLE = 20
DEFAULT_CREALITY_ENDSTOP_LEVER_X_OFFSET = 1.2
DEFAULT_CREALITY_ENDSTOP_LEVER_OVERLAP = 0.2

DEFAULT_CREALITY_ENDSTOP_PLUG_LENGTH = 8.8
DEFAULT_CREALITY_ENDSTOP_PLUG_WIDTH = 9.6
DEFAULT_CREALITY_ENDSTOP_PLUG_THICKNESS = 5.8
DEFAULT_CREALITY_ENDSTOP_PLUG_FRONT_OVERHANG = 3.8

DEFAULT_LOCAL_UP = (0.0, 0.0, 1.0)
DEFAULT_LOCAL_OUT = (0.0, -1.0, 0.0)


def create_creality_endstop_board(
    *,
    creality_endstop_board_length=DEFAULT_CREALITY_ENDSTOP_BOARD_LENGTH,
    creality_endstop_board_width=DEFAULT_CREALITY_ENDSTOP_BOARD_WIDTH,
    creality_endstop_board_thickness=DEFAULT_CREALITY_ENDSTOP_BOARD_THICKNESS,
    creality_endstop_board_fillet_radius=DEFAULT_CREALITY_ENDSTOP_BOARD_FILLET_RADIUS,
    creality_endstop_board_hole_diameter=DEFAULT_CREALITY_ENDSTOP_BOARD_HOLE_DIAMETER,
    creality_endstop_board_hole_front_inset=DEFAULT_CREALITY_ENDSTOP_BOARD_HOLE_FRONT_INSET,
    creality_endstop_board_hole_side_inset=DEFAULT_CREALITY_ENDSTOP_BOARD_HOLE_SIDE_INSET,
    creality_endstop_switch_length=DEFAULT_CREALITY_ENDSTOP_SWITCH_LENGTH,
    creality_endstop_switch_width=DEFAULT_CREALITY_ENDSTOP_SWITCH_WIDTH,
    creality_endstop_switch_thickness=DEFAULT_CREALITY_ENDSTOP_SWITCH_THICKNESS,
    creality_endstop_switch_back_inset=DEFAULT_CREALITY_ENDSTOP_SWITCH_BACK_INSET,
    creality_endstop_switch_x_offset=DEFAULT_CREALITY_ENDSTOP_SWITCH_X_OFFSET,
    creality_endstop_lever_length=DEFAULT_CREALITY_ENDSTOP_LEVER_LENGTH,
    creality_endstop_lever_width=DEFAULT_CREALITY_ENDSTOP_LEVER_WIDTH,
    creality_endstop_lever_thickness=DEFAULT_CREALITY_ENDSTOP_LEVER_THICKNESS,
    creality_endstop_lever_height=DEFAULT_CREALITY_ENDSTOP_LEVER_HEIGHT,
    creality_endstop_lever_angle=DEFAULT_CREALITY_ENDSTOP_LEVER_ANGLE,
    creality_endstop_lever_x_offset=DEFAULT_CREALITY_ENDSTOP_LEVER_X_OFFSET,
    creality_endstop_lever_overlap=DEFAULT_CREALITY_ENDSTOP_LEVER_OVERLAP,
    creality_endstop_plug_length=DEFAULT_CREALITY_ENDSTOP_PLUG_LENGTH,
    creality_endstop_plug_width=DEFAULT_CREALITY_ENDSTOP_PLUG_WIDTH,
    creality_endstop_plug_thickness=DEFAULT_CREALITY_ENDSTOP_PLUG_THICKNESS,
    creality_endstop_plug_front_overhang=DEFAULT_CREALITY_ENDSTOP_PLUG_FRONT_OVERHANG,
    big_thing=BIG_THING,
):
    base = create_filleted_box(
        creality_endstop_board_length,
        creality_endstop_board_width,
        creality_endstop_board_thickness,
        creality_endstop_board_fillet_radius,
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    mounting_holes = []
    for left_right_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(creality_endstop_board_hole_diameter / 2, big_thing)
        hole = align(hole, base, Alignment.CENTER)
        hole = align(
            hole,
            base,
            Alignment.STACK_FRONT,
            stack_gap=-creality_endstop_board_hole_diameter
            - creality_endstop_board_hole_front_inset,
        )
        hole = align(
            hole,
            base,
            left_right_alignment.stack_alignment,
            stack_gap=-creality_endstop_board_hole_diameter
            - creality_endstop_board_hole_side_inset,
        )
        base = base.cut(hole)
        mounting_holes.append(hole)

    switch = create_box(
        creality_endstop_switch_length,
        creality_endstop_switch_width,
        creality_endstop_switch_thickness,
    )
    switch = align(switch, base, Alignment.CENTER)
    switch = align(switch, base, Alignment.STACK_TOP)
    switch = align(switch, base, Alignment.BACK)
    switch = translate(
        creality_endstop_switch_x_offset,
        -creality_endstop_switch_back_inset,
        0,
    )(switch)

    lever = create_box(
        creality_endstop_lever_length,
        creality_endstop_lever_width,
        creality_endstop_lever_height,
    )
    lever = rotate(creality_endstop_lever_angle)(lever)
    lever = align(lever, switch, Alignment.CENTER)
    lever = align(lever, switch, Alignment.LEFT)
    lever = align(
        lever,
        switch,
        Alignment.STACK_BACK,
        stack_gap=-creality_endstop_lever_overlap,
    )
    
    lever = translate(creality_endstop_lever_x_offset, 0, 0)(lever)

    plug = create_box(
        creality_endstop_plug_length,
        creality_endstop_plug_width,
        creality_endstop_plug_thickness,
    )
    plug = align(plug, base, Alignment.CENTER)
    plug = align(plug, base, Alignment.STACK_TOP)
    plug = align(plug, base, Alignment.FRONT)
    plug = translate(0, -creality_endstop_plug_front_overhang, 0)(plug)

    leader = (
        base.fuse(switch)
        .fuse(lever)
        .fuse(plug)
    )
    creality_endstop_board = LeaderFollowersCuttersPart(leader)

    for index, hole in enumerate(mounting_holes):
        creality_endstop_board.add_named_cutter(hole, f"mounting_hole_{index + 1}")

    creality_endstop_board.add_named_follower(base, "base")
    creality_endstop_board.add_named_follower(switch, "switch")
    creality_endstop_board.add_named_follower(lever, "lever")
    creality_endstop_board.add_named_follower(lever, "tongue")
    creality_endstop_board.add_named_follower(plug, "plug")
    creality_endstop_board.add_named_non_production_part(leader, "board")

    return creality_endstop_board


def create_creality_endstop_board_assembly(
    *,
    creality_endstop_board_length=DEFAULT_CREALITY_ENDSTOP_BOARD_LENGTH,
    creality_endstop_board_width=DEFAULT_CREALITY_ENDSTOP_BOARD_WIDTH,
    creality_endstop_board_thickness=DEFAULT_CREALITY_ENDSTOP_BOARD_THICKNESS,
    creality_endstop_board_fillet_radius=DEFAULT_CREALITY_ENDSTOP_BOARD_FILLET_RADIUS,
    creality_endstop_board_hole_diameter=DEFAULT_CREALITY_ENDSTOP_BOARD_HOLE_DIAMETER,
    creality_endstop_board_hole_front_inset=DEFAULT_CREALITY_ENDSTOP_BOARD_HOLE_FRONT_INSET,
    creality_endstop_board_hole_side_inset=DEFAULT_CREALITY_ENDSTOP_BOARD_HOLE_SIDE_INSET,
    creality_endstop_switch_length=DEFAULT_CREALITY_ENDSTOP_SWITCH_LENGTH,
    creality_endstop_switch_width=DEFAULT_CREALITY_ENDSTOP_SWITCH_WIDTH,
    creality_endstop_switch_thickness=DEFAULT_CREALITY_ENDSTOP_SWITCH_THICKNESS,
    creality_endstop_switch_back_inset=DEFAULT_CREALITY_ENDSTOP_SWITCH_BACK_INSET,
    creality_endstop_switch_x_offset=DEFAULT_CREALITY_ENDSTOP_SWITCH_X_OFFSET,
    creality_endstop_lever_length=DEFAULT_CREALITY_ENDSTOP_LEVER_LENGTH,
    creality_endstop_lever_width=DEFAULT_CREALITY_ENDSTOP_LEVER_WIDTH,
    creality_endstop_lever_thickness=DEFAULT_CREALITY_ENDSTOP_LEVER_THICKNESS,
    creality_endstop_lever_height=DEFAULT_CREALITY_ENDSTOP_LEVER_HEIGHT,
    creality_endstop_lever_angle=DEFAULT_CREALITY_ENDSTOP_LEVER_ANGLE,
    creality_endstop_lever_x_offset=DEFAULT_CREALITY_ENDSTOP_LEVER_X_OFFSET,
    creality_endstop_lever_overlap=DEFAULT_CREALITY_ENDSTOP_LEVER_OVERLAP,
    creality_endstop_plug_length=DEFAULT_CREALITY_ENDSTOP_PLUG_LENGTH,
    creality_endstop_plug_width=DEFAULT_CREALITY_ENDSTOP_PLUG_WIDTH,
    creality_endstop_plug_thickness=DEFAULT_CREALITY_ENDSTOP_PLUG_THICKNESS,
    creality_endstop_plug_front_overhang=DEFAULT_CREALITY_ENDSTOP_PLUG_FRONT_OVERHANG,
    up=DEFAULT_LOCAL_UP,
    out=DEFAULT_LOCAL_OUT,
    big_thing=BIG_THING,
) -> LeaderFollowersCuttersPart:
    """Create a Creality-style mechanical endstop board model."""

    board = create_creality_endstop_board(
        creality_endstop_board_length=creality_endstop_board_length,
        creality_endstop_board_width=creality_endstop_board_width,
        creality_endstop_board_thickness=creality_endstop_board_thickness,
        creality_endstop_board_fillet_radius=creality_endstop_board_fillet_radius,
        creality_endstop_board_hole_diameter=creality_endstop_board_hole_diameter,
        creality_endstop_board_hole_front_inset=creality_endstop_board_hole_front_inset,
        creality_endstop_board_hole_side_inset=creality_endstop_board_hole_side_inset,
        creality_endstop_switch_length=creality_endstop_switch_length,
        creality_endstop_switch_width=creality_endstop_switch_width,
        creality_endstop_switch_thickness=creality_endstop_switch_thickness,
        creality_endstop_switch_back_inset=creality_endstop_switch_back_inset,
        creality_endstop_switch_x_offset=creality_endstop_switch_x_offset,
        creality_endstop_lever_length=creality_endstop_lever_length,
        creality_endstop_lever_width=creality_endstop_lever_width,
        creality_endstop_lever_thickness=creality_endstop_lever_thickness,
        creality_endstop_lever_height=creality_endstop_lever_height,
        creality_endstop_lever_angle=creality_endstop_lever_angle,
        creality_endstop_lever_x_offset=creality_endstop_lever_x_offset,
        creality_endstop_lever_overlap=creality_endstop_lever_overlap,
        creality_endstop_plug_length=creality_endstop_plug_length,
        creality_endstop_plug_width=creality_endstop_plug_width,
        creality_endstop_plug_thickness=creality_endstop_plug_thickness,
        creality_endstop_plug_front_overhang=creality_endstop_plug_front_overhang,
        big_thing=big_thing,
    )

    transform = coordinate_system_transformation_function(
        origin_a=(0, 0, 0),
        up_a=DEFAULT_LOCAL_UP,
        out_a=DEFAULT_LOCAL_OUT,
        origin_b=(0, 0, 0),
        up_b=up,
        out_b=out,
        degree_rotation_function_generator=rotate,
        translation_function_generator=translate,
    )
    return transform(board)