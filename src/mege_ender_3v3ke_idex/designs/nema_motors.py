"""
Nema Motors

Usage:
    cd <project_root> && ./run.sh path/to/nema_motors.py
    # or with production mode:
    cd <project_root> && SHELLFORGEPY_PRODUCTION=1 ./run.sh path/to/nema_motors.py
"""

import logging
import os
from typing import Optional
from enum import Enum

from shellforgepy.simple import *
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.geometry.m_screws import MScrew
from poemai_utils.enum_utils import add_enum_attrs

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

from enum import Enum


class NemaSizes(Enum):
    NEMA14 = "NEMA14"
    NEMA17 = "NEMA17"
    NEMA23 = "NEMA23"
    NEMA34 = "NEMA34"

add_enum_attrs(
    {
        # ---------------------------------------------------------------------
        # NEMA 14 (35mm class)
        # ---------------------------------------------------------------------
        NemaSizes.NEMA14: {
            "size_mm": 35.0,               # face size (approx)
            "hole_dist_mm": 26.0,          # common NEMA14 hole spacing
            "screw_size": "M3",
            "clearance_diameter_mm": 3.2,  # bracket clearance for M3
            "tap_drill_diameter_mm": 2.5,  # tap drill for M3
            "hole_depth_mm": 4.0,          # typical usable thread depth
            "axle_diameter_mm": 5.0,       # common, but some are 4mm
            "axle_diameter_variants_mm": [4.0, 5.0],
            "axle_length_mm": 20.0,        # typical exposed shaft length
            "thick_mm": 28.0,              # common "short" motor
            "thick_variants_mm": [20.0, 28.0, 34.0, 40.0],
            # optional CAD helpers / typical coupler sizes
            "coupler_length_mm": 20.0,
            "coupler_diameter_mm": 15.0,
            "connector_length_mm": None,
            "connector_thick_mm": None,
            # optional front boss / pilot (often present, varies widely)
            "pilot_diameter_mm": 22.0,
            "pilot_depth_mm": 1.5,
            "disc_thick_mm": 1.5,
        },

        # ---------------------------------------------------------------------
        # NEMA 17 (42mm class)
        # ---------------------------------------------------------------------
        NemaSizes.NEMA17: {
            "size_mm": 42.3,               # common nominal face size
            "hole_dist_mm": 31.0,          # very common NEMA17 hole spacing
            "screw_size": "M3",
            "clearance_diameter_mm": 3.2,  # bracket clearance for M3
            "tap_drill_diameter_mm": 2.5,  # tap drill for M3
            "hole_depth_mm": 4.5,          # typical; many motors are 4.5-5mm
            "axle_diameter_mm": 5.0,       # very common
            "axle_diameter_variants_mm": [5.0],
            "axle_length_mm": 24.0,        # very common
            "thick_mm": 40.0,              # common "mid" length
            "thick_variants_mm": [20.0, 28.0, 34.0, 40.0, 48.0, 60.0],
            "coupler_length_mm": 25.0,
            "coupler_diameter_mm": 18.0,
            "connector_length_mm": 16.15,
            "connector_thick_mm": 11.5,
            "pilot_diameter_mm": 22.0,
            "pilot_depth_mm": 2.0,
            "disc_thick_mm": 2.0,
        },

        # ---------------------------------------------------------------------
        # NEMA 23 (57mm class)
        # ---------------------------------------------------------------------
        NemaSizes.NEMA23: {
            "size_mm": 56.4,               # nominal NEMA23 face ~2.23 in = 56.6mm (varies by vendor)
            "hole_dist_mm": 47.14,         # common hole spacing used in many CAD tables (1.856 in)
            "screw_size": "M5",
            "clearance_diameter_mm": 5.5,  # bracket clearance for M5
            "tap_drill_diameter_mm": 4.2,  # tap drill for M5
            "hole_depth_mm": 6.0,          # typical usable depth
            "axle_diameter_mm": 6.35,      # 1/4" is common; some are 8mm
            "axle_diameter_variants_mm": [6.35, 8.0],
            "axle_length_mm": 20.0,
            "thick_mm": 56.0,              # common "short-ish" NEMA23
            "thick_variants_mm": [41.0, 56.0, 76.0, 100.0],
            "coupler_length_mm": 30.0,
            "coupler_diameter_mm": 22.0,
            "connector_length_mm": None,
            "connector_thick_mm": None,
            "pilot_diameter_mm": 38.1,     # 1.5" pilot is common; varies
            "pilot_depth_mm": 2.0,
            "disc_thick_mm": 2.0,
        },

        # ---------------------------------------------------------------------
        # NEMA 34 (86mm class)
        # ---------------------------------------------------------------------
        NemaSizes.NEMA34: {
            "size_mm": 86.0,               # nominal NEMA34 face ~3.4 in = 86.4mm
            "hole_dist_mm": 69.85,         # common hole spacing (2.75 in)
            "screw_size": "M6",
            "clearance_diameter_mm": 6.6,  # bracket clearance for M6
            "tap_drill_diameter_mm": 5.0,  # tap drill for M6
            "hole_depth_mm": 8.0,          # typical usable depth
            "axle_diameter_mm": 14.0,      # common; also 12.7mm (1/2") variants exist
            "axle_diameter_variants_mm": [12.7, 14.0],
            "axle_length_mm": 32.0,
            "thick_mm": 66.0,              # common
            "thick_variants_mm": [66.0, 96.0, 126.0],
            "coupler_length_mm": 35.0,
            "coupler_diameter_mm": 28.0,
            "connector_length_mm": None,
            "connector_thick_mm": None,
            "pilot_diameter_mm": 73.0,     # varies a lot; treat as rough
            "pilot_depth_mm": 2.5,
            "disc_thick_mm": 2.5,
        },
    }
)

