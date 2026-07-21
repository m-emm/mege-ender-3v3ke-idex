import inspect
from pathlib import Path

import pytest
import yaml
from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_circuits.simple import load_pinout_config
from mege_ender_3v3ke_idex.designs.assemblies.pinout_base_plate_assembly import (
    create_pinout_base_plate_assembly,
    resolve_component_profiles,
)
from shellforgepy.simple import get_bounding_box_size, get_volume

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TMC5160_PINOUT = (
    REPOSITORY_ROOT
    / "klipper_setup"
    / "klipper_config"
    / "wiring"
    / "rp2040plus_btt_tmc5160t_plus_y.yaml"
)


def _load_yaml(path):
    return yaml.load(path.read_text(), Loader=AssemblyDefaultsLoader)


def _fixture_pinout(*, translation=(0, 0)):
    x_shift, y_shift = translation
    return f"""
basename: fixture
boxes:
  - id: module_box
    label: Module
    top_left: [{10 + x_shift}, {8 + y_shift}]
    size_pitches: [4, 3]
pin_sets:
  - id: socket_left
    prefix: L_
    origin: [{1 + x_shift}, {4 + y_shift}]
    direction: down
    pins: [ONE, TWO]
  - id: socket_right
    prefix: R_
    origin: [{4 + x_shift}, {4 + y_shift}]
    direction: down
    pins: [ONE, TWO]
  - id: module_contacts
    prefix: M_
    origin: [{11 + x_shift}, {7 + y_shift}]
    direction: right
    pins: [ONE, TWO]
physical_components:
  - id: socket
    component_type: fixture_socket
    pin_sets: [socket_left, socket_right]
    downholder: center_strip
  - id: module
    component_type: boxed_module
    pin_sets: [module_contacts]
    through_pin_sets: []
    box: module_box
    downholder: none
wires:
  - from: L_ONE
    to: L_TWO
"""


def _fixture_kwargs(pinout_path):
    return {
        "pinout_base_plate_pinout_yaml_path": pinout_path,
        "pinout_base_plate_raster_pitch": 2.5,
        "pinout_base_plate_thickness": 3.0,
        "pinout_base_plate_border": 2.0,
        "pinout_base_plate_corner_radius": 1.0,
        "pinout_base_plate_pin_tail_width": 0.6,
        "pinout_base_plate_pin_pass_through_clearance": 0.2,
        "pinout_base_plate_reference_frame_width": 0.8,
        "pinout_base_plate_reference_frame_height": 2.0,
        "pinout_base_plate_component_profiles": {
            "fixture_socket": {
                "left_margin_mm": 1.0,
                "right_margin_mm": 1.5,
                "top_margin_mm": 2.0,
                "bottom_margin_mm": 2.5,
                "body_height_mm": 4.0,
            }
        },
    }


def test_pinout_base_plate_generator_matches_resource_and_is_registered():
    resource_path = ASSEMBLIES_DIR / "pinout_base_plate_assembly.yaml"
    resource = _load_yaml(resource_path)
    parameter_names = set(
        inspect.signature(create_pinout_base_plate_assembly).parameters
    )

    assert parameter_names == set(resource["Parameters"])
    part_properties = resource["Parts"]["PinoutBasePlateAssembly"]["Properties"]
    assert part_properties["Generator"].endswith(
        ".pinout_base_plate_assembly.create_pinout_base_plate_assembly"
    )

    config = _load_yaml(ASSEMBLIES_DIR / "assemblies.yaml")
    matching_entries = [
        entry
        for entry in config["assemblies"]
        if entry["name"] == "pinout_base_plate_assembly"
    ]
    assert len(matching_entries) == 1
    entry = matching_entries[0]
    assert entry["resource_file"] == resource_path.name
    assert entry["depends_on"] == []
    assert set(entry["parameters"]) == parameter_names

    configured_pinout = (
        REPOSITORY_ROOT / entry["parameters"]["pinout_base_plate_pinout_yaml_path"]
    )
    file_dependency = (
        resource_path.parent / part_properties["FileDependencies"][0]
    ).resolve()
    assert file_dependency == configured_pinout.resolve()


def test_component_profile_registry_rejects_missing_and_invalid_dimensions():
    with pytest.raises(ValueError, match="missing"):
        resolve_component_profiles({"socket": {"left_margin_mm": 1}})

    with pytest.raises(ValueError, match="margins must be non-negative"):
        resolve_component_profiles(
            {
                "socket": {
                    "left_margin_mm": -1,
                    "right_margin_mm": 1,
                    "top_margin_mm": 1,
                    "bottom_margin_mm": 1,
                    "body_height_mm": 2,
                }
            }
        )


