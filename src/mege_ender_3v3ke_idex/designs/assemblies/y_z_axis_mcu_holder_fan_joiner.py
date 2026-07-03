"""Join the Y/Z-axis MCU holder with an inward shifted replacement fan lid."""

import logging

from shellforgepy.simple import *

_logger = logging.getLogger(__name__)

BOARD_HOLDER_LID_THICKNESS = 1.2
DEFAULT_FAN_X_SHIFT = -18.0
DEFAULT_FAN_LID_PATCH_MARGIN = 4.0
DEFAULT_FAN_ROTATION_ANGLE = 90.0


def _copy_holder_without_old_lid_and_fan(y_z_axis_mcu_holder):
    joined_holder = LeaderFollowersCuttersPart(
        y_z_axis_mcu_holder.leader.copy(),
        additional_data=y_z_axis_mcu_holder.additional_data.copy(),
    )

    for name, follower in y_z_axis_mcu_holder.get_named_follower_items():
        if name == "top_lid":
            continue
        joined_holder.add_named_follower(follower.copy(), name)

    for name, cutter in y_z_axis_mcu_holder.get_named_cutter_items():
        joined_holder.add_named_cutter(cutter.copy(), name)

    for (
        name,
        non_production_part,
    ) in y_z_axis_mcu_holder.get_named_non_production_part_items():
        if name == "fan":
            continue
        joined_holder.add_named_non_production_part(non_production_part.copy(), name)

    return joined_holder


def place_y_z_axis_mcu_holder_fan(
    *,
    y_z_axis_mcu_holder,
    fan,
    fan_x_shift=DEFAULT_FAN_X_SHIFT,
    fan_rotation_angle=DEFAULT_FAN_ROTATION_ANGLE,
):
    """Place the replacement fan inside the y/z MCU holder lid."""

    input_top_lid = y_z_axis_mcu_holder.get_named_follower("top_lid")
    placed_fan = rotate(fan_rotation_angle, axis=(0, 0, 1))(fan.copy())
    placed_fan = align(placed_fan, input_top_lid, Alignment.CENTER, axes=[0, 1])
    placed_fan = align(placed_fan, input_top_lid, Alignment.STACK_BOTTOM)
    placed_fan = translate(fan_x_shift, 0, 0)(placed_fan)
    return placed_fan


def _create_lid_patch_plate(reference, input_top_lid, patch_margin):
    reference_size = get_bounding_box_size(reference)
    patch_plate = create_box(
        reference_size[0] + 2 * patch_margin,
        reference_size[1] + 2 * patch_margin,
        BOARD_HOLDER_LID_THICKNESS,
    )
    patch_plate = align(patch_plate, reference, Alignment.CENTER, axes=[0, 1])
    patch_plate = align(patch_plate, input_top_lid, Alignment.TOP)
    return patch_plate


def _create_lid_through_cutter(cutter, input_top_lid):
    lid_through_cutter = cutter.copy()
    lid_through_cutter = align(
        lid_through_cutter,
        input_top_lid,
        Alignment.CENTER,
        axes=[2],
    )
    return lid_through_cutter


def join_y_z_axis_mcu_holder_with_fan(
    *,
    y_z_axis_mcu_holder,
    fan,
    fan_x_shift=DEFAULT_FAN_X_SHIFT,
    fan_lid_patch_margin=DEFAULT_FAN_LID_PATCH_MARGIN,
    fan_rotation_angle=DEFAULT_FAN_ROTATION_ANGLE,
):
    """Return the y/z MCU holder with only the top lid replaced."""

    _logger.info("Joining Y/Z-axis MCU holder with inward shifted replacement fan")

    input_top_lid = y_z_axis_mcu_holder.get_named_follower("top_lid")
    existing_fan = y_z_axis_mcu_holder.get_named_non_production_part("fan")
    placed_fan = place_y_z_axis_mcu_holder_fan(
        y_z_axis_mcu_holder=y_z_axis_mcu_holder,
        fan=fan,
        fan_x_shift=fan_x_shift,
        fan_rotation_angle=fan_rotation_angle,
    )

    joined_holder = _copy_holder_without_old_lid_and_fan(y_z_axis_mcu_holder)
    replacement_top_lid = input_top_lid.copy()

    replacement_top_lid = replacement_top_lid.fuse(
        _create_lid_patch_plate(
            existing_fan,
            input_top_lid,
            fan_lid_patch_margin,
        )
    )
    replacement_top_lid = replacement_top_lid.fuse(
        _create_lid_patch_plate(
            placed_fan.leader,
            input_top_lid,
            fan_lid_patch_margin,
        )
    )

    replacement_top_lid = replacement_top_lid.cut(
        placed_fan.get_named_cutter("fan_hole_cutter")
    )

    for name, cutter in placed_fan.get_named_cutter_items():
        if name.startswith("screw_hole_cutters_"):
            replacement_top_lid = replacement_top_lid.cut(
                _create_lid_through_cutter(cutter, input_top_lid)
            )

    joined_holder.add_named_follower(replacement_top_lid, "top_lid")
    joined_holder.additional_data["replacement_fan_x_shift"] = fan_x_shift
    joined_holder.additional_data["replacement_fan_rotation_angle"] = fan_rotation_angle

    joined_holder.add_consumed_part_ref(
        y_z_axis_mcu_holder.part_ref_for_named_follower("top_lid")
    )
    joined_holder.add_consumed_part_ref(fan.part_ref_for_named_follower("mount_plate"))
    joined_holder.add_consumed_part_ref(fan.part_ref_for_named_follower("outlet"))

    return {
        "y_z_axis_mcu_holder": joined_holder,
        "part_fan": placed_fan.copy(),
    }
