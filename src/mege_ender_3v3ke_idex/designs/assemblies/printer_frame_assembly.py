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
    create_corner_4040,
)
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


def create_printer_frame_assembly(
    *, frame_inner_depth, frame_inner_width, frame_profile_type
):
    """Create the printer_frame assembly part."""

    frame_profile_type_enum = ExtrusionProfileType(frame_profile_type)

    profiles = PartCollector()
    _logger.info(
        f"Creating printer frame with frame_depth={frame_inner_depth} (depth profile length) and frame_inner_width={frame_inner_width} (width profile length)"
    )
    profiles_map = {}
    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        record_length_metric(
            "extrusion_profile",
            frame_profile_type_enum.value,
            f"printer_frame_side_profile_{lr.name.lower()}",
            frame_inner_depth + 2 * frame_profile_type_enum.size_mm[1],
        )

        alu_profile = create_alu_extrusion_profile(
            frame_profile_type_enum,
            length_mm=frame_inner_depth + 2 * frame_profile_type_enum.size_mm[1],
        )
        alu_profile = rotate(90, axis=(1, 0, 0))(alu_profile)

        if lr == Alignment.RIGHT:
            alu_profile = translate(
                frame_inner_width + frame_profile_type_enum.size_mm[0], 0, 0
            )(alu_profile)

        profiles = profiles.fuse(alu_profile)
        profiles_map[f"frame_profile_{lr.name.lower()}"] = alu_profile

    profiles_size = get_bounding_box_size(profiles)
    _logger.info(f"Frame Profiles bounding box size: {point_string(profiles_size)}")

    profiles_fb = PartCollector()
    for fb in [Alignment.FRONT, Alignment.BACK]:
        record_length_metric(
            "extrusion_profile",
            frame_profile_type_enum.value,
            f"printer_frame_cross_profile_{fb.name.lower()}",
            frame_inner_width,
        )

        alu_profile = create_alu_extrusion_profile(
            frame_profile_type_enum, length_mm=frame_inner_width
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

    for lr in [Alignment.LEFT, Alignment.RIGHT]:
        for fb in [Alignment.FRONT, Alignment.BACK]:

            rotation_angle_map = {
                (Alignment.LEFT, Alignment.FRONT): 90,
                (Alignment.LEFT, Alignment.BACK): 0,
                (Alignment.RIGHT, Alignment.FRONT): 180,
                (Alignment.RIGHT, Alignment.BACK): -90,
            }

            corner = create_corner_4040()
            corner = rotate(90, axis=(1, 0, 0))(corner)
            corner = rotate(rotation_angle_map[(lr, fb)], axis=(0, 0, 1))(corner)
            corner = align(
                corner,
                profiles_map[f"frame_profile_{lr.name.lower()}"],
                Alignment.CENTER,
            )
            lr_profile = profiles_map[f"frame_profile_{lr.name.lower()}"]
            fb_profile = profiles_map[f"frame_profile_{fb.name.lower()}"]

            corner = align(corner, lr_profile, lr)
            corner = align(corner, fb_profile, fb)

            lr_profile_size = get_bounding_box_size(lr_profile)
            fb_profile_size = get_bounding_box_size(fb_profile)
            corner = translate(
                -lr.sign * lr_profile_size[0], -fb.sign * fb_profile_size[1], 0
            )(corner)

            retval.add_named_non_production_part(
                corner,
                f"corner_4040_{lr.name.lower()}_{fb.name.lower()}",
            )

    return retval


def main():
    from mege_ender_3v3ke_idex.designs.idex_parameters import (
        frame_inner_depth,
        frame_inner_width,
    )

    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    # Create the part
    frame = create_printer_frame_assembly(
        frame_inner_depth=frame_inner_depth,
        frame_inner_width=frame_inner_width,
        frame_profile_type="4040",
    )

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
