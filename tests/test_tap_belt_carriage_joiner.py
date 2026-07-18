import pytest

pytest.importorskip("cadquery")

from mege_ender_3v3ke_idex.designs.assemblies.tap_belt_carriage_joiner import (
    join_tap_with_belt_carriage,
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


def test_tap_belt_joiner_enlarges_only_tap_box_y_and_preserves_visual_artifacts():
    belt_leader = create_box(30, 14, 4)
    tap_leader = align(create_box(10, 10, 10), belt_leader, Alignment.CENTER)
    idex_tap = LeaderFollowersCuttersPart(tap_leader)
    idex_tap.add_named_follower(create_box(2, 2, 2), "tap_follower")

    belt_carriage = LeaderFollowersCuttersPart(belt_leader)
    belt_carriage.additional_data["assembly_name"] = "belt_carriage_input"
    belt_carriage.add_named_follower(create_box(3, 3, 2), "clamp_base_left")
    belt_carriage.add_named_non_production_part(create_box(2, 2, 2), "clamp_screw")
    belt_carriage.add_named_non_production_part(
        create_box(2, 2, 2),
        "left_bridge_thread_inset_thread_inset",
    )
    belt_carriage.add_named_non_production_part(
        create_box(2, 2, 2),
        "right_clamp_thread_inset_thread_inset",
    )

    original_tap_volume = get_volume(idex_tap.leader)
    original_belt_volume = get_volume(belt_carriage.leader)
    unexpanded_remainder = belt_carriage.leader.cut(
        materialize_bounding_box(idex_tap.leader)
    )
    y_expanded_remainder = belt_carriage.leader.cut(
        materialize_bounding_box(idex_tap.leader, y_enlargement=5)
    )
    xy_expanded_remainder = belt_carriage.leader.cut(
        materialize_bounding_box(
            idex_tap.leader,
            x_enlargement=0.2,
            y_enlargement=5,
        )
    )

    result = join_tap_with_belt_carriage(
        idex_tap=idex_tap,
        belt_carriage=belt_carriage,
    )

    assert set(result) == {"idex_tap", "belt_carriage"}
    assert result["idex_tap"] is not idex_tap
    assert result["belt_carriage"] is not belt_carriage
    assert get_volume(idex_tap.leader) == pytest.approx(original_tap_volume)
    assert get_volume(belt_carriage.leader) == pytest.approx(original_belt_volume)
    assert belt_carriage.follower_indices_by_name == {"clamp_base_left": 0}
    assert belt_carriage.non_production_indices_by_name == {
        "clamp_screw": 0,
        "left_bridge_thread_inset_thread_inset": 1,
        "right_clamp_thread_inset_thread_inset": 2,
    }

    remainder = result["belt_carriage"].leader
    assert get_volume(remainder) == pytest.approx(get_volume(y_expanded_remainder))
    assert get_volume(remainder) < get_volume(unexpanded_remainder)
    assert get_volume(remainder) > get_volume(xy_expanded_remainder)
    assert get_volume(remainder) > 0
    assert get_volume(result["idex_tap"].leader) == pytest.approx(
        original_tap_volume + get_volume(y_expanded_remainder)
    )

    joined_tap = result["idex_tap"]
    joined_belt_carriage = result["belt_carriage"]
    assert "tap_follower" in joined_tap.follower_indices_by_name
    assert "belt_carriage_clamp_base_left" in joined_tap.follower_indices_by_name
    assert "belt_carriage_clamp_screw" in joined_tap.non_production_indices_by_name
    assert joined_belt_carriage.non_production_indices_by_name == {"clamp_screw": 0}
    assert (
        "belt_carriage_left_bridge_thread_inset_thread_inset"
        not in joined_tap.non_production_indices_by_name
    )
    assert (
        "belt_carriage_right_clamp_thread_inset_thread_inset"
        not in joined_tap.non_production_indices_by_name
    )
    assert joined_tap.additional_data["consumed_part_refs"] == [
        "belt_carriage_input.leader"
    ]
