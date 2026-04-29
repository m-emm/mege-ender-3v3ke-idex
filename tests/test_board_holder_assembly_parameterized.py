import pytest

from mege_ender_3v3ke_idex.designs.assemblies.board_holder_assembly_parameterized import (
    BoardPlacementSpec,
    BoardSpec,
    PinLineSpec,
    _create_catalog_board,
    create_board_holder_assembly_parameterized,
)
from mege_ender_3v3ke_idex.designs.sil_dil import (
    default_top_pin_length,
    dil_pitch,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_length,
    wire_wrap_pin_side,
)
from shellforgepy.simple import Alignment, get_bounding_box, get_volume


def _dil_board_spec():
    return BoardSpec(
        name="pico",
        board_type="dil",
        params={
            "int_x_distance": 4,
            "num_y_pins": 8,
            "board_thickness": 1.6,
            "board_corner_radius": 1.0,
            "top_pin_length": default_top_pin_length,
            "pin_length": wire_wrap_pin_length,
            "pin_side": wire_wrap_pin_side,
            "base_thickness": wire_wrap_pin_base_thickness,
            "board_cutter_slack": 0.3,
            "base_cutter_slack": 0.3,
        },
    )


def _sil_board_spec():
    return BoardSpec(
        name="tmc",
        board_type="sil",
        params={
            "num_y_pins": 8,
            "board_x_size_in_pins": 6,
            "board_thickness": 1.6,
            "board_corner_radius": 1.0,
            "top_pin_length": default_top_pin_length,
            "pin_length": wire_wrap_pin_length,
            "pin_side": wire_wrap_pin_side,
            "base_thickness": wire_wrap_pin_base_thickness,
            "board_cutter_slack": 0.3,
            "base_cutter_slack": 0.3,
        },
    )


def _build_assembly(
    *,
    board_catalog=None,
    board_placements=None,
    pin_lines=None,
    tpu_cover_cross_strap_pin_indices=None,
):
    if board_catalog is None:
        board_catalog = [_dil_board_spec()]
    if board_placements is None:
        board_placements = [
            BoardPlacementSpec(instance_name="pico_board", board_name="pico")
        ]
    if pin_lines is None:
        pin_lines = []

    return create_board_holder_assembly_parameterized(
        board_catalog=board_catalog,
        board_placements=board_placements,
        pin_lines=pin_lines,
        tpu_cover_cross_strap_pin_indices=tpu_cover_cross_strap_pin_indices,
    )


def test_catalog_boards_expose_normalized_board_and_pins_names():
    dil_board = _create_catalog_board(_dil_board_spec())
    sil_board = _create_catalog_board(_sil_board_spec())

    for board in (dil_board, sil_board):
        board.get_follower_part_by_name("board")
        board.get_follower_part_by_name("pins")
        board.get_cutter_part_by_name("board_cutters")


def test_stack_gap_rastered_places_board_instances_with_expected_pitch_gap():
    assembly = _build_assembly(
        board_catalog=[_dil_board_spec(), _sil_board_spec()],
        board_placements=[
            BoardPlacementSpec(instance_name="pico_board", board_name="pico"),
            BoardPlacementSpec(
                instance_name="tmc_board_1",
                board_name="tmc",
                x_alignment=Alignment.STACK_LEFT,
                stack_gap_rastered=5,
            ),
        ],
    )

    pico_bbox = get_bounding_box(
        assembly.get_named_non_production_part("pico_board_board")
    )
    tmc_bbox = get_bounding_box(
        assembly.get_named_non_production_part("tmc_board_1_board")
    )

    assert pico_bbox[0][0] - tmc_bbox[1][0] == pytest.approx(5 * dil_pitch)


def test_base_size_matches_board_envelope_plus_borders():
    assembly = _build_assembly()

    board_bbox = get_bounding_box(
        assembly.get_named_non_production_part("pico_board_board").fuse(
            assembly.get_named_non_production_part("pico_board_pins")
        )
    )
    base_bbox = get_bounding_box(assembly.leader)

    assert (base_bbox[1][0] - base_bbox[0][0]) == pytest.approx(
        (board_bbox[1][0] - board_bbox[0][0]) + 14.0
    )
    assert (base_bbox[1][1] - base_bbox[0][1]) == pytest.approx(
        (board_bbox[1][1] - board_bbox[0][1]) + 14.0
    )


