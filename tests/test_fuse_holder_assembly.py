import math
from pathlib import Path

import pytest
import yaml

from mege_ender_3v3ke_idex.designs.assemblies.fuse_holder_assembly import (
    create_fuse_holder_assembly,
)
from shellforgepy.simple import (
    create_cylinder,
    get_bounding_box,
    get_bounding_box_size,
    get_volume,
)


FUSE_HOLDER_PARAMS = {
    "fuse_holder_thread_diameter": 14.85,
    "fuse_holder_thread_length": 8.5,
    "fuse_holder_total_cylinder_length": 50,
    "fuse_holder_thin_cylinder_diameter": 11,
    "fuse_holder_thin_cylinder_length": 18.6,
    "fuse_holder_thicker_cylinder_diameter": 13.13,
    "fuse_holder_thicker_cylinder_length": 11.7,
    "fuse_holder_front_diameter": 16.9,
    "fuse_holder_front_length": 10,
    "fuse_holder_mount_nut_outer_diameter": 21,
    "fuse_holder_mount_nut_thickness": 5,
    "fuse_holder_mount_hole_clearance": 0.5,
    "fuse_holder_body_clearance": 0.5,
}


RESOURCE_FILE = (
    Path(__file__).resolve().parents[1]
    / "assembling"
    / "assemblies"
    / "fuse_holder_assembly.yaml"
)


def _build_fuse_holder():
    return create_fuse_holder_assembly(**FUSE_HOLDER_PARAMS)


def _assert_segment_radius(body, mid_x, radius):
    body_volume = get_volume(body)
    inside_probe = create_cylinder(
        radius - 0.05,
        0.3,
        origin=(mid_x - 0.15, 0, 0),
        direction=(1, 0, 0),
    )
    outside_probe = create_cylinder(
        0.1,
        0.3,
        origin=(mid_x - 0.15, radius + 0.2, 0),
        direction=(1, 0, 0),
    )

    assert body_volume - get_volume(body.cut(inside_probe)) == pytest.approx(
        get_volume(inside_probe), rel=0.01
    )
    assert body_volume - get_volume(body.cut(outside_probe)) == pytest.approx(0)


def test_fuse_holder_exposes_visual_parts_cutters_and_references():
    fuse_holder = _build_fuse_holder()

    assert set(fuse_holder.follower_indices_by_name) == {
        "holder_body",
        "mount_nut",
        "terminal_blades",
    }
    assert set(fuse_holder.cutter_indices_by_name) == {
        "mount_hole",
        "body_clearance",
    }
    assert set(fuse_holder.non_production_indices_by_name) == {
        "holder_reference",
        "mount_panel_reference",
    }


def test_fuse_holder_body_total_length_is_measured_length():
    fuse_holder = _build_fuse_holder()
    holder_body = fuse_holder.get_follower_part_by_name("holder_body")
    holder_body_bbox = get_bounding_box(holder_body)
    holder_body_size = get_bounding_box_size(holder_body)

    assert holder_body_bbox[0][0] == pytest.approx(0, abs=0.05)
    assert holder_body_bbox[1][0] == pytest.approx(50, abs=0.05)
    assert holder_body_size[0] == pytest.approx(50, abs=0.05)
    assert holder_body_size[1] == pytest.approx(16.9, abs=0.05)
    assert holder_body_size[2] == pytest.approx(16.9, abs=0.05)


