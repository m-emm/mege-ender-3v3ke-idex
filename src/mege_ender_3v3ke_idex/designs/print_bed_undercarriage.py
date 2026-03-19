"""
Print Bed Undercarriage

Usage:
    cd <project_root> && ./run.sh path/to/print_bed_undercarriage.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/print_bed_undercarriage.py
"""

import logging
import math
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

print_bed_undercarriage_profiles_height = 30
print_bed_undercarriage_profiles_width = 12
print_bed_undercarriage_profiles_wall = 1.8

print_bed_undercarriage_central_annulus_diameter = 90

print_bed_undercarriage_mount_tower_annulus_diameter = 110


print_bed_undercarriage_bed_mount_annulus_diameter = 60

print_bed_mount_tower_size = 20
print_bed_mount_tower_height = print_bed_undercarriage_profiles_height


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


def create_hollow_profile(
    profile_length, prifile_depth, profile_height, wall_thickness
):
    outer = create_box(profile_length, prifile_depth, profile_height)
    inner = create_box(
        profile_length - 2 * wall_thickness,
        prifile_depth - 2 * wall_thickness,
        profile_height - 2 * wall_thickness,
    )
    inner = align(inner, outer, Alignment.CENTER)
    return outer.cut(inner)


def create_hollow_profile_ring(
    outer_diameter, profile_depth, profile_height, wall_thickness, angle=None
):

    ring = create_ring(
        outer_diameter / 2,
        outer_diameter / 2 - profile_depth,
        profile_height,
        angle=angle,
    )

    cutter_angle = None

    if angle is not None:
        average_radius = outer_diameter / 2 - profile_depth / 2
        wall_thickness_angle = math.degrees(wall_thickness / average_radius)
        wall_angle = 2 * wall_thickness_angle
        cutter_angle = angle - wall_angle

    inner_cutter = create_ring(
        (outer_diameter - 2 * wall_thickness) / 2,
        (outer_diameter + 2 * wall_thickness) / 2 - profile_depth,
        profile_height - 2 * wall_thickness,
        angle=cutter_angle,
    )
    if angle is not None:
        inner_cutter = rotate(wall_angle / 2)(inner_cutter)

    inner_cutter = align(inner_cutter, ring, Alignment.CENTER, axes=[2])

    return ring.cut(inner_cutter)


