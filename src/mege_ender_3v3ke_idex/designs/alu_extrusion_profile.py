"""
Alu Extrusion Profile

Usage:
    cd <project_root> && ./run.sh path/to/alu_extrusion_profile.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/alu_extrusion_profile.py
"""

import logging
import os
from enum import Enum

from poemai_utils.enum_utils import add_enum_attrs
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


class ExtrusionProfileType(Enum):
    PROFILE_2020 = "2020"
    PROFILE_4040 = "4040"


add_enum_attrs(
    {
        # ---------------------------------------------------------------------
        # 20-series: 2020
        # ---------------------------------------------------------------------
        ExtrusionProfileType.PROFILE_2020: {
            "family": "20-series",
            "size_mm": (20.0, 20.0),
            "grid_pitch_mm": 20.0,
            "slots_per_side": 1,
            "slot_centers_from_profile_center_mm": [0.0],  # along each face
            "slot_type": "T-slot",
            # --- practical, vendor-agnostic "good enough" T-slot geometry -------
            # These are typical values that model well for brackets, T-nuts, etc.
            # They are NOT guaranteed vendor-accurate.
            "slot_opening_width_mm": 6.2,  # visible mouth opening
            "slot_inner_width_mm": 11,  # wider cavity behind the opening
            "slot_depth_mm": 6.2,  # from outer face into the profile
            "slot_corner_radius_mm": 1.2,  # for fillets in the slot cavity
            # --- mounting hardware assumptions ---------------------------------
            "nominal_hardware": "M5",
            # If you model a center bore at all: many 2020s are supplied with
            # a pilot / tap drill size that can be tapped to M5, but this varies.
            "center_bore_diameter_mm": 4.2,  # tap drill for M5 (if you want it)
            "corner_radius_mm": 1.5,  # outer corner rounding (typical)
            # Optional: useful “known good” clearances for brackets/printed parts
            "recommended_clearance_mm": 0.2,
        },
        # ---------------------------------------------------------------------
        # 40-series: 4040 (often conceptually "tiled 2020": same slot size, 2 slots)
        # ---------------------------------------------------------------------
        ExtrusionProfileType.PROFILE_4040: {
            "family": "40-series",
            "size_mm": (40.0, 40.0),
            "grid_pitch_mm": 20.0,
            "slots_per_side": 2,
            # For each face, there are usually two slots on a 20mm grid:
            # centerlines at +/- 10mm from the profile center
            "slot_centers_from_profile_center_mm": [-10.0, +10.0],
            "slot_type": "T-slot",
            # Keep the slot geometry identical to 2020 for modelling convenience
            "slot_opening_width_mm": 6.0,
            "slot_inner_width_mm": 11.5,
            "slot_depth_mm": 6.5,
            "slot_corner_radius_mm": 1.2,
            "nominal_hardware": "M5",
            # Center bores vary wildly for 4040 (some have a large through-hole,
            # some have multiple voids, some are intended for M8, some untapped).
            # For generic modelling: either omit it (None) or assume a large clearance.
            "center_bore_diameter_mm": None,
            "corner_radius_mm": 2.0,
            "recommended_clearance_mm": 0.2,
        },
    }
)


DEFAULT_EXTRUSION_LENGTH_MM = 120.0
SLOT_OVERSHOOT_MM = 0.4
LENGTH_OVERSHOOT_MM = 1.0


def _compute_slot_lip_depth(slot_depth_mm: float) -> float:
    capped = slot_depth_mm - 0.8
    depth_fraction = slot_depth_mm * 0.35
    return max(min(depth_fraction, capped), 0.6)


def create_t_slot_cutter(
    extrusion_profile_type: ExtrusionProfileType, length_mm: float
):
    profile = extrusion_profile_type
    lip_depth_mm = _compute_slot_lip_depth(profile.slot_depth_mm)

    opening_minus_inner_half = (
        profile.slot_inner_width_mm / 2 - profile.slot_opening_width_mm / 2
    )

    points_right = [
        (0, 0),
        (profile.slot_opening_width_mm / 2, 0),
        (profile.slot_inner_width_mm / 2, opening_minus_inner_half),
        (profile.slot_inner_width_mm / 2, profile.slot_depth_mm - lip_depth_mm),
        (profile.slot_opening_width_mm / 2, profile.slot_depth_mm - lip_depth_mm),
        (profile.slot_opening_width_mm / 2, profile.slot_depth_mm),
        (0, profile.slot_depth_mm),
    ]

    cutter_2d = create_extruded_polygon(points_right, length_mm)
    cutter_left = mirror(normal=(1, 0, 0), point=(0, 0, 0))(cutter_2d)
    cutter = cutter_2d.fuse(cutter_left)

    return cutter


def create_alu_extrusion_profile(
    extrusion_profile_type: ExtrusionProfileType = ExtrusionProfileType.PROFILE_2020,
    length_mm: float = DEFAULT_EXTRUSION_LENGTH_MM,
):
    profile = extrusion_profile_type
    size_x_mm, size_y_mm = profile.size_mm

    body = create_filleted_box(
        size_x_mm,
        size_y_mm,
        length_mm,
        fillet_radius=profile.corner_radius_mm,
        fillets_at=[
            Alignment.LEFT,
            Alignment.RIGHT,
            Alignment.FRONT,
            Alignment.BACK,
        ],
        no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    )

    body = align(body, None, Alignment.CENTER)

    slot_cutters = PartCollector()
    for i in range(4):

        slot_cutter = create_t_slot_cutter(
            extrusion_profile_type,
            length_mm + LENGTH_OVERSHOOT_MM,
        )

        slot_cutter = align(
            slot_cutter,
            body,
            Alignment.CENTER,
        )
        slot_cutter = align(slot_cutter, body, Alignment.BACK)
        for j in range(profile.slots_per_side):
            slot_center_offset = profile.slot_centers_from_profile_center_mm[j]
            slot_cutter_instance = translate(slot_center_offset, 0, 0)(slot_cutter)

            slot_cutter_instance = rotate(90 * i)(slot_cutter_instance)
            slot_cutters = slot_cutters.fuse(slot_cutter_instance)

    body = body.cut(slot_cutters)
    if profile.center_bore_diameter_mm is not None:

        center_bore_cutter = create_cylinder(
            profile.center_bore_diameter_mm / 2, length_mm + LENGTH_OVERSHOOT_MM
        )

        center_bore_cutter = align(center_bore_cutter, body, Alignment.CENTER)
        body = body.cut(center_bore_cutter)

    return body


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    for i, profile in enumerate(
        [
            ExtrusionProfileType.PROFILE_2020,
            ExtrusionProfileType.PROFILE_4040,
        ]
    ):
        part = create_alu_extrusion_profile(profile)
        part = translate(i * 40, 0, 0)(part)
        parts.add(part, f"alu_extrusion_profile_{profile.value}", flip=False)

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("alu_extrusion_profile created successfully!")


if __name__ == "__main__":
    main()