def test_fuse_holder_body_segments_match_measured_lengths_and_diameters():
    fuse_holder = _build_fuse_holder()
    holder_body = fuse_holder.get_follower_part_by_name("holder_body")
    shoulder_length = 50 - 18.6 - 11.7 - 8.5 - 10
    expected_volume = (
        math.pi * (11 / 2) ** 2 * 18.6
        + math.pi * (13.13 / 2) ** 2 * 11.7
        + math.pi * (14.85 / 2) ** 2 * shoulder_length
        + math.pi * (14.85 / 2) ** 2 * 8.5
        + math.pi * (16.9 / 2) ** 2 * 10
    )

    assert get_volume(holder_body) == pytest.approx(expected_volume, rel=0.01)
    _assert_segment_radius(holder_body, 9.3, 11 / 2)
    _assert_segment_radius(holder_body, 18.6 + 11.7 / 2, 13.13 / 2)
    _assert_segment_radius(holder_body, 18.6 + 11.7 + shoulder_length / 2, 14.85 / 2)
    _assert_segment_radius(
        holder_body,
        18.6 + 11.7 + shoulder_length + 8.5 / 2,
        14.85 / 2,
    )
    _assert_segment_radius(holder_body, 50 - 10 / 2, 16.9 / 2)


def test_fuse_holder_mount_nut_dimensions_and_bore_match_thread_clearance():
    fuse_holder = _build_fuse_holder()
    mount_nut = fuse_holder.get_follower_part_by_name("mount_nut")
    mount_nut_bbox = get_bounding_box(mount_nut)
    mount_nut_size = get_bounding_box_size(mount_nut)
    mount_nut_volume = get_volume(mount_nut)
    bore_diameter = 14.85 + 0.5
    inside_bore_probe = create_cylinder(
        bore_diameter / 2 - 0.05,
        7,
        origin=(34, 0, 0),
        direction=(1, 0, 0),
    )
    bore_edge_probe = create_cylinder(
        bore_diameter / 2 + 0.2,
        7,
        origin=(34, 0, 0),
        direction=(1, 0, 0),
    )

    assert mount_nut_bbox[0][0] == pytest.approx(35, abs=0.05)
    assert mount_nut_bbox[1][0] == pytest.approx(40, abs=0.05)
    assert mount_nut_size[0] == pytest.approx(5, abs=0.05)
    assert max(mount_nut_size[1], mount_nut_size[2]) == pytest.approx(21, abs=0.05)
    assert mount_nut_volume - get_volume(
        mount_nut.cut(inside_bore_probe)
    ) == pytest.approx(0)
    assert mount_nut_volume - get_volume(mount_nut.cut(bore_edge_probe)) > 0


def test_fuse_holder_panel_reference_and_cutters_match_clearances():
    fuse_holder = _build_fuse_holder()
    mount_panel_reference = fuse_holder.get_non_production_part_by_name(
        "mount_panel_reference"
    )
    mount_hole = fuse_holder.get_cutter_part_by_name("mount_hole")
    body_clearance = fuse_holder.get_cutter_part_by_name("body_clearance")

    assert get_bounding_box_size(mount_panel_reference) == pytest.approx(
        (1.8, 15.35, 15.35), abs=0.05
    )
    assert get_bounding_box_size(mount_hole) == pytest.approx(
        (70, 15.35, 15.35), abs=0.05
    )
    assert get_bounding_box_size(body_clearance) == pytest.approx(
        (70, 17.4, 17.4), abs=0.05
    )


def test_fuse_holder_resource_declares_visible_preview_colors_and_views():
    resource = yaml.safe_load(RESOURCE_FILE.read_text())
    preview = resource["Builder"]["Visualization"]["preview"]
    parts = resource["Builder"]["Visualization"]["parts"]

    body_rule = next(rule for rule in parts if rule.get("names") == ["holder_body"])
    nut_rule = next(rule for rule in parts if rule.get("names") == ["mount_nut"])
    blade_rule = next(
        rule for rule in parts if rule.get("names") == ["terminal_blades"]
    )

    assert preview["views"] == ["isometric", "front", "right", "top"]
    assert body_rule["artifact"] == "followers"
    assert body_rule["color"] == [0.35, 0.45, 0.55]
    assert nut_rule["artifact"] == "followers"
    assert nut_rule["color"] == [0.78, 0.78, 0.72]
    assert blade_rule["artifact"] == "followers"
    assert blade_rule["color"] == [0.9, 0.86, 0.72]
