import math
from pathlib import Path

import pytest
import yaml

from mege_ender_3v3ke_idex.designs.assemblies.electric_switchboard_assembly import (
    create_electric_switchboard_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.emergency_button_assembly import (
    create_emergency_button_assembly,
)
from shellforgepy.simple import (
    create_box,
    create_cylinder,
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
)


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
    "emergency_button_neck_mount_hole_diameter": 23.9,
    "emergency_button_neck_mount_hole_clearance": 0.5,
}


ELECTRIC_SWITCHBOARD_PARAMS = {
    "electric_switchboard_height": 90,
    "electric_switchboard_width": 40,
    "electric_switchboard_depth": 80,
    "electric_switchboard_wall_thickness": 1.8,
    "electric_switchboard_cable_hole_count": 8,
    "electric_switchboard_cable_hole_diameter": 4,
    "electric_switchboard_cable_hole_pitch": 8,
    "electric_switchboard_cable_hole_z_offset_from_open_bottom": 18,
}


RESOURCE_FILE = (
    Path(__file__).resolve().parents[1]
    / "assembling"
    / "assemblies"
    / "electric_switchboard_assembly.yaml"
)


def _build_switchboard():
    emergency_button = create_emergency_button_assembly(**EMERGENCY_BUTTON_PARAMS)
    return create_electric_switchboard_assembly(
        emergency_button=emergency_button,
        **ELECTRIC_SWITCHBOARD_PARAMS,
    )


def test_switchboard_leader_has_measured_outer_dimensions():
    switchboard = _build_switchboard()
    size = get_bounding_box_size(switchboard.leader)

    assert size[0] == pytest.approx(40, abs=0.05)
    assert size[1] == pytest.approx(80, abs=0.05)
    assert size[2] == pytest.approx(90, abs=0.05)


def test_switchboard_is_open_at_bottom_and_keeps_top_wall():
    switchboard = _build_switchboard()
    leader = switchboard.leader
    leader_volume = get_volume(leader)
    wall_thickness = ELECTRIC_SWITCHBOARD_PARAMS["electric_switchboard_wall_thickness"]
    height = ELECTRIC_SWITCHBOARD_PARAMS["electric_switchboard_height"]

    bottom_void_probe = create_box(20, 20, 1, origin=(10, 30, 0.2))
    side_wall_probe = create_box(0.8, 20, 1, origin=(0.4, 30, 0.2))
    top_wall_probe = create_box(4, 4, 0.8, origin=(2, 2, height - wall_thickness / 2))

    assert leader_volume - get_volume(leader.cut(bottom_void_probe)) == pytest.approx(0)
    assert leader_volume - get_volume(leader.cut(side_wall_probe)) > 0
    assert leader_volume - get_volume(leader.cut(top_wall_probe)) > 0


def test_switchboard_reexports_positioned_emergency_button_parts():
    switchboard = _build_switchboard()

    assert {
        "emergency_button_body",
        "emergency_button_neck",
        "emergency_button_silver_collar",
        "emergency_button_button_disc",
        "emergency_button_button_reference",
        "emergency_button_mount_panel_reference",
    }.issubset(set(switchboard.non_production_indices_by_name))
    assert {
        "emergency_button_neck_mount_hole",
        "emergency_button_neck_clearance",
        "left_cable_holes",
        "right_cable_holes",
    }.issubset(set(switchboard.cutter_indices_by_name))


def test_switchboard_aligns_top_wall_to_emergency_button_groove_reference():
    switchboard = _build_switchboard()
    mount_panel_reference = switchboard.get_non_production_part_by_name(
        "emergency_button_mount_panel_reference"
    )
    reference_center = get_bounding_box_center(mount_panel_reference)
    reference_size = get_bounding_box_size(mount_panel_reference)
    wall_thickness = ELECTRIC_SWITCHBOARD_PARAMS["electric_switchboard_wall_thickness"]

    assert reference_size[2] == pytest.approx(
        EMERGENCY_BUTTON_PARAMS["emergency_button_neck_collar_gap"], abs=0.05
    )
    assert reference_center[0] == pytest.approx(20, abs=0.05)
    assert reference_center[1] == pytest.approx(40, abs=0.05)
    assert reference_center[2] == pytest.approx(90 - wall_thickness / 2, abs=0.05)


