import yaml
import pytest

from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader, DEFAULTS
from mege_ender_3v3ke_idex.designs.assemblies.z_axis_rail_assembly import (
    create_z_axis_rail_assembly,
)
from shellforgepy.simple import get_bounding_box_center, get_bounding_box_size


ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"
RAIL_RESOURCE_FILE = ASSEMBLIES_DIR / "z_axis_rail_assembly.yaml"
INTERFACE_RESOURCE_FILE = ASSEMBLIES_DIR / "x_z_axis_interface_assembly.yaml"


def _load_yaml(path):
    return yaml.load(path.read_text(), Loader=AssemblyDefaultsLoader)


def test_z_axis_rail_instances_share_resource_and_required_placements():
    config = _load_yaml(ASSEMBLIES_FILE)
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    placements = config["placement"]["alignments"]

    for side in ["left", "right"]:
        rail_name = f"z_axis_{side}_rail_assembly"
        profile_name = f"z_axis_profile_{side}_assembly"
        rail = assemblies[rail_name]

        assert rail["resource_file"] == "z_axis_rail_assembly.yaml"
        assert rail["parameters"] == {
            "z_axis_rail_length": {"$ref": "z_axis_rail_length"}
        }
        assert {
            "part": rail_name,
            "post_rotation": {"angle": 90, "axis": [0, 1, 0]},
        } in placements
        assert {
            "part": rail_name,
            "to": profile_name,
            "alignment": "CENTER",
            "axes": [0],
        } in placements
        assert {
            "part": rail_name,
            "to": profile_name,
            "alignment": "BOTTOM",
        } in placements
        assert any(
            placement.get("part") == rail_name
            and placement.get("to") == profile_name
            and placement.get("alignment") == "STACK_FRONT"
            for placement in placements
        )


def test_z_axis_rail_resource_exposes_rail_and_carriage():
    resource = _load_yaml(RAIL_RESOURCE_FILE)
    part = resource["Parts"]["ZAxisRailAssembly"]
    visualization_parts = resource["Builder"]["Visualization"]["parts"]

    assert (
        part["Properties"]["Generator"]
        == "mege_ender_3v3ke_idex.designs.assemblies.z_axis_rail_assembly.create_z_axis_rail_assembly"
    )
    assert resource["Parameters"]["z_axis_rail_length"] == {"Type": "Float"}
    assert {
        "source": "self",
        "artifact": "leader",
        "name": "rail",
    } in visualization_parts
    assert {
        "source": "self",
        "artifact": "followers",
        "name_template": "{name}",
    } in visualization_parts


def test_z_axis_rail_generator_exposes_two_mgn12h_carriages_on_rail():
    rail_length = DEFAULTS["z_axis_rail_length"]
    assembly = create_z_axis_rail_assembly(z_axis_rail_length=rail_length)

    assert get_bounding_box_size(assembly.leader)[0] == pytest.approx(rail_length)
    assert list(assembly.follower_indices_by_name) == [
        "bottom_carriage",
        "top_carriage",
    ]

    rail_center = get_bounding_box_center(assembly.leader)
    carriage_centers = [
        get_bounding_box_center(assembly.get_follower_part_by_name(name))
        for name in ("bottom_carriage", "top_carriage")
    ]
    assert all(
        center[1] == pytest.approx(rail_center[1]) for center in carriage_centers
    )
    assert carriage_centers[0][0] != pytest.approx(carriage_centers[1][0])


def test_x_z_interface_visualizes_both_z_axis_rails():
    config = _load_yaml(ASSEMBLIES_FILE)
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    interface = assemblies["x_z_axis_interface_assembly"]
    interface_resource = _load_yaml(INTERFACE_RESOURCE_FILE)
    visualization_parts = interface_resource["Builder"]["Visualization"]["parts"]

    for side in ["left", "right"]:
        rail_name = f"z_axis_{side}_rail_assembly"
        rail_alias = f"z_axis_{side}_rail"

        assert rail_name in interface["depends_on"]
        assert interface["inject_parts"][rail_alias] == rail_name
        if side == "left":
            assert {
                "source": "injected",
                "assembly": rail_alias,
                "artifact": "leader",
                "name_template": "{assembly_name}_{name}",
            } in visualization_parts
            assert {
                "source": "injected",
                "assembly": rail_alias,
                "artifact": "followers",
                "names": ["bottom_carriage", "top_carriage"],
                "name_template": "{assembly_name}_{name}",
                "animation": {
                    "z_axis": [0, 0, {"$ref": "z_axis_z_travel"}],
                },
            } in visualization_parts
        else:
            assert {
                "source": "injected",
                "assembly": rail_alias,
                "artifact": "all",
                "name_template": "{assembly_name}_{name}",
            } in visualization_parts
