"""
Elastic Sheet

Usage:
    cd <project_root> && ./run.sh path/to/elastic_sheet.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/elastic_sheet.py
"""

import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLACF_04_HS)

PROCESS_DATA["process_overrides"].update(
    {
        "wall_loops": "1",
        "bottom_shell_layers": "1",
        "top_shell_layers": "1",
        "sparse_infill_density": "25%",
        "brim_type": "no_brim",
    }
)


def create_elastic_sheet(
    length, witdh, thickness, hole_x_pitch, hole_y_pitch, x_factor, y_factor
):

    sheet = create_box(length, witdh, thickness)

    num_x_holes = int(length / hole_x_pitch) + 1
    num_y_holes = int(witdh / hole_y_pitch)

    hole_y_size = hole_y_pitch * y_factor
    hole_x_size = hole_x_pitch * x_factor
    hole_round_radius = min(hole_x_size / 2, hole_y_size / 2)

    holes = PartCollector()
    for i in range(num_x_holes):
        for j in range(num_y_holes):
            _logger.info(f"Creating hole at row {i}, column {j}")
            x_offset = 0
            if j % 2 == 0:
                x_offset = hole_x_pitch / 2

            hole_x_pos = i * hole_x_pitch + hole_x_pitch / 2 + x_offset
            hole_y_pos = j * hole_y_pitch + hole_y_pitch / 2

            hole = create_rounded_slab(
                hole_x_size,
                hole_y_size,
                thickness + 1,
                round_radius=hole_round_radius,
            )

            hole = align(hole, sheet, Alignment.CENTER)
            hole = translate(hole_x_pos, hole_y_pos, 0)(hole)
            holes = holes.fuse(hole)

    holes = align(holes, sheet, Alignment.CENTER)

    sheet = sheet.cut(holes)

    return sheet


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part

    thickness = 2
    hole_x_pitch = 14
    hole_y_pitch = 2.5
    x_factor = 0.85
    y_factor = 0.7

    holder_fillet_radius = 3
    holder_stack_gap = 0.5

    part = create_elastic_sheet(
        length=hole_x_pitch * 3,
        witdh=hole_y_pitch * 10,
        thickness=thickness,
        hole_x_pitch=hole_x_pitch,
        hole_y_pitch=hole_y_pitch,
        x_factor=x_factor,
        y_factor=y_factor,
    )

    for fb in [Alignment.STACK_FRONT, Alignment.STACK_BACK]:
        holder = create_filleted_box(
            15,
            10,
            thickness,
            fillet_radius=holder_fillet_radius,
            no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
        )
        holder = align(holder, part, Alignment.CENTER)
        holder = align(holder, part, fb, stack_gap=-holder_stack_gap)
        part = part.fuse(holder)

    parts.add(part, "elastic_sheet", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("elastic_sheet created successfully!")


if __name__ == "__main__":
    main()
