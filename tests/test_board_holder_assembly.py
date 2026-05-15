from functools import lru_cache

import pytest

from mege_ender_3v3ke_idex.designs.assemblies.board_holder_assembly import (
    COVER_PLUG_BOARD_CLEARANCE,
    COVER_PLUG_MIN_DISTANCE,
    create_board_holder_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.x_axis_mcu_board_assemblies import (
    create_pico_w_board_assembly,
    create_sil_clamp_assembly,
    create_tmc_board_assembly,
)
from mege_ender_3v3ke_idex.designs.sil_dil import (
    default_top_pin_length,
    dil_pitch,
    wire_wrap_pin_base_thickness,
    wire_wrap_pin_length,
    wire_wrap_pin_side,
)
from shellforgepy.simple import get_bounding_box, get_volume


def _common_board_params():
    return {
        "x_axis_mcu_dil_pitch": dil_pitch,
        "x_axis_mcu_wire_wrap_pin_side": wire_wrap_pin_side,
        "x_axis_mcu_wire_wrap_pin_length": wire_wrap_pin_length,
        "x_axis_mcu_wire_wrap_pin_base_thickness": wire_wrap_pin_base_thickness,
        "x_axis_mcu_wire_wrap_pin_base_width": 2.5,
        "x_axis_mcu_top_pin_length": default_top_pin_length,
        "x_axis_mcu_electronics_holder_slack": 0.55,
        "x_axis_mcu_electronics_board_cutter_slack": 0.3,
        "x_axis_mcu_base_cutter_vertical_slack": 1.2,
    }


@lru_cache(maxsize=None)
def _build_holder(
    *,
    board_holder_tmc_board_count,
    board_holder_pico_to_tmc_gap_x,
    board_holder_tmc_to_additional_pins_gap_x=11.0,
    board_holder_frame_mount_eyes_enabled=False,
    board_holder_frame_mount_eye_width=10.0,
):
    common_board_params = _common_board_params()

    pico_w_board_assembly = create_pico_w_board_assembly(
        **common_board_params,
        x_axis_mcu_pico_board_thickness=1.1,
        x_axis_mcu_pico_board_y_pins=20,
        x_axis_mcu_pico_board_int_width=7,
        x_axis_mcu_pico_board_corner_radius=0.635,
        x_axis_mcu_pico_board_micro_usb_socket_offset=1.3,
        x_axis_mcu_pico_bar_cutter_slack=1.0,
        x_axis_mcu_micro_usb_socket_width=7.0,
        x_axis_mcu_micro_usb_socket_thickness=3.0,
        x_axis_mcu_micro_usb_socket_depth=5.0,
    )
    tmc_board_assembly = create_tmc_board_assembly(
        **common_board_params,
        x_axis_mcu_tmc_board_y_pins=8,
        x_axis_mcu_tmc_board_int_width=5,
        x_axis_mcu_tmc_board_thickness=1.6,
        x_axis_mcu_tmc_board_cooler_size=8.9,
        x_axis_mcu_tmc_board_cooler_height=12,
        x_axis_mcu_tmc_board_chip_thickness=1.8,
        x_axis_mcu_tmc_chip_y_size_rasterized=2.5,
        x_axis_mcu_tmc_current_potentiometer_underside_thickness=1.5,
        x_axis_mcu_tmc_current_potentiometer_underside_size_rasterized=1.2,
    )
    additional_pins_assembly = create_sil_clamp_assembly(
        x_axis_mcu_dil_pitch=dil_pitch,
        x_axis_mcu_wire_wrap_pin_side=wire_wrap_pin_side,
        x_axis_mcu_wire_wrap_pin_length=wire_wrap_pin_length,
        x_axis_mcu_wire_wrap_pin_base_thickness=wire_wrap_pin_base_thickness,
        x_axis_mcu_wire_wrap_pin_base_width=2.5,
        x_axis_mcu_top_pin_length=default_top_pin_length,
        board_holder_additional_pins_num_pins=20,
        board_holder_additional_pins_base_plate_length=6,
        board_holder_base_plate_thickness=3.1,
        BIG_THING=500,
    )

    return create_board_holder_assembly(
        pico_w_board_assembly=pico_w_board_assembly,
        tmc_board_assembly=tmc_board_assembly,
        additional_pins_assembly=additional_pins_assembly,
        board_holder_base_plate_border=11,
        board_holder_base_plate_thickness=3.1,
        board_holder_board_z_offset=0.005,
        board_holder_mount_screw_size="M3",
        board_holder_mount_screw_hole_inset=2.5,
        board_holder_tmc_board_count=board_holder_tmc_board_count,
        board_holder_pico_to_tmc_gap_x=board_holder_pico_to_tmc_gap_x,
        board_holder_tmc_to_additional_pins_gap_x=board_holder_tmc_to_additional_pins_gap_x,
        board_holder_usb_cable_hole_width=10,
        board_holder_usb_cable_hole_height=10,
        x_axis_mcu_dil_pitch=dil_pitch,
        board_holder_tpu_cover_thickness=1.4,
        board_holder_tpu_cover_gap_above_base=1.5,
        board_holder_tpu_cover_pin_overlap_in_pitches=0.5,
        board_holder_tpu_cover_cross_strap_width_in_pitches=1.0,
        board_holder_plug_corner_inset=5.0,
        board_holder_plug_diameter=5.0,
        board_holder_plug_angle_deg=5.0,
        board_holder_plug_height=4.0,
        board_holder_plug_wall_thickness=1.2,
        board_holder_plug_base_thickness=0.8,
        board_holder_plug_slit_width=1.0,
        board_holder_plug_fillet_radius=0.5,
        board_holder_plug_lip_height=0.8,
        board_holder_plug_lip_size=0.5,
        board_holder_plug_lip_top_gap=1.0,
        board_holder_plug_no_inner_hole=False,
        board_holder_plug_hole_slack=0.1,
        board_holder_frame_mount_eyes_enabled=board_holder_frame_mount_eyes_enabled,
        board_holder_frame_mount_eye_screw_size="M5",
        board_holder_frame_mount_eye_width=board_holder_frame_mount_eye_width,
        board_holder_frame_mount_eye_thickness=4.0,
        board_holder_frame_mount_eye_fillet_radius=3.0,
        BIG_THING=500,
    )


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


def _tmc_follower_prefix(tmc_index):
    if tmc_index == 0:
        return "tmc_board"
    return f"tmc_board_{tmc_index + 1}"


def _elko_names(assembly):
    return sorted(
        name
        for name in assembly.non_production_indices_by_name
        if name.startswith("elko_") and name.endswith("_elko")
    )


def test_pico_to_tmc_gap_x_controls_the_board_to_board_spacing():
    configured_gap = 7.25
    assembly = _build_holder(
        board_holder_tmc_board_count=1,
        board_holder_pico_to_tmc_gap_x=configured_gap,
    )

    pico_board_bbox = get_bounding_box(
        assembly.get_follower_part_by_name("pico_board_board")
    )
    tmc_board_bbox = get_bounding_box(
        assembly.get_follower_part_by_name("tmc_board_board")
    )

    assert tmc_board_bbox[0][0] - pico_board_bbox[1][0] == pytest.approx(configured_gap)


def test_automatic_cover_plugs_are_dense_and_clear_keepouts():
    assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
    )

    plug_positions = [
        tuple(plug_position)
        for plug_position in assembly.additional_data["plug_positions"]
    ]
    cover_bbox = get_bounding_box(assembly.get_follower_part_by_name("tpu_cover"))
    corner_inset = 5.0
    expected_corner_positions = [
        (cover_bbox[0][0] + corner_inset, cover_bbox[0][1] + corner_inset),
        (cover_bbox[0][0] + corner_inset, cover_bbox[1][1] - corner_inset),
        (cover_bbox[1][0] - corner_inset, cover_bbox[0][1] + corner_inset),
        (cover_bbox[1][0] - corner_inset, cover_bbox[1][1] - corner_inset),
    ]

    assert len(plug_positions) > 9
    for expected_corner_position in expected_corner_positions:
        assert _contains_point(plug_positions, expected_corner_position)

    for plug_index, plug_position in enumerate(plug_positions):
        for other_plug_position in plug_positions[plug_index + 1 :]:
            assert _distance_xy(plug_position, other_plug_position) >= (
                COVER_PLUG_MIN_DISTANCE - 1e-6
            )

    keepout_bboxes = [
        get_bounding_box(assembly.get_follower_part_by_name("pico_board_board")),
        get_bounding_box(assembly.get_follower_part_by_name("tmc_board_board")),
        get_bounding_box(assembly.get_follower_part_by_name("tmc_board_2_board")),
        get_bounding_box(
            assembly.get_non_production_part_by_name("additional_pins_pins")
        ),
        get_bounding_box(
            assembly.get_non_production_part_by_name("additional_pins_top_pins")
        ),
        assembly.additional_data["usb_cover_bridge_keepout_bbox"],
    ]
    minimum_center_to_keepout_distance = 2.5 + COVER_PLUG_BOARD_CLEARANCE
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
        board_holder_additional_pins_num_pins=20,
        board_holder_additional_pins_base_plate_length=6,
        board_holder_base_plate_thickness=3.1,
        BIG_THING=500,
    )

    base_plate_bbox = get_bounding_box(
        additional_pins.get_follower_part_by_name("additional_pins_base_plate")
    )
    leader_bbox = get_bounding_box(additional_pins.leader)

    assert base_plate_bbox[0][2] == pytest.approx(-3.1)
    assert base_plate_bbox[1][2] == pytest.approx(0.0)
    assert leader_bbox[1][2] > base_plate_bbox[1][2]


