"""Y-axis endstop holder assembly."""

import numpy as np
from shellforgepy.simple import *

BIG_THING = 500

DEFAULT_ENDSTOP_BOARD_LENGTH = 40
DEFAULT_ENDSTOP_BOARD_WIDTH = 16
DEFAULT_ENDSTOP_BOARD_THICKNESS = 1.1
DEFAULT_ENDSTOP_BOARD_PLUG_THICKNESS = 6.7
DEFAULT_ENDSTOP_BOARD_PLUG_WIDTH = 12.4
DEFAULT_ENDSTOP_BOARD_PLUG_LENGTH = 9.6

DEFAULT_ENDSTOP_BOARD_TONGUE_LENGTH = 16.7
DEFAULT_ENDSTOP_BOARD_TONGUE_THICKNESS = 0.3
DEFAULT_ENDSTOP_BOARD_TONGUE_HEIGHT = 3.6
DEFAULT_ENDSTOP_BOARD_TONGUE_ANGLE = 20
DEFAULT_ENDSTOP_SWITCH_LENGTH = 12.85
DEFAULT_ENDSTOP_SWITCH_WIDTH = 6.6
DEFAULT_ENDSTOP_SWITCH_THICKNESS = 5.5
DEFAULT_ENDSTOP_SWITCH_X_OFFSET = 5
DEFAULT_ENDSTOP_BOARD_HOLE_DIAMETER = 3.6
DEFAULT_ENDSTOP_BOARD_HOLE_INSET = 1.0

DEFAULT_ENDSTOP_BOARD_HOLDER_THICKNESS = 6.5
DEFAULT_ENDSTOP_BOARD_HOLDER_SINK = 1.5
DEFAULT_ENDSTOP_BOARD_HOLDER_LENGTH = 40
DEFAULT_ENDSTOP_BOARD_HOLDER_WIDTH = 18
DEFAULT_ENDSTOP_BOARD_HOLDER_SCREW_SIZE = "M3"
DEFAULT_ENDSTOP_BOARD_HOLDER_BOARD_CLEARANCE = 0.45
DEFAULT_ENDSTOP_BOARD_HOLDER_NUT_CUTTER_SLACK = 0.2
DEFAULT_ENDSTOP_BOARD_HOLDER_OVERSIZE_Y = 1
DEFAULT_ENDSTOP_BOARD_HOLDER_OVERSIZE_X = 3
DEFAULT_LOCAL_UP = (0.0, 0.0, 1.0)
DEFAULT_LOCAL_OUT = (0.0, -1.0, 0.0)


