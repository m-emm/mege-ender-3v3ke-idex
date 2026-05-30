import pytest

from mege_ender_3v3ke_idex.designs.assemblies.board_holder_assembly import (
    BOARD_HOLDER_ELKO_SOCKET_PLATE_MARGIN,
    COVER_PLUG_BOARD_CLEARANCE,
    COVER_PLUG_MIN_DISTANCE,
    _create_cover_plug_positions,
    _create_elko_socket_assemblies_for_tmc_boards,
    board_holder_elko_sleve_wall,
)
from mege_ender_3v3ke_idex.designs.assemblies.sil_clamp_assembly import (
    create_sil_clamp_assembly,
)
from mege_ender_3v3ke_idex.designs.sil_dil import (
    default_top_pin_length,
    dil_pitch,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_length,
    wire_wrap_pin_side,
)
from shellforgepy.simple import (
    LeaderFollowersCuttersPart,
    PartCollector,
    create_box,
    get_bounding_box,
    get_bounding_box_size,
)

TMC_PIN_CUTTER_SLACK = 0.5


def _placeholder_tmc_board(*, origin=(0, 0, -8), y_pins=3):
    board = create_box(
        14,
        (y_pins + 1) * dil_pitch,
        1.0,
        origin=(origin[0], origin[1], origin[2] + wire_wrap_pin_length),
    )
    dil = create_box(
        5 * dil_pitch,
        y_pins * dil_pitch,
        wire_wrap_pin_length,
        origin=origin,
    )
    left_pin_cutters = PartCollector()
    right_pin_cutters = PartCollector()
    for y_index in range(y_pins):
        for pin_cutters, pin_x_offset in [
            (left_pin_cutters, dil_pitch / 2),
            (right_pin_cutters, 5 * dil_pitch - dil_pitch / 2),
        ]:
            pin_cutter = create_box(
                wire_wrap_pin_side + 2 * TMC_PIN_CUTTER_SLACK,
                wire_wrap_pin_side + 2 * TMC_PIN_CUTTER_SLACK,
                wire_wrap_pin_length + 2 * TMC_PIN_CUTTER_SLACK,
                origin=(
                    origin[0]
                    + pin_x_offset
                    - wire_wrap_pin_side / 2
                    - TMC_PIN_CUTTER_SLACK,
                    origin[1]
                    + (y_index + 0.5) * dil_pitch
                    - wire_wrap_pin_side / 2
                    - TMC_PIN_CUTTER_SLACK,
                    origin[2] - TMC_PIN_CUTTER_SLACK,
                ),
            )
            pin_cutters = pin_cutters.fuse(pin_cutter)
            if pin_x_offset < dil_pitch:
                left_pin_cutters = pin_cutters
            else:
                right_pin_cutters = pin_cutters

    board_part = LeaderFollowersCuttersPart(board)
    board_part.add_named_follower(board, "board")
    board_part.add_named_follower(dil, "dil")
    board_part.add_named_cutter(left_pin_cutters, "left_pin_cutters")
    board_part.add_named_cutter(right_pin_cutters, "right_pin_cutters")
    return board_part


def _distance_xy(point_a, point_b):
    x_distance = point_a[0] - point_b[0]
    y_distance = point_a[1] - point_b[1]
    return (x_distance * x_distance + y_distance * y_distance) ** 0.5


def _distance_to_bbox_xy(point, bbox):
    x_distance = max(bbox[0][0] - point[0], 0, point[0] - bbox[1][0])
    y_distance = max(bbox[0][1] - point[1], 0, point[1] - bbox[1][1])
    return (x_distance * x_distance + y_distance * y_distance) ** 0.5


def _contains_point(positions, expected_position):
    return any(
        position[0] == pytest.approx(expected_position[0])
        and position[1] == pytest.approx(expected_position[1])
        for position in positions
    )


