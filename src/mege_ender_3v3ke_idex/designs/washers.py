"""Washer design helpers.

Usage:
    cd <project_root> && ./run.sh path/to/washers.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/washers.py
"""

import copy
import logging
import os
from pathlib import Path

from mege_3devops.process_data.mender3.process_data_04_high_speed import (
    PROCESS_DATA_PETGCF_04_HS,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

EXTUDER_STEP_PATH = PROJECT_ROOT / "resources" / "creality_sprite.step.zip"

BIG_THING = 500

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PETGCF_04_HS)

PROCESS_DATA["process_overrides"]["sparse_infill_density"] = "100%"


def create_washer(inner_diameter, outer_diameter, thickness):

    if inner_diameter <= 0:
        raise ValueError("Inner diameter must be positive.")
    if outer_diameter <= inner_diameter:
        raise ValueError("Outer diameter must be greater than inner diameter.")

    return create_ring(outer_diameter / 2, inner_diameter / 2, thickness)


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    num_washers_per_size = 4

    inner_diameter = MScrew.from_size("M3").clearance_hole_normal + 0.25
    outer_diameter = 5.1

    for i, thickness in enumerate([0.6, 1.0, 2.0, 3.0, 4.0]):
        for j in range(num_washers_per_size):
            washer = create_washer(inner_diameter, outer_diameter, thickness)

            washer = translate(i * 10, j * 10, 0)(washer)

            parts.add(
                washer,
                f"washer_{i}_{j}",
                flip=False,
                skip_in_production=False,
                prod_rotation_angle=0,
                prod_rotation_axis=(1, 0, 0),
                color=(0.8, 0.8, thickness / 4.0),
            )

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
        prod_gap=4,
    )

    _logger.info("washers design completed.")


if __name__ == "__main__":
    main()
