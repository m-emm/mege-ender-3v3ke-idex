import inspect

import pytest
import yaml
from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.extruder_cage_assembly import (
    create_extruder_cage_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_board_assembly import (
    create_nitehawk_board_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.sprite_extruder_assembly import (
    create_sprite_extruder_assembly,
)
from shellforgepy.simple import (
    Alignment,
    align,
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
    rotate,
    translate,
)


REMOVED_CAGE_PARAMETERS = [
    "tool_head_mount_base_plate_thickness",
    "tool_head_additional_mount_plate_fillet_radius",
    "tool_head_additional_mount_plate_thickness",
    "tool_head_front_mount_plate_connector_thickness",
    "duct_front_mount_plate_thickness",
    "duct_front_mount_plate_width",
    "holder_mount_plate_thickness",
    "tool_head_front_mount_plate_connector_height",
    "tool_head_front_mount_plate_connector_width",
    "holder_mount_plate_top_offset",
    "nitehawk_holder_extruder_gap",
    "tool_head_additional_mount_plate_depth_offset",
    "tool_head_additional_mount_plate_height",
    "tool_head_additional_mount_plate_z_offset",
    "holder_mount_plate_depth",
    "holder_mount_plate_size",
]


def _recut_delta(part, cutter):
    return get_volume(part) - get_volume(part.cut(cutter))


def _place_nitehawk_board_like_graph(nitehawk_board, sprite_extruder):
    nitehawk_board = rotate(-90, axis=(1, 0, 0))(nitehawk_board)
    nitehawk_board = rotate(180, axis=(0, 1, 0))(nitehawk_board)
    nitehawk_board = align(nitehawk_board, sprite_extruder, Alignment.LEFT)
    nitehawk_board = align(
        nitehawk_board,
        sprite_extruder,
        Alignment.STACK_BACK,
        stack_gap=DEFAULTS["nitehawk_board_extruder_back_gap"],
    )
    nitehawk_board = align(nitehawk_board, sprite_extruder, Alignment.BOTTOM)
    return translate(
        0,
        0,
        DEFAULTS["nitehawk_board_extruder_body_bottom_offset"],
    )(nitehawk_board)


def test_extruder_cage_signature_uses_cage_owned_mount_dimensions():
    parameters = inspect.signature(create_extruder_cage_assembly).parameters

    assert "nitehawk_board" in parameters
    assert "tool_head_mount_machined" not in parameters
    assert "carriage" not in parameters
    assert "extruder_cage_mount_plate_fillet_radius" in parameters
    assert "extruder_cage_top_right_bridge_clearance" in parameters
    for parameter_name in REMOVED_CAGE_PARAMETERS:
        assert parameter_name not in parameters


def test_extruder_cage_exposes_mounting_interfaces_and_screw_visuals():
    sprite_extruder = create_sprite_extruder_assembly(
        **assembly_kwargs(create_sprite_extruder_assembly)
    )
    nitehawk_board = create_nitehawk_board_assembly(
        **assembly_kwargs(create_nitehawk_board_assembly)
    )
    nitehawk_board = _place_nitehawk_board_like_graph(nitehawk_board, sprite_extruder)
    cage_kwargs = assembly_kwargs(
        create_extruder_cage_assembly,
        sprite_extruder=sprite_extruder,
        nitehawk_board=nitehawk_board,
    )

    cage = create_extruder_cage_assembly(**cage_kwargs)

    assert get_volume(cage.leader) > 0
    assert "left_mount_plate" not in cage.follower_indices_by_name
    assert "right_mount_plate" not in cage.follower_indices_by_name

    for follower_name in [
        "sprite_mount_base_plate",
        "part_fan_side_mount_plate",
        "part_fan_front_mount_plate",
        "nitehawk_rear_mount_plate",
    ]:
        cage.get_follower_part_by_name(follower_name)

    for screw_name in [
        "sprite_mount_screw_left",
        "sprite_mount_screw_right",
        "nitehawk_mount_screw_0",
        "nitehawk_mount_screw_1",
    ]:
        cage.get_non_production_part_by_name(screw_name)

    mount_plate_thickness = cage_kwargs["extruder_cage_mount_plate_thickness"]
    sprite_extruder_body_size = get_bounding_box_size(sprite_extruder.leader)
    sprite_mount_base_plate_size = get_bounding_box_size(
        cage.get_follower_part_by_name("sprite_mount_base_plate")
    )
    side_mount_plate_size = get_bounding_box_size(
        cage.get_follower_part_by_name("part_fan_side_mount_plate")
    )
    front_mount_plate_size = get_bounding_box_size(
        cage.get_follower_part_by_name("part_fan_front_mount_plate")
    )

    assert sprite_mount_base_plate_size[1] == pytest.approx(mount_plate_thickness)
    assert side_mount_plate_size[0] == pytest.approx(mount_plate_thickness)
    assert front_mount_plate_size[0] == pytest.approx(sprite_extruder_body_size[0])
    assert front_mount_plate_size[1] == pytest.approx(mount_plate_thickness)

    nitehawk_hole_0_center = get_bounding_box_center(
        cage.get_named_cutter("nitehawk_mount_hole_0")
    )
    nitehawk_hole_1_center = get_bounding_box_center(
        cage.get_named_cutter("nitehawk_mount_hole_1")
    )
    nitehawk_mount_plate_center = get_bounding_box_center(
        cage.get_follower_part_by_name("nitehawk_rear_mount_plate")
    )
    nitehawk_mount_plate_bbox = get_bounding_box(
        cage.get_follower_part_by_name("nitehawk_rear_mount_plate")
    )
    nitehawk_pcb_bbox = get_bounding_box(nitehawk_board.get_named_follower("pcb"))
    nitehawk_board_holes = sorted(
        [
            nitehawk_board.get_named_cutter("hole_1"),
            nitehawk_board.get_named_cutter("hole_2"),
        ],
        key=lambda hole: get_bounding_box_center(hole)[0],
    )
    nitehawk_board_hole_centers = [
        get_bounding_box_center(hole) for hole in nitehawk_board_holes
    ]

    assert nitehawk_hole_0_center[0] < nitehawk_hole_1_center[0]
    assert nitehawk_hole_1_center[0] - nitehawk_hole_0_center[0] == pytest.approx(
        cage_kwargs["nitehawk_holes_center_distance"]
    )
    assert (nitehawk_hole_0_center[0] + nitehawk_hole_1_center[0]) / 2 == pytest.approx(
        nitehawk_mount_plate_center[0]
    )
    for cage_hole_center, board_hole_center in zip(
        [nitehawk_hole_0_center, nitehawk_hole_1_center],
        nitehawk_board_hole_centers,
    ):
        assert cage_hole_center[0] == pytest.approx(board_hole_center[0])
        assert cage_hole_center[2] == pytest.approx(board_hole_center[2])
    assert nitehawk_mount_plate_bbox[1][1] == pytest.approx(nitehawk_pcb_bbox[0][1])

    board_translation = (3, 4, 2)
    shifted_nitehawk_board = translate(*board_translation)(nitehawk_board)
    shifted_cage = create_extruder_cage_assembly(
        **assembly_kwargs(
            create_extruder_cage_assembly,
            sprite_extruder=sprite_extruder,
            nitehawk_board=shifted_nitehawk_board,
        )
    )
    shifted_mount_plate_center = get_bounding_box_center(
        shifted_cage.get_follower_part_by_name("nitehawk_rear_mount_plate")
    )
    shifted_hole_0_center = get_bounding_box_center(
        shifted_cage.get_named_cutter("nitehawk_mount_hole_0")
    )
    for axis in [0, 1]:
        assert shifted_mount_plate_center[axis] - nitehawk_mount_plate_center[
            axis
        ] == pytest.approx(board_translation[axis])
    for axis in [0, 2]:
        assert shifted_hole_0_center[axis] - nitehawk_hole_0_center[
            axis
        ] == pytest.approx(board_translation[axis])

    for cutter_name in [
        "mount_hole_cutter",
        "nitehawk_mount_hole_0",
        "nitehawk_mount_hole_1",
        "nitehawk_mount_nut_pocket_0",
        "nitehawk_mount_nut_pocket_1",
    ]:
        recut_delta = _recut_delta(cage.leader, cage.get_named_cutter(cutter_name))
        assert recut_delta < 0.01


def test_extruder_cage_side_variants_use_visualization_dependencies_only():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    right_cage_resource = yaml.load(
        (ASSEMBLIES_DIR / "extruder_cage_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    left_cage_resource = yaml.load(
        (ASSEMBLIES_DIR / "extruder_cage_left_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )

    assert assemblies["nitehawk_board_left_assembly"]["resource_file"] == (
        "nitehawk_board_assembly.yaml"
    )
    assert assemblies["nitehawk_board_right_assembly"]["resource_file"] == (
        "nitehawk_board_assembly.yaml"
    )

    expected_true_inputs = {
        "left": {
            "sprite_extruder": "sprite_extruder_left_assembly",
            "nitehawk_board": "nitehawk_board_left_assembly",
        },
        "right": {
            "sprite_extruder": "sprite_extruder_right_assembly",
            "nitehawk_board": "nitehawk_board_right_assembly",
        },
    }
    expected_visual_context = {
        "left": {
            "resource": left_cage_resource,
            "resource_file": "extruder_cage_left_assembly.yaml",
            "tool_head_mount_machined": "tool_head_mount_machined_bottom_assembly",
            "carriage": "x_axis_left_carriage_assembly",
        },
        "right": {
            "resource": right_cage_resource,
            "resource_file": "extruder_cage_assembly.yaml",
            "tool_head_mount_machined": "tool_head_mount_machined_top_assembly",
            "carriage": "x_axis_right_carriage_assembly",
        },
    }

    assert assemblies["extruder_cage_assembly"]["inject_parts"] == {
        "sprite_extruder": "sprite_extruder_assembly",
        "nitehawk_board": "nitehawk_board_assembly",
    }
    assert set(assemblies["extruder_cage_assembly"]["depends_on"]) == {
        "sprite_extruder_assembly",
        "nitehawk_board_assembly",
    }

    for side, injected_context in expected_true_inputs.items():
        cage_entry = assemblies[f"extruder_cage_{side}_assembly"]
        visual_context = expected_visual_context[side]

        assert cage_entry["resource_file"] == visual_context["resource_file"]
        assert cage_entry["inject_parts"] == injected_context
        assert set(cage_entry["depends_on"]) == set(injected_context.values())
        assert not set(cage_entry["depends_on"]) & {
            visual_context["tool_head_mount_machined"],
            visual_context["carriage"],
            "x_axis_rail_assembly",
            "x_axis_lower_profile_assembly",
            "x_axis_top_profile_assembly",
        }

        visualization_parts = visual_context["resource"]["Builder"]["Visualization"][
            "parts"
        ]
        assert not any(
            rule.get("source") == "injected"
            and rule.get("assembly") in {"tool_head_mount_machined", "carriage"}
            for rule in visualization_parts
        )
        for dependency_assembly, visual_name in [
            (visual_context["tool_head_mount_machined"], "tool_head_mount_machined"),
            (visual_context["carriage"], "carriage"),
            ("x_axis_rail_assembly", "rail"),
            ("x_axis_lower_profile_assembly", "lower_axis_profile"),
            ("x_axis_top_profile_assembly", "top_axis_profile"),
        ]:
            assert {
                "source": "dependencies",
                "assembly": dependency_assembly,
                "artifact": "leader",
                "name": visual_name,
            } in visualization_parts

    placements = config["placement"]["alignments"]
    assemblies_yaml_text = (ASSEMBLIES_DIR / "assemblies.yaml").read_text()

    assert "x_axis_sprite_extruder_carriage_x_offset" not in DEFAULTS
    assert "x_axis_sprite_extruder_carriage_x_offset" not in assemblies_yaml_text
    assert DEFAULTS["x_axis_left_sprite_extruder_carriage_x_offset"] == pytest.approx(
        -21.1
    )
    assert DEFAULTS["x_axis_right_sprite_extruder_carriage_x_offset"] == pytest.approx(
        18
    )

    expected_sprite_x_offsets = {
        "sprite_extruder_left_assembly": "x_axis_left_sprite_extruder_carriage_x_offset",
        "sprite_extruder_right_assembly": "x_axis_right_sprite_extruder_carriage_x_offset",
    }
    for sprite_extruder, offset_parameter in expected_sprite_x_offsets.items():
        right_alignment = next(
            placement
            for placement in placements
            if placement.get("part") == sprite_extruder
            and placement.get("alignment") == "RIGHT"
        )
        assert right_alignment["post_translation"][0] == {"$ref": offset_parameter}

    for side, injected_context in expected_true_inputs.items():
        visual_context = expected_visual_context[side]
        machined_mount = visual_context["tool_head_mount_machined"]
        sprite_extruder = injected_context["sprite_extruder"]
        carriage = visual_context["carriage"]
        cage = f"extruder_cage_{side}_assembly"
        board = injected_context["nitehawk_board"]

        machined_group_indices = [
            index
            for index, placement in enumerate(placements)
            if machined_mount in placement.get("rigid_group", [])
        ]
        assert len(machined_group_indices) == 1
        machined_group_index = machined_group_indices[0]
        machined_group = placements[machined_group_index]
        assert machined_group["to"] == carriage
        assert machined_group["to"] not in {
            sprite_extruder,
            "x_axis_rail_assembly",
        }

        sprite_rail_alignment_index = next(
            index
            for index, placement in enumerate(placements)
            if placement.get("part") == sprite_extruder
            and placement.get("to") == "x_axis_rail_assembly"
            and placement.get("alignment") == "TOP"
        )
        assert machined_group_index > sprite_rail_alignment_index

        early_sprite_group = next(
            placement
            for index, placement in enumerate(placements)
            if index < machined_group_index
            and placement.get("to") == sprite_extruder
            and board in placement.get("rigid_group", [])
        )
        assert cage in early_sprite_group["rigid_group"]

        cage_group_indices = [
            index
            for index, placement in enumerate(placements)
            if placement.get("to") == sprite_extruder
            and cage in placement.get("rigid_group", [])
        ]
        assert cage_group_indices == [
            placements.index(early_sprite_group),
        ]

    for side in ["left", "right"]:
        board = f"nitehawk_board_{side}_assembly"
        sprite_extruder = f"sprite_extruder_{side}_assembly"

        left_alignment = next(
            placement
            for placement in placements
            if placement.get("part") == board and placement.get("alignment") == "LEFT"
        )
        assert left_alignment["to"] == sprite_extruder

        back_alignment = next(
            placement
            for placement in placements
            if placement.get("part") == board
            and placement.get("alignment") == "STACK_BACK"
        )
        assert back_alignment["to"] == sprite_extruder
        assert back_alignment["stack_gap"] == {
            "$ref": "nitehawk_board_extruder_back_gap"
        }

        bottom_alignment = next(
            placement
            for placement in placements
            if placement.get("part") == board and placement.get("alignment") == "BOTTOM"
        )
        assert bottom_alignment["to"] == sprite_extruder
        assert bottom_alignment["post_translation"][2] == {
            "$ref": "nitehawk_board_extruder_body_bottom_offset"
        }


def test_tool_head_mount_machined_assemblies_use_side_drive_context_without_belts():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    expected_context = {
        "tool_head_mount_machined_bottom_assembly": {
            "carriage": "x_axis_left_carriage_assembly",
            "sprite_extruder": "sprite_extruder_left_assembly",
            "drive_position": "bottom",
            "dependencies": {
                "x_axis_lower_profile_assembly",
                "x_axis_rail_assembly",
                "x_axis_left_carriage_assembly",
                "sprite_extruder_left_assembly",
            },
        },
        "tool_head_mount_machined_top_assembly": {
            "carriage": "x_axis_right_carriage_assembly",
            "sprite_extruder": "sprite_extruder_right_assembly",
            "drive_position": "top",
            "dependencies": {
                "x_axis_rail_assembly",
                "x_axis_right_carriage_assembly",
                "sprite_extruder_right_assembly",
            },
        },
    }

    for assembly_name, expected in expected_context.items():
        mount = assemblies[assembly_name]

        assert mount["resource_file"] == "tool_head_mount_machined_assembly.yaml"
        assert mount["inject_parts"] == {
            "carriage": expected["carriage"],
            "sprite_extruder": expected["sprite_extruder"],
        }
        assert "x_axis_belt_carriage" not in mount["inject_parts"]
        assert not any(
            "x_axis_belt_carriage" in dependency
            for dependency in mount.get("depends_on", [])
        )
        assert mount["parameters"] == {"drive_position": expected["drive_position"]}
        assert set(mount["depends_on"]).issuperset(expected["dependencies"])
