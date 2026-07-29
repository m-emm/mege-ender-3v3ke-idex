import yaml

import pytest

pytest.importorskip("cadquery")

from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader
from mege_ender_3v3ke_idex.designs.assemblies.raspberry_pi_assembly import (
    RASPBERRY_PI_MODEL_3B,
    RASPBERRY_PI_MODEL_4B,
    create_raspberry_pi_assembly,
)
from shellforgepy.simple import get_bounding_box, get_bounding_box_center


RESOURCE_FILE = ASSEMBLIES_DIR / "raspberry_pi_assembly.yaml"
ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"

LEGACY_FOLLOWER_NAMES = {
    "network",
    "usb_1",
    "usb_2",
    "micro_usb",
    "hdmi",
    "jack",
    "microsd_socket",
    "microsd_card",
    "gpio",
}
RASPBERRY_PI_4_FOLLOWER_NAMES = {
    "network",
    "usb_1",
    "usb_2",
    "usb_c",
    "micro_hdmi_1",
    "micro_hdmi_2",
    "jack",
    "microsd_socket",
    "microsd_card",
    "gpio",
}
MOUNT_HOLE_NAMES = {
    "mount_hole_left_front",
    "mount_hole_left_back",
    "mount_hole_right_front",
    "mount_hole_right_back",
}


def _flat_bounding_box(part):
    return tuple(value for point in get_bounding_box(part) for value in point)


def test_default_raspberry_pi_model_matches_explicit_legacy_3b():
    default_raspberry_pi = create_raspberry_pi_assembly()
    explicit_raspberry_pi = create_raspberry_pi_assembly(
        raspberry_pi_model=RASPBERRY_PI_MODEL_3B
    )

    assert set(default_raspberry_pi.follower_indices_by_name) == LEGACY_FOLLOWER_NAMES
    assert set(default_raspberry_pi.cutter_indices_by_name) == MOUNT_HOLE_NAMES
    assert _flat_bounding_box(default_raspberry_pi.leader) == pytest.approx(
        _flat_bounding_box(explicit_raspberry_pi.leader)
    )

    for follower_name in LEGACY_FOLLOWER_NAMES:
        assert _flat_bounding_box(
            default_raspberry_pi.get_follower_part_by_name(follower_name)
        ) == pytest.approx(
            _flat_bounding_box(
                explicit_raspberry_pi.get_follower_part_by_name(follower_name)
            )
        )

    for default_cutter, explicit_cutter in zip(
        default_raspberry_pi.cutters,
        explicit_raspberry_pi.cutters,
        strict=True,
    ):
        assert _flat_bounding_box(default_cutter) == pytest.approx(
            _flat_bounding_box(explicit_cutter)
        )


def test_raspberry_pi_4_uses_shared_board_and_documented_connector_layout():
    raspberry_pi_3 = create_raspberry_pi_assembly()
    raspberry_pi_4 = create_raspberry_pi_assembly(
        raspberry_pi_model=RASPBERRY_PI_MODEL_4B
    )

    assert set(raspberry_pi_4.follower_indices_by_name) == (
        RASPBERRY_PI_4_FOLLOWER_NAMES
    )
    assert set(raspberry_pi_4.cutter_indices_by_name) == MOUNT_HOLE_NAMES
    assert _flat_bounding_box(raspberry_pi_4.leader) == pytest.approx(
        _flat_bounding_box(raspberry_pi_3.leader)
    )

    for shared_follower_name in ["gpio", "microsd_socket", "microsd_card"]:
        assert _flat_bounding_box(
            raspberry_pi_4.get_follower_part_by_name(shared_follower_name)
        ) == pytest.approx(
            _flat_bounding_box(
                raspberry_pi_3.get_follower_part_by_name(shared_follower_name)
            )
        )

    connector_centers = {
        name: get_bounding_box_center(raspberry_pi_4.get_follower_part_by_name(name))
        for name in [
            "network",
            "usb_1",
            "usb_2",
            "usb_c",
            "micro_hdmi_1",
            "micro_hdmi_2",
            "jack",
        ]
    }
    assert connector_centers["network"][1] == pytest.approx(45.75)
    assert connector_centers["usb_1"][1] == pytest.approx(9)
    assert connector_centers["usb_2"][1] == pytest.approx(27)
    assert connector_centers["usb_c"][0] == pytest.approx(11.2)
    assert connector_centers["micro_hdmi_1"][0] == pytest.approx(26)
    assert connector_centers["micro_hdmi_2"][0] == pytest.approx(39.5)
    assert connector_centers["jack"][0] == pytest.approx(54)

    assert (
        connector_centers["network"][1]
        > connector_centers["usb_2"][1]
        > connector_centers["usb_1"][1]
    )


def test_raspberry_pi_rejects_unsupported_model():
    with pytest.raises(ValueError, match="Unsupported Raspberry Pi model"):
        create_raspberry_pi_assembly(raspberry_pi_model="5B")


def test_raspberry_pi_yaml_defaults_to_3b_and_registers_4b_instance():
    resource = yaml.load(RESOURCE_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    assert resource["Parameters"]["raspberry_pi_model"] == {
        "Type": "String",
        "Default": RASPBERRY_PI_MODEL_3B,
    }
    assert assemblies["raspberry_pi_assembly"] == {
        "name": "raspberry_pi_assembly",
        "resource_file": "raspberry_pi_assembly.yaml",
        "depends_on": [],
    }
    assert assemblies["raspberry_pi_4_assembly"] == {
        "name": "raspberry_pi_4_assembly",
        "resource_file": "raspberry_pi_assembly.yaml",
        "depends_on": [],
        "parameters": {"raspberry_pi_model": RASPBERRY_PI_MODEL_4B},
    }
