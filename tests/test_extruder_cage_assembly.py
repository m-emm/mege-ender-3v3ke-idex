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
from mege_ender_3v3ke_idex.designs.assemblies.extruder_cage_right_assembly import (
    create_extruder_cage_right_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_board_assembly import (
    create_nitehawk_board_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.sprite_extruder_assembly import (
    create_sprite_extruder_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.tool_head_mount_machined_assembly import (
    create_tool_head_mount_machined_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.x_axis_carriage_assembly import (
    create_x_axis_carriage_assembly,
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


def _create_machined_mount():
    carriage = create_x_axis_carriage_assembly()
    return create_tool_head_mount_machined_assembly(
        **assembly_kwargs(
            create_tool_head_mount_machined_assembly,
            carriage=carriage,
            drive_position="bottom",
        )
    )


def test_extruder_cage_signature_uses_cage_owned_mount_dimensions():
    parameters = inspect.signature(create_extruder_cage_assembly).parameters
    right_parameters = inspect.signature(create_extruder_cage_right_assembly).parameters

    assert "nitehawk_board" in parameters
    assert "tool_head_mount_machined" in parameters
    assert parameters["tool_head_mount_machined"].default is inspect.Parameter.empty
    assert "carriage" not in parameters
    assert "extruder_cage_mount_plate_fillet_radius" in parameters
    assert "extruder_cage_top_right_bridge_clearance" in parameters
    assert list(right_parameters) == list(parameters)
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
    tool_head_mount_machined = _create_machined_mount()
    cage_kwargs = assembly_kwargs(
        create_extruder_cage_assembly,
        sprite_extruder=sprite_extruder,
        nitehawk_board=nitehawk_board,
        tool_head_mount_machined=tool_head_mount_machined,
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
            tool_head_mount_machined=tool_head_mount_machined,
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
    whole_printer_resource = yaml.load(
        (ASSEMBLIES_DIR / "whole_printer_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    right_cage_resource = yaml.load(
        (ASSEMBLIES_DIR / "extruder_cage_right_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    left_cage_resource = yaml.load(
        (ASSEMBLIES_DIR / "extruder_cage_left_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    joiner_resource = yaml.load(
        (ASSEMBLIES_DIR / "part_fan_cage_joiner.yaml").read_text(),
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
            "resource_file": "extruder_cage_right_assembly.yaml",
            "tool_head_mount_machined": "tool_head_mount_machined_top_assembly",
            "carriage": "x_axis_right_carriage_assembly",
        },
    }

    assert right_cage_resource["Parts"]["ExtruderCageAssembly"]["Properties"][
        "Generator"
    ] == (
        "mege_ender_3v3ke_idex.designs.assemblies.extruder_cage_right_assembly"
        ".create_extruder_cage_right_assembly"
    )

    assert assemblies["extruder_cage_assembly"]["inject_parts"] == {
        "sprite_extruder": "sprite_extruder_assembly",
        "nitehawk_board": "nitehawk_board_assembly",
        "tool_head_mount_machined": "tool_head_mount_machined_bottom_assembly",
    }
    assert set(assemblies["extruder_cage_assembly"]["depends_on"]) == {
        "sprite_extruder_assembly",
        "nitehawk_board_assembly",
        "tool_head_mount_machined_bottom_assembly",
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
            rule.get("source") == "injected" and rule.get("assembly") == "carriage"
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

    for removed_parameter in [
        "x_axis_sprite_extruder_carriage_stack_gap",
        "x_axis_left_sprite_extruder_carriage_x_offset",
        "x_axis_right_sprite_extruder_carriage_x_offset",
        "x_axis_sprite_extruder_rail_z_offset",
    ]:
        assert removed_parameter not in DEFAULTS
        assert removed_parameter not in assemblies_yaml_text

    for sprite_extruder in [
        "sprite_extruder_left_assembly",
        "sprite_extruder_right_assembly",
    ]:
        assert not any(
            placement.get("part") == sprite_extruder
            and placement.get("post_rotation", {}).get("angle") == 180
            and placement.get("post_rotation", {}).get("axis") == [0, 0, 1]
            for placement in placements
        )

        assert not any(
            placement.get("part") == sprite_extruder
            and placement.get("alignment") in {"RIGHT", "STACK_FRONT", "TOP"}
            and placement.get("to")
            in {
                "x_axis_left_carriage_assembly",
                "x_axis_right_carriage_assembly",
                "x_axis_rail_assembly",
            }
            for placement in placements
        )

    for side, injected_context in expected_true_inputs.items():
        visual_context = expected_visual_context[side]
        machined_mount = visual_context["tool_head_mount_machined"]
        sprite_extruder = injected_context["sprite_extruder"]
        carriage = visual_context["carriage"]
        cage = f"extruder_cage_{side}_assembly"
        part_fan = f"part_fan_{side}_assembly"
        joined_cage = f"extruder_cage_{side}_joined_assembly"
        joined_part_fan = f"part_fan_{side}_joined_assembly"
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

        sprite_center_indices = [
            index
            for index, placement in enumerate(placements)
            if placement.get("part") == sprite_extruder
            and placement.get("to") == machined_mount
            and placement.get("alignment") == "CENTER"
        ]
        assert len(sprite_center_indices) == 1
        sprite_center_index = sprite_center_indices[0]
        sprite_center_alignment = placements[sprite_center_index]
        assert sprite_center_alignment["post_translation"] == [
            {"$ref": "x_axis_sprite_extruder_tool_head_mount_x_offset"},
            {"$ref": "x_axis_sprite_extruder_tool_head_mount_y_offset"},
            {"$ref": "x_axis_sprite_extruder_tool_head_mount_z_offset"},
        ]

        sprite_rigid_indices = [
            index
            for index, placement in enumerate(placements)
            if placement.get("rigid_group") == [sprite_extruder]
            and placement.get("to") == machined_mount
        ]
        assert len(sprite_rigid_indices) == 1
        sprite_rigid_index = sprite_rigid_indices[0]

        assert machined_group_index < max(sprite_indices) < sprite_rigid_index

        pre_join_sprite_group_indices = [
            index
            for index, placement in enumerate(placements)
            if placement.get("to") == sprite_extruder
            and {cage, part_fan}.issubset(set(placement.get("rigid_group", [])))
        ]
        assert len(pre_join_sprite_group_indices) == 1
        assert sprite_rigid_index < pre_join_sprite_group_indices[0]

        downstream_sprite_group_indices = [
            index
            for index, placement in enumerate(placements)
            if placement.get("to") == sprite_extruder
            and {joined_cage, joined_part_fan}.issubset(
                set(placement.get("rigid_group", []))
            )
        ]
        assert len(downstream_sprite_group_indices) == 1
        assert pre_join_sprite_group_indices[0] < downstream_sprite_group_indices[0]

        cage_group_indices = [
            index
            for index, placement in enumerate(placements)
            if placement.get("to") == sprite_extruder
            and joined_cage in placement.get("rigid_group", [])
        ]
        assert cage_group_indices == downstream_sprite_group_indices

    assert not any(
        set(placement.get("rigid_group", []) or [])
        == {"sprite_extruder_left_assembly", "sprite_extruder_right_assembly"}
        and placement.get("to") == "x_axis_rail_assembly"
        for placement in placements
    )

    expected_part_fans = {
        "left": {
            "mount_chain": [
                "x_axis_rail_assembly",
                "x_axis_left_carriage_assembly",
                "tool_head_mount_machined_bottom_assembly",
            ],
            "sprite": "sprite_extruder_left_assembly",
            "front": "single_part_fan_front_left_assembly",
            "side": "single_part_fan_side_left_assembly",
            "blower_ring": "blower_ring_left_assembly",
        },
        "right": {
            "mount_chain": [
                "x_axis_rail_assembly",
                "x_axis_right_carriage_assembly",
                "tool_head_mount_machined_top_assembly",
            ],
            "sprite": "sprite_extruder_right_assembly",
            "front": "single_part_fan_front_right_assembly",
            "side": "single_part_fan_side_right_assembly",
            "blower_ring": "blower_ring_right_assembly",
        },
    }
    for side, expected in expected_part_fans.items():
        assert f"part_fan_{side}_assembly" + "_v2" not in assemblies
        part_fan = assemblies[f"part_fan_{side}_assembly"]
        assert part_fan["depends_on"] == (
            expected["mount_chain"]
            + [
                expected["sprite"],
                expected["front"],
                expected["side"],
                expected["blower_ring"],
            ]
        )
        assert part_fan["inject_parts"] == {
            "sprite_extruder": expected["sprite"],
            "front_part_fan": expected["front"],
            "side_part_fan": expected["side"],
            "blower_ring": expected["blower_ring"],
        }

    assert joiner_resource["Parts"]["PartFanCageJoiner"]["Type"] == (
        "Shellforgepy::AssemblyJoiner"
    )
    assert set(joiner_resource["Builder"]["Outputs"]) == {
        "part_fans",
        "extruder_cage",
    }

    expected_joins = {
        "left": {
            "part_fans": "part_fan_left_assembly",
            "extruder_cage": "extruder_cage_left_assembly",
            "extra_inject_parts": {
                "belt_carriage": "x_axis_belt_carriage_bottom_assembly",
                "sprite_extruder": "sprite_extruder_left_assembly",
            },
            "part_fans_output": "part_fan_left_joined_assembly",
            "extruder_cage_output": "extruder_cage_left_joined_assembly",
        },
        "right": {
            "part_fans": "part_fan_right_assembly",
            "extruder_cage": "extruder_cage_right_assembly",
            "extra_inject_parts": {
                "mgn7h_rail_with_carriage": "mgn7h_rail_with_carriage_assembly",
                "idex_tap_t1": "idex_tap_t1_assembly",
            },
            "part_fans_output": "part_fan_right_joined_assembly",
            "extruder_cage_output": "extruder_cage_right_joined_assembly",
            "idex_tap_t1_output": "idex_tap_t1_joined_assembly",
        },
    }
    for side, expected_join in expected_joins.items():
        join_entry = assemblies[f"part_fan_cage_{side}_join"]
        assert join_entry["kind"] == "join"
        assert join_entry["resource_file"] == "part_fan_cage_joiner.yaml"
        assert join_entry["inject_parts"] == {
            "part_fans": expected_join["part_fans"],
            "extruder_cage": expected_join["extruder_cage"],
            **expected_join["extra_inject_parts"],
        }
        expected_outputs = {
            "part_fans": expected_join["part_fans_output"],
            "extruder_cage": expected_join["extruder_cage_output"],
        }
        if "idex_tap_t1_output" in expected_join:
            expected_outputs["idex_tap_t1"] = expected_join["idex_tap_t1_output"]
        assert join_entry["outputs"] == expected_outputs

    graph_model = builder_graph_model.build_graph_model(config["assemblies"], config)
    for side, expected_join in expected_joins.items():
        assert f"part_fan_cage_{side}_join" not in graph_model.assemblies_by_name
        assert expected_join["part_fans_output"] in graph_model.assemblies_by_name
        assert expected_join["extruder_cage_output"] in graph_model.assemblies_by_name
        if "idex_tap_t1_output" in expected_join:
            assert expected_join["idex_tap_t1_output"] in graph_model.assemblies_by_name

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
        expected_join = expected_joins[side]
        machined_mount = injected_context["tool_head_mount_machined"]
        sprite_extruder = injected_context["sprite_extruder"]
        cage = f"extruder_cage_{side}_assembly"
        part_fan = f"part_fan_{side}_assembly"
        join_node = f"join:part_fan_cage_{side}_join"
        joined_cage = f"extruder_cage_{side}_joined_assembly"
        joined_part_fan = f"part_fan_{side}_joined_assembly"
        assert generation_index[machined_mount] < generation_index[cage]
        assert generation_index[cage] < generation_index[join_node]
        assert generation_index[part_fan] < generation_index[join_node]
        assert generation_index[join_node] < generation_index[joined_cage]
        assert generation_index[join_node] < generation_index[joined_part_fan]
        if "idex_tap_t1_output" in expected_join:
            raw_tap = expected_join["extra_inject_parts"]["idex_tap_t1"]
            joined_tap = expected_join["idex_tap_t1_output"]
            assert generation_index[raw_tap] < generation_index[join_node]
            assert generation_index[join_node] < generation_index[joined_tap]

        placement_deps = set(graph_model.placement_build_dependencies[machined_mount])
        assert not placement_deps & {
            "extruder_cage_left_assembly",
            "extruder_cage_right_assembly",
            "part_fan_left_assembly",
            "part_fan_right_assembly",
            "extruder_cage_left_joined_assembly",
            "extruder_cage_right_joined_assembly",
            "part_fan_left_joined_assembly",
            "part_fan_right_joined_assembly",
        }

        joined_group_index = next(
            index
            for index, placement in enumerate(placements)
            if placement.get("to") == sprite_extruder
            and {joined_cage, joined_part_fan}.issubset(
                set(placement.get("rigid_group", []))
            )
        )
        joined_group_step = graph_model.placement_steps[joined_group_index]
        assert joined_group_step.affected_assembly_names == (
            joined_cage,
            joined_part_fan,
        )
        for joined_output in [joined_cage, joined_part_fan]:
            assert (
                graph_model.first_involved_alignment_index[joined_output]
                == joined_group_index
            )
        if "idex_tap_t1_output" in expected_join:
            joined_tap = expected_join["idex_tap_t1_output"]
            joined_tap_group_index = next(
                index
                for index, placement in enumerate(placements)
                if placement.get("to") == sprite_extruder
                and placement.get("rigid_group") == [joined_tap]
            )
            joined_tap_group_step = graph_model.placement_steps[
                joined_tap_group_index
            ]
            assert joined_tap_group_step.affected_assembly_names == (joined_tap,)
            assert (
                graph_model.first_involved_alignment_index[joined_tap]
                == joined_tap_group_index
            )

    assert not (ASSEMBLIES_DIR / "tool_head_assembly.yaml").exists()
    for side in ["left", "right"]:
        assert f"tool_head_{side}_assembly" not in assemblies

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

        side_alignment = next(
            placement
            for placement in placements
            if placement.get("part") == board and placement.get("alignment") == "RIGHT"
        )
        assert side_alignment["to"] == sprite_extruder
        assert side_alignment["post_translation"][0] == {
            "$ref": "nitehawk_board_sprite_extruder_x_offset"
        }

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
            "drive_position": "bottom",
            "dependencies": {
                "x_axis_left_carriage_assembly",
            },
        },
        "tool_head_mount_machined_top_assembly": {
            "carriage": "x_axis_right_carriage_assembly",
            "drive_position": "top",
            "dependencies": {
                "x_axis_right_carriage_assembly",
            },
        },
    }

    for assembly_name, expected in expected_context.items():
        mount = assemblies[assembly_name]

        assert mount["resource_file"] == "tool_head_mount_machined_assembly.yaml"
        assert mount["inject_parts"] == {
            "carriage": expected["carriage"],
        }
        assert "x_axis_belt_carriage" not in mount["inject_parts"]
        assert "sprite_extruder" not in mount["inject_parts"]
        assert not any(
            "x_axis_belt_carriage" in dependency
            for dependency in mount.get("depends_on", [])
        )
        assert mount["parameters"] == {"drive_position": expected["drive_position"]}
        assert set(mount["depends_on"]) == expected["dependencies"]
