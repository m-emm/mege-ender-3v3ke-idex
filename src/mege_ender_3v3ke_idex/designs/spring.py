"""
Spring

Usage:
    cd <project_root> && ./run.sh path/to/spring.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/spring.py
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


def _calculate_spring_layout(spring_total_length, spring_pitch, spring_thickness):
    """Derive spring turns and symmetric connector lengths from a total length."""

    if spring_total_length <= 0:
        raise ValueError("spring_total_length must be greater than 0")
    if spring_pitch <= 0:
        raise ValueError("spring_pitch must be greater than 0")
    if spring_thickness <= 0:
        raise ValueError("spring_thickness must be greater than 0")

    min_connector_length = spring_pitch / 2
    max_turns = math.floor(
        (spring_total_length - spring_thickness - 2 * min_connector_length)
        / spring_pitch
    )

    if max_turns < 2:
        min_total_length = spring_thickness + spring_pitch + 2 * min_connector_length
        raise ValueError(
            f"Cannot create spring for total length {spring_total_length}. "
            f"Need at least {min_total_length} for two turns and two connectors "
            f"with each connector >= {min_connector_length}."
        )

    spring_turns = max_turns
    spring_body_length = spring_turns * spring_pitch + spring_thickness
    connector_length = (spring_total_length - spring_body_length) / 2

    if connector_length + 1e-9 < min_connector_length:
        raise ValueError(
            f"Cannot create spring for total length {spring_total_length}. "
            f"Connector lengths would be {connector_length}, but each connector must be "
            f">= {min_connector_length}."
        )

    return spring_turns, connector_length


def create_spring_element(spring_thickness, spring_height, spring_width, spring_pitch):
    spring_leg_length = spring_width / 2 - spring_pitch / 2

    if spring_leg_length <= 0:
        raise ValueError(
            f"spring_width ({spring_width}) must be greater than spring_pitch ({spring_pitch})"
        )

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


def _create_spring_body(
    spring_thickness, spring_height, spring_width, spring_pitch, spring_turns
):
    if spring_turns < 1:
        raise ValueError("spring_turns must be at least 1")

    spring = PartCollector()

    for i in range(spring_turns):
        element = create_spring_element(
            spring_thickness,
            spring_height,
            spring_width,
            spring_pitch,
        )

        if i % 2 == 1:
            # For odd turns, flip the spring element to create a zig-zag pattern.
            element = rotate(
                180, center=(0, spring_pitch / 2 + spring_thickness / 2, 0)
            )(element)

        element = translate(0, i * spring_pitch, 0)(element)
        spring = spring.fuse(element)

    return spring


def _create_spring_connector(spring_thickness, spring_height, connector_length):
    return create_box(
        spring_thickness,
        connector_length + spring_thickness,
        spring_height,
    )


def create_spring(
    spring_thickness,
    spring_height,
    spring_width,
    spring_pitch,
    spring_total_length,
):
    """Create a complete spring with front and back connectors for a total length."""

    spring_turns, connector_length = _calculate_spring_layout(
        spring_total_length=spring_total_length,
        spring_pitch=spring_pitch,
        spring_thickness=spring_thickness,
    )

    spring = _create_spring_body(
        spring_thickness=spring_thickness,
        spring_height=spring_height,
        spring_width=spring_width,
        spring_pitch=spring_pitch,
        spring_turns=spring_turns,
    )

    spring_connector_front = _create_spring_connector(
        spring_thickness=spring_thickness,
        spring_height=spring_height,
        connector_length=connector_length,
    )
    spring_connector_front = align(spring_connector_front, spring, Alignment.CENTER)
    spring_connector_front = align(
        spring_connector_front,
        spring,
        Alignment.STACK_FRONT,
        stack_gap=-spring_thickness,
    )
    spring = spring.fuse(spring_connector_front)

    spring_connector_back = _create_spring_connector(
        spring_thickness=spring_thickness,
        spring_height=spring_height,
        connector_length=connector_length,
    )
    spring_connector_back = align(spring_connector_back, spring, Alignment.CENTER)
    spring_connector_back = align(
        spring_connector_back,
        spring,
        Alignment.STACK_BACK,
        stack_gap=-spring_thickness,
    )
    spring = spring.fuse(spring_connector_back)

    return spring


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # 8 turns with pitch=8 and connector length=4 on each side.
    spring_total_length = 73.8

    part = create_spring(
        spring_thickness=1.8,
        spring_height=4,
        spring_width=25,
        spring_pitch=8,
        spring_total_length=spring_total_length,
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
