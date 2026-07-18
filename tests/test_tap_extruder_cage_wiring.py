import yaml
from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader
from shellforgepy.builder import graph_model as builder_graph_model


def _load_resource(resource_name):
    return yaml.load(
        (ASSEMBLIES_DIR / resource_name).read_text(),
        Loader=AssemblyDefaultsLoader,
    )


def _load_assemblies():
    config = _load_resource("assemblies.yaml")
    return config, {assembly["name"]: assembly for assembly in config["assemblies"]}


def _rules_for_alias(resource, alias):
    return [
        rule
        for rule in resource["Builder"]["Visualization"]["parts"]
        if rule.get("assembly") == alias
    ]


def _animation_keys(rule):
    return set(rule.get("animation", {}))


def test_joiners_use_generic_tap_contracts_and_static_output_visualizations():
    fan_joiner = _load_resource("part_fan_cage_joiner.yaml")
    tap_joiner = _load_resource("tap_extruder_cage_joiner.yaml")
    belt_joiner = _load_resource("tap_belt_carriage_joiner.yaml")

    assert set(fan_joiner["Builder"]["Outputs"]) == {
        "part_fans",
        "extruder_cage",
    }
    assert set(tap_joiner["Builder"]["Outputs"]) == {
        "extruder_cage",
        "idex_tap",
    }
    assert set(belt_joiner["Builder"]["Outputs"]) == {
        "idex_tap",
        "belt_carriage",
    }
    assert "idex_tap_t0" not in tap_joiner["Builder"]["Outputs"]
    assert "idex_tap_t1" not in tap_joiner["Builder"]["Outputs"]

    for joiner in (fan_joiner, tap_joiner, belt_joiner):
        for output in joiner["Builder"]["Outputs"].values():
            for rule in output.get("Visualization", {}).get("parts", []):
                assert "animation" not in rule


def test_left_chain_is_ordered_and_intermediates_stay_out_of_top_level_scenes():
    config, assemblies = _load_assemblies()
    graph = builder_graph_model.build_graph_model(config["assemblies"], config)
    generations = builder_graph_model.resolve_build_generation_names(
        graph, ["tool_heads_assembly"]
    )
    generation_index = {
        name: index
        for index, generation in enumerate(generations)
        for name in generation
    }

    ordered_nodes = [
        "join:part_fan_cage_left_join",
        "extruder_cage_left_fan_joined_assembly",
        "join:tap_extruder_cage_left_join",
        "idex_tap_t0_cage_joined_assembly",
        "join:tap_belt_carriage_left_join",
        "idex_tap_t0_joined_assembly",
    ]
    assert [generation_index[name] for name in ordered_nodes] == sorted(
        generation_index[name] for name in ordered_nodes
    )

    intermediate_names = {
        "extruder_cage_left_fan_joined_assembly",
        "extruder_cage_right_fan_joined_assembly",
        "idex_tap_t0_cage_joined_assembly",
        "x_axis_belt_carriage_bottom_remainder_assembly",
        "x_axis_belt_carriage_bottom_assembly",
    }
    for collection_name in (
        "tool_heads_assembly",
        "whole_printer_assembly",
        "tool_head_mounts_collection_assembly",
    ):
        collection = assemblies[collection_name]
        assert not intermediate_names & set(collection.get("depends_on", []))
        assert not intermediate_names & set(collection.get("inject_parts", {}).values())

    assert graph.assemblies_by_name


def test_tool_heads_owns_independent_tap_lift_on_both_sides():
    _, assemblies = _load_assemblies()
    resource = _load_resource("tool_heads_assembly.yaml")
    tool_heads = assemblies["tool_heads_assembly"]

    assert tool_heads["parameters"]["idex_tap_trigger_lift_left"] == (
        tool_heads["parameters"]["idex_tap_trigger_lift_right"]
    )
    assert tool_heads["inject_parts"]["idex_tap_t0"] == ("idex_tap_t0_joined_assembly")
    assert tool_heads["inject_parts"]["idex_tap_t1"] == ("idex_tap_t1_joined_assembly")

    for side, carriage_animation in (
        ("left", "x_carriage_1"),
        ("right", "x_carriage_2"),
    ):
        lift = f"idex_tap_trigger_lift_{side}"
        moving_keys = {carriage_animation, lift}
        for alias in (
            f"sprite_extruder_{side}",
            f"extruder_cage_{side}",
            f"part_fan_{side}",
            f"opb991t11z_sensor_{side}",
        ):
            rules = _rules_for_alias(resource, alias)
            assert rules
            assert {frozenset(_animation_keys(rule)) for rule in rules} == {
                frozenset(moving_keys)
            }

        for fan_body in (
            f"single_part_fan_front_{side}_assembly",
            f"single_part_fan_side_{side}_assembly",
        ):
            assert {
                frozenset(_animation_keys(rule))
                for rule in _rules_for_alias(resource, fan_body)
            } == {frozenset(moving_keys)}

        tap_alias = "idex_tap_t0" if side == "left" else "idex_tap_t1"
        assert {
            frozenset(_animation_keys(rule))
            for rule in _rules_for_alias(resource, tap_alias)
        } == {frozenset({carriage_animation})}

        rail_rules = _rules_for_alias(resource, f"mgn7h_rail_with_carriage_{side}")
        assert [_animation_keys(rule) for rule in rail_rules] == [
            moving_keys,
            {carriage_animation},
        ]


