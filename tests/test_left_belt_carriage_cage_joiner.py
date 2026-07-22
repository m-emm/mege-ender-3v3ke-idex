import pytest

pytest.importorskip("cadquery")

from mege_ender_3v3ke_idex.designs.assemblies.left_belt_carriage_cage_joiner import (
    SPRITE_EXTRUDER_CUTTER_Y_ENLARGEMENT,
    join_left_belt_carriage_with_cage,
)
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.simple import (
    Alignment,
    align,
    create_box,
    get_volume,
    materialize_bounding_box,
)


def test_left_belt_carriage_joiner_cuts_and_fuses_remainder_into_cage():
    belt_leader = create_box(30, 14, 4)
    cage_leader = align(create_box(20, 10, 10), belt_leader, Alignment.CENTER)
    sprite_extruder_leader = align(
        create_box(10, 6, 8),
        belt_leader,
        Alignment.CENTER,
    )
    extruder_cage = LeaderFollowersCuttersPart(cage_leader)
    extruder_cage.add_named_follower(create_box(2, 2, 2), "cage_follower")
    sprite_extruder = LeaderFollowersCuttersPart(sprite_extruder_leader)

    belt_carriage = LeaderFollowersCuttersPart(belt_leader)
    belt_carriage.additional_data["assembly_name"] = "belt_carriage_input"
    belt_carriage.add_named_follower(create_box(3, 3, 2), "clamp_base_left")
    belt_carriage.add_named_non_production_part(
        create_box(2, 2, 2),
        "clamp_screw",
    )
    belt_carriage.add_named_non_production_part(
        create_box(2, 2, 2),
        "left_bridge_thread_inset_thread_inset",
    )
    belt_carriage.add_named_non_production_part(
        create_box(2, 2, 2),
        "right_clamp_thread_inset_thread_inset",
    )

    original_cage_volume = get_volume(extruder_cage.leader)
    original_belt_volume = get_volume(belt_carriage.leader)
    sprite_width_remainder = belt_carriage.leader.cut(
        materialize_bounding_box(
            sprite_extruder.leader,
            y_enlargement=SPRITE_EXTRUDER_CUTTER_Y_ENLARGEMENT,
        )
    )
    unexpanded_y_remainder = belt_carriage.leader.cut(
        materialize_bounding_box(sprite_extruder.leader)
    )
    cage_width_remainder = belt_carriage.leader.cut(
        materialize_bounding_box(
            extruder_cage.leader,
            y_enlargement=SPRITE_EXTRUDER_CUTTER_Y_ENLARGEMENT,
        )
    )

    result = join_left_belt_carriage_with_cage(
        extruder_cage=extruder_cage,
        belt_carriage=belt_carriage,
        sprite_extruder=sprite_extruder,
    )

    assert set(result) == {"extruder_cage", "belt_carriage"}
    assert result["extruder_cage"] is not extruder_cage
    assert result["belt_carriage"] is not belt_carriage
    assert get_volume(extruder_cage.leader) == pytest.approx(original_cage_volume)
    assert get_volume(belt_carriage.leader) == pytest.approx(original_belt_volume)
    assert belt_carriage.follower_indices_by_name == {"clamp_base_left": 0}
    assert belt_carriage.non_production_indices_by_name == {
        "clamp_screw": 0,
        "left_bridge_thread_inset_thread_inset": 1,
        "right_clamp_thread_inset_thread_inset": 2,
    }

    remainder = result["belt_carriage"].leader
    assert get_volume(remainder) == pytest.approx(get_volume(sprite_width_remainder))
    assert get_volume(remainder) < get_volume(unexpanded_y_remainder)
    assert get_volume(remainder) > get_volume(cage_width_remainder)
    assert get_volume(remainder) > 0
    expected_fused_cage = extruder_cage.leader.fuse(sprite_width_remainder)
    assert get_volume(result["extruder_cage"].leader) == pytest.approx(
        get_volume(expected_fused_cage)
    )
    assert get_volume(result["extruder_cage"].leader) > original_cage_volume

    joined_cage = result["extruder_cage"]
    joined_belt_carriage = result["belt_carriage"]
    assert "cage_follower" in joined_cage.follower_indices_by_name
    assert "belt_carriage_clamp_base_left" in joined_cage.follower_indices_by_name
    assert "belt_carriage_clamp_screw" in joined_cage.non_production_indices_by_name
    assert joined_belt_carriage.non_production_indices_by_name == {
        "clamp_screw": 0,
        "left_bridge_thread_inset_thread_inset": 1,
        "right_clamp_thread_inset_thread_inset": 2,
    }
    assert (
        "belt_carriage_left_bridge_thread_inset_thread_inset"
        in joined_cage.non_production_indices_by_name
    )
    assert (
        "belt_carriage_right_clamp_thread_inset_thread_inset"
        in joined_cage.non_production_indices_by_name
    )
    assert joined_cage.additional_data["consumed_part_refs"] == [
        "belt_carriage_input.leader"
    ]
