import inspect
from pathlib import Path

import pytest

pytest.importorskip("cadquery")

from assembly_defaults import DEFAULTS, assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.part_fan_cage_joiner import (
    _create_join_flange_halves,
    join_part_fans_with_extruder_cage,
)
from mege_ender_3v3ke_idex.designs.assemblies.part_fan_assembly import (
    _blower_air_squeeze_scale,
    _blower_feeder_ring_path_metrics,
    _blower_nozzle_tip_scales,
    _blower_outer_squeeze_scale,
    create_part_fan_assembly,
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


def test_blower_feeder_ring_path_metrics_match_current_geometry():
    metrics = _blower_feeder_ring_path_metrics(**_current_blower_path_kwargs())

    assert [metric["fan_entry_angle_degrees"] for metric in metrics] == pytest.approx(
        [143.91, 143.91, 143.91],
        abs=0.01,
    )
    assert [metric["nozzle_tip_angle_degrees"] for metric in metrics] == pytest.approx(
        [10.39, 130.39, 250.39],
        abs=0.01,
    )
    assert [metric["path_angle_degrees"] for metric in metrics] == pytest.approx(
        [133.52, 13.52, 106.48],
        abs=0.01,
    )
    assert [metric["path_length"] for metric in metrics] == pytest.approx(
        [57.67, 5.84, 46.00],
        abs=0.05,
    )


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


def test_part_fan_clearance_is_declarative_parameter():
    parameters = inspect.signature(create_part_fan_assembly).parameters

    assert "part_fan_clearance" in parameters
    assert "side_part_fan_parameters" in parameters
    assert "front_part_fan_parameters" in parameters
    assert "left_part_fan_parameters" not in parameters
    assert "right_part_fan_parameters" not in parameters

    assembly_yaml = Path("assembling/assemblies/part_fan_assembly.yaml").read_text()
    defaults_yaml = Path(
        "assembling/assemblies", "idex" + "_parameters.yaml"
    ).read_text()

    assert "part_fan_clearance:" in assembly_yaml
    assert "part_fan_clearance: 0.8" in defaults_yaml
    assert "side_part_fan_parameters:" in assembly_yaml
    assert "front_part_fan_parameters:" in assembly_yaml
    assert "side_part_fan_parameters:" in defaults_yaml
    assert "front_part_fan_parameters:" in defaults_yaml
    assert "left_part_fan_parameters:" not in assembly_yaml
    assert "right_part_fan_parameters:" not in assembly_yaml
    assert "left_part_fan_parameters:" not in defaults_yaml
    assert "right_part_fan_parameters:" not in defaults_yaml


def test_part_fans_use_physical_side_and_front_roles():
    sprite_extruder = create_sprite_extruder_assembly(
        **assembly_kwargs(create_sprite_extruder_assembly)
    )
    part_fans = create_part_fan_assembly(
        **assembly_kwargs(create_part_fan_assembly, sprite_extruder=sprite_extruder)
    )

    hotend_center = get_bounding_box_center(
        sprite_extruder.get_named_non_production_part("hotend")
    )
    sprite_body_bbox = get_bounding_box(sprite_extruder.leader)
    side_fan_center = get_bounding_box_center(
        part_fans.get_named_non_production_part("side_fan")
    )
    front_fan_center = get_bounding_box_center(
        part_fans.get_named_non_production_part("front_fan")
    )

    assert side_fan_center[0] > hotend_center[0]
    assert side_fan_center[1] < hotend_center[1]
    assert front_fan_center[1] < hotend_center[1]
    assert abs(front_fan_center[0] - hotend_center[0]) < DEFAULTS["part_fan_size"] / 2
    assert side_fan_center[1] >= sprite_body_bbox[0][1] - DEFAULTS["part_fan_size"] / 2
    assert front_fan_center[1] >= sprite_body_bbox[0][1] - DEFAULTS["part_fan_size"] / 2


def test_part_fan_cage_joiner_adds_split_flange_without_mutating_inputs():
    sprite_extruder = create_sprite_extruder_assembly(
        **assembly_kwargs(create_sprite_extruder_assembly)
    )
    part_fans = create_part_fan_assembly(
        **assembly_kwargs(create_part_fan_assembly, sprite_extruder=sprite_extruder)
    )
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
        fillet_radius=0.0,
    )
    side_mount_plate_depth = get_bounding_box_size(side_mount_plate)[1]

    assert get_volume(bottom_flange) < 8.0 * side_mount_plate_depth * 3.0
    assert get_volume(top_flange) < 8.0 * side_mount_plate_depth * 3.0

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