def test_switchboard_top_opening_uses_collar_inner_bore_mount_hole():
    switchboard = _build_switchboard()
    leader = switchboard.leader
    leader_volume = get_volume(leader)
    inside_hole_probe = create_cylinder(
        12.15,
        1.0,
        origin=(20, 40, 88.5),
    )
    outside_hole_probe = create_cylinder(
        12.45,
        1.0,
        origin=(20, 40, 88.5),
    )

    assert leader_volume - get_volume(leader.cut(inside_hole_probe)) == pytest.approx(0)
    assert leader_volume - get_volume(leader.cut(outside_hole_probe)) > 0


def test_switchboard_cable_hole_rows_are_on_both_long_sides():
    switchboard = _build_switchboard()
    params = ELECTRIC_SWITCHBOARD_PARAMS
    expected_row_volume = (
        params["electric_switchboard_cable_hole_count"]
        * math.pi
        * (params["electric_switchboard_cable_hole_diameter"] / 2) ** 2
        * (params["electric_switchboard_wall_thickness"] + 2)
    )

    for name, expected_x_min, expected_x_max in [
        ("left_cable_holes", -1, params["electric_switchboard_wall_thickness"] + 1),
        (
            "right_cable_holes",
            params["electric_switchboard_width"]
            - params["electric_switchboard_wall_thickness"],
            params["electric_switchboard_width"] + 2,
        ),
    ]:
        cable_holes = switchboard.get_cutter_part_by_name(name)
        bbox = get_bounding_box(cable_holes)
        size = get_bounding_box_size(cable_holes)
        center = get_bounding_box_center(cable_holes)

        assert bbox[0][0] == pytest.approx(expected_x_min, abs=0.05)
        assert bbox[1][0] == pytest.approx(expected_x_max, abs=0.05)
        assert size[1] == pytest.approx(
            params["electric_switchboard_cable_hole_pitch"]
            * (params["electric_switchboard_cable_hole_count"] - 1)
            + params["electric_switchboard_cable_hole_diameter"],
            abs=0.05,
        )
        assert size[2] == pytest.approx(
            params["electric_switchboard_cable_hole_diameter"], abs=0.05
        )
        assert center[1] == pytest.approx(
            params["electric_switchboard_depth"] / 2, abs=0.05
        )
        assert center[2] == pytest.approx(
            params["electric_switchboard_cable_hole_z_offset_from_open_bottom"],
            abs=0.05,
        )
        assert get_volume(cable_holes) == pytest.approx(expected_row_volume, rel=0.01)


def test_switchboard_resource_declares_visualization_and_production_rules():
    resource = yaml.safe_load(RESOURCE_FILE.read_text())
    visualization_parts = resource["Builder"]["Visualization"]["parts"]
    production = resource["Builder"]["Production"]

    switchboard_rule = next(
        rule
        for rule in visualization_parts
        if rule.get("name") == "electric_switchboard_box"
    )
    beige_rule = next(
        rule
        for rule in visualization_parts
        if rule.get("names") == ["emergency_button_body", "emergency_button_neck"]
    )
    collar_rule = next(
        rule
        for rule in visualization_parts
        if rule.get("names") == ["emergency_button_silver_collar"]
    )
    button_rule = next(
        rule
        for rule in visualization_parts
        if rule.get("names") == ["emergency_button_button_disc"]
    )
    production_part = production["parts"][0]

    assert switchboard_rule["color"] == [1, 1, 1]
    assert beige_rule["color"] == [0.72, 0.62, 0.46]
    assert collar_rule["color"] == [1.0, 1.0, 1.0]
    assert button_rule["color"] == [0.88, 0.02, 0.02]
    assert production["process_data_preset"] == "petgcf_max_strength_high_speed_06"
    assert production_part["artifact"] == "leader"
    assert production_part["name"] == "electric_switchboard_box"
    assert production_part["flip"] is True
    assert production["arrange"]["plates"] == [
        {"name": "electric_switchboard", "parts": ["electric_switchboard_box"]}
    ]
