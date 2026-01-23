"""
Gt2Belt

Usage:
    cd <project_root> && ./run.sh path/to/gt2belt.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/gt2belt.py
"""

import logging
import math
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
gt2_pitch = 2.0
gt2_thickness = 1.38
gt2_teeth_thickness = 0.75
gt2_width = 6.0
gt2_tooth_radius = 0.555
gt2_tooth_bend_offset = 0.4
gt2_tooth_side_radius = 1.0
gt2_tooth_inter_radius = 0.15


def creae_gt2_tooth():

    tooth_half = create_cylinder(gt2_tooth_radius, gt2_width, angle=180)
    tooth_half = rotate(90)(tooth_half)
    tooth_half = translate(0, gt2_tooth_radius, 0)(tooth_half)

    belt = create_box(gt2_pitch / 2, gt2_thickness - gt2_teeth_thickness, gt2_width)
    belt = translate(-gt2_pitch / 2, 0, 0)(belt)
    belt = translate(0, gt2_teeth_thickness, 0)(belt)

    retval = belt.fuse(tooth_half)
    mirrored = mirror((1, 0, 0))(retval)
    mirrored = align(mirrored, retval, Alignment.STACK_LEFT)
    retval = retval.fuse(mirrored)

    return retval


def create_gt2_pulley(
    num_teeth=20, belt_width=6, top_disk_thickness=1.5, bottom_disk_thickness=5
):
    """Create a simple GT2 pulley model."""
    outer_diameter = (
        (num_teeth * gt2_pitch) / math.pi - gt2_thickness + gt2_teeth_thickness
    )
    outer_disk_diameter = (num_teeth * gt2_pitch) / math.pi

    pulley = create_cylinder(outer_diameter / 2, belt_width)

    tooth_cutter = create_cylinder(gt2_teeth_thickness, belt_width)
    tooth_cutter = translate(outer_diameter / 2, 0, 0)(tooth_cutter)
    for i in range(num_teeth):
        rotated_cutter = rotate(i * (360 / num_teeth))(tooth_cutter)
        pulley = pulley.cut(rotated_cutter)

    top_disk = create_cylinder(outer_disk_diameter / 2, top_disk_thickness)

    top_disk = align(top_disk, pulley, Alignment.STACK_TOP)
    pulley = pulley.fuse(top_disk)

    bottom_disk = create_cylinder(outer_disk_diameter / 2, bottom_disk_thickness)
    bottom_disk = align(bottom_disk, pulley, Alignment.STACK_BOTTOM)
    pulley = pulley.fuse(bottom_disk)

    return pulley


def create_gt2_idler(
    num_teeth=20, belt_width=6, shaft_diameter=3, end_disk_thickness=0.8
):
    """Create a simple GT2 pulley model."""
    core_diameter = (num_teeth * gt2_pitch) / math.pi - gt2_thickness
    outer_disk_diameter = (num_teeth * gt2_pitch) / math.pi

    center = create_cylinder(core_diameter / 2, belt_width)

    top_disk = create_cylinder(outer_disk_diameter / 2, end_disk_thickness)
    top_disk = align(top_disk, center, Alignment.STACK_TOP)

    retval = center.fuse(top_disk)

    bottom_disk = create_cylinder(outer_disk_diameter / 2, end_disk_thickness)
    bottom_disk = align(bottom_disk, center, Alignment.STACK_BOTTOM)
    retval = retval.fuse(bottom_disk)
    shaft = create_cylinder(shaft_diameter / 2, BIG_THING)

    shaft = align(shaft, retval, Alignment.CENTER)
    retval = retval.cut(shaft)

    return retval


def create_gt2belt(num_teeth=100):
    """Create the gt2belt part."""

    retval = PartCollector()

    for i in range(num_teeth):
        tooth = creae_gt2_tooth()
        tooth = translate(i * gt2_pitch, 0, 0)(tooth)
        retval = retval.fuse(tooth)

    return retval


def create_gt2belt_loop(num_teeth=20, angle=180):
    """Create the gt2belt part."""

    outer_belt_length = gt2_pitch * num_teeth
    belt_outer_radius = outer_belt_length / (2 * math.pi) * 360 / angle
    belt_loop = create_ring(
        outer_radius=belt_outer_radius,
        inner_radius=belt_outer_radius - gt2_thickness,
        angle=angle,
    )

    tooth_cutter = create_cylinder(
        gt2_tooth_radius + gt2_tooth_bend_offset, gt2_width, angle=angle
    )


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # part = create_gt2belt(num_teeth=100)
    # parts.add(part, "belt", flip=False)

    pulley = create_gt2_pulley(num_teeth=20, belt_width=gt2_width)

    pulley = translate(0, 50, 0)(pulley)
    parts.add(pulley, "pulley_20t", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("gt2belt created successfully!")


if __name__ == "__main__":
    main()
