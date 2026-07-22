import math

import pytest
import yaml
from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.bigtreetech_stepper_driver_tmc_5160t_plus_assembly import (
    create_bigtreetech_stepper_driver_tmc_5160t_plus_assembly,
)
from shellforgepy.simple import (
    MScrew,
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
)

RESOURCE_FILE = (
    ASSEMBLIES_DIR / "bigtreetech_stepper_driver_tmc_5160t_plus_assembly.yaml"
)
ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"


@pytest.fixture(scope="module")
def driver_kwargs():
    return assembly_kwargs(create_bigtreetech_stepper_driver_tmc_5160t_plus_assembly)


@pytest.fixture(scope="module")
def driver(driver_kwargs):
    return create_bigtreetech_stepper_driver_tmc_5160t_plus_assembly(**driver_kwargs)


def test_driver_exposes_only_reference_capacitors_and_mount_cutters(driver):
    assert driver.followers == []
    assert driver.follower_indices_by_name == {}
    assert set(driver.non_production_indices_by_name) == {
        "capacitor_left",
        "capacitor_right",
    }
    assert set(driver.cutter_indices_by_name) == {
        "mount_hole_front_left",
        "mount_hole_front_right",
        "mount_hole_back_left",
        "mount_hole_back_right",
    }


def test_driver_housing_and_capacitors_match_configured_envelope(
    driver,
    driver_kwargs,
):
    assert get_bounding_box(driver.leader)[0] == pytest.approx((0, 0, 0))
    assert get_bounding_box_size(driver.leader) == pytest.approx(
        (
            driver_kwargs["bigtreetech_tmc5160t_plus_housing_length"],
            driver_kwargs["bigtreetech_tmc5160t_plus_housing_width"],
            driver_kwargs["bigtreetech_tmc5160t_plus_housing_height"],
        )
    )

    expected_capacitor_height = (
        driver_kwargs["bigtreetech_tmc5160t_plus_capacitor_top_height"]
        - driver_kwargs["bigtreetech_tmc5160t_plus_housing_height"]
    )
    for name, expected_x in (
        (
            "capacitor_left",
            driver_kwargs["bigtreetech_tmc5160t_plus_capacitor_left_x"],
        ),
        (
            "capacitor_right",
            driver_kwargs["bigtreetech_tmc5160t_plus_capacitor_right_x"],
        ),
    ):
        capacitor = driver.get_named_non_production_part(name)
        assert get_bounding_box_size(capacitor) == pytest.approx(
            (
                driver_kwargs["bigtreetech_tmc5160t_plus_capacitor_diameter"],
                driver_kwargs["bigtreetech_tmc5160t_plus_capacitor_diameter"],
                expected_capacitor_height,
            )
        )
        assert get_bounding_box_center(capacitor) == pytest.approx(
            (
                expected_x,
                driver_kwargs["bigtreetech_tmc5160t_plus_capacitor_y"],
                (
                    driver_kwargs["bigtreetech_tmc5160t_plus_housing_height"]
                    + driver_kwargs["bigtreetech_tmc5160t_plus_capacitor_top_height"]
                )
                / 2,
            )
        )


def test_driver_mount_cutters_form_configured_m3_pattern(driver, driver_kwargs):
    centers = {
        name: get_bounding_box_center(driver.get_cutter_part_by_name(name))
        for name in driver.cutter_indices_by_name
    }
    front_left = centers["mount_hole_front_left"]
    front_right = centers["mount_hole_front_right"]
    back_left = centers["mount_hole_back_left"]
    back_right = centers["mount_hole_back_right"]

    assert front_right[0] - front_left[0] == pytest.approx(
        driver_kwargs["bigtreetech_tmc5160t_plus_mount_hole_pitch_x"]
    )
    assert back_left[1] - front_left[1] == pytest.approx(
        driver_kwargs["bigtreetech_tmc5160t_plus_mount_hole_pitch_y"]
    )
    assert back_right[0] == pytest.approx(front_right[0])
    assert back_right[1] == pytest.approx(back_left[1])

    expected_diameter = MScrew.from_size(
        driver_kwargs["bigtreetech_tmc5160t_plus_mount_screw_size"]
    ).clearance_hole_normal
    for name in centers:
        cutter = driver.get_cutter_part_by_name(name)
        cutter_bbox = get_bounding_box(cutter)
        assert get_bounding_box_size(cutter)[0:2] == pytest.approx(
            (expected_diameter, expected_diameter)
        )
        assert cutter_bbox[1][2] == pytest.approx(0)
        assert cutter_bbox[0][2] < 0


def test_driver_housing_has_four_blind_m3_core_bores(driver, driver_kwargs):
    mount_screw = MScrew.from_size(
        driver_kwargs["bigtreetech_tmc5160t_plus_mount_screw_size"]
    )
    unbored_volume = (
        driver_kwargs["bigtreetech_tmc5160t_plus_housing_length"]
        * driver_kwargs["bigtreetech_tmc5160t_plus_housing_width"]
        * driver_kwargs["bigtreetech_tmc5160t_plus_housing_height"]
    )
    expected_bore_volume = (
        4
        * math.pi
        * (mount_screw.core_hole / 2) ** 2
        * driver_kwargs["bigtreetech_tmc5160t_plus_mount_hole_core_bore_depth"]
    )

    assert get_volume(driver.leader) == pytest.approx(
        unbored_volume - expected_bore_volume,
        abs=0.1,
    )
    assert mount_screw.core_hole < mount_screw.clearance_hole_normal


def test_driver_resource_is_visualization_only_and_has_no_explicit_colors():
    resource = yaml.safe_load(RESOURCE_FILE.read_text())
    visualization = resource["Builder"]["Visualization"]

    assert resource["Builder"]["Production"]["parts"] == []
    assert visualization["preview"]["views"] == [
        "isometric",
        "top",
        "bottom",
        "front",
        "back",
        "left",
        "right",
    ]
    assert "color:" not in RESOURCE_FILE.read_text()


def test_driver_is_registered_as_a_standalone_assembly():
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    driver = assemblies["bigtreetech_stepper_driver_tmc_5160t_plus_assembly"]

    assert driver["resource_file"] == (
        "bigtreetech_stepper_driver_tmc_5160t_plus_assembly.yaml"
    )
    assert driver["depends_on"] == []
