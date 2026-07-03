import pytest
import yaml

pytest.importorskip("cadquery")

from assembly_defaults import (
    ASSEMBLIES_DIR,
    DEFAULTS,
    AssemblyDefaultsLoader,
    assembly_kwargs,
)
from mege_ender_3v3ke_idex.designs.assemblies.board_holder_assembly import (
    create_board_holder_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.mosfet_driver_board_assembly import (
    create_mosfet_driver_board_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.pico_w_board_assembly import (
    create_pico_w_board_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.sil_clamp_assembly import (
    create_sil_clamp_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.single_part_fan_assembly import (
    create_single_part_fan_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.tmc_board_assembly import (
    create_tmc_board_assembly,
)
from mege_ender_3v3ke_idex.designs.assemblies.y_z_axis_mcu_holder_fan_joiner import (
    DEFAULT_FAN_X_SHIFT,
    DEFAULT_FAN_ROTATION_ANGLE,
    _create_lid_through_cutter,
    join_y_z_axis_mcu_holder_with_fan,
    place_y_z_axis_mcu_holder_fan,
)
from shellforgepy.simple import get_bounding_box, get_bounding_box_size, get_volume


def _create_y_z_axis_mcu_holder_base():
    pico_board = create_pico_w_board_assembly(
        **assembly_kwargs(create_pico_w_board_assembly)
    )
    tmc_board = create_tmc_board_assembly(**assembly_kwargs(create_tmc_board_assembly))
    additional_pins = create_sil_clamp_assembly(
        **assembly_kwargs(
            create_sil_clamp_assembly,
            board_holder_additional_pins_num_pins=DEFAULTS[
                "y_z_axis_mcu_holder_additional_pins_num_pins"
            ],
        )
    )
    mosfet_driver_board = create_mosfet_driver_board_assembly(
        **assembly_kwargs(create_mosfet_driver_board_assembly)
    )
    holder = create_board_holder_assembly(
        **assembly_kwargs(
            create_board_holder_assembly,
            pico_w_board_assembly=pico_board,
            tmc_board_assembly=tmc_board,
            additional_pins_assembly=additional_pins,
            mosfet_driver_board_assembly=mosfet_driver_board,
            board_holder_tmc_board_count=DEFAULTS[
                "y_z_axis_mcu_holder_tmc_board_count"
            ],
        )
    )
    holder.additional_data["part_ref_origin"] = {
        "assembly_name": "y_z_axis_mcu_holder_base_assembly"
    }
    return holder


def _create_y_z_axis_mcu_holder_fan():
    fan = create_single_part_fan_assembly(
        **assembly_kwargs(
            create_single_part_fan_assembly,
            part_fan_mount_plate_blow_direction_offset=0,
            part_fan_mount_plate_blow_direction_oversize=5,
            part_fan_mount_plate_cross_oversize=5,
        )
    )
    fan.additional_data["part_ref_origin"] = {
        "assembly_name": "y_z_axis_mcu_holder_fan_assembly"
    }
    return fan


def _bbox_values(part):
    return tuple(value for corner in get_bounding_box(part) for value in corner)


def _bboxes_overlap(part, cutter):
    part_bbox = get_bounding_box(part)
    cutter_bbox = get_bounding_box(cutter)
    return all(
        part_bbox[0][axis] <= cutter_bbox[1][axis]
        and cutter_bbox[0][axis] <= part_bbox[1][axis]
        for axis in range(3)
    )


def _intersection_volume(part, cutter):
    return get_volume(part) - get_volume(part.cut(cutter))


def _assert_no_intersection(part, cutter):
    if not _bboxes_overlap(part, cutter):
        return

    assert _intersection_volume(part, cutter) == pytest.approx(0, abs=0.01)


def _holder_named_parts(holder):
    return {
        **dict(holder.get_named_follower_items()),
        **dict(holder.get_named_non_production_part_items()),
    }


def _plate_by_name(plates, name):
    return next(plate for plate in plates if plate["name"] == name)


def test_y_z_axis_mcu_holder_fan_joiner_only_changes_top_lid_and_fan_visual():
    base_holder = _create_y_z_axis_mcu_holder_base()
    fan = _create_y_z_axis_mcu_holder_fan()

    result = join_y_z_axis_mcu_holder_with_fan(
        y_z_axis_mcu_holder=base_holder,
        fan=fan,
    )

    joined_holder = result["y_z_axis_mcu_holder"]
    joined_fan = result["part_fan"]

    assert set(result) == {"y_z_axis_mcu_holder", "part_fan"}
    assert joined_holder is not base_holder
    assert joined_fan is not fan
    assert get_volume(joined_holder.leader) == pytest.approx(
        get_volume(base_holder.leader)
    )
    assert "fan" not in joined_holder.non_production_indices_by_name
    assert joined_holder.additional_data["replacement_fan_x_shift"] == pytest.approx(
        DEFAULT_FAN_X_SHIFT
    )
    assert joined_holder.additional_data[
        "replacement_fan_rotation_angle"
    ] == pytest.approx(DEFAULT_FAN_ROTATION_ANGLE)

    for name, follower in base_holder.get_named_follower_items():
        joined_follower = joined_holder.get_named_follower(name)
        if name == "top_lid":
            assert get_volume(joined_follower) != pytest.approx(get_volume(follower))
            continue
        assert _bbox_values(joined_follower) == pytest.approx(_bbox_values(follower))
        assert get_volume(joined_follower) == pytest.approx(get_volume(follower))

    for name, part in base_holder.get_named_non_production_part_items():
        if name == "fan":
            continue
        assert _bbox_values(
            joined_holder.get_named_non_production_part(name)
        ) == pytest.approx(_bbox_values(part))

    assert joined_holder.consumed_part_refs() == [
        "y_z_axis_mcu_holder_base_assembly.followers.top_lid",
        "y_z_axis_mcu_holder_fan_assembly.followers.mount_plate",
        "y_z_axis_mcu_holder_fan_assembly.followers.outlet",
    ]


def test_y_z_axis_mcu_holder_replacement_lid_has_through_fan_and_screw_holes():
    base_holder = _create_y_z_axis_mcu_holder_base()
    fan = _create_y_z_axis_mcu_holder_fan()

    result = join_y_z_axis_mcu_holder_with_fan(
        y_z_axis_mcu_holder=base_holder,
        fan=fan,
    )

    base_top_lid = base_holder.get_named_follower("top_lid")
    replacement_top_lid = result["y_z_axis_mcu_holder"].get_named_follower("top_lid")
    placed_fan = result["part_fan"]
    fan_hole_cutter = placed_fan.get_named_cutter("fan_hole_cutter")

    assert _intersection_volume(
        replacement_top_lid,
        fan_hole_cutter,
    ) == pytest.approx(0, abs=0.01)

    screw_cutters = [
        (name, cutter)
        for name, cutter in placed_fan.get_named_cutter_items()
        if name.startswith("screw_hole_cutters_")
    ]
    assert len(screw_cutters) == 4

    top_lid_bbox = get_bounding_box(base_top_lid)
    for _name, cutter in screw_cutters:
        lid_through_cutter = _create_lid_through_cutter(cutter, base_top_lid)
        lid_through_cutter_bbox = get_bounding_box(lid_through_cutter)

        assert lid_through_cutter_bbox[0][2] < top_lid_bbox[0][2]
        assert lid_through_cutter_bbox[1][2] > top_lid_bbox[1][2]
        assert _intersection_volume(
            replacement_top_lid,
            lid_through_cutter,
        ) == pytest.approx(0, abs=0.01)


def test_y_z_axis_mcu_holder_inward_fan_shift_mounts_flush_and_clears_electronics():
    base_holder = _create_y_z_axis_mcu_holder_base()
    fan = _create_y_z_axis_mcu_holder_fan()

    centered_fan_body = place_y_z_axis_mcu_holder_fan(
        y_z_axis_mcu_holder=base_holder,
        fan=fan,
        fan_x_shift=0,
    ).leader
    shifted_fan_body = place_y_z_axis_mcu_holder_fan(
        y_z_axis_mcu_holder=base_holder,
        fan=fan,
    ).leader
    shifted_fan = place_y_z_axis_mcu_holder_fan(
        y_z_axis_mcu_holder=base_holder,
        fan=fan,
    )
    shifted_fan_outlet = shifted_fan.get_named_follower("outlet")
    shifted_fan_bbox = get_bounding_box(shifted_fan_body)
    shifted_fan_outlet_bbox = get_bounding_box(shifted_fan_outlet)
    top_lid_bbox = get_bounding_box(base_holder.get_named_follower("top_lid"))

    middle_cooler = base_holder.get_named_non_production_part("tmc_board_2_cooler")
    assert _intersection_volume(middle_cooler, centered_fan_body) > 50
    assert shifted_fan_bbox[1][2] == pytest.approx(top_lid_bbox[0][2])
    assert shifted_fan_outlet_bbox[1][0] > shifted_fan_bbox[1][0]
    assert (
        get_bounding_box_size(shifted_fan_outlet)[0]
        < get_bounding_box_size(shifted_fan_outlet)[1]
    )

    for cooler_name in [
        "tmc_board_cooler",
        "tmc_board_2_cooler",
        "tmc_board_3_cooler",
    ]:
        cooler = base_holder.get_named_non_production_part(cooler_name)
        cooler_bbox = get_bounding_box(cooler)

        assert _intersection_volume(cooler, shifted_fan_body) == pytest.approx(
            0,
            abs=0.01,
        )
        assert cooler_bbox[0][0] - shifted_fan_bbox[1][0] > 5.0
        assert cooler_bbox[0][0] - shifted_fan_outlet_bbox[1][0] > 2.0

    checked_parts = _holder_named_parts(base_holder)
    for checked_part_name in [
        "tmc_board_cooler",
        "tmc_board_2_cooler",
        "tmc_board_3_cooler",
        "tmc_board_chip",
        "tmc_board_2_chip",
        "tmc_board_3_chip",
        "tmc_board_top_pins",
        "tmc_board_2_top_pins",
        "tmc_board_3_top_pins",
        "mosfet_driver_board_mosfet_package_front",
        "mosfet_driver_board_mosfet_package_back",
        "tpu_cover",
    ]:
        checked_part = checked_parts[checked_part_name]
        _assert_no_intersection(checked_part, shifted_fan_body)
        _assert_no_intersection(checked_part, shifted_fan_outlet)


def test_y_z_axis_mcu_holder_big_fan_is_joined_output_in_assembly_graph():
    config = yaml.load(
        (ASSEMBLIES_DIR / "assemblies.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assemblies = {assembly["name"]: assembly for assembly in config["assemblies"]}

    assert assemblies["y_z_axis_mcu_holder_base_assembly"]["resource_file"] == (
        "board_holder_assembly.yaml"
    )
    assert "y_z_axis_mcu_holder_assembly" not in assemblies

    fan = assemblies["y_z_axis_mcu_holder_fan_assembly"]
    assert fan["resource_file"] == "single_part_fan_assembly.yaml"
    assert fan["parameters"] == {
        "part_fan_mount_plate_blow_direction_offset": 0,
        "part_fan_mount_plate_blow_direction_oversize": 5,
        "part_fan_mount_plate_cross_oversize": 5,
    }

    join = assemblies["y_z_axis_mcu_holder_fan_join"]
    assert join["kind"] == "join"
    assert join["resource_file"] == "y_z_axis_mcu_holder_fan_joiner.yaml"
    assert join["inject_parts"] == {
        "y_z_axis_mcu_holder": "y_z_axis_mcu_holder_base_assembly",
        "fan": "y_z_axis_mcu_holder_fan_assembly",
    }
    assert join["outputs"] == {
        "y_z_axis_mcu_holder": "y_z_axis_mcu_holder_assembly",
        "part_fan": "y_z_axis_mcu_holder_fan_joined_assembly",
    }
    assert {
        "rigid_group": ["y_z_axis_mcu_holder_fan_joined_assembly"],
        "to": "y_z_axis_mcu_holder_assembly",
    } in config["placement"]["alignments"]

    joiner = yaml.load(
        (ASSEMBLIES_DIR / "y_z_axis_mcu_holder_fan_joiner.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    assert joiner["Parameters"]["fan_rotation_angle"]["Default"] == 90.0
    assert {
        "source": "output",
        "assembly": "part_fan",
        "artifact": "leader",
        "name": "part_fan_body",
    } in joiner["Builder"]["Outputs"]["y_z_axis_mcu_holder"]["Visualization"]["parts"]


def test_y_z_axis_mcu_holder_top_lid_plate_uses_tb6600_stock_production_process():
    joiner = yaml.load(
        (ASSEMBLIES_DIR / "y_z_axis_mcu_holder_fan_joiner.yaml").read_text(),
        Loader=AssemblyDefaultsLoader,
    )
    tb6600 = yaml.load(
        (
            ASSEMBLIES_DIR / "tb6600_stripboard_interface_housing_assembly.yaml"
        ).read_text(),
        Loader=AssemblyDefaultsLoader,
    )

    y_z_plates = joiner["Builder"]["Outputs"]["y_z_axis_mcu_holder"]["Production"][
        "arrange"
    ]["plates"]
    y_z_top_lid_plate = _plate_by_name(y_z_plates, "y_z_axis_mcu_holder_top_lid")

    tb6600_plate = _plate_by_name(
        tb6600["Builder"]["Production"]["arrange"]["plates"],
        "tb6600_stripboard_interface_housing",
    )

    assert y_z_top_lid_plate["process_data_preset"] == (
        "petgcf_max_strength_high_speed_06"
    )
    assert y_z_top_lid_plate["parts"] == ["top_lid"]
    assert "_idex" not in yaml.safe_dump(y_z_top_lid_plate)
    assert y_z_top_lid_plate["process_data"]["overrides"]["process_overrides"] == (
        tb6600_plate["process_data"]["overrides"]["process_overrides"]
    )
