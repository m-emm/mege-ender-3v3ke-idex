"""Creality endstop holder assembly."""

from mege_ender_3v3ke_idex.designs.assemblies.creality_endstop_board_assembly import (
    BIG_THING,
    DEFAULT_LOCAL_OUT,
    DEFAULT_LOCAL_UP,
    create_creality_endstop_board,
)
from shellforgepy.simple import *

DEFAULT_CREALITY_ENDSTOP_HOLDER_THICKNESS = 6.0
DEFAULT_CREALITY_ENDSTOP_HOLDER_SINK = 1.2
DEFAULT_CREALITY_ENDSTOP_HOLDER_LENGTH_OVERSIZE = 3
DEFAULT_CREALITY_ENDSTOP_HOLDER_WIDTH_OVERSIZE = 3
DEFAULT_CREALITY_ENDSTOP_HOLDER_SCREW_SIZE = "M3"
DEFAULT_CREALITY_ENDSTOP_HOLDER_BOARD_CLEARANCE = 0.45
DEFAULT_CREALITY_ENDSTOP_HOLDER_NUT_CUTTER_SLACK = 0.2


def create_creality_endstop_holder_assembly(
    *,
    creality_endstop_holder_thickness=DEFAULT_CREALITY_ENDSTOP_HOLDER_THICKNESS,
    creality_endstop_holder_sink=DEFAULT_CREALITY_ENDSTOP_HOLDER_SINK,
    creality_endstop_holder_length_oversize=DEFAULT_CREALITY_ENDSTOP_HOLDER_LENGTH_OVERSIZE,
    creality_endstop_holder_width_oversize=DEFAULT_CREALITY_ENDSTOP_HOLDER_WIDTH_OVERSIZE,
    creality_endstop_holder_screw_size=DEFAULT_CREALITY_ENDSTOP_HOLDER_SCREW_SIZE,
    creality_endstop_holder_board_clearance=DEFAULT_CREALITY_ENDSTOP_HOLDER_BOARD_CLEARANCE,
    creality_endstop_holder_nut_cutter_slack=DEFAULT_CREALITY_ENDSTOP_HOLDER_NUT_CUTTER_SLACK,
    up=DEFAULT_LOCAL_UP,
    out=DEFAULT_LOCAL_OUT,
    big_thing=BIG_THING,
) -> LeaderFollowersCuttersPart:
    """Create a printable holder for the Creality-style endstop board."""

    board = create_creality_endstop_board(big_thing=big_thing)

    pcb = board.get_named_follower("base")
    pcb_size = get_bounding_box_size(pcb)

    holder = create_box(
        pcb_size[0] + creality_endstop_holder_length_oversize,
        pcb_size[1] + creality_endstop_holder_width_oversize,
        creality_endstop_holder_thickness,
    )
    holder = align(holder, pcb, Alignment.CENTER)
    holder = align(holder, pcb, Alignment.TOP)

    pcb_cutter = create_box(
        pcb_size[0] + 2 * creality_endstop_holder_board_clearance,
        pcb_size[1] + 2 * creality_endstop_holder_board_clearance,
        pcb_size[2] + creality_endstop_holder_sink,
    )
    pcb_cutter = align(pcb_cutter, pcb, Alignment.CENTER)
    pcb_cutter = align(pcb_cutter, pcb, Alignment.TOP)
    holder = holder.cut(pcb_cutter)

    for cutter in board.cutters:
        spacer_width = (
            get_bounding_box_size(cutter)[0]
            + 2 * creality_endstop_holder_board_clearance
        )
        spacer_length = pcb_size[1] + creality_endstop_holder_width_oversize
        spacer_thickness = creality_endstop_holder_thickness - pcb_size[2]

        spacer = create_box(spacer_width, spacer_length, spacer_thickness)
        spacer = align(spacer, cutter, Alignment.CENTER)
        spacer = align(spacer, holder, Alignment.BACK)
        spacer = align(spacer, holder, Alignment.BOTTOM)
        holder = holder.fuse(spacer)

        screw_hole_drill = create_cylinder(
            MScrew.from_size(creality_endstop_holder_screw_size).clearance_hole_normal
            / 2,
            big_thing,
        )
        screw_hole_drill = align(screw_hole_drill, cutter, Alignment.CENTER)
        holder = holder.cut(screw_hole_drill)

        nut_cutter = create_nut(
            creality_endstop_holder_screw_size,
            slack=creality_endstop_holder_nut_cutter_slack,
        )
        nut_cutter = align(nut_cutter, screw_hole_drill, Alignment.CENTER)
        nut_cutter = align(nut_cutter, holder, Alignment.BOTTOM)
        holder = holder.cut(nut_cutter)

    assembly = LeaderFollowersCuttersPart(holder)
    assembly.add_named_follower(holder, "holder")
    for name, non_production_part in board.get_named_non_production_part_items():
        assembly.add_named_non_production_part(non_production_part, name)

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