def test_cover_plug_positions_are_dense_and_clear_keepouts_without_building_holder():
    cover = create_box(56, 42, 1)
    keepout_bboxes = [
        ((18, 12, -1), (38, 30, 3)),
        ((22, 2, -1), (30, 8, 3)),
    ]
    corner_inset = 5.0
    plug_diameter = 5.0

    plug_positions = _create_cover_plug_positions(
        cover=cover,
        board_keepout_bboxes=keepout_bboxes,
        board_holder_plug_corner_inset=corner_inset,
        board_holder_plug_diameter=plug_diameter,
    )
    cover_bbox = get_bounding_box(cover)
    expected_corner_positions = [
        (cover_bbox[0][0] + corner_inset, cover_bbox[0][1] + corner_inset),
        (cover_bbox[0][0] + corner_inset, cover_bbox[1][1] - corner_inset),
        (cover_bbox[1][0] - corner_inset, cover_bbox[0][1] + corner_inset),
        (cover_bbox[1][0] - corner_inset, cover_bbox[1][1] - corner_inset),
    ]

    assert len(plug_positions) > 4
    for expected_corner_position in expected_corner_positions:
        assert _contains_point(plug_positions, expected_corner_position)

    for plug_index, plug_position in enumerate(plug_positions):
        for other_plug_position in plug_positions[plug_index + 1 :]:
            assert _distance_xy(plug_position, other_plug_position) >= (
                COVER_PLUG_MIN_DISTANCE - 1e-6
            )

    minimum_center_to_keepout_distance = (
        plug_diameter / 2 + COVER_PLUG_BOARD_CLEARANCE
    )
    for plug_position in plug_positions:
        for keepout_bbox in keepout_bboxes:
            assert _distance_to_bbox_xy(plug_position, keepout_bbox) >= (
                minimum_center_to_keepout_distance - 1e-6
            )


def test_additional_pins_base_plate_follower_tracks_the_flat_plate_bottom():
    additional_pins = create_sil_clamp_assembly(
        x_axis_mcu_dil_pitch=dil_pitch,
        x_axis_mcu_wire_wrap_pin_side=wire_wrap_pin_side,
        x_axis_mcu_wire_wrap_pin_length=wire_wrap_pin_length,
        x_axis_mcu_wire_wrap_pin_base_thickness=wire_wrap_pin_base_thickness,
        x_axis_mcu_wire_wrap_pin_base_width=2.5,
        x_axis_mcu_top_pin_length=default_top_pin_length,
        board_holder_additional_pins_num_pins=4,
        board_holder_additional_pins_base_plate_length=5,
        board_holder_base_plate_thickness=2.0,
        BIG_THING=120,
    )

    base_plate_bbox = get_bounding_box(
        additional_pins.get_follower_part_by_name("additional_pins_base_plate")
    )
    leader_bbox = get_bounding_box(additional_pins.leader)

    assert base_plate_bbox[0][2] == pytest.approx(-2.0)
    assert base_plate_bbox[1][2] == pytest.approx(0.0)
    assert leader_bbox[1][2] > base_plate_bbox[1][2]


def test_elko_socket_count_tracks_tmc_board_count_without_full_holder():
    tmc_boards = [
        _placeholder_tmc_board(origin=(0, index * 24, -8))
        for index in range(3)
    ]
    sockets = _create_elko_socket_assemblies_for_tmc_boards(
        positioned_tmc_boards=tmc_boards,
    )

    assert sorted(sockets.non_production_indices_by_name) == [
        "elko_1_elko",
        "elko_2_elko",
        "elko_3_elko",
    ]
    assert sorted(sockets.follower_indices_by_name) == [
        "elko_sleeve_plate_1",
        "elko_sleeve_plate_2",
        "elko_sleeve_plate_3",
    ]
    assert len(sockets.additional_data["socket_plate_bboxes"]) == 3
    assert len(sockets.additional_data["socket_sleeve_bboxes"]) == 3


