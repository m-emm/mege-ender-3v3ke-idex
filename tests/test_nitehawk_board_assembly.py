import inspect

import pytest
from assembly_defaults import assembly_kwargs
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_board_assembly import (
    create_nitehawk_board_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.nitehawk_holder_assembly import (
    create_nitehawk_holder_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.sprite_extruder_assembly import (
    create_sprite_extruder_assembly,
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

REMOVED_HOLDER_BOARD_PARAMETERS = [
    "nitehawk_front_cutter_back_width",
    "nitehawk_front_cutter_width",
    "nitehawk_front_cutter_y_size",
    "nitehawk_heater_connector_length",
    "nitehawk_heater_connector_thickness",
    "nitehawk_heater_connector_width",
    "nitehawk_heater_connector_x_offset_from_right",
    "nitehawk_heater_connector_y_offset_from_front",
    "nitehawk_height",
    "nitehawk_hole_diameter",
    "nitehawk_holes_y_offset",
    "nitehawk_pcb_thickness",
    "nitehawk_plug_length",
    "nitehawk_plug_overhang",
    "nitehawk_plug_thickness",
    "nitehawk_plug_width",
    "nitehawk_top_width",
    "nitehawk_umbilical_cable_diameter",
    "nitehawk_umbilical_cable_length",
    "nitehawk_umbilical_connector_cable_connector_end_diameter",
    "nitehawk_umbilical_connector_cable_connector_height",
    "nitehawk_umbilical_connector_gap",
    "nitehawk_umbilical_connector_height",
    "nitehawk_width",
]


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


def test_nitehawk_holder_accepts_injected_board_and_republishes_parts():
    parameters = inspect.signature(create_nitehawk_holder_assembly).parameters

    assert "nitehawk_board" in parameters
    for parameter_name in REMOVED_HOLDER_BOARD_PARAMETERS:
        assert parameter_name not in parameters

    sprite_extruder = create_sprite_extruder_assembly(
        **assembly_kwargs(create_sprite_extruder_assembly)
    )
    nitehawk_board = create_nitehawk_board_assembly(
        **assembly_kwargs(create_nitehawk_board_assembly)
    )
    holder = create_nitehawk_holder_assembly(
        **assembly_kwargs(
            create_nitehawk_holder_assembly,
            sprite_extruder=sprite_extruder,
            nitehawk_board=nitehawk_board,
        )
    )

    assert get_volume(holder.leader) > 0
    holder.get_non_production_part_by_name("nitehawk_pcb")
    for follower_name in BOARD_FOLLOWERS - {"pcb"}:
        holder.get_non_production_part_by_name(f"nitehawk_board_{follower_name}")
    assert "nitehawk_embellishments" not in holder.non_production_indices_by_name
