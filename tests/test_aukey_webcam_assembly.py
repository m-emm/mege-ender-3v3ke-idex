import yaml

import pytest

pytest.importorskip("cadquery")

from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader
from mege_ender_3v3ke_idex.designs.assemblies.aukey_webcam_assembly import (
    create_aukey_webcam_assembly,
)
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.simple import get_bounding_box_size


RESOURCE_FILE = ASSEMBLIES_DIR / "aukey_webcam_assembly.yaml"
ASSEMBLIES_FILE = ASSEMBLIES_DIR / "assemblies.yaml"

DIMENSIONS = {
    "aukey_webcam_body_width": 103.0,
    "aukey_webcam_body_depth": 23.1,
    "aukey_webcam_body_height": 22.5,
    "aukey_webcam_lens_diameter": 16.8,
    "aukey_webcam_lens_depth": 2.0,
    "aukey_webcam_holder_front_width": 44.6,
    "aukey_webcam_holder_back_width": 36.1,
    "aukey_webcam_holder_thickness": 17.7,
    "aukey_webcam_holder_depth": 50.0,
    "aukey_webcam_body_to_holder_gap": 0.8,
    "aukey_webcam_body_cutter_angle": 20.0,
    "aukey_webcam_holder_back_offset": 7.4,
    "aukey_webcam_holder_link_cylinder_diameter": 17.3,
    "aukey_webcam_holder_link_cylinder_height": 10.0,
}


def test_aukey_webcam_uses_top_body_leader_and_visual_context_parts():
    webcam = create_aukey_webcam_assembly(**DIMENSIONS)

    assert isinstance(webcam, LeaderFollowersCuttersPart)
    assert get_bounding_box_size(webcam.leader) == pytest.approx(
        (
            DIMENSIONS["aukey_webcam_body_width"],
            DIMENSIONS["aukey_webcam_body_depth"],
            DIMENSIONS["aukey_webcam_body_height"],
        )
    )
    assert set(webcam.non_production_indices_by_name) == {"lens", "bottom_holder"}
    assert webcam.follower_indices_by_name == {}
    assert webcam.cutter_indices_by_name == {}

    lens = webcam.get_named_non_production_part("lens")
    assert get_bounding_box_size(lens) == pytest.approx(
        (
            DIMENSIONS["aukey_webcam_lens_diameter"],
            DIMENSIONS["aukey_webcam_lens_depth"],
            DIMENSIONS["aukey_webcam_lens_diameter"],
        ),
        abs=0.05,
    )

    bottom_holder = webcam.get_named_non_production_part("bottom_holder")
    assert get_bounding_box_size(bottom_holder) == pytest.approx(
        (
            DIMENSIONS["aukey_webcam_holder_front_width"],
            DIMENSIONS["aukey_webcam_holder_depth"],
            DIMENSIONS["aukey_webcam_holder_thickness"]
            + DIMENSIONS["aukey_webcam_holder_link_cylinder_height"] / 2,
        ),
        abs=0.05,
    )


def test_aukey_webcam_yaml_wiring_uses_minimal_all_visualization():
    resource_text = RESOURCE_FILE.read_text()
    resource = yaml.load(resource_text, Loader=AssemblyDefaultsLoader)
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)

    assert "color:" not in resource_text
    assert resource["Builder"]["Visualization"]["preview"]["enabled"] is True
    assert resource["Builder"]["Visualization"]["parts"] == [
        {"source": "self", "artifact": "all"}
    ]
    assert {
        "aukey_webcam_body_cutter_angle",
        "aukey_webcam_holder_back_offset",
        "aukey_webcam_holder_link_cylinder_diameter",
        "aukey_webcam_holder_link_cylinder_height",
    } <= set(resource["Parameters"])
    assert resource["Builder"]["Production"]["parts"] == [
        {
            "source": "self",
            "artifact": "leader",
            "name": "aukey_webcam_top_body",
        }
    ]

    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    assert assemblies["aukey_webcam_assembly"] == {
        "name": "aukey_webcam_assembly",
        "resource_file": "aukey_webcam_assembly.yaml",
        "depends_on": [],
    }
