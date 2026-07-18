import inspect
from pathlib import Path

import yaml
from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.idex_tap_t1_assembly import (
    create_idex_tap_t1_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.mgn7h_rail_with_carriage_assembly import (
    create_mgn7h_rail_with_carriage_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.tool_head_mount_machined_assembly import (
    create_tool_head_mount_machined_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.x_axis_carriage_assembly import (
    create_x_axis_carriage_assembly,
)
from shellforgepy.simple import get_volume


REPO_ROOT = ASSEMBLIES_DIR.parents[1]
T0_SUFFIX = "t" + "0"
STALE_TAP_PREFIX = "idex_tap_"
STALE_T0_TAP_TOKENS = (
    STALE_TAP_PREFIX + T0_SUFFIX,
    "IdexTap" + "T" + "0",
    "create_" + STALE_TAP_PREFIX + T0_SUFFIX,
)
REMOVED_SPRITE_KEEP_OUT_REFERENCE = "sprite_" + "keepout_reference"
JOINED_TAP_ASSEMBLY = "idex_tap_t1_joined_assembly"
RETIRED_SHUTTLE_ASSEMBLY = "idex_tap_t1_shuttle_assembly"
PARKED_OPB_ASSEMBLY = "opb991t11z_sensor_assembly"


def _load_assemblies():
    config = _load_config()
    return {assembly["name"]: assembly for assembly in config["assemblies"]}


def _load_config():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    return config


def _load_resource(resource_file):
    return yaml.load(
        (ASSEMBLIES_DIR / resource_file).read_text(),
        Loader=AssemblyDefaultsLoader,
    )


def _build_idex_tap_t1_assembly():
    x_axis_carriage = create_x_axis_carriage_assembly()
    fixed_tool_head_mount = create_tool_head_mount_machined_assembly(
        **assembly_kwargs(
            create_tool_head_mount_machined_assembly,
            carriage=x_axis_carriage,
            drive_position="top",
        )
    )
    mgn7h_rail_with_carriage = create_mgn7h_rail_with_carriage_assembly(
        **assembly_kwargs(create_mgn7h_rail_with_carriage_assembly)
    )

    return create_idex_tap_t1_assembly(
        **assembly_kwargs(
            create_idex_tap_t1_assembly,
            fixed_tool_head_mount=fixed_tool_head_mount,
            x_axis_carriage=x_axis_carriage,
            mgn7h_rail_with_carriage=mgn7h_rail_with_carriage,
        )
    )


def test_idex_tap_assemblies_are_t1_named_in_builder_contract():
    assemblies = _load_assemblies()

    expected_resource_files = {
        "idex_tap_t1_assembly": "idex_tap_t1_assembly.yaml",
        "idex_tap_t1_stack_assembly": "idex_tap_t1_stack_assembly.yaml",
        PARKED_OPB_ASSEMBLY: "opb991t11z_sensor_assembly.yaml",
    }
    for assembly_name, resource_file in expected_resource_files.items():
        assert assembly_name in assemblies
        assert assemblies[assembly_name]["resource_file"] == resource_file

    for old_assembly_name in (
        STALE_TAP_PREFIX + T0_SUFFIX + "_assembly",
        STALE_TAP_PREFIX + T0_SUFFIX + "_shuttle_assembly",
        STALE_TAP_PREFIX + T0_SUFFIX + "_stack_assembly",
        RETIRED_SHUTTLE_ASSEMBLY,
    ):
        assert old_assembly_name not in assemblies

    for top_level_name in ("tool_heads_assembly", "whole_printer_assembly"):
        top_level = assemblies[top_level_name]
        assert JOINED_TAP_ASSEMBLY in top_level["depends_on"]
        assert "idex_tap_t1_assembly" not in top_level["depends_on"]
        assert RETIRED_SHUTTLE_ASSEMBLY not in top_level["depends_on"]
        assert top_level["inject_parts"]["idex_tap_t1"] == JOINED_TAP_ASSEMBLY
        assert "idex_tap_t1_shuttle" not in top_level["inject_parts"]
        assert STALE_TAP_PREFIX + T0_SUFFIX not in top_level["inject_parts"]
        assert (
            STALE_TAP_PREFIX + T0_SUFFIX + "_shuttle" not in top_level["inject_parts"]
        )

    tool_heads = assemblies["tool_heads_assembly"]
    assert PARKED_OPB_ASSEMBLY in tool_heads["depends_on"]
    assert tool_heads["inject_parts"]["opb991t11z_sensor"] == PARKED_OPB_ASSEMBLY

    whole_printer = assemblies["whole_printer_assembly"]
    assert PARKED_OPB_ASSEMBLY not in whole_printer["depends_on"]
    assert "opb991t11z_sensor" not in whole_printer["inject_parts"]

    fixed_tap = assemblies["idex_tap_t1_assembly"]
    assert "sprite_extruder_right_assembly" not in fixed_tap["depends_on"]
    assert "extruder_cage_right_assembly" not in fixed_tap["depends_on"]
    assert PARKED_OPB_ASSEMBLY not in fixed_tap["depends_on"]
    assert "sprite_extruder" not in fixed_tap["inject_parts"]
    assert "sprite_extruder_right" not in fixed_tap["inject_parts"]
    assert "extruder_cage_right" not in fixed_tap["inject_parts"]
    assert "opb991t11z_sensor" not in fixed_tap["inject_parts"]


def test_opb991t11z_sensor_consumers_match_active_toolhead_wiring():
    config = _load_config()
    assemblies = _load_assemblies()

    assert assemblies[PARKED_OPB_ASSEMBLY]["resource_file"] == (
        "opb991t11z_sensor_assembly.yaml"
    )
    consumers = {
        assembly_name
        for assembly_name, assembly in assemblies.items()
        if assembly_name != PARKED_OPB_ASSEMBLY
        and (
            PARKED_OPB_ASSEMBLY in assembly.get("depends_on", [])
            or PARKED_OPB_ASSEMBLY in assembly.get("inject_parts", {}).values()
        )
    }
    assert consumers == {
        "tap_extruder_cage_right_join",
        "tool_head_cable_attach_shield_right_assembly",
        "tool_heads_assembly",
    }

    for inactive_consumer_name in (
        "whole_printer_assembly",
        "idex_tap_t1_assembly",
        "idex_tap_t1_stack_assembly",
        "part_fan_cage_right_join",
    ):
        inactive_consumer = assemblies[inactive_consumer_name]
        assert PARKED_OPB_ASSEMBLY not in inactive_consumer.get("depends_on", [])
        assert (
            PARKED_OPB_ASSEMBLY
            not in inactive_consumer.get("inject_parts", {}).values()
        )

    placements = config["placement"]["alignments"]
    assert [
        placement
        for placement in placements
        if placement.get("part") == PARKED_OPB_ASSEMBLY
    ] == [
        {
            "part": PARKED_OPB_ASSEMBLY,
            "post_rotation": {"angle": -90, "axis": [1, 0, 0]},
        },
        {
            "part": PARKED_OPB_ASSEMBLY,
            "to": "tool_head_mount_machined_top_assembly",
            "alignment": "CENTER",
        },
        {
            "part": PARKED_OPB_ASSEMBLY,
            "to": "sprite_extruder_right_assembly",
            "alignment": "RIGHT",
            "post_translation": [-5, 0, 0],
        },
        {
            "part": PARKED_OPB_ASSEMBLY,
            "to": "sprite_extruder_right_assembly",
            "alignment": "STACK_TOP",
        },
    ]
    assert {
        "rigid_group": [PARKED_OPB_ASSEMBLY],
        "to": "sprite_extruder_right_assembly",
    } in placements

    tool_heads_resource = _load_resource("tool_heads_assembly.yaml")
    assert [
        part
        for part in tool_heads_resource["Builder"]["Visualization"]["parts"]
        if part.get("assembly") == "opb991t11z_sensor"
    ] == [
        {
            "source": "injected",
            "assembly": "opb991t11z_sensor",
            "artifact": "all",
            "name_template": "opb991t11z_sensor_{name}",
            "animation": {
                "x_carriage_2": [{"$ref": "x_axis_x_travel_negative"}, 0, 0],
                "idex_tap_trigger_lift_right": [
                    0,
                    0,
                    {"$ref": "idex_tap_trigger_lift_right"},
                ],
            },
        }
    ]

    idex_tap_resource = _load_resource("idex_tap_t1_assembly.yaml")
    assert [
        part
        for part in idex_tap_resource["Builder"]["Visualization"]["parts"]
        if part.get("assembly") == PARKED_OPB_ASSEMBLY
    ] == [
        {
            "source": "dependencies",
            "assembly": PARKED_OPB_ASSEMBLY,
            "artifact": "all",
            "name_template": "opb991t11z_sensor_{name}",
        }
    ]


def test_idex_tap_t1_fixed_generator_drops_unused_right_toolhead_context():
    parameters = inspect.signature(create_idex_tap_t1_assembly).parameters

    for removed_parameter in (
        "x_axis_profile",
        "sprite_extruder_right",
        "extruder_cage_right",
        "opb991t11z_sensor",
        "idex_tap_shuttle_height",
    ):
        assert removed_parameter not in parameters


def test_idex_tap_t1_lower_mount_strips_include_threaded_insert_visuals():
    tap = _build_idex_tap_t1_assembly()

    expected_thread_inset_names = {
        "lower_mount_strip_thread_inset_left_front_thread_inset",
        "lower_mount_strip_thread_inset_left_back_thread_inset",
        "lower_mount_strip_thread_inset_right_front_thread_inset",
        "lower_mount_strip_thread_inset_right_back_thread_inset",
    }

    assert get_volume(tap.leader) > 0
    for name in expected_thread_inset_names:
        assert get_volume(tap.get_named_non_production_part(name)) > 0


def test_active_idex_tap_files_have_no_t0_prototype_symbols():
    active_paths = [
        REPO_ROOT / "MEGE_IDEX_TAP_CONCEPT.md",
        ASSEMBLIES_DIR / "assemblies.yaml",
        ASSEMBLIES_DIR / "tool_heads_assembly.yaml",
        ASSEMBLIES_DIR / "whole_printer_assembly.yaml",
        ASSEMBLIES_DIR / "idex_tap_t1_assembly.yaml",
        ASSEMBLIES_DIR / "idex_tap_t1_stack_assembly.yaml",
        Path(
            REPO_ROOT,
            "src/mege_ender_3v3ke_idex/designs/assemblies/idex_tap_t1_assembly.py",
        ),
        Path(
            REPO_ROOT,
            "src/mege_ender_3v3ke_idex/designs/assemblies/"
            "idex_tap_t1_stack_assembly.py",
        ),
    ]

    for path in active_paths:
        text = path.read_text()
        for stale_token in STALE_T0_TAP_TOKENS:
            assert stale_token not in text, f"{path} still contains {stale_token}"

    retired_paths = [
        ASSEMBLIES_DIR / "idex_tap_t1_shuttle_assembly.yaml",
        Path(
            REPO_ROOT,
            "src/mege_ender_3v3ke_idex/designs/assemblies/"
            "idex_tap_t1_shuttle_assembly.py",
        ),
    ]
    for path in retired_paths:
        assert not path.exists()


def test_idex_tap_t1_does_not_emit_removed_sprite_reference_box():
    active_paths = [
        REPO_ROOT / "MEGE_IDEX_TAP_CONCEPT.md",
        ASSEMBLIES_DIR / "idex_tap_t1_assembly.yaml",
        Path(
            REPO_ROOT,
            "src/mege_ender_3v3ke_idex/designs/assemblies/idex_tap_t1_assembly.py",
        ),
    ]

    for path in active_paths:
        assert REMOVED_SPRITE_KEEP_OUT_REFERENCE not in path.read_text()

    resource = _load_resource("idex_tap_t1_assembly.yaml")
    for part in resource["Builder"]["Visualization"]["parts"]:
        assert REMOVED_SPRITE_KEEP_OUT_REFERENCE not in part.get("names", [])