def create_nema_screw_holes(
    nema: NemaSizes = NemaSizes.NEMA17,
    hole_diameter: Optional[float] = None,
    screw_size: Optional[str] = None,
    clearance_kind: str = "normal",
    hole_clearance: float = 0.0,
    hole_dist: Optional[float] = None,
    body_thickness: Optional[float] = None,
    hole_depth: Optional[float] = None,
    extra_front_depth: float = 0.0,
    back_extension: float = 0.0,
    align_to_top: bool = False,
):
    """Create the front-face mounting screw holes for a NEMA motor."""
    holes = PartCollector()

    resolved_hole_dist = hole_dist if hole_dist is not None else nema.hole_dist_mm
    if resolved_hole_dist is None:
        raise ValueError(f"{nema.value} missing 'hole_dist_mm'")
    offset = resolved_hole_dist / 2.0

    screw_choice = screw_size if screw_size is not None else nema.screw_size

    final_diameter = hole_diameter
    if final_diameter is None:
        if nema.clearance_diameter_mm is not None:
            final_diameter = nema.clearance_diameter_mm
        elif screw_choice is not None:
            screw_info = MScrew.from_size(screw_choice)
            base_diameter = getattr(
                screw_info,
                f"clearance_hole_{clearance_kind}",
                screw_info.clearance_hole_normal,
            )
            final_diameter = base_diameter
        else:
            final_diameter = 3.0  # conservative fallback
    final_diameter += 2.0 * hole_clearance

    resolved_body_thickness = (
        body_thickness if body_thickness is not None else nema.thick_mm
    )
    resolved_hole_depth = (
        hole_depth if hole_depth is not None else nema.hole_depth_mm
    )
    if resolved_body_thickness is None or resolved_hole_depth is None:
        raise ValueError(f"{nema.value} missing body thickness or hole depth")

    hole_height = resolved_hole_depth + max(extra_front_depth, 0.0) + back_extension
    hole_start_z = (
        0.0 if align_to_top else resolved_body_thickness - resolved_hole_depth - back_extension
    )

    for x in (-offset, offset):
        for y in (-offset, offset):
            hole = create_cylinder(final_diameter / 2.0, hole_height)
            hole = translate(x, y, hole_start_z)(hole)
            holes = holes.fuse(hole)

    return holes


def create_nema_motor(
    nema: NemaSizes = NemaSizes.NEMA17,
    enlarge_h: float = 0.0,
    enlarge_v: float = 0.0,
    screw_size: Optional[str] = None,
    mount_hole_clearance: float = 0.0,
    clearance_kind: str = "normal",
):
    """Create a NEMA motor body (leader-only), without axle/coupler/connector."""
    body_size = nema.size_mm
    body_thick = nema.thick_mm
    disc_thick = nema.disc_thick_mm if nema.disc_thick_mm is not None else (nema.pilot_depth_mm or 2.0)
    if None in (body_size, body_thick):
        raise ValueError(f"{nema.value} missing body dimensions (size/thick)")

    body_width = body_size + 2.0 * enlarge_h
    body_height = body_thick + 2.0 * enlarge_v

    body = create_box(
        body_width,
        body_width,
        body_height,
        origin=(-body_width / 2.0, -body_width / 2.0, -enlarge_v),
    )

    screw_holes = create_nema_screw_holes(
        nema=nema,
        screw_size=screw_size,
        clearance_kind=clearance_kind,
        hole_clearance=mount_hole_clearance,
        extra_front_depth=enlarge_v,
    )
    body = body.cut(screw_holes)

    motor = PartCollector()
    motor = motor.fuse(body)

    pilot_radius = (nema.pilot_diameter_mm / 2.0) if nema.pilot_diameter_mm is not None else (body_size / 4.0)
    front_disc = create_cylinder(pilot_radius, disc_thick)
    front_disc = translate(0, 0, body_thick)(front_disc)
    motor = motor.fuse(front_disc)

    return motor


