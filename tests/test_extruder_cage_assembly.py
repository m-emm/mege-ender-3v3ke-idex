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

    assert "nitehawk_board" in parameters
    assert "tool_head_mount_machined" in parameters
    assert parameters["tool_head_mount_machined"].default is inspect.Parameter.empty
    assert "carriage" not in parameters
    assert "extruder_cage_mount_plate_fillet_radius" in parameters
    assert "extruder_cage_top_right_bridge_clearance" in parameters
    for parameter_name in REMOVED_CAGE_PARAMETERS:
        assert parameter_name not in parameters


def test_extruder_cage_exposes_shared_tap_mounting_interfaces_and_hardware():
    tool_head_mount_machined = _create_machined_mount()
    sprite_extruder = create_sprite_extruder_assembly(
        **assembly_kwargs(create_sprite_extruder_assembly)
    )
    sprite_extruder = align(
        sprite_extruder,
        tool_head_mount_machined,
        Alignment.CENTER,
    )
    sprite_extruder = translate(
        DEFAULTS["x_axis_sprite_extruder_tool_head_mount_x_offset"],
        DEFAULTS["x_axis_sprite_extruder_tool_head_mount_y_offset"],
        DEFAULTS["x_axis_sprite_extruder_tool_head_mount_z_offset"],
    )(sprite_extruder)
    nitehawk_board = create_nitehawk_board_assembly(
        **assembly_kwargs(create_nitehawk_board_assembly)
    )
    nitehawk_board = _place_nitehawk_board_like_graph(nitehawk_board, sprite_extruder)
    cage = create_extruder_cage_assembly(
        **assembly_kwargs(
            create_extruder_cage_assembly,
            sprite_extruder=sprite_extruder,
            nitehawk_board=nitehawk_board,
            tool_head_mount_machined=tool_head_mount_machined,
        )
    )

    assert get_volume(cage.leader) > 0
    assert cage.follower_indices_by_name == {}
    for screw_name in (
        "sprite_mount_screw_left_top",
        "sprite_mount_screw_left_bottom",
        "sprite_mount_screw_right_top",
        "sprite_mount_screw_right_bottom",
        "nitehawk_mount_screw_0",
        "nitehawk_mount_screw_1",
    ):
        assert get_volume(cage.get_named_non_production_part(screw_name)) > 0

    for cutter_name in (
        "mount_hole_cutter",
        "nitehawk_mount_hole_0",
        "nitehawk_mount_hole_1",
        "nitehawk_mount_nut_pocket_0",
        "nitehawk_mount_nut_pocket_1",
    ):
        assert _recut_delta(cage.leader, cage.get_named_cutter(cutter_name)) < 0.01


def test_extruder_cage_sides_share_resource_and_follow_ordered_join_chains():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    cage_resource = yaml.load(
        (ASSEMBLIES_DIR / "extruder_cage_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )

    assert cage_resource["Parts"]["ExtruderCageAssembly"]["Properties"][
        "Generator"
    ] == (
        "mege_ender_3v3ke_idex.designs.assemblies.extruder_cage_assembly"
        ".create_extruder_cage_assembly"
    )
    assert not (ASSEMBLIES_DIR / "extruder_cage_left_assembly.yaml").exists()
    assert not (ASSEMBLIES_DIR / "extruder_cage_right_assembly.yaml").exists()

    side_context = {
        "left": {
            "sprite_extruder": "sprite_extruder_left_assembly",
            "nitehawk_board": "nitehawk_board_left_assembly",
            "tool_head_mount_machined": "tool_head_mount_machined_bottom_assembly",
            "rail": "mgn7h_rail_with_carriage_left_assembly",
            "sensor": "opb991t11z_sensor_left_assembly",
            "raw_tap": "idex_tap_t0_assembly",
            "fan_cage": "extruder_cage_left_fan_joined_assembly",
            "final_cage": "extruder_cage_left_joined_assembly",
            "cage_tap": "idex_tap_t0_cage_joined_assembly",
            "final_tap": "idex_tap_t0_joined_assembly",
        },
        "right": {
            "sprite_extruder": "sprite_extruder_right_assembly",
            "nitehawk_board": "nitehawk_board_right_assembly",
            "tool_head_mount_machined": "tool_head_mount_machined_top_assembly",
            "rail": "mgn7h_rail_with_carriage_right_assembly",
            "sensor": "opb991t11z_sensor_right_assembly",
            "raw_tap": "idex_tap_t1_assembly",
            "fan_cage": "extruder_cage_right_fan_joined_assembly",
            "final_cage": "extruder_cage_right_joined_assembly",
            "final_tap": "idex_tap_t1_joined_assembly",
        },
    }

    for side, expected in side_context.items():
        cage = assemblies[f"extruder_cage_{side}_assembly"]
        assert cage["resource_file"] == "extruder_cage_assembly.yaml"
        assert cage["inject_parts"] == {
            key: expected[key]
            for key in (
                "sprite_extruder",
                "nitehawk_board",
                "tool_head_mount_machined",
            )
        }

        fan_join = assemblies[f"part_fan_cage_{side}_join"]
        assert fan_join["inject_parts"] == {
            "part_fans": f"part_fan_{side}_assembly",
            "extruder_cage": f"extruder_cage_{side}_assembly",
        }
        assert fan_join["outputs"]["extruder_cage"] == expected["fan_cage"]

        tap_join = assemblies[f"tap_extruder_cage_{side}_join"]
        assert tap_join["inject_parts"] == {
            "extruder_cage": expected["fan_cage"],
            "sprite_extruder": expected["sprite_extruder"],
            "mgn7h_rail_with_carriage": expected["rail"],
            "idex_tap": expected["raw_tap"],
            "opb991t11z_sensor": expected["sensor"],
        }
        assert tap_join["outputs"]["extruder_cage"] == expected["final_cage"]

    belt_join = assemblies["tap_belt_carriage_left_join"]
    assert belt_join["inject_parts"] == {
        "idex_tap": side_context["left"]["cage_tap"],
        "belt_carriage": "x_axis_belt_carriage_bottom_assembly",
    }
    assert belt_join["outputs"]["idex_tap"] == side_context["left"]["final_tap"]

    graph = builder_graph_model.build_graph_model(config["assemblies"], config)
    generations = builder_graph_model.resolve_build_generation_names(
        graph, ["tool_heads_assembly"]
    )
    generation_index = {
        name: index
        for index, generation in enumerate(generations)
        for name in generation
    }
    assert (
        generation_index["join:part_fan_cage_left_join"]
        < generation_index["join:tap_extruder_cage_left_join"]
    )
    assert (
        generation_index["join:tap_extruder_cage_left_join"]
        < generation_index["join:tap_belt_carriage_left_join"]
    )
    assert (
        generation_index["join:tap_belt_carriage_left_join"]
        < generation_index["idex_tap_t0_joined_assembly"]
    )


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
