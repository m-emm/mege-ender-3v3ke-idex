"""
Leaf Spring Clamp

Usage:
    cd <project_root> && ./run.sh path/to/leaf_spring_clamp.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/leaf_spring_clamp.py
"""

import copy
import logging
import math
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
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


def arc_from_chord_and_sagitta(L, d):
    """
    L: chord length (distance between endpoints)
    d: sagitta (mid deflection from chord to arc, must be > 0)
    returns (R, theta_rad)
    """
    if d <= 0:
        raise ValueError("sagitta d must be > 0")
    if L <= 0:
        raise ValueError("chord length L must be > 0")

    R = ((L / 2) ** 2 + d**2) / (2 * d)
    # Numerical safety: argument to asin should be <= 1
    x = L / (2 * R)
    x = max(-1.0, min(1.0, x))
    theta = 2 * math.asin(x)
    return R, theta


def create_leaf_sping(
    spring_length, spring_thickness, spring_height, spring_mid_deflection
):

    # The angle must be such that the spring thas the given bounding box of spring_length in x direction and the spring_mid_deflection in y direction at the middle of the spring (spring_length/2)

    spring_radius, spring_angle = arc_from_chord_and_sagitta(
        spring_length, spring_mid_deflection
    )
    spring_angle = math.degrees(spring_angle)

    spring = create_ring(
        outer_radius=spring_radius,
        inner_radius=spring_radius - spring_thickness,
        height=spring_height,
        angle=spring_angle,
    )
    spring = rotate(-spring_angle / 2 + 90)(spring)
    spring = align(spring, None, Alignment.CENTER, axes=[0, 1])

    return spring


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    part = create_leaf_sping(
        spring_length=20,
        spring_thickness=1.5,
        spring_height=5,
        spring_mid_deflection=0.5,
    )
    parts.add(part, "leaf_spring", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("leaf_spring_clamp created successfully!")


if __name__ == "__main__":
    main()
