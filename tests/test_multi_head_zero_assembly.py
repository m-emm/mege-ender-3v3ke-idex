import inspect
import math

import pytest
import yaml
from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.multi_head_zero_assembly import (
    create_multi_head_zero_assembly,
)
from shellforgepy.simple import get_bounding_box, get_bounding_box_size, get_volume


def _load_yaml(path):
    return yaml.load(path.read_text(), Loader=AssemblyDefaultsLoader)


def test_multi_head_zero_generator_matches_resource_and_measured_envelope():
    resource = _load_yaml(ASSEMBLIES_DIR / "multi_head_zero_assembly.yaml")
    kwargs = assembly_kwargs(create_multi_head_zero_assembly)
    assembly = create_multi_head_zero_assembly(**kwargs)

    assert set(inspect.signature(create_multi_head_zero_assembly).parameters) == set(
        resource["Parameters"]
    )
    assert get_bounding_box_size(assembly.leader) == pytest.approx(
        [
            kwargs["multi_head_zero_body_width"],
            kwargs["multi_head_zero_body_depth"],
            kwargs["multi_head_zero_body_height"]
            + kwargs["multi_head_zero_ball_shaft_receptacle_height"],
        ]
    )
    assert get_volume(assembly.leader) == pytest.approx(
        kwargs["multi_head_zero_body_width"]
        * kwargs["multi_head_zero_body_depth"]
        * kwargs["multi_head_zero_body_height"]
        + math.pi
        * (
            (kwargs["multi_head_zero_ball_shaft_receptacle_diameter"] / 2) ** 2
            - (kwargs["multi_head_zero_ball_shaft_diameter"] / 2) ** 2
        )
        * kwargs["multi_head_zero_ball_shaft_receptacle_height"]
    )


def test_multi_head_zero_ball_is_centered_and_reaches_the_measured_top_height():
    kwargs = assembly_kwargs(create_multi_head_zero_assembly)
    assembly = create_multi_head_zero_assembly(**kwargs)
    leader_bbox = get_bounding_box(assembly.leader)
    ball_bbox = get_bounding_box(assembly.get_non_production_part_by_name("ball"))

    assert set(assembly.non_production_indices_by_name) == {"ball"}
    assert ball_bbox[0][0] + ball_bbox[1][0] == pytest.approx(
        leader_bbox[0][0] + leader_bbox[1][0]
    )
    assert ball_bbox[0][1] + ball_bbox[1][1] == pytest.approx(
        leader_bbox[0][1] + leader_bbox[1][1]
    )
    assert ball_bbox[0][2] == pytest.approx(
        leader_bbox[1][2]
        - kwargs["multi_head_zero_ball_shaft_receptacle_height"]
    )
    assert ball_bbox[1][2] - ball_bbox[0][2] == pytest.approx(
        kwargs["multi_head_zero_ball_top_height"]
    )


def test_multi_head_zero_is_standalone_and_animates_only_the_ball():
    resource = _load_yaml(ASSEMBLIES_DIR / "multi_head_zero_assembly.yaml")
    assemblies = {
        assembly["name"]: assembly
        for assembly in _load_yaml(ASSEMBLIES_DIR / "assemblies.yaml")["assemblies"]
    }
    parts = resource["Builder"]["Visualization"]["parts"]

    assert assemblies["multi_head_zero_assembly"] == {
        "name": "multi_head_zero_assembly",
        "resource_file": "multi_head_zero_assembly.yaml",
        "depends_on": [],
    }
    assert resource["Builder"]["Production"]["parts"] == []
    assert parts[0] == {
        "source": "self",
        "artifact": "leader",
        "name": "multi_head_zero_body",
    }
    assert parts[1] == {
        "source": "self",
        "artifact": "non_production_parts",
        "name_template": "{name}",
        "animation": {"multi_head_zero_press": [0, 0, -0.7]},
    }