def test_whole_printer_adds_left_lift_without_changing_right_rail_ownership():
    _, assemblies = _load_assemblies()
    resource = _load_resource("whole_printer_assembly.yaml")
    whole_printer = assemblies["whole_printer_assembly"]

    assert whole_printer["inject_parts"]["idex_tap_t0"] == (
        "idex_tap_t0_joined_assembly"
    )
    assert whole_printer["inject_parts"]["idex_tap_t1"] == (
        "idex_tap_t1_joined_assembly"
    )
    assert "x_axis_belt_carriage_bottom" not in whole_printer["inject_parts"]

    for side, carriage_animation in (
        ("left", "x_carriage_1"),
        ("right", "x_carriage_2"),
    ):
        lift = f"idex_tap_trigger_lift_{side}"
        moving_keys = {carriage_animation, "z_axis", lift}
        for alias in (
            f"sprite_extruder_{side}",
            f"extruder_cage_{side}",
            f"part_fan_{side}",
            f"opb991t11z_sensor_{side}",
        ):
            rules = _rules_for_alias(resource, alias)
            assert rules
            assert {frozenset(_animation_keys(rule)) for rule in rules} == {
                frozenset(moving_keys)
            }

    left_rail_rules = _rules_for_alias(resource, "mgn7h_rail_with_carriage_left")
    assert [_animation_keys(rule) for rule in left_rail_rules] == [
        {"x_carriage_1", "z_axis", "idex_tap_trigger_lift_left"},
        {"x_carriage_1", "z_axis"},
    ]

    right_rail_rules = _rules_for_alias(resource, "mgn7h_rail_with_carriage_right")
    assert [_animation_keys(rule) for rule in right_rail_rules] == [
        {"x_carriage_2", "z_axis"},
        {"x_carriage_2", "z_axis", "idex_tap_trigger_lift_right"},
    ]


def test_generic_tap_stack_can_focus_each_side_independently():
    _, assemblies = _load_assemblies()
    resource = _load_resource("idex_tap_stack_assembly.yaml")

    for side in ("t0", "t1"):
        stack = assemblies[f"idex_tap_{side}_stack_assembly"]
        assert stack["resource_file"] == "idex_tap_stack_assembly.yaml"
        assert set(stack["inject_parts"]) == {
            "tool_head_mount_machined",
            "idex_tap",
            "mgn7h_rail_with_carriage",
            "sprite_extruder",
            "opb991t11z_sensor",
        }

    assert _animation_keys(_rules_for_alias(resource, "idex_tap")[0]) == set()
    assert [
        _animation_keys(rule)
        for rule in _rules_for_alias(resource, "mgn7h_rail_with_carriage")
    ] == [{"idex_tap_total_travel"}, set()]
    assert _animation_keys(_rules_for_alias(resource, "sprite_extruder")[0]) == {
        "idex_tap_total_travel"
    }
    assert _animation_keys(_rules_for_alias(resource, "opb991t11z_sensor")[0]) == set()


def test_left_tap_production_plate_contains_exactly_four_rotated_leaders():
    resource = _load_resource("tool_heads_assembly.yaml")
    production = resource["Builder"]["Production"]
    parts = {part["name"]: part for part in production["parts"]}
    plate = next(
        plate
        for plate in production["arrange"]["plates"]
        if plate["name"] == "tool_heads_left_tap_petgcf"
    )

    assert plate["process_data_preset"] == "petgcf_max_strength_high_speed_06"
    assert plate["parts"] == [
        "extruder_cage_left_joined",
        "idex_tap_t0_joined",
        "tool_head_cable_attach_shield_left",
        "part_fan_left_joined",
    ]
    assert {
        name: (parts[name]["prod_rotation_angle"], parts[name]["prod_rotation_axis"])
        for name in plate["parts"]
    } == {
        "extruder_cage_left_joined": (135, [0, 1, 0]),
        "idex_tap_t0_joined": (29, [1, 0, 0]),
        "tool_head_cable_attach_shield_left": (90, [1, 0, 0]),
        "part_fan_left_joined": (50, [1, 0, 0]),
    }


def test_only_right_tap_plate_overrides_support_type_without_distance_tuning():
    resource = _load_resource("tool_heads_assembly.yaml")
    plates = {
        plate["name"]: plate
        for plate in resource["Builder"]["Production"]["arrange"]["plates"]
    }
    right_tap_overrides = plates["tool_head_right_tap"]["process_data"]["overrides"][
        "process_overrides"
    ]

    assert right_tap_overrides["support_type"] == "normal(auto)"
    assert right_tap_overrides["support_style"] == "default"
    assert {
        "support_top_z_distance",
        "support_bottom_z_distance",
        "support_object_xy_distance",
        "support_object_first_layer_gap",
        "support_interface_spacing",
        "support_bottom_interface_spacing",
    }.isdisjoint(right_tap_overrides)

    for sibling_plate_name in (
        "tool_head_right_petgcf",
        "tool_heads_left_tap_petgcf",
    ):
        sibling_overrides = plates[sibling_plate_name]["process_data"]["overrides"][
            "process_overrides"
        ]
        assert "support_type" not in sibling_overrides
        assert "support_style" not in sibling_overrides
