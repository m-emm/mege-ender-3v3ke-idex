"""
Z Axis

Usage:
    cd <project_root> && ./run.sh path/to/z_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/z_axis.py
"""

import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.gt2belt import create_gt_belt_clamp
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.mgh_linear import (
    create_mgn12h_carriage,
    create_mgn12h_rail,
)
from mege_ender_3v3ke_idex.designs.sprite_extruder import create_sprite_extruder
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"


_logger = logging.getLogger(__name__)

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)
PROCESS_DATA["process_overrides"].update(
    {
        "brim_type": "no_brim",
        "enable_support": "1",
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

z_axis_threaded_rod_diameter = 8
z_axis_threaded_rod_length = 500

z_axis_guide_rod_length = 600
z_axis_guide_rod_diameter = 8

z_axis_profile_length = 700

z_axis_guide_rod_threaded_rod_distance = 18
z_axis_guide_rod_profile_distance = 50

z_axis_carriage_height = 60
z_axis_carriage_width = 45
z_axis_carriage_depth = 50
z_axis_carriage_fillet_radius = 4
z_axis_carriage_mount_screw_size = "M3"
z_axis_carriage_bearing_inset = 5
z_axis_carriage_threaded_rod_clearance = 0.3
z_axis_carriage_profile_clearance = 2

igus_drylin_bearing_inner_diameter = 8
igus_drylin_bearing_outer_diameter = 16
igus_drylin_bearing_length = 25


def create_igus_drylin_bearing(cutter_clearance=0.1, cutter_extra_length=2):
    bearing = create_ring(
        igus_drylin_bearing_outer_diameter / 2,
        igus_drylin_bearing_inner_diameter / 2,
        igus_drylin_bearing_length,
    )
    cutter = create_cylinder(
        (igus_drylin_bearing_outer_diameter / 2) + cutter_clearance,
        igus_drylin_bearing_length + cutter_extra_length,
    )
    cutter = align(cutter, bearing, Alignment.CENTER)

    retval = LeaderFollowersCuttersPart(bearing, cutters=[cutter])

    return retval


def create_creality_threaded_rod_nut():
    base_thickness = 3.5
    base_width = 12.5
    base_cut_radius = 15
    base_length = 23.8
    rod_guide_diameter = 9.97
    rod_guide_height = 10.55
    rod_guide_bottom_overstand = 2
    mount_hole_center_center_distance = 16.5
    mount_screw_size = "M3"

    base = create_box(base_length, base_width, base_thickness)

    mount_hole_drill_diaameter = MScrew.from_size(mount_screw_size).core_hole
    external_mount_hole_drill_diameter = MScrew.from_size(
        mount_screw_size
    ).clearance_hole_normal

    base_cutter = create_box(BIG_THING, BIG_THING, 2 * base_thickness)
    external_mount_hole_drills = []
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        cutter_reducer = create_cylinder(base_cut_radius, 2 * base_thickness)
        cutter_reducer = align(cutter_reducer, base_cutter, Alignment.CENTER)
        cutter_reducer = align(cutter_reducer, base_cutter, lr)

        current_cutter_lfc = LeaderFollowersCuttersPart(cutter_reducer)
        current_cutter = base_cutter.cut(cutter_reducer)
        current_cutter_lfc.add_named_cutter(current_cutter, "base_cutter")
        current_cutter_lfc = align(current_cutter_lfc, base, Alignment.CENTER)
        current_cutter_lfc = align(current_cutter_lfc, base, lr)

        base = current_cutter_lfc.use_as_cutter_on(base)

        mount_hole_drill_cutter = create_cylinder(
            mount_hole_drill_diaameter / 2, 2 * base_thickness
        )
        mount_hole_drill_cutter = align(mount_hole_drill_cutter, base, Alignment.CENTER)
        mount_hole_drill_cutter = translate(
            lr.sign * mount_hole_center_center_distance / 2, 0, 0
        )(mount_hole_drill_cutter)

        external_mount_hole_drill = create_cylinder(
            external_mount_hole_drill_diameter / 2, BIG_THING
        )
        external_mount_hole_drill = align(
            external_mount_hole_drill, mount_hole_drill_cutter, Alignment.CENTER
        )
        external_mount_hole_drill = external_mount_hole_drill.cut(base)
        external_mount_hole_drills.append(external_mount_hole_drill)

        base = base.cut(mount_hole_drill_cutter)

    rod_guide = create_cylinder(rod_guide_diameter / 2, rod_guide_height)

    rod_guide = align(rod_guide, base, Alignment.CENTER)
    rod_guide = align(rod_guide, base, Alignment.BOTTOM)
    rod_guide = translate(0, 0, -rod_guide_bottom_overstand)(rod_guide)

    base = base.fuse(rod_guide)
    rod_cutter = create_cylinder(z_axis_threaded_rod_diameter / 2, BIG_THING)
    rod_cutter = align(rod_cutter, rod_guide, Alignment.CENTER)
    base = base.cut(rod_cutter)

    retval = LeaderFollowersCuttersPart(base)
    for idx, external_mount_hole_drill in enumerate(external_mount_hole_drills):
        retval.add_named_cutter(
            external_mount_hole_drill, f"external_mount_hole_drill_{idx}"
        )

    return retval


def create_carriage(guide_rod, threaded_rod, profile):
    carriage = create_filleted_box(
        z_axis_carriage_width,
        z_axis_carriage_depth,
        z_axis_carriage_height,
        z_axis_carriage_fillet_radius,
    )

    carriage = align(carriage, guide_rod, Alignment.CENTER)
    carriage = align(carriage, guide_rod, Alignment.BOTTOM)
    carriage = align(
        carriage,
        profile,
        Alignment.STACK_FRONT,
        stack_gap=z_axis_carriage_profile_clearance,
    )

    bearing = create_igus_drylin_bearing(
        cutter_clearance=0.1, cutter_extra_length=z_axis_carriage_height
    )
    bearing = align(bearing, carriage, Alignment.CENTER)
    bearing = align(bearing, guide_rod, Alignment.CENTER, axes=[0, 1])

    carriage = bearing.use_as_cutter_on(carriage)

    top_bearing = align(bearing, carriage, Alignment.TOP)

    threaded_rod_cutter = create_cylinder(
        z_axis_threaded_rod_diameter / 2 + z_axis_carriage_threaded_rod_clearance,
        z_axis_carriage_height + 10,
    )

    threaded_rod_cutter = align(threaded_rod_cutter, carriage, Alignment.CENTER)
    threaded_rod_cutter = align(
        threaded_rod_cutter, threaded_rod, Alignment.CENTER, axes=[0, 1]
    )

    carriage = carriage.cut(threaded_rod_cutter)

    retval = LeaderFollowersCuttersPart(carriage)

    retval.add_named_non_production_part(top_bearing, "top_bearing")

    bottom_bearing = align(bearing, carriage, Alignment.BOTTOM)
    retval.add_named_non_production_part(bottom_bearing, "bottom_bearing")

    return retval


def create_z_axis():
    """Create the z_axis part."""

    z_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_4040, length_mm=z_axis_profile_length
    )

    guide_rod = create_cylinder(z_axis_guide_rod_diameter / 2, z_axis_guide_rod_length)

    guide_rod = align(guide_rod, z_axis_profile, Alignment.CENTER)
    guide_rod = align(guide_rod, z_axis_profile, Alignment.BOTTOM)

    guide_rod = translate(0, -z_axis_guide_rod_profile_distance, 0)(guide_rod)

    threaded_rod = create_cylinder(
        z_axis_threaded_rod_diameter / 2, z_axis_threaded_rod_length
    )

    threaded_rod = align(threaded_rod, guide_rod, Alignment.CENTER)
    threaded_rod = align(threaded_rod, guide_rod, Alignment.BOTTOM)

    threaded_rod = translate(0, z_axis_guide_rod_threaded_rod_distance, 0)(threaded_rod)

    retval = LeaderFollowersCuttersPart(z_axis_profile)

    retval.add_named_non_production_part(guide_rod, "guide_rod")
    retval.add_named_non_production_part(threaded_rod, "threaded_rod")

    return retval


def main():

    from mege_ender_3v3ke_idex.designs.printer_frame import create_printer_frame

    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    z_axis = create_z_axis()

    parts.add(z_axis, "z_axis", flip=False)

    for name, npp in z_axis.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    carriage = create_carriage(
        z_axis.get_named_non_production_part("guide_rod"),
        z_axis.get_named_non_production_part("threaded_rod"),
        z_axis,
    )

    carriage = translate(0, 0, 100)(carriage)

    parts.add(carriage, "z_axis_carriage", flip=False)

    for name, npp in carriage.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    # printer_frame = create_printer_frame()

    # parts.add(printer_frame, "printer_frame", flip=False, skip_in_production=True)

    # # Create the part
    # part = create_z_axis()
    # parts.add(part, "z_axis", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("z_axis created successfully!")


if __name__ == "__main__":
    main()
