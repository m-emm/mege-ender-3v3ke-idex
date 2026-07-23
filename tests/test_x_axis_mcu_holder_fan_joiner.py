import pytest

pytest.importorskip("cadquery")

from mege_ender_3v3ke_idex.designs.assemblies.x_axis_mcu_holder_fan_joiner import (
    join_x_axis_mcu_holder_with_fan,
)
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.simple import create_box, get_volume, translate


def _create_holder():
    holder = LeaderFollowersCuttersPart(
        create_box(40, 4, 40),
        additional_data={
            "part_ref_origin": {"assembly_name": "x_axis_mcu_holder_assembly"},
            "nested": {"values": [1, 2]},
            "consumed_part_refs": ["existing.holder.ref"],
        },
    )
    holder.add_named_follower(create_box(30, 2, 30), "top_lid")
    holder.followers.append(translate(50, 0, 0)(create_box(1, 1, 1)))
    holder.add_named_follower(
        translate(52, 0, 0)(create_box(1, 1, 1)),
        "retained_follower",
    )

    holder.cutters.append(translate(54, 0, 0)(create_box(1, 1, 1)))
    holder.add_named_cutter(
        translate(56, 0, 0)(create_box(1, 1, 1)),
        "retained_cutter",
    )

    holder.add_named_non_production_part(create_box(10, 10, 10), "fan")
    holder.non_production_parts.append(translate(58, 0, 0)(create_box(1, 1, 1)))
    holder.add_named_non_production_part(
        translate(60, 0, 0)(create_box(1, 1, 1)),
        "retained_reference",
    )
    holder.set_hidden_by_default("fan")
    holder.set_hidden_by_default("retained_reference")

    holder.direction_vectors.append((1, 0, 0))
    holder.add_named_direction_vector((0, 1, 0), "retained_direction")
    return holder


def _create_fan():
    fan = LeaderFollowersCuttersPart(
        create_box(10, 10, 10),
        additional_data={
            "part_ref_origin": {"assembly_name": "x_axis_mcu_holder_fan_assembly"}
        },
    )
    fan.add_named_follower(create_box(10, 2, 10), "mount_plate")
    fan.add_named_follower(create_box(8, 8, 8), "outlet")
    fan.add_named_cutter(create_box(4, 20, 4), "fan_hole_cutter")
    return fan


def test_x_axis_mcu_holder_joiner_filters_exactly_and_preserves_copy_state():
    holder = _create_holder()
    fan = _create_fan()
    original_holder_volume = get_volume(holder.leader)
    original_consumed_part_refs = holder.consumed_part_refs()

    result = join_x_axis_mcu_holder_with_fan(
        x_axis_mcu_holder=holder,
        fan=fan,
    )

    joined_holder = result["x_axis_mcu_holder"]
    joined_fan = result["part_fan"]

    assert set(result) == {"x_axis_mcu_holder", "part_fan"}
    assert joined_holder is not holder
    assert joined_fan is not fan
    assert get_volume(holder.leader) == pytest.approx(original_holder_volume)
    assert holder.consumed_part_refs() == original_consumed_part_refs
    assert holder.additional_data["nested"] == {"values": [1, 2]}
    assert holder.hidden_by_default_names == ["fan", "retained_reference"]

    assert set(joined_holder.follower_indices_by_name) == {
        "retained_follower",
        "top_lid",
    }
    assert joined_holder.cutter_indices_by_name == {"retained_cutter": 1}
    assert joined_holder.non_production_indices_by_name == {"retained_reference": 1}
    assert joined_holder.direction_vector_indices_by_name == {"retained_direction": 1}
    assert joined_holder.direction_vectors == [(1, 0, 0), (0, 1, 0)]
    assert len(joined_holder.followers) == len(holder.followers)
    assert len(joined_holder.cutters) == len(holder.cutters)
    assert len(joined_holder.non_production_parts) == (
        len(holder.non_production_parts) - 1
    )

    assert "fan" not in joined_holder.non_production_indices_by_name
    assert joined_holder.hidden_by_default_names == ["retained_reference"]
    assert joined_holder.hidden_by_default_names is not holder.hidden_by_default_names
    assert joined_holder.get_named_follower(
        "retained_follower"
    ) is not holder.get_named_follower("retained_follower")
    assert joined_holder.get_named_non_production_part(
        "retained_reference"
    ) is not holder.get_named_non_production_part("retained_reference")
    assert joined_holder.get_named_follower("top_lid") is not holder.get_named_follower(
        "top_lid"
    )

    assert joined_holder.additional_data["nested"] == {"values": [1, 2]}
    assert (
        joined_holder.additional_data["nested"] is not holder.additional_data["nested"]
    )
    assert joined_holder.consumed_part_refs() == [
        "existing.holder.ref",
        "x_axis_mcu_holder_assembly.followers.top_lid",
        "x_axis_mcu_holder_fan_assembly.followers.mount_plate",
        "x_axis_mcu_holder_fan_assembly.followers.outlet",
    ]
