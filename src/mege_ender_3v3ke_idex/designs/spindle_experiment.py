"""
Spindle Experiment

Usage:
    cd <project_root> && ./run.sh path/to/spindle_experiment.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/spindle_experiment.py
"""

import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (
    PROCESS_DATA_PETGCF_04_HS,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# Optional slicer process overrides
PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)
BIG_THING = 500

z_profile_width = 40
z_pillar_front_thickness = 3

z_threaded_leadscrew_to_profile_front = 40

z_profile_height = 100

connector_wall_height = 20
connector_wall_thickness = 4

bearing_608z_diameter = 22
bearing_608z_thickness = 7
bearing_608z_inner_diameter = 8


def create_t8_spindle_nut(length, outer_diameter):
    """
    Create a simple cylindrical spindle nut for a T8 lead screw.

    T8 4-start trapezoidal lead screw specifications:
    - Thread type: Metric trapezoidal (ISO Tr8x8)
    - Flank angle: 30° trapezoidal
    - Major (outer) diameter: 8mm
    - Pitch (distance between adjacent threads): 2mm
    - Number of starts: 4-start
    - Lead (travel per revolution): 8mm (4 starts × 2mm pitch)

    Args:
        length: Length/height of the nut in mm
        outer_diameter: Outer diameter of the nut body in mm

    Returns:
        A cylindrical nut with internal T8 4-start threads
    """
    # T8 4-start lead screw specifications
    pitch = 2.0  # 2mm pitch (distance between adjacent threads)
    starts = 4  # 4-start thread (lead = 4 × 2mm = 8mm)
    thread_major_radius = 8.0 / 2  # 4.0mm (outer diameter of screw)
    thread_minor_radius = 6.5 / 2  # 3.25mm (inner diameter at thread root)
    thread_outer_thickness = 0.665  # Thread depth for trapezoidal profile

    thread_radial_clearance = 0.1
    thread_outer_radial_correction = 1.1
    thread_axial_clearance = 0.2

    # Calculate number of turns based on length and pitch
    num_turns = length / pitch
    if num_turns < 1:
        num_turns = 1  # Minimum one turn

    # Create outer cylindrical body
    nut_body = create_cylinder(outer_diameter / 2, length)

    # Create thread cutter (for internal threads)
    # This creates the negative space that will be cut from the nut body
    inner_radius = (
        thread_minor_radius
        + thread_radial_clearance
        + thread_outer_radial_correction * 0.5
    )
    outer_radius = (
        thread_major_radius + thread_radial_clearance + thread_outer_radial_correction
    )

    nut = nut_body

    if False:
        thread_cutter = create_screw_thread(
            pitch=pitch,
            inner_radius=inner_radius,
            outer_radius=outer_radius,
            outer_thickness=thread_outer_thickness + thread_axial_clearance,
            inner_thickness=thread_outer_thickness * 2.2 + thread_axial_clearance,
            num_turns=num_turns,
            starts=starts,  # 4-start thread
            resolution=48,  # High resolution for smooth threads
            with_core=False,  # Include solid core for proper cutting
        )

        core_cutter = create_cylinder(
            inner_radius + (outer_radius - inner_radius) * 0.05, length + 2
        )
        core_cutter = align(core_cutter, nut_body, Alignment.CENTER)
        nut = nut_body.cut(core_cutter)
        nut = nut.cut(thread_cutter)

    flanges = PartCollector()
    screw_hole_drills = PartCollector()
    for a in [Alignment.FRONT, Alignment.BACK]:
        flange = create_box(outer_diameter / 2, 10, length)

        flange = align(flange, nut, Alignment.CENTER)
        flange = align(flange, nut, a.stack_alignment, stack_gap=-outer_diameter / 6)
        flanges = flanges.fuse(flange)
        screw_hole_drill = create_cylinder(
            MScrew.from_size("M3").clearance_hole_normal / 2, 100
        )
        screw_hole_drill = rotate(90, axis=(0, 1, 0))(screw_hole_drill)
        screw_hole_drill = align(screw_hole_drill, flange, Alignment.CENTER)
        screw_hole_drill = align(
            screw_hole_drill, flange, a.stack_alignment, stack_gap=-6
        )
        screw_hole_drills = screw_hole_drills.fuse(screw_hole_drill)

    nut = nut.fuse(flanges)
    nut = nut.cut(screw_hole_drills)

    return nut


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    spindle_nut = create_t8_spindle_nut(length=6, outer_diameter=16)

    z_profile = create_box(
        z_profile_width,
        z_pillar_front_thickness,
        z_profile_height,
    )

    rod = create_cylinder(8 / 2, z_profile_height)

    rod = align(rod, z_profile, Alignment.CENTER)
    rod = translate(
        0, z_threaded_leadscrew_to_profile_front - z_pillar_front_thickness / 2, 0
    )(rod)

    z_axis_parts = z_profile.fuse(rod)

    parts.add(
        z_axis_parts,
        "z_axis_parts",
        flip=False,
        skip_in_production=True,
        color=(1, 0.4, 0.4),
    )

    spindle_nut = align(spindle_nut, rod, Alignment.CENTER)

    # carriage_base = create_box(60, 60, 4)

    # carriage_base = align(carriage_base, z_profile, Alignment.CENTER)

    connectors = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        connector = create_box(18, 15, 2)

        connector = align(connector, spindle_nut, Alignment.CENTER)
        connector = align(connector, spindle_nut, Alignment.BOTTOM)
        connector = align(connector, spindle_nut, lr.stack_alignment, stack_gap=-2)

        connectors = connectors.fuse(connector)

        connector_wall = create_box(connector_wall_thickness, 55, connector_wall_height)

        connector_wall = align(connector_wall, connector, Alignment.CENTER)
        connector_wall = align(connector_wall, connector, Alignment.BACK)
        connector_wall = align(connector_wall, connector, Alignment.BOTTOM)
        connector_wall = align(
            connector_wall, connector, lr.stack_alignment, stack_gap=-2
        )
        connectors = connectors.fuse(connector_wall)

    spindle_nut = spindle_nut.fuse(connectors)
    spindle_nut_size = get_bounding_box_size(spindle_nut)

    front_axle = create_cylinder(
        bearing_608z_inner_diameter / 2, spindle_nut_size[0], direction=(1, 0, 0)
    )

    front_axle = align(front_axle, spindle_nut, Alignment.CENTER)
    front_axle = align(front_axle, spindle_nut, Alignment.FRONT)
    front_axle = align(front_axle, spindle_nut, Alignment.BOTTOM)
    front_axle_m4_drill = create_cylinder(
        MScrew.from_size("M4").clearance_hole_normal / 2, BIG_THING, direction=(1, 0, 0)
    )
    front_axle_m4_drill = align(front_axle_m4_drill, front_axle, Alignment.CENTER)

    spindle_nut = spindle_nut.fuse(front_axle)
    spindle_nut = spindle_nut.cut(front_axle_m4_drill)

    parts.add(
        spindle_nut,
        "spindle_nut",
        flip=False,
        skip_in_production=False,
        color=(0.4, 0.4, 1),
    )

    # part = create_cylinder(15, 10)
    # part = rotate(25, axis=(0, 1, 0))(part)
    # part = rotate(30)(part)

    # n1, n2 = cut_in_two(part, cut_normal=(1, 0, 0))
    # n1 = translate(30, 0, 0)(n1)
    # n2 = translate(-30, 0, 0)(n2)
    # parts.add(n1, "spindle_nut_part1", flip=False, skip_in_production=False)
    # parts.add(n2, "spindle_nut_part2", flip=False, skip_in_production=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("spindle_experiment created successfully!")


if __name__ == "__main__":
    main()
