import pytest
import yaml

from assembly_defaults import ASSEMBLIES_DIR, DEFAULTS, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.panasonic_ssr_assembly import (
    create_panasonic_ssr_assembly,
)
from shellforgepy.simple import (
    get_bounding_box_center,
    get_bounding_box_size,
)


RESOURCE_FILE = ASSEMBLIES_DIR / "panasonic_ssr_assembly.yaml"


@pytest.fixture(scope="module")
def panasonic_ssr():
    return create_panasonic_ssr_assembly(
        **assembly_kwargs(create_panasonic_ssr_assembly)
    )


def test_panasonic_ssr_exposes_visual_parts_and_mount_cutters(panasonic_ssr):
    assert set(panasonic_ssr.follower_indices_by_name) == {
        "body",
        "output_terminal_cover",
        "input_terminal_cover",
        "output_terminal_screws",
        "input_terminal_screws",
    }
    assert set(panasonic_ssr.cutter_indices_by_name) == {
        "mounting_holes",
        "mounting_hole_pattern",
        "mounting_hole_1",
        "mounting_hole_2",
    }
    assert set(panasonic_ssr.non_production_indices_by_name) == {"reference"}


def test_panasonic_ssr_body_matches_datasheet_size(panasonic_ssr):
    body = panasonic_ssr.get_follower_part_by_name("body")

    assert get_bounding_box_size(body) == pytest.approx(
        (
            DEFAULTS["panasonic_ssr_width"],
            DEFAULTS["panasonic_ssr_length"],
            DEFAULTS["panasonic_ssr_height"],
        ),
        abs=0.05,
    )


def test_panasonic_ssr_m4_mounting_holes_match_datasheet_pitch(panasonic_ssr):
    hole_1 = panasonic_ssr.get_cutter_part_by_name("mounting_hole_1")
    hole_2 = panasonic_ssr.get_cutter_part_by_name("mounting_hole_2")
    center_1 = get_bounding_box_center(hole_1)
    center_2 = get_bounding_box_center(hole_2)

    assert center_1[0] == pytest.approx(DEFAULTS["panasonic_ssr_width"] / 2)
    assert center_2[0] == pytest.approx(DEFAULTS["panasonic_ssr_width"] / 2)
    assert abs(center_2[1] - center_1[1]) == pytest.approx(
        DEFAULTS["panasonic_ssr_mount_hole_pitch"]
    )
    for hole in [hole_1, hole_2]:
        assert get_bounding_box_size(hole)[0:2] == pytest.approx(
            (
                DEFAULTS["panasonic_ssr_mount_hole_diameter"],
                DEFAULTS["panasonic_ssr_mount_hole_diameter"],
            ),
            abs=0.05,
        )


def test_panasonic_ssr_resource_is_visualization_only():
    resource = yaml.safe_load(RESOURCE_FILE.read_text())
    visual_parts = resource["Builder"]["Visualization"]["parts"]

    assert "Production" not in resource["Builder"]
    assert any(rule.get("names") == ["body"] for rule in visual_parts)
    assert any(
        rule.get("names") == ["output_terminal_screws", "input_terminal_screws"]
        for rule in visual_parts
    )
