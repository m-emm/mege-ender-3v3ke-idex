import inspect

import pytest
import yaml

pytest.importorskip("cadquery")

from assembly_defaults import ASSEMBLIES_DIR, DEFAULTS, AssemblyDefaultsLoader
from mege_ender_3v3ke_idex.designs.assemblies.energy_chain_tpu_assembly import (
    create_energy_chain_tpu_assembly,
)
from shellforgepy.simple import get_bounding_box_size


RESOURCE_FILE = ASSEMBLIES_DIR / "energy_chain_tpu_assembly.yaml"
ENERGY_CHAIN_PARAMETERS = [
    "energy_chain_num_links",
    "energy_chain_width",
    "energy_chain_base_thickness",
    "energy_chain_link_length",
    "energy_chain_link_connector_thickness",
    "energy_chain_link_connector_width",
    "energy_chain_plug_diameter",
    "energy_chain_plug_slit_width",
    "energy_chain_plug_base_thickness",
    "energy_chain_plug_fillet_radius",
    "energy_chain_plug_wall_thickness",
    "energy_chain_plug_lip_height",
    "energy_chain_plug_lip_size",
    "energy_chain_plug_lip_top_gap",
    "energy_chain_plug_hole_slack",
    "energy_chain_channel_wall_thickness",
    "energy_chain_channel_link_thickness",
    "energy_chain_channel_link_width",
    "energy_chain_channel_height",
    "energy_chain_plug_plate_width",
]


def _y_axis_energy_chain_kwargs():
    return {
        parameter: DEFAULTS[f"y_axis_{parameter}"]
        for parameter in ENERGY_CHAIN_PARAMETERS
    }


def test_energy_chain_tpu_builder_requires_all_parameters_without_defaults():
    signature = inspect.signature(create_energy_chain_tpu_assembly)

    assert list(signature.parameters) == ENERGY_CHAIN_PARAMETERS
    for parameter in signature.parameters.values():
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY
        assert parameter.default is inspect.Parameter.empty


def test_energy_chain_tpu_skeleton_uses_y_axis_dimensions():
    assembly = create_energy_chain_tpu_assembly(**_y_axis_energy_chain_kwargs())

    assert get_bounding_box_size(assembly.leader) == pytest.approx((15, 10, 3))
    assert assembly.followers == []
    assert assembly.cutters == []
    assert assembly.non_production_parts == []


def test_energy_chain_tpu_manifest_declares_parameters_and_tpu_plate():
    resource = yaml.safe_load(RESOURCE_FILE.read_text())
    parameters = resource["Parameters"]
    visualization = resource["Builder"]["Visualization"]
    production = resource["Builder"]["Production"]

    assert list(parameters) == ENERGY_CHAIN_PARAMETERS
    assert parameters["energy_chain_num_links"] == {"Type": "Integer"}
    for parameter in ENERGY_CHAIN_PARAMETERS[1:]:
        assert parameters[parameter] == {"Type": "Float"}

    assert visualization["parts"] == [
        {
            "source": "self",
            "artifact": "leader",
            "name": "energy_chain_tpu",
        }
    ]
    assert (
        production["process_data_preset"]
        == "tpu_minimal_quality_minimal_strength_06"
    )
    assert production["process_data"]["overrides"]["process_overrides"] == {
        "enable_support": "0",
        "brim_type": "no_brim",
        "sparse_infill_density": "100%",
        "wall_loops": "3",
    }
    assert production["parts"] == [
        {
            "source": "self",
            "artifact": "leader",
            "name": "energy_chain_tpu",
        }
    ]
    assert production["arrange"]["plates"] == [
        {
            "name": "energy_chain_tpu",
            "parts": ["energy_chain_tpu"],
        }
    ]


def test_energy_chain_tpu_assembly_maps_to_y_axis_parameters():
    assemblies_config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assembly_entry = next(
        entry
        for entry in assemblies_config["assemblies"]
        if entry["name"] == "y_axis_energy_chain_tpu_assembly"
    )

    assert assembly_entry["resource_file"] == "energy_chain_tpu_assembly.yaml"
    assert assembly_entry["depends_on"] == []
    assert assembly_entry["parameters"] == {
        parameter: {"$ref": f"y_axis_{parameter}"}
        for parameter in ENERGY_CHAIN_PARAMETERS
    }
