import inspect

import pytest
import yaml
from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.eddy_duo_assembly import (
    create_eddy_duo_assembly,
)
from shellforgepy.simple import (
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
)


def _load_yaml(path):
    return yaml.load(path.read_text(), Loader=AssemblyDefaultsLoader)


def test_eddy_duo_generator_matches_resource_and_measured_envelope():
    resource = _load_yaml(ASSEMBLIES_DIR / "eddy_duo_assembly.yaml")
    parameter_names = set(inspect.signature(create_eddy_duo_assembly).parameters)

    assert parameter_names == set(resource["Parameters"])

    kwargs = assembly_kwargs(create_eddy_duo_assembly)
    eddy_duo = create_eddy_duo_assembly(**kwargs)
    body_size = get_bounding_box_size(eddy_duo.leader)

    assert get_volume(eddy_duo.leader) > 0
    assert body_size == pytest.approx(
        [
            kwargs["eddy_duo_width"],
            kwargs["eddy_duo_depth"],
            kwargs["eddy_duo_height"],
        ],
        abs=0.01,
    )
    assert set(eddy_duo.cutter_indices_by_name) == {
        "mounting_hole_left",
        "mounting_hole_right",
    }
    assert set(eddy_duo.follower_indices_by_name) == {
        "fiducial_outer_ring",
        "fiducial_inner_ring",
        "fiducial_cross_x",
        "fiducial_cross_y",
    }


def test_eddy_duo_holes_and_fiducial_match_measured_locations():
    kwargs = assembly_kwargs(create_eddy_duo_assembly)
    eddy_duo = create_eddy_duo_assembly(**kwargs)

    left_hole = get_bounding_box_center(
        eddy_duo.get_cutter_part_by_name("mounting_hole_left")
    )
    right_hole = get_bounding_box_center(
        eddy_duo.get_cutter_part_by_name("mounting_hole_right")
    )
    fiducial_center = get_bounding_box_center(
        eddy_duo.get_follower_part_by_name("fiducial_outer_ring")
    )
    body_bbox = get_bounding_box(eddy_duo.leader)

    assert right_hole[0] - left_hole[0] == pytest.approx(
        kwargs["eddy_duo_mounting_hole_spacing"]
    )
    assert left_hole[2] == pytest.approx(
        kwargs["eddy_duo_height"] - kwargs["eddy_duo_mounting_hole_center_from_top"]
    )
    assert right_hole[2] == pytest.approx(left_hole[2])
    assert fiducial_center[0] == pytest.approx(0)
    assert fiducial_center[1] == pytest.approx(0)
    assert body_bbox[0][1] == pytest.approx(
        -(kwargs["eddy_duo_depth"] / 2 + kwargs["eddy_duo_coil_center_depth_offset"])
    )
    assert body_bbox[1][1] == pytest.approx(
        kwargs["eddy_duo_depth"] / 2 - kwargs["eddy_duo_coil_center_depth_offset"]
    )


def test_eddy_duo_is_registered_as_a_standalone_visualization_assembly():
    config = _load_yaml(ASSEMBLIES_DIR / "assemblies.yaml")
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    assert assemblies["eddy_duo_assembly"] == {
        "name": "eddy_duo_assembly",
        "resource_file": "eddy_duo_assembly.yaml",
        "depends_on": [],
    }
