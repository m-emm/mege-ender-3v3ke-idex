import pytest
import yaml

from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.tb6600_stripboard_interface_housing_assembly import (
    create_tb6600_stripboard_interface_housing_assembly,
)
from shellforgepy.geometry.m_screws import get_core_hole_diameter
from shellforgepy.simple import get_bounding_box, get_bounding_box_center
from shellforgepy.simple import create_cylinder, get_bounding_box_size
from shellforgepy.simple import get_clearance_hole_diameter, get_volume
from shellforgepy.simple import MScrew


RESOURCE_FILE = ASSEMBLIES_DIR / "tb6600_stripboard_interface_housing_assembly.yaml"
TB6600_PREFIX = "tb6600_stripboard_interface_housing_"


def _build_housing():
    return create_tb6600_stripboard_interface_housing_assembly(
        **assembly_kwargs(create_tb6600_stripboard_interface_housing_assembly)
    )


def _load_resource():
    return yaml.load(RESOURCE_FILE.read_text(), Loader=AssemblyDefaultsLoader)


def _load_assemblies_config():
    return yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(), Loader=AssemblyDefaultsLoader
    )


def _tb6600_assembly_entry():
    config = _load_assemblies_config()
    return next(
        assembly
        for assembly in config["assemblies"]
        if assembly["name"] == "tb6600_stripboard_interface_housing_assembly"
    )


def _assert_m3_self_threading_z_cutter(cutter):
    size = get_bounding_box_size(cutter)
    clearance = get_clearance_hole_diameter("M3", "close")
    adjusted_core_radius = (
        get_core_hole_diameter("M3") / 2
        + DEFAULTS[
            "tb6600_stripboard_interface_housing_self_threading_core_radius_adjustment"
        ]
    )

    assert size[:2] == pytest.approx([clearance, clearance])
    assert get_volume(cutter) < get_volume(create_cylinder(clearance / 2, size[2]))
    assert get_volume(cutter) > get_volume(
        create_cylinder(adjusted_core_radius, size[2])
    )


def test_tb6600_stripboard_interface_housing_exports_stable_artifacts():
    housing = _build_housing()

    assert get_volume(housing.leader) > 0
    assert set(housing.follower_indices_by_name) == {
        "tb6600_stripboard_interface_housing_lid"
    }

    expected_cutters = {
        "inner_space",
        "cable_exit",
        "cable_tie_slots",
        "cable_tie_slot_left_front",
        "cable_tie_slot_left_back",
        "cable_tie_slot_right_front",
        "cable_tie_slot_right_back",
        "mount_flange_screw_hole",
        "lid_mount_pilot_holes",
        "lid_mount_clearance_holes",
    }
    expected_cutters.update({f"lid_mount_pilot_hole_{index}" for index in range(1, 5)})
    expected_cutters.update(
        {f"lid_mount_clearance_hole_{index}" for index in range(1, 5)}
    )
    assert expected_cutters <= set(housing.cutter_indices_by_name)

    expected_non_production = {
        "tb6600_stripboard_interface_housing_body_reference",
        "lid_mount_screws",
        "mount_flange_screw",
    }
    assert set(housing.non_production_indices_by_name) == expected_non_production

    exported_names = (
        set(housing.follower_indices_by_name)
        | set(housing.cutter_indices_by_name)
        | set(housing.non_production_indices_by_name)
    )
    assert not any("thread_inset" in name for name in exported_names)


def test_tb6600_stripboard_interface_housing_does_not_model_the_board():
    housing = _build_housing()
    exported_names = (
        set(housing.follower_indices_by_name)
        | set(housing.cutter_indices_by_name)
        | set(housing.non_production_indices_by_name)
    )

    forbidden_fragments = ("pcb", "board_keepout", "stripboard_reference")
    for exported_name in exported_names:
        assert not any(fragment in exported_name for fragment in forbidden_fragments)


def test_tb6600_stripboard_interface_housing_is_roomy_for_real_stripboard():
    housing = _build_housing()
    body_reference = housing.get_non_production_part_by_name(
        "tb6600_stripboard_interface_housing_body_reference"
    )
    body_size = get_bounding_box_size(body_reference)

    board_width = (
        DEFAULTS["tb6600_stripboard_interface_housing_board_columns"]
        * DEFAULTS["tb6600_stripboard_interface_housing_board_pitch"]
    )
    board_depth = (
        DEFAULTS["tb6600_stripboard_interface_housing_board_rows"]
        * DEFAULTS["tb6600_stripboard_interface_housing_board_pitch"]
    )
    wall = DEFAULTS["tb6600_stripboard_interface_housing_wall_thickness"]
    screw_block = DEFAULTS[
        "tb6600_stripboard_interface_housing_lid_screw_mount_block_size"
    ]
    clearance = DEFAULTS["tb6600_stripboard_interface_housing_board_clearance"]
    front_corridor = DEFAULTS[
        "tb6600_stripboard_interface_housing_front_cable_corridor"
    ]

    usable_width_between_corner_posts = body_size[0] - 2 * wall - 2 * screw_block
    usable_depth_between_corner_posts = (
        body_size[1] - 2 * wall - 2 * screw_block - front_corridor
    )
    assert usable_width_between_corner_posts >= board_width + 2 * clearance
    assert usable_depth_between_corner_posts >= board_depth + 2 * clearance


