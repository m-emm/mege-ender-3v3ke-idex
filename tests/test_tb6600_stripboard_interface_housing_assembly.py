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
from shellforgepy.simple import get_bounding_box, get_bounding_box_center
from shellforgepy.simple import get_bounding_box_size, get_volume
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
    }
    expected_cutters.update(
        {f"lid_mount_screw_{index}_hole_cutter" for index in range(4)}
    )
    expected_cutters.update(
        {f"lid_mount_screw_{index}_cylinder_head_cutter" for index in range(4)}
    )
    assert expected_cutters <= set(housing.cutter_indices_by_name)

    expected_non_production = {"tb6600_stripboard_interface_housing_body_reference"}
    expected_non_production.update(
        {f"lid_mount_screw_{index}_screw" for index in range(4)}
    )
    expected_non_production.update(
        {f"lid_mount_screw_{index}_thread_inset" for index in range(4)}
    )
    expected_non_production.add("mount_flange_screw")
    assert set(housing.non_production_indices_by_name) == expected_non_production


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

    assert DEFAULTS["tb6600_stripboard_interface_housing_board_columns"] == 13
    assert DEFAULTS["tb6600_stripboard_interface_housing_board_rows"] == 9
    assert board_width == pytest.approx(33.02)
    assert board_depth == pytest.approx(22.86)
    assert body_size[2] - wall == pytest.approx(35.0)

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

    assert (
        DEFAULTS["tb6600_stripboard_interface_housing_mount_flange_screw_size"] == "M5"
    )
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


def test_tb6600_stripboard_interface_housing_lid_screws_use_hv_style_threaded_insets():
    housing = _build_housing()
    screw_spec = MScrew.from_size(
        DEFAULTS["tb6600_stripboard_interface_housing_lid_screw_size"]
    )
    inset_depth = (
        screw_spec.thread_inset_length
        + DEFAULTS[
            "tb6600_stripboard_interface_housing_lid_thread_inset_extra_screw_depth"
        ]
    )

    assert DEFAULTS["tb6600_stripboard_interface_housing_lid_screw_size"] == "M3"
    assert DEFAULTS[
        "tb6600_stripboard_interface_housing_lid_thread_inset_extra_screw_depth"
    ] == pytest.approx(4.0)

    for lid_screw_index in range(4):
        screw = housing.get_named_non_production_part(
            f"lid_mount_screw_{lid_screw_index}_screw"
        )
        hole = housing.get_named_cutter(
            f"lid_mount_screw_{lid_screw_index}_hole_cutter"
        )
        inset = housing.get_named_non_production_part(
            f"lid_mount_screw_{lid_screw_index}_thread_inset"
        )
        inset_cutter = housing.get_named_cutter(
            f"lid_mount_screw_{lid_screw_index}_assembly_cutter"
        )

        screw_center = get_bounding_box_center(screw)
        hole_center = get_bounding_box_center(hole)
        inset_center = get_bounding_box_center(inset)
        inset_size = get_bounding_box_size(inset)
        inset_cutter_size = get_bounding_box_size(inset_cutter)

        assert screw_center[:2] == pytest.approx(hole_center[:2], abs=0.05)
        assert inset_center[:2] == pytest.approx(hole_center[:2], abs=0.05)
        assert inset_size[2] == pytest.approx(
            screw_spec.thread_inset_length,
            abs=0.05,
        )
        assert inset_cutter_size[2] == pytest.approx(
            inset_depth,
            abs=0.05,
        )


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
    assert "lid_mount_screw_*_screw" in visual_names
    assert "lid_mount_screw_*_thread_inset" in visual_names

    hole_only_names = {
        "cable_exit",
        "cable_tie_slots",
        "mount_flange_screw_hole",
    }
    assert visual_names.isdisjoint(hole_only_names)


def test_tb6600_stripboard_interface_housing_production_plate_contains_body_and_lid():
    resource = _load_resource()
    production = resource["Builder"]["Production"]

    assert production["process_data_preset"] == "petgcf_max_strength_high_speed_06_idex"
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
            "process_data_preset": "petgcf_max_strength_high_speed_06_idex",
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