def _create_endstop_board(
    *,
    endstop_board_length=DEFAULT_ENDSTOP_BOARD_LENGTH,
    endstop_board_width=DEFAULT_ENDSTOP_BOARD_WIDTH,
    endstop_board_thickness=DEFAULT_ENDSTOP_BOARD_THICKNESS,
    endstop_board_plug_thickness=DEFAULT_ENDSTOP_BOARD_PLUG_THICKNESS,
    endstop_board_plug_width=DEFAULT_ENDSTOP_BOARD_PLUG_WIDTH,
    endstop_board_plug_length=DEFAULT_ENDSTOP_BOARD_PLUG_LENGTH,
    endstop_board_tongue_length=DEFAULT_ENDSTOP_BOARD_TONGUE_LENGTH,
    endstop_board_tongue_thickness=DEFAULT_ENDSTOP_BOARD_TONGUE_THICKNESS,
    endstop_board_tongue_height=DEFAULT_ENDSTOP_BOARD_TONGUE_HEIGHT,
    endstop_board_tongue_angle=DEFAULT_ENDSTOP_BOARD_TONGUE_ANGLE,
    endstop_switch_length=DEFAULT_ENDSTOP_SWITCH_LENGTH,
    endstop_switch_width=DEFAULT_ENDSTOP_SWITCH_WIDTH,
    endstop_switch_thickness=DEFAULT_ENDSTOP_SWITCH_THICKNESS,
    endstop_switch_x_offset=DEFAULT_ENDSTOP_SWITCH_X_OFFSET,
    endstop_board_hole_diameter=DEFAULT_ENDSTOP_BOARD_HOLE_DIAMETER,
    endstop_board_hole_inset=DEFAULT_ENDSTOP_BOARD_HOLE_INSET,
    big_thing=BIG_THING,
):
    base = create_box(
        endstop_board_length,
        endstop_board_width,
        endstop_board_thickness,
    )

    plug = create_box(
        endstop_board_plug_length,
        endstop_board_plug_width,
        endstop_board_plug_thickness,
    )
    plug = align(plug, base, Alignment.CENTER)
    plug = align(plug, base, Alignment.STACK_TOP)
    plug = align(plug, base, Alignment.RIGHT)

    switch = create_box(
        endstop_switch_length,
        endstop_switch_width,
        endstop_switch_thickness,
    )
    switch = align(switch, base, Alignment.CENTER)
    switch = align(switch, base, Alignment.STACK_TOP)
    switch = align(switch, base, Alignment.LEFT)
    switch = align(switch, base, Alignment.FRONT)
    switch = translate(endstop_switch_x_offset, 0, 0)(switch)

    tongue = create_box(
        endstop_board_tongue_length,
        endstop_board_tongue_thickness,
        endstop_board_tongue_height,
    )
    tongue = rotate(endstop_board_tongue_angle)(tongue)
    tongue = align(tongue, switch, Alignment.CENTER)
    tongue = align(tongue, switch, Alignment.RIGHT)
    tongue = align(tongue, switch, Alignment.STACK_FRONT)

    for front_back_alignment in [Alignment.FRONT, Alignment.BACK]:
        hole = create_cylinder(endstop_board_hole_diameter / 2, big_thing)
        hole = align(hole, base, Alignment.CENTER)
        hole = align(
            hole,
            base,
            front_back_alignment.stack_alignment,
            stack_gap=-endstop_board_hole_diameter - endstop_board_hole_inset,
        )
        hole = align(
            hole,
            base,
            Alignment.STACK_RIGHT,
            stack_gap=-endstop_board_hole_diameter - endstop_board_hole_inset,
        )
        base = base.cut(hole)

    screw_holes = []
    for left_right_alignment in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(endstop_board_hole_diameter / 2, big_thing)
        hole = align(hole, base, Alignment.CENTER)
        hole = align(
            hole,
            switch,
            left_right_alignment.stack_alignment,
            stack_gap=endstop_board_hole_inset,
        )
        hole = align(
            hole,
            base,
            Alignment.STACK_FRONT,
            stack_gap=-endstop_board_hole_diameter - endstop_board_hole_inset,
        )
        base = base.cut(hole)
        screw_holes.append(hole)

    endstop_board = LeaderFollowersCuttersPart(
        base.fuse(switch).fuse(tongue).fuse(plug)
    )
    for index, hole in enumerate(screw_holes):
        endstop_board.add_named_cutter(hole, f"screw_hole_{index + 1}")
    endstop_board.add_named_follower(base, "base")
    endstop_board.add_named_follower(tongue, "tongue")
    return endstop_board


