import inspect
import pytest
import yaml

pytest.importorskip("cadquery")

from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.part_fan_cage_joiner import (
    _create_join_flange_halves,
    join_part_fans_with_extruder_cage,
)
from mege_ender_3v3ke_idex.designs.assemblies.blower_ring_assembly import (
    _blower_air_squeeze_scale,
    _blower_nozzle_tip_scales,
    _blower_outer_squeeze_scale,
    create_blower_ring_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.part_fan_assembly import (
    create_part_fan_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.single_part_fan_assembly import (
    create_single_part_fan_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.sprite_extruder_assembly import (
    create_sprite_extruder_assembly,
)
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.simple import (
    create_box,
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
    translate,
)


def _current_blower_path_kwargs():
    return {
        "num_blowers": DEFAULTS["num_blowers"],
        "feeder_ring_inner_diameter": DEFAULTS["feeder_ring_inner_diameter"],
        "blowers_nozzle_center_distance": DEFAULTS["blowers_nozzle_center_distance"],
        "feeder_ring_width": DEFAULTS["feeder_ring_width"],
        "feeder_ring_wall": DEFAULTS["feeder_ring_wall"],
        "blowers_down_angle": DEFAULTS["blowers_down_angle"],
        "blowers_duct_diameter": DEFAULTS["blowers_duct_diameter"],
        "blower_center_offset": DEFAULTS["blower_center_offset"],
        "feeder_ring_rotation_angle": DEFAULTS["feeder_ring_rotation_angle"],
    }


def _create_part_fan_inputs(sprite_extruder=None):
    if sprite_extruder is None:
        sprite_extruder = create_sprite_extruder_assembly(
            **assembly_kwargs(create_sprite_extruder_assembly)
        )

    front_part_fan = create_single_part_fan_assembly(
        **assembly_kwargs(create_single_part_fan_assembly)
    )
    front_part_fan.additional_data["part_ref_origin"] = {
        "assembly_name": "single_part_fan_front_left_assembly"
    }
    side_part_fan = create_single_part_fan_assembly(
        **assembly_kwargs(create_single_part_fan_assembly)
    )
    side_part_fan.additional_data["part_ref_origin"] = {
        "assembly_name": "single_part_fan_side_left_assembly"
    }
    blower_ring = create_blower_ring_assembly(
        **assembly_kwargs(create_blower_ring_assembly)
    )
    blower_ring.additional_data["part_ref_origin"] = {
        "assembly_name": "blower_ring_left_assembly"
    }
    return sprite_extruder, front_part_fan, side_part_fan, blower_ring


def _create_part_fans_with_origin():
    sprite_extruder, front_part_fan, side_part_fan, blower_ring = (
        _create_part_fan_inputs()
    )
    part_fans = create_part_fan_assembly(
        **assembly_kwargs(
            create_part_fan_assembly,
            sprite_extruder=sprite_extruder,
            front_part_fan=front_part_fan,
            side_part_fan=side_part_fan,
            blower_ring=blower_ring,
        )
    )
    part_fans.additional_data["part_ref_origin"] = {
        "assembly_name": "part_fan_left_assembly"
    }
    return part_fans


def test_blower_nozzle_tip_scales_increase_with_path_length():
    scales = _blower_nozzle_tip_scales(**_current_blower_path_kwargs())

    assert scales == pytest.approx([0.75, 0.25, 0.63], abs=0.01)
    assert scales[1] < scales[2] < scales[0]
    assert all(0.25 <= scale <= 0.75 for scale in scales)


@pytest.mark.parametrize("tip_scale", [0.25, 0.63, 0.75])
def test_blower_outer_squeeze_preserves_wall_without_changing_airflow(tip_scale):
    inner_radius = DEFAULTS["blowers_duct_diameter"] / 2
    wall = DEFAULTS["blowers_wall"]
    outer_radius = inner_radius + wall

    air_scale = _blower_air_squeeze_scale(
        tip_scale=tip_scale,
        relative_x=0,
        blower_tube_length=20,
    )
    outer_scale = _blower_outer_squeeze_scale(
        air_scale=air_scale,
        blowers_duct_diameter=DEFAULTS["blowers_duct_diameter"],
        blowers_wall=wall,
    )

    assert inner_radius * air_scale == pytest.approx(inner_radius * tip_scale)
    assert outer_radius * outer_scale - inner_radius * air_scale == pytest.approx(wall)


def test_blower_outer_squeeze_is_unsqueezed_when_air_scale_is_unsqueezed():
    outer_scale = _blower_outer_squeeze_scale(
        air_scale=1.0,
        blowers_duct_diameter=DEFAULTS["blowers_duct_diameter"],
        blowers_wall=DEFAULTS["blowers_wall"],
    )

    assert outer_scale == pytest.approx(1.0)


def test_part_fan_promoted_signature_and_defaults_drop_legacy_role_parameters():
    parameters = inspect.signature(create_part_fan_assembly).parameters

    assert "front_part_fan" in parameters
    assert "side_part_fan" in parameters
    assert "blower_ring" in parameters
    assert "part_fan_clearance" not in parameters
    assert "side_part_fan_parameters" not in parameters
    assert "front_part_fan_parameters" not in parameters

    assembly_yaml = (ASSEMBLIES_DIR / "part_fan_assembly.yaml").read_text()
    defaults_yaml = (ASSEMBLIES_DIR / ("idex" + "_parameters.yaml")).read_text()

    assert "part_fan_clearance:" not in assembly_yaml
    assert "part_fan_clearance:" not in defaults_yaml
    assert "side_part_fan_parameters:" not in assembly_yaml
    assert "front_part_fan_parameters:" not in assembly_yaml
    assert "side_part_fan_parameters:" not in defaults_yaml
    assert "front_part_fan_parameters:" not in defaults_yaml
    assert "front_part_fan_mount_plate_cross_oversize:" in defaults_yaml
    assert "side_part_fan_mount_plate_cross_oversize:" in defaults_yaml


def test_single_part_fan_assembly_exposes_body_mount_plate_and_outlet():
    single_part_fan = create_single_part_fan_assembly(
        **assembly_kwargs(create_single_part_fan_assembly)
    )

    assert get_volume(single_part_fan.leader) > 0
    assert {"mount_plate", "outlet"}.issubset(single_part_fan.follower_indices_by_name)

    body_bbox = get_bounding_box(single_part_fan.leader)
    outlet_bbox = get_bounding_box(single_part_fan.get_named_follower("outlet"))

    assert outlet_bbox[0][1] < body_bbox[0][1]


def test_single_part_fan_mount_plate_uses_role_specific_oversize_and_offset():
    baseline_mount_plate = create_single_part_fan_assembly(
        **assembly_kwargs(
            create_single_part_fan_assembly,
            part_fan_mount_plate_blow_direction_offset=0,
            part_fan_mount_plate_blow_direction_oversize=7,
            part_fan_mount_plate_cross_oversize=8,
        )
    ).get_named_follower("mount_plate")
    mount_plate = create_single_part_fan_assembly(
        **assembly_kwargs(
            create_single_part_fan_assembly,
            part_fan_mount_plate_blow_direction_offset=-2,
            part_fan_mount_plate_blow_direction_oversize=7,
            part_fan_mount_plate_cross_oversize=8,
        )
    ).get_named_follower("mount_plate")

    mount_plate_size = get_bounding_box_size(mount_plate)
    mount_plate_center = get_bounding_box_center(mount_plate)

    assert mount_plate_size[0] == pytest.approx(DEFAULTS["part_fan_size"] + 8)
    assert mount_plate_size[1] == pytest.approx(DEFAULTS["part_fan_size"] + 7)
    assert mount_plate_center[1] - get_bounding_box_center(baseline_mount_plate)[
        1
    ] == pytest.approx(2)


def test_single_part_fan_assembly_is_registered_as_standalone():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    single_part_fan_resource = yaml.load(
        (ASSEMBLIES_DIR / "single_part_fan_assembly.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )

    single_part_fan = assemblies["single_part_fan_assembly"]

    assert single_part_fan["resource_file"] == "single_part_fan_assembly.yaml"
    assert single_part_fan["depends_on"] == []
    assert "inject_parts" not in single_part_fan
    generator_path = single_part_fan_resource["Parts"]["SinglePartFanAssembly"][
        "Properties"
    ]["Generator"]

    assert generator_path == (
        "mege_ender_3v3ke_idex.designs.assemblies.single_part_fan_assembly."
        "create_single_part_fan_assembly"
    )
    assert ".part_fan_assembly." not in generator_path


def test_blower_ring_assembly_exposes_standalone_ring():
    blower_ring = create_blower_ring_assembly(
        **assembly_kwargs(create_blower_ring_assembly)
    )

    blower_ring_bbox = get_bounding_box(blower_ring.leader)
    blower_ring_size = get_bounding_box_size(blower_ring.leader)
    ring_center_reference = blower_ring.get_named_non_production_part(
        "ring_center_reference"
    )
    ring_center_reference_bbox_size = get_bounding_box_size(ring_center_reference)
    ring_center_reference_center = get_bounding_box_center(ring_center_reference)

    assert get_volume(blower_ring.leader) > 0
    assert blower_ring_bbox[0][2] == pytest.approx(0)
    assert all(size > 0 for size in blower_ring_size)
    assert get_volume(ring_center_reference) == pytest.approx(0.001)
    assert all(size < 0.12 for size in ring_center_reference_bbox_size)
    assert ring_center_reference_center[0] == pytest.approx(0)
    assert ring_center_reference_center[1] == pytest.approx(0)
    assert blower_ring_bbox[0][2] < ring_center_reference_center[2]
    assert ring_center_reference_center[2] < blower_ring_bbox[1][2]


def test_blower_ring_assembly_is_registered_as_standalone():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}
    blower_ring_resource_text = (
        ASSEMBLIES_DIR / "blower_ring_assembly.yaml"
    ).read_text()
    blower_ring_resource = yaml.load(
        blower_ring_resource_text,
        Loader=AssemblyDefaultsLoader,
    )

    for blower_ring_name in [
        "blower_ring_assembly",
        "blower_ring_left_assembly",
        "blower_ring_right_assembly",
    ]:
        blower_ring = assemblies[blower_ring_name]
        assert blower_ring["resource_file"] == "blower_ring_assembly.yaml"
        assert blower_ring["depends_on"] == []
        assert "inject_parts" not in blower_ring

    generator_path = blower_ring_resource["Parts"]["BlowerRingAssembly"]["Properties"][
        "Generator"
    ]

    assert generator_path == (
        "mege_ender_3v3ke_idex.designs.assemblies.blower_ring_assembly."
        "create_blower_ring_assembly"
    )
    assert ".part_fan_assembly." not in generator_path
    assert "duct_extension_width" not in blower_ring_resource_text
    assert "part_fan_duct_extension_length" not in blower_ring_resource_text


def test_part_fan_assembly_fuses_and_consumes_selected_injected_artifacts():
    sprite_extruder, front_part_fan, side_part_fan, blower_ring = (
        _create_part_fan_inputs(
            sprite_extruder=LeaderFollowersCuttersPart(create_box(1, 1, 1))
        )
    )
    side_outlet = side_part_fan.get_named_follower("outlet")
    side_outlet_bbox = get_bounding_box(side_outlet)
    side_outlet_center = get_bounding_box_center(side_outlet)
    ring_center = get_bounding_box_center(
        blower_ring.get_named_non_production_part("ring_center_reference")
    )

    part_fans = create_part_fan_assembly(
        **assembly_kwargs(
            create_part_fan_assembly,
            sprite_extruder=sprite_extruder,
            front_part_fan=front_part_fan,
            side_part_fan=side_part_fan,
            blower_ring=blower_ring,
        )
    )
    part_fans_bbox = get_bounding_box(part_fans.leader)
    connector_axis = (
        0
        if abs(ring_center[0] - side_outlet_center[0])
        >= abs(ring_center[1] - side_outlet_center[1])
        else 1
    )

    assert get_volume(part_fans.leader) > 0
    assert {"side_mount_plate", "duct_back_mount_plate_connector"}.issubset(
        part_fans.non_production_indices_by_name
    )
    assert get_volume(part_fans.get_named_non_production_part("side_mount_plate")) > 0
    assert (
        get_volume(
            part_fans.get_named_non_production_part("duct_back_mount_plate_connector")
        )
        > 0
    )
    if ring_center[connector_axis] > side_outlet_center[connector_axis]:
        assert part_fans_bbox[1][connector_axis] > side_outlet_bbox[1][connector_axis]
    else:
        assert part_fans_bbox[0][connector_axis] < side_outlet_bbox[0][connector_axis]
    assert part_fans.consumed_part_refs() == [
        "single_part_fan_front_left_assembly.followers.mount_plate",
        "single_part_fan_front_left_assembly.followers.outlet",
        "single_part_fan_side_left_assembly.followers.mount_plate",
        "single_part_fan_side_left_assembly.followers.outlet",
        "blower_ring_left_assembly.leader",
        "blower_ring_left_assembly.followers.feeder_ring",
    ]


def test_part_fan_resource_has_canonical_generator_and_consumption_visualization():
    resource_text = (ASSEMBLIES_DIR / "part_fan_assembly.yaml").read_text()
    resource = yaml.load(resource_text, Loader=AssemblyDefaultsLoader)

    assert not (ASSEMBLIES_DIR / ("part_fan_assembly" + "_v2.yaml")).exists()
    assert "Collection" not in resource["Builder"]
    assert resource["Builder"]["Production"]["parts"] == [
        {
            "source": "self",
            "artifact": "leader",
            "name": "blower_ducts",
            "prod_rotation_angle": 50,
            "prod_rotation_axis": [1, 0, 0],
        }
    ]
    generator_path = resource["Parts"]["PartFanAssembly"]["Properties"]["Generator"]
    assert generator_path == (
        "mege_ender_3v3ke_idex.designs.assemblies.part_fan_assembly."
        "create_part_fan_assembly"
    )

    visualization_parts = resource["Builder"]["Visualization"]["parts"]
    assert visualization_parts[:2] == [
        {
            "source": "self",
            "artifact": "leader",
            "name": "part_fan",
        },
        {
            "source": "self",
            "artifact": "non_production_parts",
            "name_template": "{name}",
        },
    ]
    assert visualization_parts[2:] == [
        {
            "source": "injected",
            "assembly": "sprite_extruder",
            "artifact": "all",
            "name_template": "sprite_extruder_{name}",
        },
        {
            "source": "injected",
            "assembly": "front_part_fan",
            "artifact": "leader",
            "name": "front_part_fan",
        },
        {
            "source": "injected",
            "assembly": "front_part_fan",
            "artifact": "followers",
            "name_template": "front_part_fan_{name}",
        },
        {
            "source": "injected",
            "assembly": "side_part_fan",
            "artifact": "leader",
            "name": "side_part_fan",
        },
        {
            "source": "injected",
            "assembly": "side_part_fan",
            "artifact": "followers",
            "name_template": "side_part_fan_{name}",
        },
        {
            "source": "injected",
            "assembly": "blower_ring",
            "artifact": "leader",
            "name": "blower_ring",
        },
    ]
    assert resource["Parameters"] == {
        "duct_extension_width": {"Type": "Float"},
        "part_fan_duct_extension_length": {"Type": "Float"},
        "feeder_ring_height": {"Type": "Float"},
        "feeder_ring_wall": {"Type": "Float"},
        "tool_head_additional_mount_plate_clearance": {"Type": "Float"},
        "tool_head_additional_mount_plate_depth": {"Type": "Float"},
        "tool_head_additional_mount_plate_depth_offset": {"Type": "Float"},
        "tool_head_additional_mount_plate_height": {"Type": "Float"},
        "tool_head_additional_mount_plate_thickness": {"Type": "Float"},
        "tool_head_back_mount_plate_connector_height": {"Type": "Float"},
        "tool_head_back_mount_plate_connector_thickness": {"Type": "Float"},
        "tool_head_back_mount_plate_connector_width": {"Type": "Float"},
        "duct_back_mount_plate_height": {"Type": "Float"},
        "duct_back_mount_plate_height_border": {"Type": "Float"},
        "duct_back_mount_plate_offset": {"Type": "Float"},
        "duct_back_mount_plate_thickness": {"Type": "Float"},
        "duct_back_mount_plate_width": {"Type": "Float"},
        "duct_back_mount_plate_width_border": {"Type": "Float"},
    }


def test_part_fan_assemblies_are_registered_with_standalone_fans():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    for fan_name in [
        "single_part_fan_front_left_assembly",
        "single_part_fan_front_right_assembly",
        "single_part_fan_side_left_assembly",
        "single_part_fan_side_right_assembly",
    ]:
        fan = assemblies[fan_name]
        assert fan["resource_file"] == "single_part_fan_assembly.yaml"
        assert fan["depends_on"] == []
        assert "inject_parts" not in fan

    assert assemblies["single_part_fan_front_left_assembly"]["parameters"] == {
        "part_fan_mount_plate_blow_direction_offset": {
            "$ref": "front_part_fan_mount_plate_blow_direction_offset"
        },
        "part_fan_mount_plate_blow_direction_oversize": {
            "$ref": "front_part_fan_mount_plate_blow_direction_oversize"
        },
        "part_fan_mount_plate_cross_oversize": {
            "$ref": "front_part_fan_mount_plate_cross_oversize"
        },
    }
    assert assemblies["single_part_fan_side_left_assembly"]["parameters"] == {
        "part_fan_mount_plate_blow_direction_offset": {
            "$ref": "side_part_fan_mount_plate_blow_direction_offset"
        },
        "part_fan_mount_plate_blow_direction_oversize": {
            "$ref": "side_part_fan_mount_plate_blow_direction_oversize"
        },
        "part_fan_mount_plate_cross_oversize": {
            "$ref": "side_part_fan_mount_plate_cross_oversize"
        },
    }

    for blower_ring_name in [
        "blower_ring_left_assembly",
        "blower_ring_right_assembly",
    ]:
        blower_ring = assemblies[blower_ring_name]
        assert blower_ring["resource_file"] == "blower_ring_assembly.yaml"
        assert blower_ring["depends_on"] == []
        assert "inject_parts" not in blower_ring

    expected_v2 = {
        "left": {
            "mount_chain": [
                "x_axis_rail_assembly",
                "x_axis_left_carriage_assembly",
                "tool_head_mount_machined_bottom_assembly",
            ],
            "sprite": "sprite_extruder_left_assembly",
            "front": "single_part_fan_front_left_assembly",
            "side": "single_part_fan_side_left_assembly",
            "blower_ring": "blower_ring_left_assembly",
        },
        "right": {
            "mount_chain": [
                "x_axis_rail_assembly",
                "x_axis_right_carriage_assembly",
                "tool_head_mount_machined_top_assembly",
            ],
            "sprite": "sprite_extruder_right_assembly",
            "front": "single_part_fan_front_right_assembly",
            "side": "single_part_fan_side_right_assembly",
            "blower_ring": "blower_ring_right_assembly",
        },
    }
    for side, expected in expected_v2.items():
        assert f"part_fan_{side}_assembly" + "_v2" not in assemblies
        assembly = assemblies[f"part_fan_{side}_assembly"]
        assert assembly["resource_file"] == "part_fan_assembly.yaml"
        assert assembly["depends_on"] == (
            expected["mount_chain"]
            + [
                expected["sprite"],
                expected["front"],
                expected["side"],
                expected["blower_ring"],
            ]
        )
        assert assembly["inject_parts"] == {
            "sprite_extruder": expected["sprite"],
            "front_part_fan": expected["front"],
            "side_part_fan": expected["side"],
            "blower_ring": expected["blower_ring"],
        }


def test_part_fan_v2_standalone_fans_use_parameterized_legacy_pose():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    placements = config["placement"]["alignments"]

    front_rotation = {
        "$expr": {
            "$sub": "180 - ${part_fan_v2_front_rotation}",
        },
    }
    front_translation = [
        0,
        {"$ref": "part_fan_v2_front_y_shift"},
        {"$ref": "part_fan_v2_front_z_shift"},
    ]
    side_translation = [
        0,
        {"$ref": "part_fan_v2_side_y_shift"},
        0,
    ]
    blower_ring_translation = [
        0,
        0,
        {"$ref": "part_fan_ducts_clearance"},
    ]

    expected_front_targets = {
        "left": "sprite_extruder_left_assembly.non_production_parts.hotend",
        "right": "sprite_extruder_right_assembly.non_production_parts.hotend",
    }

    for side, target in expected_front_targets.items():
        fan_name = f"single_part_fan_front_{side}_assembly"
        rotation_step = next(
            placement
            for placement in placements
            if placement.get("part") == fan_name and "post_rotation" in placement
        )
        assert rotation_step["post_rotation"] == {
            "angle": front_rotation,
            "axis": [1, 0, 0],
        }
        assert "center" not in rotation_step["post_rotation"]

        fan_steps = [
            placement
            for placement in placements
            if placement.get("part") == fan_name and placement.get("to") == target
        ]
        assert [(step["alignment"], step.get("axes")) for step in fan_steps] == [
            ("CENTER", [0]),
            ("BOTTOM", None),
            ("STACK_FRONT", None),
        ]
        assert fan_steps[-1]["post_translation"] == front_translation

    for side in ["left", "right"]:
        fan_name = f"single_part_fan_side_{side}_assembly"
        rotation_steps = [
            placement["post_rotation"]
            for placement in placements
            if placement.get("part") == fan_name and "post_rotation" in placement
        ]
        assert rotation_steps == [
            {"angle": 90, "axis": [0, 0, 1]},
            {"angle": 90, "axis": [0, 1, 0]},
        ]

        mount_plate_steps = [
            placement
            for placement in placements
            if placement.get("part") == f"{fan_name}.followers.mount_plate"
            and placement.get("to") == f"sprite_extruder_{side}_assembly"
        ]
        assert [step["alignment"] for step in mount_plate_steps] == [
            "FRONT",
            "STACK_RIGHT",
        ]
        assert mount_plate_steps[-1]["stack_gap"] == {
            "$ref": "part_fan_v2_side_stack_gap"
        }
        assert mount_plate_steps[-1]["post_translation"] == side_translation

        blower_ring_name = f"blower_ring_{side}_assembly"
        hotend_target = f"sprite_extruder_{side}_assembly.non_production_parts.hotend"
        ring_center_steps = [
            placement
            for placement in placements
            if placement.get("part")
            == f"{blower_ring_name}.non_production_parts.ring_center_reference"
            and placement.get("to") == hotend_target
        ]
        assert [
            (step["alignment"], step.get("axes")) for step in ring_center_steps
        ] == [("CENTER", [0, 1])]

        ring_leader_steps = [
            placement
            for placement in placements
            if placement.get("part") == blower_ring_name
            and placement.get("to") == hotend_target
        ]
        assert [
            (step["alignment"], step.get("axes")) for step in ring_leader_steps
        ] == [("BOTTOM", None)]
        assert ring_leader_steps[-1]["post_translation"] == blower_ring_translation

    for side in ["left", "right"]:
        fan_group = {
            f"single_part_fan_front_{side}_assembly",
            f"single_part_fan_side_{side}_assembly",
            f"blower_ring_{side}_assembly",
        }
        rigid_step = next(
            placement
            for placement in placements
            if set(placement.get("rigid_group", [])) == fan_group
        )
        assert rigid_step["to"] == f"sprite_extruder_{side}_assembly"


def test_part_fans_preserve_joiner_anchor_markers_in_leader():
    part_fans = _create_part_fans_with_origin()

    for marker_name in ["side_mount_plate", "duct_back_mount_plate_connector"]:
        marker = part_fans.get_named_non_production_part(marker_name)
        assert get_volume(marker) > 0
        assert (
            get_volume(part_fans.leader) - get_volume(part_fans.leader.cut(marker)) > 1
        )


def test_part_fan_cage_joiner_adds_split_flange_without_mutating_inputs():
    part_fans = _create_part_fans_with_origin()
    extruder_cage = LeaderFollowersCuttersPart(
        translate(100, 100, 100)(create_box(5, 5, 5))
    )

    original_part_fan_volume = get_volume(part_fans.leader)
    original_cage_volume = get_volume(extruder_cage.leader)
    original_part_fan_non_production_names = dict(
        part_fans.non_production_indices_by_name
    )

    result = join_part_fans_with_extruder_cage(
        part_fans=part_fans,
        extruder_cage=extruder_cage,
    )

    assert set(result) == {"part_fans", "extruder_cage"}
    assert result["part_fans"] is not part_fans
    assert result["extruder_cage"] is not extruder_cage
    assert get_volume(part_fans.leader) == pytest.approx(original_part_fan_volume)
    assert get_volume(extruder_cage.leader) == pytest.approx(original_cage_volume)
    assert (
        part_fans.non_production_indices_by_name
        == original_part_fan_non_production_names
    )

    joined_part_fans = result["part_fans"]
    joined_extruder_cage = result["extruder_cage"]
    assert get_volume(joined_part_fans.leader) > original_part_fan_volume
    assert get_volume(joined_extruder_cage.leader) > original_cage_volume

    side_mount_plate = part_fans.get_named_non_production_part("side_mount_plate")
    bottom_flange, top_flange, clearance_hole = _create_join_flange_halves(
        side_mount_plate=side_mount_plate,
        flange_extension=8.0,
        flange_half_height=3.0,
        screw_size="M3",
        clearance_type="loose",
    )
    side_mount_plate_depth = get_bounding_box_size(side_mount_plate)[1]

    assert get_volume(bottom_flange) > 8.0 * side_mount_plate_depth * 3.0
    assert get_volume(top_flange) > 8.0 * side_mount_plate_depth * 3.0

    fan_bottom_delta = get_volume(joined_part_fans.leader) - get_volume(
        joined_part_fans.leader.cut(bottom_flange)
    )
    fan_top_delta = get_volume(joined_part_fans.leader) - get_volume(
        joined_part_fans.leader.cut(top_flange)
    )
    cage_top_delta = get_volume(joined_extruder_cage.leader) - get_volume(
        joined_extruder_cage.leader.cut(top_flange)
    )
    cage_bottom_delta = get_volume(joined_extruder_cage.leader) - get_volume(
        joined_extruder_cage.leader.cut(bottom_flange)
    )

    assert fan_bottom_delta > 1
    assert abs(fan_top_delta) < 0.01
    assert cage_top_delta > 1
    assert abs(cage_bottom_delta) < 0.01
    assert (
        abs(
            get_volume(joined_part_fans.leader)
            - get_volume(joined_part_fans.leader.cut(clearance_hole))
        )
        < 0.01
    )
    assert (
        abs(
            get_volume(joined_extruder_cage.leader)
            - get_volume(joined_extruder_cage.leader.cut(clearance_hole))
        )
        < 0.01
    )


def test_part_fan_cage_joiner_signature_has_no_tap_dependencies():
    parameters = inspect.signature(join_part_fans_with_extruder_cage).parameters

    assert "mgn7h_rail_with_carriage" not in parameters
    assert "idex_tap_t1" not in parameters
    assert "opb991t11z_sensor" not in parameters
