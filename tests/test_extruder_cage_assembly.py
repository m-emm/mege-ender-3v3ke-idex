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
from shellforgepy.builder import graph_model as builder_graph_model
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
    "tool_head_back_mount_plate_connector_thickness",
    "duct_back_mount_plate_thickness",
    "duct_back_mount_plate_width",
    "holder_mount_plate_thickness",
    "tool_head_back_mount_plate_connector_height",
    "tool_head_back_mount_plate_connector_width",
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
    nitehawk_board = rotate(180, axis=(0, 0, 1))(nitehawk_board)
    nitehawk_board = align(nitehawk_board, sprite_extruder, Alignment.LEFT)
    nitehawk_board = align(
        nitehawk_board,
        sprite_extruder,
        Alignment.STACK_FRONT,
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
    assert "tool_head_mount_machined" in parameters
    assert parameters["tool_head_mount_machined"].default is None
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
    sprite_extruder_bbox = get_bounding_box(sprite_extruder)
    sprite_extruder_center = get_bounding_box_center(sprite_extruder.leader)
    hotend_center = get_bounding_box_center(
        sprite_extruder.get_named_non_production_part("hotend")
    )
    lever_center = get_bounding_box_center(
        sprite_extruder.get_named_non_production_part("lever")
    )
    built_in_fan_center = get_bounding_box_center(
        sprite_extruder.get_named_non_production_part("fan")
    )
    sprite_extruder_body_size = get_bounding_box_size(sprite_extruder.leader)
    sprite_mount_base_plate = cage.get_follower_part_by_name("sprite_mount_base_plate")
    side_mount_plate = cage.get_follower_part_by_name("part_fan_side_mount_plate")
    front_mount_plate = cage.get_follower_part_by_name("part_fan_front_mount_plate")
    sprite_mount_base_plate_size = get_bounding_box_size(sprite_mount_base_plate)
    side_mount_plate_size = get_bounding_box_size(side_mount_plate)
    front_mount_plate_size = get_bounding_box_size(front_mount_plate)
    side_mount_plate_bbox = get_bounding_box(side_mount_plate)
    front_mount_plate_bbox = get_bounding_box(front_mount_plate)

    assert sprite_mount_base_plate_size[1] == pytest.approx(mount_plate_thickness)
    assert side_mount_plate_size[0] == pytest.approx(mount_plate_thickness)
    assert front_mount_plate_size[0] == pytest.approx(sprite_extruder_body_size[0])
    assert front_mount_plate_size[1] == pytest.approx(mount_plate_thickness)
    assert hotend_center[0] < sprite_extruder_center[0]
    assert hotend_center[1] > sprite_extruder_center[1]
    assert lever_center[0] < sprite_extruder_center[0]
    assert lever_center[1] > sprite_extruder_center[1]
    assert built_in_fan_center[0] < sprite_extruder_center[0]
    assert built_in_fan_center[1] > sprite_extruder_center[1]
    assert side_mount_plate_bbox[0][0] >= sprite_extruder_bbox[1][0] - 1e-6
    assert side_mount_plate_bbox[1][1] <= sprite_extruder_center[1] + 1e-6
    assert front_mount_plate_bbox[1][1] <= sprite_extruder_bbox[0][1] + 1e-6

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
    assert nitehawk_mount_plate_bbox[1][1] <= sprite_extruder_bbox[0][1] + 1e-6
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
    assert nitehawk_mount_plate_bbox[0][1] == pytest.approx(nitehawk_pcb_bbox[1][1])

    board_translation = (3, -4, 2)
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


def test_extruder_cage_side_variants_use_placed_mount_before_downstream_parts():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    tool_head_resource_text = (ASSEMBLIES_DIR / "tool_head_assembly.yaml").read_text()
    tool_head_resource = yaml.load(
        tool_head_resource_text,
        Loader=AssemblyDefaultsLoader,
    )
    whole_printer_resource = yaml.load(
        (ASSEMBLIES_DIR / "whole_printer_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
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
            "tool_head_mount_machined": "tool_head_mount_machined_bottom_assembly",
        },
        "right": {
            "sprite_extruder": "sprite_extruder_right_assembly",
            "nitehawk_board": "nitehawk_board_right_assembly",
            "tool_head_mount_machined": "tool_head_mount_machined_top_assembly",
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
            visual_context["carriage"],
            "x_axis_rail_assembly",
            "x_axis_lower_profile_assembly",
            "x_axis_top_profile_assembly",
        }

        visualization_parts = visual_context["resource"]["Builder"]["Visualization"][
            "parts"
        ]
        assert {
            "source": "injected",
            "assembly": "tool_head_mount_machined",
            "artifact": "leader",
            "name": "tool_head_mount_machined",
        } in visualization_parts
        assert not any(
            rule.get("source") == "injected"
            and rule.get("assembly") == "carriage"
            for rule in visualization_parts
        )
        for dependency_assembly, visual_name in [
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
        assert not any(
            placement.get("part") == sprite_extruder
            and placement.get("post_rotation", {}).get("angle") == 180
            and placement.get("post_rotation", {}).get("axis") == [0, 0, 1]
            for placement in placements
        )

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
        part_fan = f"part_fan_{side}_assembly"
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

        sprite_indices = [
            index
            for index, placement in enumerate(placements)
            if placement.get("part") == sprite_extruder
        ]
        assert sprite_indices

        sprite_rigid_indices = [
            index
            for index, placement in enumerate(placements)
            if placement.get("rigid_group") == [sprite_extruder]
            and placement.get("to") == carriage
        ]
        assert len(sprite_rigid_indices) == 1
        sprite_rigid_index = sprite_rigid_indices[0]

        assert max(sprite_indices) < sprite_rigid_index < machined_group_index

        downstream_sprite_group_indices = [
            index
            for index, placement in enumerate(placements)
            if placement.get("to") == sprite_extruder
            and {cage, part_fan, board}.issubset(set(placement.get("rigid_group", [])))
        ]
        assert len(downstream_sprite_group_indices) == 1
        assert machined_group_index < downstream_sprite_group_indices[0]

        cage_group_indices = [
            index
            for index, placement in enumerate(placements)
            if placement.get("to") == sprite_extruder
            and cage in placement.get("rigid_group", [])
        ]
        assert cage_group_indices == downstream_sprite_group_indices

    assert not any(
        set(placement.get("rigid_group", []) or [])
        == {"sprite_extruder_left_assembly", "sprite_extruder_right_assembly"}
        and placement.get("to") == "x_axis_rail_assembly"
        for placement in placements
    )

    for side in ["left", "right"]:
        part_fan = assemblies[f"part_fan_{side}_assembly"]
        sprite_extruder = f"sprite_extruder_{side}_assembly"
        assert part_fan["depends_on"] == [sprite_extruder]
        assert part_fan["inject_parts"] == {"sprite_extruder": sprite_extruder}

    graph_model = builder_graph_model.build_graph_model(config["assemblies"], config)
    generation_index = {
        assembly_name: index
        for index, generation in enumerate(
            builder_graph_model.resolve_build_generation_names(
                graph_model,
                ["tool_heads_assembly"],
            )
        )
        for assembly_name in generation
    }
    for side, injected_context in expected_true_inputs.items():
        machined_mount = injected_context["tool_head_mount_machined"]
        cage = f"extruder_cage_{side}_assembly"
        part_fan = f"part_fan_{side}_assembly"
        assert generation_index[machined_mount] < generation_index[cage]
        assert generation_index[machined_mount] < generation_index[part_fan]

        placement_deps = set(graph_model.placement_build_dependencies[machined_mount])
        assert not placement_deps & {
            "extruder_cage_left_assembly",
            "extruder_cage_right_assembly",
            "part_fan_left_assembly",
            "part_fan_right_assembly",
        }

    assert "nitehawk_holder" not in tool_head_resource_text
    tool_head_composite = tool_head_resource["Parts"]["ToolHeadAssembly"][
        "Properties"
    ]["Composite"]
    assert tool_head_composite["Leader"]["Fused"] == [
        {
            "source": "injected",
            "assembly": "extruder_cage",
            "artifact": "leader",
        },
        {
            "source": "injected",
            "assembly": "part_fans",
            "artifact": "leader",
        },
    ]
    assert tool_head_composite["NonProductionParts"] == [
        {
            "source": "injected",
            "assembly": "part_fans",
            "artifact": "non_production_parts",
            "name_template": "part_fans_{name}",
        },
    ]

    expected_tool_head_inputs = {
        "left": {
            "sprite_extruder": "sprite_extruder_left_assembly",
            "extruder_cage": "extruder_cage_left_assembly",
            "part_fans": "part_fan_left_assembly",
        },
        "right": {
            "sprite_extruder": "sprite_extruder_right_assembly",
            "extruder_cage": "extruder_cage_right_assembly",
            "part_fans": "part_fan_right_assembly",
        },
    }
    for side, expected_inputs in expected_tool_head_inputs.items():
        tool_head = assemblies[f"tool_head_{side}_assembly"]
        assert tool_head["inject_parts"] == expected_inputs
        assert set(tool_head["depends_on"]) == set(expected_inputs.values())
        assert "nitehawk_holder" not in tool_head["inject_parts"]
        assert not any(
            "nitehawk_holder" in dependency
            for dependency in tool_head.get("depends_on", [])
        )

    whole_printer = assemblies["whole_printer_assembly"]
    whole_printer_visualization_parts = whole_printer_resource["Builder"][
        "Visualization"
    ]["parts"]
    expected_board_inputs = {
        "left": {
            "alias": "nitehawk_board_left",
            "assembly": "nitehawk_board_left_assembly",
            "animation": {
                "x_carriage_1": [{"$ref": "x_axis_x_travel"}, 0, 0],
                "z_axis": [0, 0, {"$ref": "z_axis_z_travel"}],
            },
        },
        "right": {
            "alias": "nitehawk_board_right",
            "assembly": "nitehawk_board_right_assembly",
            "animation": {
                "x_carriage_2": [{"$ref": "x_axis_x_travel_negative"}, 0, 0],
                "z_axis": [0, 0, {"$ref": "z_axis_z_travel"}],
            },
        },
    }
    for expected in expected_board_inputs.values():
        assert expected["assembly"] in whole_printer["depends_on"]
        assert whole_printer["inject_parts"][expected["alias"]] == expected["assembly"]

        board_rule = next(
            rule
            for rule in whole_printer_visualization_parts
            if rule.get("source") == "injected"
            and rule.get("assembly") == expected["alias"]
        )
        assert board_rule["artifact"] == "followers"
        assert board_rule["name_template"] == "{assembly_name}_{name}"
        assert board_rule["animation"] == expected["animation"]

    for side in ["left", "right"]:
        board = f"nitehawk_board_{side}_assembly"
        sprite_extruder = f"sprite_extruder_{side}_assembly"

        board_z_rotation = next(
            placement
            for placement in placements
            if placement.get("part") == board
            and placement.get("post_rotation", {}).get("angle") == 180
            and placement.get("post_rotation", {}).get("axis") == [0, 0, 1]
        )
        assert board_z_rotation["post_rotation"]["center"] == f"{board}.CENTER"

        left_alignment = next(
            placement
            for placement in placements
            if placement.get("part") == board and placement.get("alignment") == "LEFT"
        )
        assert left_alignment["to"] == sprite_extruder

        front_alignment = next(
            placement
            for placement in placements
            if placement.get("part") == board
            and placement.get("alignment") == "STACK_FRONT"
        )
        assert front_alignment["to"] == sprite_extruder
        assert front_alignment["stack_gap"] == {
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
