import inspect

import pytest
import yaml
from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.extruder_cage_assembly import (
    create_extruder_cage_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_board_assembly import (
    create_nitehawk_board_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.sprite_extruder_assembly import (
    create_sprite_extruder_assembly,
)
from shellforgepy.simple import (
    Alignment,
    align,
    get_bounding_box,
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
    rotate,
    translate,
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
    "nitehawk_holder_extruder_gap",
]


def _recut_delta(part, cutter):
    return get_volume(part) - get_volume(part.cut(cutter))


def _place_nitehawk_board_like_graph(nitehawk_board, sprite_extruder):
    nitehawk_board = rotate(-90, axis=(1, 0, 0))(nitehawk_board)
    nitehawk_board = rotate(180, axis=(0, 1, 0))(nitehawk_board)
    nitehawk_board = align(nitehawk_board, sprite_extruder, Alignment.LEFT)
    nitehawk_board = align(
        nitehawk_board,
        sprite_extruder,
        Alignment.STACK_BACK,
        stack_gap=DEFAULTS["nitehawk_board_extruder_back_gap"],
    )
    nitehawk_board = align(nitehawk_board, sprite_extruder, Alignment.BOTTOM)
    return translate(
        0,
        0,
        DEFAULTS["nitehawk_board_extruder_body_bottom_offset"],
    )(nitehawk_board)


def test_extruder_cage_signature_uses_cage_owned_mount_dimensions():
    parameters = inspect.signature(create_extruder_cage_assembly).parameters

    assert "nitehawk_board" in parameters
    assert "extruder_cage_mount_plate_fillet_radius" in parameters
    for parameter_name in REMOVED_CAGE_PARAMETERS:
        assert parameter_name not in parameters


def test_extruder_cage_exposes_mounting_interfaces_and_screw_visuals():
    sprite_extruder = create_sprite_extruder_assembly(
        **assembly_kwargs(create_sprite_extruder_assembly)
    )
    nitehawk_board = create_nitehawk_board_assembly(
        **assembly_kwargs(create_nitehawk_board_assembly)
    )
    nitehawk_board = _place_nitehawk_board_like_graph(nitehawk_board, sprite_extruder)
    cage_kwargs = assembly_kwargs(
        create_extruder_cage_assembly,
        sprite_extruder=sprite_extruder,
        nitehawk_board=nitehawk_board,
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
    nitehawk_pcb_bbox = get_bounding_box(nitehawk_board.get_named_follower("pcb"))
    nitehawk_board_holes = sorted(
        [
            nitehawk_board.get_named_cutter("hole_1"),
            nitehawk_board.get_named_cutter("hole_2"),
        ],
        key=lambda hole: get_bounding_box_center(hole)[0],
    )
    nitehawk_board_hole_centers = [
        get_bounding_box_center(hole) for hole in nitehawk_board_holes
    ]

    assert nitehawk_hole_0_center[0] < nitehawk_hole_1_center[0]
    assert nitehawk_hole_1_center[0] - nitehawk_hole_0_center[0] == pytest.approx(
        cage_kwargs["nitehawk_holes_center_distance"]
    )
    assert (nitehawk_hole_0_center[0] + nitehawk_hole_1_center[0]) / 2 == pytest.approx(
        nitehawk_mount_plate_center[0]
    )
    for cage_hole_center, board_hole_center in zip(
        [nitehawk_hole_0_center, nitehawk_hole_1_center],
        nitehawk_board_hole_centers,
    ):
        assert cage_hole_center[0] == pytest.approx(board_hole_center[0])
        assert cage_hole_center[2] == pytest.approx(board_hole_center[2])
    assert nitehawk_mount_plate_bbox[1][1] == pytest.approx(nitehawk_pcb_bbox[0][1])

    board_translation = (3, 4, 2)
    shifted_nitehawk_board = translate(*board_translation)(nitehawk_board)
    shifted_cage = create_extruder_cage_assembly(
        **assembly_kwargs(
            create_extruder_cage_assembly,
            sprite_extruder=sprite_extruder,
            nitehawk_board=shifted_nitehawk_board,
        )
    )
    shifted_mount_plate_center = get_bounding_box_center(
        shifted_cage.get_follower_part_by_name("nitehawk_rear_mount_plate")
    )
    shifted_hole_0_center = get_bounding_box_center(
        shifted_cage.get_named_cutter("nitehawk_mount_hole_0")
    )
    for axis, translation in enumerate(board_translation):
        assert shifted_mount_plate_center[axis] - nitehawk_mount_plate_center[
            axis
        ] == pytest.approx(translation)
        assert shifted_hole_0_center[axis] - nitehawk_hole_0_center[
            axis
        ] == pytest.approx(translation)

    for cutter_name in [
        "mount_hole_cutter",
        "nitehawk_mount_hole_0",
        "nitehawk_mount_hole_1",
        "nitehawk_mount_nut_pocket_0",
        "nitehawk_mount_nut_pocket_1",
    ]:
        recut_delta = _recut_delta(cage.leader, cage.get_named_cutter(cutter_name))
        assert recut_delta < 0.01


def test_extruder_cage_side_variants_inject_side_specific_nitehawk_boards():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    assert assemblies["nitehawk_board_left_assembly"]["resource_file"] == (
        "nitehawk_board_assembly.yaml"
    )
    assert assemblies["nitehawk_board_right_assembly"]["resource_file"] == (
        "nitehawk_board_assembly.yaml"
    )

    assert assemblies["extruder_cage_left_assembly"]["inject_parts"] == {
        "sprite_extruder": "sprite_extruder_left_assembly",
        "nitehawk_board": "nitehawk_board_left_assembly",
    }
    assert assemblies["extruder_cage_right_assembly"]["inject_parts"] == {
        "sprite_extruder": "sprite_extruder_right_assembly",
        "nitehawk_board": "nitehawk_board_right_assembly",
    }

    placements = config["placement"]["alignments"]

    for side in ["left", "right"]:
        board = f"nitehawk_board_{side}_assembly"
        sprite_extruder = f"sprite_extruder_{side}_assembly"
        cage = f"extruder_cage_{side}_assembly"

        left_alignment = next(
            placement
            for placement in placements
            if placement.get("part") == board and placement.get("alignment") == "LEFT"
        )
        assert left_alignment["to"] == sprite_extruder

        back_alignment = next(
            placement
            for placement in placements
            if placement.get("part") == board
            and placement.get("alignment") == "STACK_BACK"
        )
        assert back_alignment["to"] == sprite_extruder
        assert back_alignment["stack_gap"] == {
            "$ref": "nitehawk_board_extruder_back_gap"
        }

        bottom_alignment = next(
            placement
            for placement in placements
            if placement.get("part") == board and placement.get("alignment") == "BOTTOM"
        )
        assert bottom_alignment["to"] == sprite_extruder
        assert bottom_alignment["post_translation"][2] == {
            "$ref": "nitehawk_board_extruder_body_bottom_offset"
        }

        rigid_group = next(
            placement
            for placement in placements
            if placement.get("to") == sprite_extruder
            and cage in placement.get("rigid_group", [])
        )
        assert board in rigid_group["rigid_group"]
