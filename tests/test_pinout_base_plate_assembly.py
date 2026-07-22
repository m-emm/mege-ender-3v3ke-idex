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
from shellforgepy.simple import get_bounding_box, get_bounding_box_size, get_volume

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
    direction: right
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
    downholder: none
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


def _fixture_kwargs(pinout_path, *, pass_through_style="row_slot"):
    return {
        "pinout_base_plate_pinout_yaml_path": pinout_path,
        "pinout_base_plate_raster_pitch": 2.5,
        "pinout_base_plate_thickness": 3.0,
        "pinout_base_plate_border_left": 2.0,
        "pinout_base_plate_border_right": 2.0,
        "pinout_base_plate_border_top": 0.0,
        "pinout_base_plate_border_bottom": 2.0,
        "pinout_base_plate_corner_radius": 1.0,
        "pinout_base_plate_pin_tail_width": 0.6,
        "pinout_base_plate_pin_pass_through_clearance": 0.2,
        "pinout_base_plate_pin_row_base_width": 2.4,
        "pinout_base_plate_pin_row_slot_clearance": 0.3,
        "pinout_base_plate_pin_row_vertical_clearance": 0.4,
        "pinout_base_plate_wire_wrap_pin_length": 10.0,
        "pinout_base_plate_wire_wrap_pin_base_thickness": 2.0,
        "pinout_base_plate_top_pin_length": 2.5,
        "pinout_base_plate_pin_line_clamp_base_length": 6.0,
        "pinout_base_plate_pin_line_clamp_holder_slack": 0.3,
        "pinout_base_plate_pin_line_clamp_vertical_slack": 0.2,
        "pinout_base_plate_pin_line_clamp_lip_size": 0.8,
        "pinout_base_plate_pin_line_clamp_slit_width": 0.4,
        "pinout_base_plate_reference_frame_width": 0.8,
        "pinout_base_plate_reference_frame_height": 2.0,
        "pinout_base_plate_mount_screw_size": "M2.5",
        "pinout_base_plate_mount_screw_length": 12.0,
        "pinout_base_plate_mount_screw_clearance_type": "loose",
        "pinout_base_plate_self_threading_clearance_type": "close",
        "pinout_base_plate_self_threading_core_radius_adjustment": -0.25,
        "pinout_base_plate_self_threading_extra_hole_length": 1.0,
        "pinout_base_plate_mount_eye_diameter_clearance": 2.0,
        "pinout_base_plate_downholder_profiles": {
            "corner": {
                "thickness_mm": 2.1,
                "rail_width_mm": 2.5,
                "bridge_width_mm": 2.5,
                "bridge_pin_indices_from_bottom": [1, 2],
            },
            "center_strip": {"thickness_mm": 2.1, "strip_width_mm": 1.0},
            "perimeter_frame": {
                "thickness_mm": 2.1,
                "rail_width_mm": 2.5,
                "crossbar_width_mm": 2.5,
            },
            "pin_line_upholder": {
                "thickness_mm": 2.1,
                "body_border_mm": 1.5,
                "roof_thickness_mm": 1.0,
                "recess_fit_clearance_mm": 0.3,
                "pocket_vertical_clearance_mm": 0.2,
                "screw_length_mm": 8.0,
                "minimum_thread_engagement_mm": 4.0,
                "screw_tip_clearance_mm": 0.3,
                "boss_diameter_mm": 6.5,
            },
        },
        "pinout_base_plate_usb_bridge_wall_thickness": 2.0,
        "pinout_base_plate_usb_cable_hole_width": 15.0,
        "pinout_base_plate_usb_cable_hole_height": 15.0,
        "pinout_base_plate_pico_usb_connector_width": 7.0,
        "pinout_base_plate_pico_usb_connector_thickness": 3.0,
        "pinout_base_plate_pico_usb_connector_depth": 5.0,
        "pinout_base_plate_pico_usb_connector_offset": 1.0,
        "pinout_base_plate_component_profiles": {
            "fixture_socket": {
                "left_margin_mm": 1.0,
                "right_margin_mm": 1.5,
                "top_margin_mm": 2.0,
                "bottom_margin_mm": 2.5,
                "body_height_mm": 4.0,
                "pass_through_style": pass_through_style,
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
        if entry["name"] == "y_axis_driver_board_holder_assembly"
    ]
    assert len(matching_entries) == 1
    assert not any(
        entry["name"] == "pinout_base_plate_assembly" for entry in config["assemblies"]
    )
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
                    "pass_through_style": "row_slot",
                }
            }
        )

    with pytest.raises(ValueError, match="pass_through_style"):
        resolve_component_profiles(
            {
                "socket": {
                    "left_margin_mm": 1,
                    "right_margin_mm": 1,
                    "top_margin_mm": 1,
                    "bottom_margin_mm": 1,
                    "body_height_mm": 2,
                    "pass_through_style": "invented",
                }
            }
        )

    profile = resolve_component_profiles(
        {
            "socket": {
                "left_margin_mm": 1,
                "right_margin_mm": 1,
                "top_margin_mm": 1,
                "bottom_margin_mm": 1,
                "body_height_mm": 2,
                "pass_through_style": "row_slot",
            }
        }
    )["socket"]
    assert profile.clamp_surface_height_mm == profile.body_height_mm


