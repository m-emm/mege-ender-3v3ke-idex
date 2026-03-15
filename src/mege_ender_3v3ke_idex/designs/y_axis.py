"""
Y Axis

Usage:
    cd <project_root> && ./run.sh path/to/y_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/y_axis.py
"""

import logging
import os

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.metrics_collector import record_length_metric
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12ca_rail_with_carriages
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


def create_print_bed():

    plate = create_box(print_bed_width, print_bed_depth, print_bed_thickness)

    inset = (print_bed_depth - print_bed_mount_hole_pitch) / 2

    retval = LeaderFollowersCuttersPart(plate)

    for lr in [Alignment.EDGE_LEFT, Alignment.EDGE_RIGHT]:
        for fb in [Alignment.EDGE_FRONT, Alignment.EDGE_BACK]:

            hole_drill = create_cylinder(print_bed_mount_hole_diameter / 2, BIG_THING)
            hole_drill = align(hole_drill, plate, Alignment.CENTER, axes=[2])
            hole_drill = align(hole_drill, plate, lr)
            hole_drill = align(hole_drill, plate, fb)
            hole_drill = translate(-inset * lr.sign, -inset * fb.sign, 0)(hole_drill)

            retval = retval.cut(hole_drill)

            screw = create_conical_head_screw(
                print_bed_mount_screw_size, print_bed_mount_screw_length
            )

            screw = align(screw, hole_drill, Alignment.CENTER)
            screw = align(screw, plate, Alignment.TOP)

            retval.add_named_non_production_part(screw, f"screw_{lr.name}_{fb.name}")
            retval = retval.cut(screw)

            damper = create_cylinder(
                print_bed_damper_diameter / 2, print_bed_damper_height
            )

            damper = align(damper, hole_drill, Alignment.CENTER)
            damper = align(damper, plate, Alignment.STACK_BOTTOM)
            damper = damper.cut(hole_drill)

            retval.add_named_non_production_part(damper, f"damper_{lr.name}_{fb.name}")

    foil = create_box(print_bed_width, print_bed_depth, print_bed_foil_thickness)
    foil = align(foil, plate, Alignment.CENTER, axes=[0, 1])
    foil = align(foil, plate, Alignment.STACK_TOP)
    retval.add_named_non_production_part(foil, "print_bed_foil")

    return retval


def create_positioned_print_bed(y_axis, frame):
    y_axis_carriages = PartCollector()
    for name, follower in y_axis.get_named_follower_items():
        if "carriage" not in name:
            continue

        y_axis_carriages = y_axis_carriages.fuse(follower)

    print_bed = create_print_bed()
    print_bed = align(print_bed, y_axis_carriages, Alignment.CENTER, axes=[0, 1])
    print_bed = align(
        print_bed,
        frame,
        Alignment.STACK_TOP,
        stack_gap=print_bed_vertical_gap_to_frame,
    )

    return print_bed


def align_y_axis_to_frame(y_axis, frame):
    y_axis = align(y_axis, frame, Alignment.CENTER, axes=[0, 1])
    y_axis_profile_left = y_axis.get_non_production_part_by_name("profile_left")

    axis_aligner = align_translation(
        y_axis_profile_left, frame, Alignment.CENTER, axes=[2]
    )

    return axis_aligner(y_axis)


def create_y_axis():
    """Create the y_axis part."""

    rails = []
    for i in [-1, 1]:

        rail_side_name = "left" if i == -1 else "right"
        record_length_metric(
            "extrusion_profile",
            ExtrusionProfileType.PROFILE_2020.value,
            f"y_axis_profile_{rail_side_name}",
            y_axis_profile_length,
        )
        profile = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_2020, length_mm=y_axis_profile_length
        )

        profile = rotate(90, axis=(1, 0, 0))(profile)
        profile = align(profile, None, Alignment.CENTER)
        profile = translate(i * y_axis_rail_spacing / 2, 0, 0)(profile)

        rail_side_name = "left" if i == -1 else "right"
        record_length_metric(
            "linear_rail",
            "MGN12",
            f"y_axis_rail_{rail_side_name}",
            y_axis_rail_length,
        )
        rail = create_mgn12ca_rail_with_carriages(
            y_axis_rail_length,
            carriage_offsets=[
                -y_axis_rail_length / 2 + mgn_12ca_carriage_length / 2,
                -y_axis_rail_length / 2
                + y_axis_carriage_spacing
                + mgn_12ca_carriage_length / 2,
            ],
            carriage_names=["carriage_front", "carriage_back"],
        )
        rail = rotate(90)(rail)
        rail = rail.prefixed_copy(f"rail_{rail_side_name}")
        rail.rename_follower(
            f"rail_{rail_side_name}_carriage_front",
            f"carriage_front_carriage_{rail_side_name}",
        )
        rail.rename_follower(
            f"rail_{rail_side_name}_carriage_back",
            f"carriage_back_carriage_{rail_side_name}",
        )

        rail = align(rail, profile, Alignment.CENTER)
        rail = align(rail, profile, Alignment.STACK_TOP)
        rail.add_named_non_production_part(profile, f"profile_{rail_side_name}")

        rails.append(rail)

    return rails[0].fuse(rails[1])


def main():

    from mege_ender_3v3ke_idex.designs.printer_frame import (  # noqa: F401
        create_printer_frame,
    )

    logging.basicConfig(level=logging.INFO)

    _logger.info(f"y_axis_profile_length: {y_axis_profile_length}")
    _logger.info(f"y_axis_rail_length: {y_axis_rail_length}")

    bed_animation = {"bed_y": (0, print_bed_y_travel, 0)}

    parts = PartList()

    frame = create_printer_frame()

    parts.add(frame, "printer_frame", flip=False, skip_in_production=True)

    y_axis = align_y_axis_to_frame(create_y_axis(), frame)
    print_bed = create_positioned_print_bed(y_axis, frame)

    parts.add(y_axis.leader, "y_axis", flip=False, skip_in_production=True)
    parts.add(
        print_bed,
        "print_bed",
        flip=False,
        skip_in_production=True,
        animation=bed_animation,
    )
    for name, npp in print_bed.get_named_non_production_part_items():
        parts.add(
            npp,
            name,
            flip=False,
            skip_in_production=True,
            animation=bed_animation,
        )

    for name, follower in y_axis.get_named_follower_items():
        animation = None

        if "carriage" in name:
            _logger.info(f"Using bed_animation for {name}")
            animation = bed_animation
        else:
            _logger.info(f"NOT Using bed_animation for {name}")

        parts.add(
            follower, name, flip=False, skip_in_production=True, animation=animation
        )

    for name, npp in y_axis.get_named_non_production_part_items():
        animation = None

        if "carriage" in name:
            _logger.info(f"Using bed_animation for {name}")
            animation = bed_animation
        else:
            _logger.info(f"NOT Using bed_animation for {name}")

        parts.add(npp, name, flip=False, skip_in_production=True, animation=animation)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        export_stl=PROD,
    )

    _logger.info("y_axis created successfully!")


if __name__ == "__main__":
    main()
