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

    screw_hole_diameter = MScrew.from_size("M3").clearance_hole_normal

    carriage = create_box(
        mgn_12h_carriage_length, mgn_12h_carriage_width, mgn_12h_height
    )

    holes = PartCollector()
    for x in [-mgn_12h_screw_hole_pitch / 2, mgn_12h_screw_hole_pitch / 2]:
        for y in [-mgn_12h_screw_hole_pitch / 2, mgn_12h_screw_hole_pitch / 2]:
            hole = create_cylinder(screw_hole_diameter / 2, mgn_12h_height)
            hole = translate(x, y, 0)(hole)
            holes = holes.fuse(hole)

    holes = align(holes, carriage, Alignment.CENTER)
    holes = align(
        holes, carriage, Alignment.STACK_TOP, stack_gap=-mgn_12h_screw_hole_depth
    )

    carriage = carriage.cut(holes)

    carriage = LeaderFollowersCuttersPart(carriage, cutters=[holes])

    carriage = translate(0, 0, mgn_12h_h1)(carriage)

    return carriage


def create_mgn12ca_carriage():
    """Create the MGN12CA carriage part."""

    screw_hole_diameter = MScrew.from_size("M3").clearance_hole_normal

    carriage = create_box(
        mgn_12ca_carriage_length, mgn_12ca_cariage_width, mgn_12ca_height
    )

    holes = PartCollector()
    for x in [-mgn_12ca_screw_hole_pitch / 2, mgn_12ca_screw_hole_pitch / 2]:
        for y in [-mgn_12ca_screw_hole_pitch / 2, mgn_12ca_screw_hole_pitch / 2]:
            hole = create_cylinder(screw_hole_diameter / 2, mgn_12ca_height)
            hole = translate(x, y, 0)(hole)
            holes = holes.fuse(hole)

    holes = align(holes, carriage, Alignment.CENTER)
    holes = align(
        holes, carriage, Alignment.STACK_TOP, stack_gap=-mgn_12ca_screw_hole_depth
    )

    carriage = carriage.cut(holes)

    carriage = LeaderFollowersCuttersPart(carriage, cutters=[holes])

    carriage = translate(0, 0, mgn_12ca_h1)(carriage)

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


def create_mgn12h_rail_with_carriages(
    length_mm: float,
    carriage_offsets=None,
    carriage_names=None,
):
    """Create a rail assembly with carriages mounted at the correct rail-relative height.

    The carriage body is modeled in its own local coordinates with the required vertical
    offset above the rail floor. By attaching carriages as followers of the rail assembly,
    any later alignment or translation of the assembly preserves that relationship.
    """

    rail = create_mgn12h_rail(length_mm=length_mm)

    if carriage_offsets is None:
        return rail

    if carriage_names is None:
        carriage_names = [f"carriage_{i + 1}" for i in range(len(carriage_offsets))]

    if len(carriage_names) != len(carriage_offsets):
        raise ValueError("carriage_names must match carriage_offsets length")

    for carriage_offset, carriage_name in zip(carriage_offsets, carriage_names):
        carriage = create_mgn12h_carriage()
        carriage = align(carriage, rail.leader, Alignment.CENTER, axes=[0, 1])
        carriage = translate(carriage_offset, 0, 0)(carriage)
        carriage = carriage.prefixed_copy(carriage_name)
        rail.add_named_follower(carriage.leader, name=carriage_name)
        rail = rail.merge_except_leader(carriage)

    return rail


def create_mgn12ca_rail_with_carriages(
    length_mm: float,
    carriage_offsets=None,
    carriage_names=None,
):
    """Create a rail assembly with carriages mounted at the correct rail-relative height.

    The carriage body is modeled in its own local coordinates with the required vertical
    offset above the rail floor. By attaching carriages as followers of the rail assembly,
    any later alignment or translation of the assembly preserves that relationship.
    """

    rail = create_mgn12h_rail(length_mm=length_mm)

    if carriage_offsets is None:
        return rail

    if carriage_names is None:
        carriage_names = [f"carriage_{i + 1}" for i in range(len(carriage_offsets))]

    if len(carriage_names) != len(carriage_offsets):
        raise ValueError("carriage_names must match carriage_offsets length")

    for carriage_offset, carriage_name in zip(carriage_offsets, carriage_names):
        carriage = create_mgn12ca_carriage()
        carriage = align(carriage, rail.leader, Alignment.CENTER, axes=[0, 1])
        carriage = translate(carriage_offset, 0, 0)(carriage)
        carriage = carriage.prefixed_copy(carriage_name)
        rail.add_named_follower(carriage.leader, name=carriage_name)
        rail = rail.merge_except_leader(carriage)

    return rail


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_mgn12h_rail_with_carriages(length_mm=150, carriage_offsets=[0])
    parts.add(part.leader, "mgh_linear", flip=False)
    parts.add(
        part.get_named_follower("carriage_1"),
        "mgh_linear_carriage",
        flip=False,
    )

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