def test_base_plate_uses_derived_envelopes_through_contacts_and_exact_box(tmp_path):
    pinout_path = tmp_path / "fixture.yaml"
    pinout_path.write_text(_fixture_pinout())
    assembly = create_pinout_base_plate_assembly(**_fixture_kwargs(pinout_path))

    assert get_volume(assembly.leader) > 0
    assert assembly.followers == []
    non_production_names = set(assembly.non_production_indices_by_name)
    assert {
        "component_socket",
        "reference_module_box",
    } <= non_production_names
    assert set(assembly.cutter_indices_by_name) == {"pin_row_slots"}

    project = load_pinout_config(pinout_path)
    through_pin_count = sum(
        len(project.pin_sets[pin_set_id])
        for component in project.physical_components
        for pin_set_id in component.through_pin_sets
    )
    assert len(assembly.additional_data["pin_pass_throughs"]) == through_pin_count
    assert len(assembly.additional_data["pin_row_slots"]) == 2
    assert {
        slot["orientation"] for slot in assembly.additional_data["pin_row_slots"]
    } == {"horizontal", "vertical"}
    for slot in assembly.additional_data["pin_row_slots"]:
        preview_name = f"pin_header_{slot['component_id']}_{slot['pin_set_id']}_pins"
        assert preview_name in non_production_names
        preview_bbox = get_bounding_box(
            assembly.get_named_non_production_part(preview_name)
        )
        top_pins_bbox = get_bounding_box(
            assembly.get_named_non_production_part(
                preview_name.removesuffix("_pins") + "_top_pins"
            )
        )
        preview_center = [
            (top_pins_bbox[0][axis] + top_pins_bbox[1][axis]) / 2 for axis in (0, 1)
        ]
        slot_center = [
            (slot["minimum_mm"][axis] + slot["maximum_mm"][axis]) / 2 for axis in (0, 1)
        ]
        assert preview_center == pytest.approx(slot_center)
        assert preview_bbox[0][2] < 0
        assert preview_bbox[1][2] == pytest.approx(
            assembly.additional_data["plate_size_mm"][2]
        )
    assert assembly.additional_data["individual_pin_pass_throughs"] == []
    row_slots_bbox = get_bounding_box(assembly.get_named_cutter("pin_row_slots"))
    assert row_slots_bbox[0][2] < 0
    assert row_slots_bbox[1][2] > assembly.additional_data["plate_size_mm"][2]

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
    margins = assembly.additional_data["plate_margins_mm"]
    plate_size = assembly.additional_data["plate_size_mm"]
    assert component_minimum_x >= margins["left"]
    assert component_minimum_y >= margins["bottom"]
    assert plate_size[0] - component_maximum_x >= margins["right"]
    assert plate_size[1] - component_maximum_y == pytest.approx(margins["top"])


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


def test_individual_hole_profile_preserves_per_contact_cutters(tmp_path):
    pinout_path = tmp_path / "individual.yaml"
    pinout_path.write_text(_fixture_pinout())
    assembly = create_pinout_base_plate_assembly(
        **_fixture_kwargs(pinout_path, pass_through_style="individual_holes")
    )

    assert set(assembly.cutter_indices_by_name) == {"individual_pin_pass_throughs"}
    assert assembly.additional_data["pin_row_slots"] == []
    assert len(assembly.additional_data["individual_pin_pass_throughs"]) == 4


def test_row_slot_rejects_non_unit_pin_spacing(tmp_path):
    pinout_path = tmp_path / "irregular.yaml"
    pinout_path.write_text(
        _fixture_pinout().replace(
            "direction: down\n    pins: [ONE, TWO]",
            "direction: down\n    step: 2\n    pins: [ONE, TWO]",
            1,
        )
    )

    with pytest.raises(ValueError, match="one-pitch spacing"):
        create_pinout_base_plate_assembly(**_fixture_kwargs(pinout_path))