def test_base_plate_uses_derived_envelopes_through_contacts_and_exact_box(tmp_path):
    pinout_path = tmp_path / "fixture.yaml"
    pinout_path.write_text(_fixture_pinout())
    assembly = create_pinout_base_plate_assembly(**_fixture_kwargs(pinout_path))

    assert get_volume(assembly.leader) > 0
    assert assembly.followers == []
    assert set(assembly.non_production_indices_by_name) == {
        "component_socket",
        "reference_module_box",
    }
    assert set(assembly.cutter_indices_by_name) == {"pin_pass_throughs"}

    project = load_pinout_config(pinout_path)
    through_pin_count = sum(
        len(project.pin_sets[pin_set_id])
        for component in project.physical_components
        for pin_set_id in component.through_pin_sets
    )
    assert len(assembly.additional_data["pin_pass_throughs"]) == through_pin_count

    box = project.boxes[0]
    frame = assembly.get_non_production_part_by_name("reference_module_box")
    frame_size = get_bounding_box_size(frame)
    assert frame_size[0] == pytest.approx(
        box.size_pitches[0] * assembly.additional_data["raster_pitch_mm"]
    )
    assert frame_size[1] == pytest.approx(
        box.size_pitches[1] * assembly.additional_data["raster_pitch_mm"]
    )

    envelopes = assembly.additional_data["component_envelopes"]
    component_minimum_x = min(value["minimum_mm"][0] for value in envelopes.values())
    component_minimum_y = min(value["minimum_mm"][1] for value in envelopes.values())
    component_maximum_x = max(value["maximum_mm"][0] for value in envelopes.values())
    component_maximum_y = max(value["maximum_mm"][1] for value in envelopes.values())
    border = _fixture_kwargs(pinout_path)["pinout_base_plate_border"]
    plate_size = assembly.additional_data["plate_size_mm"]
    assert component_minimum_x == pytest.approx(border)
    assert component_minimum_y == pytest.approx(border)
    assert plate_size[0] - component_maximum_x == pytest.approx(border)
    assert plate_size[1] - component_maximum_y == pytest.approx(border)


def test_global_pinout_translation_preserves_normalized_plate_geometry(tmp_path):
    first_path = tmp_path / "first.yaml"
    second_path = tmp_path / "second.yaml"
    first_path.write_text(_fixture_pinout())
    second_path.write_text(_fixture_pinout(translation=(7, -5)))

    first = create_pinout_base_plate_assembly(**_fixture_kwargs(first_path))
    second = create_pinout_base_plate_assembly(**_fixture_kwargs(second_path))

    assert second.additional_data["plate_size_mm"] == pytest.approx(
        first.additional_data["plate_size_mm"]
    )
    for component_id, first_envelope in first.additional_data[
        "component_envelopes"
    ].items():
        second_envelope = second.additional_data["component_envelopes"][component_id]
        assert second_envelope["minimum_mm"] == pytest.approx(
            first_envelope["minimum_mm"]
        )
        assert second_envelope["maximum_mm"] == pytest.approx(
            first_envelope["maximum_mm"]
        )
        assert second_envelope["box_id"] == first_envelope["box_id"]
    first_centers = [
        entry["center_mm"] for entry in first.additional_data["pin_pass_throughs"]
    ]
    second_centers = [
        entry["center_mm"] for entry in second.additional_data["pin_pass_throughs"]
    ]
    for second_center, first_center in zip(second_centers, first_centers, strict=True):
        assert second_center == pytest.approx(first_center)


def test_tmc5160_pinout_physical_topology_builds_without_position_assertions():
    project = load_pinout_config(TMC5160_PINOUT)
    owned_pin_sets = {
        pin_set_id
        for component in project.physical_components
        for pin_set_id in component.pin_sets
    }
    assert owned_pin_sets == set(project.pin_sets)

    kwargs = assembly_kwargs(
        create_pinout_base_plate_assembly,
        pinout_base_plate_pinout_yaml_path=TMC5160_PINOUT,
        pinout_base_plate_raster_pitch=DEFAULTS["x_axis_mcu_dil_pitch"],
        pinout_base_plate_pin_tail_width=DEFAULTS["x_axis_mcu_wire_wrap_pin_side"],
    )
    assembly = create_pinout_base_plate_assembly(**kwargs)

    expected_through_pins = sum(
        len(project.pin_sets[pin_set_id])
        for component in project.physical_components
        for pin_set_id in component.through_pin_sets
    )
    assert len(assembly.additional_data["pin_pass_throughs"]) == expected_through_pins
    assert "reference_tmc5160t_plus_driver" in (assembly.non_production_indices_by_name)