def test_tb6600_stripboard_interface_housing_cable_exit_and_flange_orientation():
    housing = _build_housing()
    body_reference = housing.get_non_production_part_by_name(
        "tb6600_stripboard_interface_housing_body_reference"
    )
    body_bbox = get_bounding_box(body_reference)
    body_center = get_bounding_box_center(body_reference)

    cable_exit = housing.get_cutter_part_by_name("cable_exit")
    cable_exit_bbox = get_bounding_box(cable_exit)
    cable_exit_size = get_bounding_box_size(cable_exit)
    cable_exit_center = get_bounding_box_center(cable_exit)

    assert cable_exit_bbox[0][1] < body_bbox[0][1]
    assert (
        cable_exit_bbox[1][1]
        <= body_bbox[0][1]
        + DEFAULTS["tb6600_stripboard_interface_housing_wall_thickness"]
        + 2
    )
    assert cable_exit_size[0] == pytest.approx(
        DEFAULTS["tb6600_stripboard_interface_housing_cable_exit_width"]
    )
    assert cable_exit_size[2] == pytest.approx(
        DEFAULTS["tb6600_stripboard_interface_housing_cable_exit_height"]
    )
    assert cable_exit_center[0] == pytest.approx(body_center[0])
    assert cable_exit_bbox[0][2] == pytest.approx(
        DEFAULTS["tb6600_stripboard_interface_housing_cable_exit_floor_bridge"]
    )

    mount_hole = housing.get_cutter_part_by_name("mount_flange_screw_hole")
    mount_hole_bbox = get_bounding_box(mount_hole)
    mount_hole_center = get_bounding_box_center(mount_hole)
    mount_hole_size = get_bounding_box_size(mount_hole)

    assert mount_hole_center[0] == pytest.approx(body_center[0])
    assert mount_hole_center[1] > body_bbox[1][1]
    assert mount_hole_bbox[0][2] == pytest.approx(-1)
    assert mount_hole_size[2] == pytest.approx(
        DEFAULTS["tb6600_stripboard_interface_housing_mount_flange_thickness"] + 2
    )

    mount_screw = housing.get_named_non_production_part("mount_flange_screw")
    mount_screw_bbox = get_bounding_box(mount_screw)
    mount_screw_center = get_bounding_box_center(mount_screw)
    mount_screw_size = get_bounding_box_size(mount_screw)
    mount_screw_spec = MScrew.from_size(
        DEFAULTS["tb6600_stripboard_interface_housing_mount_flange_screw_size"]
    )
    mount_screw_length = DEFAULTS[
        "tb6600_stripboard_interface_housing_mount_flange_screw_length"
    ]

    assert mount_screw_length == pytest.approx(12.0)
    assert mount_screw_center[:2] == pytest.approx(mount_hole_center[:2], abs=0.05)
    assert mount_screw_bbox[0][2] == pytest.approx(
        mount_hole_bbox[1][2] - 1 - mount_screw_length,
        abs=0.05,
    )
    assert mount_screw_bbox[1][2] > mount_hole_bbox[1][2] - 1
    assert mount_screw_size[2] == pytest.approx(
        mount_screw_length + mount_screw_spec.cylinder_head_height,
        abs=0.05,
    )


def test_tb6600_stripboard_interface_housing_lid_screws_use_self_threading_bosses():
    housing = _build_housing()
    screw_spec = MScrew.from_size(
        DEFAULTS["tb6600_stripboard_interface_housing_lid_screw_size"]
    )
    body_reference = housing.get_non_production_part_by_name(
        "tb6600_stripboard_interface_housing_body_reference"
    )
    body_bbox = get_bounding_box(body_reference)

    pilot_centers = []
    clearance_centers = []
    for lid_screw_index in range(1, 5):
        pilot_hole = housing.get_cutter_part_by_name(
            f"lid_mount_pilot_hole_{lid_screw_index}"
        )
        clearance_hole = housing.get_cutter_part_by_name(
            f"lid_mount_clearance_hole_{lid_screw_index}"
        )

        _assert_m3_self_threading_z_cutter(pilot_hole)
        pilot_bbox = get_bounding_box(pilot_hole)
        pilot_center = get_bounding_box_center(pilot_hole)
        clearance_center = get_bounding_box_center(clearance_hole)
        clearance_size = get_bounding_box_size(clearance_hole)

        assert pilot_bbox[1][2] == pytest.approx(body_bbox[1][2], abs=0.05)
        assert pilot_center[:2] == pytest.approx(clearance_center[:2], abs=0.05)
        assert clearance_size[:2] == pytest.approx(
            [screw_spec.clearance_hole_loose, screw_spec.clearance_hole_loose]
        )
        assert clearance_size[0] < screw_spec.cylinder_head_diameter
        assert clearance_size[2] == pytest.approx(
            DEFAULTS["tb6600_stripboard_interface_housing_lid_thickness"] + 2
        )
        pilot_centers.append(pilot_center)
        clearance_centers.append(clearance_center)

    assert len({round(center[0], 2) for center in pilot_centers}) == 2
    assert len({round(center[1], 2) for center in pilot_centers}) == 2

    lid_screws = housing.get_named_non_production_part("lid_mount_screws")
    screw_center = get_bounding_box_center(lid_screws)
    centers_center = [
        sum(center[axis] for center in clearance_centers) / len(clearance_centers)
        for axis in range(3)
    ]
    assert screw_center[:2] == pytest.approx(centers_center[:2], abs=0.05)


