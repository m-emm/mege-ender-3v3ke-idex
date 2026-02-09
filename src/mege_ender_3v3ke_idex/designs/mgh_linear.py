"""
Mgh Linear

Usage:
    cd <project_root> && ./run.sh path/to/mgh_linear.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/mgh_linear.py
"""

import logging
import os

from mege_ender_3v3ke_idex.designs.idex_parameters import *
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


def create_mgn12h_carriage():
    """Create the MGN12H carriage part."""

    width = 27
    length = 45.4
    screw_hole_pitch = 20
    height = 10
    screw_hole_depth = 3.5
    screw_hole_diameter = MScrew.from_size("M3").clearance_hole_normal
    h1 = 3.4

    carriage = create_box(length, width, height)

    holes = PartCollector()
    for x in [-screw_hole_pitch / 2, screw_hole_pitch / 2]:
        for y in [-screw_hole_pitch / 2, screw_hole_pitch / 2]:
            hole = create_cylinder(screw_hole_diameter / 2, height)
            hole = translate(x, y, 0)(hole)
            holes = holes.fuse(hole)

    holes = align(holes, carriage, Alignment.CENTER)
    holes = align(holes, carriage, Alignment.STACK_TOP, stack_gap=-screw_hole_depth)

    carriage = carriage.cut(holes)

    carriage = LeaderFollowersCuttersPart(carriage, cutters=[holes])

    carriage = translate(0, 0, h1)(carriage)

    return carriage


def create_mgn12h_rail(length_mm: float):
    """Create the MGN12H rail part."""

    width = 12
    height = 8.5
    hole_pitch = 25
    top_hole_diameter = 8
    bottom_hole_diameter = 4.5
    top_hole_depth = 4.5

    rail = create_box(length_mm, width, height)

    num_holes = int(length_mm // hole_pitch)
    holes_aligned = []

    if num_holes > 0:
        holes = PartCollector()
        holes_list = []
        for i in range(num_holes):
            x = i * hole_pitch
            # Top hole
            top_hole = create_cylinder(top_hole_diameter / 2, top_hole_depth)
            top_hole = translate(x, 0, 0)(top_hole)
            top_hole = align(top_hole, rail, Alignment.TOP)

            current_hole = top_hole
            holes = holes.fuse(top_hole)
            # Bottom hole
            bottom_hole = create_cylinder(bottom_hole_diameter / 2, height)
            bottom_hole = translate(x, 0, 0)(bottom_hole)
            bottom_hole = align(bottom_hole, rail, Alignment.BOTTOM)
            holes = holes.fuse(bottom_hole)
            current_hole = current_hole.fuse(bottom_hole)
            holes_list.append(current_hole)

        holes_align_translation = align_translation(
            holes, rail, Alignment.CENTER, axes=[0, 1]
        )

        holes_aligned = [holes_align_translation(hole) for hole in holes_list]

        for hole in holes_aligned:
            rail = rail.cut(hole)

    return LeaderFollowersCuttersPart(rail, cutters=holes_aligned)


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_mgn12h_rail(length_mm=150)
    parts.add(part, "mgh_linear", flip=False)

    carriage = create_mgn12h_carriage()
    carriage = align(carriage, part, Alignment.CENTER, axes=[0, 1])
    parts.add(carriage, "mgh_linear_carriage", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("mgh_linear created successfully!")


if __name__ == "__main__":
    main()
