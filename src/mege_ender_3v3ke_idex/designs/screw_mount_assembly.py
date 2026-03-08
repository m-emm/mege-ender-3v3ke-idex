"""
Screw Mount Assembly

Usage:
    cd <project_root> && ./run.sh path/to/screw_mount_assembly.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/screw_mount_assembly.py
"""

import logging
import os

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


def create_single_screw_mount_for_top(
    part_thickness,
    screw_size,
    screw_length,
    with_nut_cutter=True,
    nut_cutter_clearance=0.15,
    flush_with_top=False,
    cylincder_head_cutter_clearance=0.1,
):

    screw = create_cylinder_screw(screw_size, screw_length)
    screw = translate(0, 0, -screw_length)(screw)

    m_screw_record = MScrew.from_size(screw_size)
    cylinder_head_height = m_screw_record.cylinder_head_height

    if flush_with_top:
        screw = translate(0, 0, -cylinder_head_height)(screw)

    size_float = float(screw_size[1:])

    screw_body = create_cylinder(size_float / 2, screw_length)

    screw_body = align(screw_body, screw, Alignment.CENTER)
    screw_body = align(screw_body, screw, Alignment.BOTTOM)

    hole_cutter = create_cylinder(
        m_screw_record.clearance_hole_normal / 2, part_thickness
    )

    hole_cutter = align(hole_cutter, screw_body, Alignment.CENTER)
    hole_cutter = align(hole_cutter, screw_body, Alignment.TOP)

    retval = LeaderFollowersCuttersPart(screw_body)
    retval.add_named_cutter(hole_cutter, "hole_cutter")

    if with_nut_cutter:
        nut_cutter = create_nut(
            screw_size,
            height=BIG_THING,
            slack=nut_cutter_clearance,
        )

        nut_cutter = align(nut_cutter, screw_body, Alignment.CENTER)
        nut_cutter = align(
            nut_cutter,
            screw_body,
            Alignment.STACK_BOTTOM,
            stack_gap=-m_screw_record.nut_thickness * 1.5 - nut_cutter_clearance,
        )

        retval.add_named_cutter(nut_cutter, "nut_cutter")

        nut = create_nut(screw_size)
        nut = align(nut, screw_body, Alignment.CENTER)
        nut = align(
            nut,
            screw_body,
            Alignment.BOTTOM,
        )
        nut = translate(0, 0, m_screw_record.nut_thickness / 2)(nut)
        retval.add_named_non_production_part(nut, "nut")

    if flush_with_top:

        cylinder_head_cutter = create_cylinder(
            m_screw_record.cylinder_head_diameter / 2 + cylincder_head_cutter_clearance,
            cylinder_head_height + cylincder_head_cutter_clearance,
        )
        cylinder_head_cutter = align(cylinder_head_cutter, screw, Alignment.CENTER)
        cylinder_head_cutter = align(cylinder_head_cutter, screw, Alignment.TOP)
        retval.add_named_cutter(cylinder_head_cutter, "cylinder_head_cutter")

    retval.add_named_non_production_part(screw, "screw")

    return retval


def create_screw_mount_assembly(
    for_part,
    screw_sicz,
    screw_length,
    screw_direction=Alignment.TOP,
    num_screws=4,
    depth_inset=None,
    width_inset=None,
):
    """Create the screw_mount_assembly"""
    # Example: simple box with a cylindrical hole
    width = 30
    depth = 20
    height = 10
    hole_radius = 4

    # Create base box
    part = create_box(width, depth, height)

    # Create a hole cutter
    hole = create_cylinder(hole_radius, height + 2)
    hole = align(hole, part, Alignment.CENTER)
    hole = translate(0, 0, -1)(hole)

    # Cut the hole
    part = part.cut(hole)

    return part


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    test_thickness = 30
    base_plate = create_box(50, 50, test_thickness)
    base_plate = translate(0, 0, -test_thickness)(base_plate)

    single_screw_mount = create_single_screw_mount_for_top(
        test_thickness,
        "M3",
        25,
    )

    single_screw_mount = align(
        single_screw_mount, base_plate, Alignment.CENTER, axes=[0, 1]
    )  # leave z alignment alone, to test if the z is correctly aligned

    for name, npp in single_screw_mount.get_named_non_production_part_items():
        parts.add(npp, name, skip_in_production=True)

    base_plate = single_screw_mount.use_as_cutter_on(base_plate)



    single_screw_mount_2 = create_single_screw_mount_for_top(
        test_thickness,
        "M3",
        25,
        flush_with_top=True,
    )

    single_screw_mount_2 = align(
        single_screw_mount_2, base_plate, Alignment.CENTER, axes=[0, 1]
    )  

    single_screw_mount_2 = translate(10, 0, 0)(single_screw_mount_2)

    for name, npp in single_screw_mount_2.get_named_non_production_part_items():
        parts.add(npp, name + "_2", skip_in_production=True)
    base_plate = single_screw_mount_2.use_as_cutter_on(base_plate)

    base_plate, _ = cut_in_two(base_plate, cut_normal=(0, 1, 0))



    parts.add(
        base_plate,
        "base_plate",
    )

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("screw_mount_assembly created successfully!")


if __name__ == "__main__":
    main()
