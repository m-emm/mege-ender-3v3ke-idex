import pytest

pytest.importorskip("cadquery")

from mege_ender_3v3ke_idex.designs.assemblies.tap_extruder_cage_joiner import (
    join_tap_with_extruder_cage,
)
from shellforgepy.construct.leader_followers_cutters_part import (
    LeaderFollowersCuttersPart,
)
from shellforgepy.simple import create_box, get_volume, translate


def test_tap_extruder_cage_joiner_adds_magnet_counterparts_without_mutation():
    extruder_cage = LeaderFollowersCuttersPart(
        translate(100, 100, 100)(create_box(5, 5, 5))
    )
    sprite_extruder = LeaderFollowersCuttersPart(create_box(20, 20, 20))
    mgn7h_rail_with_carriage = LeaderFollowersCuttersPart(create_box(8, 3, 30))
    mgn7h_rail_with_carriage.add_named_follower(
        translate(0, 0, 4)(create_box(6, 2, 8)),
        "carriage",
    )
    idex_tap = LeaderFollowersCuttersPart(create_box(12, 4, 16))
    opb991t11z_sensor = LeaderFollowersCuttersPart(create_box(5, 4, 8))

    original_cage_volume = get_volume(extruder_cage.leader)
    original_tap_volume = get_volume(idex_tap.leader)
    original_tap_non_production_names = dict(idex_tap.non_production_indices_by_name)

    result = join_tap_with_extruder_cage(
        extruder_cage=extruder_cage,
        sprite_extruder=sprite_extruder,
        mgn7h_rail_with_carriage=mgn7h_rail_with_carriage,
        idex_tap=idex_tap,
        opb991t11z_sensor=opb991t11z_sensor,
    )

    assert set(result) == {"extruder_cage", "idex_tap"}
    assert result["extruder_cage"] is not extruder_cage
    assert result["idex_tap"] is not idex_tap
    assert get_volume(extruder_cage.leader) == pytest.approx(original_cage_volume)
    assert get_volume(idex_tap.leader) == pytest.approx(original_tap_volume)
    assert idex_tap.non_production_indices_by_name == original_tap_non_production_names

    joined_extruder_cage = result["extruder_cage"]
    joined_idex_tap = result["idex_tap"]

    for side in ["LEFT", "RIGHT"]:
        assert (
            f"magnet_screw_{side.lower()}"
            in joined_extruder_cage.non_production_indices_by_name
        )
        assert (
            f"magnet_{side}" not in joined_extruder_cage.non_production_indices_by_name
        )
        assert f"magnet_{side}" in joined_idex_tap.non_production_indices_by_name


def test_tap_extruder_cage_joiner_adds_opb_sensor_holder():
    extruder_cage = LeaderFollowersCuttersPart(create_box(10, 10, 10))
    sprite_extruder = LeaderFollowersCuttersPart(create_box(20, 20, 20))
    idex_tap = LeaderFollowersCuttersPart(create_box(12, 4, 16))
    opb991t11z_sensor = LeaderFollowersCuttersPart(create_box(5, 4, 8))

    without_sensor = join_tap_with_extruder_cage(
        extruder_cage=extruder_cage,
        sprite_extruder=sprite_extruder,
        mgn7h_rail_with_carriage=None,
        idex_tap=idex_tap,
        opb991t11z_sensor=None,
    )
    with_sensor = join_tap_with_extruder_cage(
        extruder_cage=extruder_cage,
        sprite_extruder=sprite_extruder,
        mgn7h_rail_with_carriage=None,
        idex_tap=idex_tap,
        opb991t11z_sensor=opb991t11z_sensor,
    )

    assert get_volume(with_sensor["extruder_cage"].leader) > get_volume(
        without_sensor["extruder_cage"].leader
    )
