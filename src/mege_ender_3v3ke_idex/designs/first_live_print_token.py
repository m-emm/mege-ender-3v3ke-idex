"""Tiny first-print token for the live X-left-only IDEX bring-up.

Usage:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/first_live_print_token.py
"""

import logging
import os

from mege_3devops.process_data.mege_ender_3v3ke_idex import (
    SAFE_BED_DEPTH_MM,
    SAFE_BED_ORIGIN,
    SAFE_BED_WIDTH_MM,
    SAFE_X_MAX_MM,
    SAFE_X_MIN_MM,
    SAFE_Y_MAX_MM,
    SAFE_Y_MIN_MM,
    copy_cold_bed_pla_04_first_print_process_data,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

TOKEN_DIAMETER_MM = 20.0
TOKEN_HOLE_DIAMETER_MM = 4.0
TOKEN_THICKNESS_MM = 1.0
TOKEN_CENTER_X_MM = (SAFE_X_MIN_MM + SAFE_X_MAX_MM) / 2.0
TOKEN_CENTER_Y_MM = (SAFE_Y_MIN_MM + SAFE_Y_MAX_MM) / 2.0


def create_first_live_print_token():
    token = create_ring(
        TOKEN_DIAMETER_MM / 2.0,
        TOKEN_HOLE_DIAMETER_MM / 2.0,
        TOKEN_THICKNESS_MM,
    )
    return translate(TOKEN_CENTER_X_MM, TOKEN_CENTER_Y_MM, 0)(token)


def assert_part_inside_temporary_safe_zone(part):
    min_point, max_point = get_bounding_box(part)
    min_x, min_y, min_z = min_point
    max_x, max_y, max_z = max_point

    if not (
        SAFE_X_MIN_MM <= min_x <= max_x <= SAFE_X_MAX_MM
        and SAFE_Y_MIN_MM <= min_y <= max_y <= SAFE_Y_MAX_MM
        and 0.0 <= min_z <= max_z <= TOKEN_THICKNESS_MM
    ):
        raise ValueError(
            "First live print token is outside the temporary safe zone: "
            f"bbox=({min_point}, {max_point}), "
            f"safe_x={SAFE_X_MIN_MM}..{SAFE_X_MAX_MM}, "
            f"safe_y={SAFE_Y_MIN_MM}..{SAFE_Y_MAX_MM}"
        )


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    token = create_first_live_print_token()
    assert_part_inside_temporary_safe_zone(token)

    parts.add(
        token,
        "first_live_print_token",
        flip=False,
        skip_in_production=False,
        prod_rotation_angle=0,
        color=(0.9, 0.15, 0.08),
    )

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=copy_cold_bed_pla_04_first_print_process_data(),
        prod_gap=4,
        bed_width=SAFE_BED_WIDTH_MM,
        bed_depth=SAFE_BED_DEPTH_MM,
        prod_origin=SAFE_BED_ORIGIN,
    )

    _logger.info("first live print token design completed.")


if __name__ == "__main__":
    main()
