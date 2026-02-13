"""
Creality Wheel

Usage:
    cd <project_root> && ./run.sh path/to/creality_wheel.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/creality_wheel.py
"""

# import copy
# import logging
# import math
# import os

# from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
#     PROCESS_DATA_PETGCF_04_HS,
#     PROCESS_DATA_PLACF_04_HS,
# )
# from mege_3devops.process_data.mender3.process_data_04_high_precision import (  # noqa: F401
#     PROCESS_DATA_PLACF_04_HP,
# )
# from mege_ender_3v3ke_idex.designs.idex_parameters import *
# from mege_ender_3v3ke_idex.designs.leaf_spring_clamp import create_leaf_spring
# from mege_ender_3v3ke_idex.designs.linear_guide import create_linear_guide
# from mege_ender_3v3ke_idex.designs.mcu_housing_x_axis import (
#     create_pico_w_board,
#     create_tmc_board,
# )
# from shellforgepy.simple import *

# _logger = logging.getLogger(__name__)

# # Production mode from environment variable
# PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLACF_04_HS)

# PROCESS_DATA["process_overrides"].update(
#     {
#         # "wall_loops": "1",
#         # "bottom_shell_layers": "1",
#         # "top_shell_layers": "1",
#         # "sparse_infill_density": "25%",
#         "brim_type": "no_brim",
#     }
# )

# BIG_THING = 500


