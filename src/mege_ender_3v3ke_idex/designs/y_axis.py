"""
Y Axis

Usage:
    cd <project_root> && ./run.sh path/to/y_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/y_axis.py
"""

import copy
import inspect
import logging
import math
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import (
    create_gt2_pulley,
    create_gt2belt,
    gt2_pitch,
    gt2_teeth_thickness,
    gt2_thickness,
    gt2_width,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.idler_cage import create_idler_cage
from mege_ender_3v3ke_idex.designs.metrics_collector import (
    Material,
    log_metrics_report,
    record_length_metric,
    record_weight_metric,
    reset_metrics,
)
from mege_ender_3v3ke_idex.designs.mgh_linear import create_mgn12ca_rail_with_carriages
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
from mege_ender_3v3ke_idex.designs.print_bed import (
    Y_AXIS_MOVING_MASS_ASSEMBLY_ID,
    add_print_bed_parts_to_assembly,
    create_print_bed,
)
from mege_ender_3v3ke_idex.designs.print_bed_undercarriage import (
    create_print_bed_undercarriage,
)
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (
    create_four_screws_mount_assembly,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)
PROCESS_DATA["process_overrides"].update(
    {
        "brim_type": "no_brim",
        "enable_support": "0",
        "support_object_first_layer_gap": 0.8,
        "external_perimeter_speed": "75",
        "fan_max_speed": "25",
        "fan_min_speed": "10",
        "outer_wall_speed": "75",
        "sparse_infill_density": "75%",
        "support_critical_regions_only": "1",
        "support_interface_spacing": "0.8",
        "support_on_build_plate_only": "1",
        "support_threshold_angle": "30",
        "support_top_z_distance": "0.3",
        "wall_loops": "3",
    }
)


y_axis_drive_profile_mount_plate_width = z_axis_profile_mount_width
y_axis_drive_profile_mount_plate_height = z_axis_profile_mount_plate_height
y_axis_drive_profile_mount_plate_thickness = z_axis_profile_mount_plate_thickness
y_axis_drive_profile_mount_plate_fillet_radius = (
    z_axis_profile_mount_plate_fillet_radius
)
y_axis_drive_mount_screw_inset = 5
y_axis_drive_mount_screw_size = "M5"
y_axis_drive_motor_plate_width = motor_mount_plate_size
y_axis_drive_motor_plate_depth = 60
y_axis_drive_idler_plate_width = 34
y_axis_drive_idler_plate_depth = 40
y_axis_drive_motor_pulley_teeth = 20
y_axis_drive_idler_teeth = 20
y_axis_drive_belt_clear_span_extra = 0
y_axis_drive_idler_housing_side_wall = endcap_wall
y_axis_drive_idler_housing_front_wall = motor_mount_plate_thickness
y_axis_drive_idler_housing_top_wall = 1.0
y_axis_drive_idler_cage_top_clearance = 0.0
y_axis_drive_idler_cage_front_clearance = idler_cage_clearance
y_axis_drive_idler_cage_height = 19
y_axis_drive_clamped_run_side = Alignment.RIGHT
y_axis_drive_use_toothed_belt_visuals = False
y_axis_drive_clamped_run_contact_alignment = (
    Alignment.STACK_LEFT
    if y_axis_drive_clamped_run_side == Alignment.RIGHT
    else Alignment.STACK_RIGHT
)
y_axis_drive_return_run_alignment = (
    Alignment.STACK_LEFT
    if y_axis_drive_clamped_run_side == Alignment.RIGHT
    else Alignment.STACK_RIGHT
)
gt2_idler_running_surface_diameter_factor = 1.061032953945969



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


def _get_y_axis_carriages_fused(y_axis):
    y_axis_carriages = PartCollector()
    for name, follower in y_axis.get_named_follower_items():
        if "carriage" not in name:
            continue

        y_axis_carriages = y_axis_carriages.fuse(follower)

    return y_axis_carriages


def _align_y_axis_to_print_bed_undercarriage(y_axis, frame):
    reference_print_bed = create_positioned_print_bed(
        y_axis,
        frame,
        record_metrics=False,
    )
    undercarriage = create_print_bed_undercarriage(
        reference_print_bed,
        record_metrics=False,
    )
    y_axis_carriages = _get_y_axis_carriages_fused(y_axis)

    undercarriage_bb = get_bounding_box(undercarriage.leader)
    y_axis_carriages_bb = get_bounding_box(y_axis_carriages)
    y_axis_drop_mm = y_axis_carriages_bb[1][2] - undercarriage_bb[0][2]

    _logger.info(
        "Dropping y_axis by %.3f mm so the print bed undercarriage seats on the Y carriages while preserving the bed Z reference",
        y_axis_drop_mm,
    )

    return translate(0, 0, -y_axis_drop_mm)(y_axis)


def create_positioned_print_bed(y_axis, frame, *, record_metrics=True):
    y_axis_carriages = _get_y_axis_carriages_fused(y_axis)

    print_bed = create_print_bed(record_metrics=record_metrics)
    print_bed = align(print_bed, y_axis_carriages, Alignment.CENTER, axes=[0, 1])
    print_bed = align(
        print_bed,
        frame,
        Alignment.STACK_TOP,
        stack_gap=print_bed_vertical_gap_to_frame,
    )

    return print_bed


def create_positioned_print_bed_assembly(y_axis, frame):
    print_bed = create_positioned_print_bed(y_axis, frame)
    print_bed_undercarriage = create_print_bed_undercarriage(print_bed)
    return add_print_bed_parts_to_assembly(print_bed_undercarriage, print_bed)


def align_y_axis_to_frame(y_axis, frame):
    y_axis = align(y_axis, frame, Alignment.CENTER, axes=[0, 1])
    y_axis_profile_left = y_axis.get_non_production_part_by_name("profile_left")

    axis_aligner = align_translation(
        y_axis_profile_left, frame, Alignment.CENTER, axes=[2]
    )

    y_axis = axis_aligner(y_axis)

    return _align_y_axis_to_print_bed_undercarriage(y_axis, frame)





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
    print_bed_assembly = create_positioned_print_bed_assembly(y_axis, frame)
    y_axis = add_y_axis_drive_hardware(y_axis, print_bed_assembly, frame)

    parts.add(y_axis.leader, "y_axis", flip=False, skip_in_production=True)
    # parts.add(
    #     print_bed_assembly,
    #     "print_bed_undercarriage",
    #     flip=False,
    #     skip_in_production=False,
    #     animation=bed_animation,
    # )
    for name, follower in print_bed_assembly.get_named_follower_items():
        parts.add(
            follower,
            name,
            flip=False,
            skip_in_production=True,
            animation=bed_animation,
        )
    for name, npp in print_bed_assembly.get_named_non_production_part_items():
        parts.add(
            npp,
            name,
            flip=False,
            skip_in_production=True,
            animation=bed_animation,
        )

    for name, follower in y_axis.get_named_follower_items():
        animation = None
        skip_in_production = True

        if "carriage" in name:
            _logger.info(f"Using bed_animation for {name}")
            animation = bed_animation
        elif "mount" in name or "cage" in name:
            skip_in_production = False
        else:
            _logger.info(f"NOT Using bed_animation for {name}")

        parts.add(
            follower,
            name,
            flip=False,
            skip_in_production=skip_in_production,
            animation=animation,
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
        "Y-axis moving mass currently includes the bed plate, magnetic foil, MGN12CA carriages, bed screws, "
        "the PETG_CF print bed undercarriage, and the aluminum mount towers. "
        "The bed plate and foil use measured masses. The linear rails do not move and are excluded. "
        "Dampers are currently excluded."
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
