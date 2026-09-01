import pytest

pytest.importorskip("cadquery")

from mege_ender_3v3ke_idex.designs.assemblies.mgn_12_4040_m3_counter_rail_assembly import (
    create_mgn_12_4040_m3_counter_rail_assembly,
)
from shellforgepy.simple import (
    Alignment,
    MScrew,
    align,
    create_cylinder,
    get_bounding_box_center,
    get_bounding_box_size,
    get_volume,
)


@pytest.fixture(scope="module")
def counter_rail():
    return create_mgn_12_4040_m3_counter_rail_assembly()


def test_counter_rail_preserves_insert_references_pitch_and_envelope(counter_rail):
    screw = MScrew.from_size("M3")
    insert_names = [f"insert_{index}_thread_inset" for index in range(3)]
    cutter_names = [f"insert_{index}_assembly_cutter" for index in range(3)]

    assert set(counter_rail.non_production_indices_by_name) == set(insert_names)
    assert set(counter_rail.cutter_indices_by_name) == set(cutter_names)
    assert get_bounding_box_size(counter_rail.leader) == pytest.approx(
        [57.5, 14.0, 8.3]
    )

    insert_centers = [
        get_bounding_box_center(counter_rail.get_named_non_production_part(name))
        for name in insert_names
    ]
    assert [
        insert_centers[index + 1][0] - insert_centers[index][0] for index in range(2)
    ] == pytest.approx([25.0, 25.0])
    assert insert_centers[2][0] - insert_centers[0][0] == pytest.approx(50.0)

    for insert_name, cutter_name in zip(insert_names, cutter_names):
        assert get_bounding_box_size(
            counter_rail.get_named_non_production_part(insert_name)
        ) == pytest.approx(
            [
                screw.thread_inset_hole_diameter,
                screw.thread_inset_hole_diameter,
                screw.thread_inset_length,
            ]
        )
        assert get_bounding_box_size(
            counter_rail.get_named_cutter(cutter_name)
        ) == pytest.approx([5.3, 5.3, 8.3])


def test_counter_rail_restores_material_around_each_insert_pocket(counter_rail):
    screw = MScrew.from_size("M3")
    leader_volume = get_volume(counter_rail.leader)
    pocket_probe_radius = screw.thread_inset_hole_diameter / 2 - 0.1
    boss_material_probe_radius = screw.thread_inset_hole_diameter / 2 + 0.25

    for index in range(3):
        thread_inset = counter_rail.get_named_non_production_part(
            f"insert_{index}_thread_inset"
        )

        pocket_probe = create_cylinder(
            pocket_probe_radius,
            screw.thread_inset_length - 0.5,
        )
        pocket_probe = align(
            pocket_probe,
            thread_inset,
            Alignment.CENTER,
            axes=[0, 1],
        )
        pocket_probe = align(
            pocket_probe,
            counter_rail.leader,
            Alignment.BOTTOM,
        )
        assert leader_volume - get_volume(
            counter_rail.leader.cut(pocket_probe)
        ) == pytest.approx(0, abs=1e-5)

        boss_material_probe = create_cylinder(
            boss_material_probe_radius,
            screw.thread_inset_length - 0.5,
        )
        boss_material_probe = align(
            boss_material_probe,
            thread_inset,
            Alignment.CENTER,
            axes=[0, 1],
        )
        boss_material_probe = align(
            boss_material_probe,
            counter_rail.leader,
            Alignment.BOTTOM,
        )
        assert (
            leader_volume - get_volume(counter_rail.leader.cut(boss_material_probe)) > 1
        )