def test_tb6600_stripboard_interface_housing_cable_tie_slots_cut_the_floor():
    housing = _build_housing()
    wall = DEFAULTS["tb6600_stripboard_interface_housing_wall_thickness"]

    for side_name in ["left", "right"]:
        for position_name in ["front", "back"]:
            slot = housing.get_cutter_part_by_name(
                f"cable_tie_slot_{side_name}_{position_name}"
            )
            slot_size = get_bounding_box_size(slot)
            slot_bbox = get_bounding_box(slot)

            assert slot_size[0] == pytest.approx(
                DEFAULTS["tb6600_stripboard_interface_housing_cable_tie_slot_length"]
            )
            assert slot_size[1] == pytest.approx(
                DEFAULTS["tb6600_stripboard_interface_housing_cable_tie_slot_width"]
            )
            assert slot_bbox[0][2] == pytest.approx(-1)
            assert slot_bbox[1][2] == pytest.approx(wall + 1)


def test_tb6600_stripboard_interface_housing_resource_uses_local_parameters_only():
    resource = _load_resource()
    parameter_names = set(resource["Parameters"])

    assert parameter_names
    assert all(name.startswith(TB6600_PREFIX) for name in parameter_names)

    resource_text = RESOURCE_FILE.read_text()
    forbidden = ("nitehawk", "hv_switchbox", "electric_switchboard")
    assert not any(fragment in resource_text for fragment in forbidden)

    entry = _tb6600_assembly_entry()
    assert entry["resource_file"] == "tb6600_stripboard_interface_housing_assembly.yaml"
    assert entry["depends_on"] == []
    assert set(entry["parameters"]) == parameter_names
    for key, value in entry["parameters"].items():
        assert key.startswith(TB6600_PREFIX)
        assert value == {"$ref": key}


def test_tb6600_stripboard_interface_housing_visualization_exports_only_real_parts():
    resource = _load_resource()
    visualization_parts = resource["Builder"]["Visualization"]["parts"]

    assert all(part["artifact"] != "cutters" for part in visualization_parts)

    visual_names = set()
    for part in visualization_parts:
        if "name" in part:
            visual_names.add(part["name"])
        visual_names.update(part.get("names", []))

    assert "mount_flange_screw" in visual_names
    assert "lid_mount_screws" in visual_names
    assert not any("thread_inset" in name for name in visual_names)

    hole_only_names = {
        "cable_exit",
        "cable_tie_slots",
        "mount_flange_screw_hole",
        "lid_mount_pilot_holes",
        "lid_mount_clearance_holes",
    }
    assert visual_names.isdisjoint(hole_only_names)


def test_tb6600_stripboard_interface_housing_production_plate_contains_body_and_lid():
    resource = _load_resource()
    production = resource["Builder"]["Production"]

    assert production["process_data_preset"] == "petgcf_max_strength_high_speed_06"
    assert "_idex" not in yaml.safe_dump(production)
    assert production["parts"] == [
        {
            "source": "self",
            "artifact": "leader",
            "name": "tb6600_stripboard_interface_housing",
        },
        {
            "source": "self",
            "artifact": "followers",
            "names": ["tb6600_stripboard_interface_housing_lid"],
            "name_template": "{name}",
            "prod_rotation_angle": 180,
            "prod_rotation_axis": [1, 0, 0],
        },
    ]
    assert production["arrange"]["auto_assign_plates"] is False
    assert production["arrange"]["plates"] == [
        {
            "name": "tb6600_stripboard_interface_housing",
            "process_data_preset": "petgcf_max_strength_high_speed_06",
            "process_data": {
                "overrides": {
                    "process_overrides": {
                        "brim_type": "no_brim",
                        "enable_support": "1",
                        "support_type": "tree(auto)",
                        "support_style": "organic",
                        "support_on_build_plate_only": "1",
                        "support_top_z_distance": "0.47",
                        "max_bridge_length": "0",
                        "bridge_no_support": "0",
                        "support_interface_top_layers": "2",
                        "support_interface_spacing": "0.8",
                        "support_object_xy_distance": "0.8",
                        "support_bottom_z_distance": "0.2",
                        "wall_loops": "3",
                    },
                },
            },
            "parts": [
                "tb6600_stripboard_interface_housing",
                "tb6600_stripboard_interface_housing_lid",
            ],
        }
    ]
