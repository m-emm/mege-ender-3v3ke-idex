import math
from pathlib import Path

import pytest
import yaml

from mege_ender_3v3ke_idex.designs.assemblies.emergency_button_assembly import (
    create_emergency_button_assembly,
)
from shellforgepy.simple import get_bounding_box, get_bounding_box_size, get_volume


EMERGENCY_BUTTON_PARAMS = {
    "emergency_button_button_diameter": 40.15,
    "emergency_button_button_thickness": 6,
    "emergency_button_neck_diameter": 27.9,
    "emergency_button_neck_height": 27,
    "emergency_button_neck_silver_collar_height": 14,
    "emergency_button_neck_collar_wall_thickness": 2.0,
    "emergency_button_neck_collar_fit_clearance": 0.1,
    "emergency_button_neck_collar_gap": 2.4,
    "emergency_button_body_width": 30,
    "emergency_button_body_length": 36,
    "emergency_button_body_height": 34.2,
    "emergency_button_neck_mount_hole_diameter": 22,
    "emergency_button_neck_mount_hole_clearance": 1.0,
}


RESOURCE_FILE = (
    Path(__file__).resolve().parents[1]
    / "assembling"
    / "assemblies"
    / "emergency_button_assembly.yaml"
)


def test_emergency_button_exposes_visual_parts_and_cutters():
    emergency_button = create_emergency_button_assembly(**EMERGENCY_BUTTON_PARAMS)

    assert set(emergency_button.follower_indices_by_name) == {
        "body",
        "neck",
        "silver_collar",
        "button_disc",
    }
    assert set(emergency_button.cutter_indices_by_name) == {
        "neck_mount_hole",
        "neck_clearance",
    }
    emergency_button.get_non_production_part_by_name("button_reference")


def test_emergency_button_disc_matches_measured_size():
    emergency_button = create_emergency_button_assembly(**EMERGENCY_BUTTON_PARAMS)
    button_disc = emergency_button.get_follower_part_by_name("button_disc")
    button_disc_size = get_bounding_box_size(button_disc)

    assert button_disc_size[0] == pytest.approx(40.15, abs=0.05)
    assert button_disc_size[1] == pytest.approx(40.15, abs=0.05)
    assert button_disc_size[2] == pytest.approx(6, abs=0.05)


def test_emergency_button_collar_uses_measured_ring_dimensions():
    emergency_button = create_emergency_button_assembly(**EMERGENCY_BUTTON_PARAMS)
    silver_collar = emergency_button.get_follower_part_by_name("silver_collar")
    silver_collar_size = get_bounding_box_size(silver_collar)
    collar_inner_diameter = 27.9 - 2 * 2.0
    expected_volume = (
        math.pi
        * ((27.9 / 2) ** 2 - (collar_inner_diameter / 2) ** 2)
        * EMERGENCY_BUTTON_PARAMS["emergency_button_neck_silver_collar_height"]
    )

    assert silver_collar_size[0] == pytest.approx(27.9, abs=0.05)
    assert silver_collar_size[1] == pytest.approx(27.9, abs=0.05)
    assert silver_collar_size[2] == pytest.approx(14, abs=0.05)
    assert get_volume(silver_collar) == pytest.approx(expected_volume, rel=0.01)


def test_emergency_button_neck_steps_down_inside_collar():
    emergency_button = create_emergency_button_assembly(**EMERGENCY_BUTTON_PARAMS)
    neck = emergency_button.get_follower_part_by_name("neck")
    neck_size = get_bounding_box_size(neck)
    lower_height = 27 - 14 - 2.4
    top_diameter = 27.9 - 2 * 2.0 - 0.1
    expected_volume = (
        math.pi * (27.9 / 2) ** 2 * lower_height
        + math.pi * (top_diameter / 2) ** 2 * (14 + 2.4)
    )

    assert neck_size[0] == pytest.approx(27.9, abs=0.05)
    assert neck_size[1] == pytest.approx(27.9, abs=0.05)
    assert neck_size[2] == pytest.approx(27, abs=0.05)
    assert get_volume(neck) == pytest.approx(expected_volume, rel=0.01)


def test_emergency_button_collar_leaves_gap_to_thick_neck():
    emergency_button = create_emergency_button_assembly(**EMERGENCY_BUTTON_PARAMS)
    body = emergency_button.get_follower_part_by_name("body")
    silver_collar = emergency_button.get_follower_part_by_name("silver_collar")
    body_bbox = get_bounding_box(body)
    silver_collar_bbox = get_bounding_box(silver_collar)
    lower_neck_top = body_bbox[1][2] + 27 - 14 - 2.4

    assert silver_collar_bbox[0][2] - lower_neck_top == pytest.approx(2.4, abs=0.05)


def test_emergency_button_mount_hole_includes_clearance():
    emergency_button = create_emergency_button_assembly(**EMERGENCY_BUTTON_PARAMS)
    mount_hole = emergency_button.get_cutter_part_by_name("neck_mount_hole")
    mount_hole_size = get_bounding_box_size(mount_hole)

    assert mount_hole_size[0] == pytest.approx(23.0, abs=0.05)
    assert mount_hole_size[1] == pytest.approx(23.0, abs=0.05)


def test_emergency_button_resource_declares_visualization_colors():
    resource = yaml.safe_load(RESOURCE_FILE.read_text())
    parts = resource["Builder"]["Visualization"]["parts"]

    beige_rule = next(rule for rule in parts if rule.get("names") == ["body", "neck"])
    collar_rule = next(rule for rule in parts if rule.get("names") == ["silver_collar"])
    button_rule = next(rule for rule in parts if rule.get("names") == ["button_disc"])

    assert beige_rule["artifact"] == "followers"
    assert beige_rule["color"] == [0.72, 0.62, 0.46]
    assert collar_rule["artifact"] == "followers"
    assert collar_rule["color"] == [1.0, 1.0, 1.0]
    assert button_rule["artifact"] == "followers"
    assert button_rule["color"] == [0.88, 0.02, 0.02]
