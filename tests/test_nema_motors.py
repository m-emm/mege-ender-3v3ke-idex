from mege_ender_3v3ke_idex.designs.nema_motors import create_nema_composite


def test_create_nema_composite_names_are_unique_across_component_maps():
    motor = create_nema_composite()

    name_groups = [
        set(motor.follower_indices_by_name),
        set(motor.cutter_indices_by_name),
        set(motor.non_production_indices_by_name),
        set(motor.direction_vector_indices_by_name),
    ]
    all_names = [name for group in name_groups for name in group]

    assert len(all_names) == len(set(all_names))
    assert set(motor.follower_indices_by_name) >= {"axle", "coupler", "body"}
    assert set(motor.cutter_indices_by_name) == {
        "body_clearance",
        "front_boss_clearance",
        "axle_clearance",
        "mount_holes",
    }