def test_tmc_row_keeps_the_same_front_back_story_as_before():
    assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
    )

    pico_board_bbox = get_bounding_box(
        assembly.get_follower_part_by_name("pico_board_board")
    )
    first_tmc_board_bbox = get_bounding_box(
        assembly.get_follower_part_by_name("tmc_board_board")
    )
    second_tmc_board_bbox = get_bounding_box(
        assembly.get_follower_part_by_name("tmc_board_2_board")
    )

    row_front = min(first_tmc_board_bbox[0][1], second_tmc_board_bbox[0][1])
    row_back = max(first_tmc_board_bbox[1][1], second_tmc_board_bbox[1][1])

    assert row_front == pytest.approx(pico_board_bbox[0][1])
    assert row_back == pytest.approx(pico_board_bbox[1][1])


def test_elko_socket_count_tracks_tmc_board_count():
    for tmc_board_count in [2, 3]:
        assembly = _build_holder(
            board_holder_tmc_board_count=tmc_board_count,
            board_holder_pico_to_tmc_gap_x=11.43,
        )

        assembly.get_follower_part_by_name("elko_sleeve_plates")
        assert _elko_names(assembly) == [
            f"elko_{tmc_index + 1}_elko"
            for tmc_index in range(tmc_board_count)
        ]
        assert len(assembly.additional_data["elko_socket_plate_bboxes"]) == (
            tmc_board_count
        )
        assert len(assembly.additional_data["elko_socket_sleeve_bboxes"]) == (
            tmc_board_count
        )