def _create_coupler(nema: NemaSizes):
    coupler = create_cylinder(
        nema.coupler_diameter_mm / 2.0,
        nema.coupler_length_mm,
    )
    if None in (nema.thick_mm, nema.axle_length_mm, nema.coupler_length_mm):
        raise ValueError(f"{nema.value} missing coupler placement dimensions")
    return translate(
        0,
        0,
        nema.thick_mm + nema.axle_length_mm - nema.coupler_length_mm / 2.0,
    )(coupler)


def _create_axle(nema: NemaSizes):
    axle = create_cylinder(
        nema.axle_diameter_mm / 2.0,
        nema.axle_length_mm,
    )
    if None in (nema.thick_mm, nema.axle_length_mm, nema.axle_diameter_mm):
        raise ValueError(f"{nema.value} missing axle dimensions")
    return translate(0, 0, nema.thick_mm)(axle)


def _create_connector(nema: NemaSizes):
    connector = create_box(
        nema.connector_length_mm,
        nema.connector_length_mm,
        nema.connector_thick_mm,
    )
    if None in (
        nema.size_mm,
        nema.connector_length_mm,
        nema.connector_thick_mm,
    ):
        raise ValueError(f"{nema.value} missing connector dimensions")
    return translate(
        nema.size_mm / 2.0,
        -nema.connector_length_mm / 2.0,
        0,
    )(connector)


def create_nema_composite(
    nema: NemaSizes = NemaSizes.NEMA17,
    enlarge_h: float = 0.0,
    enlarge_v: float = 0.0,
    mount_hole_clearance: float = 0.0,
    mount_hole_back_extension: float = 0.0,
    axle_clearance: float = 0.0,
    boss_clearance: float = 0.0,
    boss_cut_depth: Optional[float] = None,
    body_clearance: float = 0.0,
    body_cut_depth: Optional[float] = None,
    screw_size: Optional[str] = None,
):
    """Build a LeaderFollowersCuttersPart for a NEMA motor with named followers/cutters.

    Cutters:
    - mount_holes: through-hole drill pattern, extended backwards by mount_hole_back_extension
    - axle: clearance hole for the shaft (axle_clearance to loosen fit)
    - front_boss: clearance recess for the front disc (boss_clearance for diameter slack)
    - body: clearance box for the motor body itself (body_clearance on X/Y, depth via body_cut_depth)

    Followers:
    - coupler, axle, connector: kept separate so consumers can fuse selectively.
    """

    body_thick = nema.thick_mm
    disc_thick = nema.disc_thick_mm if nema.disc_thick_mm is not None else (nema.pilot_depth_mm or 2.0)
    body_size = nema.size_mm
    if None in (body_thick, disc_thick, body_size):
        raise ValueError(f"{nema.value} missing body dimensions for composite generation")
    boss_base_depth = (
        boss_cut_depth
        if boss_cut_depth is not None
        else (nema.pilot_depth_mm if nema.pilot_depth_mm is not None else disc_thick)
    )
    boss_cut_depth = boss_base_depth

    leader = create_nema_motor(
        nema=nema,
        enlarge_h=enlarge_h,
        enlarge_v=enlarge_v,
        screw_size=screw_size,
        mount_hole_clearance=mount_hole_clearance,
        clearance_kind="normal",
    )

    axle_radius = nema.axle_diameter_mm / 2.0 + 2.0 * axle_clearance
    axle_height = nema.axle_length_mm + mount_hole_back_extension + 4.0 * axle_clearance
    if None in (nema.axle_diameter_mm, nema.axle_length_mm):
        raise ValueError(f"{nema.value} missing axle dimensions for composite generation")
    axle_cutter = create_cylinder(axle_radius, axle_height)
    axle_center_z = body_thick + (nema.axle_length_mm / 2.0)
    axle_cutter = translate(0, 0, axle_center_z - axle_height / 2.0)(axle_cutter)

    pilot_radius = (nema.pilot_diameter_mm / 2.0) if nema.pilot_diameter_mm is not None else (body_size / 4.0)
    boss_radius = pilot_radius + 2.0 * boss_clearance
    boss_height = boss_base_depth + 2.0 * boss_clearance
    boss_cutter = create_cylinder(boss_radius, boss_height)
    boss_center_z = body_thick + (boss_base_depth / 2.0)
    boss_cutter = translate(0, 0, boss_center_z - boss_height / 2.0)(boss_cutter)

    followers = [_create_axle(nema), _create_coupler(nema), _create_connector(nema)]
    follower_names = ["axle", "coupler", "connector"]

    body_base_height = body_cut_depth if body_cut_depth is not None else body_thick
    body_cut_height = body_base_height + 4.0 * body_clearance
    body_width = body_size + 4.0 * body_clearance
    body_cutter = create_box(
        body_width,
        body_width,
        body_cut_height,
        origin=(-body_width / 2.0, -body_width / 2.0, -body_cut_height / 2.0),
    )
    body_cutter = align(body_cutter, leader, Alignment.CENTER)

    # Mount holes cutter that extends upward from the motor top.
    mount_holes_cutter = create_nema_screw_holes(
        nema=nema,
        screw_size=screw_size,
        clearance_kind="normal",
        hole_clearance=mount_hole_clearance,
        body_thickness=body_thick,
        hole_depth=body_thick,
        back_extension=mount_hole_back_extension,
        align_to_top=True,
    )
    mount_holes_cutter = align(mount_holes_cutter, leader, Alignment.CENTER)
    mount_holes_cutter = align(mount_holes_cutter, leader, Alignment.STACK_TOP)

    cutters = [mount_holes_cutter, axle_cutter, boss_cutter, body_cutter]
    cutter_names = ["mount_holes", "axle", "front_boss", "body"]

    return LeaderFollowersCuttersPart(
        leader=leader,
        followers=followers,
        cutters=cutters,
        follower_names=follower_names if follower_names else None,
        cutter_names=cutter_names,
        additional_data={
            "type": nema.value.lower(),
            "mount_hole_clearance": mount_hole_clearance,
            "axle_clearance": axle_clearance,
            "boss_clearance": boss_clearance,
            "body_clearance": body_clearance,
            "screw_size": screw_size,
            "nema_size": nema.value,
        },
    )


