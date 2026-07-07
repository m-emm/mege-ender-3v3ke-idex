import pytest

from assembly_defaults import DEFAULTS
from mege_ender_3v3ke_idex.designs.alu_extrusion_profile import ExtrusionProfileType
from shellforgepy.simple import MScrew


def test_printer_foot_defaults_fit_m5x50_hammer_nut_interface():
    assert DEFAULTS["printer_foot_height"] == 65
    assert DEFAULTS["printer_foot_screw_length"] == 50
    assert DEFAULTS["printer_foot_mount_screw_sink"] == 17
    assert DEFAULTS["printer_foot_mount_screw_size"] == "M5"
    assert DEFAULTS["printer_foot_groove_filler_thickness"] == 1.5

    screw = MScrew.from_size(DEFAULTS["printer_foot_mount_screw_size"])
    screw_reach_past_profile_outside = (
        DEFAULTS["printer_foot_screw_length"]
        + screw.cylinder_head_height
        + DEFAULTS["printer_foot_mount_screw_sink"]
        - DEFAULTS["printer_foot_height"]
    )
    groove_inner_plane_height = (
        ExtrusionProfileType.PROFILE_4040.slot_inner_width_mm
        - ExtrusionProfileType.PROFILE_4040.slot_opening_width_mm
    ) / 2
    screw_reach_above_groove_inner_plane = (
        screw_reach_past_profile_outside - groove_inner_plane_height
    )

    assert groove_inner_plane_height == pytest.approx(3.0)
    assert screw_reach_past_profile_outside == pytest.approx(7.0)
    assert screw_reach_above_groove_inner_plane >= 4.0
    assert DEFAULTS["printer_foot_groove_filler_thickness"] < groove_inner_plane_height
