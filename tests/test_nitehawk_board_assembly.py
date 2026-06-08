import pytest
from assembly_defaults import assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_board_assembly import (
    create_nitehawk_board_assembly,
)
from shellforgepy.simple import get_bounding_box_center, get_volume


BOARD_FOLLOWERS = {
    "pcb",
    "plug",
    "umbilical_connector",
    "umbilical_cable_connector",
    "umbilical_cable",
    "heater_connector",
}

def test_nitehawk_board_exposes_individual_visual_parts_and_mount_holes():
    board_kwargs = assembly_kwargs(create_nitehawk_board_assembly)
    board = create_nitehawk_board_assembly(**board_kwargs)

    assert get_volume(board.leader) > 0
    assert set(board.follower_indices_by_name) == BOARD_FOLLOWERS
    assert set(board.cutter_indices_by_name) == {"hole_1", "hole_2"}

    hole_1_center = get_bounding_box_center(board.get_cutter_part_by_name("hole_1"))
    hole_2_center = get_bounding_box_center(board.get_cutter_part_by_name("hole_2"))

    assert hole_1_center[0] < hole_2_center[0]
    assert hole_2_center[0] - hole_1_center[0] == pytest.approx(
        board_kwargs["nitehawk_holes_center_distance"]
    )
