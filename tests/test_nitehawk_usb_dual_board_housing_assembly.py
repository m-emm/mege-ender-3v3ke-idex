import pytest
import yaml

from assembly_defaults import ASSEMBLIES_DIR, DEFAULTS, AssemblyDefaultsLoader
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_usb_board_assembly import (
    create_nitehawk_usb_board_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_usb_dual_board_housing_assembly import (
    create_nitehawk_usb_dual_board_housing_assembly,
)
from shellforgepy.simple import (
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_clearance_hole_diameter,
    get_volume,
)


def _board():
    board_kwargs = {
        name: DEFAULTS[name]
        for name in DEFAULTS
        if name.startswith("nitehawk_usb_")
        and not name.startswith("nitehawk_usb_dual_housing_")
    }
    return create_nitehawk_usb_board_assembly(**board_kwargs)


def _housing():
    housing_kwargs = {
        name: DEFAULTS[name]
        for name in DEFAULTS
        if name.startswith("nitehawk_usb_dual_housing_")
    }
    return create_nitehawk_usb_dual_board_housing_assembly(
        nitehawk_usb_board=_board(),
        **housing_kwargs,
    )


def _combined_bbox(parts):
    bboxes = [get_bounding_box(part) for part in parts]
    return (
        tuple(min(bbox[0][axis] for bbox in bboxes) for axis in range(3)),
        tuple(max(bbox[1][axis] for bbox in bboxes) for axis in range(3)),
    )


def _assert_m3_self_threading_x_cutter(cutter):
    size = get_bounding_box_size(cutter)
    clearance = get_clearance_hole_diameter("M3", "close")

    assert size[2] == pytest.approx(clearance)
    assert size[1] < clearance
    assert size[1] > clearance * 0.9


def test_nitehawk_usb_dual_board_housing_exposes_stable_artifacts():
    housing = _housing()

    assert get_volume(housing.leader) > 0
    assert "nitehawk_usb_dual_housing_lid" in housing.follower_indices_by_name

    for name in [
        "board_1_board",
        "board_1_terminal_block",
        "board_1_usb_c_connector",
        "board_1_front_plug",
        "board_1_white_connector",
        "board_2_board",
        "board_2_terminal_block",
        "board_2_usb_c_connector",
        "board_2_front_plug",
        "board_2_white_connector",
        "board_mount_screws",
        "lid_mount_screws",
        "profile_mount_screws",
        "profile_mount_reference",
    ]:
        assert name in housing.non_production_indices_by_name

    for name in [
        "board_1_mounting_hole_front_left_pilot_hole",
        "board_1_mounting_hole_front_right_pilot_hole",
        "board_1_mounting_hole_back_pilot_hole",
        "board_2_mounting_hole_front_left_pilot_hole",
        "board_2_mounting_hole_front_right_pilot_hole",
        "board_2_mounting_hole_back_pilot_hole",
        "cable_slit",
        "rear_connector_cable_slits",
        "rear_connector_cable_slit_board_1",
        "rear_connector_cable_slit_board_2",
        "cable_tie_slot_board_1_front",
        "cable_tie_slot_board_1_back",
        "cable_tie_slot_board_2_front",
        "cable_tie_slot_board_2_back",
        "profile_mount_hole_bottom",
        "profile_mount_hole_top",
    ]:
        assert name in housing.cutter_indices_by_name


def test_nitehawk_usb_dual_board_housing_uses_self_threading_screw_holes():
    housing = _housing()

    for board_index in [1, 2]:
        for hole_name in [
            "mounting_hole_front_left",
            "mounting_hole_front_right",
            "mounting_hole_back",
        ]:
            _assert_m3_self_threading_x_cutter(
                housing.get_cutter_part_by_name(
                    f"board_{board_index}_{hole_name}_pilot_hole"
                )
            )

    for index in range(1, 5):
        _assert_m3_self_threading_x_cutter(
            housing.get_cutter_part_by_name(f"lid_mount_pilot_hole_{index}")
        )


def test_nitehawk_usb_dual_board_housing_lid_does_not_cut_body():
    housing = _housing()
    bottom_box = housing.leader
    lid = housing.get_follower_part_by_name("nitehawk_usb_dual_housing_lid")

    bottom_box_volume = get_volume(bottom_box)

    assert get_volume(bottom_box.cut(lid)) == pytest.approx(
        bottom_box_volume,
        abs=0.001,
    )


def test_nitehawk_usb_dual_board_housing_places_two_boards_side_by_side():
    housing = _housing()

    board_1_center = get_bounding_box_center(
        housing.get_non_production_part_by_name("board_1_board")
    )
    board_2_center = get_bounding_box_center(
        housing.get_non_production_part_by_name("board_2_board")
    )

    expected_y_offset = (
        DEFAULTS["nitehawk_usb_board_length"]
        + DEFAULTS["nitehawk_usb_dual_housing_board_gap"]
    )
    assert board_2_center[1] - board_1_center[1] == pytest.approx(expected_y_offset)
    assert board_2_center[0] == pytest.approx(board_1_center[0])
    assert board_2_center[2] == pytest.approx(board_1_center[2])


def test_nitehawk_usb_dual_board_housing_keeps_breathing_room():
    housing = _housing()
    body_bbox = get_bounding_box(
        housing.get_non_production_part_by_name(
            "nitehawk_usb_dual_housing_body_reference"
        )
    )
    board_1_bbox = _combined_bbox(
        [
            housing.get_non_production_part_by_name(name)
            for name in [
                "board_1_board",
                "board_1_terminal_block",
                "board_1_usb_c_connector",
                "board_1_front_plug",
                "board_1_white_connector",
            ]
        ]
    )
    board_2_bbox = _combined_bbox(
        [
            housing.get_non_production_part_by_name(name)
            for name in [
                "board_2_board",
                "board_2_terminal_block",
                "board_2_usb_c_connector",
                "board_2_front_plug",
                "board_2_white_connector",
            ]
        ]
    )

    wall = DEFAULTS["nitehawk_usb_dual_housing_wall_thickness"]
    assert board_1_bbox[0][1] - (body_bbox[0][1] + wall) == pytest.approx(
        DEFAULTS["nitehawk_usb_dual_housing_board_side_margin"]
    )
    assert board_2_bbox[0][1] - board_1_bbox[1][1] == pytest.approx(
        DEFAULTS["nitehawk_usb_dual_housing_board_gap"]
    )
    assert body_bbox[1][1] - wall - board_2_bbox[1][1] == pytest.approx(
        DEFAULTS["nitehawk_usb_dual_housing_board_side_margin"]
    )
    assert board_1_bbox[0][2] - (body_bbox[0][2] + wall) == pytest.approx(
        DEFAULTS["nitehawk_usb_dual_housing_board_bottom_margin"]
    )
    assert body_bbox[1][2] - wall - board_1_bbox[1][2] == pytest.approx(
        DEFAULTS["nitehawk_usb_dual_housing_board_top_margin"]
    )


def test_nitehawk_usb_dual_board_housing_encloses_board_visuals():
    housing = _housing()
    housing_bbox = get_bounding_box(housing.leader)

    board_visual_names = [
        "board_1_board",
        "board_1_terminal_block",
        "board_1_usb_c_connector",
        "board_1_front_plug",
        "board_1_white_connector",
        "board_2_board",
        "board_2_terminal_block",
        "board_2_usb_c_connector",
        "board_2_front_plug",
        "board_2_white_connector",
    ]
    for name in board_visual_names:
        board_part_bbox = get_bounding_box(
            housing.get_non_production_part_by_name(name)
        )
        for axis in range(3):
            assert board_part_bbox[0][axis] >= housing_bbox[0][axis] - 1e-6
            assert board_part_bbox[1][axis] <= housing_bbox[1][axis] + 1e-6


def test_nitehawk_usb_dual_board_housing_cable_slits_are_deep_and_aligned():
    housing = _housing()
    body_bbox = get_bounding_box(
        housing.get_non_production_part_by_name(
            "nitehawk_usb_dual_housing_body_reference"
        )
    )
    wall = DEFAULTS["nitehawk_usb_dual_housing_wall_thickness"]
    slit_start_x = (
        DEFAULTS["nitehawk_usb_dual_housing_lid_rim_depth"]
        + DEFAULTS["nitehawk_usb_dual_housing_lid_body_clearance"]
    )
    slit_end_x = (
        body_bbox[1][0]
        - wall
        - DEFAULTS["nitehawk_usb_dual_housing_cable_slit_floor_clearance"]
    )

    cable_slit_bbox = get_bounding_box(housing.get_cutter_part_by_name("cable_slit"))
    assert cable_slit_bbox[0][0] == pytest.approx(slit_start_x)
    assert cable_slit_bbox[1][0] == pytest.approx(slit_end_x)
    assert cable_slit_bbox[0][2] < body_bbox[0][2]
    assert cable_slit_bbox[1][2] >= (
        DEFAULTS["nitehawk_usb_dual_housing_cable_slit_z_size"] - 1
    )

    for index in [1, 2]:
        connector_bbox = get_bounding_box(
            housing.get_non_production_part_by_name(f"board_{index}_front_plug")
        )
        slit_bbox = get_bounding_box(
            housing.get_cutter_part_by_name(f"rear_connector_cable_slit_board_{index}")
        )
        assert slit_bbox[0][0] == pytest.approx(slit_start_x)
        assert slit_bbox[1][0] == pytest.approx(slit_end_x)
        assert slit_bbox[0][1] <= (
            connector_bbox[0][1]
            - DEFAULTS["nitehawk_usb_dual_housing_rear_connector_slit_y_margin"]
            + 1e-6
        )
        assert slit_bbox[1][1] >= (
            connector_bbox[1][1]
            + DEFAULTS["nitehawk_usb_dual_housing_rear_connector_slit_y_margin"]
            - 1e-6
        )
        assert slit_bbox[0][2] < body_bbox[1][2]
        assert slit_bbox[1][2] > body_bbox[1][2] - wall


def test_nitehawk_usb_dual_board_housing_profile_mount_holes_are_vertical_pair():
    housing = _housing()

    bottom = get_bounding_box_center(
        housing.get_cutter_part_by_name("profile_mount_hole_bottom")
    )
    top = get_bounding_box_center(
        housing.get_cutter_part_by_name("profile_mount_hole_top")
    )

    assert top[0] == pytest.approx(bottom[0])
    assert top[1] == pytest.approx(bottom[1])
    assert top[2] - bottom[2] == pytest.approx(
        DEFAULTS["nitehawk_usb_dual_housing_profile_mount_hole_spacing"]
    )


def test_nitehawk_usb_dual_board_housing_has_no_external_profile_mount_boss():
    housing = _housing()
    body_reference_bbox = get_bounding_box(
        housing.get_non_production_part_by_name(
            "nitehawk_usb_dual_housing_body_reference"
        )
    )
    housing_bbox = get_bounding_box(housing.leader)
    profile_mount_reference_bbox = get_bounding_box(
        housing.get_non_production_part_by_name("profile_mount_reference")
    )

    assert housing_bbox[1][0] == pytest.approx(body_reference_bbox[1][0])
    assert profile_mount_reference_bbox[1][0] == pytest.approx(
        body_reference_bbox[1][0]
    )


def test_nitehawk_usb_dual_board_housing_slots_stay_on_backplate():
    housing = _housing()
    board_1 = get_bounding_box(housing.get_non_production_part_by_name("board_1_board"))
    board_2 = get_bounding_box(housing.get_non_production_part_by_name("board_2_board"))

    for name, board_bbox in [
        ("cable_tie_slot_board_1_front", board_1),
        ("cable_tie_slot_board_1_back", board_1),
        ("cable_tie_slot_board_2_front", board_2),
        ("cable_tie_slot_board_2_back", board_2),
    ]:
        slot_bbox = get_bounding_box(housing.get_cutter_part_by_name(name))
        assert slot_bbox[0][0] > board_bbox[1][0]
        assert slot_bbox[0][2] > DEFAULTS["nitehawk_usb_dual_housing_wall_thickness"]

    assert not any(
        name.startswith(("board_1_", "board_2_")) and "clearance" in name
        for name in housing.cutter_indices_by_name.keys()
    )


def test_nitehawk_usb_dual_board_housing_yaml_and_whole_printer_wiring():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    housing_entry = assemblies["nitehawk_usb_dual_board_housing_assembly"]
    assert housing_entry["resource_file"] == (
        "nitehawk_usb_dual_board_housing_assembly.yaml"
    )
    assert housing_entry["depends_on"] == ["nitehawk_usb_board_assembly"]
    assert housing_entry["inject_parts"] == {
        "nitehawk_usb_board": "nitehawk_usb_board_assembly"
    }

    whole_printer = assemblies["whole_printer_assembly"]
    assert "nitehawk_usb_dual_board_housing_assembly" in whole_printer["depends_on"]
    assert whole_printer["inject_parts"]["nitehawk_usb_dual_board_housing"] == (
        "nitehawk_usb_dual_board_housing_assembly"
    )

    placements = config["placement"]["alignments"]
    assert {
        "part": (
            "nitehawk_usb_dual_board_housing_assembly.non_production_parts."
            "profile_mount_reference"
        ),
        "to": "z_axis_profile_left_assembly",
        "alignment": "STACK_LEFT",
    } in placements
    assert any(
        placement.get("rigid_group")
        and "nitehawk_usb_dual_board_housing_assembly" in placement["rigid_group"]
        and placement.get("to") == "x_axis_rail_assembly"
        for placement in placements
    )

    whole_printer_resource = yaml.load(
        (ASSEMBLIES_DIR / "whole_printer_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    visualization_parts = whole_printer_resource["Builder"]["Visualization"]["parts"]
    assert any(
        part.get("assembly") == "nitehawk_usb_dual_board_housing"
        and part.get("artifact") == "leader"
        for part in visualization_parts
    )


def test_nitehawk_usb_dual_board_housing_production_prints_on_one_plate():
    resource = yaml.load(
        (ASSEMBLIES_DIR / "nitehawk_usb_dual_board_housing_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    production = resource["Builder"]["Production"]
    production_parts = production["parts"]

    body = next(part for part in production_parts if part.get("artifact") == "leader")
    lid = next(part for part in production_parts if part.get("artifact") == "followers")
    plates = production["arrange"]["plates"]

    assert body["prod_rotation_angle"] == 90
    assert body["prod_rotation_axis"] == [0, 1, 0]
    assert lid["prod_rotation_angle"] == -90
    assert lid["prod_rotation_axis"] == [0, 1, 0]
    assert plates == [
        {
            "name": "nitehawk_usb_dual_board_housing",
            "parts": [
                "nitehawk_usb_dual_board_housing",
                "nitehawk_usb_dual_housing_lid",
            ],
        }
    ]
    assert production["arrange"]["auto_assign_plates"] is False
