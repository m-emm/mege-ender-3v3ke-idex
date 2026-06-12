"""Join the X-axis MCU holder with a replacement part fan lid."""

import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)


def _copy_holder_without_old_lid_and_fan(x_axis_mcu_holder):
    joined_holder = LeaderFollowersCuttersPart(
        x_axis_mcu_holder.leader.copy(),
        additional_data=x_axis_mcu_holder.additional_data.copy(),
    )

    for name, follower in x_axis_mcu_holder.get_named_follower_items():
        if name == "top_lid":
            continue
        joined_holder.add_named_follower(follower.copy(), name)

    for name, cutter in x_axis_mcu_holder.get_named_cutter_items():
        joined_holder.add_named_cutter(cutter.copy(), name)

    for (
        name,
        non_production_part,
    ) in x_axis_mcu_holder.get_named_non_production_part_items():
        if name == "fan":
            continue
        joined_holder.add_named_non_production_part(non_production_part.copy(), name)

    return joined_holder


BOARD_HOLDER_LID_THICKNESS = 1.2

def join_x_axis_mcu_holder_with_fan(
    *,
    x_axis_mcu_holder,
    fan,
    replacement_lid_fillet_radius=3.0,
):
    """Return the X-axis MCU holder with a rough replacement part-fan lid."""

    _logger.info("Joining X-axis MCU holder with replacement part fan")

    input_top_lid = x_axis_mcu_holder.get_named_follower("top_lid")

    joined_holder = _copy_holder_without_old_lid_and_fan(x_axis_mcu_holder)

    top_lid_size = get_bounding_box_size(input_top_lid)
    # replacement_top_lid = create_filleted_box(
    #     top_lid_size[0],
    #     top_lid_size[1],
    #     top_lid_size[2],
    #     fillet_radius=replacement_lid_fillet_radius,
    #     no_fillets_at=[Alignment.TOP, Alignment.BOTTOM],
    # )
    # replacement_top_lid = align(replacement_top_lid, input_top_lid, Alignment.CENTER)

    replacement_top_lid = input_top_lid.copy()

    fan_size = get_bounding_box_size(fan)

    fan_plate = create_box(fan_size[0]+4, BOARD_HOLDER_LID_THICKNESS, fan_size[2]+4)
    fan_plate = align(fan_plate, fan    , Alignment.CENTER)
    fan_plate = align(fan_plate, replacement_top_lid, Alignment.FRONT)

    replacement_top_lid = replacement_top_lid.fuse(fan_plate)

    existing_fan = x_axis_mcu_holder.get_named_non_production_part("fan")

    existing_fan_size = get_bounding_box_size(existing_fan)

    fan_hole_patch_plate = create_box(
        existing_fan_size[0]+4,
        BOARD_HOLDER_LID_THICKNESS,
        existing_fan_size[2]+4,
    )
    fan_hole_patch_plate = align(fan_hole_patch_plate, existing_fan, Alignment.CENTER)
    fan_hole_patch_plate = align(fan_hole_patch_plate, replacement_top_lid, Alignment.FRONT)

    replacement_top_lid = replacement_top_lid.fuse(fan_hole_patch_plate)



    fan_hole_cutter = fan.get_named_cutter("fan_hole_cutter")

    replacement_top_lid = replacement_top_lid.cut(fan_hole_cutter)

    for name, cutter in fan.get_named_cutter_items():
        if name.startswith("screw_hole_cutters_"):
            replacement_top_lid = replacement_top_lid.cut(cutter)

    joined_holder.add_named_follower(replacement_top_lid, "top_lid")

    joined_holder.add_consumed_part_ref(
        x_axis_mcu_holder.part_ref_for_named_follower("top_lid")
    )
    joined_holder.add_consumed_part_ref(fan.part_ref_for_named_follower("mount_plate"))
    joined_holder.add_consumed_part_ref(fan.part_ref_for_named_follower("outlet"))

    joined_part_fan = fan.copy()

    return {
        "x_axis_mcu_holder": joined_holder,
        "part_fan": joined_part_fan,
    }