def test_elko_socket_plates_span_the_tmc_pin_fields():
    tmc_board_count = 3
    assembly = _build_holder(
        board_holder_tmc_board_count=tmc_board_count,
        board_holder_pico_to_tmc_gap_x=11.43,
    )

    for tmc_index in range(tmc_board_count):
        tmc_dil_bbox = get_bounding_box(
            assembly.get_follower_part_by_name(
                f"{_tmc_follower_prefix(tmc_index)}_dil"
            )
        )
        socket_plate_bbox = assembly.additional_data["elko_socket_plate_bboxes"][
            tmc_index
        ]

        assert socket_plate_bbox[0][0] < tmc_dil_bbox[0][0]
        assert socket_plate_bbox[1][0] > tmc_dil_bbox[1][0]
        assert socket_plate_bbox[0][1] < tmc_dil_bbox[0][1]
        assert socket_plate_bbox[1][1] > tmc_dil_bbox[1][1]
        assert socket_plate_bbox[0][2] == pytest.approx(tmc_dil_bbox[0][2])


def test_elko_sleeves_fall_back_to_the_fixed_side_wall_envelope():
    assembly = _build_holder(
        board_holder_tmc_board_count=3,
        board_holder_pico_to_tmc_gap_x=11.43,
    )

    side_walls_bbox = get_bounding_box(assembly.get_follower_part_by_name("side_walls"))
    assert assembly.additional_data["elko_socket_placements"] == [
        "side",
        "side",
        "side",
    ]

    for sleeve_bbox in assembly.additional_data["elko_socket_sleeve_bboxes"]:
        for axis in range(3):
            assert sleeve_bbox[0][axis] >= side_walls_bbox[0][axis]
            assert sleeve_bbox[1][axis] <= side_walls_bbox[1][axis]


def test_tmc_to_additional_pins_gap_x_controls_holder_width():
    tighter_assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
        board_holder_tmc_to_additional_pins_gap_x=4.0,
    )
    looser_assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
        board_holder_tmc_to_additional_pins_gap_x=9.5,
    )

    tighter_bbox = get_bounding_box(tighter_assembly.leader)
    looser_bbox = get_bounding_box(looser_assembly.leader)

    tighter_width = tighter_bbox[1][0] - tighter_bbox[0][0]
    looser_width = looser_bbox[1][0] - looser_bbox[0][0]

    assert looser_width - tighter_width == pytest.approx(5.5)


def test_disabled_frame_mount_eyes_do_not_change_side_wall_width():
    baseline_assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
        board_holder_frame_mount_eyes_enabled=False,
        board_holder_frame_mount_eye_width=10.0,
    )
    wider_disabled_assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
        board_holder_frame_mount_eyes_enabled=False,
        board_holder_frame_mount_eye_width=22.0,
    )

    baseline_bbox = get_bounding_box(
        baseline_assembly.get_follower_part_by_name("side_walls")
    )
    wider_disabled_bbox = get_bounding_box(
        wider_disabled_assembly.get_follower_part_by_name("side_walls")
    )

    assert wider_disabled_bbox[0][0] == pytest.approx(baseline_bbox[0][0])
    assert wider_disabled_bbox[1][0] == pytest.approx(baseline_bbox[1][0])