import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_precision import (  # noqa: F401
    PROCESS_DATA_PLACF_04_HP,
)
from mege_3devops.process_data.mender3.process_data_04_high_speed import (  # noqa: F401
    PROCESS_DATA_PETGCF_04_HS,
    PROCESS_DATA_PLACF_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = copy.deepcopy(PROCESS_DATA_PLACF_04_HP)

PROCESS_DATA["process_overrides"].update(
    {
        #   "wall_loops": "1",
        # "bottom_shell_layers": "1",
        # "top_shell_layers": "1",
        "sparse_infill_density": "25%",
        "brim_type": "no_brim",
        "seam_position": "random",
    }
)

BIG_THING = 500


outer_diameter_608z = 22


def create_608z_bearing(diameter_increase=0, height_increase=0):
    inner_diameter = 8
    height = 7 + height_increase
    outer_ring_width = 2
    inner_ring_width = 1.8
    bearing_height = height - 0.2

    outer_diameter = outer_diameter_608z + diameter_increase
    bb_608_z = create_ring(
        outer_diameter / 2, outer_diameter / 2 - outer_ring_width, height
    )
    bb_608_z = bb_608_z.fuse(
        create_ring(inner_diameter / 2 + outer_ring_width, inner_diameter / 2, height)
    )
    bearing = bb_608_z.fuse(
        create_ring(
            outer_diameter / 2 - outer_ring_width,
            inner_diameter / 2 + inner_ring_width,
            bearing_height,
        )
    )
    bearing = translate(0, 0, (height - bearing_height) / 2)(bearing)

    bb_608_z = bb_608_z.fuse(bearing)

    return bb_608_z


def create_creality_wheel():
    """Create the creality_wheel part."""

    bearing_radial_clearance = 0.05
    bearing_axial_clearance = 0.1

    width = 10.2
    inner_width = 5
    outer_diameter = 24

    outer_radius_reduction = (width - inner_width) / 2

    roller_base = create_cylinder(outer_diameter / 2, width)

    roller_cutter_base = create_cylinder(outer_diameter / 2 + 1, width + 2)

    roller_cutter_base = align(roller_cutter_base, roller_base, Alignment.CENTER)

    for i in [Alignment.TOP, Alignment.BOTTOM]:

        roller_cutter = create_cone(
            radius1=outer_diameter / 2,
            radius2=outer_diameter / 2 - outer_radius_reduction,
            height=outer_radius_reduction,
        )
        if i == Alignment.BOTTOM:
            roller_cutter = rotate(180, axis=(0, 1, 0))(roller_cutter)

        roller_cutter = align(roller_cutter, roller_base, Alignment.CENTER)
        roller_cutter = align(
            roller_cutter,
            roller_base,
            i.stack_alignment,
            stack_gap=-outer_radius_reduction,
        )

        roller_cutter_base = roller_cutter_base.cut(roller_cutter)

    central_wheel = create_cylinder(outer_diameter / 2, inner_width)
    central_wheel = align(central_wheel, roller_base, Alignment.CENTER)
    roller_cutter_base = roller_cutter_base.cut(central_wheel)

    roller_base = roller_base.cut(roller_cutter_base)

    # bb_cutter = create_cylinder(outer_diameter_608z / 2, BIG_THING)
    # bb_cutter = align(bb_cutter, roller_base, Alignment.CENTER)
    # roller_base = roller_base.cut(bb_cutter)

    # bearing_cutter = create_608z_bearing(
    #     diameter_increase=bearing_radial_clearance,
    #     height_increase=bearing_axial_clearance,
    # )

    # bearing_cutter = align(bearing_cutter, roller_base, Alignment.CENTER)
    # roller_base = roller_base.cut(bearing_cutter)

    return roller_base


def create_v_slot_wheel_608z():

    bearing_radial_clearance = 0.5
    bearing_axial_clearance = 0.2

    width = 10.2
    inner_width = 5
    outer_diameter = 27

    outer_radius_reduction = (width - inner_width) / 2

    roller_base = create_cylinder(outer_diameter / 2, width)

    roller_cutter_base = create_cylinder(outer_diameter / 2 + 1, width + 2)

    roller_cutter_base = align(roller_cutter_base, roller_base, Alignment.CENTER)

    for i in [Alignment.TOP, Alignment.BOTTOM]:

        roller_cutter = create_cone(
            radius1=outer_diameter / 2,
            radius2=outer_diameter / 2 - outer_radius_reduction,
            height=outer_radius_reduction,
        )
        if i == Alignment.BOTTOM:
            roller_cutter = rotate(180, axis=(0, 1, 0))(roller_cutter)

        roller_cutter = align(roller_cutter, roller_base, Alignment.CENTER)
        roller_cutter = align(
            roller_cutter,
            roller_base,
            i.stack_alignment,
            stack_gap=-outer_radius_reduction,
        )

        roller_cutter_base = roller_cutter_base.cut(roller_cutter)

    central_wheel = create_cylinder(outer_diameter / 2, inner_width)
    central_wheel = align(central_wheel, roller_base, Alignment.CENTER)
    roller_cutter_base = roller_cutter_base.cut(central_wheel)

    roller_base = roller_base.cut(roller_cutter_base)

    bb_cutter = create_cylinder(outer_diameter_608z / 2, BIG_THING)
    bb_cutter = align(bb_cutter, roller_base, Alignment.CENTER)
    roller_base = roller_base.cut(bb_cutter)

    bearing_cutter = create_608z_bearing(
        diameter_increase=bearing_radial_clearance,
        height_increase=bearing_axial_clearance,
    )

    bearing_cutter = align(bearing_cutter, roller_base, Alignment.CENTER)
    roller_base = roller_base.cut(bearing_cutter)

    for i in [Alignment.TOP, Alignment.BOTTOM]:
        singularity_cutter = create_cylinder(BIG_THING, BIG_THING)
        singularity_cutter = align(singularity_cutter, roller_base, Alignment.CENTER)
        singularity_cutter = align(
            singularity_cutter, roller_base, i.stack_alignment, stack_gap=-0.1
        )
        roller_base = roller_base.cut(singularity_cutter)

    return roller_base


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # # Create the part
    # part = create_608z_bearing()
    # parts.add(part, "608z_bearing", flip=False, skip_in_production=True)

    # creality_wheel = create_creality_wheel()
    # creality_wheel = align(creality_wheel, part, Alignment.STACK_TOP, stack_gap=1)
    # parts.add(creality_wheel, "creality_wheel", flip=False, skip_in_production=True)

    # v_slot_wheel_608z = create_v_slot_wheel_608z()
    # v_slot_wheel_608z = align(
    #     v_slot_wheel_608z, creality_wheel, Alignment.STACK_TOP, stack_gap=1
    # )
    # parts.add(v_slot_wheel_608z, "v_slot_wheel_608z", flip=False)

    # bb_2 = create_608z_bearing()

    # bb_2 = align(bb_2, v_slot_wheel_608z, Alignment.CENTER)
    # bb_2 = align(bb_2, v_slot_wheel_608z, Alignment.STACK_RIGHT, stack_gap=1)

    # parts.add(bb_2, "608z_bearing_2", flip=False, skip_in_production=True)

    part = create_v_slot_wheel_608z()
    parts.add(part, "box", flip=False, skip_in_production=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("creality_wheel created successfully!")


if __name__ == "__main__":
    main()
