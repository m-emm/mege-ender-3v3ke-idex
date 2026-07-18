import inspect

import pytest
import yaml
from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.idex_tap_assembly import (
    create_idex_tap_assembly,
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


def _load_config():
    return yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )


def _load_assemblies():
    return {assembly["name"]: assembly for assembly in _load_config()["assemblies"]}


def _load_resource(resource_file):
    return yaml.load(
        (ASSEMBLIES_DIR / resource_file).read_text(),
        Loader=AssemblyDefaultsLoader,
    )


def _build_idex_tap(drive_position):
    x_axis_carriage = create_x_axis_carriage_assembly()
    fixed_tool_head_mount = create_tool_head_mount_machined_assembly(
        **assembly_kwargs(
            create_tool_head_mount_machined_assembly,
            carriage=x_axis_carriage,
            drive_position=drive_position,
        )
    )
    mgn7h_rail_with_carriage = create_mgn7h_rail_with_carriage_assembly(
        **assembly_kwargs(create_mgn7h_rail_with_carriage_assembly)
    )
    return create_idex_tap_assembly(
        **assembly_kwargs(
            create_idex_tap_assembly,
            fixed_tool_head_mount=fixed_tool_head_mount,
            x_axis_carriage=x_axis_carriage,
            mgn7h_rail_with_carriage=mgn7h_rail_with_carriage,
        )
    )


def test_shared_tap_generator_has_only_generic_side_context():
    parameters = inspect.signature(create_idex_tap_assembly).parameters

    for required_parameter in (
        "fixed_tool_head_mount",
        "x_axis_carriage",
        "mgn7h_rail_with_carriage",
    ):
        assert required_parameter in parameters
    for side_specific_parameter in (
        "sprite_extruder_right",
        "extruder_cage_right",
        "opb991t11z_sensor",
        "idex_tap_shuttle_height",
    ):
        assert side_specific_parameter not in parameters


@pytest.mark.parametrize("drive_position", ["bottom", "top"])
def test_shared_tap_builds_for_both_machined_mount_sides(drive_position):
    tap = _build_idex_tap(drive_position)

    assert get_volume(tap.leader) > 0
    for side in ("left", "right"):
        for front_back in ("front", "back"):
            name = f"lower_mount_strip_thread_inset_{side}_{front_back}_thread_inset"
            assert get_volume(tap.get_named_non_production_part(name)) > 0


def test_t0_and_t1_use_shared_tap_stack_and_dedicated_hardware_instances():
    assemblies = _load_assemblies()

    side_context = {
        "t0": {
            "mount": "tool_head_mount_machined_bottom_assembly",
            "carriage": "x_axis_left_carriage_assembly",
            "rail": "mgn7h_rail_with_carriage_left_assembly",
            "sensor": "opb991t11z_sensor_left_assembly",
            "sprite": "sprite_extruder_left_assembly",
            "joined": "idex_tap_t0_joined_assembly",
        },
        "t1": {
            "mount": "tool_head_mount_machined_top_assembly",
            "carriage": "x_axis_right_carriage_assembly",
            "rail": "mgn7h_rail_with_carriage_right_assembly",
            "sensor": "opb991t11z_sensor_right_assembly",
            "sprite": "sprite_extruder_right_assembly",
            "joined": "idex_tap_t1_joined_assembly",
        },
    }

    for tap_name, expected in side_context.items():
        tap = assemblies[f"idex_tap_{tap_name}_assembly"]
        assert tap["resource_file"] == "idex_tap_assembly.yaml"
        assert tap["inject_parts"] == {
            "fixed_tool_head_mount": expected["mount"],
            "x_axis_carriage": expected["carriage"],
            "mgn7h_rail_with_carriage": expected["rail"],
        }

        stack = assemblies[f"idex_tap_{tap_name}_stack_assembly"]
        assert stack["resource_file"] == "idex_tap_stack_assembly.yaml"
        assert stack["inject_parts"] == {
            "tool_head_mount_machined": expected["mount"],
            "idex_tap": expected["joined"],
            "mgn7h_rail_with_carriage": expected["rail"],
            "sprite_extruder": expected["sprite"],
            "opb991t11z_sensor": expected["sensor"],
        }

        assert assemblies[expected["rail"]]["resource_file"] == (
            "mgn7h_rail_with_carriage_assembly.yaml"
        )
        assert assemblies[expected["sensor"]]["resource_file"] == (
            "opb991t11z_sensor_assembly.yaml"
        )


def test_both_sensors_have_side_specific_placement_and_consumers():
    config = _load_config()
    assemblies = _load_assemblies()

    for side, tap_name in (("left", "t0"), ("right", "t1")):
        sensor = f"opb991t11z_sensor_{side}_assembly"
        rail = f"mgn7h_rail_with_carriage_{side}_assembly"
        placements = [
            placement
            for placement in config["placement"]["alignments"]
            if placement.get("part") == sensor
            or sensor in placement.get("rigid_group", [])
        ]
        assert placements
        assert any(
            placement.get("rigid_group") == [sensor]
            and placement.get("to") == f"sprite_extruder_{side}_assembly"
            for placement in placements
        )

        tap_join = assemblies[f"tap_extruder_cage_{side}_join"]
        assert tap_join["inject_parts"]["opb991t11z_sensor"] == sensor
        assert tap_join["inject_parts"]["mgn7h_rail_with_carriage"] == rail
        assert tap_join["inject_parts"]["idex_tap"] == f"idex_tap_{tap_name}_assembly"

        shield = assemblies[f"tool_head_cable_attach_shield_{side}_assembly"]
        assert shield["inject_parts"]["light_barrier_assembly"] == sensor


def test_generic_tap_resources_replace_retired_t1_specific_files():
    tap_resource = _load_resource("idex_tap_assembly.yaml")
    stack_resource = _load_resource("idex_tap_stack_assembly.yaml")

    assert tap_resource["Parts"]["IdexTapAssembly"]["Properties"]["Generator"] == (
        "mege_ender_3v3ke_idex.designs.assemblies.idex_tap_assembly"
        ".create_idex_tap_assembly"
    )
    assert stack_resource["Parts"]["IdexTapStackAssembly"]["Properties"][
        "Generator"
    ] == (
        "mege_ender_3v3ke_idex.designs.assemblies.idex_tap_stack_assembly"
        ".create_idex_tap_stack_assembly"
    )

    repo_root = ASSEMBLIES_DIR.parents[1]
    retired_paths = [
        ASSEMBLIES_DIR / "idex_tap_t1_assembly.yaml",
        ASSEMBLIES_DIR / "idex_tap_t1_stack_assembly.yaml",
        repo_root
        / "src/mege_ender_3v3ke_idex/designs/assemblies/idex_tap_t1_assembly.py",
        repo_root
        / "src/mege_ender_3v3ke_idex/designs/assemblies/idex_tap_t1_stack_assembly.py",
    ]
    assert all(not path.exists() for path in retired_paths)
