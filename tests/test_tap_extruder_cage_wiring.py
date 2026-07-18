import yaml
from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader

INTERMEDIATE_CAGE = "extruder_cage_right_fan_joined_assembly"
FINAL_CAGE = "extruder_cage_right_joined_assembly"
FINAL_FAN = "part_fan_right_joined_assembly"
FINAL_TAP = "idex_tap_t1_joined_assembly"


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


def test_join_outputs_have_static_standalone_visualization_contracts():
    fan_joiner = _load_resource("part_fan_cage_joiner.yaml")
    tap_joiner = _load_resource("tap_extruder_cage_joiner.yaml")

    assert set(fan_joiner["Builder"]["Outputs"]) == {
        "part_fans",
        "extruder_cage",
    }
    assert set(tap_joiner["Builder"]["Outputs"]) == {
        "extruder_cage",
        "idex_tap_t1",
    }
    assert (
        tap_joiner["Builder"]["Outputs"]["extruder_cage"]["Production"]
        == fan_joiner["Builder"]["Outputs"]["extruder_cage"]["Production"]
    )
    assert "Production" not in tap_joiner["Builder"]["Outputs"]["idex_tap_t1"]

    for joiner in [fan_joiner, tap_joiner]:
        for output in joiner["Builder"]["Outputs"].values():
            for rule in output.get("Visualization", {}).get("parts", []):
                assert "animation" not in rule


def test_intermediate_cage_stays_out_of_visualization_collectors():
    _, assemblies = _load_assemblies()
    collection_names = [
        "whole_printer_assembly",
        "tool_heads_assembly",
        "tool_head_mounts_collection_assembly",
        "idex_tap_t1_stack_assembly",
    ]

    for collection_name in collection_names:
        collection = assemblies[collection_name]
        assert INTERMEDIATE_CAGE not in collection.get("depends_on", [])
        assert INTERMEDIATE_CAGE not in collection.get("inject_parts", {}).values()

    for resource_name in [
        "whole_printer_assembly.yaml",
        "tool_heads_assembly.yaml",
        "idex_tap_t1_stack_assembly.yaml",
    ]:
        assert INTERMEDIATE_CAGE not in (ASSEMBLIES_DIR / resource_name).read_text()

    mounts_collection = assemblies["tool_head_mounts_collection_assembly"]
    assert mounts_collection["inject_parts"]["extruder_cage_right"] == FINAL_CAGE
    assert mounts_collection["inject_parts"]["part_fan_right"] == FINAL_FAN
    assert FINAL_TAP not in mounts_collection["depends_on"]
    assert not (ASSEMBLIES_DIR / "tool_head_mounts_collection_assembly.yaml").exists()


def test_tool_heads_collection_keeps_final_aliases_and_animation_ownership():
    _, assemblies = _load_assemblies()
    tool_heads = assemblies["tool_heads_assembly"]
    resource = _load_resource("tool_heads_assembly.yaml")

    assert tool_heads["inject_parts"]["extruder_cage_right"] == FINAL_CAGE
    assert tool_heads["inject_parts"]["part_fan_right"] == FINAL_FAN
    assert tool_heads["inject_parts"]["idex_tap_t1"] == FINAL_TAP

    moving_tap_keys = {"x_carriage_2", "idex_tap_trigger_lift_right"}
    for alias in [
        "extruder_cage_right",
        "part_fan_right",
        "opb991t11z_sensor",
    ]:
        rules = _rules_for_alias(resource, alias)
        assert rules
        assert {frozenset(_animation_keys(rule)) for rule in rules} == {
            frozenset(moving_tap_keys)
        }

    tap_rules = _rules_for_alias(resource, "idex_tap_t1")
    assert tap_rules
    assert {frozenset(_animation_keys(rule)) for rule in tap_rules} == {
        frozenset({"x_carriage_2"})
    }

    rail_rules = _rules_for_alias(resource, "mgn7h_rail_with_carriage")
    assert [_animation_keys(rule) for rule in rail_rules] == [
        {"x_carriage_2", "idex_tap_trigger_lift_right"},
        {"x_carriage_2"},
    ]


def test_whole_printer_keeps_final_outputs_and_animation_ownership():
    _, assemblies = _load_assemblies()
    whole_printer = assemblies["whole_printer_assembly"]
    resource = _load_resource("whole_printer_assembly.yaml")

    assert whole_printer["inject_parts"]["extruder_cage_right"] == FINAL_CAGE
    assert whole_printer["inject_parts"]["part_fan_right"] == FINAL_FAN
    assert whole_printer["inject_parts"]["idex_tap_t1"] == FINAL_TAP
    assert "opb991t11z_sensor" not in whole_printer["inject_parts"]

    right_toolhead_keys = {
        "x_carriage_2",
        "z_axis",
        "idex_tap_trigger_lift_right",
    }
    for alias in ["extruder_cage_right", "part_fan_right"]:
        rules = _rules_for_alias(resource, alias)
        assert rules
        assert {frozenset(_animation_keys(rule)) for rule in rules} == {
            frozenset(right_toolhead_keys)
        }

    tap_rules = _rules_for_alias(resource, "idex_tap_t1")
    assert tap_rules
    assert {frozenset(_animation_keys(rule)) for rule in tap_rules} == {
        frozenset({"x_carriage_2", "z_axis"})
    }

    rail_rules = _rules_for_alias(resource, "mgn7h_rail_with_carriage")
    assert [_animation_keys(rule) for rule in rail_rules] == [
        {"x_carriage_2", "z_axis"},
        {"x_carriage_2", "z_axis", "idex_tap_trigger_lift_right"},
    ]


def test_tap_stack_keeps_registered_sensor_and_total_travel_animation():
    resource = _load_resource("idex_tap_t1_stack_assembly.yaml")

    assert _animation_keys(_rules_for_alias(resource, FINAL_TAP)[0]) == set()
    assert [
        _animation_keys(rule)
        for rule in _rules_for_alias(resource, "mgn7h_rail_with_carriage_assembly")
    ] == [{"idex_tap_total_travel"}, set()]
    assert _animation_keys(
        _rules_for_alias(resource, "sprite_extruder_right_assembly")[0]
    ) == {"idex_tap_total_travel"}
    assert (
        _animation_keys(_rules_for_alias(resource, "opb991t11z_sensor_assembly")[0])
        == set()
    )
