"""Creality endstop holder assembly."""

import copy

from shellforgepy.simple import *

BIG_THING = 500
DEFAULT_LOCAL_UP = (0.0, 0.0, 1.0)
DEFAULT_LOCAL_OUT = (0.0, -1.0, 0.0)


def create_creality_endstop_holder_assembly(
    *,
    creality_endstop_board_assembly,
    creality_endstop_holder_board_clearance,
    creality_endstop_holder_thickness,
    creality_endstop_holder_sink,
    creality_endstop_holder_length_oversize,
    creality_endstop_holder_width_oversize,
    creality_endstop_holder_screw_size,
    creality_endstop_holder_nut_cutter_slack,
    up=DEFAULT_LOCAL_UP,
    out=DEFAULT_LOCAL_OUT,
    big_thing=BIG_THING,
) -> LeaderFollowersCuttersPart:
    """Create a printable holder for the Creality-style endstop board."""

    board = copy.deepcopy(creality_endstop_board_assembly)

    pcb = board.get_named_follower("base")
    pcb_size = get_bounding_box_size(pcb)

    holder = create_box(
        pcb_size[0] + creality_endstop_holder_width_oversize,
        pcb_size[1] + creality_endstop_holder_length_oversize,
        creality_endstop_holder_thickness,
    )
    holder = align(holder, pcb, Alignment.CENTER)
    holder = align(holder, pcb, Alignment.TOP)

    holder = align(holder, pcb, Alignment.BACK)
    holder = translate(0, creality_endstop_holder_board_clearance, 0)(holder)

    pcb_cutter = create_box(
        pcb_size[0] + 2 * creality_endstop_holder_board_clearance,
        pcb_size[1] + 2 * creality_endstop_holder_board_clearance,
        pcb_size[2] + creality_endstop_holder_sink,
    )
    pcb_cutter = align(pcb_cutter, pcb, Alignment.CENTER)
    pcb_cutter = align(pcb_cutter, pcb, Alignment.TOP)
    holder = holder.cut(pcb_cutter)

    spacers = PartCollector()

    for cutter in board.cutters:
        cutter_size = get_bounding_box_size(cutter)
        spacer_width = cutter_size[0] * 1.5
        spacer_length = 2 * cutter_size[1]
        spacer_thickness = creality_endstop_holder_thickness - pcb_size[2]

        fillet_radius = min(spacer_width, spacer_length, spacer_thickness) / 4
        spacer = create_filleted_box(
            spacer_width,
            spacer_length,
            spacer_thickness,
            fillet_radius=fillet_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
        )
        spacer = align(spacer, cutter, Alignment.CENTER)
        spacer = align(spacer, pcb, Alignment.FRONT)
        spacer = align(spacer, holder, Alignment.BOTTOM)

        screw_hole_drill = create_cylinder(
            MScrew.from_size(creality_endstop_holder_screw_size).clearance_hole_loose
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

        spacer = spacer.cut(screw_hole_drill)
        spacer = spacer.cut(nut_cutter)
        spacers = spacers.fuse(spacer)

    holder = holder.fuse(spacers)
    assembly = LeaderFollowersCuttersPart(holder)
    assembly.add_named_follower(holder, "holder")
    for name, non_production_part in board.get_named_non_production_part_items():
        assembly.add_named_non_production_part(non_production_part, name)

    assembly.add_named_cutter(pcb_cutter, "pcb_cutter")
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