def test_carrier_border_pin_lines_orient_and_cut_the_base():
    assembly_without_pin_lines = _build_assembly()
    assembly_with_pin_lines = _build_assembly(
        pin_lines=[
            PinLineSpec(
                instance_name="right_pin_line",
                pin_count=10,
                border_alignment=Alignment.RIGHT,
                params={
                    "top_pin_length": default_top_pin_length,
                    "pin_length": wire_wrap_pin_length,
                    "pin_side": wire_wrap_pin_side,
                    "base_thickness": wire_wrap_pin_base_thickness,
                    "base_cutter_slack": 0.3,
                },
            ),
            PinLineSpec(
                instance_name="back_pin_line",
                pin_count=24,
                border_alignment=Alignment.BACK,
                params={
                    "top_pin_length": default_top_pin_length,
                    "pin_length": wire_wrap_pin_length,
                    "pin_side": wire_wrap_pin_side,
                    "base_thickness": wire_wrap_pin_base_thickness,
                    "base_cutter_slack": 0.3,
                },
            ),
        ]
    )

    right_bbox = get_bounding_box(
        assembly_with_pin_lines.get_named_non_production_part("right_pin_line")
    )
    back_bbox = get_bounding_box(
        assembly_with_pin_lines.get_named_non_production_part("back_pin_line")
    )

    assert (right_bbox[1][1] - right_bbox[0][1]) > (right_bbox[1][0] - right_bbox[0][0])
    assert (back_bbox[1][0] - back_bbox[0][0]) > (back_bbox[1][1] - back_bbox[0][1])
    assert get_volume(assembly_with_pin_lines.leader) < get_volume(
        assembly_without_pin_lines.leader
    )


def test_default_tpu_cover_creates_one_centered_cross_strap():
    assembly = _build_assembly()

    straps = assembly.additional_data["tpu_cover_straps"]
    board_bbox = get_bounding_box(
        assembly.get_named_non_production_part("pico_board_board")
    )
    board_center_y = (board_bbox[0][1] + board_bbox[1][1]) / 2

    assert len(straps) == 1
    assert straps[0]["center_y"] == pytest.approx(board_center_y)
    assert straps[0]["pin_index"] is None


def test_explicit_cross_strap_pin_indices_produce_expected_straps():
    assembly = _build_assembly(tpu_cover_cross_strap_pin_indices=[2, 7])

    straps = assembly.additional_data["tpu_cover_straps"]
    board_bbox = get_bounding_box(
        assembly.get_named_non_production_part("pico_board_board")
    )

    assert [strap["pin_index"] for strap in straps] == [2, 7]
    assert [strap["width"] for strap in straps] == pytest.approx([dil_pitch, dil_pitch])

    expected_centers = [
        board_bbox[0][1] + 0.5 * dil_pitch + (pin_index + 0.5) * dil_pitch
        for pin_index in [2, 7]
    ]
    assert [strap["center_y"] for strap in straps] == pytest.approx(expected_centers)


def test_base_has_plug_holes_and_tpu_cover_contains_plug_geometry():
    assembly = _build_assembly()

    assembly.get_cutter_part_by_name("cover_plug_holes")
    cover_bbox = get_bounding_box(assembly.get_follower_part_by_name("tpu_cover"))
    base_bbox = get_bounding_box(assembly.leader)
    non_production_names = {
        name for name, _ in assembly.get_named_non_production_part_items()
    }

    assert cover_bbox[0][2] < base_bbox[1][2]
    assert len(assembly.additional_data["plug_positions"]) == 4
    assert "tpu_cover_plug_0" not in non_production_names
    assert "tpu_cover_strap_0" not in non_production_names


def test_mixed_parameterized_holder_builds_without_raising():
    assembly = _build_assembly(
        board_catalog=[_dil_board_spec(), _sil_board_spec()],
        board_placements=[
            BoardPlacementSpec(instance_name="pico_board", board_name="pico"),
            BoardPlacementSpec(
                instance_name="tmc_board_1",
                board_name="tmc",
                x_alignment=Alignment.STACK_LEFT,
                stack_gap_rastered=5,
            ),
        ],
        pin_lines=[
            PinLineSpec(
                instance_name="right_pin_line",
                pin_count=10,
                border_alignment=Alignment.RIGHT,
                params={
                    "top_pin_length": default_top_pin_length,
                    "pin_length": wire_wrap_pin_length,
                    "pin_side": wire_wrap_pin_side,
                    "base_thickness": wire_wrap_pin_base_thickness,
                    "base_cutter_slack": 0.3,
                },
            ),
            PinLineSpec(
                instance_name="back_pin_line",
                pin_count=24,
                border_alignment=Alignment.BACK,
                params={
                    "top_pin_length": default_top_pin_length,
                    "pin_length": wire_wrap_pin_length,
                    "pin_side": wire_wrap_pin_side,
                    "base_thickness": wire_wrap_pin_base_thickness,
                    "base_cutter_slack": 0.3,
                },
            ),
        ],
        tpu_cover_cross_strap_pin_indices=[2, 7],
    )

    assert get_volume(assembly.leader) > 0
    assembly.get_follower_part_by_name("tpu_cover")
    assembly.get_named_non_production_part("pico_board_board")
    assembly.get_named_non_production_part("pico_board_pins")
    assembly.get_named_non_production_part("tmc_board_1_board")
    assembly.get_named_non_production_part("tmc_board_1_pins")
    assembly.get_named_non_production_part("right_pin_line")
