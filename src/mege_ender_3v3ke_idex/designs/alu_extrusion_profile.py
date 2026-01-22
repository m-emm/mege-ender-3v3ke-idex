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

from mege_3devops.process_data.mender3.process_data_04_high_speed import *
from poemai_utils.enum_utils import add_enum_attrs
from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

# Production mode from environment variable
PROD = os.environ.get("SHELLFORGEPY_PRODUCTION", "0") == "1"

PROCESS_DATA = PROCESS_DATA_PETGCF_04_HS


class ExtrusionProfileType(Enum):
    PROFILE_2020 = "2020"

    # “Most common” 4040 in Europe/industrial catalogs:
    # 40x40 with ONE slot per face, slot size 8 (often called “slot 8 / Nut 8”).
    PROFILE_4040 = "4040"

    # Special / less common (but exists): 4040 with TWO slots per face (20 mm pitch tiled style)
    PROFILE_4040_2SLOT = "4040_2slot"


def add_enum_attrs(enum_to_attrs: dict):
    for enum_member, attrs in enum_to_attrs.items():
        for k, v in attrs.items():
            setattr(enum_member, k, v)


add_enum_attrs(
    {
        # ---------------------------------------------------------------------
        # 20-series: 2020 (slot ~6, “Nut 5” ecosystem)
        # ---------------------------------------------------------------------
        ExtrusionProfileType.PROFILE_2020: {
            "family": "20-series",
            "size_mm": (20.0, 20.0),
            "grid_pitch_mm": 20.0,
            "slots_per_side": 1,
            "slot_centers_from_profile_center_mm": [0.0],
            "slot_type": "T-slot",
            "slot_series": 6,  # informal: “slot 6”
            # Practical, vendor-agnostic values (good for modelling brackets/T-nuts)
            "slot_opening_width_mm": 6.2,
            "slot_inner_width_mm": 11.0,
            "slot_depth_mm": 6.2,
            "slot_corner_radius_mm": 1.2,
            # Hardware assumptions (typical)
            "nominal_hardware": "M5",
            "center_bore_diameter_mm": 4.2,  # tap drill for M5 (if you model tapping)
            "corner_radius_mm": 1.5,
            "recommended_clearance_mm": 0.2,
        },
        # ---------------------------------------------------------------------
        # 40-series: 4040 “slot 8” style (as in your drawing)
        # ONE slot per face, centered; opening ~8 mm; center bore ~Ø6.8; outer corner R4
        # ---------------------------------------------------------------------
        ExtrusionProfileType.PROFILE_4040: {
            "family": "40-series",
            "size_mm": (40.0, 40.0),
            "grid_pitch_mm": 40.0,  # the natural grid unit for this family is 40
            "slots_per_side": 1,
            "slot_centers_from_profile_center_mm": [0.0],
            "slot_type": "T-slot",
            "slot_series": 8,  # informal: “slot 8 / Nut 8”
            # Values aligned with the common 40x40 slot-8 geometry (good modelling start)
            "slot_opening_width_mm": 8.0,  # your drawing explicitly shows 8
            "slot_inner_width_mm": 14.0,  # typical cavity behind an 8mm mouth
            "slot_depth_mm": 8.0,  # typical depth for slot-8 profiles
            "slot_corner_radius_mm": 1.5,
            # Hardware assumptions (slot 8 commonly uses M6 / M8 depending on nut type;
            # M6 is the “typical” light-duty assumption, M8 exists for heavier hardware)
            "nominal_hardware": "M6",
            # Your drawing shows Ø6.80 center hole (often for M8 tap drill-ish / or clearance-ish
            # depending on profile system). Keep as modelling default.
            "center_bore_diameter_mm": 6.8,
            "corner_radius_mm": 4.0,  # your drawing shows R4
            "recommended_clearance_mm": 0.2,
        },
        # ---------------------------------------------------------------------
        # 4040 “tiled 20mm grid” variant (two slots per face) — special case
        # This is the one you had before; keep it as an explicit alternative.
        # ---------------------------------------------------------------------
        ExtrusionProfileType.PROFILE_4040_2SLOT: {
            "family": "40-series",
            "size_mm": (40.0, 40.0),
            "grid_pitch_mm": 20.0,  # tiled 20mm pitch
            "slots_per_side": 2,
            "slot_centers_from_profile_center_mm": [-10.0, +10.0],
            "slot_type": "T-slot",
            "slot_series": 6,  # often these are literally two 20-series-style slots
            "slot_opening_width_mm": 6.2,
            "slot_inner_width_mm": 11.0,
            "slot_depth_mm": 6.2,
            "slot_corner_radius_mm": 1.2,
            "nominal_hardware": "M5",
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


def creeate_demo_parts(parts: PartList):
    for i, profile in enumerate(
        [
            ExtrusionProfileType.PROFILE_2020,
            ExtrusionProfileType.PROFILE_4040,
            ExtrusionProfileType.PROFILE_4040_2SLOT,
        ]
    ):
        part = create_alu_extrusion_profile(profile)
        part = translate(i * 60, 0, 0)(part)
        parts.add(part, f"alu_extrusion_profile_{profile.value}", flip=False)


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    if os.environ.get("CREATE_DEMO_PARTS", "0") == "1":
        creeate_demo_parts(parts)

    else:
        # add a test part for a PETG CF test print
        part = create_alu_extrusion_profile(
            ExtrusionProfileType.PROFILE_2020, length_mm=20
        )
        parts.add(part, "alu_extrusion_profile_2020_30mm", flip=False)

    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("alu_extrusion_profile created successfully!")


if __name__ == "__main__":
    main()