def test_elko_socket_plate_is_short_and_front_aligned_without_full_holder():
    tmc_board = _placeholder_tmc_board(origin=(10, 20, -8), y_pins=8)
    tmc_dil = tmc_board.get_follower_part_by_name("dil")
    sockets = _create_elko_socket_assemblies_for_tmc_boards(
        positioned_tmc_boards=[tmc_board],
    )

    tmc_dil_bbox = get_bounding_box(tmc_dil)
    tmc_dil_size = get_bounding_box_size(tmc_dil)
    socket_plate_bbox = sockets.additional_data["socket_plate_bboxes"][0]
    socket_plate_size = (
        socket_plate_bbox[1][0] - socket_plate_bbox[0][0],
        socket_plate_bbox[1][1] - socket_plate_bbox[0][1],
        socket_plate_bbox[1][2] - socket_plate_bbox[0][2],
    )

    assert socket_plate_bbox[0][0] == pytest.approx(
        tmc_dil_bbox[0][0] - BOARD_HOLDER_ELKO_SOCKET_PLATE_MARGIN
    )
    assert socket_plate_bbox[1][0] == pytest.approx(
        tmc_dil_bbox[1][0] + BOARD_HOLDER_ELKO_SOCKET_PLATE_MARGIN
    )
    assert socket_plate_bbox[0][1] == pytest.approx(tmc_dil_bbox[0][1])
    assert socket_plate_size[1] < tmc_dil_size[1]
    assert socket_plate_bbox[0][2] == pytest.approx(tmc_dil_bbox[0][2])


def test_elko_socket_pin_holes_use_named_tmc_pin_cutters():
    tmc_board = _placeholder_tmc_board(origin=(10, 20, -8), y_pins=8)
    tmc_dil = tmc_board.get_follower_part_by_name("dil")
    sockets = _create_elko_socket_assemblies_for_tmc_boards(
        positioned_tmc_boards=[tmc_board],
    )

    tmc_dil_bbox = get_bounding_box(tmc_dil)
    socket_plate_bbox = sockets.additional_data["socket_plate_bboxes"][0]

    left_pin_cutters_bbox = get_bounding_box(
        tmc_board.get_cutter_part_by_name("left_pin_cutters")
    )
    right_pin_cutters_bbox = get_bounding_box(
        tmc_board.get_cutter_part_by_name("right_pin_cutters")
    )
    left_pin_cutters_size = get_bounding_box_size(
        tmc_board.get_cutter_part_by_name("left_pin_cutters")
    )

    assert left_pin_cutters_size[0] == pytest.approx(
        wire_wrap_pin_side + 2 * TMC_PIN_CUTTER_SLACK
    )
    assert socket_plate_bbox[0][0] < left_pin_cutters_bbox[0][0]
    assert socket_plate_bbox[1][0] > right_pin_cutters_bbox[1][0]
    assert socket_plate_bbox[0][1] <= left_pin_cutters_bbox[0][1]
    assert socket_plate_bbox[1][1] < tmc_dil_bbox[1][1]


def test_elko_sleeves_center_x_front_align_and_overlap_plate_by_wall():
    tmc_boards = [
        _placeholder_tmc_board(origin=(0, index * 24, -8))
        for index in range(2)
    ]
    sockets = _create_elko_socket_assemblies_for_tmc_boards(
        positioned_tmc_boards=tmc_boards,
    )

    for plate_bbox, sleeve_bbox in zip(
        sockets.additional_data["socket_plate_bboxes"],
        sockets.additional_data["socket_sleeve_bboxes"],
    ):
        assert sleeve_bbox[0][0] + sleeve_bbox[1][0] == pytest.approx(
            plate_bbox[0][0] + plate_bbox[1][0]
        )
        assert sleeve_bbox[0][1] == pytest.approx(plate_bbox[0][1])
        assert sleeve_bbox[1][2] == pytest.approx(
            plate_bbox[0][2] + board_holder_elko_sleve_wall
        )
