"""
Spring

Usage:
    cd <project_root> && ./run.sh path/to/spring.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/spring.py
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


def create_spring_element(
    spring_thickness, spring_height, spring_width, spring_pitch, spring_turns
):
    spring_leg_length = spring_width / 2 - spring_pitch / 2

    leg_1 = create_box(spring_leg_length, spring_thickness, spring_height)
    leg_2 = create_box(spring_leg_length, spring_thickness, spring_height)
    leg_2 = translate(0, spring_pitch, 0)(leg_2)

    turnaround = create_ring(
        spring_pitch / 2 + spring_thickness / 2,
        spring_pitch / 2 - spring_thickness / 2,
        spring_height,
        angle=180,
    )
    turnaround = rotate(-90)(turnaround)

    legs_fused = leg_1.fuse(leg_2)

    turnaround = align(turnaround, legs_fused, Alignment.CENTER)
    turnaround = align(turnaround, legs_fused, Alignment.STACK_RIGHT)

    part = legs_fused.fuse(turnaround)

    return part


def create_spring(
    spring_thickness, spring_height, spring_width, spring_pitch, spring_turns
):
    """Create the spring part."""

    spring = PartCollector()

    for i in range(spring_turns):
        element = create_spring_element(
            spring_thickness, spring_height, spring_width, spring_pitch, spring_turns
        )

        if i % 2 == 1:
            # For odd turns, flip the spring element to create a zig-zag pattern
            element = rotate(
                180, center=(0, spring_pitch / 2 + spring_thickness / 2, 0)
            )(element)

        element = translate(0, i * spring_pitch, 0)(element)
        spring = spring.fuse(element)

    return spring


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_spring(
        spring_thickness=1.8,
        spring_height=4,
        spring_width=25,
        spring_pitch=8,
        spring_turns=8,
    )
    parts.add(part, "spring", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("spring created successfully!")


if __name__ == "__main__":
    main()