def create_print_bed_undercarriage(print_bed):
    """Create the print_bed_undercarriage part."""

    central_annulus = create_hollow_profile_ring(
        outer_diameter=print_bed_undercarriage_central_annulus_diameter,
        profile_depth=print_bed_undercarriage_profiles_width,
        profile_height=print_bed_undercarriage_profiles_height,
        wall_thickness=print_bed_undercarriage_profiles_wall,
    )

    central_annulus = align(central_annulus, print_bed, Alignment.CENTER)

    annulus_z_aligner = align_translation(
        central_annulus,
        print_bed.get_non_production_part_by_name("damper_left_front"),
        Alignment.STACK_BOTTOM,
    )

    central_annulus = annulus_z_aligner(central_annulus)
    mount_square_placeholder = create_box(
        print_bed_mount_hole_pitch, print_bed_mount_hole_pitch, 1
    )

    mount_square_placeholder = align(
        mount_square_placeholder, central_annulus, Alignment.CENTER
    )

    outer_frame = PartCollector()

    for alignment, angle in (
        (Alignment.EDGE_FRONT, 0),
        (Alignment.EDGE_RIGHT, 90),
        (Alignment.EDGE_BACK, 180),
        (Alignment.EDGE_LEFT, 270),
    ):
        profile = create_hollow_profile(
            profile_length=print_bed_mount_hole_pitch - print_bed_mount_tower_size,
            prifile_depth=print_bed_undercarriage_profiles_width,
            profile_height=print_bed_undercarriage_profiles_height,
            wall_thickness=print_bed_undercarriage_profiles_wall,
        )

        profile = rotate(angle)(profile)
        profile = align(profile, central_annulus, Alignment.CENTER)
        profile = align(profile, mount_square_placeholder, alignment)
        outer_frame = outer_frame.fuse(profile)

    undercarriage = central_annulus.fuse(outer_frame)

    half_diagonal = math.sqrt(2) * (print_bed_mount_hole_pitch) / 2

    diagonal_profile_length = (
        half_diagonal
        - print_bed_undercarriage_central_annulus_diameter / 2
        - print_bed_undercarriage_mount_tower_annulus_diameter / 2
        + 4 * print_bed_undercarriage_profiles_wall
    )

    diagonal_profiles = PartCollector()
    for i in range(4):
        angle = 45 + i * 90

        profile = create_hollow_profile(
            profile_length=diagonal_profile_length,
            prifile_depth=print_bed_undercarriage_profiles_width,
            profile_height=print_bed_undercarriage_profiles_height,
            wall_thickness=print_bed_undercarriage_profiles_wall,
        )

        profile = translate(
            print_bed_undercarriage_central_annulus_diameter / 2
            - print_bed_undercarriage_profiles_wall,
            -print_bed_undercarriage_profiles_width / 2,
            0,
        )(profile)
        profile = rotate(angle)(profile)
        diagonal_profiles = diagonal_profiles.fuse(profile)

    diagonal_profiles = align(diagonal_profiles, central_annulus, Alignment.CENTER)

    undercarriage = undercarriage.fuse(diagonal_profiles)

    all_mount_annulus = PartCollector()
    for i in range(4):

        angle = i * 90

        mount_annulus = create_hollow_profile_ring(
            outer_diameter=print_bed_undercarriage_mount_tower_annulus_diameter,
            profile_depth=print_bed_undercarriage_profiles_width,
            profile_height=print_bed_undercarriage_profiles_height,
            wall_thickness=print_bed_undercarriage_profiles_wall,
            angle=90,
        )
        mount_annulus = rotate(180)(mount_annulus)

        mount_annulus = translate(
            print_bed_mount_hole_pitch / 2, print_bed_mount_hole_pitch / 2, 0
        )(mount_annulus)

        mount_annulus = rotate(angle)(mount_annulus)

        all_mount_annulus = all_mount_annulus.fuse(mount_annulus)

    all_mount_annulus = align(all_mount_annulus, central_annulus, Alignment.CENTER)
    undercarriage = undercarriage.fuse(all_mount_annulus)

    straight_profile_length = (
        print_bed_mount_hole_pitch / 2
        - print_bed_undercarriage_central_annulus_diameter / 2
        + 2 * print_bed_undercarriage_profiles_wall
    )

    straight_profiles = PartCollector()
    for i in range(4):
        angle = i * 90
        straight_profile = create_hollow_profile(
            profile_length=straight_profile_length,
            prifile_depth=print_bed_undercarriage_profiles_width,
            profile_height=print_bed_undercarriage_profiles_height,
            wall_thickness=print_bed_undercarriage_profiles_wall,
        )

        straight_profile = translate(
            print_bed_undercarriage_central_annulus_diameter / 2
            - print_bed_undercarriage_profiles_wall,
            -print_bed_undercarriage_profiles_width / 2,
            0,
        )(straight_profile)

        straight_profile = rotate(angle)(straight_profile)
        straight_profiles = straight_profiles.fuse(straight_profile)

    straight_profiles = align(straight_profiles, central_annulus, Alignment.CENTER)
    undercarriage = undercarriage.fuse(straight_profiles)

    retval = LeaderFollowersCuttersPart(undercarriage)

    for name, npp in print_bed.get_named_non_production_part_items():
        if not name.startswith("damper_"):
            continue

        mount_tower = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_2020, length_mm=print_bed_mount_tower_height
        )
        mount_tower = align(mount_tower, npp, Alignment.CENTER)
        mount_tower = align(mount_tower, npp, Alignment.STACK_BOTTOM)

        retval.add_named_non_production_part(
            mount_tower, f"mount_tower_{name.replace('damper','')}"
        )

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    print_bed = create_print_bed()

    # Create the part
    undercarriage = create_print_bed_undercarriage(print_bed)

    cut_normal = [1, 1, 0]
    # print_bed, _ = cut_in_two(print_bed, cut_normal=cut_normal)
    # undercarriage_cut, _ = cut_in_two(undercarriage, cut_normal=cut_normal)

    # parts.add(print_bed, "print_bed", flip=False, skip_in_production=True)
    # npps_fused = PartCollector()
    for name, npp in print_bed.get_named_non_production_part_items():

        if "foil" in name:
            continue

        parts.add(npp, name, flip=False, skip_in_production=True)
        # npps_fused = npps_fused.fuse(npp)

    # npps_fused, _ = cut_in_two(npps_fused, cut_normal=cut_normal)
    # parts.add(npps_fused, "print_bed_npps", flip=False, skip_in_production=True)

    # parts.add(undercarriage_cut, "print_bed_undercarriage", flip=False)

    parts.add(undercarriage, "print_bed_undercarriage", flip=False)

    # uc_parts_fused = PartCollector()
    # for name, npp in undercarriage.get_named_non_production_part_items():
    #     uc_parts_fused = uc_parts_fused.fuse(npp)

    # uc_parts_fused, _ = cut_in_two(uc_parts_fused, cut_normal=cut_normal)
    # parts.add(uc_parts_fused, "print_bed_undercarriage_npps", flip=False)

    for name, npp in undercarriage.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    dovetail = create_dovetail_tongue_and_groove(
        dovetail_width=10.0,
        length=30.0,
        box_size_x=18.0,
        box_size_y=6.0,
        taper_per_side=1.5,
        dovetail_clearance=0.2,
        parts_clearance=0.5,
        groove_box_size_y=18,
        front_wall_clearance=0.2,
    )

    # dovetail = translate(0, 0, 0)(dovetail)

    parts.add(dovetail, "dovetail_leader", flip=False)
    for name, follower in dovetail.get_named_follower_items():
        parts.add(follower, name, flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        export_stl=False,
        export_individual_parts=False,
    )

    _logger.info("print_bed_undercarriage created successfully!")


if __name__ == "__main__":
    main()
