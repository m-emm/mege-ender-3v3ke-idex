import ast
from pathlib import Path

import pytest
import yaml

from assembly_defaults import (
    ASSEMBLIES_DIR,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.linear_bearing_LM8LUU_assembly import (
    create_linear_bearing_LM8LUU_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.z_axis_carriage_assembly import (
    create_z_axis_carriage_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.z_axis_rail_assembly import (
    create_z_axis_rail_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.z_axis_profile_assembly import (
    create_z_axis_profile_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.z_axis_threaded_rod_assembly import (
    create_z_axis_threaded_rod_assembly,
)
from shellforgepy.simple import get_bounding_box_center, get_bounding_box_size


ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"
SOURCE_ASSEMBLIES_DIR = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "mege_ender_3v3ke_idex"
    / "designs"
    / "assemblies"
)


def _load_yaml(path):
    return yaml.load(path.read_text(), Loader=AssemblyDefaultsLoader)


def _assemblies():
    config = _load_yaml(ASSEMBLIES_FILE)
    return {assembly["name"]: assembly for assembly in config["assemblies"]}


def test_active_z_axis_graph_uses_rails_and_neutral_top_mount_names():
    assemblies = _assemblies()

    assert not any("z_axis_guide_rod" in name for name in assemblies)
    for side in ("left", "right"):
        rail_name = f"z_axis_{side}_rail_assembly"
        for assembly_name in (
            f"z_axis_motor_mount_{side}_assembly",
            f"z_axis_top_mount_{side}_assembly",
            f"z_axis_carriage_{side}_assembly",
        ):
            assembly = assemblies[assembly_name]
            assert rail_name in assembly["depends_on"]
            assert assembly["inject_parts"]["z_axis_rail"] == rail_name
            if "carriage" in assembly_name:
                profile_name = f"z_axis_profile_{side}_assembly"
                assert profile_name in assembly["depends_on"]
                assert assembly["inject_parts"]["z_axis_profile"] == profile_name


def test_active_z_axis_resources_and_scenes_have_no_guide_rod_references():
    active_files = [
        ASSEMBLIES_FILE,
        ASSEMBLIES_DIR / "idex_parameters.yaml",
        ASSEMBLIES_DIR / "whole_printer_assembly.yaml",
        ASSEMBLIES_DIR / "x_z_axis_interface_assembly.yaml",
        ASSEMBLIES_DIR / "waste_bin_visu_assembly.yaml",
        ASSEMBLIES_DIR / "z_axis_motor_mount_assembly.yaml",
        ASSEMBLIES_DIR / "z_axis_top_mount_assembly.yaml",
        ASSEMBLIES_DIR / "z_axis_carriage_assembly.yaml",
        SOURCE_ASSEMBLIES_DIR / "z_axis_motor_mount_assembly.py",
        SOURCE_ASSEMBLIES_DIR / "z_axis_top_mount_assembly.py",
        SOURCE_ASSEMBLIES_DIR / "z_axis_carriage_assembly.py",
    ]

    for path in active_files:
        assert "z_axis_guide_rod" not in path.read_text(), path

    assert not (ASSEMBLIES_DIR / "z_axis_guide_rod_assembly.yaml").exists()
    assert not (ASSEMBLIES_DIR / "z_axis_guide_rod_top_mount_assembly.yaml").exists()
    assert not (SOURCE_ASSEMBLIES_DIR / "z_axis_guide_rod_assembly.py").exists()
    assert not (
        SOURCE_ASSEMBLIES_DIR / "z_axis_guide_rod_top_mount_assembly.py"
    ).exists()


def test_monolithic_z_axis_resources_only_export_their_leaders_for_production():
    expected_leaders = {
        "z_axis_motor_mount_assembly.yaml": "mount_plate",
        "z_axis_top_mount_assembly.yaml": "top_mount",
        "z_axis_carriage_assembly.yaml": "carriage",
    }

    for filename, leader_name in expected_leaders.items():
        resource = _load_yaml(ASSEMBLIES_DIR / filename)
        production_parts = resource["Builder"]["Production"]["parts"]
        assert len(production_parts) == 1
        assert production_parts[0]["source"] == "self"
        assert production_parts[0]["artifact"] == "leader"
        assert production_parts[0]["name"] == leader_name
        assert all(
            part["artifact"] != "followers"
            for mode in resource["Builder"].values()
            for part in mode["parts"]
        )


def test_z_axis_carriage_is_monolithic_and_retains_brass_angle_hardware():
    profile = create_z_axis_profile_assembly(
        **assembly_kwargs(create_z_axis_profile_assembly, side="left")
    )
    rail = create_z_axis_rail_assembly(**assembly_kwargs(create_z_axis_rail_assembly))
    threaded_rod = create_z_axis_threaded_rod_assembly(
        **assembly_kwargs(create_z_axis_threaded_rod_assembly)
    )
    carriage = create_z_axis_carriage_assembly(
        **assembly_kwargs(
            create_z_axis_carriage_assembly,
            z_axis_profile=profile,
            z_axis_rail=rail,
            z_axis_threaded_rod=threaded_rod,
        )
    )
    non_production_names = {
        name for name, _part in carriage.get_named_non_production_part_items()
    }

    assert carriage.follower_indices_by_name == {}
    assert {
        "carriage_top_brass_angle_left",
        "carriage_top_brass_angle_right",
        "carriage_bottom_brass_angle",
        "brass_angle_thread_inserts",
        "threaded_rod_nut",
        "x_axis_alignment_reference",
    } <= non_production_names
    assert (
        len(
            {
                name
                for name in non_production_names
                if name.startswith("screw_reference_") and name.endswith("_screw")
            }
        )
        == 6
    )
    assert not any(
        "bearing" in name or "clamp" in name for name in non_production_names
    )

    carriage_center = get_bounding_box_center(carriage.leader)
    carriage_size = get_bounding_box_size(carriage.leader)
    for rail_carriage_name in ("bottom_carriage", "top_carriage"):
        rail_carriage = rail.get_follower_part_by_name(rail_carriage_name)
        rail_carriage_center = get_bounding_box_center(rail_carriage)
        rail_carriage_size = get_bounding_box_size(rail_carriage)
        assert carriage_center[1] + carriage_size[1] / 2 == pytest.approx(
            rail_carriage_center[1] - rail_carriage_size[1] / 2
        )


def test_top_mount_retained_geometry_is_not_sized_by_big_thing():
    source = (SOURCE_ASSEMBLIES_DIR / "z_axis_top_mount_assembly.py").read_text()
    tree = ast.parse(source)
    retained_geometry_calls = [
        call
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id in {"create_box", "create_filleted_box"}
    ]

    assert not any(
        isinstance(node, ast.Name) and node.id == "BIG_THING"
        for call in retained_geometry_calls
        for argument in call.args
        for node in ast.walk(argument)
    )


def test_standalone_lm8luu_remains_buildable_but_has_no_dependants_or_injections():
    assemblies = _assemblies()
    standalone_name = "linear_bearing_LM8LUU_assembly"
    standalone = assemblies[standalone_name]

    assert standalone == {
        "name": standalone_name,
        "resource_file": "linear_bearing_LM8LUU_assembly.yaml",
        "depends_on": [],
    }
    for name, assembly in assemblies.items():
        if name == standalone_name:
            continue
        assert standalone_name not in assembly.get("depends_on", [])
        assert standalone_name not in assembly.get("inject_parts", {}).values()

    bearing = create_linear_bearing_LM8LUU_assembly()
    assert bearing is not None
