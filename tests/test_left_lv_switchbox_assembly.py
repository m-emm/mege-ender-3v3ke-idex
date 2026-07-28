import inspect

import pytest
import yaml

pytest.importorskip("cadquery")

from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.left_lv_switchbox_assembly import (
    LID_SCREW_ENGAGEMENT,
    LID_SCREW_SIZE,
    TERMINAL_COUNT,
    TERMINAL_SCREW_SIZE,
    create_left_lv_switchbox_assembly,
)
from shellforgepy.simple import (
    MScrew,
    get_bounding_box,
    get_bounding_box_size,
    get_volume,
)

ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"
RESOURCE_FILE = ASSEMBLIES_DIR / "left_lv_switchbox_assembly.yaml"
ASSEMBLY_NAME = "left_lv_switchbox_assembly"
PARAMETER_PREFIX = "left_lv_switchbox_"


def _load_config():
    return yaml.load(
        ASSEMBLIES_FILE.read_text(),
        Loader=AssemblyDefaultsLoader,
    )


def _load_resource():
    return yaml.load(
        RESOURCE_FILE.read_text(),
        Loader=AssemblyDefaultsLoader,
    )


@pytest.fixture(scope="module")
def switchbox():
    return create_left_lv_switchbox_assembly(
        **assembly_kwargs(create_left_lv_switchbox_assembly)
    )


def test_switchbox_exports_one_body_one_lid_and_expected_hardware(switchbox):
    assert get_volume(switchbox.leader) > 0
    assert set(switchbox.follower_indices_by_name) == {"left_lv_switchbox_lid"}

    for index in range(2):
        prefix = f"lid_mount_screw_{index}"
        assert f"{prefix}_clearance_hole" in switchbox.cutter_indices_by_name
        assert f"{prefix}_thread_inset_pocket" in switchbox.cutter_indices_by_name
        assert f"{prefix}_screw" in switchbox.non_production_indices_by_name
        assert f"{prefix}_thread_inset" in switchbox.non_production_indices_by_name

    for index in range(TERMINAL_COUNT):
        assert f"terminal_{index}_square_nut_pocket" in switchbox.cutter_indices_by_name
        assert (
            f"terminal_{index}_square_nut" in switchbox.non_production_indices_by_name
        )

    all_names = (
        set(switchbox.follower_indices_by_name)
        | set(switchbox.cutter_indices_by_name)
        | set(switchbox.non_production_indices_by_name)
    )
    assert not any(
        forbidden in name
        for name in all_names
        for forbidden in ("board", "fuse", "bottom_lid")
    )


def test_fixed_bottom_and_closed_lid_match_parameterized_envelope(switchbox):
    body_reference_bbox = switchbox.additional_data["body_reference_bbox"]
    inner_space_bbox = get_bounding_box(switchbox.get_named_cutter("inner_space"))
    lid_bbox = get_bounding_box(switchbox.get_named_follower("left_lv_switchbox_lid"))

    assert body_reference_bbox[1][0] - body_reference_bbox[0][0] == pytest.approx(
        DEFAULTS["left_lv_switchbox_width"]
    )
    assert body_reference_bbox[1][1] - body_reference_bbox[0][1] == pytest.approx(
        DEFAULTS["left_lv_switchbox_depth"]
    )
    assert inner_space_bbox[0][2] - body_reference_bbox[0][2] == pytest.approx(
        DEFAULTS["left_lv_switchbox_bottom_thickness"]
    )
    assert lid_bbox[1][2] - body_reference_bbox[0][2] == pytest.approx(
        DEFAULTS["left_lv_switchbox_total_height"]
    )


def test_terminal_rail_and_lid_hardware_use_requested_fastener_families(switchbox):
    assert switchbox.additional_data["terminal_count"] == TERMINAL_COUNT
    assert switchbox.additional_data["terminal_screw_size"] == TERMINAL_SCREW_SIZE
    assert switchbox.additional_data["lid_screw_size"] == LID_SCREW_SIZE
    assert switchbox.additional_data["lid_screw_length"] == pytest.approx(
        DEFAULTS["left_lv_switchbox_lid_thickness"] + LID_SCREW_ENGAGEMENT
    )

    lid_screw = MScrew.from_size(LID_SCREW_SIZE)
    for index in range(2):
        clearance_hole = switchbox.get_named_cutter(
            f"lid_mount_screw_{index}_clearance_hole"
        )
        thread_inset = switchbox.get_named_non_production_part(
            f"lid_mount_screw_{index}_thread_inset"
        )
        assert get_bounding_box_size(clearance_hole)[:2] == pytest.approx(
            [lid_screw.clearance_hole_loose, lid_screw.clearance_hole_loose]
        )
        assert get_bounding_box_size(thread_inset)[2] == pytest.approx(
            lid_screw.thread_inset_length
        )


def test_resource_is_standalone_and_uses_petgcf_two_plate_production():
    resource = _load_resource()
    parameter_names = set(resource["Parameters"])
    assert parameter_names == set(
        inspect.signature(create_left_lv_switchbox_assembly).parameters
    )
    assert all(name.startswith(PARAMETER_PREFIX) for name in parameter_names)

    config = _load_config()
    entry = next(
        assembly
        for assembly in config["assemblies"]
        if assembly["name"] == ASSEMBLY_NAME
    )
    assert entry["depends_on"] == []
    assert "inject_parts" not in entry
    assert set(entry["parameters"]) == parameter_names

    production = resource["Builder"]["Production"]
    assert production["process_data_preset"] == "petgcf_max_strength_high_speed_06"
    assert [plate["name"] for plate in production["arrange"]["plates"]] == [
        "left_lv_switchbox",
        "left_lv_switchbox_lid",
    ]
    assert production["arrange"]["auto_assign_plates"] is False
