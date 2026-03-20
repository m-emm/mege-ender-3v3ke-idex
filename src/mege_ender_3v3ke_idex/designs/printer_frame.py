"""
Printer Frame

Usage:
    cd <project_root> && ./run.sh path/to/printer_frame.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/printer_frame.py
"""

import logging
import os

from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import (
    ExtrusionProfileType,
    create_alu_extrusion_profile,
)
from mege_ender_3v3ke_idex.designs.idex_parameters import *
from mege_ender_3v3ke_idex.designs.metrics_collector import record_length_metric
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


def create_printer_frame():
    """Create the printer_frame part."""

    profiles = PartCollector()
    _logger.info(
        f"Creating printer frame with frame_depth={frame_inner_depth} (depth profile length) and frame_inner_width={frame_inner_width} (width profile length)"
    )
    profiles_map = {}
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        record_length_metric(
            "extrusion_profile",
            ExtrusionProfileType.PROFILE_4040.value,
            f"printer_frame_side_profile_{lr.name.lower()}",
            frame_inner_depth + 2 * ExtrusionProfileType.PROFILE_4040.size_mm[1],
        )

        alu_profile = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_4040,
            length_mm=frame_inner_depth
            + 2 * ExtrusionProfileType.PROFILE_4040.size_mm[1],
        )
        alu_profile = rotate(90, axis=(1, 0, 0))(alu_profile)

        if lr == Alignment.RIGHT:
            alu_profile = translate(
                frame_inner_width + ExtrusionProfileType.PROFILE_4040.size_mm[0], 0, 0
            )(alu_profile)

        profiles = profiles.fuse(alu_profile)
        profiles_map[f"frame_profile_{lr.name.lower()}"] = alu_profile

    profiles_size = get_bounding_box_size(profiles)
    _logger.info(f"Frame Profiles bounding box size: {point_string(profiles_size)}")

    profiles_fb = PartCollector()
    for fb in [Alignment.FRONT, Alignment.BACK]:
        record_length_metric(
            "extrusion_profile",
            ExtrusionProfileType.PROFILE_4040.value,
            f"printer_frame_cross_profile_{fb.name.lower()}",
            frame_inner_width,
        )

        alu_profile = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_4040, length_mm=frame_inner_width
        )
        alu_profile = rotate(90, axis=(0, 1, 0))(alu_profile)
        alu_profile = align(alu_profile, profiles, Alignment.CENTER)
        alu_profile = align(alu_profile, profiles, fb)
        profiles_fb = profiles_fb.fuse(alu_profile)

        profiles_map[f"frame_profile_{fb.name.lower()}"] = alu_profile

    profiles = profiles.fuse(profiles_fb)

    retval = LeaderFollowersCuttersPart(profiles)

    for name, profile in profiles_map.items():
        retval.add_named_non_production_part(
            profile,
            name,
        )

    return retval


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    frame = create_printer_frame()

    for name, npp in frame.get_named_non_production_part_items():
        parts.add(npp, name, flip=False, skip_in_production=True)
    # parts.add(frame, "printer_frame", flip=False, skip_in_production=True)

    

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
