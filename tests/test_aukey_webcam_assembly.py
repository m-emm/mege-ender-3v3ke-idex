import yaml

import pytest

pytest.importorskip("cadquery")

from assembly_defaults import ASSEMBLIES_DIR, AssemblyDefaultsLoader
from mege_ender_3v3ke_idex.designs.assemblies.aukey_nozzle_cam_holder_assembly import (
    create_aukey_nozzle_cam_holder_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.aukey_webcam_assembly import (
    create_aukey_webcam_assembly,
)
from shellforgepy.builder import graph_model as builder_graph_model
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.simple import (
    Alignment,
    align,
    create_box,
    get_bounding_box,
    get_bounding_box_size,
    rotate,
)


RESOURCE_FILE = ASSEMBLIES_DIR / "aukey_webcam_assembly.yaml"
HOLDER_RESOURCE_FILE = ASSEMBLIES_DIR / "aukey_nozzle_cam_holder_assembly.yaml"
Y_AXIS_RESOURCE_FILE = ASSEMBLIES_DIR / "y_axis_assembly.yaml"
HOLDER_GENERATOR_FILE = (
    ASSEMBLIES_DIR.parents[1]
    / "src/mege_ender_3v3ke_idex/designs/assemblies/"
    / "aukey_nozzle_cam_holder_assembly.py"
)
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


def _camera_visual_envelope(nozzle_cam):
    camera_visual = nozzle_cam.leaders_followers_fused()
    for non_production_part in nozzle_cam.non_production_parts:
        camera_visual = camera_visual.fuse(non_production_part)
    return camera_visual


def _placed_nozzle_cam_and_y_axis():
    profile_right = create_box(20, 120, 20)
    y_axis = LeaderFollowersCuttersPart(leader=create_box(1, 1, 1))
    y_axis.add_named_non_production_part(profile_right, "profile_right")

    nozzle_cam = create_aukey_webcam_assembly(**DIMENSIONS)
    nozzle_cam = rotate(-90, axis=(1, 0, 0))(nozzle_cam)
    nozzle_cam = align(nozzle_cam, profile_right, Alignment.TOP)
    nozzle_cam = align(nozzle_cam, profile_right, Alignment.STACK_LEFT, stack_gap=7.0)
    nozzle_cam = align(nozzle_cam, profile_right, Alignment.CENTER, axes=[1])

    return nozzle_cam, y_axis


def test_aukey_nozzle_cam_holder_exports_only_base_plate_around_placed_camera():
    nozzle_cam, y_axis = _placed_nozzle_cam_and_y_axis()
    margin = 4.0
    plate_thickness = 3.0

    holder = create_aukey_nozzle_cam_holder_assembly(
        nozzle_cam=nozzle_cam,
        y_axis=y_axis,
        aukey_nozzle_cam_holder_base_plate_margin=margin,
        aukey_nozzle_cam_holder_base_plate_thickness=plate_thickness,
        aukey_nozzle_cam_holder_base_plate_fillet_radius=1.0,
    )

    assert isinstance(holder, LeaderFollowersCuttersPart)
    assert holder.followers == []
    assert holder.cutters == []
    assert holder.non_production_parts == []
    assert get_bounding_box_size(holder.leader)[2] == pytest.approx(
        plate_thickness,
        abs=0.05,
    )

    camera_visual = _camera_visual_envelope(nozzle_cam)
    camera_size = get_bounding_box_size(camera_visual)
    plate_size = get_bounding_box_size(holder.leader)

    assert plate_size[0] == pytest.approx(camera_size[0] + 2 * margin, abs=0.05)
    assert plate_size[1] == pytest.approx(camera_size[1] + 2 * margin, abs=0.05)

    camera_bbox = get_bounding_box(camera_visual)
    plate_bbox = get_bounding_box(holder.leader)

    assert plate_bbox[1][2] == pytest.approx(camera_bbox[0][2], abs=0.05)
    assert plate_bbox[0][0] <= camera_bbox[0][0] - margin + 0.05
    assert plate_bbox[1][0] >= camera_bbox[1][0] + margin - 0.05
    assert plate_bbox[0][1] <= camera_bbox[0][1] - margin + 0.05
    assert plate_bbox[1][1] >= camera_bbox[1][1] + margin - 0.05


def test_aukey_nozzle_cam_holder_yaml_uses_placed_injected_camera_context():
    holder_resource_text = HOLDER_RESOURCE_FILE.read_text()
    holder_resource = yaml.load(holder_resource_text, Loader=AssemblyDefaultsLoader)
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    assert "color:" not in holder_resource_text
    assert assemblies["nozzle_cam_assembly"] == {
        "name": "nozzle_cam_assembly",
        "resource_file": "aukey_webcam_assembly.yaml",
        "depends_on": [],
    }
    assert assemblies["aukey_nozzle_cam_holder_assembly"] == {
        "name": "aukey_nozzle_cam_holder_assembly",
        "resource_file": "aukey_nozzle_cam_holder_assembly.yaml",
        "depends_on": ["nozzle_cam_assembly", "y_axis_assembly"],
        "inject_parts": {
            "nozzle_cam": "nozzle_cam_assembly",
            "y_axis": "y_axis_assembly",
        },
    }

    assert {
        "aukey_nozzle_cam_holder_profile_gap",
        "aukey_nozzle_cam_holder_base_plate_margin",
        "aukey_nozzle_cam_holder_base_plate_thickness",
        "aukey_nozzle_cam_holder_base_plate_fillet_radius",
    } <= set(holder_resource["Parameters"])

    assert holder_resource["Builder"]["Production"]["parts"] == []
    assert holder_resource["Builder"]["Visualization"]["parts"] == [
        {"source": "self", "artifact": "all"},
        {
            "source": "injected",
            "assembly": "nozzle_cam",
            "artifact": "all",
            "name_template": "nozzle_cam_{name}",
        },
        {
            "source": "injected",
            "assembly": "y_axis",
            "artifact": "non_production_parts",
            "names": ["profile_right"],
            "name_template": "y_axis_{name}",
        },
    ]

    generator_source = HOLDER_GENERATOR_FILE.read_text()
    assert "copy(" not in generator_source
    assert "deepcopy" not in generator_source
    assert "rotate(" not in generator_source
    assert "translate(" not in generator_source


def test_aukey_nozzle_cam_holder_waits_for_yaml_placed_camera():
    config = yaml.load(ASSEMBLIES_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    placements = config["placement"]["alignments"]

    rotation_index = next(
        index
        for index, placement in enumerate(placements)
        if placement.get("part") == "nozzle_cam_assembly"
        and placement.get("post_rotation")
        == {
            "angle": -90,
            "axis": [1, 0, 0],
            "center": "nozzle_cam_assembly.CENTER",
        }
    )
    top_index = next(
        index
        for index, placement in enumerate(placements)
        if placement.get("part") == "nozzle_cam_assembly"
        and placement.get("to") == "y_axis_assembly.non_production_parts.profile_right"
        and placement.get("alignment") == "TOP"
    )
    stack_left_index = next(
        index
        for index, placement in enumerate(placements)
        if placement.get("part") == "nozzle_cam_assembly"
        and placement.get("to") == "y_axis_assembly.non_production_parts.profile_right"
        and placement.get("alignment") == "STACK_LEFT"
        and placement.get("stack_gap")
        == {"$ref": "aukey_nozzle_cam_holder_profile_gap"}
    )
    center_y_index = next(
        index
        for index, placement in enumerate(placements)
        if placement.get("part") == "nozzle_cam_assembly"
        and placement.get("to") == "y_axis_assembly.non_production_parts.profile_right"
        and placement.get("alignment") == "CENTER"
        and placement.get("axes") == [1]
    )
    boundary_index = next(
        index
        for index, placement in enumerate(placements)
        if placement.get("rigid_group") == ["aukey_nozzle_cam_holder_assembly"]
        and placement.get("to") == "nozzle_cam_assembly"
    )

    assert rotation_index < top_index < stack_left_index < center_y_index
    assert center_y_index < boundary_index

    graph = builder_graph_model.build_graph_model(config["assemblies"], config)
    placement_dependencies = set(
        graph.placement_build_dependencies["aukey_nozzle_cam_holder_assembly"]
    )
    assert {"nozzle_cam_assembly", "y_axis_assembly"} <= placement_dependencies


def test_y_axis_visualizes_nozzle_cam_and_holder_context():
    resource = yaml.load(Y_AXIS_RESOURCE_FILE.read_text(), Loader=AssemblyDefaultsLoader)
    visualization = resource["Builder"]["Visualization"]["parts"]
    name_template = "{assembly_name}_{artifact}_{default_name}"

    expected_context = [
        {
            "source": "dependencies",
            "assembly": "nozzle_cam_assembly",
            "artifact": "all",
            "name_template": name_template,
        },
        {
            "source": "dependencies",
            "assembly": "aukey_nozzle_cam_holder_assembly",
            "artifact": "all",
            "name_template": name_template,
        },
    ]

    for expected_part in expected_context:
        assert expected_part in visualization

    for part in visualization:
        if part.get("assembly") in {
            "nozzle_cam_assembly",
            "aukey_nozzle_cam_holder_assembly",
        }:
            assert "color" not in part
            assert "animation" not in part
