"""
Endstop Holder

Usage:
    cd <project_root> && ./run.sh path/to/endstop_holder.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/endstop_holder.py
"""

import logging
import os

import numpy as np
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# Optional slicer process overrides
PROCESS_DATA = {
    "filament": "FilamentPLAMegeMaster",
    "process_overrides": {
        "nozzle_diameter": "0.6",
        "layer_height": "0.2",
    },
}

BIG_THING = 500

endstop_board_length = 40
endstop_board_width = 16
endstop_board_thickness = 1.1
endstop_board_plug_thickness = 6.7
endstop_board_plug_width = 12.4
endstop_board_plug_length = 9.6

endstop_board_tongue_length = 16.7
endstop_board_tongue_thickness = 0.3
endstop_board_tongue_height = 3.6
endstop_board_tongue_angle = 20
endstop_switch_length = 12.85
endstop_switch_width = 6.6
endstop_switch_thickness = 5.5
endstop_switch_x_offset = 5
endstop_board_hole_diameter = 3.6
endstop_board_hole_inset = 1.0

endstop_board_holder_thickness = 6.5
endstop_board_holder_sink = 1.5

endstop_board_holder_length = 40
endstop_board_holder_width = 18
endstop_board_holder_screw_size = "M3"
endstop_board_holder_screw_length = 12
endstop_board_holder_board_clearance = 0.45
endstop_board_holder_nut_cutter_slack = 0.2


endstop_board_holder_oversize_y = 1
endstop_board_holder_oversize_x = 3


def create_endstop_board():
    base = create_box(
        endstop_board_length, endstop_board_width, endstop_board_thickness
    )

    # Create plug
    plug = create_box(
        endstop_board_plug_length,
        endstop_board_plug_width,
        endstop_board_plug_thickness,
    )
    plug = align(plug, base, Alignment.CENTER)
    plug = align(plug, base, Alignment.STACK_TOP)
    plug = align(plug, base, Alignment.RIGHT)

    # Create microwitch with tongue
    switch = create_box(
        endstop_switch_length, endstop_switch_width, endstop_switch_thickness
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

    for fb in [Alignment.FRONT, Alignment.BACK]:
        hole = create_cylinder(endstop_board_hole_diameter / 2, BIG_THING)

        hole = align(hole, base, Alignment.CENTER)
        hole = align(
            hole,
            base,
            fb.stack_alignment,
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
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        hole = create_cylinder(endstop_board_hole_diameter / 2, BIG_THING)

        hole = align(hole, base, Alignment.CENTER)
        hole = align(
            hole, switch, lr.stack_alignment, stack_gap=endstop_board_hole_inset
        )
        hole = align(
            hole,
            base,
            Alignment.STACK_FRONT,
            stack_gap=-endstop_board_hole_diameter - endstop_board_hole_inset,
        )
        base = base.cut(hole)
        screw_holes.append(hole)

    retval = LeaderFollowersCuttersPart(base.fuse(switch).fuse(tongue).fuse(plug))

    for i, hole in enumerate(screw_holes):
        retval.add_named_cutter(hole, f"screw_hole_{i+1}")
    retval.add_named_follower(base, "base")
    retval.add_named_follower(tongue, "tongue")

    return retval


def create_endstop_holder() -> LeaderFollowersCuttersPart:
    """Create the endstop_holder part."""

    board = create_endstop_board()

    pcb = board.get_named_follower("base")
    pcb_size = np.array(get_bounding_box_size(pcb))

    base = create_box(
        endstop_board_holder_length + endstop_board_holder_oversize_x,
        endstop_board_holder_width + endstop_board_holder_oversize_y,
        endstop_board_holder_thickness,
    )

    base = align(base, pcb, Alignment.CENTER)
    base = align(base, pcb, Alignment.TOP)
    base = align(base, pcb, Alignment.FRONT)
    base = translate(0, -endstop_board_holder_oversize_y, 0)(base)

    pcb_cutter = create_box(
        pcb_size[0]
        + endstop_board_holder_board_clearance * 2
        + endstop_board_holder_oversize_x,
        pcb_size[1]
        + endstop_board_holder_board_clearance * 2
        + endstop_board_holder_oversize_y,
        pcb_size[2] + endstop_board_holder_sink,
    )

    pcb_cutter = align(pcb_cutter, pcb, Alignment.CENTER)
    pcb_cutter = align(pcb_cutter, pcb, Alignment.TOP)
    pcb_cutter = translate(0, -endstop_board_holder_oversize_y, 0)(pcb_cutter)

    base = base.cut(pcb_cutter)

    for cutter in board.cutters:

        spacer_width = (
            get_bounding_box_size(cutter)[0] + 2 * endstop_board_holder_board_clearance
        )
        spacer_thickness = endstop_board_holder_thickness - endstop_board_thickness

        spacer_length = endstop_board_holder_width + endstop_board_holder_oversize_y

        spacer = create_box(spacer_width, spacer_length, spacer_thickness)
        spacer = align(spacer, cutter, Alignment.CENTER)
        spacer = align(spacer, base, Alignment.BACK)
        spacer = align(spacer, base, Alignment.BOTTOM)

        base = base.fuse(spacer)

        screw_hole_drill = create_cylinder(
            MScrew.from_size(endstop_board_holder_screw_size).clearance_hole_normal / 2,
            BIG_THING,
        )
        screw_hole_drill = align(screw_hole_drill, cutter, Alignment.CENTER)
        base = base.cut(screw_hole_drill)

        nut_cutter = create_nut(
            endstop_board_holder_screw_size, slack=endstop_board_holder_nut_cutter_slack
        )
        nut_cutter = align(nut_cutter, screw_hole_drill, Alignment.CENTER)
        nut_cutter = align(nut_cutter, base, Alignment.BOTTOM)
        base = base.cut(nut_cutter)

    retval = LeaderFollowersCuttersPart(base)

    retval.add_named_non_production_part(board.leader, "board")
    for npp, name in board.get_named_non_production_part_items():
        retval.add_named_non_production_part(npp, name)

    tongue = board.get_named_follower("tongue")
    retval.add_named_non_production_part(tongue, "tongue")

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    holder = create_endstop_holder()

    parts.add(holder, "endstop_holder", flip=False)

    for name, part in holder.get_named_non_production_part_items():
        parts.add(part, name, flip=False, skip_in_production=True)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("endstop_holder created successfully!")


if __name__ == "__main__":
    main()
