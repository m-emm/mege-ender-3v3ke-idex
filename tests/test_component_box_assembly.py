import pytest

from mege_ender_3v3ke_idex.designs.assemblies.component_box_assembly import (
    RESISTOR_BODY_DIAMETER,
    RESISTOR_WIRE_LENGTH,
    create_component_box_assembly,
)
from shellforgepy.simple import (
    create_box,
    get_bounding_box,
    get_bounding_box_size,
    get_volume,
)


RESISTOR_BOX_PARAMETERS = {
    "inner_length": 38,
    "inner_width": 3,
    "inner_height": 3,
    "wall_thickness": 1.0,
    "floor_thickness": 0.8,
    "lid_thickness": 0.8,
    "lid_clearance": 0.2,
    "wire_cut_width": 0.8,
    "fillet_radius": 0.4,
    "hinge_gap": 10,
    "hinge_width": 15,
    "hinge_depth": 1.2,
    "hinge_thickness": 0.5,
}


def _build_resistor_box():
    return create_component_box_assembly(**RESISTOR_BOX_PARAMETERS)


def test_component_box_exports_only_one_production_leader():
    component_box = _build_resistor_box()

    assert component_box.leader is not None
    assert component_box.followers == []


def test_component_box_contains_exact_resistor_visual_size():
    component_box = _build_resistor_box()

    resistor_visual = component_box.get_non_production_part_by_name("resistor_visual")
    resistor_size = get_bounding_box_size(resistor_visual)

    assert resistor_size[0] == pytest.approx(RESISTOR_WIRE_LENGTH)
    assert resistor_size[1] == pytest.approx(RESISTOR_BODY_DIAMETER)
    assert resistor_size[2] == pytest.approx(RESISTOR_BODY_DIAMETER)


def test_component_box_resistor_visual_fits_inside_cavity():
    component_box = _build_resistor_box()

    resistor_visual = component_box.get_non_production_part_by_name("resistor_visual")
    resistor_bbox = get_bounding_box(resistor_visual)

    assert resistor_bbox[0][0] == pytest.approx(5.0)
    assert resistor_bbox[1][0] == pytest.approx(35.0)
    assert resistor_bbox[0][1] == pytest.approx(1.25)
    assert resistor_bbox[1][1] == pytest.approx(3.75)
    assert resistor_bbox[0][2] >= RESISTOR_BOX_PARAMETERS["floor_thickness"]
    assert resistor_bbox[1][2] <= (
        RESISTOR_BOX_PARAMETERS["floor_thickness"]
        + RESISTOR_BOX_PARAMETERS["inner_height"]
        + 1e-6
    )


def test_component_box_exposes_lid_copy_for_closing_preview():
    component_box = _build_resistor_box()

    component_box.get_non_production_part_by_name("lid_closing_preview")


def test_body_has_wire_slits_cut_halfway_down_end_walls():
    component_box = _build_resistor_box()
    params = RESISTOR_BOX_PARAMETERS

    outer_length = params["inner_length"] + 2 * params["wall_thickness"]
    outer_width = params["inner_width"] + 2 * params["wall_thickness"]
    body_height = params["inner_height"] + params["floor_thickness"]
    slit_height = params["inner_height"] / 2

    left_slit_probe = create_box(
        params["wall_thickness"] / 2,
        params["wire_cut_width"] / 2,
        slit_height / 2,
        origin=(
            params["wall_thickness"] / 4,
            outer_width / 2 - params["wire_cut_width"] / 4,
            body_height - slit_height / 2,
        ),
    )
    right_slit_probe = create_box(
        params["wall_thickness"] / 2,
        params["wire_cut_width"] / 2,
        slit_height / 2,
        origin=(
            outer_length - params["wall_thickness"] * 3 / 4,
            outer_width / 2 - params["wire_cut_width"] / 4,
            body_height - slit_height / 2,
        ),
    )
    lower_wall_probe = create_box(
        params["wall_thickness"] / 2,
        params["wire_cut_width"] / 2,
        slit_height / 3,
        origin=(
            params["wall_thickness"] / 4,
            outer_width / 2 - params["wire_cut_width"] / 4,
            params["floor_thickness"] + 0.1,
        ),
    )

    leader_volume = get_volume(component_box.leader)
    assert leader_volume - get_volume(
        component_box.leader.cut(left_slit_probe)
    ) == pytest.approx(0)
    assert leader_volume - get_volume(
        component_box.leader.cut(right_slit_probe)
    ) == pytest.approx(0)
    assert leader_volume - get_volume(component_box.leader.cut(lower_wall_probe)) > 0


def test_lid_hinge_clearance_is_on_lid_open_top_edge():
    component_box = _build_resistor_box()
    lid = component_box.get_non_production_part_by_name("lid_closing_preview")

    params = RESISTOR_BOX_PARAMETERS
    outer_length = params["inner_length"] + 2 * params["wall_thickness"]
    outer_width = params["inner_width"] + 2 * params["wall_thickness"]
    body_height = params["inner_height"] + params["floor_thickness"]
    lid_inner_height = body_height + params["lid_clearance"]
    lid_outer_length = (
        outer_length + 2 * params["lid_clearance"] + 2 * params["wall_thickness"]
    )
    lid_outer_height = lid_inner_height + params["lid_thickness"]
    lid_origin = (
        (outer_length - lid_outer_length) / 2,
        outer_width + params["hinge_gap"],
        0,
    )
    hinge_x = (outer_length - params["hinge_width"]) / 2
    cutout_width = params["hinge_width"] + 2 * params["lid_clearance"]
    cutout_depth = (
        params["wall_thickness"] + params["hinge_depth"] + 2 * params["lid_clearance"]
    )
    cutout_height = params["hinge_thickness"] + params["lid_clearance"]

    top_clearance_probe = create_box(
        cutout_width - 0.2,
        cutout_depth - 0.2,
        cutout_height / 2,
        origin=(
            hinge_x - params["lid_clearance"] + 0.1,
            lid_origin[1] - params["lid_clearance"] + 0.1,
            lid_outer_height - cutout_height + 0.1,
        ),
    )
    old_floor_notch_probe = create_box(
        cutout_width - 0.2,
        cutout_depth - 0.2,
        cutout_height / 2,
        origin=(
            hinge_x - params["lid_clearance"] + 0.1,
            lid_origin[1] - params["lid_clearance"] + 0.1,
            params["lid_thickness"] - cutout_height + 0.1,
        ),
    )

    lid_volume = get_volume(lid)
    assert lid_volume - get_volume(lid.cut(top_clearance_probe)) == pytest.approx(0)
    assert lid_volume - get_volume(lid.cut(old_floor_notch_probe)) > 1


def test_component_box_leader_is_larger_than_inner_target():
    component_box = _build_resistor_box()

    leader_size = get_bounding_box_size(component_box.leader)

    assert leader_size[0] > 38
    assert leader_size[1] > 3
    assert leader_size[2] > 3