def test_center_strip_rejects_a_strip_wider_than_the_socket_channel(tmp_path):
    pinout_path = tmp_path / "narrow-channel.yaml"
    pinout_path.write_text(
        _fixture_pinout()
        .replace(
            "direction: right\n    pins: [ONE, TWO]",
            "direction: down\n    pins: [ONE, TWO]",
        )
        .replace("downholder: none", "downholder: center_strip", 1)
    )
    kwargs = _fixture_kwargs(pinout_path)
    kwargs["pinout_base_plate_downholder_profiles"]["center_strip"][
        "strip_width_mm"
    ] = 100

    with pytest.raises(ValueError, match="between socket rows"):
        create_pinout_base_plate_assembly(**kwargs)


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
        pinout_base_plate_pin_row_base_width=DEFAULTS[
            "x_axis_mcu_wire_wrap_pin_base_width"
        ],
        pinout_base_plate_pin_row_slot_clearance=DEFAULTS[
            "x_axis_mcu_electronics_holder_slack"
        ],
        pinout_base_plate_pin_row_vertical_clearance=DEFAULTS[
            "x_axis_mcu_base_cutter_vertical_slack"
        ],
        pinout_base_plate_wire_wrap_pin_length=DEFAULTS[
            "x_axis_mcu_wire_wrap_pin_length"
        ],
        pinout_base_plate_wire_wrap_pin_base_thickness=DEFAULTS[
            "x_axis_mcu_wire_wrap_pin_base_thickness"
        ],
        pinout_base_plate_top_pin_length=DEFAULTS["x_axis_mcu_top_pin_length"],
        pinout_base_plate_pin_line_clamp_base_length=DEFAULTS[
            "board_holder_additional_pins_base_plate_length"
        ],
    )
    assembly = create_pinout_base_plate_assembly(**kwargs)

    expected_through_pins = sum(
        len(project.pin_sets[pin_set_id])
        for component in project.physical_components
        for pin_set_id in component.through_pin_sets
    )
    assert len(assembly.additional_data["pin_pass_throughs"]) == expected_through_pins
    assert assembly.additional_data["pin_row_slots"]
    assert assembly.additional_data["individual_pin_pass_throughs"] == []
    assert "individual_pin_pass_throughs" not in assembly.cutter_indices_by_name
    roof_slits = assembly.additional_data["pin_line_upholder_roof_slits"]
    assert len(roof_slits) == 1
    roof_slit = roof_slits[0]
    assert roof_slit["component_id"] == "external_io_pin_line"
    assert roof_slit["pin_count"] == len(project.pin_sets["external_io"])
    assert "pin_line_upholder_roof_slits" in assembly.cutter_indices_by_name
    assert assembly.additional_data["pin_line_clamp_component_ids"] == []
    assert assembly.additional_data["pin_line_upholder_component_ids"] == [
        "external_io_pin_line"
    ]
    assert all(
        slot["component_id"] != "external_io_pin_line"
        for slot in assembly.additional_data["pin_row_slots"]
    )
    non_production_names = set(assembly.non_production_indices_by_name)
    for slot in assembly.additional_data["pin_row_slots"]:
        preview_name = f"pin_header_{slot['component_id']}_{slot['pin_set_id']}_pins"
        assert preview_name in non_production_names
        preview_bbox = get_bounding_box(
            assembly.get_named_non_production_part(preview_name)
        )
        assert preview_bbox[0][2] < 0
        assert preview_bbox[1][2] == pytest.approx(
            assembly.additional_data["plate_size_mm"][2]
        )

    assert "pin_line_external_io_pin_line_pins" in non_production_names
    pin_line_pins_bbox = get_bounding_box(
        assembly.get_named_non_production_part("pin_line_external_io_pin_line_pins")
    )
    assert pin_line_pins_bbox[0][2] < 0
    assert pin_line_pins_bbox[1][2] < assembly.additional_data["plate_size_mm"][2]
    pin_line_top_pins_bbox = get_bounding_box(
        assembly.get_named_non_production_part("pin_line_external_io_pin_line_top_pins")
    )
    assert pin_line_top_pins_bbox[1][2] > assembly.additional_data["plate_size_mm"][2]
    pin_line_center = [
        (pin_line_top_pins_bbox[0][axis] + pin_line_top_pins_bbox[1][axis]) / 2
        for axis in (0, 1)
    ]
    pin_line_recess = next(
        recess
        for recess in assembly.additional_data["pin_line_upholder_recesses"]
        if recess["component_id"] == "external_io_pin_line"
    )
    pin_line_recess_center = [
        (
            pin_line_recess["minimum_mm"][axis]
            + pin_line_recess["maximum_mm"][axis]
        )
        / 2
        for axis in (0, 1)
    ]
    assert pin_line_center == pytest.approx(pin_line_recess_center)
    assert pin_line_recess["depth_mm"] + pin_line_recess[
        "roof_thickness_mm"
    ] == pytest.approx(assembly.additional_data["plate_size_mm"][2])
    assert "reference_tmc5160t_plus_driver" in (assembly.non_production_indices_by_name)
    assert "pico_usb_cable_passage" in assembly.cutter_indices_by_name
    assert "pico_usb_connector" in non_production_names
    usb_cable_passage_bbox = get_bounding_box(
        assembly.get_named_cutter("pico_usb_cable_passage")
    )
    assert usb_cable_passage_bbox[0][2] < 0
    assert usb_cable_passage_bbox[1][2] > assembly.additional_data["plate_size_mm"][2]
    usb_bridge = assembly.additional_data["pico_usb_bridge"]
    assert usb_bridge["component_id"] == "pico"
    assert usb_bridge["opening_width_mm"] > 0
    assert usb_bridge["opening_height_mm"] > 0
    assert usb_bridge["minimum_y_mm"] < usb_bridge["maximum_y_mm"]
    assert usb_bridge["plate_cutout_minimum_y_mm"] == pytest.approx(
        usb_bridge["minimum_y_mm"]
    )
    assert (
        usb_bridge["minimum_y_mm"] - usb_bridge["pico_board_maximum_y_mm"]
    ) == pytest.approx(usb_bridge["retaining_land_depth_mm"])
    assert usb_bridge["retaining_land_depth_mm"] == pytest.approx(
        assembly.additional_data["raster_pitch_mm"]
    )
    assert usb_bridge["maximum_y_mm"] == pytest.approx(
        assembly.additional_data["plate_size_mm"][1]
    )
    expected_downholders = {
        "downholder_pico",
        "downholder_socket_b",
        "downholder_socket_a",
        "downholder_u1_socket",
        "downholder_socket_hv",
        "downholder_socket_c",
        "downholder_tmc_adapter",
        "downholder_external_io_pin_line",
    }
    assert set(assembly.follower_indices_by_name) == expected_downholders
    assert "downholder_self_threading_holes" in assembly.cutter_indices_by_name
    assert "downholder_loose_holes" in assembly.cutter_indices_by_name

    downholders = {
        downholder["component_id"]: downholder
        for downholder in assembly.additional_data["downholders"]
    }
    pico_downholder = downholders["pico"]
    assert pico_downholder["rail_count"] == 2
    assert pico_downholder["bridge_count"] == len(
        pico_downholder["bridge_pin_indices_from_bottom"]
    )
    assert pico_downholder["eye_count"] == 4
    assert pico_downholder["loose_hole_count"] == 4

    adapter_downholder = downholders["tmc_adapter"]
    assert adapter_downholder["rail_count"] == 2
    assert adapter_downholder["crossbar_count"] == 2
    assert adapter_downholder["crossbar_offset_pitches"] == 1
    assert adapter_downholder["eye_count"] == 2
    assert adapter_downholder["loose_hole_count"] == 2

    pin_line_upholder = downholders["external_io_pin_line"]
    assert pin_line_upholder["eye_count"] == 2
    assert pin_line_upholder["loose_hole_count"] == 2
    assert pin_line_upholder["tail_slit_count"] == 1
    assert pin_line_upholder["tail_contact_count"] == len(
        project.pin_sets["external_io"]
    )
    assert "pin_line_upholder_tail_slits" in assembly.cutter_indices_by_name
    roof_slit_bbox = get_bounding_box(
        assembly.get_named_cutter("pin_line_upholder_roof_slits")
    )
    tail_slit_bbox = get_bounding_box(
        assembly.get_named_cutter("pin_line_upholder_tail_slits")
    )
    assert roof_slit_bbox[0][:2] == pytest.approx(tail_slit_bbox[0][:2])
    assert roof_slit_bbox[1][:2] == pytest.approx(tail_slit_bbox[1][:2])
    active_axis = 1 if pin_line_upholder["orientation"] == "vertical" else 0
    cross_axis = 1 - active_axis
    assert roof_slit_bbox[1][active_axis] - roof_slit_bbox[0][active_axis] > (
        assembly.additional_data["raster_pitch_mm"]
    )
    assert roof_slit_bbox[1][cross_axis] - roof_slit_bbox[0][cross_axis] == (
        pytest.approx(assembly.additional_data["pin_hole_size_mm"])
    )
    assert pin_line_upholder["screw_direction"] == "upward"
    assert pin_line_upholder["self_threading_lead_in_face"] == "bottom"
    assert all(
        downholder["self_threading_lead_in_face"] == "top"
        for component_id, downholder in downholders.items()
        if component_id != "external_io_pin_line"
    )
    plate_thickness = assembly.additional_data["plate_size_mm"][2]
    for component_id, downholder in downholders.items():
        cutter_bbox = get_bounding_box(
            assembly.get_named_cutter(
                f"downholder_{component_id}_self_threading_holes"
            )
        )
        if downholder["self_threading_lead_in_face"] == "bottom":
            assert cutter_bbox[0][2] == pytest.approx(
                downholder["self_threading_entry_z_mm"], abs=1e-6
            )
            assert downholder[
                "self_threading_hole_distance_from_head_mm"
            ] == pytest.approx(-downholder["holder_bottom_z_mm"])
        else:
            assert cutter_bbox[1][2] == pytest.approx(
                downholder["self_threading_entry_z_mm"], abs=1e-6
            )
            assert downholder["self_threading_entry_z_mm"] == pytest.approx(
                plate_thickness
            )
            assert downholder[
                "self_threading_hole_distance_from_head_mm"
            ] == pytest.approx(downholder["holder_top_z_mm"] - plate_thickness)
            assert cutter_bbox[0][2] < 0
    pin_line_profile = DEFAULTS["pinout_base_plate_downholder_profiles"][
        "pin_line_upholder"
    ]
    assert pin_line_upholder["screw_length_mm"] == pytest.approx(
        pin_line_profile["screw_length_mm"]
    )
    assert pin_line_upholder["thread_engagement_mm"] >= pin_line_profile[
        "minimum_thread_engagement_mm"
    ]
    assert pin_line_upholder["boss_count"] == 2
    assert pin_line_upholder["boss_height_mm"] > 0
    assert pin_line_upholder["boss_minimum_z_mm"] == pytest.approx(
        assembly.additional_data["plate_size_mm"][2]
    )
    assert pin_line_upholder["boss_maximum_z_mm"] > pin_line_upholder[
        "boss_minimum_z_mm"
    ]
    pin_line_thread_cutter_bbox = get_bounding_box(
        assembly.get_named_cutter(
            "downholder_external_io_pin_line_self_threading_holes"
        )
    )
    assert pin_line_thread_cutter_bbox[1][2] > pin_line_upholder[
        "boss_maximum_z_mm"
    ]
    assert pin_line_upholder["holder_bottom_z_mm"] < 0
    assert pin_line_upholder["holder_top_z_mm"] == pytest.approx(0)
    upholder_bbox = get_bounding_box(
        assembly.get_follower_part_by_name("downholder_external_io_pin_line")
    )
    assert upholder_bbox[0][2] < 0
    assert upholder_bbox[1][2] == pytest.approx(0)
    assert get_bounding_box(assembly.leader)[0][2] == pytest.approx(0, abs=1e-6)
    adapter_envelope = assembly.additional_data["component_envelopes"]["tmc_adapter"]
    assert (
        upholder_bbox[1][0] < adapter_envelope["minimum_mm"][0]
        or upholder_bbox[0][0] > adapter_envelope["maximum_mm"][0]
        or upholder_bbox[1][1] < adapter_envelope["minimum_mm"][1]
        or upholder_bbox[0][1] > adapter_envelope["maximum_mm"][1]
    )
    for screw_index in (1, 2):
        screw_bbox = get_bounding_box(
            assembly.get_named_non_production_part(
                f"downholder_external_io_pin_line_screw_{screw_index}"
            )
        )
        assert screw_bbox[0][2] < upholder_bbox[0][2]
        assert screw_bbox[1][2] > assembly.additional_data["plate_size_mm"][2]

    center_strip_component_ids = {
        component.id
        for component in project.physical_components
        if component.downholder.value == "center_strip"
    }
    assert center_strip_component_ids == set(downholders) - {
        "pico",
        "tmc_adapter",
        "external_io_pin_line",
    }
    for component_id in center_strip_component_ids:
        downholder = downholders[component_id]
        assert downholder["strip_count"] == 1
        assert downholder["eye_count"] == 2
        assert downholder["loose_hole_count"] == 2
        envelope = assembly.additional_data["component_envelopes"][component_id]
        screw_y_coordinates = sorted(
            center[1] for center in downholder["screw_centers_mm"]
        )
        assert screw_y_coordinates[0] < envelope["minimum_mm"][1]
        assert screw_y_coordinates[1] > envelope["maximum_mm"][1]

    pico_envelope = assembly.additional_data["component_envelopes"]["pico"]
    pico_screw_x_coordinates = sorted(
        {center[0] for center in pico_downholder["screw_centers_mm"]}
    )
    assert pico_screw_x_coordinates[0] < pico_envelope["minimum_mm"][0]
    assert pico_screw_x_coordinates[1] > pico_envelope["maximum_mm"][0]

    plate_width, plate_depth, _plate_thickness = assembly.additional_data[
        "plate_size_mm"
    ]
    for follower_name in expected_downholders:
        follower_bbox = get_bounding_box(
            assembly.get_follower_part_by_name(follower_name)
        )
        assert 0 <= follower_bbox[0][0] < follower_bbox[1][0] <= plate_width
        assert 0 <= follower_bbox[0][1] < follower_bbox[1][1] <= plate_depth

    topmost_physical_y = max(
        [
            envelope["maximum_mm"][1]
            for envelope in assembly.additional_data["component_envelopes"].values()
        ]
        + [
            get_bounding_box(assembly.get_follower_part_by_name(follower_name))[1][1]
            for follower_name in expected_downholders
        ]
    )
    assert plate_depth - topmost_physical_y == pytest.approx(
        assembly.additional_data["plate_margins_mm"]["top"]
    )
    assert all(
        downholder["holder_top_z_mm"] < DEFAULTS["pinout_base_plate_mount_screw_length"]
        for downholder in downholders.values()
    )
    screw_preview_names = {
        name
        for name in assembly.non_production_indices_by_name
        if name.startswith("downholder_") and "_screw_" in name
    }
    assert len(screw_preview_names) == sum(
        downholder["loose_hole_count"] for downholder in downholders.values()
    )