def create_nema_motors(
    nema: NemaSizes = NemaSizes.NEMA17,
    plate_size: float = 70.0,
    plate_thickness: float = 6.0,
    mount_hole_clearance: float = 0.2,
    axle_clearance: float = 0.2,
    boss_clearance: float = 0.8,
    body_clearance: float = 0.2,
    body_cut_depth: Optional[float] = None,
    screw_size: Optional[str] = None,
):
    """Create a NEMA17 assembly and a visualization with cutters fused on."""
    chosen_body_cut_depth = (
        body_cut_depth if body_cut_depth is not None else plate_thickness + 1.0
    )

    motor = create_nema_composite(
        mount_hole_clearance=mount_hole_clearance,
        mount_hole_back_extension=plate_thickness + 1.0,
        axle_clearance=axle_clearance,
        boss_clearance=boss_clearance,
        boss_cut_depth=None,
        body_clearance=body_clearance,
        body_cut_depth=chosen_body_cut_depth,
        screw_size=screw_size,
        nema=nema,
    )

    # Visualization: fuse selected followers (axle and coupler) to the leader.
    visual_motor = motor.get_leader_as_part().fuse(
        motor.get_follower_part_by_name("axle")
    )
    visual_motor = visual_motor.fuse(motor.get_follower_part_by_name("coupler"))
    # Experiment: fuse all cutters to visualize alignment/positions.
    cutter_visual = PartCollector()
    for cutter in motor.cutters:
        cutter_visual.fuse(cutter)
    if cutter_visual.part is not None:
        visual_motor = visual_motor.fuse(cutter_visual.part)

    return motor, visual_motor


def main():
    logging.basicConfig(level=logging.INFO)
    parts = PartList()

    motor, visual_motor = create_nema_motors()
    nema_name = motor.additional_data.get("nema_size", "nema")
    parts.add(motor.get_leader_as_part(), f"{nema_name}_motor_leader", flip=False)
    parts.add(visual_motor, f"{nema_name}_motor_visual_with_cutters", flip=False)

    # Arrange and export
    arrange_and_export(
        parts.as_list(),
        script_file=__file__,
        prod=PROD,
        process_data=PROCESS_DATA,
    )

    _logger.info("nema_motors created successfully!")


if __name__ == "__main__":
    main()
