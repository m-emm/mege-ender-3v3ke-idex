import pytest

from assembly_defaults import assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.heatbed_psu_housing_assembly import (
    create_heatbed_psu_housing_assembly,
)
from shellforgepy.simple import get_bounding_box, get_bounding_box_size, get_volume


def _build_heatbed_psu_housing():
    return create_heatbed_psu_housing_assembly(
        **assembly_kwargs(create_heatbed_psu_housing_assembly)
    )


def test_heatbed_psu_housing_exports_box_lid_and_expected_cutters():
    housing = _build_heatbed_psu_housing()

    assert housing.leader is not None
    assert set(housing.follower_indices_by_name) == {"heatbed_psu_housing_lid"}
    assert {"mount_flange_screw_holes", "cable_hole"} <= set(
        housing.cutter_indices_by_name
    )


def test_heatbed_psu_housing_has_expected_local_body_size():
    housing = _build_heatbed_psu_housing()

    body_reference = housing.get_non_production_part_by_name(
        "heatbed_psu_housing_body_reference"
    )
    body_size = get_bounding_box_size(body_reference)

    assert body_size[0] == pytest.approx(55)
    assert body_size[1] == pytest.approx(90)
    assert body_size[2] == pytest.approx(45)


def test_heatbed_psu_housing_has_no_switchboard_specific_exports():
    housing = _build_heatbed_psu_housing()
    exported_names = (
        set(housing.follower_indices_by_name)
        | set(housing.cutter_indices_by_name)
        | set(housing.non_production_indices_by_name)
    )

    forbidden_fragments = ("emergency", "fuse", "rail", "cable_cutout_cover")
    for exported_name in exported_names:
        assert not any(fragment in exported_name for fragment in forbidden_fragments)


def test_heatbed_psu_housing_cable_hole_matches_creality_psu_style_position():
    housing = _build_heatbed_psu_housing()

    cable_hole = housing.get_cutter_part_by_name("cable_hole")
    cable_hole_size = get_bounding_box_size(cable_hole)
    cable_hole_bbox = get_bounding_box(cable_hole)
    cable_hole_center = (
        (cable_hole_bbox[0][0] + cable_hole_bbox[1][0]) / 2,
        (cable_hole_bbox[0][1] + cable_hole_bbox[1][1]) / 2,
        (cable_hole_bbox[0][2] + cable_hole_bbox[1][2]) / 2,
    )

    assert cable_hole_size[0] == pytest.approx(9)
    assert cable_hole_size[1] == pytest.approx(9)
    assert cable_hole_center[0] == pytest.approx(55 - 16)
    assert cable_hole_center[1] == pytest.approx(12)

    leader_volume = get_volume(housing.leader)
    assert leader_volume - get_volume(housing.leader.cut(cable_hole)) == pytest.approx(
        0
    )