def test_tmc5160_external_pin_line_keeps_power_isolation_spares_and_endstop():
    project = load_pinout_config(TMC5160_PINOUT)
    component = next(
        component
        for component in project.physical_components
        if component.id == "external_io_pin_line"
    )
    pin_names = project.pin_sets[component.pin_sets[0]]

    assert component.component_type == "pin_line"
    assert component.downholder.value == "pin_line_upholder"
    assert pin_names == (
        "LINE18_F1_5A_OUT",
        "LINE18_F1_5A_IN",
        "LINE18_PWR_V24_SW_A",
        "LINE18_PWR_V24_SW_B",
        "LINE18_NC_ISOLATION",
        "LINE18_PWR_GND_A",
        "LINE18_PWR_GND_B",
        "LINE18_SPARE_01",
        "LINE18_SPARE_02",
        "LINE18_SPARE_03",
        "LINE18_SPARE_04",
        "LINE18_SPARE_05",
        "LINE18_SPARE_06",
        "LINE18_SPARE_07",
        "LINE18_SPARE_08",
        "LINE18_ENDSTOP_NO",
        "LINE18_ENDSTOP_GND",
        "LINE18_ENDSTOP_VCC",
    )

    edges = {
        frozenset((connection["from"], connection["to"]))
        for connection in project.connections
    }
    assert frozenset((pin_names[2], pin_names[3])) in edges
    assert frozenset((pin_names[3], pin_names[1])) in edges
    assert frozenset((pin_names[5], pin_names[6])) in edges
    assert frozenset((pin_names[15], "PICO_GPIO_4")) in edges
    assert frozenset((pin_names[16], "PICO_GND_03")) in edges
    assert frozenset((pin_names[17], "PICO_THREEV3_OUT_36")) in edges

    connected_pins = {pin for edge in edges for pin in edge}
    assert frozenset((pin_names[0], pin_names[1])) not in edges
    assert pin_names[4] not in connected_pins
    assert not set(pin_names[7:15]) & connected_pins

    physical_component_ids = {
        physical_component.id for physical_component in project.physical_components
    }
    assert "branch_fuse" not in physical_component_ids
    assert "f1" not in project.pin_sets
