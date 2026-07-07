import pytest
import yaml
from assembly_defaults import ASSEMBLIES_DIR, DEFAULTS, AssemblyDefaultsLoader
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_usb_board_assembly import (
    create_nitehawk_usb_board_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_usb_dual_board_housing_assembly import (
    create_nitehawk_usb_dual_board_housing_assembly,
)
from shellforgepy.geometry.m_screws import get_core_hole_diameter
from shellforgepy.simple import (
    MScrew,
    create_cylinder,
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_clearance_hole_diameter,
    get_volume,
    materialize_bounding_box,
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
    adjusted_core_radius = (
        get_core_hole_diameter("M3") / 2
        + DEFAULTS["nitehawk_usb_dual_housing_self_threading_core_radius_adjustment"]
    )

    assert size[1:] == pytest.approx([clearance, clearance])
    assert get_volume(cutter) < get_volume(create_cylinder(clearance / 2, size[0]))
    assert get_volume(cutter) > get_volume(
        create_cylinder(adjusted_core_radius, size[0])
    )


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
    screw = MScrew.from_size("M3")

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
        clearance_hole_size = get_bounding_box_size(
            housing.get_cutter_part_by_name(f"lid_mount_clearance_hole_{index}")
        )
        assert clearance_hole_size[0] == pytest.approx(
            DEFAULTS["nitehawk_usb_dual_housing_lid_thickness"] + 1
        )
        assert clearance_hole_size[1:] == pytest.approx(
            [screw.clearance_hole_loose, screw.clearance_hole_loose]
        )
        assert clearance_hole_size[1] < screw.cylinder_head_diameter


def test_nitehawk_usb_dual_board_housing_lid_pilot_lead_ins_start_at_boss_face():
    housing = _housing()
    body_bbox = get_bounding_box(
        housing.get_non_production_part_by_name(
            "nitehawk_usb_dual_housing_body_reference"
        )
    )
    boss_inset = DEFAULTS["nitehawk_usb_dual_housing_lid_screw_inset"]

    expected_centers = [
        (boss_inset, boss_inset),
        (boss_inset, body_bbox[1][2] - boss_inset),
        (body_bbox[1][1] - boss_inset, boss_inset),
        (body_bbox[1][1] - boss_inset, body_bbox[1][2] - boss_inset),
    ]

    for index, (expected_y, expected_z) in enumerate(expected_centers, start=1):
        pilot_hole = housing.get_cutter_part_by_name(f"lid_mount_pilot_hole_{index}")
        pilot_bbox = get_bounding_box(pilot_hole)
        pilot_center = get_bounding_box_center(pilot_hole)

        assert pilot_bbox[0][0] == pytest.approx(body_bbox[0][0])
        assert pilot_bbox[1][0] > body_bbox[1][0]
        assert pilot_center[1] == pytest.approx(expected_y)
        assert pilot_center[2] == pytest.approx(expected_z)


def test_nitehawk_usb_dual_board_housing_board_pilot_lead_ins_start_at_standoffs():
    housing = _housing()
    body_bbox = get_bounding_box(
        housing.get_non_production_part_by_name(
            "nitehawk_usb_dual_housing_body_reference"
        )
    )

    for board_index in [1, 2]:
        board_bbox = get_bounding_box(
            housing.get_non_production_part_by_name(f"board_{board_index}_board")
        )
        for hole_name in [
            "mounting_hole_front_left",
            "mounting_hole_front_right",
            "mounting_hole_back",
        ]:
            pilot_hole = housing.get_cutter_part_by_name(
                f"board_{board_index}_{hole_name}_pilot_hole"
            )
            pilot_bbox = get_bounding_box(pilot_hole)
            pilot_center = get_bounding_box_center(pilot_hole)

            assert pilot_bbox[0][0] == pytest.approx(board_bbox[1][0])
            assert pilot_bbox[1][0] > body_bbox[1][0]
            assert board_bbox[0][1] <= pilot_center[1] <= board_bbox[1][1]
            assert board_bbox[0][2] <= pilot_center[2] <= board_bbox[1][2]


def test_nitehawk_usb_dual_board_housing_defaults_are_roomy_for_boards_and_lid_bosses():
    screw = MScrew.from_size(DEFAULTS["nitehawk_usb_dual_housing_lid_screw_size"])

    assert (
        DEFAULTS["nitehawk_usb_dual_housing_lid_screw_boss_diameter"]
        - screw.clearance_hole_close
    ) / 2 >= 2


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


def test_nitehawk_usb_dual_board_housing_cable_windows_clear_lid_bosses():
    housing = _housing()
    body_bbox = get_bounding_box(
        housing.get_non_production_part_by_name(
            "nitehawk_usb_dual_housing_body_reference"
        )
    )
    wall = DEFAULTS["nitehawk_usb_dual_housing_wall_thickness"]
    boss_radius = DEFAULTS["nitehawk_usb_dual_housing_lid_screw_boss_diameter"] / 2
    boss_inset = DEFAULTS["nitehawk_usb_dual_housing_lid_screw_inset"]
    keepout_margin = 2.0

    front_boss_outer_y = body_bbox[0][1] + boss_inset + boss_radius
    rear_boss_outer_y = body_bbox[1][1] - boss_inset - boss_radius
    cable_slit_bbox = get_bounding_box(housing.get_cutter_part_by_name("cable_slit"))
    assert cable_slit_bbox[0][1] >= front_boss_outer_y + keepout_margin - 1e-6
    assert cable_slit_bbox[1][1] <= rear_boss_outer_y - keepout_margin + 1e-6

    front_pilot_bbox = get_bounding_box(
        housing.get_cutter_part_by_name("lid_mount_pilot_hole_1")
    )
    rear_pilot_bbox = get_bounding_box(
        housing.get_cutter_part_by_name("lid_mount_pilot_hole_3")
    )
    assert cable_slit_bbox[0][1] - front_pilot_bbox[1][1] >= keepout_margin - 1e-6
    assert rear_pilot_bbox[0][1] - cable_slit_bbox[1][1] >= keepout_margin - 1e-6

    lid_boss_keepouts = []
    for y in [boss_inset, body_bbox[1][1] - boss_inset]:
        for z in [boss_inset, body_bbox[1][2] - boss_inset]:
            lid_boss = create_cylinder(
                boss_radius,
                body_bbox[1][0] - wall,
                origin=(body_bbox[0][0], y, z),
                direction=(1, 0, 0),
            )
            lid_boss_keepouts.append(
                materialize_bounding_box(
                    lid_boss,
                    x_enlargement=2 * keepout_margin,
                    y_enlargement=2 * keepout_margin,
                    z_enlargement=2 * keepout_margin,
                )
            )

    for cutter_name in [
        "rear_connector_cable_slit_board_1",
        "rear_connector_cable_slit_board_2",
    ]:
        cutter = housing.get_cutter_part_by_name(cutter_name)
        cutter_volume = get_volume(cutter)
        for lid_boss_keepout in lid_boss_keepouts:
            assert get_volume(cutter.cut(lid_boss_keepout)) == pytest.approx(
                cutter_volume,
                abs=0.001,
            )


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
    assert housing_entry["parameters"][
        "nitehawk_usb_dual_housing_self_threading_core_radius_adjustment"
    ] == {"$ref": "nitehawk_usb_dual_housing_self_threading_core_radius_adjustment"}
    assert housing_entry["parameters"][
        "nitehawk_usb_dual_housing_self_threading_lead_in"
    ] == {"$ref": "nitehawk_usb_dual_housing_self_threading_lead_in"}

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

    assert production["process_data_preset"] == "petgcf_max_strength_high_speed_06"
    assert body["prod_rotation_angle"] == 90
    assert body["prod_rotation_axis"] == [0, 1, 0]
    assert lid["prod_rotation_angle"] == -90
    assert lid["prod_rotation_axis"] == [0, 1, 0]
    assert plates == [
        {
            "name": "nitehawk_usb_dual_board_housing",
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
                        "support_remove_small_overhang": "0",
                        "support_interface_top_layers": "2",
                        "support_interface_spacing": "0.8",
                        "support_object_xy_distance": "0.8",
                        "support_bottom_z_distance": "0.2",
                        "wall_loops": "3",
                    },
                },
            },
            "parts": [
                "nitehawk_usb_dual_board_housing",
                "nitehawk_usb_dual_housing_lid",
            ],
        }
    ]
    assert production["arrange"]["prod_gap"] == pytest.approx(12.0)
    assert production["arrange"]["auto_assign_plates"] is False


def test_nitehawk_usb_dual_board_housing_declares_screw_hole_prototype():
    resource = yaml.load(
        (ASSEMBLIES_DIR / "nitehawk_usb_dual_board_housing_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    prototype = resource["Builder"]["Production"]["prototype"]

    assert prototype["process_data_preset"] == "petgcf_medium_strength_high_speed_06"
    assert prototype["include_parts"] == ["nitehawk_usb_dual_board_housing"]
    assert prototype["box_cutters"] == [
        {
            "part": "nitehawk_usb_dual_board_housing",
            "around": "self.cutters.board_1_mounting_hole_front_left_pilot_hole",
            "size": [10, 31, 12],
            "offset": [0, 11.8, 0],
        }
    ]
    assert prototype["arrange"]["plates"] == [
        {
            "name": "nitehawk_usb_dual_board_housing_screw_hole_prototype",
            "filename": "nitehawk_usb_dual_screw_hole_proto",
            "parts": ["nitehawk_usb_dual_board_housing"],
        }
    ]
    assert prototype["arrange"]["auto_assign_plates"] is False