def create_y_axis_endstop_holder_assembly(
    *,
    endstop_board_length=DEFAULT_ENDSTOP_BOARD_LENGTH,
    endstop_board_width=DEFAULT_ENDSTOP_BOARD_WIDTH,
    endstop_board_thickness=DEFAULT_ENDSTOP_BOARD_THICKNESS,
    endstop_board_plug_thickness=DEFAULT_ENDSTOP_BOARD_PLUG_THICKNESS,
    endstop_board_plug_width=DEFAULT_ENDSTOP_BOARD_PLUG_WIDTH,
    endstop_board_plug_length=DEFAULT_ENDSTOP_BOARD_PLUG_LENGTH,
    endstop_board_tongue_length=DEFAULT_ENDSTOP_BOARD_TONGUE_LENGTH,
    endstop_board_tongue_thickness=DEFAULT_ENDSTOP_BOARD_TONGUE_THICKNESS,
    endstop_board_tongue_height=DEFAULT_ENDSTOP_BOARD_TONGUE_HEIGHT,
    endstop_board_tongue_angle=DEFAULT_ENDSTOP_BOARD_TONGUE_ANGLE,
    endstop_switch_length=DEFAULT_ENDSTOP_SWITCH_LENGTH,
    endstop_switch_width=DEFAULT_ENDSTOP_SWITCH_WIDTH,
    endstop_switch_thickness=DEFAULT_ENDSTOP_SWITCH_THICKNESS,
    endstop_switch_x_offset=DEFAULT_ENDSTOP_SWITCH_X_OFFSET,
    endstop_board_hole_diameter=DEFAULT_ENDSTOP_BOARD_HOLE_DIAMETER,
    endstop_board_hole_inset=DEFAULT_ENDSTOP_BOARD_HOLE_INSET,
    endstop_board_holder_thickness=DEFAULT_ENDSTOP_BOARD_HOLDER_THICKNESS,
    endstop_board_holder_sink=DEFAULT_ENDSTOP_BOARD_HOLDER_SINK,
    endstop_board_holder_length=DEFAULT_ENDSTOP_BOARD_HOLDER_LENGTH,
    endstop_board_holder_width=DEFAULT_ENDSTOP_BOARD_HOLDER_WIDTH,
    endstop_board_holder_screw_size=DEFAULT_ENDSTOP_BOARD_HOLDER_SCREW_SIZE,
    endstop_board_holder_board_clearance=DEFAULT_ENDSTOP_BOARD_HOLDER_BOARD_CLEARANCE,
    endstop_board_holder_nut_cutter_slack=DEFAULT_ENDSTOP_BOARD_HOLDER_NUT_CUTTER_SLACK,
    endstop_board_holder_oversize_y=DEFAULT_ENDSTOP_BOARD_HOLDER_OVERSIZE_Y,
    endstop_board_holder_oversize_x=DEFAULT_ENDSTOP_BOARD_HOLDER_OVERSIZE_X,
    up=DEFAULT_LOCAL_UP,
    out=DEFAULT_LOCAL_OUT,
    big_thing=BIG_THING,
) -> LeaderFollowersCuttersPart:
    """Create the y-axis endstop holder assembly with vector-defined orientation."""

    board = _create_endstop_board(
        endstop_board_length=endstop_board_length,
        endstop_board_width=endstop_board_width,
        endstop_board_thickness=endstop_board_thickness,
        endstop_board_plug_thickness=endstop_board_plug_thickness,
        endstop_board_plug_width=endstop_board_plug_width,
        endstop_board_plug_length=endstop_board_plug_length,
        endstop_board_tongue_length=endstop_board_tongue_length,
        endstop_board_tongue_thickness=endstop_board_tongue_thickness,
        endstop_board_tongue_height=endstop_board_tongue_height,
        endstop_board_tongue_angle=endstop_board_tongue_angle,
        endstop_switch_length=endstop_switch_length,
        endstop_switch_width=endstop_switch_width,
        endstop_switch_thickness=endstop_switch_thickness,
        endstop_switch_x_offset=endstop_switch_x_offset,
        endstop_board_hole_diameter=endstop_board_hole_diameter,
        endstop_board_hole_inset=endstop_board_hole_inset,
        big_thing=big_thing,
    )

    pcb = board.get_named_follower("base")
    pcb_size = np.array(get_bounding_box_size(pcb))

    holder = create_box(
        endstop_board_holder_length + endstop_board_holder_oversize_x,
        endstop_board_holder_width + endstop_board_holder_oversize_y,
        endstop_board_holder_thickness,
    )
    holder = align(holder, pcb, Alignment.CENTER)
    holder = align(holder, pcb, Alignment.TOP)
    holder = align(holder, pcb, Alignment.FRONT)
    holder = translate(0, -endstop_board_holder_oversize_y, 0)(holder)

    pcb_cutter = create_box(
        pcb_size[0]
        + 2 * endstop_board_holder_board_clearance
        + endstop_board_holder_oversize_x,
        pcb_size[1]
        + 2 * endstop_board_holder_board_clearance
        + endstop_board_holder_oversize_y,
        pcb_size[2] + endstop_board_holder_sink,
    )
    pcb_cutter = align(pcb_cutter, pcb, Alignment.CENTER)
    pcb_cutter = align(pcb_cutter, pcb, Alignment.TOP)
    pcb_cutter = translate(0, -endstop_board_holder_oversize_y, 0)(pcb_cutter)
    holder = holder.cut(pcb_cutter)

    for cutter in board.cutters:
        spacer_width = (
            get_bounding_box_size(cutter)[0] + 2 * endstop_board_holder_board_clearance
        )
        spacer_thickness = endstop_board_holder_thickness - endstop_board_thickness
        spacer_length = endstop_board_holder_width + endstop_board_holder_oversize_y

        spacer = create_box(spacer_width, spacer_length, spacer_thickness)
        spacer = align(spacer, cutter, Alignment.CENTER)
        spacer = align(spacer, holder, Alignment.BACK)
        spacer = align(spacer, holder, Alignment.BOTTOM)
        holder = holder.fuse(spacer)

        screw_hole_drill = create_cylinder(
            MScrew.from_size(endstop_board_holder_screw_size).clearance_hole_normal / 2,
            big_thing,
        )
        screw_hole_drill = align(screw_hole_drill, cutter, Alignment.CENTER)
        holder = holder.cut(screw_hole_drill)

        nut_cutter = create_nut(
            endstop_board_holder_screw_size,
            slack=endstop_board_holder_nut_cutter_slack,
        )
        nut_cutter = align(nut_cutter, screw_hole_drill, Alignment.CENTER)
        nut_cutter = align(nut_cutter, holder, Alignment.BOTTOM)
        holder = holder.cut(nut_cutter)

    assembly = LeaderFollowersCuttersPart(holder)
    assembly.add_named_follower(holder, "holder")
    assembly.add_named_non_production_part(board.leader, "board")
    for name, non_production_part in board.get_named_non_production_part_items():
        assembly.add_named_non_production_part(non_production_part, name)
    assembly.add_named_non_production_part(board.get_named_follower("tongue"), "tongue")

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
    return transform(assembly)
