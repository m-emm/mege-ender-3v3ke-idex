import inspect

import pytest
from assembly_defaults import assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.extruder_cage_assembly import (
    create_extruder_cage_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.sprite_extruder_assembly import (
    create_sprite_extruder_assembly,
)
from shellforgepy.simple import (
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
)


REMOVED_CAGE_PARAMETERS = [
    "tool_head_mount_base_plate_thickness",
    "tool_head_additional_mount_plate_fillet_radius",
    "tool_head_additional_mount_plate_thickness",
    "tool_head_front_mount_plate_connector_thickness",
    "duct_front_mount_plate_thickness",
    "duct_front_mount_plate_width",
    "holder_mount_plate_thickness",
    "tool_head_front_mount_plate_connector_height",
    "tool_head_front_mount_plate_connector_width",
    "holder_mount_plate_top_offset",
]


def _recut_delta(part, cutter):
    return get_volume(part) - get_volume(part.cut(cutter))


def test_extruder_cage_signature_uses_cage_owned_mount_dimensions():
    parameters = inspect.signature(create_extruder_cage_assembly).parameters

    assert "extruder_cage_mount_plate_fillet_radius" in parameters
    assert "nitehawk_holder_extruder_gap" in parameters
    for parameter_name in REMOVED_CAGE_PARAMETERS:
        assert parameter_name not in parameters


def test_extruder_cage_exposes_mounting_interfaces_and_screw_visuals():
    sprite_extruder = create_sprite_extruder_assembly(
        **assembly_kwargs(create_sprite_extruder_assembly)
    )
    cage_kwargs = assembly_kwargs(
        create_extruder_cage_assembly,
        sprite_extruder=sprite_extruder,
    )

    cage = create_extruder_cage_assembly(**cage_kwargs)

    assert get_volume(cage.leader) > 0
    assert "left_mount_plate" not in cage.follower_indices_by_name
    assert "right_mount_plate" not in cage.follower_indices_by_name

    for follower_name in [
        "sprite_mount_base_plate",
        "part_fan_side_mount_plate",
        "part_fan_front_mount_plate",
        "nitehawk_rear_mount_plate",
    ]:
        cage.get_follower_part_by_name(follower_name)

    for screw_name in [
        "sprite_mount_screw_left",
        "sprite_mount_screw_right",
        "nitehawk_mount_screw_0",
        "nitehawk_mount_screw_1",
    ]:
        cage.get_non_production_part_by_name(screw_name)

    mount_plate_thickness = cage_kwargs["extruder_cage_mount_plate_thickness"]
    sprite_extruder_body_size = get_bounding_box_size(sprite_extruder.leader)
    sprite_mount_base_plate_size = get_bounding_box_size(
        cage.get_follower_part_by_name("sprite_mount_base_plate")
    )
    side_mount_plate_size = get_bounding_box_size(
        cage.get_follower_part_by_name("part_fan_side_mount_plate")
    )
    front_mount_plate_size = get_bounding_box_size(
        cage.get_follower_part_by_name("part_fan_front_mount_plate")
    )

    assert sprite_mount_base_plate_size[1] == pytest.approx(mount_plate_thickness)
    assert side_mount_plate_size[0] == pytest.approx(mount_plate_thickness)
    assert front_mount_plate_size[0] == pytest.approx(sprite_extruder_body_size[0])
    assert front_mount_plate_size[1] == pytest.approx(mount_plate_thickness)

    nitehawk_hole_0_center = get_bounding_box_center(
        cage.get_named_cutter("nitehawk_mount_hole_0")
    )
    nitehawk_hole_1_center = get_bounding_box_center(
        cage.get_named_cutter("nitehawk_mount_hole_1")
    )
    nitehawk_mount_plate_center = get_bounding_box_center(
        cage.get_follower_part_by_name("nitehawk_rear_mount_plate")
    )
    nitehawk_mount_plate_bbox = get_bounding_box(
        cage.get_follower_part_by_name("nitehawk_rear_mount_plate")
    )
    sprite_extruder_bbox = get_bounding_box(sprite_extruder)

    assert nitehawk_hole_0_center[0] < nitehawk_hole_1_center[0]
    assert nitehawk_hole_1_center[0] - nitehawk_hole_0_center[0] == pytest.approx(
        cage_kwargs["nitehawk_holes_center_distance"]
    )
    assert (nitehawk_hole_0_center[0] + nitehawk_hole_1_center[0]) / 2 == pytest.approx(
        nitehawk_mount_plate_center[0]
    )
    assert nitehawk_mount_plate_bbox[0][1] - sprite_extruder_bbox[1][
        1
    ] == pytest.approx(cage_kwargs["nitehawk_holder_extruder_gap"])

    for cutter_name in [
        "mount_hole_cutter",
        "nitehawk_mount_hole_0",
        "nitehawk_mount_hole_1",
        "nitehawk_mount_nut_pocket_0",
        "nitehawk_mount_nut_pocket_1",
    ]:
        recut_delta = _recut_delta(cage.leader, cage.get_named_cutter(cutter_name))
        assert recut_delta < 0.01
