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
from mege_ender_3v3ke_idex.designs.metrics_collector import (
    Material,
    log_metrics_report,
    record_length_metric,
    record_measured_mass_metric,
    record_weight_metric,
    reset_metrics,
)
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12ca_rail_with_carriages
from mege_ender_3v3ke_idex.designs.print_bed import create_print_bed
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


def _record_weight_for_part(part, *, material: Material, part_id: str):
    record_weight_metric(
        Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
        material,
        get_volume(part),
        part_id=part_id,
    )


def _record_y_axis_carriage_weight_metrics(y_axis):
    carriage_volume_mm3 = 0.0
    for name, part in y_axis.get_named_follower_items():
        if "carriage" not in name:
            continue
        carriage_volume_mm3 += get_volume(part)

    if carriage_volume_mm3 > 0:
        record_weight_metric(
            Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
            Material.STEEL,
            carriage_volume_mm3,
            part_id="mgn12ca_carriages",
        )


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

    y_axis = rails[0].fuse(rails[1])
    _record_y_axis_carriage_weight_metrics(y_axis)

    return y_axis


def main():

    from mege_ender_3v3ke_idex.designs.printer_frame import (  # noqa: F401
        create_printer_frame,
    )

    logging.basicConfig(level=logging.INFO)
    reset_metrics()

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

    log_metrics_report(_logger)
    _logger.info(
        "Y-axis moving mass currently includes the bed plate, magnetic foil, MGN12CA carriages, and bed screws. "
        "The bed plate and foil use measured masses. The linear rails do not move and are excluded. "
        "The bed holder is not implemented yet, and dampers are currently excluded."
    )

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
