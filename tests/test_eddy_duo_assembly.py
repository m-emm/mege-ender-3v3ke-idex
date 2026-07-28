import inspect
from pathlib import Path

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
    assert set(eddy_duo.non_production_indices_by_name) == {"fiducial"}


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
        eddy_duo.get_non_production_part_by_name("fiducial")
    )
    body_bbox = get_bounding_box(eddy_duo.leader)

    assert right_hole[0] - left_hole[0] == pytest.approx(
        kwargs["eddy_duo_mounting_hole_spacing"]
    )
    assert left_hole[2] == pytest.approx(
        kwargs["eddy_duo_height"] - kwargs["eddy_duo_mounting_hole_center_from_top"]
    )
    assert right_hole[2] == pytest.approx(left_hole[2])
    assert fiducial_center[0] == pytest.approx(
        (body_bbox[0][0] + body_bbox[1][0]) / 2
    )
    assert fiducial_center[1] - body_bbox[0][1] == pytest.approx(
        kwargs["eddy_duo_depth"] / 2 + kwargs["eddy_duo_coil_center_depth_offset"]
    )
    assert body_bbox[1][1] - fiducial_center[1] == pytest.approx(
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


def test_eddy_duo_is_placed_and_animated_with_the_left_tool_head():
    config = _load_yaml(ASSEMBLIES_DIR / "assemblies.yaml")
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    tool_heads = assemblies["tool_heads_assembly"]
    tool_heads_resource = _load_yaml(ASSEMBLIES_DIR / "tool_heads_assembly.yaml")

    assert "eddy_duo_assembly" in tool_heads["depends_on"]
    assert tool_heads["inject_parts"]["eddy_duo"] == "eddy_duo_assembly"

    placements = config["placement"]["alignments"]
    assert {
        "part": "eddy_duo_assembly",
        "to": "tool_head_mount_machined_bottom_assembly",
        "alignment": "STACK_LEFT",
        "stack_gap": {"$ref": "eddy_duo_tool_head_side_gap"},
    } in placements
    assert {
        "part": "eddy_duo_assembly",
        "to": "tool_head_mount_machined_bottom_assembly",
        "alignment": "FRONT",
    } in placements
    assert {
        "part": "eddy_duo_assembly",
        "to": "sprite_extruder_left_assembly.non_production_parts.hotend",
        "alignment": "BOTTOM",
        "post_translation": [
            -6,
            9,
            {"$ref": "eddy_duo_nozzle_clearance"},
        ],
    } in placements
    assert {
        "rigid_group": ["eddy_duo_assembly"],
        "to": "tool_head_mount_machined_bottom_assembly",
    } in placements

    visualization_parts = tool_heads_resource["Builder"]["Visualization"]["parts"]
    eddy_visualization = next(
        part for part in visualization_parts if part.get("assembly") == "eddy_duo"
    )
    assert eddy_visualization["artifact"] == "all"
    assert eddy_visualization["animation"] == {
        "x_carriage_1": [
            {"$ref": "x_axis_x_travel"},
            0,
            0,
        ]
    }


def test_runtime_eddy_xy_offset_matches_resolved_assembly_graph_parameters():
    config = _load_yaml(ASSEMBLIES_DIR / "assemblies.yaml")
    parameters = _load_yaml(ASSEMBLIES_DIR / "idex_parameters.yaml")["globals"]
    calib_path = (
        Path(__file__).resolve().parents[1]
        / "klipper_setup"
        / "klipper_config"
        / "calib.yaml"
    )
    runtime = yaml.safe_load(calib_path.read_text(encoding="utf-8"))[
        "eddy_relative_calibration"
    ]["nozzle_to_coil"]
    placements = config["placement"]["alignments"]
    rotation = next(
        item
        for item in placements
        if item.get("part") == "eddy_duo_assembly" and item.get("post_rotation")
    )
    final = next(
        item
        for item in placements
        if item.get("part") == "eddy_duo_assembly"
        and item.get("alignment") == "BOTTOM"
        and item.get("post_translation")
    )
    assert rotation["post_rotation"] == {"angle": 90, "axis": [0, 0, 1]}
    translation = final["post_translation"]
    # The local +Y coil-depth offset rotates to printer -X.
    resolved_x = float(translation[0]) - float(
        parameters["eddy_duo_coil_center_depth_offset"]
    )
    resolved_y = float(translation[1])
    resolved_z = float(parameters["eddy_duo_nozzle_clearance"])
    assert runtime == pytest.approx(
        {"x": resolved_x, "y": resolved_y, "z": resolved_z}
    )
