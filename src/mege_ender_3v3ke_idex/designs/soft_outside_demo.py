"""Small IDEX PETG-CF core with TPU outside shell demo.

Usage:
    cd <project_root> && ./run.sh --slice --open \
        src/mege_ender_3v3ke_idex/designs/soft_outside_demo.py
"""

import logging
import os

from mege_3devops.process_data.mege_ender_3v3ke_idex import (
    SAFE_BED_DEPTH_MM,
    SAFE_BED_ORIGIN,
    SAFE_BED_WIDTH_MM,
    copy_dual_petgcf_tpu95a_06_demo_process_data,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

DEMO_GROUP_NAME = "soft_outside_demo"
PETGCF_CORE_PART_NAME = "soft_outside_demo_petgcf_core"
TPU_SHELL_PART_NAME = "soft_outside_demo_tpu_shell"

PETGCF_COLOR = (0.08, 0.08, 0.08)
TPU_COLOR = (0.0, 0.85, 0.2)

CORE_WIDTH_MM = 25.0
CORE_DEPTH_MM = 25.0
CORE_HEIGHT_MM = 25.0
SHELL_THICKNESS_MM = 5
SHELL_OUTER_WIDTH_MM = CORE_WIDTH_MM + 2 * SHELL_THICKNESS_MM
SHELL_OUTER_DEPTH_MM = CORE_DEPTH_MM + 2 * SHELL_THICKNESS_MM
SHELL_OUTER_HEIGHT_MM = CORE_HEIGHT_MM + SHELL_THICKNESS_MM
SHELL_FILLET_RADIUS_MM = 1.0

BIG_SQUARE_SIZE = 75
BIG_SQUARE_THICKNESS = 0.6
BIG_SQUARE_STRIP_WIDTH = 10

def create_soft_outside_demo_materials():
    petgcf_core = create_box(CORE_WIDTH_MM, CORE_DEPTH_MM, CORE_HEIGHT_MM)

    tpu_shell = create_filleted_box(
        SHELL_OUTER_WIDTH_MM,
        SHELL_OUTER_DEPTH_MM,
        SHELL_OUTER_HEIGHT_MM,
        fillet_radius=SHELL_FILLET_RADIUS_MM,
        no_fillets_at=[Alignment.BOTTOM],
    )
    tpu_shell = align(tpu_shell, petgcf_core, Alignment.CENTER)
    tpu_shell = align(tpu_shell, petgcf_core, Alignment.BOTTOM)

    petgcf_core_void = create_box(CORE_WIDTH_MM, CORE_DEPTH_MM, CORE_HEIGHT_MM)
    petgcf_core_void = align(petgcf_core_void, petgcf_core, Alignment.CENTER)
    petgcf_core_void = align(petgcf_core_void, petgcf_core, Alignment.BOTTOM)
    tpu_shell = tpu_shell.cut(petgcf_core_void)

    return petgcf_core, tpu_shell


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    petgcf_core, tpu_shell = create_soft_outside_demo_materials()



    big_square_strip = create_box(BIG_SQUARE_SIZE, BIG_SQUARE_SIZE, BIG_SQUARE_THICKNESS)
    hole = materialize_bounding_box(big_square_strip, x_enlargement=-BIG_SQUARE_STRIP_WIDTH, y_enlargement=-BIG_SQUARE_STRIP_WIDTH, z_enlargement=0)

    big_square_strip = big_square_strip.cut(hole)


    big_square_strip = align(big_square_strip, petgcf_core, Alignment.BOTTOM)
    big_square_strip = align(big_square_strip, petgcf_core, Alignment.LEFT)
    big_square_strip = align(big_square_strip, petgcf_core, Alignment.STACK_BACK  )



    petgcf_core = petgcf_core.fuse(big_square_strip)
    tpu_shell = tpu_shell.cut(big_square_strip)


    big_square_strip = align(big_square_strip, tpu_shell    , Alignment.RIGHT)  
    big_square_strip = align(big_square_strip, tpu_shell    , Alignment.STACK_FRONT)

    tpu_shell = tpu_shell.fuse(big_square_strip)
    petgcf_core = petgcf_core.cut(big_square_strip)




    parts.add(
        petgcf_core,
        PETGCF_CORE_PART_NAME,
        color=PETGCF_COLOR,
        flip=False,
        obj_metadata={
            "production_group": DEMO_GROUP_NAME,
            "slicer_filament_id": 1,
            "tool": "T0",
        },
    )
    parts.add(
        tpu_shell,
        TPU_SHELL_PART_NAME,
        color=TPU_COLOR,
        flip=False,
        obj_metadata={
            "production_group": DEMO_GROUP_NAME,
            "slicer_filament_id": 2,
            "tool": "T1",
        },
    )




    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=(copy_dual_petgcf_tpu95a_06_demo_process_data() if PROD else None),
        prod_gap=4,
        bed_width=SAFE_BED_WIDTH_MM,
        bed_depth=SAFE_BED_DEPTH_MM,
        prod_origin=SAFE_BED_ORIGIN,
    )

    _logger.info("soft outside demo created successfully.")


if __name__ == "__main__":
    main()
