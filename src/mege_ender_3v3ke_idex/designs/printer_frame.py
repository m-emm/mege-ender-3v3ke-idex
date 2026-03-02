"""
Printer Frame

Usage:
    cd <project_root> && ./run.sh path/to/printer_frame.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/printer_frame.py
"""

import logging
import os

from shellforgepy.simple import *
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)

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


def create_printer_frame():
    """Create the printer_frame part."""

    profiles = PartCollector()
    for lr in [Alignment.LEFT, Alignment.RIGHT]:

        alu_profile = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_4040, length_mm=frame_depth
        )
        alu_profile = rotate(90, axis=(1, 0, 0))(alu_profile)

        if lr == Alignment.RIGHT:
            alu_profile = translate(
                frame_width + ExtrusionProfileType.PROFILE_4040.size_mm[0], 0, 0
            )(alu_profile)

        profiles = profiles.fuse(alu_profile)

    profiles_fb = PartCollector()
    for fb in [Alignment.FRONT, Alignment.BACK]:

        alu_profile = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_4040, length_mm=frame_width
        )
        alu_profile = rotate(90, axis=(0, 1, 0))(alu_profile)
        alu_profile = align(alu_profile, profiles, Alignment.CENTER)
        alu_profile = align(alu_profile, profiles, fb)
        profiles_fb = profiles_fb.fuse(alu_profile)

    profiles = profiles.fuse(profiles_fb)

    print_bed = create_box(print_bed_width, print_bed_depth, print_bed_thickness)
    print_bed = align(print_bed, profiles, Alignment.CENTER)
    print_bed = align(print_bed, profiles, Alignment.STACK_TOP, stack_gap=20)

    retval = LeaderFollowersCuttersPart(profiles)

    retval.add_named_non_production_part(print_bed, "print_bed")

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    frame = create_printer_frame()
    parts.add(frame, "printer_frame", flip=False, skip_in_production=True)

    for name, npp in frame.get_named_non_production_part_items():
        _logger.info(f"Adding non-production part: {name}")
        parts.add(npp, name, flip=False, skip_in_production=True)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("printer_frame created successfully!")


if __name__ == "__main__":
    main()
