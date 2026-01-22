"""
X Axis

Usage:
    cd <project_root> && ./run.sh path/to/x_axis.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/x_axis.py
"""

import logging
import os
from pathlib import Path

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite
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

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXTUDER_STEP_PATH = PROJECT_ROOT / "resources" / "creality_sprite.step.zip"


axis_profile_length = 500
rail_length = 450
axis_profile_pitch = 40
motor_y_offset = 6

z_axis_guide_distance = 256
motor_x_offset = z_axis_guide_distance / 2 - 35


def create_z_axis():
    """Create the x_axis part."""

    # # resources/ender3top_only.step

    # step_file_path = PROJECT_ROOT / "resources" / "zaxis_only.step"

    # ender_part = import_solid_from_step(step_file_path)

    # ender_part = rotate(90, axis=(1, 0, 0))(ender_part)

    guide_width = 40
    guide_thickness = 2
    guide_length = 350

    guide1 = create_box(guide_width, guide_thickness, guide_length)
    guide2 = create_box(guide_width, guide_thickness, guide_length)
    guide2 = align(
        guide2, guide1, Alignment.STACK_RIGHT, stack_gap=z_axis_guide_distance
    )

    z_guides = guide1.fuse(guide2)

    # z_guides = align(z_guides, ender_part, Alignment.CENTER)

    # ender_part = ender_part.fuse(guides)

    return z_guides


def create_mgn12h_carriage():
    """Create the MGN12H carriage part."""

    width = 27
    length = 45.4
    screw_hole_pitch = 20
    height = 10
    screw_hole_depth = 3.5
    screw_hole_diameter = 3
    h1 = 3.4

    carriage = create_box(length, width, height)

    holes = PartCollector()
    for x in [-screw_hole_pitch / 2, screw_hole_pitch / 2]:
        for y in [-width / 2 + 4, width / 2 - 4]:
            hole = create_cylinder(screw_hole_diameter / 2, height)
            hole = translate(x, y, 0)(hole)
            holes = holes.fuse(hole)

    holes = align(holes, carriage, Alignment.CENTER)
    holes = align(holes, carriage, Alignment.STACK_TOP, stack_gap=-screw_hole_depth)

    carriage = carriage.cut(holes)

    carriage = translate(0, 0, h1)(carriage)

    return carriage


def create_mgn12h_rail(length_mm: float):
    """Create the MGN12H rail part."""

    width = 12
    height = 8.5
    hole_pitch = 40
    top_hole_diameter = 8
    bottom_hole_diameter = 4.5
    top_hole_depth = 4.5

    rail = create_box(length_mm, width, height)

    num_holes = int(length_mm // hole_pitch)

    holes = PartCollector()
    for i in range(num_holes):
        x = i * hole_pitch
        # Top hole
        top_hole = create_cylinder(top_hole_diameter / 2, top_hole_depth)
        top_hole = translate(x, 0, 0)(top_hole)
        top_hole = align(top_hole, rail, Alignment.TOP)

        holes = holes.fuse(top_hole)
        # Bottom hole
        bottom_hole = create_cylinder(bottom_hole_diameter / 2, height)
        bottom_hole = translate(x, 0, 0)(bottom_hole)
        bottom_hole = align(bottom_hole, rail, Alignment.BOTTOM)
        holes = holes.fuse(bottom_hole)

    holes = align(holes, rail, Alignment.CENTER, axes=[0, 1])

    rail = rail.cut(holes)

    return rail


def create_x_axis():
    """Create the x_axis part."""

    # resources/ender3top_only.step

    lower_axis_profile = create_alu_extrusion_profile(
        ExtrusionProfileType.PROFILE_2020, length_mm=axis_profile_length
    )

    lower_axis_profile = rotate(90, axis=(0, 1, 0))(lower_axis_profile)

    top_axis_profile = translate(0, 0, axis_profile_pitch)(lower_axis_profile)

    axis = lower_axis_profile.fuse(top_axis_profile)

    rail = create_mgn12h_rail(length_mm=rail_length)

    carriages = PartCollector()
    for i in [-1, 1]:
        carriage = create_mgn12h_carriage()
        carriage = align(carriage, rail, Alignment.CENTER, axes=[0, 1])
        carriage = translate(i * 50, 0, 0)(carriage)
        carriages = carriages.fuse(carriage)

    rail = rail.fuse(carriages)

    rail = align(rail, lower_axis_profile, Alignment.CENTER, axes=[0, 1])
    rail = align(rail, lower_axis_profile, Alignment.STACK_TOP)

    axis = axis.fuse(rail)

    motors = PartCollector()
    for i in [-1, 1]:
        motor = create_nema_composite(axle_length=10)
        if i == -1:
            motor = rotate(180, axis=(0, 1, 0))(motor)

        profile_to_align = lower_axis_profile if i == -1 else top_axis_profile

        motor = align(motor, profile_to_align, Alignment.CENTER)
        motor = align(motor, profile_to_align, Alignment.STACK_BACK)
        motor = align(
            motor,
            profile_to_align,
            Alignment.STACK_TOP if i == -1 else Alignment.STACK_BOTTOM,
        )

        motor = translate(i * motor_x_offset, motor_y_offset, 0)(motor)
        motors = motors.fuse(motor.leader)
        motors = motors.fuse(motor.get_follower_part_by_name("axle"))

    axis = axis.fuse(motors)

    return axis


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    z_axis = create_z_axis()
    parts.add(z_axis, "z_axis", flip=False, skip_in_production=True)

    x_axis = create_x_axis()

    x_axis = align(x_axis, z_axis, Alignment.CENTER)
    x_axis = align(x_axis, z_axis, Alignment.STACK_BACK, stack_gap=-28)

    parts.add(x_axis, "x_axis", flip=False, skip_in_production=True)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("x_axis created successfully!")


if __name__ == "__main__":
    main()
