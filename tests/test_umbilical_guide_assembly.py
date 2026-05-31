import pytest

from mege_ender_3v3ke_idex.designs import idex_parameters
from mege_ender_3v3ke_idex.designs.assemblies.umbilical_guide import (
    create_umbilical_guide_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.x_axis_profile_assembly import (
    create_x_axis_profile_assembly,
)
from shellforgepy.simple import (
    Alignment,
    align,
    get_bounding_box,
    get_bounding_box_size,
    get_volume,
)


UMBILICAL_GUIDE_PARAMETERS = {
    "x_axis_umbilical_guide_radius": idex_parameters.x_axis_umbilical_guide_radius,
    "x_axis_umbilical_guide_cable_diameter": idex_parameters.x_axis_umbilical_guide_cable_diameter,
    "x_axis_umbilical_guide_inner_width": idex_parameters.x_axis_umbilical_guide_inner_width,
    "x_axis_umbilical_guide_wall_thickness": idex_parameters.x_axis_umbilical_guide_wall_thickness,
    "x_axis_umbilical_guide_depth": idex_parameters.x_axis_umbilical_guide_depth,
}


def _build_guide():
    return create_umbilical_guide_assembly(**UMBILICAL_GUIDE_PARAMETERS)


def test_umbilical_guide_has_positive_volume_and_clean_output_channels():
    guide = _build_guide()

    assert get_volume(guide.leader) > 0
    assert guide.followers == []
    assert guide.non_production_parts == []


def test_umbilical_guide_uses_expected_printable_prototype_bounds():
    guide = _build_guide()
    guide_size = get_bounding_box_size(guide.leader)

    outside_width = (
        UMBILICAL_GUIDE_PARAMETERS["x_axis_umbilical_guide_inner_width"]
        + 2 * UMBILICAL_GUIDE_PARAMETERS["x_axis_umbilical_guide_wall_thickness"]
    )
    outside_radius = (
        UMBILICAL_GUIDE_PARAMETERS["x_axis_umbilical_guide_radius"] + outside_width / 2
    )

    assert guide_size[0] == pytest.approx(2 * outside_radius, abs=0.05)
    assert guide_size[1] == pytest.approx(
        UMBILICAL_GUIDE_PARAMETERS["x_axis_umbilical_guide_depth"], abs=0.05
    )
    assert guide_size[2] == pytest.approx(outside_radius, abs=0.05)


def test_umbilical_guide_stacks_on_top_of_x_axis_top_profile():
    guide = _build_guide()
    top_profile = create_x_axis_profile_assembly(
        profile_name="x_axis_top_profile",
        x_axis_profile_length=idex_parameters.x_axis_profile_length,
    )

    placed_guide = align(
        guide.leader, top_profile.leader, Alignment.CENTER, axes=[0, 1]
    )
    placed_guide = align(
        placed_guide,
        top_profile.leader,
        Alignment.STACK_TOP,
        stack_gap=idex_parameters.x_axis_umbilical_guide_stack_gap,
    )

    guide_bbox = get_bounding_box(placed_guide)
    profile_bbox = get_bounding_box(top_profile.leader)

    assert guide_bbox[0][2] == pytest.approx(
        profile_bbox[1][2] + idex_parameters.x_axis_umbilical_guide_stack_gap
    )
