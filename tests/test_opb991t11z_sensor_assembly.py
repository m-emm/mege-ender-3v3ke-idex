import inspect

import yaml
from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.opb991t11z_sensor_assembly import (
    create_opb991t11z_sensor_assembly,
)
from shellforgepy.simple import get_volume


def _load_yaml(path):
    return yaml.load(path.read_text(), Loader=AssemblyDefaultsLoader)


def test_opb991t11z_generator_matches_resource_and_builds_reference_geometry():
    resource = _load_yaml(ASSEMBLIES_DIR / "opb991t11z_sensor_assembly.yaml")
    parameter_names = set(
        inspect.signature(create_opb991t11z_sensor_assembly).parameters
    )

    assert parameter_names == set(resource["Parameters"])
    assert resource["Parts"]["Opb991t11zSensorAssembly"]["Properties"]["Generator"] == (
        "mege_ender_3v3ke_idex.designs.assemblies.opb991t11z_sensor_assembly"
        ".create_opb991t11z_sensor_assembly"
    )

    sensor = create_opb991t11z_sensor_assembly(
        **assembly_kwargs(create_opb991t11z_sensor_assembly)
    )

    assert get_volume(sensor.leader) > 0
    assert {"hole_1", "hole_2", "connector_towers_cutter"}.issubset(
        sensor.cutter_indices_by_name
    )
    assert {"mount_tab_reference", "light_reference"}.issubset(
        sensor.non_production_indices_by_name
    )


def test_opb991t11z_is_registered_once_as_a_dependency_free_standalone_assembly():
    config = _load_yaml(ASSEMBLIES_DIR / "assemblies.yaml")
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    sensor_name = "opb991t11z_sensor_assembly"

    assert [name for name in assemblies if name.startswith("opb991t11z_sensor_")] == [
        sensor_name
    ]
    assert assemblies[sensor_name] == {
        "name": sensor_name,
        "resource_file": "opb991t11z_sensor_assembly.yaml",
        "depends_on": [],
    }

    for assembly_name, assembly in assemblies.items():
        if assembly_name == sensor_name:
            continue
        assert sensor_name not in assembly.get("depends_on", [])
        assert sensor_name not in assembly.get("inject_parts", {}).values()

    for placement in config["placement"]["alignments"]:
        assert placement.get("part") != sensor_name
        assert sensor_name not in placement.get("rigid_group", [])