def test_enabled_frame_mount_eyes_expand_side_walls_left_and_right():
    mount_eye_width = 10.0
    disabled_assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
        board_holder_frame_mount_eyes_enabled=False,
        board_holder_frame_mount_eye_width=mount_eye_width,
    )
    enabled_assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
        board_holder_frame_mount_eyes_enabled=True,
        board_holder_frame_mount_eye_width=mount_eye_width,
    )

    disabled_bbox = get_bounding_box(
        disabled_assembly.get_follower_part_by_name("side_walls")
    )
    enabled_bbox = get_bounding_box(
        enabled_assembly.get_follower_part_by_name("side_walls")
    )

    assert disabled_bbox[0][0] - enabled_bbox[0][0] == pytest.approx(mount_eye_width)
    assert enabled_bbox[1][0] - disabled_bbox[1][0] == pytest.approx(mount_eye_width)
    assert enabled_bbox[0][1] == pytest.approx(disabled_bbox[0][1])
    assert enabled_bbox[0][2] == pytest.approx(disabled_bbox[0][2])
    assert enabled_bbox[1][2] == pytest.approx(disabled_bbox[1][2])


def test_exterior_lids_and_mount_hardware_are_exposed():
    assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
    )

    top_lid_bbox = get_bounding_box(assembly.get_follower_part_by_name("top_lid"))
    bottom_lid_bbox = get_bounding_box(assembly.get_follower_part_by_name("bottom_lid"))
    side_walls_bbox = get_bounding_box(assembly.get_follower_part_by_name("side_walls"))

    assembly.get_non_production_part_by_name("mount_screws")
    assembly.get_non_production_part_by_name("mount_nuts")

    assert top_lid_bbox[0][0] == pytest.approx(bottom_lid_bbox[0][0])
    assert top_lid_bbox[1][0] == pytest.approx(bottom_lid_bbox[1][0])
    assert top_lid_bbox[0][1] == pytest.approx(bottom_lid_bbox[0][1])
    assert top_lid_bbox[1][1] == pytest.approx(bottom_lid_bbox[1][1])
    assert top_lid_bbox[1][2] > side_walls_bbox[1][2]
    assert top_lid_bbox[0][2] < side_walls_bbox[1][2]
    assert bottom_lid_bbox[0][2] < side_walls_bbox[0][2]
    assert bottom_lid_bbox[1][2] > side_walls_bbox[0][2]


def test_bottom_lid_clears_fixed_mount_hardware():
    assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
    )

    top_lid = assembly.get_follower_part_by_name("top_lid")
    bottom_lid = assembly.get_follower_part_by_name("bottom_lid")
    bottom_lid_bbox = get_bounding_box(bottom_lid)
    mount_nuts_bbox = get_bounding_box(
        assembly.get_non_production_part_by_name("mount_nuts")
    )

    assert get_volume(bottom_lid) < get_volume(top_lid)
    assert mount_nuts_bbox[0][2] < bottom_lid_bbox[1][2]
    assert bottom_lid_bbox[0][2] < mount_nuts_bbox[1][2]

    clearance_radius = assembly.additional_data["bottom_lid_hardware_clearance_radius"]
    for mount_screw_position in assembly.additional_data["mount_screw_positions"]:
        assert bottom_lid_bbox[0][0] + clearance_radius < mount_screw_position[0]
        assert mount_screw_position[0] < bottom_lid_bbox[1][0] - clearance_radius
        assert bottom_lid_bbox[0][1] + clearance_radius < mount_screw_position[1]
        assert mount_screw_position[1] < bottom_lid_bbox[1][1] - clearance_radius


def test_frame_mount_eyes_do_not_enlarge_exterior_lids():
    disabled_assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
        board_holder_frame_mount_eyes_enabled=False,
    )
    enabled_assembly = _build_holder(
        board_holder_tmc_board_count=2,
        board_holder_pico_to_tmc_gap_x=11.43,
        board_holder_frame_mount_eyes_enabled=True,
        board_holder_frame_mount_eye_width=10.0,
    )

    for lid_name in ["top_lid", "bottom_lid"]:
        disabled_lid_bbox = get_bounding_box(
            disabled_assembly.get_follower_part_by_name(lid_name)
        )
        enabled_lid_bbox = get_bounding_box(
            enabled_assembly.get_follower_part_by_name(lid_name)
        )

        assert enabled_lid_bbox[0][0] == pytest.approx(disabled_lid_bbox[0][0])
        assert enabled_lid_bbox[1][0] == pytest.approx(disabled_lid_bbox[1][0])
        assert enabled_lid_bbox[0][1] == pytest.approx(disabled_lid_bbox[0][1])
        assert enabled_lid_bbox[1][1] == pytest.approx(disabled_lid_bbox[1][1])
