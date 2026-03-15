"""
Printer Feet

Usage:
    cd <project_root> && ./run.sh path/to/printer_feet.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/printer_feet.py
"""

import copy
import logging
import os

from mege_3devops.process_data.mender3.process_data_04_high_speed import (
    PROCESS_DATA_TPU_04_HS,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.screw_mount_assembly import (  # noqa: F401
    create_four_screws_mount_assembly,
    create_screw_mount_assembly,
)
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

# Optional slicer process overrides
PROCESS_DATA = copy.deepcopy(PROCESS_DATA_TPU_04_HS)
PROCESS_DATA["process_overrides"].update(
    {
        "brim_type": "no_brim",
    }
)


def create_printer_feet(frame):
    """Create the printer_feet part."""

    retval = LeaderFollowersCuttersPart(PartCollector())
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:
            foot = create_pyramid_stump(
                printer_foot_base_size,
                printer_foot_top_size,
                printer_foot_base_size,
                printer_foot_top_size,
                printer_foot_height,
            )
            foot = rotate(180, axis=(1, 0, 0))(foot)

            foot = align(foot, frame, lr)
            foot = align(foot, frame, fb)

            foot = align(
                foot,
                frame,
                Alignment.STACK_BOTTOM,
            )

            screw_mount_assembly = create_screw_mount_assembly(
                foot,
                printer_foot_mount_screw_size,
                printer_foot_screw_length,
                screw_direction=Alignment.BOTTOM,
                with_nut_cutter=False,
                cylinder_head_cutter_clearance=printer_foot_screw_cylinder_head_clearance,
                flush_with_top=True,
                top_sink=printer_foot_mount_screw_sink,
            )
            foot = screw_mount_assembly.use_as_cutter_on(foot)
            foot_assembly = LeaderFollowersCuttersPart(foot)

            foot_assembly = foot_assembly.merge_except_leader(screw_mount_assembly)

            foot_assembly = foot_assembly.prefixed_copy(
                f"printer_foot_{lr.name.lower()}_{fb.name.lower()}"
            )

            retval = retval.fuse(foot_assembly)
            retval.add_named_follower(foot, f"foot_{lr.name.lower()}_{fb.name.lower()}")

    return retval


def main():

    from mege_ender_3v3ke_idex.designs.printer_frame import (  # noqa: F401
        create_printer_frame,
    )

    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    frame = create_printer_frame()
    parts.add(frame, "printer_frame", flip=False, skip_in_production=True)

    feet = create_printer_feet(frame)

    for name, follower in feet.get_named_follower_items():
        parts.add(follower, name, flip=True, skip_in_production=False)

    for name, npp in feet.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("printer_feet created successfully!")


if __name__ == "__main__":
    main()
